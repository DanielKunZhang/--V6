#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import v6b_theme_rotation_backtest as bt
import v6ab_classifier_bridge_backtest as bridge
import v6ab_pit_classifier_bridge_backtest as pit_bridge


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_daily_evolution"
DEFAULT_REPLAY = OUT_DIR / "pit_replay" / "latest_pit_classifier_replay.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def monthly_return(eq: pd.Series, decision_dates: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for idx, raw_date in enumerate(decision_dates[:-1]):
        start = pd.Timestamp(raw_date)
        end = pd.Timestamp(decision_dates[idx + 1])
        if start not in eq.index:
            start_pos = eq.index.searchsorted(start)
            if start_pos >= len(eq.index):
                continue
            start = eq.index[start_pos]
        if end not in eq.index:
            end_pos = eq.index.searchsorted(end)
            if end_pos >= len(eq.index):
                end = eq.index[-1]
            else:
                end = eq.index[end_pos]
        if end <= start:
            continue
        start_val = float(eq.loc[start])
        end_val = float(eq.loc[end])
        if start_val > 0:
            out[str(pd.Timestamp(raw_date).date())] = end_val / start_val - 1.0
    return out


def top_theme_labels(row: dict[str, Any], limit: int = 3) -> str:
    themes = row.get("top_themes", [])[:limit]
    if not themes:
        return ""
    return ", ".join(f"{item.get('theme_id')}:{item.get('selected_proxy')}" for item in themes)


def selected_theme_labels(row: dict[str, Any], limit: int = 3) -> str:
    themes = row.get("selected_themes") or [item for item in row.get("top_themes", []) if item.get("selected")]
    themes = themes[:limit]
    if not themes:
        return top_theme_labels(row, limit=limit)
    return ", ".join(f"{item.get('theme_id')}:{item.get('selected_proxy')}" for item in themes)


def summarize_period(rows: list[dict[str, Any]], start: str, end: str) -> dict[str, Any]:
    seg = [row for row in rows if start <= row["date"] <= end]
    if not seg:
        return {"count": 0}
    deltas = [float(row["hard_minus_v2"]) for row in seg]
    overlay_deltas = [float(row["overlay_minus_v2"]) for row in seg]
    tier_deltas = [float(row["tier_minus_v2"]) for row in seg]
    guarded_deltas = [float(row.get("guarded_minus_v2", 0.0)) for row in seg]
    active = [row for row in seg if row.get("pit_active")]
    tier_active = [row for row in seg if row.get("tier_active")]
    guarded_active = [row for row in seg if row.get("guarded_active")]
    return {
        "count": len(seg),
        "pit_active": len(active),
        "tier_active": len(tier_active),
        "guarded_active": len(guarded_active),
        "hard_avg_delta": float(np.mean(deltas)),
        "hard_sum_delta": float(np.sum(deltas)),
        "overlay_avg_delta": float(np.mean(overlay_deltas)),
        "overlay_sum_delta": float(np.sum(overlay_deltas)),
        "tier_avg_delta": float(np.mean(tier_deltas)),
        "tier_sum_delta": float(np.sum(tier_deltas)),
        "guarded_avg_delta": float(np.mean(guarded_deltas)),
        "guarded_sum_delta": float(np.sum(guarded_deltas)),
        "hard_win_rate": float(np.mean([x > 0 for x in deltas])),
        "overlay_win_rate": float(np.mean([x > 0 for x in overlay_deltas])),
        "tier_win_rate": float(np.mean([x > 0 for x in tier_deltas])),
        "guarded_win_rate": float(np.mean([x > 0 for x in guarded_deltas])),
    }


