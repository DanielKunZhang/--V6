#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from v6b_theme_rotation_backtest import (
    INITIAL_CAPITAL,
    build_price_matrix,
    run_strategy,
    stats,
)


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "v6ab_sleeve_blend"
DEFAULT_V6A_DAILY = ROOT / "backtest_results" / "attack_engine_replay" / "attack_replay_daily_20260520_live_refreshed.csv"


V6B_CONFIGS: dict[str, dict[str, Any]] = {
    "v6b_guarded_top3_90": {
        "top_n": 3,
        "min_theme_score": 0.08,
        "risk_weight": 0.90,
        "use_cooldown": True,
        "vol_target": 0.22,
        "dd_brake": True,
        "expression": "stocks",
        "stock_top_n": 2,
    },
    "v6b_raw_top3_100": {
        "top_n": 3,
        "min_theme_score": 0.02,
        "risk_weight": 1.00,
        "use_cooldown": False,
        "vol_target": None,
        "dd_brake": False,
        "expression": "stocks",
        "stock_top_n": 2,
    },
}


def load_v6a_composite(path: Path) -> pd.Series:
    daily = pd.read_csv(path)
    if daily.empty:
        raise SystemExit(f"empty V6-A daily file: {path}")
    wide = daily.pivot(index="date", columns="candidate_id", values="equity").sort_index()
    wide.index = pd.to_datetime(wide.index)
    returns = wide.pct_change().dropna()
    eq = (1.0 + returns.mean(axis=1)).cumprod() * INITIAL_CAPITAL
    eq.name = "V6A_ATTACK_EQUAL_REPLAY"
    return eq


def benchmark_equity(prices: pd.DataFrame, ticker: str) -> pd.Series:
    series = prices[ticker].dropna()
    eq = series / float(series.iloc[0]) * INITIAL_CAPITAL
    eq.name = ticker
    return eq


