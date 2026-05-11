#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd

import alpha_cash_enhancement_search as alpha


ROOT = Path(__file__).parent
OUT_DIR = ROOT / "backtest_results" / "v6b_radar_momentum"
TRADING_DAYS = alpha.TRADING_DAYS
INITIAL_CAPITAL = alpha.INITIAL_CAPITAL
RISK_FREE = alpha.RISK_FREE


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def rolling_hv(prices: pd.Series, window: int) -> pd.Series:
    return np.log(prices / prices.shift(1)).rolling(window).std() * math.sqrt(TRADING_DAYS)


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def calc_stats(eq: pd.Series) -> Dict[str, Any]:
    return alpha.calc_stats(eq) if not eq.empty else {}


def rolling_gate(eq: pd.Series) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    monthly = eq.resample("ME").last()
    for years in [3, 5]:
        ann: List[float] = []
        dd: List[float] = []
        for end in monthly.index:
            start = end - pd.DateOffset(years=years)
            seg = eq[(eq.index >= start) & (eq.index <= end)].dropna()
            if len(seg) < years * 180:
                continue
            seg = seg / float(seg.iloc[0]) * INITIAL_CAPITAL
            stats = calc_stats(seg)
            if stats:
                ann.append(as_float(stats.get("ann_ret")))
                dd.append(as_float(stats.get("max_dd")))
        if ann:
            out[f"rolling_{years}y_worst_ann"] = round(float(np.min(ann)), 2)
            out[f"rolling_{years}y_p10_ann"] = round(float(np.quantile(ann, 0.10)), 2)
            out[f"rolling_{years}y_median_ann"] = round(float(np.median(ann)), 2)
            out[f"rolling_{years}y_worst_dd"] = round(float(np.min(dd)), 2)
    return out


def evaluate_equity(eq: pd.Series) -> Dict[str, Any]:
    row = alpha.evaluate_equity(eq)
    if not row:
        return {}
    row["min_equity_pct"] = round(float(eq.min() / INITIAL_CAPITAL * 100), 2)
    row.update(rolling_gate(eq))
    return row


def all_tickers(config: Dict[str, Any], variants: Iterable[str]) -> List[str]:
    required = {"US.SPY", "US.QQQ"}
    for variant in variants:
        required.update(config["candidate_pool_variants"][variant])
    required.update(t for t in config["defensive_pool"] if t != "CASH")
    return sorted(required)


