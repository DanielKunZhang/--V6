#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from v6b_synthetic_historical import build_price_matrix


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "v6b_theme_rotation"
INITIAL_CAPITAL = 10_000.0
TRADING_DAYS = 252
RISK_FREE = 0.05
TX_COST_BPS = 8.0

THEMES = {
    "broad_beta": {"label": "Broad Beta", "proxies": ["US.SPY", "US.QQQ", "US.IWM"]},
    "technology": {"label": "Technology / Software", "proxies": ["US.XLK", "US.IGV", "US.FDN", "US.ARKK"]},
    "semis_ai": {"label": "Semis / AI Compute", "proxies": ["US.SMH", "US.SOXX"]},
    "healthcare_biotech": {"label": "Healthcare / Biotech", "proxies": ["US.XLV", "US.XBI"]},
    "energy_resources": {"label": "Energy / Resources", "proxies": ["US.XLE", "US.XOP", "US.DBC"]},
    "precious_metals": {"label": "Gold / Precious Metals", "proxies": ["US.GLD", "US.SLV", "US.GDX"]},
    "financials": {"label": "Financials", "proxies": ["US.XLF", "US.KRE"]},
    "industrials_infra": {"label": "Industrials / Infrastructure", "proxies": ["US.XLI"]},
    "utilities_power": {"label": "Utilities / Power", "proxies": ["US.XLU"]},
    "consumer_discretionary": {"label": "Consumer Discretionary", "proxies": ["US.XLY"]},
}

DEFENSIVE = ["US.BIL", "US.IEF", "US.GLD"]
BENCHMARKS = ["US.SPY", "US.QQQ"]


def pct_change(monthly: pd.DataFrame, date: pd.Timestamp, ticker: str, months: int) -> float | None:
    loc = monthly.index.get_loc(date)
    if loc < months:
        return None
    now = float(monthly.loc[date, ticker])
    prev = float(monthly.iloc[loc - months][ticker])
    if prev <= 0 or now <= 0:
        return None
    return now / prev - 1.0


def avg_momentum(monthly: pd.DataFrame, date: pd.Timestamp, ticker: str, windows: list[int]) -> float | None:
    values = [pct_change(monthly, date, ticker, window) for window in windows]
    values = [value for value in values if value is not None and np.isfinite(value)]
    if not values:
        return None
    return float(np.mean(values))


def above_ma(monthly: pd.DataFrame, date: pd.Timestamp, ticker: str, months: int) -> bool:
    loc = monthly.index.get_loc(date)
    if loc < months:
        return False
    ma = float(monthly[ticker].iloc[loc - months + 1 : loc + 1].mean())
    return ma > 0 and float(monthly.loc[date, ticker]) > ma


def theme_scores(monthly: pd.DataFrame, date: pd.Timestamp) -> list[dict[str, Any]]:
    spy_mom = avg_momentum(monthly, date, "US.SPY", [3, 6, 12]) or 0.0
    rows = []
    for theme_id, theme in THEMES.items():
        proxy_rows = []
        for proxy in theme["proxies"]:
            if proxy not in monthly.columns or pd.isna(monthly.loc[date, proxy]):
                continue
            mom = avg_momentum(monthly, date, proxy, [1, 3, 6, 12])
            mom_slow = avg_momentum(monthly, date, proxy, [3, 6, 12])
            if mom is None or mom_slow is None:
                continue
            rel = mom_slow - spy_mom
            trend = above_ma(monthly, date, proxy, 10)
            score = mom * 0.55 + rel * 0.30 + (0.08 if trend else -0.08)
            proxy_rows.append(
                {
                    "proxy": proxy,
                    "score": score,
                    "mom": mom,
                    "mom_slow": mom_slow,
                    "rel_vs_spy": rel,
                    "trend": trend,
                }
            )
        if not proxy_rows:
            continue
        proxy_rows = sorted(proxy_rows, key=lambda row: row["score"], reverse=True)
        top = proxy_rows[0]
        avg_score = float(np.mean([row["score"] for row in proxy_rows]))
        breadth = float(np.mean([1.0 if row["score"] > 0 and row["trend"] else 0.0 for row in proxy_rows]))
        rows.append(
            {
                "theme_id": theme_id,
                "label": theme["label"],
                "selected_proxy": top["proxy"],
                "theme_score": avg_score * 0.65 + top["score"] * 0.25 + breadth * 0.10,
                "top_proxy_score": top["score"],
                "breadth": breadth,
                "proxies": proxy_rows,
            }
        )
    return sorted(rows, key=lambda row: row["theme_score"], reverse=True)


