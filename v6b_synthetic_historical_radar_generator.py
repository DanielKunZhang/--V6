#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from v6b_synthetic_historical import (
    DEFAULT_POLICY_PATH,
    DEFAULT_SEED_PATH,
    REGIME_TICKERS,
    build_price_matrix,
    build_snapshot,
    load_json,
    load_seed_templates,
    month_end_trading_days,
    write_snapshot_series,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate monthly synthetic historical Radar universe snapshots.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--seed", default=str(DEFAULT_SEED_PATH))
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2026-05-12")
    parser.add_argument("--tag", default="20260513_v1")
    args = parser.parse_args()

    policy = load_json(Path(args.policy))
    templates = load_seed_templates(Path(args.seed))
    tickers = set(REGIME_TICKERS + [policy["benchmarks"]["semi"]])
    for track_policy in policy["tracks"].values():
        tickers.update(track_policy["members"])

    prices = build_price_matrix(sorted(tickers), args.start, args.end)
    coverage = []
    for ticker in sorted(tickers):
        if ticker not in prices.columns:
            coverage.append({"ticker": ticker, "first_date": "missing", "last_date": "missing", "bars": 0})
            continue
        series = prices[ticker].dropna()
        coverage.append(
            {
                "ticker": ticker,
                "first_date": str(series.index.min().date()) if not series.empty else "missing",
                "last_date": str(series.index.max().date()) if not series.empty else "missing",
                "bars": int(series.shape[0]),
            }
        )

    snapshots = []
    for as_of in month_end_trading_days(prices.index, args.start, args.end):
        snapshot = build_snapshot(prices, policy, templates, as_of)
        snapshots.append(snapshot)

    out_dir = Path("v6_strategy_lab/configs/synthetic_history") / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path, report_path = write_snapshot_series(snapshots, out_dir, policy, coverage)
    print(f"Manifest: {manifest_path}")
    print(f"Report:   {report_path}")
    print(f"Count:    {len(snapshots)} snapshots")


if __name__ == "__main__":
    main()
