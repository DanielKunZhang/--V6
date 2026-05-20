#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from v6b_synthetic_historical import (
    DEFENSIVE,
    REGIME_TICKERS,
    V6A_POOL,
    build_price_matrix,
    load_json,
)


INITIAL_CAPITAL = 10_000.0
TRADING_DAYS = 252
RISK_FREE = 0.05
ENGINE_PARAMS = [
    dict(trend_ma=100, market_ma=150, mom_days=60, top_n=3, dd_stop=0.10, rebal=5, label="base    (mom60  top3 dd10%)"),
    dict(trend_ma=100, market_ma=150, mom_days=120, top_n=3, dd_stop=0.10, rebal=5, label="slow    (mom120 top3 dd10%)"),
    dict(trend_ma=100, market_ma=150, mom_days=60, top_n=2, dd_stop=0.10, rebal=5, label="conc    (mom60  top2 dd10%)"),
    dict(trend_ma=100, market_ma=150, mom_days=60, top_n=3, dd_stop=0.15, rebal=5, label="loose   (mom60  top3 dd15%)"),
]

VARIANTS = {
    "v6a_base_only": {"tracks": [], "overlay_base": True, "dynamic_only": False},
    "v6b_core_track": {"tracks": ["core_reacceleration"], "overlay_base": False, "dynamic_only": True},
    "v6b_bottleneck_track": {"tracks": ["bottleneck_diffusion"], "overlay_base": False, "dynamic_only": True},
    "v6b_optics_track": {"tracks": ["optics_and_interconnect"], "overlay_base": False, "dynamic_only": True},
    "v6b_turnaround_track": {"tracks": ["turnaround_momentum"], "overlay_base": False, "dynamic_only": True},
    "v6b_blended_tracks": {
        "tracks": "__ALL_DYNAMIC_TRACKS__",
        "overlay_base": False,
        "dynamic_only": True,
    },
    "v6ab_core_overlay": {"tracks": ["core_reacceleration"], "overlay_base": True, "dynamic_only": False},
    "v6ab_bottleneck_overlay": {"tracks": ["bottleneck_diffusion"], "overlay_base": True, "dynamic_only": False},
    "v6ab_optics_overlay": {"tracks": ["optics_and_interconnect"], "overlay_base": True, "dynamic_only": False},
    "v6ab_blended_overlay": {
        "tracks": "__ALL_DYNAMIC_TRACKS__",
        "overlay_base": True,
        "dynamic_only": False,
    },
}


def load_snapshot_schedule(manifest_path: Path) -> tuple[list[pd.Timestamp], dict[pd.Timestamp, dict[str, list[str]]]]:
    payload = load_json(manifest_path)
    schedule = {}
    dates = []
    for row in payload.get("snapshots", []):
        as_of = pd.Timestamp(row["as_of"])
        dates.append(as_of)
        schedule[as_of] = {track: list(tickers) for track, tickers in row.get("selected", {}).items()}
    dates.sort()
    return dates, schedule


def expand_variant_tracks(variant: dict[str, Any], schedule: dict[pd.Timestamp, dict[str, list[str]]]) -> dict[str, Any]:
    tracks = variant.get("tracks")
    if tracks == "__ALL_DYNAMIC_TRACKS__":
        all_tracks = sorted({track for rows in schedule.values() for track in rows})
        updated = dict(variant)
        updated["tracks"] = all_tracks
        return updated
    return variant


def current_snapshot_tickers(dt: pd.Timestamp, dates: list[pd.Timestamp], schedule: dict[pd.Timestamp, dict[str, list[str]]], variant: dict[str, Any]) -> list[str]:
    eligible_dates = [as_of for as_of in dates if as_of <= dt]
    dynamic = []
    if eligible_dates:
        snapshot = schedule[eligible_dates[-1]]
        for track in variant["tracks"]:
            dynamic.extend(snapshot.get(track, []))
    tickers = []
    if variant["overlay_base"]:
        tickers.extend(V6A_POOL)
    if variant["dynamic_only"] or dynamic:
        tickers.extend(dynamic)
    deduped = []
    seen = set()
    for ticker in tickers:
        if ticker not in seen:
            seen.add(ticker)
            deduped.append(ticker)
    return deduped


def calc_metrics(eq: pd.Series) -> dict[str, Any]:
    if len(eq) < 50:
        return {}
    dr = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    ann_ret = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1 if n_years > 0 else 0.0
    roll_max = eq.cummax()
    max_dd = ((eq - roll_max) / roll_max).min()
    rf_d = RISK_FREE / TRADING_DAYS
    sharpe = (dr - rf_d).mean() / dr.std() * np.sqrt(TRADING_DAYS) if dr.std() > 0 else 0.0

    oos = eq.loc[eq.index >= "2024-01-01"]
    if len(oos) > 50:
        dr_oos = oos.pct_change().dropna()
        n_oos = (oos.index[-1] - oos.index[0]).days / 365.25
        oos_ann = (oos.iloc[-1] / oos.iloc[0]) ** (1 / n_oos) - 1 if n_oos > 0 else 0.0
        oos_sharpe = (dr_oos - rf_d).mean() / dr_oos.std() * np.sqrt(TRADING_DAYS) if dr_oos.std() > 0 else 0.0
        oos_dd = ((oos - oos.cummax()) / oos.cummax()).min()
    else:
        oos_ann = float("nan")
        oos_sharpe = float("nan")
        oos_dd = float("nan")

    return {
        "ann_ret": ann_ret,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "oos_ann": oos_ann,
        "oos_sharpe": oos_sharpe,
        "oos_dd": oos_dd,
        "final_equity": float(eq.iloc[-1]),
    }