def market_ok(monthly: pd.DataFrame, date: pd.Timestamp) -> bool:
    spy_ok = above_ma(monthly, date, "US.SPY", 10) and (pct_change(monthly, date, "US.SPY", 6) or -1.0) > 0
    qqq_ok = above_ma(monthly, date, "US.QQQ", 10) and (pct_change(monthly, date, "US.QQQ", 6) or -1.0) > 0
    return spy_ok or qqq_ok


def defensive_weights(monthly: pd.DataFrame, date: pd.Timestamp) -> dict[str, float]:
    scores = {ticker: avg_momentum(monthly, date, ticker, [1, 3, 6]) for ticker in DEFENSIVE if ticker in monthly.columns}
    valid = {ticker: score for ticker, score in scores.items() if score is not None and np.isfinite(score)}
    if not valid:
        return {"CASH": 1.0}
    winner = max(valid, key=valid.get)
    return {winner: 1.0}


def pick_weights(monthly: pd.DataFrame, date: pd.Timestamp, top_n: int, min_theme_score: float, risk_weight: float) -> tuple[dict[str, float], list[dict[str, Any]]]:
    rows = theme_scores(monthly, date)
    if not market_ok(monthly, date):
        return defensive_weights(monthly, date), rows
    chosen = [row for row in rows if row["theme_score"] >= min_theme_score and row["top_proxy_score"] > 0][:top_n]
    if not chosen:
        return defensive_weights(monthly, date), rows
    weights = {row["selected_proxy"]: risk_weight / len(chosen) for row in chosen}
    if risk_weight < 1.0:
        weights["US.BIL"] = 1.0 - risk_weight
    return weights, rows


def month_end_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    grouped = pd.Series(index=index, dtype=float).groupby(index.to_period("M")).apply(lambda _: _.index.max())
    return [pd.Timestamp(value) for value in grouped.tolist()]


def run_strategy(prices: pd.DataFrame, top_n: int, min_theme_score: float, risk_weight: float) -> tuple[pd.Series, list[dict[str, Any]]]:
    monthly_dates = [dt for dt in month_end_dates(prices.index) if dt in prices.index]
    monthly = prices.loc[monthly_dates].dropna(how="all")
    returns = prices.pct_change().fillna(0.0)
    weights_by_date: dict[pd.Timestamp, dict[str, float]] = {}
    decisions = []
    for dt in monthly.index:
        if monthly.index.get_loc(dt) < 12:
            weights = {"CASH": 1.0}
            rows = []
        else:
            weights, rows = pick_weights(monthly, pd.Timestamp(dt), top_n, min_theme_score, risk_weight)
        weights_by_date[pd.Timestamp(dt)] = weights
        decisions.append(
            {
                "date": str(pd.Timestamp(dt).date()),
                "weights": weights,
                "top_themes": [
                    {
                        "theme_id": row["theme_id"],
                        "label": row["label"],
                        "selected_proxy": row["selected_proxy"],
                        "theme_score": round(float(row["theme_score"]), 6),
                        "breadth": round(float(row["breadth"]), 6),
                    }
                    for row in rows[:5]
                ],
            }
        )

    equity = INITIAL_CAPITAL
    current_weights = {"CASH": 1.0}
    records = []
    for dt in prices.index:
        day_ret = current_weights.get("CASH", 0.0) * (RISK_FREE / TRADING_DAYS)
        for ticker, weight in current_weights.items():
            if ticker == "CASH":
                continue
            if ticker in returns.columns and pd.notna(returns.loc[dt, ticker]):
                day_ret += weight * float(returns.loc[dt, ticker])
        equity = max(equity * (1.0 + day_ret), 0.0)
        if dt in weights_by_date:
            new_weights = weights_by_date[dt]
            turnover = sum(abs(new_weights.get(k, 0.0) - current_weights.get(k, 0.0)) for k in set(new_weights) | set(current_weights) if k != "CASH")
            equity -= equity * turnover * TX_COST_BPS / 10_000.0
            current_weights = dict(new_weights)
        records.append((dt, equity))
    return pd.Series([value for _, value in records], index=[dt for dt, _ in records]), decisions


def stats(eq: pd.Series) -> dict[str, Any]:
    eq = eq.dropna()
    if len(eq) < 20:
        return {}
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 0.1)
    ann = (float(eq.iloc[-1]) / float(eq.iloc[0])) ** (1.0 / years) - 1.0
    dd = eq / eq.cummax() - 1.0
    dr = eq.pct_change().dropna()
    sharpe = 0.0
    if dr.std() > 1e-10:
        sharpe = float((dr - RISK_FREE / TRADING_DAYS).mean() / dr.std() * np.sqrt(TRADING_DAYS))
    return {
        "ann_ret": ann,
        "max_dd": float(dd.min()),
        "sharpe": sharpe,
        "final": float(eq.iloc[-1]),
    }