def fetch_data_cache_only(tickers: Iterable[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    cache_dir = ROOT / "backtest_results" / "price_cache"
    data: Dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        cached = alpha.read_cache(ticker, cache_dir, start, end)
        if cached is not None and not cached.empty:
            data[ticker] = cached
            print(f"  cache {ticker}: {cached['date'].min().date()}~{cached['date'].max().date()} {len(cached)} days")
        else:
            print(f"  missing cache {ticker}")
    return data


def missing_tickers(prices: pd.DataFrame, tickers: Iterable[str]) -> List[str]:
    return [t for t in tickers if t != "CASH" and (t not in prices.columns or prices[t].dropna().shape[0] <= 260)]


def run_v6b_strategy(
    prices: pd.DataFrame,
    risk_assets: List[str],
    defensive: Dict[str, float],
    params: Dict[str, Any],
) -> tuple[pd.Series, pd.DataFrame]:
    needed = sorted(set(risk_assets + [t for t in defensive if t != "CASH"] + ["US.SPY", "US.QQQ"]))
    if missing_tickers(prices, needed):
        return pd.Series(dtype=float), pd.DataFrame()

    px = prices[needed].dropna().copy()
    if len(px) < 500:
        return pd.Series(dtype=float), pd.DataFrame()

    returns = px.pct_change().fillna(0.0)
    qqq = px["US.QQQ"]
    spy = px["US.SPY"]
    trend = qqq.rolling(params["trend_ma"]).mean()
    slow = spy.rolling(params["market_ma"]).mean()
    market_mom = qqq.pct_change(params["market_mom"])
    hv = rolling_hv(qqq, params["vol_window"]).fillna(0.30)
    risk_mom = {ticker: px[ticker].pct_change(params["asset_mom"]) for ticker in risk_assets}

    equity = INITIAL_CAPITAL
    peak = equity
    stopped = False
    current_weights: Dict[str, float] = {"CASH": 1.0}
    records = []
    rebalances = []

    for idx, dt in enumerate(px.index):
        day_ret = current_weights.get("CASH", 0.0) * (RISK_FREE / TRADING_DAYS)
        gross = 0.0
        for ticker, weight in current_weights.items():
            if ticker == "CASH":
                continue
            gross += abs(weight)
            day_ret += weight * float(returns.loc[dt, ticker])
        if gross > 1.0:
            day_ret -= (gross - 1.0) * ((RISK_FREE + params["financing_spread"]) / TRADING_DAYS)
        equity = max(equity * (1.0 + day_ret), 0.0)

        peak = max(peak, equity)
        dd = equity / peak - 1.0 if peak > 0 else 0.0
        if dd <= -params["dd_stop"]:
            stopped = True
        if stopped and qqq.loc[dt] > trend.loc[dt] and hv.loc[dt] <= params["recovery_hv"]:
            stopped = False
            peak = equity

        if idx % params["rebalance_days"] == 0:
            risk_on = (
                not stopped
                and pd.notna(trend.loc[dt])
                and pd.notna(slow.loc[dt])
                and qqq.loc[dt] > trend.loc[dt]
                and spy.loc[dt] > slow.loc[dt]
                and market_mom.loc[dt] >= params["market_mom_threshold"]
                and hv.loc[dt] <= params["hv_cap"]
            )
            if risk_on:
                scored = sorted(risk_assets, key=lambda ticker: risk_mom[ticker].loc[dt], reverse=True)
                chosen = [ticker for ticker in scored[: params["top_n"]] if pd.notna(risk_mom[ticker].loc[dt])]
                if not chosen:
                    new_weights = {"CASH": 1.0}
                else:
                    vol_scale = params["target_vol"] / max(float(hv.loc[dt]), 0.05)
                    exposure = min(params["max_exposure"], max(params["min_exposure"], params["base_exposure"] * vol_scale))
                    if dd <= -params["dd_soft"]:
                        brake = max(0.0, min(1.0, (params["dd_stop"] + dd) / max(params["dd_stop"] - params["dd_soft"], 1e-6)))
                        exposure *= brake
                    new_weights = {ticker: exposure / len(chosen) for ticker in chosen}
                    new_weights["CASH"] = max(0.0, 1.0 - sum(new_weights.values()))
            else:
                new_weights = dict(defensive)

            turnover = sum(
                abs(new_weights.get(k, 0.0) - current_weights.get(k, 0.0))
                for k in set(new_weights) | set(current_weights)
                if k != "CASH"
            )
            equity -= equity * turnover * params["transaction_cost_bps"] / 10_000
            current_weights = new_weights
            rebalances.append(
                {
                    "date": dt,
                    "risk_on": risk_on,
                    "stopped": stopped,
                    "chosen": "|".join([k for k, v in current_weights.items() if k != "CASH" and abs(v) > 1e-9]),
                    "turnover": round(float(turnover), 6),
                    "gross_exposure": round(sum(abs(v) for k, v in current_weights.items() if k != "CASH"), 6),
                    "weights_json": json.dumps(current_weights, ensure_ascii=False, sort_keys=True),
                    "drawdown": round(float(dd), 6),
                }
            )

        records.append((dt, equity))

    eq = pd.Series([v for _, v in records], index=[dt for dt, _ in records]).sort_index()
    rb = pd.DataFrame(rebalances)
    return eq, rb


def parameter_grid() -> List[Dict[str, Any]]:
    rows = []
    idx = 1
    for top_n in [2, 3, 4]:
        for asset_mom in [20, 60, 120]:
            for max_exposure in [1.0, 1.25]:
                rows.append(
                    {
                        "candidate_id": f"V6B{idx:04d}",
                        "top_n": top_n,
                        "asset_mom": asset_mom,
                        "trend_ma": 100,
                        "market_ma": 150,
                        "market_mom": 60,
                        "market_mom_threshold": 0.0,
                        "vol_window": 20,
                        "hv_cap": 0.35,
                        "recovery_hv": 0.22,
                        "target_vol": 0.16,
                        "base_exposure": 1.0,
                        "min_exposure": 0.50,
                        "max_exposure": max_exposure,
                        "dd_soft": 0.12,
                        "dd_stop": 0.25,
                        "rebalance_days": 21,
                        "transaction_cost_bps": 8.0,
                        "financing_spread": 0.015,
                    }
                )
                idx += 1
    return rows


def gate(row: Dict[str, Any], baseline: Dict[str, Any] | None) -> str:
    if not baseline:
        return "baseline_or_no_gate"
    oos = as_float(row.get("oos_ann_ret"))
    oos_sharpe = as_float(row.get("oos_sharpe"))
    dd = as_float(row.get("full_max_dd"))
    b_oos = as_float(baseline.get("oos_ann_ret"))
    b_sharpe = as_float(baseline.get("oos_sharpe"))
    b_dd = as_float(baseline.get("full_max_dd"))
    if oos >= b_oos + 3.0 and oos_sharpe >= b_sharpe and dd >= b_dd - 5.0:
        return "v6b_challenger_candidate"
    if oos >= b_oos and dd >= b_dd - 5.0:
        return "v6b_watchlist"
    return "research_only"


def write_report(results: pd.DataFrame, missing: Dict[str, List[str]], path: Path) -> None:
    lines = [
        "# V6-B Radar Momentum Challenger",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        "- Status: research only; no live trading approval.",
        "- Goal: test whether Radar-generated universe improves V6-A without overfitting or worse drawdown.",
        "",
        "## Data Coverage",
        "",
    ]
    for variant, miss in missing.items():
        status = "PASS" if not miss else "MISSING: " + ", ".join(miss)
        lines.append(f"- `{variant}`: {status}")
    lines.extend(
        [
            "",
            "## Top Results",
            "",
            "| rank | variant | candidate | gate | full | OOS | recent | DD | Sharpe full/OOS | rolling 3y worst | desc |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    top = results.sort_values(["gate_rank", "oos_sharpe", "oos_ann_ret"], ascending=[True, False, False]).head(30)
    for rank, (_, row) in enumerate(top.iterrows(), start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    str(row["variant"]),
                    str(row["candidate_id"]),
                    str(row["gate"]),
                    f"{row['full_ann_ret']:.2f}% / {row['full_max_dd']:.2f}%",
                    f"{row['oos_ann_ret']:.2f}% / {row['oos_max_dd']:.2f}%",
                    f"{row['recent_ann_ret']:.2f}% / {row['recent_max_dd']:.2f}%",
                    f"{row['full_max_dd']:.2f}%",
                    f"{row['full_sharpe']:.2f} / {row['oos_sharpe']:.2f}",
                    f"{row.get('rolling_3y_worst_ann', math.nan):.2f}",
                    str(row["candidate_desc"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation Rules",
            "",
            "- If broader V6-B variants underperform narrower V6-B variants, satellites are adding noise.",
            "- If `v6b_eligible_only` or an equivalent high-score pool improves over `v6a_base_only`, Radar scoring may add value.",
            "- If no V6-B variant beats or complements baseline, Radar remains research input and V6-B allocation stays 0%.",
            "- Missing data means no conclusion for that V6-B variant; do not infer failure or success until coverage is complete.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="V6-B Radar momentum challenger research backtest.")
    parser.add_argument("--config", default="v6_strategy_lab/configs/v6b_radar_universe_20260510.json")
    parser.add_argument("--start", default="2012-01-01")
    parser.add_argument("--end", default="2026-05-08")
    parser.add_argument("--refresh-data", action="store_true")
    parser.add_argument("--cache-only", action="store_true", help="Do not call Futu; only use existing price_cache files.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    config = load_config(Path(args.config))
    variants = list(config["candidate_pool_variants"].keys())
    required = all_tickers(config, variants)
    if args.cache_only:
        data = fetch_data_cache_only(required, args.start, args.end)
    else:
        data = alpha.fetch_data(required, args.start, args.end, args.refresh_data)
    prices = alpha.prepare_prices(data, args.start, args.end)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    missing_by_variant: Dict[str, List[str]] = {}
    rows = []
    rebalances = []
    baseline_best: Dict[str, Any] | None = None

    for variant in variants:
        risk_assets = config["candidate_pool_variants"][variant]
        miss = missing_tickers(prices, risk_assets + ["US.SPY", "US.QQQ"] + [t for t in config["defensive_pool"] if t != "CASH"])
        missing_by_variant[variant] = miss
        if miss:
            continue
        best_for_variant: Dict[str, Any] | None = None
        for params in parameter_grid():
            eq, rb = run_v6b_strategy(prices, risk_assets, config["defensive_pool"], params)
            metrics = evaluate_equity(eq)
            if not metrics:
                continue
            record = {
                "variant": variant,
                "candidate_id": params["candidate_id"],
                "candidate_desc": f"top{params['top_n']} mom{params['asset_mom']} maxExp{params['max_exposure']}",
                **params,
                **metrics,
            }
            rows.append(record)
            if rb is not None and not rb.empty:
                rb = rb.copy()
                rb["variant"] = variant
                rb["candidate_id"] = params["candidate_id"]
                rebalances.append(rb)
            if best_for_variant is None or as_float(record.get("oos_sharpe")) > as_float(best_for_variant.get("oos_sharpe")):
                best_for_variant = record
        if variant == "v6a_base_only":
            baseline_best = best_for_variant

    results = pd.DataFrame(rows)
    if results.empty:
        missing_path = OUT_DIR / f"v6b_missing_{args.tag}.json"
        missing_path.write_text(json.dumps(missing_by_variant, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"No valid results. Missing coverage written to {missing_path}")
        return

    gates = []
    for _, row in results.iterrows():
        row_dict = row.to_dict()
        g = "v6a_baseline" if row["variant"] == "v6a_base_only" else gate(row_dict, baseline_best)
        gates.append(g)
    results["gate"] = gates
    rank_map = {"v6b_challenger_candidate": 0, "v6b_watchlist": 1, "v6a_baseline": 2, "research_only": 3, "baseline_or_no_gate": 4}
    results["gate_rank"] = results["gate"].map(rank_map).fillna(9)

    csv_path = OUT_DIR / f"v6b_results_{args.tag}.csv"
    md_path = OUT_DIR / f"v6b_report_{args.tag}.md"
    rb_path = OUT_DIR / f"v6b_rebalances_{args.tag}.csv"
    missing_path = OUT_DIR / f"v6b_missing_{args.tag}.json"

    results.to_csv(csv_path, index=False)
    if rebalances:
        pd.concat(rebalances, ignore_index=True).to_csv(rb_path, index=False)
    missing_path.write_text(json.dumps(missing_by_variant, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(results, missing_by_variant, md_path)

    print(f"Results: {csv_path}")
    print(f"Report:  {md_path}")
    print(f"Missing: {missing_path}")
    if rebalances:
        print(f"Rebals:  {rb_path}")


if __name__ == "__main__":
    main()
