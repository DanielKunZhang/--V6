#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_RESULTS = ROOT / "backtest_results" / "v6a_parameter_challenger" / "v6a_parameter_challenger_20260513_v1.csv"
OUT_DIR = ROOT / "backtest_results" / "v6a_parameter_robustness"


def neighbor_count(target: dict[str, Any], row: dict[str, Any]) -> int:
    fields = ["top_n", "mom_days", "trend_ma", "market_ma", "dd_stop", "rebal"]
    return sum(1 for field in fields if row[field] != target[field])


def classify_stability(neighbors: pd.DataFrame) -> str:
    if neighbors.empty:
        return "insufficient_neighbors"
    good = neighbors[neighbors["gate"].isin(["promising_core_upgrade", "full_sample_upgrade"])]
    if len(good) / len(neighbors) >= 0.6:
        return "stable_neighbor_cluster"
    if len(good) / len(neighbors) >= 0.3:
        return "mixed_but_workable_cluster"
    return "fragile_peak"


def render_md(target: dict[str, Any], neighbors: pd.DataFrame, output: dict[str, Any]) -> str:
    lines = [
        "# V6-A Parameter Neighbor Robustness",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Target: `{target['label']}`",
        f"- Verdict: `{output['verdict']}`",
        "",
        "## Target Metrics",
        "",
        f"- Gate: `{target['gate']}`",
        f"- AnnR: `{target['ann_ret'] * 100:+.1f}%`",
        f"- MaxDD: `{target['max_dd'] * 100:+.1f}%`",
        f"- Sharpe: `{target['sharpe']:.2f}`",
        f"- OOS Sharpe: `{target['oos_sharpe']:.2f}`",
        "",
        "## Neighbor Summary",
        "",
        f"- Neighbor count: `{output['neighbor_count']}`",
        f"- Good neighbors (`promising_core_upgrade` or `full_sample_upgrade`): `{output['good_neighbor_count']}`",
        f"- Median neighbor AnnΔ: `{output['median_ann_delta'] * 100:+.1f}%`",
        f"- Median neighbor SharpeΔ: `{output['median_sharpe_delta']:+.2f}`",
        f"- Median neighbor dd_worse: `{output['median_dd_worse'] * 100:+.1f}%`",
        "",
        "## Nearest Neighbors",
        "",
        "| gate | label | annΔ | shΔ | dd_worse | OOS shΔ |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for _, row in neighbors.sort_values(["gate_rank", "ann_delta", "sharpe_delta"], ascending=[True, False, False]).head(20).iterrows():
        lines.append(
            f"| `{row['gate']}` | `{row['label']}` | {row['ann_delta'] * 100:+.1f}% | {row['sharpe_delta']:+.2f} | {row['dd_worse'] * 100:+.1f}% | {row['oos_sharpe_delta']:+.2f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check local neighbor robustness for a V6-A parameter challenger candidate.")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--label", required=True)
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    df = pd.read_csv(Path(args.results))
    target_df = df[df["label"] == args.label]
    if target_df.empty:
        raise SystemExit(f"Target label not found: {args.label}")
    target = target_df.iloc[0].to_dict()

    neighbors = df[df["label"] != args.label].copy()
    neighbors["distance"] = neighbors.apply(lambda row: neighbor_count(target, row.to_dict()), axis=1)
    neighbors = neighbors[neighbors["distance"] == 1].copy()

    verdict = classify_stability(neighbors)
    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_label": args.label,
        "verdict": verdict,
        "neighbor_count": int(len(neighbors)),
        "good_neighbor_count": int(len(neighbors[neighbors["gate"].isin(["promising_core_upgrade", "full_sample_upgrade"])])),
        "median_ann_delta": float(neighbors["ann_delta"].median()) if not neighbors.empty else 0.0,
        "median_sharpe_delta": float(neighbors["sharpe_delta"].median()) if not neighbors.empty else 0.0,
        "median_dd_worse": float(neighbors["dd_worse"].median()) if not neighbors.empty else 0.0,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"v6a_parameter_robustness_{args.tag}.json"
    md_path = OUT_DIR / f"v6a_parameter_robustness_{args.tag}.md"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_md(target, neighbors, output), encoding="utf-8")
    print(f"JSON:   {json_path}")
    print(f"Report: {md_path}")
    print(f"Verdict: {verdict}")


if __name__ == "__main__":
    main()
