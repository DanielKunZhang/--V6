#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import v6ab_classifier_bridge_backtest as bridge
import v6ab_pit_classifier_bridge_backtest as pit
import v6b_theme_rotation_backtest as bt
from v6ab_sleeve_blend_backtest import benchmark_equity, dynamic_b_sizing_equity, load_v6a_composite


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_turnover_guard_threshold_experiment"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def parse_thresholds(raw: str) -> list[float]:
    values: list[float] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(float(part))
    return sorted(set(values))


def period_stats(eq: pd.Series, start: str, end: str) -> dict[str, Any]:
    seg = eq[(eq.index >= pd.Timestamp(start)) & (eq.index <= pd.Timestamp(end))]
    if len(seg) < 30:
        return {}
    return bt.stats(seg / float(seg.iloc[0]) * bt.INITIAL_CAPITAL)


def build_base_curves(
    prices: pd.DataFrame,
    baseline_eq: pd.Series,
    args: argparse.Namespace,
) -> dict[str, pd.Series]:
    return {
        "V6A": load_v6a_composite(args.v6a_daily),
        "baseline_v2": baseline_eq,
        "GLD": benchmark_equity(prices, "US.GLD"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
    }


def active_cap_from_snapshots(snapshots: list[dict[str, Any]]) -> float:
    caps = [
        float(snap.get("b_sleeve_cap_hint", 0.05))
        for snap in snapshots
        if snap.get("theme_allowlist") and not snap.get("fallback_to_v2", True)
    ]
    return max(caps) if caps else 0.45


def run_dynamic_candidate(
    curves: dict[str, pd.Series],
    b_key: str,
    pit_cap: float,
    args: argparse.Namespace,
) -> pd.Series:
    return dynamic_b_sizing_equity(
        curves,
        b_key=b_key,
        b_low=0.05,
        b_mid=min(0.30, pit_cap),
        b_high=max(0.05, min(0.45, pit_cap)),
        b_strong_126d=0.08,
        b_weak_63d=-0.08,
        hedge_max=0.30,
        vol_threshold=0.28,
        corr_threshold=0.60,
        dd_threshold=-0.12,
        start=args.start,
        end=args.end,
    )[0]


def summarize_candidate(
    threshold: float,
    standalone_eq: pd.Series,
    v6ab_eq: pd.Series,
    decisions: list[dict[str, Any]],
    baseline_v6ab: pd.Series,
    args: argparse.Namespace,
) -> dict[str, Any]:
    stats = bt.stats(v6ab_eq)
    baseline_stats = bt.stats(baseline_v6ab)
    periods = {
        "full": stats,
        "2020": period_stats(v6ab_eq, "2020-01-01", "2020-12-31"),
        "2022": period_stats(v6ab_eq, "2022-01-01", "2022-12-31"),
        "2024_2026": period_stats(v6ab_eq, "2024-01-01", args.end),
    }
    baseline_periods = {
        "full": baseline_stats,
        "2020": period_stats(baseline_v6ab, "2020-01-01", "2020-12-31"),
        "2022": period_stats(baseline_v6ab, "2022-01-01", "2022-12-31"),
        "2024_2026": period_stats(baseline_v6ab, "2024-01-01", args.end),
    }
    turnover = pit.decision_metrics(decisions)
    guard_dates = [
        row["date"]
        for row in decisions
        if str(row.get("pit_guard_reason", "")).startswith("turnover_guard")
    ]
    active_dates = [row["date"] for row in decisions if row.get("pit_active_for_mode")]
    return {
        "threshold": threshold,
        "stats": stats,
        "standalone_stats": bt.stats(standalone_eq),
        "periods": periods,
        "turnover_cost": turnover,
        "delta": {
            "ann_delta": stats.get("ann_ret", 0.0) - baseline_stats.get("ann_ret", 0.0),
            "sharpe_delta": stats.get("sharpe", 0.0) - baseline_stats.get("sharpe", 0.0),
            "max_dd_delta": stats.get("max_dd", 0.0) - baseline_stats.get("max_dd", 0.0),
            "ann_2020_delta": periods["2020"].get("ann_ret", 0.0) - baseline_periods["2020"].get("ann_ret", 0.0),
            "ann_2022_delta": periods["2022"].get("ann_ret", 0.0) - baseline_periods["2022"].get("ann_ret", 0.0),
            "ann_2024_2026_delta": periods["2024_2026"].get("ann_ret", 0.0)
            - baseline_periods["2024_2026"].get("ann_ret", 0.0),
        },
        "active_rebalances": turnover.get("pit_active_rebalances", 0),
        "guarded_out_rebalances": len(guard_dates),
        "guarded_out_dates": guard_dates,
        "active_dates": active_dates,
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

    rows: list[dict[str, Any]] = []
    for threshold in parse_thresholds(args.thresholds):
        standalone_eq, decisions = pit.run_pit_v6b(
            prices,
            snapshots,
            bridge.BASELINE_CONFIG,
            mode="tier_turnover_guarded",
            turnover_guard_threshold=threshold,
        )
        curves = dict(base_curves)
        key = f"pit_guard_{threshold:.2f}"
        curves[key] = standalone_eq
        v6ab_eq = run_dynamic_candidate(curves, key, pit_cap, args)
        rows.append(summarize_candidate(threshold, standalone_eq, v6ab_eq, decisions, baseline_v6ab, args))

    ranked = sorted(
        rows,
        key=lambda row: (
            row["active_rebalances"] >= args.min_active,
            row["delta"]["ann_delta"],
            row["delta"]["sharpe_delta"],
            row["delta"]["ann_2024_2026_delta"],
        ),
        reverse=True,
    )
    return {
        "asof": args.asof,
        "replay_json": str(args.replay_json),
        "start": args.start,
        "end": args.end,
        "baseline": {
            "stats": bt.stats(baseline_v6ab),
            "periods": {
                "2020": period_stats(baseline_v6ab, "2020-01-01", "2020-12-31"),
                "2022": period_stats(baseline_v6ab, "2022-01-01", "2022-12-31"),
                "2024_2026": period_stats(baseline_v6ab, "2024-01-01", args.end),
            },
        },
        "min_active": args.min_active,
        "rows": rows,
        "ranked": ranked,
        "interpretation": [
            "这是 turnover guard 阈值敏感性实验，不改变正式 PIT 候选和模拟盘。",
            "如果略微放宽阈值能补足 active 样本且不恶化 maxDD/Sharpe/2022，说明原 1.40 可能过严。",
            "如果只有很宽阈值才通过 active，或收益来自单一月份，则不能作为晋级依据。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB Turnover Guard Threshold Experiment",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- active threshold：`{payload['min_active']}`",
        "- 用途：评估 guarded BOOST 的换手阈值是否过严；不改变模拟盘。",
        "",
        "## Ranked Thresholds",
        "",
        "| threshold | active | guarded out | ann | ann delta | maxDD | Sharpe | 2020 delta | 2022 delta | 2024-2026 delta | avg turnover | cost drag |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["ranked"]:
        stats = row["stats"]
        delta = row["delta"]
        turnover = row["turnover_cost"]
        lines.append(
            f"| {row['threshold']:.2f} | {row['active_rebalances']} | {row['guarded_out_rebalances']} | "
            f"{fmt_pct(stats.get('ann_ret'))} | {fmt_pct(delta.get('ann_delta'))} | "
            f"{fmt_pct(stats.get('max_dd'))} | {stats.get('sharpe', 0.0):.2f} | "
            f"{fmt_pct(delta.get('ann_2020_delta'))} | {fmt_pct(delta.get('ann_2022_delta'))} | "
            f"{fmt_pct(delta.get('ann_2024_2026_delta'))} | "
            f"{float(turnover.get('avg_turnover', 0.0) or 0.0):.2f} | {fmt_pct(turnover.get('est_cost_drag'))} |"
        )

    lines += [
        "",
        "## Guarded-Out Dates",
        "",
        "| threshold | dates |",
        "| ---: | --- |",
    ]
    for row in payload["rows"]:
        lines.append(f"| {row['threshold']:.2f} | `{', '.join(row['guarded_out_dates']) or 'none'}` |")

    lines += [
        "",
        "## Interpretation",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["interpretation"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run V6AB PIT turnover guard threshold sensitivity experiment.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--v6a-daily", type=Path, default=pit.DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--thresholds", default="1.20,1.30,1.40,1.45,1.50,1.60,1.80,2.00")
    parser.add_argument("--min-active", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Turnover_Guard_Threshold_Experiment_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORT_ROOT / "V6AB_Turnover_Guard_Threshold_Experiment_LATEST.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