def run_engine(
    prices: pd.DataFrame,
    snapshot_dates: list[pd.Timestamp],
    schedule: dict[pd.Timestamp, dict[str, list[str]]],
    variant: dict[str, Any],
    params: dict[str, Any],
) -> tuple[pd.Series, dict[str, Any]]:
    needed = REGIME_TICKERS + [ticker for ticker in DEFENSIVE if ticker != "CASH"]
    sub = prices.copy().dropna(subset=needed)
    if len(sub) < 200:
        return pd.Series(dtype=float), {"error": "insufficient_data"}

    rets = sub.pct_change().fillna(0.0)
    qqq = sub["US.QQQ"]
    spy = sub["US.SPY"]
    trend = qqq.rolling(params["trend_ma"]).mean()
    slow = spy.rolling(params["market_ma"]).mean()

    equity = INITIAL_CAPITAL
    peak = equity
    stopped = False
    current_weights = {"CASH": 1.0}
    curve = []

    for idx, dt in enumerate(sub.index):
        day_ret = current_weights.get("CASH", 0.0) * (RISK_FREE / TRADING_DAYS)
        for ticker, weight in current_weights.items():
            if ticker == "CASH":
                continue
            if ticker in rets.columns and pd.notna(rets.loc[dt, ticker]):
                day_ret += weight * float(rets.loc[dt, ticker])
        equity = max(equity * (1 + day_ret), 0.0)
        peak = max(peak, equity)
        dd = equity / peak - 1.0

        if dd <= -params["dd_stop"]:
            stopped = True
        if stopped and pd.notna(trend.loc[dt]) and qqq.loc[dt] > trend.loc[dt]:
            stopped = False
            peak = equity

        if idx % params["rebal"] == 0:
            qqq_ok = pd.notna(trend.loc[dt]) and qqq.loc[dt] > trend.loc[dt]
            spy_ok = pd.notna(slow.loc[dt]) and spy.loc[dt] > slow.loc[dt]
            risk_on = (not stopped) and qqq_ok and spy_ok
            risk_pool = current_snapshot_tickers(dt, snapshot_dates, schedule, variant)
            if risk_on and risk_pool:
                scores = {}
                for ticker in risk_pool:
                    if ticker not in sub.columns:
                        continue
                    hist = sub.loc[:dt, ticker].dropna()
                    if len(hist) <= params["mom_days"]:
                        continue
                    base = float(hist.iloc[-params["mom_days"] - 1])
                    if base <= 0:
                        continue
                    scores[ticker] = float(hist.iloc[-1] / base - 1.0)
                ranked = sorted(scores, key=scores.get, reverse=True)
                chosen = [ticker for ticker in ranked if scores[ticker] > 0][: params["top_n"]]
                if chosen:
                    weight = 1.0 / len(chosen)
                    current_weights = {ticker: weight for ticker in chosen}
                else:
                    current_weights = dict(DEFENSIVE)
            else:
                current_weights = dict(DEFENSIVE)

        curve.append(equity)

    eq = pd.Series(curve, index=sub.index)
    return eq, calc_metrics(eq)


def write_report(rows: list[dict[str, Any]], manifest_path: Path, out_path: Path) -> None:
    lines = [
        "# V6-B Synthetic Historical Challenger",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Snapshot Manifest: `{manifest_path}`",
        "- Boundary: this is a price-only synthetic no-lookahead probe. Better than lookahead rough test, but still not a final allocator approval.",
        "",
        "| rank | variant | config | ann | OOS | maxDD | sharpe | oos_sharpe | final |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    ranked = sorted(rows, key=lambda row: (row["variant"], -row["metrics"]["sharpe"], -row["metrics"]["ann_ret"]))
    for rank, row in enumerate(ranked, start=1):
        metrics = row["metrics"]
        lines.append(
            f"| {rank} | `{row['variant']}` | `{row['label']}` | "
            f"{metrics['ann_ret'] * 100:+.1f}% | {metrics['oos_ann'] * 100:+.1f}% | "
            f"{metrics['max_dd'] * 100:+.1f}% | {metrics['sharpe']:.2f} | {metrics['oos_sharpe']:.2f} | "
            f"${metrics['final_equity']:,.0f} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run dynamic challenger on synthetic historical Radar snapshots.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2026-05-12")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    snapshot_dates, schedule = load_snapshot_schedule(Path(args.manifest))
    tickers = set(REGIME_TICKERS + list(DEFENSIVE.keys()) + V6A_POOL)
    for rows in schedule.values():
        for selected in rows.values():
            tickers.update(selected)
    tickers.discard("CASH")
    prices = build_price_matrix(sorted(tickers), args.start, args.end)

    rows = []
    for variant_name, variant in VARIANTS.items():
        variant = expand_variant_tracks(variant, schedule)
        for params in ENGINE_PARAMS:
            eq, metrics = run_engine(prices, snapshot_dates, schedule, variant, params)
            if not metrics:
                continue
            rows.append({"variant": variant_name, "label": params["label"], "metrics": metrics})

    out_dir = Path("backtest_results/v6b_synthetic_historical")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"v6b_synth_challenger_{args.tag}.csv"
    md_path = out_dir / f"v6b_synth_challenger_{args.tag}.md"
    payload = []
    for row in rows:
        payload.append({"variant": row["variant"], "label": row["label"], **row["metrics"]})
    pd.DataFrame(payload).to_csv(csv_path, index=False)
    write_report(rows, Path(args.manifest), md_path)
    print(f"CSV:    {csv_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
