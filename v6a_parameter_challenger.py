#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from v6b_profile_parameter_search import build_baseline_params, compare_metrics
from v6b_synthetic_historical import DEFENSIVE, REGIME_TICKERS, V6A_POOL, build_price_matrix, load_json
from v6b_synthetic_historical_challenger import load_snapshot_schedule, run_engine


BASELINE_VARIANT = {"tracks": [], "overlay_base": True, "dynamic_only": False}


def parameter_grid(policy: dict[str, Any]) -> list[dict[str, Any]]:
    ranges = policy["parameter_research_range"]
    fields = [
        ("top_n", "top_n"),
        ("asset_mom_days", "mom_days"),
        ("trend_ma_days", "trend_ma"),
        ("market_ma_days", "market_ma"),
        ("dd_stop", "dd_stop"),
        ("rebal_days", "rebal"),
    ]
    values = [ranges[src] for src, _ in fields]
    rows = []
    for combo in itertools.product(*values):
        row = {dest: value for (_, dest), value in zip(fields, combo)}
        row["label"] = (
            f"mom{row['mom_days']} top{row['top_n']} "
            f"trend{row['trend_ma']} mkt{row['market_ma']} "
            f"dd{int(round(row['dd_stop'] * 100)):02d} rebal{row['rebal']}"
        )
        rows.append(row)
    return rows


def classify_candidate(
    deltas: dict[str, Any],
    gate_rules: dict[str, Any],
    baseline_label: str,
    label: str,
) -> tuple[str, int]:
    if label == baseline_label:
        return "baseline_anchor", 2
    ann_ok = deltas["ann_delta"] > 0
    sharpe_ok = deltas["sharpe_delta"] >= 0 if gate_rules.get("require_non_negative_sharpe_delta", True) else True
    dd_ok = deltas["dd_worse"] <= gate_rules.get("safe_upgrade_max_dd_worse", 0.05)
    oos_sharpe = deltas["oos_sharpe_delta"]
    oos_ok = (not math.isnan(oos_sharpe) and oos_sharpe >= 0) if gate_rules.get("prefer_non_negative_oos_sharpe_delta", True) else True

    if ann_ok and sharpe_ok and dd_ok and oos_ok:
        return "promising_core_upgrade", 0
    if ann_ok and sharpe_ok and dd_ok:
        return "full_sample_upgrade", 1
    if ann_ok and dd_ok:
        return "return_plus_candidate", 3
    if sharpe_ok and dd_ok:
        return "safer_but_not_faster", 4
    return "not_ready", 5


def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    metrics = row["metrics"]
    deltas = row["deltas"]
    return (
        row["gate_rank"],
        -round(deltas["ann_delta"], 6),
        -round(deltas["sharpe_delta"], 6),
        round(deltas["dd_worse"], 6),
        -round(float(deltas["oos_sharpe_delta"]) if not math.isnan(deltas["oos_sharpe_delta"]) else -99.0, 6),
        -round(float(metrics["oos_sharpe"]) if not math.isnan(metrics["oos_sharpe"]) else -99.0, 6),
        -round(float(metrics["sharpe"]), 6),
    )


