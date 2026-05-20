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
DEFAULT_PIT_MANIFEST = (
    ROOT
    / "v6_strategy_lab"
    / "configs"
    / "synthetic_history"
    / "20260520_v3_dynamic_optics"
    / "manifest.json"
)


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
    "v6b_pit_guarded_top3_90": {
        "top_n": 3,
        "min_theme_score": 0.08,
        "risk_weight": 0.90,
        "use_cooldown": True,
        "vol_target": 0.22,
        "dd_brake": True,
        "expression": "stocks",
        "stock_top_n": 2,
        "pit_manifest": str(DEFAULT_PIT_MANIFEST),
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


def dynamic_overlay_equity(
    curves: dict[str, pd.Series],
    *,
    base_weights: dict[str, float],
    hedge_max: float,
    vol_threshold: float,
    corr_threshold: float,
    dd_threshold: float,
    b_mom_threshold: float | None = None,
    b_dd_threshold: float | None = None,
    b_bad_scale: float = 1.0,
    start: str,
    end: str,
) -> tuple[pd.Series, pd.DataFrame]:
    frame = pd.DataFrame(curves).sort_index().ffill().dropna()
    frame = frame[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
    rets = frame.pct_change().fillna(0.0)
    base_total = sum(base_weights.values())
    if base_total <= 0:
        raise ValueError("base weights must be positive")
    base_norm = {key: value / base_total for key, value in base_weights.items()}
    base_ret = sum(rets[key] * base_norm.get(key, 0.0) for key in base_norm)
    base_eq = (1.0 + base_ret).cumprod()
    base_dd = base_eq / base_eq.cummax() - 1.0

    spy_ma = frame["SPY"].rolling(200).mean()
    qqq_ma = frame["QQQ"].rolling(200).mean()
    gld_ma = frame["GLD"].rolling(126).mean()
    base_vol = base_ret.rolling(63).std() * np.sqrt(252)
    b_key = [key for key in base_norm if key != "V6A"][0]
    ab_corr = rets["V6A"].rolling(63).corr(rets[b_key])
    b_mom = frame[b_key].pct_change(63)
    b_eq = (1.0 + rets[b_key]).cumprod()
    b_dd = b_eq / b_eq.cummax() - 1.0

    equity = INITIAL_CAPITAL
    rows: list[dict[str, Any]] = []
    records: list[tuple[pd.Timestamp, float]] = []
    for i, dt in enumerate(frame.index):
        if i == 0:
            weights = {**base_norm, "GLD": 0.0, "BIL": 0.0}
        else:
            prev = frame.index[i - 1]
            market_bad = (
                pd.notna(spy_ma.loc[prev])
                and pd.notna(qqq_ma.loc[prev])
                and (frame.loc[prev, "SPY"] < spy_ma.loc[prev] or frame.loc[prev, "QQQ"] < qqq_ma.loc[prev])
            )
            drawdown_bad = bool(pd.notna(base_dd.loc[prev]) and base_dd.loc[prev] <= dd_threshold)
            vol_bad = bool(pd.notna(base_vol.loc[prev]) and base_vol.loc[prev] >= vol_threshold)
            corr_bad = bool(pd.notna(ab_corr.loc[prev]) and ab_corr.loc[prev] >= corr_threshold)
            trigger_count = sum([market_bad, drawdown_bad, vol_bad, corr_bad and market_bad])
            hedge_weight = 0.0
            if trigger_count >= 2:
                hedge_weight = hedge_max
            elif trigger_count == 1:
                hedge_weight = hedge_max * 0.5

            hedge_asset = "GLD" if pd.notna(gld_ma.loc[prev]) and frame.loc[prev, "GLD"] >= gld_ma.loc[prev] else "BIL"
            risky_scale = 1.0 - hedge_weight
            weights = {key: value * risky_scale for key, value in base_norm.items()}
            weights["GLD"] = hedge_weight if hedge_asset == "GLD" else 0.0
            weights["BIL"] = hedge_weight if hedge_asset == "BIL" else 0.0
            b_bad = False
            if b_mom_threshold is not None:
                b_bad = b_bad or bool(pd.notna(b_mom.loc[prev]) and b_mom.loc[prev] <= b_mom_threshold)
            if b_dd_threshold is not None:
                b_bad = b_bad or bool(pd.notna(b_dd.loc[prev]) and b_dd.loc[prev] <= b_dd_threshold)
            if b_bad and b_bad_scale < 1.0:
                old_b = weights.get(b_key, 0.0)
                new_b = old_b * b_bad_scale
                freed = old_b - new_b
                weights[b_key] = new_b
                weights[hedge_asset] = weights.get(hedge_asset, 0.0) + freed

        day_ret = sum(float(rets.loc[dt, key]) * weight for key, weight in weights.items() if key in rets.columns)
        equity *= 1.0 + day_ret
        records.append((dt, equity))
        rows.append(
            {
                "date": str(dt.date()),
                "equity": round(float(equity), 2),
                "weights": json.dumps({key: round(float(value), 6) for key, value in weights.items() if value > 1e-9}, sort_keys=True),
            }
        )
    return pd.Series([value for _, value in records], index=[dt for dt, _ in records]), pd.DataFrame(rows)


def dynamic_b_sizing_equity(
    curves: dict[str, pd.Series],
    *,
    b_key: str,
    b_low: float,
    b_mid: float,
    b_high: float,
    b_strong_126d: float,
    b_weak_63d: float,
    hedge_max: float,
    vol_threshold: float,
    corr_threshold: float,
    dd_threshold: float,
    start: str,
    end: str,
) -> tuple[pd.Series, pd.DataFrame]:
    frame = pd.DataFrame(curves).sort_index().ffill().dropna()
    frame = frame[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
    rets = frame.pct_change().fillna(0.0)
    spy_ma = frame["SPY"].rolling(200).mean()
    qqq_ma = frame["QQQ"].rolling(200).mean()
    gld_ma = frame["GLD"].rolling(126).mean()
    b_mom_63 = frame[b_key].pct_change(63)
    b_mom_126 = frame[b_key].pct_change(126)
    ab_corr = rets["V6A"].rolling(63).corr(rets[b_key])

    equity = INITIAL_CAPITAL
    base_equity = 1.0
    base_peak = 1.0
    records: list[tuple[pd.Timestamp, float]] = []
    rows: list[dict[str, Any]] = []
    for i, dt in enumerate(frame.index):
        if i == 0:
            b_weight = b_mid
            weights = {"V6A": 1.0 - b_weight, b_key: b_weight, "GLD": 0.0, "BIL": 0.0}
        else:
            prev = frame.index[i - 1]
            market_ok = (
                pd.notna(spy_ma.loc[prev])
                and pd.notna(qqq_ma.loc[prev])
                and frame.loc[prev, "SPY"] > spy_ma.loc[prev]
                and frame.loc[prev, "QQQ"] > qqq_ma.loc[prev]
            )
            market_bad = (
                pd.notna(spy_ma.loc[prev])
                and pd.notna(qqq_ma.loc[prev])
                and (frame.loc[prev, "SPY"] < spy_ma.loc[prev] or frame.loc[prev, "QQQ"] < qqq_ma.loc[prev])
            )
            b_weight = b_mid
            if pd.notna(b_mom_126.loc[prev]) and b_mom_126.loc[prev] >= b_strong_126d and market_ok:
                b_weight = b_high
            if pd.notna(b_mom_63.loc[prev]) and b_mom_63.loc[prev] <= b_weak_63d:
                b_weight = b_low
            if market_bad and pd.notna(ab_corr.loc[prev]) and ab_corr.loc[prev] >= corr_threshold:
                b_weight = min(b_weight, b_low)

            a_weight = 1.0 - b_weight
            base_ret = a_weight * float(rets.loc[dt, "V6A"]) + b_weight * float(rets.loc[dt, b_key])
            base_equity *= 1.0 + base_ret
            base_peak = max(base_peak, base_equity)
            base_dd = base_equity / base_peak - 1.0
            blend_ret = a_weight * rets["V6A"] + b_weight * rets[b_key]
            base_vol = float(blend_ret.iloc[max(0, i - 63) : i].std() * np.sqrt(252)) if i > 20 else np.nan
            trigger_count = 0
            if market_bad:
                trigger_count += 1
            if np.isfinite(base_vol) and base_vol >= vol_threshold:
                trigger_count += 1
            if base_dd <= dd_threshold:
                trigger_count += 1
            if market_bad and pd.notna(ab_corr.loc[prev]) and ab_corr.loc[prev] >= corr_threshold:
                trigger_count += 1
            hedge_weight = hedge_max if trigger_count >= 2 else (hedge_max * 0.5 if trigger_count == 1 else 0.0)
            hedge_asset = "GLD" if pd.notna(gld_ma.loc[prev]) and frame.loc[prev, "GLD"] >= gld_ma.loc[prev] else "BIL"
            weights = {"V6A": a_weight * (1.0 - hedge_weight), b_key: b_weight * (1.0 - hedge_weight), "GLD": 0.0, "BIL": 0.0}
            weights[hedge_asset] = hedge_weight

        day_ret = sum(float(rets.loc[dt, key]) * weight for key, weight in weights.items() if key in rets.columns)
        equity *= 1.0 + day_ret
        records.append((dt, equity))
        rows.append(
            {
                "date": str(dt.date()),
                "equity": round(float(equity), 2),
                "weights": json.dumps({key: round(float(value), 6) for key, value in weights.items() if value > 1e-9}, sort_keys=True),
            }
        )
    return pd.Series([value for _, value in records], index=[dt for dt, _ in records]), pd.DataFrame(rows)


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
        "- Purpose: test whether V6-A stability plus V6-B theme rotation plus dynamic Hedge/Cash Overlay can raise portfolio Sharpe.",
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
            "- Dynamic overlay rows use GLD/BIL only when risk triggers fire; GLD is not treated as a fixed permanent sleeve.",
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
            "US.INTC",
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
                        rows.append({"mode": "static", "config": b_name, "weights": weights, "stats": s})

        if b_name not in {"v6b_guarded_top3_90", "v6b_pit_guarded_top3_90"}:
            continue
        for a_w in [0.65, 0.70, 0.75]:
            for b_w in [0.25, 0.30, 0.35]:
                if a_w + b_w <= 0 or a_w + b_w > 1.0:
                    continue
                for hedge_max in [0.25, 0.30]:
                    for vol_threshold in [0.28]:
                        for corr_threshold in [0.60, 0.65]:
                            for dd_threshold in [-0.10, -0.12]:
                                weights = {"V6A": a_w, b_name: b_w}
                                eq, overlay_log = dynamic_overlay_equity(
                                    {key: curves[key] for key in ["V6A", b_name, "GLD", "BIL", "SPY", "QQQ"]},
                                    base_weights=weights,
                                    hedge_max=hedge_max,
                                    vol_threshold=vol_threshold,
                                    corr_threshold=corr_threshold,
                                    dd_threshold=dd_threshold,
                                    start=args.start,
                                    end=args.end,
                                )
                                s = stats(eq)
                                if not s:
                                    continue
                                rows.append(
                                    {
                                        "mode": "dynamic_overlay_refined",
                                        "config": b_name,
                                        "weights": {
                                            **weights,
                                            "hedge_max": hedge_max,
                                            "vol_trigger": vol_threshold,
                                            "corr_trigger": corr_threshold,
                                            "dd_trigger": dd_threshold,
                                        },
                                        "stats": s,
                                        "overlay_days": int((overlay_log["weights"].str.contains("GLD|BIL")).sum()) if not overlay_log.empty else 0,
                                    }
                                )
        for a_w, b_w in [(0.70, 0.30), (0.65, 0.25), (0.75, 0.25)]:
            for hedge_max in [0.25, 0.30]:
                for corr_threshold in [0.60, 0.65]:
                    for dd_threshold in [-0.10, -0.12]:
                        for b_bad_scale in [0.0, 0.5]:
                            for b_mom_threshold in [0.0, -0.03]:
                                for b_dd_threshold in [-0.08, -0.12]:
                                    weights = {"V6A": a_w, b_name: b_w}
                                    eq, overlay_log = dynamic_overlay_equity(
                                        {key: curves[key] for key in ["V6A", b_name, "GLD", "BIL", "SPY", "QQQ"]},
                                        base_weights=weights,
                                        hedge_max=hedge_max,
                                        vol_threshold=0.28,
                                        corr_threshold=corr_threshold,
                                        dd_threshold=dd_threshold,
                                        b_mom_threshold=b_mom_threshold,
                                        b_dd_threshold=b_dd_threshold,
                                        b_bad_scale=b_bad_scale,
                                        start=args.start,
                                        end=args.end,
                                    )
                                    s = stats(eq)
                                    if not s:
                                        continue
                                    rows.append(
                                        {
                                            "mode": "dynamic_overlay_b_control",
                                            "config": b_name,
                                            "weights": {
                                                **weights,
                                                "hedge_max": hedge_max,
                                                "vol_trigger": 0.28,
                                                "corr_trigger": corr_threshold,
                                                "dd_trigger": dd_threshold,
                                                "b_bad_scale": b_bad_scale,
                                                "b_mom_trigger": b_mom_threshold,
                                                "b_dd_trigger": b_dd_threshold,
                                            },
                                            "stats": s,
                                            "overlay_days": int((overlay_log["weights"].str.contains("GLD|BIL")).sum()) if not overlay_log.empty else 0,
                                        }
                                    )
        dynamic_b_grid = [
            {"b_low": 0.05, "b_mid": 0.30, "b_high": 0.45, "b_strong_126d": 0.08, "b_weak_63d": -0.08},
            {"b_low": 0.05, "b_mid": 0.30, "b_high": 0.35, "b_strong_126d": 0.16, "b_weak_63d": -0.08},
            {"b_low": 0.10, "b_mid": 0.30, "b_high": 0.45, "b_strong_126d": 0.08, "b_weak_63d": -0.08},
        ]
        for grid in dynamic_b_grid:
            eq, sizing_log = dynamic_b_sizing_equity(
                {key: curves[key] for key in ["V6A", b_name, "GLD", "BIL", "SPY", "QQQ"]},
                b_key=b_name,
                hedge_max=0.30,
                vol_threshold=0.28,
                corr_threshold=0.60,
                dd_threshold=-0.12,
                start=args.start,
                end=args.end,
                **grid,
            )
            s = stats(eq)
            if not s:
                continue
            rows.append(
                {
                    "mode": "dynamic_b_sizing",
                    "config": b_name,
                    "weights": {
                        "V6A": 1.0 - grid["b_mid"],
                        b_name: grid["b_mid"],
                        **grid,
                        "hedge_max": 0.30,
                        "vol_trigger": 0.28,
                        "corr_trigger": 0.60,
                        "dd_trigger": -0.12,
                    },
                    "stats": s,
                    "overlay_days": int((sizing_log["weights"].str.contains("GLD|BIL")).sum()) if not sizing_log.empty else 0,
                }
            )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"v6ab_sleeve_blend_{args.tag}.json"
    md_path = OUT_DIR / f"v6ab_sleeve_blend_{args.tag}.md"
    csv_path = OUT_DIR / f"v6ab_sleeve_blend_{args.tag}.csv"
    pd.DataFrame([{**{"mode": row["mode"], "config": row["config"], "overlay_days": row.get("overlay_days", "")}, **row["weights"], **row["stats"]} for row in rows]).sort_values(["sharpe", "ann_ret"], ascending=False).to_csv(csv_path, index=False)
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
