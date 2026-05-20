#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from v6ab_sleeve_blend_backtest import V6B_CONFIGS, benchmark_equity, dynamic_b_sizing_equity, load_v6a_composite
from v6b_theme_rotation_backtest import INITIAL_CAPITAL, build_price_matrix, run_strategy, stats


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "v6ab_candidate_quick_compare"
DEFAULT_V6A_DAILY = ROOT / "backtest_results" / "attack_engine_replay" / "attack_replay_daily_20260520_live_refreshed.csv"


def config_tickers(config_names: list[str]) -> list[str]:
    tickers = {
        "US.SPY",
        "US.QQQ",
        "US.BIL",
        "US.GLD",
        "US.IEF",
    }
    for name in config_names:
        cfg = V6B_CONFIGS[name]
        manifest = cfg.get("pit_manifest")
        if manifest:
            payload = json.loads(Path(manifest).read_text(encoding="utf-8"))
            for row in payload.get("snapshots", []):
                for selected in row.get("selected", {}).values():
                    tickers.update(selected)
    # Static V2 pool / proxies still need to be present.
    tickers.update(
        [
            "US.IWM",
            "US.XLK",
            "US.IGV",
            "US.FDN",
            "US.ARKK",
            "US.SMH",
            "US.SOXX",
            "US.XLV",
            "US.XBI",
            "US.XLE",
            "US.XOP",
            "US.DBC",
            "US.SLV",
            "US.GDX",
            "US.XLF",
            "US.KRE",
            "US.XLI",
            "US.XLU",
            "US.XLY",
            "US.AMZN",
            "US.MSFT",
            "US.GOOGL",
            "US.META",
            "US.TSLA",
            "US.NFLX",
            "US.NVDA",
            "US.AVGO",
            "US.AMD",
            "US.ANET",
            "US.TSM",
            "US.MU",
            "US.WDC",
            "US.AMKR",
            "US.COHR",
            "US.AAOI",
            "US.LITE",
            "US.MRVL",
            "US.NOK",
            "US.LLY",
            "US.JPM",
            "US.BRK.B",
            "US.ROK",
            "US.ETN",
            "US.HON",
            "US.IR",
            "US.TER",
        ]
    )
    return sorted(tickers)


def period_stats(eq: pd.Series, start: str, end: str) -> dict[str, Any]:
    seg = eq[(eq.index >= pd.Timestamp(start)) & (eq.index <= pd.Timestamp(end))]
    if len(seg) < 30:
        return {}
    return stats(seg / float(seg.iloc[0]) * INITIAL_CAPITAL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick compare V6AB candidates without broad static/overlay grid search.")
    parser.add_argument("--configs", default="v6b_guarded_top3_90,v6b_pit_guarded_top3_90,v6b_real_stock_pit_guarded_top3_90,v6b_real_stock_hybrid_gap_pit_guarded_top3_90")
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--v6a-daily", default=str(DEFAULT_V6A_DAILY))
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    config_names = [name.strip() for name in args.configs.split(",") if name.strip()]
    prices = build_price_matrix(config_tickers(config_names), args.start, args.end).ffill(limit=3)
    v6a = load_v6a_composite(Path(args.v6a_daily))
    curves: dict[str, pd.Series] = {
        "V6A": v6a,
        "GLD": benchmark_equity(prices, "US.GLD"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
    }
    decisions: dict[str, list[dict[str, Any]]] = {}
    for name in config_names:
        eq, rows = run_strategy(prices, **V6B_CONFIGS[name])
        curves[name] = eq
        decisions[name] = rows[-12:]

    dynamic_b_grid = [
        {"b_low": 0.05, "b_mid": 0.30, "b_high": 0.45, "b_strong_126d": 0.08, "b_weak_63d": -0.08},
        {"b_low": 0.05, "b_mid": 0.30, "b_high": 0.35, "b_strong_126d": 0.16, "b_weak_63d": -0.08},
        {"b_low": 0.10, "b_mid": 0.30, "b_high": 0.45, "b_strong_126d": 0.08, "b_weak_63d": -0.08},
    ]
    rows = []
    for name in config_names:
        standalone = stats(curves[name][(curves[name].index >= pd.Timestamp(args.start)) & (curves[name].index <= pd.Timestamp(args.end))])
        rows.append({"candidate": name, "mode": "standalone_v6b", **standalone})
        for grid in dynamic_b_grid:
            eq, log = dynamic_b_sizing_equity(
                {key: curves[key] for key in ["V6A", name, "GLD", "BIL", "SPY", "QQQ"]},
                b_key=name,
                hedge_max=0.30,
                vol_threshold=0.28,
                corr_threshold=0.60,
                dd_threshold=-0.12,
                start=args.start,
                end=args.end,
                **grid,
            )
            s = stats(eq)
            rows.append(
                {
                    "candidate": name,
                    "mode": "v6ab_dynamic_b_sizing",
                    **grid,
                    "hedge_max": 0.30,
                    "vol_trigger": 0.28,
                    "corr_trigger": 0.60,
                    "dd_trigger": -0.12,
                    "overlay_days": int((log["weights"].str.contains("GLD|BIL")).sum()) if not log.empty else 0,
                    **s,
                    "2018q4_dd": period_stats(eq, "2018-09-01", "2018-12-31").get("max_dd"),
                    "2020_ann": period_stats(eq, "2020-01-01", "2020-12-31").get("ann_ret"),
                    "2022_ann": period_stats(eq, "2022-01-01", "2022-12-31").get("ann_ret"),
                    "2024_2026_ann": period_stats(eq, "2024-01-01", args.end).get("ann_ret"),
                }
            )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"v6ab_candidate_quick_compare_{args.tag}.csv"
    json_path = OUT_DIR / f"v6ab_candidate_quick_compare_{args.tag}.json"
    pd.DataFrame(rows).sort_values(["mode", "sharpe", "ann_ret"], ascending=[True, False, False]).to_csv(csv_path, index=False)
    json_path.write_text(json.dumps({"generated_at": datetime.now().isoformat(timespec="seconds"), "rows": rows, "recent_decisions": decisions}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
