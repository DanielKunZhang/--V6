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
    "broad_beta": {"label": "Broad Beta", "proxies": ["US.SPY", "US.QQQ", "US.IWM"], "stocks": ["US.AMZN", "US.MSFT", "US.GOOGL", "US.META", "US.TSLA"]},
    "technology": {"label": "Technology / Software", "proxies": ["US.XLK", "US.IGV", "US.FDN", "US.ARKK"], "stocks": ["US.MSFT", "US.GOOGL", "US.META", "US.AMZN", "US.NFLX"]},
    "semis_ai": {"label": "Semis / AI Compute", "proxies": ["US.SMH", "US.SOXX"], "stocks": ["US.NVDA", "US.AVGO", "US.AMD", "US.ANET", "US.TSM", "US.MU", "US.WDC", "US.AMKR", "US.COHR", "US.AAOI", "US.LITE", "US.MRVL", "US.NOK"]},
    "healthcare_biotech": {"label": "Healthcare / Biotech", "proxies": ["US.XLV", "US.XBI"], "stocks": ["US.LLY"]},
    "energy_resources": {"label": "Energy / Resources", "proxies": ["US.XLE", "US.XOP", "US.DBC"], "stocks": []},
    "precious_metals": {"label": "Gold / Precious Metals", "proxies": ["US.GLD", "US.SLV", "US.GDX"], "stocks": []},
    "financials": {"label": "Financials", "proxies": ["US.XLF", "US.KRE"], "stocks": ["US.JPM", "US.BRK.B"]},
    "industrials_infra": {"label": "Industrials / Infrastructure", "proxies": ["US.XLI"], "stocks": ["US.ROK", "US.ETN", "US.HON", "US.IR", "US.TER"]},
    "utilities_power": {"label": "Utilities / Power", "proxies": ["US.XLU"], "stocks": []},
    "consumer_discretionary": {"label": "Consumer Discretionary", "proxies": ["US.XLY"], "stocks": ["US.AMZN", "US.TSLA", "US.NFLX"]},
}

DEFENSIVE = ["US.BIL", "US.IEF", "US.GLD"]
BENCHMARKS = ["US.SPY", "US.QQQ", "US.BRK.B", "US.VTV"]
DEFAULT_PIT_THEME_MAP = {
    "semis_ai": [
        "core_reacceleration",
        "bottleneck_diffusion",
        "optics_and_interconnect",
        "turnaround_momentum",
    ]
}


