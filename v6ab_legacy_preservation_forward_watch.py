#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

import v6ab_classifier_bridge_backtest as bridge
import v6ab_legacy_winner_preservation_experiment as legacy
import v6ab_pit_classifier_bridge_backtest as pit_bridge
import v6b_theme_rotation_backtest as bt
from v6ab_pit_vs_v2_attribution import selected_theme_labels


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_legacy_preservation_forward_watch"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2%}"


def by_date(decisions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("date")): row for row in decisions}


def selected_ids(row: dict[str, Any]) -> list[str]:
    themes = row.get("selected_themes") or [item for item in row.get("top_themes", []) if item.get("selected")]
    if not themes:
        themes = row.get("top_themes", [])[:3]
    return [str(item.get("theme_id")) for item in themes if item.get("theme_id")]


def selected_proxies(row: dict[str, Any]) -> list[str]:
    themes = row.get("selected_themes") or [item for item in row.get("top_themes", []) if item.get("selected")]
    if not themes:
        themes = row.get("top_themes", [])[:3]
    return [
        f"{item.get('theme_id')}:{item.get('selected_proxy')}"
        for item in themes
        if item.get("theme_id") and item.get("selected_proxy")
    ]


def row_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "selected": selected_proxies(row),
        "selected_theme_ids": selected_ids(row),
        "weights": row.get("weights", {}),
        "pit_signal_tier": row.get("pit_signal_tier", "WATCH"),
        "pit_active_for_mode": bool(row.get("pit_active_for_mode", False)),
        "fallback_to_v2": bool(row.get("fallback_to_v2", True)),
        "turnover": float(row.get("turnover", 0.0) or 0.0),
    }


def latest_common_date(*decision_lists: list[dict[str, Any]]) -> str:
    common: set[str] | None = None
    for decisions in decision_lists:
        dates = {str(row.get("date")) for row in decisions if row.get("date")}
        common = dates if common is None else common & dates
    if not common:
        raise SystemExit("no common decision date for forward WATCH observation")
    return sorted(common)[-1]


