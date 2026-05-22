#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd

import v6ab_classifier_bridge_backtest as bridge
import v6ab_pit_classifier_bridge_backtest as pit
import v6b_theme_rotation_backtest as bt
from v6ab_risk_skill_gate_experiment import (
    active_cap_from_snapshots,
    build_base_curves,
    period_stats,
    run_dynamic_candidate,
)


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_theme_mapping_experiment"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"

PARENT_THEME = {
    "ai_platform": "technology",
    "ai_memory": "semis_ai",
    "ai_networking": "semis_ai",
    "ai_optical": "semis_ai",
    "ai_infra": "semis_ai",
    "ai_power_datacenter": "utilities_power",
    "robotics_automation": "industrials_infra",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):+.2%}"


def theme_by_id(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("theme")): row for row in snap.get("themes", []) if row.get("theme")}


def map_allowlist(
    snap: dict[str, Any],
    rule: Callable[[str, dict[str, Any], dict[str, Any]], str],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    item = copy.deepcopy(snap)
    by_theme = theme_by_id(item)
    before_boost = list(item.get("boost_allowlist", []))
    before_override = list(item.get("override_allowlist", []))
    after_boost: list[str] = []
    mapped: list[dict[str, Any]] = []
    for theme in before_boost:
        mapped_theme = rule(theme, by_theme.get(theme, {}), item)
        if mapped_theme != theme:
            mapped.append({"from": theme, "to": mapped_theme})
        if mapped_theme not in after_boost:
            after_boost.append(mapped_theme)
    item["boost_allowlist"] = after_boost
    if mapped:
        return item, {
            "asof": item.get("asof"),
            "mapped": mapped,
            "before_boost": before_boost,
            "after_boost": after_boost,
            "before_override": before_override,
            "after_override": before_override,
        }
    return item, None


def apply_mapping(
    snapshots: list[dict[str, Any]],
    name: str,
    rule: Callable[[str, dict[str, Any], dict[str, Any]], str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for snap in snapshots:
        item, changed = map_allowlist(snap, rule)
        out.append(item)
        if changed:
            rows.append(changed)
    return out, {"candidate": name, "changed_snapshots": len(rows), "mapped_rows": rows}


def identity_rule(theme: str, detail: dict[str, Any], snap: dict[str, Any]) -> str:
    return theme


def platform_low_fact_to_technology(theme: str, detail: dict[str, Any], snap: dict[str, Any]) -> str:
    if theme == "ai_platform" and float(detail.get("fact_precision_score", 0.0) or 0.0) < 35:
        return "technology"
    return theme


def ai_child_low_fact_to_parent(theme: str, detail: dict[str, Any], snap: dict[str, Any]) -> str:
    if theme in PARENT_THEME and float(detail.get("fact_precision_score", 0.0) or 0.0) < 35:
        return PARENT_THEME[theme]
    return theme


def ai_child_no_override_to_parent(theme: str, detail: dict[str, Any], snap: dict[str, Any]) -> str:
    if snap.get("override_allowlist"):
        return theme
    return PARENT_THEME.get(theme, theme)


def ai_child_no_entry_to_parent(theme: str, detail: dict[str, Any], snap: dict[str, Any]) -> str:
    if theme in PARENT_THEME and str(detail.get("entry_quality_action", "")) == "NO_ENTRY_EDGE":
        return PARENT_THEME[theme]
    return theme


def summarize(
    name: str,
    standalone_eq: pd.Series,
    v6ab_eq: pd.Series,
    decisions: list[dict[str, Any]],
    baseline_v6ab: pd.Series,
    guarded_v6ab: pd.Series,
    args: argparse.Namespace,
    meta: dict[str, Any],
) -> dict[str, Any]:
    stats = bt.stats(v6ab_eq)
    baseline_stats = bt.stats(baseline_v6ab)
    guarded_stats = bt.stats(guarded_v6ab)
    periods = {
        "2020": period_stats(v6ab_eq, "2020-01-01", "2020-12-31"),
        "2022": period_stats(v6ab_eq, "2022-01-01", "2022-12-31"),
        "2024_2026": period_stats(v6ab_eq, "2024-01-01", args.end),
    }
    baseline_periods = {
        "2020": period_stats(baseline_v6ab, "2020-01-01", "2020-12-31"),
        "2022": period_stats(baseline_v6ab, "2022-01-01", "2022-12-31"),
        "2024_2026": period_stats(baseline_v6ab, "2024-01-01", args.end),
    }
    guarded_periods = {
        "2020": period_stats(guarded_v6ab, "2020-01-01", "2020-12-31"),
        "2022": period_stats(guarded_v6ab, "2022-01-01", "2022-12-31"),
        "2024_2026": period_stats(guarded_v6ab, "2024-01-01", args.end),
    }
    turnover = pit.decision_metrics(decisions)
    return {
        "candidate": name,
        "stats": stats,
        "standalone_stats": bt.stats(standalone_eq),
        "periods": periods,
        "turnover_cost": turnover,
        "delta_vs_v2": {
            "ann_delta": stats.get("ann_ret", 0.0) - baseline_stats.get("ann_ret", 0.0),
            "sharpe_delta": stats.get("sharpe", 0.0) - baseline_stats.get("sharpe", 0.0),
            "max_dd_delta": stats.get("max_dd", 0.0) - baseline_stats.get("max_dd", 0.0),
            "ann_2020_delta": periods["2020"].get("ann_ret", 0.0) - baseline_periods["2020"].get("ann_ret", 0.0),
            "ann_2022_delta": periods["2022"].get("ann_ret", 0.0) - baseline_periods["2022"].get("ann_ret", 0.0),
            "ann_2024_2026_delta": periods["2024_2026"].get("ann_ret", 0.0) - baseline_periods["2024_2026"].get("ann_ret", 0.0),
        },
        "delta_vs_guarded": {
            "ann_delta": stats.get("ann_ret", 0.0) - guarded_stats.get("ann_ret", 0.0),
            "sharpe_delta": stats.get("sharpe", 0.0) - guarded_stats.get("sharpe", 0.0),
            "max_dd_delta": stats.get("max_dd", 0.0) - guarded_stats.get("max_dd", 0.0),
            "ann_2020_delta": periods["2020"].get("ann_ret", 0.0) - guarded_periods["2020"].get("ann_ret", 0.0),
            "ann_2022_delta": periods["2022"].get("ann_ret", 0.0) - guarded_periods["2022"].get("ann_ret", 0.0),
            "ann_2024_2026_delta": periods["2024_2026"].get("ann_ret", 0.0) - guarded_periods["2024_2026"].get("ann_ret", 0.0),
        },
        "active_rebalances": turnover.get("pit_active_rebalances", 0),
        "changed_snapshots": meta.get("changed_snapshots", 0),
        "mapped_rows": meta.get("mapped_rows", [])[:25],
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    if not snapshots:
        raise SystemExit(f"empty replay snapshots: {args.replay_json}")

    prices = bt.build_price_matrix(pit.required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    baseline_eq, _ = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    base_curves = build_base_curves(prices, baseline_eq, args)
    baseline_v6ab = bridge.run_v6ab(base_curves, "baseline_v2", 0.45, args.start, args.end)[0]
    pit_cap = active_cap_from_snapshots(snapshots)

    baseline_standalone, baseline_decisions = pit.run_pit_v6b(
        prices,
        snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
        turnover_guard_threshold=args.turnover_guard,
    )
    guarded_curves = dict(base_curves)
    guarded_curves["baseline_guarded_no_mapping"] = baseline_standalone
    guarded_v6ab = run_dynamic_candidate(guarded_curves, "baseline_guarded_no_mapping", pit_cap, args)

    candidates = [
        apply_mapping(snapshots, "baseline_guarded_no_mapping", identity_rule),
        apply_mapping(snapshots, "platform_low_fact_to_technology", platform_low_fact_to_technology),
        apply_mapping(snapshots, "ai_child_low_fact_to_parent", ai_child_low_fact_to_parent),
        apply_mapping(snapshots, "ai_child_no_entry_to_parent", ai_child_no_entry_to_parent),
        apply_mapping(snapshots, "ai_child_no_override_to_parent", ai_child_no_override_to_parent),
    ]
    rows = []
    for mapped_snapshots, meta in candidates:
        name = meta["candidate"]
        standalone_eq, decisions = pit.run_pit_v6b(
            prices,
            mapped_snapshots,
            bridge.BASELINE_CONFIG,
            mode="tier_turnover_guarded",
            turnover_guard_threshold=args.turnover_guard,
        )
        curves = dict(base_curves)
        curves[name] = standalone_eq
        v6ab_eq = run_dynamic_candidate(curves, name, pit_cap, args)
        rows.append(summarize(name, standalone_eq, v6ab_eq, decisions, baseline_v6ab, guarded_v6ab, args, meta))

    ranked = sorted(
        rows,
        key=lambda row: (
            row["delta_vs_guarded"]["ann_delta"],
            row["delta_vs_guarded"]["sharpe_delta"],
            row["delta_vs_v2"]["ann_2020_delta"],
        ),
        reverse=True,
    )
    promoted = [
        row
        for row in rows[1:]
        if row["delta_vs_guarded"]["ann_delta"] > 0.001
        and row["delta_vs_guarded"]["sharpe_delta"] >= 0.0
        and row["active_rebalances"] >= 25
        and row["delta_vs_v2"]["ann_2020_delta"] >= rows[0]["delta_vs_v2"]["ann_2020_delta"] - 0.01
    ]
    return {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "turnover_guard": args.turnover_guard,
        "baseline_v2": {
            "candidate": "baseline_v2_v6ab_dynamic_b",
            "stats": bt.stats(baseline_v6ab),
            "periods": {
                "2020": period_stats(baseline_v6ab, "2020-01-01", "2020-12-31"),
                "2022": period_stats(baseline_v6ab, "2022-01-01", "2022-12-31"),
                "2024_2026": period_stats(baseline_v6ab, "2024-01-01", args.end),
            },
        },
        "rows": rows,
        "ranked": ranked,
        "decision": "REVIEW_THEME_MAPPING_CANDIDATE" if promoted else "NO_THEME_MAPPING_PROMOTION",
        "promoted_candidates": [row["candidate"] for row in promoted],
        "interpretation": [
            "该实验只测试 PIT BOOST 主题映射质量，不改变正式 classifier、PIT replay 或模拟盘。",
            "目标是验证 AI 子主题在证据不足时是否应回到父主题，避免挤掉当期真实大主线。",
            "若改善不稳定或主要来自减少 active 表达，应保持诊断层。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB Theme Mapping Experiment",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- turnover guard：`{payload['turnover_guard']:.2f}`",
        f"- decision：`{payload['decision']}`",
        f"- promoted candidates：`{', '.join(payload.get('promoted_candidates', [])) or 'none'}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "",
        "## Ranked Candidates",
        "",
        "| candidate | ann | maxDD | Sharpe | ann vs guarded | 2020 vs V2 | 2024-2026 vs V2 | active | changed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["ranked"]:
        stats = row["stats"]
        dg = row["delta_vs_guarded"]
        dv2 = row["delta_vs_v2"]
        lines.append(
            f"| `{row['candidate']}` | {fmt_pct(stats.get('ann_ret'))} | {fmt_pct(stats.get('max_dd'))} | "
            f"{stats.get('sharpe', 0.0):.2f} | {fmt_pct(dg.get('ann_delta'))} | "
            f"{fmt_pct(dv2.get('ann_2020_delta'))} | {fmt_pct(dv2.get('ann_2024_2026_delta'))} | "
            f"{row.get('active_rebalances', 0)} | {row.get('changed_snapshots', 0)} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
    ]
    lines.extend(f"- {item}" for item in payload.get("interpretation", []))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test PIT theme consolidation/mapping candidates.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--v6a-daily", type=Path, default=bridge.DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--turnover-guard", type=float, default=1.40)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Theme_Mapping_Experiment_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (REPORT_ROOT / "V6AB_Theme_Mapping_Experiment_LATEST.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
