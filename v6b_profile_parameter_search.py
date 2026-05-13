#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from v6b_synthetic_historical import DEFENSIVE, REGIME_TICKERS, V6A_POOL, build_price_matrix, load_json
from v6b_synthetic_historical_challenger import calc_metrics, load_snapshot_schedule, run_engine


PROFILE_TO_VARIANTS = {
    "core_reaccel_profile": {
        "standalone": ("v6b_core_track", {"tracks": ["core_reacceleration"], "overlay_base": False, "dynamic_only": True}),
        "overlay": ("v6ab_core_overlay", {"tracks": ["core_reacceleration"], "overlay_base": True, "dynamic_only": False}),
    },
    "bottleneck_diffusion_profile": {
        "standalone": ("v6b_bottleneck_track", {"tracks": ["bottleneck_diffusion"], "overlay_base": False, "dynamic_only": True}),
        "overlay": ("v6ab_bottleneck_overlay", {"tracks": ["bottleneck_diffusion"], "overlay_base": True, "dynamic_only": False}),
    },
    "turnaround_momentum_profile": {
        "standalone": ("v6b_turnaround_track", {"tracks": ["turnaround_momentum"], "overlay_base": False, "dynamic_only": True}),
        "overlay": ("v6ab_blended_overlay", {"tracks": ["turnaround_momentum"], "overlay_base": True, "dynamic_only": False}),
    },
}


def profile_grid(profile_config: dict[str, Any]) -> list[dict[str, Any]]:
    ranges = profile_config["parameters_research_range"]
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


def build_baseline_params(policy: dict[str, Any]) -> dict[str, Any]:
    base = policy["profiles"]["v6a_core_baseline"]["parameters"]
    return {
        "top_n": int(base["top_n"]),
        "mom_days": int(base["asset_mom_days"]),
        "trend_ma": int(base["trend_ma_days"]),
        "market_ma": int(base["market_ma_days"]),
        "dd_stop": float(base["dd_stop"]),
        "rebal": int(base["rebal_days"]),
        "label": "v6a_core_baseline",
    }