def load_history(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    rows = payload.get("observations", [])
    return rows if isinstance(rows, list) else []


def update_history(history: list[dict[str, Any]], observation: dict[str, Any]) -> list[dict[str, Any]]:
    key = (observation["asof"], observation["decision_date"])
    replaced = False
    out: list[dict[str, Any]] = []
    for row in history:
        if (row.get("asof"), row.get("decision_date")) == key:
            out.append(observation)
            replaced = True
        else:
            out.append(row)
    if not replaced:
        out.append(observation)
    return sorted(out, key=lambda row: (str(row.get("decision_date", "")), str(row.get("asof", ""))))


def build_observation(args: argparse.Namespace) -> dict[str, Any]:
    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    if not snapshots:
        raise SystemExit(f"empty PIT replay: {args.replay_json}")

    prices = bt.build_price_matrix(pit_bridge.required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    baseline_eq, baseline_decisions = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    original_eq, original_decisions = pit_bridge.run_pit_v6b(
        prices,
        snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
    )
    qualified_eq, qualified_decisions = legacy.run_guarded_v6b(
        prices,
        snapshots,
        bridge.BASELINE_CONFIG,
        policy="v2_memory_requires_broad_legacy_confirmation",
    )

    decision_date = latest_common_date(baseline_decisions, original_decisions, qualified_decisions)
    baseline_row = by_date(baseline_decisions)[decision_date]
    original_row = by_date(original_decisions)[decision_date]
    qualified_row = by_date(qualified_decisions)[decision_date]
    protection_applied = bool(qualified_row.get("legacy_preservation_applied", False))
    blocked_theme_ids = sorted(set(selected_ids(original_row)) - set(selected_ids(qualified_row)))
    added_theme_ids = sorted(set(selected_ids(qualified_row)) - set(selected_ids(original_row)))
    blocked_replacements = sorted(set(selected_proxies(original_row)) - set(selected_proxies(qualified_row)))

    observation = {
        "asof": args.asof,
        "decision_date": decision_date,
        "paper_sim_action": "NO_CHANGE",
        "active_paper_sim_baseline": "V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING",
        "watch_candidate": "legacy_preserve_qualified_v6ab_dynamic_b",
        "status": "PROTECTION_TRIGGERED" if protection_applied else "NO_PROTECTION_TRIGGER",
        "pit_asof": qualified_row.get("pit_asof"),
        "pit_boost_allowlist": qualified_row.get("pit_boost_allowlist", []),
        "pit_override_allowlist": qualified_row.get("pit_override_allowlist", []),
        "legacy_preservation_policy": qualified_row.get("legacy_preservation_policy"),
        "legacy_preservation_applied": protection_applied,
        "legacy_preserved_themes": qualified_row.get("legacy_preserved_themes", []),
        "legacy_preservation_candidates": qualified_row.get("legacy_preservation_candidates", []),
        "trigger_reason": qualified_row.get("pit_guard_reason", "") if protection_applied else "",
        "blocked_theme_ids": blocked_theme_ids if protection_applied else [],
        "added_theme_ids": added_theme_ids if protection_applied else [],
        "blocked_replacements": blocked_replacements if protection_applied else [],
        "v2": row_summary(baseline_row),
        "original_pit": row_summary(original_row),
        "qualified_preservation": row_summary(qualified_row),
        "latest_equity": {
            "v2_standalone": float(baseline_eq.iloc[-1]) if len(baseline_eq) else None,
            "original_pit_standalone": float(original_eq.iloc[-1]) if len(original_eq) else None,
            "qualified_preservation_standalone": float(qualified_eq.iloc[-1]) if len(qualified_eq) else None,
        },
        "notes": [
            "Forward WATCH 只记录纸面观察，不改变 V2 模拟盘。",
            "同一 decision_date 在没有新月末价格/证据时可能连续多天重复观察，这是预期行为。",
        ],
    }
    return observation


def render_daily(payload: dict[str, Any]) -> str:
    obs = payload["latest_observation"]
    lines = [
        "# V6AB Qualified Legacy Preservation Forward WATCH",
        "",
        f"- 日期：`{obs['asof']}`",
        f"- 决策截面：`{obs['decision_date']}`",
        f"- WATCH candidate：`{obs['watch_candidate']}`",
        f"- 当前模拟盘：`{obs['active_paper_sim_baseline']}`",
        f"- 模拟盘动作：`{obs['paper_sim_action']}`",
        f"- 状态：`{obs['status']}`",
        "",
        "## 今日三套选择",
        "",
        "| sleeve | signal tier | active | fallback V2 | turnover | selected |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for key, label in [
        ("v2", "V2 baseline"),
        ("original_pit", "Original PIT"),
        ("qualified_preservation", "Qualified preservation"),
    ]:
        row = obs[key]
        lines.append(
            f"| {label} | `{row.get('pit_signal_tier')}` | {row.get('pit_active_for_mode')} | "
            f"{row.get('fallback_to_v2')} | {float(row.get('turnover', 0.0) or 0.0):.2f} | "
            f"{', '.join(row.get('selected', [])) or '-'} |"
        )
    lines += [
        "",
        "## Legacy Protection",
        "",
        f"- triggered：`{obs['legacy_preservation_applied']}`",
        f"- candidates：`{', '.join(obs.get('legacy_preservation_candidates', [])) or '-'}`",
        f"- preserved：`{', '.join(obs.get('legacy_preserved_themes', [])) or '-'}`",
        f"- reason：`{obs.get('trigger_reason') or '-'}`",
        f"- blocked replacement：`{', '.join(obs.get('blocked_replacements', [])) or '-'}`",
        "",
        "## 观察口径",
        "",
        "- 这是 forward paper WATCH，不是 PAPER_SIM_CANDIDATE，不替换 V2。",
        "- 重点看 PIT 是否持续错误挤掉已被 V2 识别的非 AI 主线，以及 qualified 条件是否足够克制。",
    ]
    return "\n".join(lines)


def render_weekly(payload: dict[str, Any]) -> str:
    history = payload.get("history", [])
    if not history:
        return "# V6AB Legacy Preservation Forward WATCH Weekly\n\n- no observations"
    frame = pd.DataFrame(history)
    frame["asof_dt"] = pd.to_datetime(frame["asof"], errors="coerce")
    latest_asof = frame["asof_dt"].max()
    if pd.isna(latest_asof):
        week_rows = history[-5:]
    else:
        latest_period = latest_asof.to_period("W-FRI")
        week_rows = frame[frame["asof_dt"].dt.to_period("W-FRI") == latest_period].to_dict("records")
    triggered = [row for row in week_rows if row.get("legacy_preservation_applied")]
    lines = [
        "# V6AB Legacy Preservation Forward WATCH Weekly",
        "",
        f"- 截止日期：`{payload['latest_observation']['asof']}`",
        f"- 本周观察数：`{len(week_rows)}`",
        f"- protection triggers：`{len(triggered)}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "",
        "## Weekly Rows",
        "",
        "| asof | decision date | status | preserved | blocked | qualified selected |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in week_rows:
        qualified = row.get("qualified_preservation", {}) if isinstance(row.get("qualified_preservation"), dict) else {}
        lines.append(
            f"| `{row.get('asof')}` | `{row.get('decision_date')}` | `{row.get('status')}` | "
            f"`{', '.join(row.get('legacy_preserved_themes', [])) or '-'}` | "
            f"`{', '.join(row.get('blocked_replacements', [])) or '-'}` | "
            f"{', '.join(qualified.get('selected', [])) or '-'} |"
        )
    lines += [
        "",
        "## Weekly Read",
        "",
        "- 连续无触发：说明 qualified 条件没有过度介入，保持观察。",
        "- 有触发：人工复核被拦截的 PIT 替换是否确实属于 AI 子主题过度挤占 legacy 主线。",
    ]
    return "\n".join(lines)


def flatten_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in history:
        rows.append(
            {
                "asof": row.get("asof"),
                "decision_date": row.get("decision_date"),
                "status": row.get("status"),
                "protection_applied": row.get("legacy_preservation_applied"),
                "candidates": ",".join(row.get("legacy_preservation_candidates", [])),
                "preserved": ",".join(row.get("legacy_preserved_themes", [])),
                "blocked": ",".join(row.get("blocked_replacements", [])),
                "v2_selected": ",".join(row.get("v2", {}).get("selected", [])),
                "original_pit_selected": ",".join(row.get("original_pit", {}).get("selected", [])),
                "qualified_selected": ",".join(row.get("qualified_preservation", {}).get("selected", [])),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward paper WATCH ledger for qualified V6AB legacy preservation.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    observation = build_observation(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    history = update_history(load_history(args.output_dir / "latest_history.json"), observation)
    payload = {
        "asof": args.asof,
        "latest_observation": observation,
        "history": history,
    }
    daily_md = render_daily(payload)
    weekly_md = render_weekly(payload)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest_history.json").write_text(
        json.dumps({"observations": history}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (args.output_dir / "latest_history.csv").write_text(
        pd.DataFrame(flatten_history(history)).to_csv(index=False),
        encoding="utf-8",
    )
    (args.output_dir / "latest_daily.md").write_text(daily_md, encoding="utf-8")
    (args.output_dir / "latest_weekly.md").write_text(weekly_md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Legacy_Preservation_Forward_WATCH_Daily_LATEST.md").write_text(daily_md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Legacy_Preservation_Forward_WATCH_Weekly_LATEST.md").write_text(weekly_md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Legacy_Preservation_Forward_WATCH_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(daily_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