def load_pit_universe(manifest_path: str | Path | None) -> dict[str, Any] | None:
    if not manifest_path:
        return None
    path = Path(manifest_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    schedule: dict[pd.Timestamp, dict[str, list[str]]] = {}
    dates: list[pd.Timestamp] = []
    for row in payload.get("snapshots", []):
        as_of = pd.Timestamp(row["as_of"])
        dates.append(as_of)
        schedule[as_of] = {track: list(tickers) for track, tickers in row.get("selected", {}).items()}
    dates.sort()
    return {"manifest_path": str(path), "dates": dates, "schedule": schedule}


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


def is_overheated(monthly: pd.DataFrame, date: pd.Timestamp, ticker: str) -> bool:
    one_month = pct_change(monthly, date, ticker, 1)
    three_month = pct_change(monthly, date, ticker, 3)
    loc = monthly.index.get_loc(date)
    if loc < 12 or one_month is None or three_month is None:
        return False
    window = monthly[ticker].iloc[loc - 11 : loc + 1].dropna()
    if window.empty:
        return False
    close = float(monthly.loc[date, ticker])
    high_12m = float(window.max())
    near_high = high_12m > 0 and close / high_12m > 0.97
    return near_high and (one_month > 0.18 or three_month > 0.35)


def realized_vol(monthly: pd.DataFrame, date: pd.Timestamp, ticker: str, months: int = 6) -> float | None:
    loc = monthly.index.get_loc(date)
    if loc < months:
        return None
    prices = monthly[ticker].iloc[loc - months : loc + 1].dropna()
    rets = prices.pct_change().dropna()
    if rets.empty or rets.std() <= 0:
        return None
    return float(rets.std() * np.sqrt(12))


def stock_candidates_for_theme(
    theme_id: str,
    date: pd.Timestamp | None = None,
    pit_universe: dict[str, Any] | None = None,
    pit_theme_map: dict[str, list[str]] | None = None,
) -> list[str]:
    if date is not None and pit_universe is not None:
        theme_map = pit_theme_map or DEFAULT_PIT_THEME_MAP
        tracks = theme_map.get(theme_id)
        if tracks:
            eligible_dates = [as_of for as_of in pit_universe["dates"] if as_of <= date]
            if eligible_dates:
                snapshot = pit_universe["schedule"].get(eligible_dates[-1], {})
                dynamic: list[str] = []
                for track in tracks:
                    dynamic.extend(snapshot.get(track, []))
                return list(dict.fromkeys(dynamic))
            return []
    return list(THEMES.get(theme_id, {}).get("stocks", []))


def rank_stock_candidates(
    monthly: pd.DataFrame,
    date: pd.Timestamp,
    theme_id: str,
    max_names: int,
    *,
    pit_universe: dict[str, Any] | None = None,
    pit_theme_map: dict[str, list[str]] | None = None,
) -> list[str]:
    candidates = []
    for ticker in stock_candidates_for_theme(theme_id, date, pit_universe, pit_theme_map):
        if ticker not in monthly.columns or pd.isna(monthly.loc[date, ticker]):
            continue
        if not above_ma(monthly, date, ticker, 10):
            continue
        mom = avg_momentum(monthly, date, ticker, [1, 3, 6])
        mom_slow = avg_momentum(monthly, date, ticker, [3, 6, 12])
        if mom is None or mom_slow is None or mom <= 0:
            continue
        candidates.append((ticker, mom * 0.65 + mom_slow * 0.35))
    candidates.sort(key=lambda row: row[1], reverse=True)
    return [ticker for ticker, _ in candidates[:max_names]]


def pick_weights(
    monthly: pd.DataFrame,
    date: pd.Timestamp,
    top_n: int,
    min_theme_score: float,
    risk_weight: float,
    *,
    use_cooldown: bool,
    vol_target: float | None,
    expression: str,
    stock_top_n: int,
    pit_universe: dict[str, Any] | None = None,
    pit_theme_map: dict[str, list[str]] | None = None,
    selection_mode: str = "multi_theme",
    dominant_state: dict[str, Any] | None = None,
    dominant_margin: float = 0.08,
    challenger_confirm_months: int = 2,
    incumbent_exit_rank: int = 3,
    mainline_confirm_months: int = 4,
    mainline_exit_months: int = 2,
    mainline_min_score: float = 0.18,
    mainline_rank_limit: int = 2,
    mainline_confirm_score: float = 4.0,
    mainline_decay: float = 0.65,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    rows = theme_scores(monthly, date)
    if not market_ok(monthly, date):
        return defensive_weights(monthly, date), rows
    candidates = [row for row in rows if row["theme_score"] >= min_theme_score and row["top_proxy_score"] > 0]
    if use_cooldown:
        cooled = [row for row in candidates if not is_overheated(monthly, date, row["selected_proxy"])]
        if cooled:
            candidates = cooled
    if not candidates:
        return defensive_weights(monthly, date), rows
    if selection_mode == "dominant_confirmed":
        if dominant_state is None:
            dominant_state = {}
        leader = candidates[0]
        current_theme = dominant_state.get("current_theme")
        current_idx = next((idx for idx, row in enumerate(candidates) if row["theme_id"] == current_theme), None)
        current_row = candidates[current_idx] if current_idx is not None else None
        if current_row is None or current_idx + 1 > incumbent_exit_rank:
            dominant_state["current_theme"] = leader["theme_id"]
            dominant_state["challenger_theme"] = None
            dominant_state["challenger_count"] = 0
            chosen = [leader]
        elif leader["theme_id"] == current_theme:
            dominant_state["challenger_theme"] = None
            dominant_state["challenger_count"] = 0
            chosen = [current_row]
        else:
            lead = float(leader["theme_score"] - current_row["theme_score"])
            if lead >= dominant_margin:
                if dominant_state.get("challenger_theme") == leader["theme_id"]:
                    dominant_state["challenger_count"] = int(dominant_state.get("challenger_count", 0)) + 1
                else:
                    dominant_state["challenger_theme"] = leader["theme_id"]
                    dominant_state["challenger_count"] = 1
                if int(dominant_state.get("challenger_count", 0)) >= challenger_confirm_months:
                    dominant_state["current_theme"] = leader["theme_id"]
                    dominant_state["challenger_theme"] = None
                    dominant_state["challenger_count"] = 0
                    chosen = [leader]
                else:
                    chosen = [current_row]
            else:
                dominant_state["challenger_theme"] = None
                dominant_state["challenger_count"] = 0
                chosen = [current_row]
    elif selection_mode == "mainline_state_v1":
        if dominant_state is None:
            dominant_state = {}
        leader = candidates[0]
        current_theme = dominant_state.get("mainline_theme")
        candidate_theme = dominant_state.get("candidate_theme")
        candidate_count = int(dominant_state.get("candidate_count", 0))
        confirmed = bool(dominant_state.get("confirmed", False))
        current_idx = next((idx for idx, row in enumerate(candidates) if row["theme_id"] == current_theme), None)
        current_row = candidates[current_idx] if current_idx is not None else None
        leader_is_confirmable = leader["theme_score"] >= mainline_min_score and leader["breadth"] >= 0.66

        if leader_is_confirmable and (candidate_theme == leader["theme_id"]):
            candidate_count += 1
        elif leader_is_confirmable:
            candidate_theme = leader["theme_id"]
            candidate_count = 1
        else:
            candidate_theme = None
            candidate_count = 0

        if (not confirmed) and candidate_theme and candidate_count >= mainline_confirm_months:
            current_theme = candidate_theme
            current_row = leader
            confirmed = True
            dominant_state["weak_count"] = 0

        if confirmed:
            if current_row is None or current_idx is None or current_idx + 1 > incumbent_exit_rank or current_row["theme_score"] < min_theme_score:
                dominant_state["weak_count"] = int(dominant_state.get("weak_count", 0)) + 1
            else:
                dominant_state["weak_count"] = 0
            if int(dominant_state.get("weak_count", 0)) >= mainline_exit_months:
                confirmed = False
                current_theme = None
                current_row = None
                dominant_state["weak_count"] = 0

        dominant_state["candidate_theme"] = candidate_theme
        dominant_state["candidate_count"] = candidate_count
        dominant_state["mainline_theme"] = current_theme
        dominant_state["confirmed"] = confirmed
        if confirmed and current_row is not None:
            chosen = [current_row]
        else:
            chosen = candidates[:top_n]
    elif selection_mode == "mainline_state_v2":
        if dominant_state is None:
            dominant_state = {}
        persistence = dict(dominant_state.get("persistence", {}))
        eligible_theme_ids = set()
        for rank, row in enumerate(candidates, start=1):
            if rank > mainline_rank_limit:
                continue
            if row["theme_score"] < mainline_min_score or row["breadth"] < 0.66:
                continue
            eligible_theme_ids.add(row["theme_id"])
            persistence[row["theme_id"]] = float(persistence.get(row["theme_id"], 0.0)) + 1.0 + max(float(row["theme_score"]) - mainline_min_score, 0.0)
        for theme_id in list(persistence):
            if theme_id not in eligible_theme_ids:
                persistence[theme_id] = float(persistence[theme_id]) * mainline_decay
            if persistence[theme_id] < 0.25:
                persistence.pop(theme_id, None)

        current_theme = dominant_state.get("mainline_theme")
        confirmed = bool(dominant_state.get("confirmed", False))
        current_idx = next((idx for idx, row in enumerate(candidates) if row["theme_id"] == current_theme), None)
        current_row = candidates[current_idx] if current_idx is not None else None
        best_theme = max(persistence, key=persistence.get) if persistence else None
        best_score = float(persistence.get(best_theme, 0.0)) if best_theme else 0.0

        if not confirmed and best_theme and best_score >= mainline_confirm_score:
            current_theme = best_theme
            confirmed = True
            dominant_state["weak_count"] = 0
            current_idx = next((idx for idx, row in enumerate(candidates) if row["theme_id"] == current_theme), None)
            current_row = candidates[current_idx] if current_idx is not None else None

        if confirmed:
            current_persistence = float(persistence.get(current_theme, 0.0))
            if current_row is None or current_idx is None or current_idx + 1 > incumbent_exit_rank or current_persistence < mainline_confirm_score * 0.35:
                dominant_state["weak_count"] = int(dominant_state.get("weak_count", 0)) + 1
            else:
                dominant_state["weak_count"] = 0
            if int(dominant_state.get("weak_count", 0)) >= mainline_exit_months:
                confirmed = False
                current_theme = None
                current_row = None
                dominant_state["weak_count"] = 0

        dominant_state["persistence"] = persistence
        dominant_state["mainline_theme"] = current_theme
        dominant_state["confirmed"] = confirmed
        if confirmed and current_row is not None:
            chosen = [current_row]
        else:
            chosen = candidates[:top_n]
    else:
        chosen = candidates[:top_n]
    if not chosen:
        return defensive_weights(monthly, date), rows
    chosen_ids = {row["theme_id"] for row in chosen}
    for row in rows:
        row["selected"] = row["theme_id"] in chosen_ids
    effective_risk = risk_weight
    if vol_target is not None:
        vols = [realized_vol(monthly, date, row["selected_proxy"]) for row in chosen]
        vols = [vol for vol in vols if vol is not None and np.isfinite(vol)]
        if vols:
            avg_vol = float(np.mean(vols))
            if avg_vol > 0:
                effective_risk = min(effective_risk, max(0.35, vol_target / avg_vol))
    sleeves: list[str] = []
    for row in chosen:
        if expression == "stocks":
            stocks = rank_stock_candidates(
                monthly,
                date,
                row["theme_id"],
                stock_top_n,
                pit_universe=pit_universe,
                pit_theme_map=pit_theme_map,
            )
            sleeves.extend(stocks if stocks else [row["selected_proxy"]])
        else:
            sleeves.append(row["selected_proxy"])
    sleeves = list(dict.fromkeys(sleeves))
    if not sleeves:
        return defensive_weights(monthly, date), rows
    weights = {ticker: effective_risk / len(sleeves) for ticker in sleeves}
    if effective_risk < 1.0:
        weights["US.BIL"] = 1.0 - effective_risk
    return weights, rows


def month_end_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    grouped = pd.Series(index=index, dtype=float).groupby(index.to_period("M")).apply(lambda _: _.index.max())
    return [pd.Timestamp(value) for value in grouped.tolist()]


def run_strategy(
    prices: pd.DataFrame,
    top_n: int,
    min_theme_score: float,
    risk_weight: float,
    *,
    use_cooldown: bool = False,
    vol_target: float | None = None,
    dd_brake: bool = False,
    expression: str = "etf",
    stock_top_n: int = 2,
    pit_manifest: str | Path | None = None,
    pit_theme_map: dict[str, list[str]] | None = None,
    selection_mode: str = "multi_theme",
    dominant_margin: float = 0.08,
    challenger_confirm_months: int = 2,
    incumbent_exit_rank: int = 3,
    mainline_confirm_months: int = 4,
    mainline_exit_months: int = 2,
    mainline_min_score: float = 0.18,
    mainline_rank_limit: int = 2,
    mainline_confirm_score: float = 4.0,
    mainline_decay: float = 0.65,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    monthly_dates = [dt for dt in month_end_dates(prices.index) if dt in prices.index]
    monthly = prices.loc[monthly_dates].dropna(how="all")
    returns = prices.pct_change().fillna(0.0)
    rebalance_dates = set(monthly.index)
    monthly_rows: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    decisions = []
    preview_weights_by_date: dict[pd.Timestamp, dict[str, float]] = {}
    pit_universe = load_pit_universe(pit_manifest)
    dominant_state: dict[str, Any] = {}
    for dt in monthly.index:
        if monthly.index.get_loc(dt) < 12:
            weights = {"CASH": 1.0}
            rows = []
        else:
            weights, rows = pick_weights(
                monthly,
                pd.Timestamp(dt),
                top_n,
                min_theme_score,
                risk_weight,
                use_cooldown=use_cooldown,
                vol_target=vol_target,
                expression=expression,
                stock_top_n=stock_top_n,
                pit_universe=pit_universe,
                pit_theme_map=pit_theme_map,
                selection_mode=selection_mode,
                dominant_state=dominant_state,
                dominant_margin=dominant_margin,
                challenger_confirm_months=challenger_confirm_months,
                incumbent_exit_rank=incumbent_exit_rank,
                mainline_confirm_months=mainline_confirm_months,
                mainline_exit_months=mainline_exit_months,
                mainline_min_score=mainline_min_score,
                mainline_rank_limit=mainline_rank_limit,
                mainline_confirm_score=mainline_confirm_score,
                mainline_decay=mainline_decay,
            )
        preview_weights_by_date[pd.Timestamp(dt)] = weights
        monthly_rows[pd.Timestamp(dt)] = rows

    equity = INITIAL_CAPITAL
    peak = equity
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
        peak = max(peak, equity)
        dd = equity / peak - 1.0

        if dt in rebalance_dates:
            weights = dict(preview_weights_by_date.get(dt, {"CASH": 1.0}))
            if dd_brake:
                if dd <= -0.25:
                    weights = defensive_weights(monthly, pd.Timestamp(dt))
                elif dd <= -0.15:
                    risky = sum(weight for ticker, weight in weights.items() if ticker != "CASH")
                    if risky > 0:
                        scale = 0.50
                        weights = {ticker: weight * scale for ticker, weight in weights.items() if ticker != "CASH"}
                        weights["US.BIL"] = weights.get("US.BIL", 0.0) + (1.0 - sum(weights.values()))
            new_weights = weights
            turnover = sum(abs(new_weights.get(k, 0.0) - current_weights.get(k, 0.0)) for k in set(new_weights) | set(current_weights) if k != "CASH")
            equity -= equity * turnover * TX_COST_BPS / 10_000.0
            current_weights = dict(new_weights)
            rows = monthly_rows.get(pd.Timestamp(dt), [])
            decisions.append(
                {
                    "date": str(pd.Timestamp(dt).date()),
                    "weights": current_weights,
                    "drawdown": round(float(dd), 6),
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


def write_report(
    result_rows: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    path: Path,
    start: str,
    end: str,
) -> None:
    ranked = sorted(result_rows, key=lambda row: (row["stats"]["sharpe"], row["stats"]["ann_ret"]), reverse=True)
    lines = [
        "# V6-B Dynamic Theme Rotation Backtest",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Window: `{start}` to `{end}`",
        "- Scope: dynamic ETF theme discovery, then either ETF expression or theme-to-stock expression.",
        "- Design intent: confirm the main uptrend later but avoid staying trapped in an expired theme.",
        "",
        "## Benchmarks",
        "",
        "| ticker | ann | maxDD | Sharpe | final |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in benchmark_rows:
        s = row["stats"]
        lines.append(
            f"| `{row['ticker']}` | {fmt_pct(s.get('ann_ret'))} | {fmt_pct(s.get('max_dd'))} | "
            f"{s.get('sharpe', 0):.2f} | ${s.get('final', 0):,.0f} |"
        )
    lines.extend(
        [
        "",
        "## Strategy Grid",
        "",
        "| rank | config | ann | maxDD | Sharpe | 2020 | 2022 | 2024-2025 | final |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
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

    tickers = sorted(
        set(
            BENCHMARKS
            + DEFENSIVE
            + [proxy for theme in THEMES.values() for proxy in theme["proxies"]]
            + [stock for theme in THEMES.values() for stock in theme.get("stocks", [])]
        )
    )
    prices = build_price_matrix(tickers, args.start, args.end)
    required = [ticker for ticker in tickers if ticker in prices.columns]
    prices = prices[required].dropna(axis=1, how="all").ffill(limit=3).dropna(subset=["US.SPY", "US.QQQ", "US.BIL"])

    configs: list[dict[str, Any]] = []
    for top_n in [1, 2, 3]:
        for min_score in [0.02, 0.05, 0.08]:
            for risk_weight in [0.75, 0.90, 1.0]:
                for expression in ["etf", "stocks"]:
                    configs.append(
                        {
                            "top_n": top_n,
                            "min_score": min_score,
                            "risk_weight": risk_weight,
                            "use_cooldown": False,
                            "vol_target": None,
                            "dd_brake": False,
                            "expression": expression,
                            "stock_top_n": 2,
                            "version": "v0",
                        }
                    )
                    configs.append(
                        {
                            "top_n": top_n,
                            "min_score": min_score,
                            "risk_weight": risk_weight,
                            "use_cooldown": True,
                            "vol_target": 0.22,
                            "dd_brake": True,
                            "expression": expression,
                            "stock_top_n": 2,
                            "version": "v1_guarded",
                        }
                    )

    rows = []
    benchmark_rows = []
    for ticker in BENCHMARKS:
        if ticker not in prices.columns:
            continue
        series = prices[ticker].dropna()
        if len(series) < 20:
            continue
        eq = series / float(series.iloc[0]) * INITIAL_CAPITAL
        benchmark_rows.append({"ticker": ticker, "stats": stats(eq)})

    best_decisions: list[dict[str, Any]] = []
    best_score = -1e9
    for config in configs:
        eq, decisions = run_strategy(
            prices,
            top_n=int(config["top_n"]),
            min_theme_score=float(config["min_score"]),
            risk_weight=float(config["risk_weight"]),
            use_cooldown=bool(config["use_cooldown"]),
            vol_target=config["vol_target"],
            dd_brake=bool(config["dd_brake"]),
            expression=str(config["expression"]),
            stock_top_n=int(config["stock_top_n"]),
        )
        s = stats(eq)
        if not s:
            continue
        periods = {
            "2020": period_stats(eq, "2020-01-01", "2020-12-31"),
            "2022": period_stats(eq, "2022-01-01", "2022-12-31"),
            "2024_2025": period_stats(eq, "2024-01-01", "2025-12-31"),
        }
        label = (
            f"{config['version']}_top{config['top_n']}_min{config['min_score']:.2f}_"
            f"risk{config['risk_weight']:.0%}_{config['expression']}"
        )
        row = {"config": label, **config, "stats": s, "periods": periods}
        rows.append(row)
        score = s["sharpe"] + max(s["max_dd"], -0.40) + s["ann_ret"] * 0.25
        if score > best_score:
            best_score = score
            best_decisions = decisions

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"v6b_theme_rotation_{args.tag}.json"
    md_path = OUT_DIR / f"v6b_theme_rotation_{args.tag}.md"
    serializable = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start": args.start,
        "end": args.end,
        "benchmarks": benchmark_rows,
        "rows": rows,
        "best_recent_decisions": best_decisions[-24:],
    }
    json_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    write_report(rows, best_decisions, benchmark_rows, md_path, args.start, args.end)
    print(f"JSON: {json_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