def blend_equity(curves: dict[str, pd.Series], weights: dict[str, float], start: str, end: str) -> pd.Series:
    frame = pd.DataFrame(curves).sort_index().ffill().dropna()
    frame = frame[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
    rets = frame.pct_change().fillna(0.0)
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("weights must be positive")
    norm = {key: value / total_weight for key, value in weights.items()}
    blended_ret = sum(rets[key] * norm.get(key, 0.0) for key in frame.columns)
    eq = (1.0 + blended_ret).cumprod() * INITIAL_CAPITAL
    return eq


def max_corr(curves: dict[str, pd.Series], start: str, end: str) -> pd.DataFrame:
    frame = pd.DataFrame(curves).sort_index().ffill().dropna()
    frame = frame[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
    return frame.pct_change().dropna().corr()


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value * 100:+.1f}%"


def write_report(
    path: Path,
    rows: list[dict[str, Any]],
    standalone: list[dict[str, Any]],
    corr: pd.DataFrame,
    start: str,
    end: str,
) -> None:
    ranked = sorted(rows, key=lambda row: (row["stats"]["sharpe"], row["stats"]["ann_ret"]), reverse=True)
    lines = [
        "# V6-A + V6-B Sleeve Blend Backtest",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Window: `{start}` to `{end}`",
        "- Purpose: test whether V6-A stability plus V6-B theme rotation plus GLD/IEF/BIL hedges can raise portfolio Sharpe.",
        "- V6-A source: `attack_replay_daily_20260520_live_refreshed.csv` equal replay composite.",
        "- V6-B source: dynamic `ETF theme discovery -> theme-to-stock expression` rerun from local cache.",
        "",
        "## Standalone",
        "",
        "| sleeve | ann | maxDD | Sharpe | final |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in standalone:
        s = row["stats"]
        lines.append(f"| `{row['name']}` | {fmt_pct(s.get('ann_ret'))} | {fmt_pct(s.get('max_dd'))} | {s.get('sharpe', 0):.2f} | ${s.get('final', 0):,.0f} |")

    lines.extend(["", "## Top Blends", "", "| rank | weights | ann | maxDD | Sharpe | final |", "| ---: | --- | ---: | ---: | ---: | ---: |"])
    for idx, row in enumerate(ranked[:25], start=1):
        s = row["stats"]
        weights = ", ".join(f"{key}:{value:.0%}" for key, value in row["weights"].items() if value > 0)
        lines.append(f"| {idx} | `{weights}` | {fmt_pct(s.get('ann_ret'))} | {fmt_pct(s.get('max_dd'))} | {s.get('sharpe', 0):.2f} | ${s.get('final', 0):,.0f} |")

    lines.extend(["", "## Correlation", "", corr.round(3).to_markdown(), ""])
    lines.extend(
        [
            "## Interpretation",
            "",
            "- This is a research blend, not a live allocation change.",
            "- A blend is only interesting if Sharpe improves versus both V6-A and V6-B alone while max drawdown remains controlled.",
            "- Next production step is sleeve sizing with explicit capital caps and live execution constraints.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Blend V6-A replay, V6-B theme-to-stock, and hedge sleeves.")
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--v6a-daily", default=str(DEFAULT_V6A_DAILY))
    args = parser.parse_args()

    v6a = load_v6a_composite(Path(args.v6a_daily))

    prices = build_price_matrix(
        [
            "US.SPY",
            "US.QQQ",
            "US.BIL",
            "US.IEF",
            "US.GLD",
            "US.VTV",
            "US.BRK.B",
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
            "US.ROK",
            "US.ETN",
            "US.HON",
            "US.IR",
            "US.TER",
        ],
        args.start,
        args.end,
    ).ffill(limit=3)

    curves: dict[str, pd.Series] = {
        "V6A": v6a,
        "GLD": benchmark_equity(prices, "US.GLD"),
        "IEF": benchmark_equity(prices, "US.IEF"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
    }
    decisions_by_b: dict[str, list[dict[str, Any]]] = {}
    for name, cfg in V6B_CONFIGS.items():
        eq, decisions = run_strategy(prices, **cfg)
        curves[name] = eq
        decisions_by_b[name] = decisions[-12:]

    standalone = [{"name": name, "stats": stats(curve[(curve.index >= pd.Timestamp(args.start)) & (curve.index <= pd.Timestamp(args.end))])} for name, curve in curves.items()]

    rows: list[dict[str, Any]] = []
    for b_name in V6B_CONFIGS:
        for a_w in [0.40, 0.50, 0.60, 0.70, 0.80]:
            for b_w in [0.10, 0.20, 0.30, 0.40, 0.50]:
                for gld_w in [0.00, 0.05, 0.10, 0.15, 0.20]:
                    for ief_w in [0.00, 0.05, 0.10, 0.15]:
                        bil_w = 1.0 - a_w - b_w - gld_w - ief_w
                        if bil_w < -1e-9 or bil_w > 0.30:
                            continue
                        weights = {"V6A": a_w, b_name: b_w, "GLD": gld_w, "IEF": ief_w, "BIL": max(0.0, bil_w)}
                        eq = blend_equity({key: curves[key] for key in weights}, weights, args.start, args.end)
                        s = stats(eq)
                        if not s:
                            continue
                        rows.append({"config": b_name, "weights": weights, "stats": s})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"v6ab_sleeve_blend_{args.tag}.json"
    md_path = OUT_DIR / f"v6ab_sleeve_blend_{args.tag}.md"
    csv_path = OUT_DIR / f"v6ab_sleeve_blend_{args.tag}.csv"
    pd.DataFrame([{**{"config": row["config"]}, **row["weights"], **row["stats"]} for row in rows]).sort_values(["sharpe", "ann_ret"], ascending=False).to_csv(csv_path, index=False)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start": args.start,
        "end": args.end,
        "standalone": standalone,
        "rows": rows,
        "recent_v6b_decisions": decisions_by_b,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    corr = max_corr({key: curves[key] for key in ["V6A", *V6B_CONFIGS.keys(), "GLD", "IEF", "BIL", "SPY", "QQQ"]}, args.start, args.end)
    write_report(md_path, rows, standalone, corr, args.start, args.end)
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