def write_report(
    rows: list[dict[str, Any]],
    baseline_params: dict[str, Any],
    baseline_metrics: dict[str, Any],
    manifest_path: Path,
    output_path: Path,
) -> None:
    lines = [
        "# V6-A Parameter Challenger",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Snapshot Manifest: `{manifest_path}`",
        (
            f"- Baseline Params: `mom{baseline_params['mom_days']} top{baseline_params['top_n']} "
            f"trend{baseline_params['trend_ma']} mkt{baseline_params['market_ma']} "
            f"dd{int(round(baseline_params['dd_stop'] * 100)):02d} rebal{baseline_params['rebal']}`"
        ),
        f"- Baseline Metrics: `AnnR {baseline_metrics['ann_ret'] * 100:+.1f}% / MaxDD {baseline_metrics['max_dd'] * 100:+.1f}% / Sharpe {baseline_metrics['sharpe']:.2f}`",
        "- Ranking rule: prefer bounded base-only upgrades that improve full-sample quality without obvious OOS deterioration.",
        "",
        "| rank | gate | config | ann | maxDD | sharpe | annΔ | shΔ | dd_worse | OOS ann | OOS sh | OOS annΔ | OOS shΔ |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rank, row in enumerate(sorted(rows, key=sort_key)[:30], start=1):
        metrics = row["metrics"]
        deltas = row["deltas"]
        lines.append(
            f"| {rank} | `{row['gate']}` | `{row['label']}` | "
            f"{metrics['ann_ret'] * 100:+.1f}% | {metrics['max_dd'] * 100:+.1f}% | {metrics['sharpe']:.2f} | "
            f"{deltas['ann_delta'] * 100:+.1f}% | {deltas['sharpe_delta']:+.2f} | {deltas['dd_worse'] * 100:+.1f}% | "
            f"{metrics['oos_ann'] * 100:+.1f}% | {metrics['oos_sharpe']:.2f} | {deltas['oos_ann_delta'] * 100:+.1f}% | {deltas['oos_sharpe_delta']:+.2f} |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bounded V6-A parameter challenger search.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--baseline-policy", default="v6_strategy_lab/configs/v6_engine_profile_selector_v1.json")
    parser.add_argument("--search-policy", default="v6_strategy_lab/configs/v6a_parameter_challenger_v1.json")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    baseline_policy = load_json(Path(args.baseline_policy))
    search_policy = load_json(Path(args.search_policy))
    baseline_params = build_baseline_params(baseline_policy)
    baseline_label = baseline_params["label"]
    params_grid = parameter_grid(search_policy)

    snapshot_dates, schedule = load_snapshot_schedule(Path(args.manifest))
    tickers = set(REGIME_TICKERS + list(DEFENSIVE.keys()) + V6A_POOL)
    for track_rows in schedule.values():
        for selected in track_rows.values():
            tickers.update(selected)
    tickers.discard("CASH")
    prices = build_price_matrix(sorted(tickers), args.start, args.end)

    _, baseline_metrics = run_engine(prices, snapshot_dates, schedule, BASELINE_VARIANT, baseline_params)
    if not baseline_metrics:
        raise RuntimeError("Failed to compute V6-A baseline metrics.")

    rows = []
    for params in params_grid:
        _, metrics = run_engine(prices, snapshot_dates, schedule, BASELINE_VARIANT, params)
        if not metrics:
            continue
        deltas = compare_metrics(metrics, baseline_metrics)
        gate, gate_rank = classify_candidate(deltas, search_policy["gate_rules"], baseline_label, params["label"])
        rows.append(
            {
                "label": params["label"],
                "params": params,
                "metrics": metrics,
                "deltas": deltas,
                "gate": gate,
                "gate_rank": gate_rank,
            }
        )

    out_dir = Path("backtest_results/v6a_parameter_challenger")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"v6a_parameter_challenger_{args.tag}.csv"
    md_path = out_dir / f"v6a_parameter_challenger_{args.tag}.md"

    flat_rows = []
    for row in rows:
        flat_rows.append(
            {
                "gate": row["gate"],
                "gate_rank": row["gate_rank"],
                "label": row["label"],
                **row["params"],
                **row["metrics"],
                "ann_delta": row["deltas"]["ann_delta"],
                "sharpe_delta": row["deltas"]["sharpe_delta"],
                "dd_worse": row["deltas"]["dd_worse"],
                "oos_ann_delta": row["deltas"]["oos_ann_delta"],
                "oos_sharpe_delta": row["deltas"]["oos_sharpe_delta"],
            }
        )
    pd.DataFrame(flat_rows).sort_values(
        ["gate_rank", "ann_delta", "sharpe_delta", "dd_worse"],
        ascending=[True, False, False, True],
    ).to_csv(csv_path, index=False)
    write_report(rows, baseline_params, baseline_metrics, Path(args.manifest), md_path)
    print(f"CSV:    {csv_path}")
    print(f"Report: {md_path}")
    print(f"Rows:   {len(rows)}")


if __name__ == "__main__":
    main()