def period_stats(eq: pd.Series, start: str, end: str) -> dict[str, Any]:
    seg = eq[(eq.index >= pd.Timestamp(start)) & (eq.index <= pd.Timestamp(end))]
    if len(seg) < 20:
        return {}
    return stats(seg / float(seg.iloc[0]) * INITIAL_CAPITAL)


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.1f}%"


def write_report(result_rows: list[dict[str, Any]], decisions: list[dict[str, Any]], path: Path, start: str, end: str) -> None:
    ranked = sorted(result_rows, key=lambda row: (row["stats"]["sharpe"], row["stats"]["ann_ret"]), reverse=True)
    lines = [
        "# V6-B Dynamic Theme Rotation Backtest v0",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Window: `{start}` to `{end}`",
        "- Scope: first-layer ETF theme discovery only. This tests whether the system can rotate across market themes before entering stock-level candidate pools.",
        "- Design intent: confirm the main uptrend later but avoid staying trapped in an expired theme.",
        "",
        "| rank | config | ann | maxDD | Sharpe | 2020 | 2022 | 2024-2025 | final |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for idx, row in enumerate(ranked, start=1):
        s = row["stats"]
        p2020 = row.get("periods", {}).get("2020", {})
        p2022 = row.get("periods", {}).get("2022", {})
        p2425 = row.get("periods", {}).get("2024_2025", {})
        lines.append(
            f"| {idx} | `{row['config']}` | {fmt_pct(s.get('ann_ret'))} | {fmt_pct(s.get('max_dd'))} | {s.get('sharpe', 0):.2f} | "
            f"{fmt_pct(p2020.get('ann_ret'))} | {fmt_pct(p2022.get('ann_ret'))} | {fmt_pct(p2425.get('ann_ret'))} | ${s.get('final', 0):,.0f} |"
        )
    lines.extend(["", "## Recent Theme Decisions", "", "| date | weights | top themes |", "| --- | --- | --- |"])
    for row in decisions[-12:]:
        weights = ", ".join(f"{ticker}:{weight:.0%}" for ticker, weight in row["weights"].items())
        themes = ", ".join(f"{item['label']}({item['selected_proxy']},{item['theme_score']:.2f})" for item in row["top_themes"][:3])
        lines.append(f"| `{row['date']}` | `{weights}` | {themes} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="V6-B first-layer dynamic theme rotation backtest.")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    tickers = sorted(set(BENCHMARKS + DEFENSIVE + [proxy for theme in THEMES.values() for proxy in theme["proxies"]]))
    prices = build_price_matrix(tickers, args.start, args.end)
    required = [ticker for ticker in tickers if ticker in prices.columns]
    prices = prices[required].dropna(axis=1, how="all").ffill(limit=3).dropna(subset=["US.SPY", "US.QQQ", "US.BIL"])

    configs = []
    for top_n in [1, 2, 3]:
        for min_score in [0.02, 0.05, 0.08]:
            for risk_weight in [0.75, 0.90, 1.0]:
                configs.append((top_n, min_score, risk_weight))

    rows = []
    best_decisions: list[dict[str, Any]] = []
    best_score = -1e9
    for top_n, min_score, risk_weight in configs:
        eq, decisions = run_strategy(prices, top_n=top_n, min_theme_score=min_score, risk_weight=risk_weight)
        s = stats(eq)
        if not s:
            continue
        periods = {
            "2020": period_stats(eq, "2020-01-01", "2020-12-31"),
            "2022": period_stats(eq, "2022-01-01", "2022-12-31"),
            "2024_2025": period_stats(eq, "2024-01-01", "2025-12-31"),
        }
        label = f"top{top_n}_min{min_score:.2f}_risk{risk_weight:.0%}"
        row = {"config": label, "top_n": top_n, "min_score": min_score, "risk_weight": risk_weight, "stats": s, "periods": periods}
        rows.append(row)
        score = s["sharpe"] + max(s["max_dd"], -0.40) + s["ann_ret"] * 0.25
        if score > best_score:
            best_score = score
            best_decisions = decisions

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"v6b_theme_rotation_{args.tag}.json"
    md_path = OUT_DIR / f"v6b_theme_rotation_{args.tag}.md"
    serializable = {"generated_at": datetime.now().isoformat(timespec="seconds"), "start": args.start, "end": args.end, "rows": rows, "best_recent_decisions": best_decisions[-24:]}
    json_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    write_report(rows, best_decisions, md_path, args.start, args.end)
    print(f"JSON: {json_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