def compare_metrics(metrics: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    ann_delta = float(metrics["ann_ret"] - baseline["ann_ret"])
    sharpe_delta = float(metrics["sharpe"] - baseline["sharpe"])
    dd_worse = abs(float(metrics["max_dd"])) - abs(float(baseline["max_dd"]))
    oos_ann_delta = float(metrics["oos_ann"] - baseline["oos_ann"]) if not math.isnan(metrics["oos_ann"]) and not math.isnan(baseline["oos_ann"]) else float("nan")
    oos_sharpe_delta = float(metrics["oos_sharpe"] - baseline["oos_sharpe"]) if not math.isnan(metrics["oos_sharpe"]) and not math.isnan(baseline["oos_sharpe"]) else float("nan")
    return {
        "ann_delta": ann_delta,
        "sharpe_delta": sharpe_delta,
        "dd_worse": dd_worse,
        "oos_ann_delta": oos_ann_delta,
        "oos_sharpe_delta": oos_sharpe_delta,
    }


def classify_vs_baseline(mode: str, deltas: dict[str, Any]) -> tuple[str, int]:
    ann_ok = deltas["ann_delta"] > 0
    sharpe_ok = deltas["sharpe_delta"] >= 0
    dd_ok = deltas["dd_worse"] <= 0.05
    if mode == "overlay":
        if ann_ok and sharpe_ok and dd_ok:
            return "promising_safe_overlay", 0
        if ann_ok and dd_ok:
            return "return_plus_overlay", 1
        if ann_ok:
            return "return_only_overlay", 2
        return "not_ready_overlay", 3
    if sharpe_ok and dd_ok:
        return "research_stable_standalone", 4
    if ann_ok:
        return "research_return_standalone", 5
    return "weak_standalone", 6


def classify_track_increment(mode: str, deltas: dict[str, Any] | None) -> tuple[str, int]:
    if mode != "overlay" or not deltas:
        return "n/a", 9
    ann_ok = deltas["ann_delta"] > 0
    sharpe_ok = deltas["sharpe_delta"] >= 0
    dd_ok = deltas["dd_worse"] <= 0.05
    if ann_ok and sharpe_ok and dd_ok:
        return "real_track_alpha", 0
    if ann_ok and dd_ok:
        return "return_only_track", 1
    if ann_ok:
        return "risky_track_return", 2
    return "no_track_edge", 3


def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    metrics = row["metrics"]
    baseline_deltas = row["baseline_deltas"]
    track_deltas = row.get("track_deltas") or {}
    return (
        row["track_gate_rank"],
        row["baseline_gate_rank"],
        -round(float(track_deltas.get("ann_delta", -99.0)), 6),
        -round(float(track_deltas.get("sharpe_delta", -99.0)), 6),
        round(float(track_deltas.get("dd_worse", 99.0)), 6),
        -round(baseline_deltas["ann_delta"], 6),
        -round(baseline_deltas["sharpe_delta"], 6),
        round(baseline_deltas["dd_worse"], 6),
        -round(float(metrics["oos_sharpe"]) if not math.isnan(metrics["oos_sharpe"]) else -99.0, 6),
        -round(float(metrics["sharpe"]), 6),
    )


def write_report(
    rows: list[dict[str, Any]],
    baseline_metrics: dict[str, Any],
    profile_name: str,
    manifest_path: Path,
    output_path: Path,
) -> None:
    lines = [
        "# V6-B Profile Parameter Search",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Profile: `{profile_name}`",
        f"- Snapshot Manifest: `{manifest_path}`",
        f"- Baseline: `AnnR {baseline_metrics['ann_ret'] * 100:+.1f}% / MaxDD {baseline_metrics['max_dd'] * 100:+.1f}% / Sharpe {baseline_metrics['sharpe']:.2f}`",
        "- Ranking rule: for overlays, prioritize real track alpha versus same-parameter V6-A base-only control before baseline-relative uplift.",
        "",
        "| rank | mode | base gate | track gate | config | ann | maxDD | sharpe | vs base annΔ | vs base shΔ | vs base dd | track ann+ | track sh+ | track dd | OOS ann | OOS sh |",
        "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rank, row in enumerate(sorted(rows, key=sort_key)[:30], start=1):
        metrics = row["metrics"]
        baseline_deltas = row["baseline_deltas"]
        track_deltas = row.get("track_deltas")
        track_ann = f"{track_deltas['ann_delta'] * 100:+.1f}%" if track_deltas else "n/a"
        track_sh = f"{track_deltas['sharpe_delta']:+.2f}" if track_deltas else "n/a"
        track_dd = f"{track_deltas['dd_worse'] * 100:+.1f}%" if track_deltas else "n/a"
        lines.append(
            f"| {rank} | `{row['mode']}` | `{row['baseline_gate']}` | `{row['track_gate']}` | `{row['label']}` | "
            f"{metrics['ann_ret'] * 100:+.1f}% | {metrics['max_dd'] * 100:+.1f}% | {metrics['sharpe']:.2f} | "
            f"{baseline_deltas['ann_delta'] * 100:+.1f}% | {baseline_deltas['sharpe_delta']:+.2f} | {baseline_deltas['dd_worse'] * 100:+.1f}% | "
            f"{track_ann} | {track_sh} | {track_dd} | {metrics['oos_ann'] * 100:+.1f}% | {metrics['oos_sharpe']:.2f} |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search bounded parameters for V6 track-aware profiles.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--profile-policy", default="v6_strategy_lab/configs/v6_engine_profile_selector_v1.json")
    parser.add_argument("--profile", required=True, choices=sorted(PROFILE_TO_VARIANTS))
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    policy = load_json(Path(args.profile_policy))
    profile_cfg = policy["profiles"][args.profile]
    params_grid = profile_grid(profile_cfg)
    snapshot_dates, schedule = load_snapshot_schedule(Path(args.manifest))
    tickers = set(REGIME_TICKERS + list(DEFENSIVE.keys()) + V6A_POOL)
    for track_rows in schedule.values():
        for selected in track_rows.values():
            tickers.update(selected)
    tickers.discard("CASH")
    prices = build_price_matrix(sorted(tickers), args.start, args.end)

    baseline_variant = {"tracks": [], "overlay_base": True, "dynamic_only": False}
    baseline_params = build_baseline_params(policy)
    _, baseline_metrics = run_engine(prices, snapshot_dates, schedule, baseline_variant, baseline_params)
    if not baseline_metrics:
        raise RuntimeError("Failed to compute V6-A baseline metrics.")

    base_same_params_cache: dict[str, dict[str, Any]] = {}
    rows = []
    for mode, (variant_name, variant) in PROFILE_TO_VARIANTS[args.profile].items():
        for params in params_grid:
            _, metrics = run_engine(prices, snapshot_dates, schedule, variant, params)
            if not metrics:
                continue
            base_control = base_same_params_cache.get(params["label"])
            if base_control is None:
                _, base_control = run_engine(prices, snapshot_dates, schedule, baseline_variant, params)
                base_same_params_cache[params["label"]] = base_control
            baseline_deltas = compare_metrics(metrics, baseline_metrics)
            track_deltas = compare_metrics(metrics, base_control) if mode == "overlay" else None
            baseline_gate, baseline_gate_rank = classify_vs_baseline(mode, baseline_deltas)
            track_gate, track_gate_rank = classify_track_increment(mode, track_deltas)
            rows.append(
                {
                    "profile": args.profile,
                    "variant": variant_name,
                    "mode": mode,
                    "label": params["label"],
                    "params": params,
                    "metrics": metrics,
                    "base_control_metrics": base_control,
                    "baseline_deltas": baseline_deltas,
                    "track_deltas": track_deltas,
                    "baseline_gate": baseline_gate,
                    "baseline_gate_rank": baseline_gate_rank,
                    "track_gate": track_gate,
                    "track_gate_rank": track_gate_rank,
                }
            )

    out_dir = Path("backtest_results/v6b_profile_search")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{args.profile}_{args.tag}.csv"
    md_path = out_dir / f"{args.profile}_{args.tag}.md"
    flat_rows = []
    for row in rows:
        flat_rows.append(
            {
                "profile": row["profile"],
                "variant": row["variant"],
                "mode": row["mode"],
                "baseline_gate": row["baseline_gate"],
                "baseline_gate_rank": row["baseline_gate_rank"],
                "track_gate": row["track_gate"],
                "track_gate_rank": row["track_gate_rank"],
                "label": row["label"],
                **row["params"],
                **row["metrics"],
                "base_same_ann_ret": row["base_control_metrics"]["ann_ret"],
                "base_same_max_dd": row["base_control_metrics"]["max_dd"],
                "base_same_sharpe": row["base_control_metrics"]["sharpe"],
                "base_same_oos_ann": row["base_control_metrics"]["oos_ann"],
                "base_same_oos_sharpe": row["base_control_metrics"]["oos_sharpe"],
                "vs_baseline_ann_delta": row["baseline_deltas"]["ann_delta"],
                "vs_baseline_sharpe_delta": row["baseline_deltas"]["sharpe_delta"],
                "vs_baseline_dd_worse": row["baseline_deltas"]["dd_worse"],
                "vs_baseline_oos_ann_delta": row["baseline_deltas"]["oos_ann_delta"],
                "vs_baseline_oos_sharpe_delta": row["baseline_deltas"]["oos_sharpe_delta"],
                "track_ann_inc": row["track_deltas"]["ann_delta"] if row["track_deltas"] else float("nan"),
                "track_sharpe_inc": row["track_deltas"]["sharpe_delta"] if row["track_deltas"] else float("nan"),
                "track_dd_inc": row["track_deltas"]["dd_worse"] if row["track_deltas"] else float("nan"),
                "track_oos_ann_inc": row["track_deltas"]["oos_ann_delta"] if row["track_deltas"] else float("nan"),
                "track_oos_sharpe_inc": row["track_deltas"]["oos_sharpe_delta"] if row["track_deltas"] else float("nan"),
            }
        )
    pd.DataFrame(flat_rows).sort_values(
        ["track_gate_rank", "baseline_gate_rank", "track_ann_inc", "track_sharpe_inc", "vs_baseline_ann_delta"],
        ascending=[True, True, False, False, False],
    ).to_csv(csv_path, index=False)
    write_report(rows, baseline_metrics, args.profile, Path(args.manifest), md_path)
    print(f"CSV:    {csv_path}")
    print(f"Report: {md_path}")
    print(f"Rows:   {len(rows)}")


if __name__ == "__main__":
    main()