def build_attribution(args: argparse.Namespace) -> dict[str, Any]:
    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    if not snapshots:
        raise SystemExit(f"empty PIT replay: {args.replay_json}")

    prices = bt.build_price_matrix(pit_bridge.required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    baseline_eq, baseline_decisions = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    hard_eq, hard_decisions = pit_bridge.run_pit_v6b(prices, snapshots, bridge.BASELINE_CONFIG, mode="hard_replace")
    overlay_eq, overlay_decisions = pit_bridge.run_pit_v6b(prices, snapshots, bridge.BASELINE_CONFIG, mode="overlay")
    tier_eq, tier_decisions = pit_bridge.run_pit_v6b(prices, snapshots, bridge.BASELINE_CONFIG, mode="tier")
    guarded_eq, guarded_decisions = pit_bridge.run_pit_v6b(
        prices,
        snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
    )

    decision_dates = [row["date"] for row in baseline_decisions]
    v2_rets = monthly_return(baseline_eq, decision_dates)
    hard_rets = monthly_return(hard_eq, decision_dates)
    overlay_rets = monthly_return(overlay_eq, decision_dates)
    tier_rets = monthly_return(tier_eq, decision_dates)
    guarded_rets = monthly_return(guarded_eq, decision_dates)
    hard_by_date = {row["date"]: row for row in hard_decisions}
    overlay_by_date = {row["date"]: row for row in overlay_decisions}
    tier_by_date = {row["date"]: row for row in tier_decisions}
    guarded_by_date = {row["date"]: row for row in guarded_decisions}
    v2_by_date = {row["date"]: row for row in baseline_decisions}

    rows: list[dict[str, Any]] = []
    for raw_date in decision_dates[:-1]:
        if raw_date not in v2_rets:
            continue
        hard_row = hard_by_date.get(raw_date, {})
        overlay_row = overlay_by_date.get(raw_date, {})
        tier_row = tier_by_date.get(raw_date, {})
        guarded_row = guarded_by_date.get(raw_date, {})
        v2_row = v2_by_date.get(raw_date, {})
        pit_active = bool(hard_row and not hard_row.get("fallback_to_v2", True))
        tier_active = bool(tier_row and not tier_row.get("fallback_to_v2", True))
        guarded_active = bool(guarded_row and not guarded_row.get("fallback_to_v2", True))
        v2_ret = float(v2_rets.get(raw_date, 0.0))
        hard_ret = float(hard_rets.get(raw_date, 0.0))
        overlay_ret = float(overlay_rets.get(raw_date, 0.0))
        tier_ret = float(tier_rets.get(raw_date, 0.0))
        guarded_ret = float(guarded_rets.get(raw_date, 0.0))
        rows.append(
            {
                "date": raw_date,
                "pit_active": pit_active,
                "tier_active": tier_active,
                "guarded_active": guarded_active,
                "pit_allowlist": hard_row.get("pit_allowlist", []),
                "pit_boost_allowlist": hard_row.get("pit_boost_allowlist", []),
                "pit_override_allowlist": hard_row.get("pit_override_allowlist", []),
                "pit_signal_tier": tier_row.get("pit_signal_tier", "WATCH"),
                "guarded_signal_tier": guarded_row.get("pit_signal_tier", "WATCH"),
                "guarded_guard_reason": guarded_row.get("pit_guard_reason", ""),
                "v2_next_ret": v2_ret,
                "hard_next_ret": hard_ret,
                "overlay_next_ret": overlay_ret,
                "tier_next_ret": tier_ret,
                "guarded_next_ret": guarded_ret,
                "hard_minus_v2": hard_ret - v2_ret,
                "overlay_minus_v2": overlay_ret - v2_ret,
                "tier_minus_v2": tier_ret - v2_ret,
                "guarded_minus_v2": guarded_ret - v2_ret,
                "v2_top": top_theme_labels(v2_row),
                "hard_top": top_theme_labels(hard_row),
                "overlay_top": top_theme_labels(overlay_row),
                "tier_top": top_theme_labels(tier_row),
                "guarded_top": top_theme_labels(guarded_row),
                "v2_selected": selected_theme_labels(v2_row),
                "hard_selected": selected_theme_labels(hard_row),
                "overlay_selected": selected_theme_labels(overlay_row),
                "tier_selected": selected_theme_labels(tier_row),
                "guarded_selected": selected_theme_labels(guarded_row),
                "hard_turnover": float(hard_row.get("turnover", 0.0)),
                "overlay_turnover": float(overlay_row.get("turnover", 0.0)),
                "tier_turnover": float(tier_row.get("turnover", 0.0)),
                "guarded_turnover": float(guarded_row.get("turnover", 0.0)),
            }
        )

    active_rows = [row for row in rows if row["pit_active"]]
    worst_hard = sorted(active_rows, key=lambda row: row["hard_minus_v2"])[:12]
    best_hard = sorted(active_rows, key=lambda row: row["hard_minus_v2"], reverse=True)[:12]
    by_tier: dict[str, dict[str, Any]] = {}
    for tier in ["WATCH", "BOOST", "OVERRIDE"]:
        tier_rows = [row for row in rows if row.get("pit_signal_tier") == tier]
        if not tier_rows:
            by_tier[tier] = {"count": 0}
            continue
        deltas = [float(row["tier_minus_v2"]) for row in tier_rows]
        by_tier[tier] = {
            "count": len(tier_rows),
            "sum_delta": float(np.sum(deltas)),
            "avg_delta": float(np.mean(deltas)),
            "win_rate": float(np.mean([value > 0 for value in deltas])),
        }
    guarded_by_tier: dict[str, dict[str, Any]] = {}
    for tier in ["WATCH", "BOOST", "OVERRIDE"]:
        tier_rows = [row for row in rows if row.get("guarded_signal_tier") == tier]
        if not tier_rows:
            guarded_by_tier[tier] = {"count": 0}
            continue
        deltas = [float(row["guarded_minus_v2"]) for row in tier_rows]
        guarded_by_tier[tier] = {
            "count": len(tier_rows),
            "sum_delta": float(np.sum(deltas)),
            "avg_delta": float(np.mean(deltas)),
            "win_rate": float(np.mean([value > 0 for value in deltas])),
        }
    periods = {
        "full": summarize_period(rows, args.start, args.end),
        "2020": summarize_period(rows, "2020-01-01", "2020-12-31"),
        "2022": summarize_period(rows, "2022-01-01", "2022-12-31"),
        "2024_2026": summarize_period(rows, "2024-01-01", args.end),
    }
    return {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "replay_json": str(args.replay_json),
        "periods": periods,
        "tier_summary": by_tier,
        "guarded_tier_summary": guarded_by_tier,
        "pit_active_count": len(active_rows),
        "rows": rows,
        "worst_hard_active_months": worst_hard,
        "best_hard_active_months": best_hard,
    }


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB PIT vs V2 Monthly Attribution",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 区间：`{payload['start']} -> {payload['end']}`",
        f"- PIT active months：`{payload['pit_active_count']}`",
        "- 用途：诊断 PIT 主线识别何时增益/拖累 V2；不作为模拟盘替换依据。",
        "",
        "## Period Summary",
        "",
        "| period | months | PIT active | tier active | guarded active | hard sum delta | overlay sum delta | tier sum delta | guarded sum delta | guarded win |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, row in payload["periods"].items():
        lines.append(
            f"| {name} | {row.get('count', 0)} | {row.get('pit_active', 0)} | {row.get('tier_active', 0)} | {row.get('guarded_active', 0)} | "
            f"{fmt_pct(row.get('hard_sum_delta'))} | {fmt_pct(row.get('overlay_sum_delta'))} | "
            f"{fmt_pct(row.get('tier_sum_delta'))} | {fmt_pct(row.get('guarded_sum_delta'))} | {fmt_pct(row.get('guarded_win_rate'))} |"
        )
    lines += [
        "",
        "## Tier Summary",
        "",
        "| tier | months | sum delta | avg delta | win rate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for tier, row in payload.get("tier_summary", {}).items():
        lines.append(
            f"| `{tier}` | {row.get('count', 0)} | {fmt_pct(row.get('sum_delta'))} | "
            f"{fmt_pct(row.get('avg_delta'))} | {fmt_pct(row.get('win_rate'))} |"
        )
    lines += [
        "",
        "## Guarded Tier Summary",
        "",
        "| tier | months | sum delta | avg delta | win rate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for tier, row in payload.get("guarded_tier_summary", {}).items():
        lines.append(
            f"| `{tier}` | {row.get('count', 0)} | {fmt_pct(row.get('sum_delta'))} | "
            f"{fmt_pct(row.get('avg_delta'))} | {fmt_pct(row.get('win_rate'))} |"
        )
    lines += [
        "",
        "## Worst Active PIT Months",
        "",
        "| date | tier | allowlist | hard-v2 | overlay-v2 | tier-v2 | V2 selected | hard selected | tier selected |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in payload["worst_hard_active_months"]:
        lines.append(
            f"| {row['date']} | `{row.get('pit_signal_tier', '')}` | `{', '.join(row.get('pit_allowlist', []))}` | "
            f"{fmt_pct(row['hard_minus_v2'])} | {fmt_pct(row['overlay_minus_v2'])} | {fmt_pct(row['tier_minus_v2'])} | "
            f"{row.get('v2_selected', row['v2_top'])} | {row.get('hard_selected', row['hard_top'])} | {row.get('tier_selected', row['tier_top'])} |"
        )
    lines += [
        "",
        "## Best Active PIT Months",
        "",
        "| date | tier | allowlist | hard-v2 | overlay-v2 | tier-v2 | V2 selected | hard selected | tier selected |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in payload["best_hard_active_months"]:
        lines.append(
            f"| {row['date']} | `{row.get('pit_signal_tier', '')}` | `{', '.join(row.get('pit_allowlist', []))}` | "
            f"{fmt_pct(row['hard_minus_v2'])} | {fmt_pct(row['overlay_minus_v2'])} | {fmt_pct(row['tier_minus_v2'])} | "
            f"{row.get('v2_selected', row['v2_top'])} | {row.get('hard_selected', row['hard_top'])} | {row.get('tier_selected', row['tier_top'])} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- `hard` 表示 PIT allowlist 硬替换 V2 theme universe。",
        "- `overlay` 表示 STARTER 只扩展候选，不剥夺 V2 原有主线竞争权。",
        "- `tier` 表示 WATCH 不影响、BOOST overlay、OVERRIDE hard replace。",
        "- 若 overlay 明显优于 hard，说明 PIT 证据还只能作为主线候选增强，不能作为排他性过滤器。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Attribute monthly PIT vs V2 differences for V6AB research.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_attribution(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest_pit_vs_v2_attribution.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest_pit_vs_v2_attribution.md").write_text(md, encoding="utf-8")
    pd.DataFrame(payload["rows"]).to_csv(args.output_dir / "latest_pit_vs_v2_attribution.csv", index=False)
    (REPORT_ROOT / "V6AB_PIT_vs_V2_Attribution_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_PIT_vs_V2_Attribution_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
