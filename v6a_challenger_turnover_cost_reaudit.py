#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from v6b_profile_parameter_search import build_baseline_params
from v6b_synthetic_historical import DEFENSIVE, REGIME_TICKERS, V6A_POOL, build_price_matrix, load_json
from v6b_synthetic_historical_challenger import INITIAL_CAPITAL, RISK_FREE, TRADING_DAYS, calc_metrics


ROOT = Path(__file__).resolve().parent
DEFAULT_RESULTS_CSV = ROOT / "backtest_results" / "v6a_parameter_challenger" / "v6a_parameter_challenger_20260513_v1.csv"
DEFAULT_BASELINE_POLICY = ROOT / "v6_strategy_lab" / "configs" / "v6_engine_profile_selector_v1.json"
OUT_DIR = ROOT / "backtest_results" / "v6a_challenger_turnover_cost_reaudit"
COST_BPS_LEVELS = [0, 5, 10, 25, 50, 100]
ACCOUNT_NOTIONALS = [5_000, 25_000, 50_000, 100_000]


def one_way_turnover(old_weights: dict[str, float], new_weights: dict[str, float]) -> float:
    keys = set(old_weights) | set(new_weights)
    return 0.5 * sum(abs(old_weights.get(key, 0.0) - new_weights.get(key, 0.0)) for key in keys)


def pick_v6a_weights(sub: pd.DataFrame, dt: pd.Timestamp, params: dict[str, Any], stopped: bool, trend: pd.Series, slow: pd.Series) -> tuple[dict[str, float], bool, list[str]]:
    qqq_ok = pd.notna(trend.loc[dt]) and sub.loc[dt, "US.QQQ"] > trend.loc[dt]
    spy_ok = pd.notna(slow.loc[dt]) and sub.loc[dt, "US.SPY"] > slow.loc[dt]
    risk_on = (not stopped) and qqq_ok and spy_ok
    if not risk_on:
        return dict(DEFENSIVE), False, []

    scores: dict[str, float] = {}
    for ticker in V6A_POOL:
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
    if not chosen:
        return dict(DEFENSIVE), False, []
    weight = 1.0 / len(chosen)
    return {ticker: weight for ticker in chosen}, True, chosen


def simulate_trace(prices: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    needed = REGIME_TICKERS + [ticker for ticker in DEFENSIVE if ticker != "CASH"]
    sub = prices.copy().dropna(subset=needed)
    if len(sub) < 200:
        raise RuntimeError("insufficient price coverage for simulation")

    rets = sub.pct_change().fillna(0.0)
    qqq = sub["US.QQQ"]
    spy = sub["US.SPY"]
    trend = qqq.rolling(params["trend_ma"]).mean()
    slow = spy.rolling(params["market_ma"]).mean()

    equity = INITIAL_CAPITAL
    peak = equity
    stopped = False
    current_weights = {"CASH": 1.0}
    curve: list[float] = []
    daily_rows: list[dict[str, Any]] = []
    rebalance_rows: list[dict[str, Any]] = []

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

        turnover = 0.0
        chosen: list[str] = []
        risk_on = False
        if idx % params["rebal"] == 0:
            target_weights, risk_on, chosen = pick_v6a_weights(sub, dt, params, stopped, trend, slow)
            turnover = one_way_turnover(current_weights, target_weights)
            current_weights = target_weights
            if turnover > 0:
                rebalance_rows.append(
                    {
                        "date": dt,
                        "turnover": turnover,
                        "risk_on": risk_on,
                        "chosen": ",".join(chosen) if chosen else "DEFENSIVE",
                        "equity": equity,
                    }
                )

        curve.append(equity)
        daily_rows.append(
            {
                "date": dt,
                "daily_return": day_ret,
                "turnover": turnover,
                "equity_0bps": equity,
                "drawdown_0bps": dd,
                "stopped": stopped,
                "holdings": ",".join(sorted(key for key in current_weights if key != "CASH")) or "CASH",
            }
        )

    eq = pd.Series(curve, index=sub.index)
    return pd.DataFrame(daily_rows), pd.DataFrame(rebalance_rows), calc_metrics(eq)


def annualized_turnover(daily_df: pd.DataFrame, start: str | None = None) -> float:
    subset = daily_df.copy()
    if start:
        subset = subset[subset["date"] >= pd.Timestamp(start)]
    if subset.empty:
        return 0.0
    years = (subset["date"].max() - subset["date"].min()).days / 365.25
    if years <= 0:
        return 0.0
    return float(subset["turnover"].sum() / years)


def rebalances_per_year(rebalance_df: pd.DataFrame, daily_df: pd.DataFrame) -> float:
    if daily_df.empty:
        return 0.0
    years = (daily_df["date"].max() - daily_df["date"].min()).days / 365.25
    if years <= 0:
        return 0.0
    return float(len(rebalance_df) / years)


def average_turnover(rebalance_df: pd.DataFrame) -> float:
    if rebalance_df.empty:
        return 0.0
    return float(rebalance_df["turnover"].mean())


def max_turnover(rebalance_df: pd.DataFrame) -> float:
    if rebalance_df.empty:
        return 0.0
    return float(rebalance_df["turnover"].max())


def cost_ladder(daily_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    base = daily_df.sort_values("date").copy()
    for bps in COST_BPS_LEVELS:
        adjusted_returns = base["daily_return"] - base["turnover"] * bps / 10_000.0
        eq = (1.0 + adjusted_returns).cumprod() * INITIAL_CAPITAL
        eq.index = pd.to_datetime(base["date"])
        metrics = calc_metrics(eq)
        rows.append(
            {
                "cost_bps": bps,
                "ann_ret": float(metrics["ann_ret"]),
                "max_dd": float(metrics["max_dd"]),
                "sharpe": float(metrics["sharpe"]),
                "oos_ann": float(metrics["oos_ann"]),
                "oos_sharpe": float(metrics["oos_sharpe"]),
            }
        )
    return rows


def rows_to_map(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(row["cost_bps"]): row for row in rows}


def load_candidate_params(results_csv: Path, label: str) -> dict[str, Any]:
    df = pd.read_csv(results_csv)
    row = df[df["label"] == label]
    if row.empty:
        raise RuntimeError(f"candidate label not found: {label}")
    picked = row.iloc[0]
    return {
        "top_n": int(picked["top_n"]),
        "mom_days": int(picked["mom_days"]),
        "trend_ma": int(picked["trend_ma"]),
        "market_ma": int(picked["market_ma"]),
        "dd_stop": float(picked["dd_stop"]),
        "rebal": int(picked["rebal"]),
        "label": str(picked["label"]),
    }


def build_summary_row(label: str, metrics: dict[str, Any], ladder_map: dict[int, dict[str, Any]], daily_df: pd.DataFrame, rebalance_df: pd.DataFrame) -> dict[str, Any]:
    row_25 = ladder_map[25]
    return {
        "label": label,
        "full_ann_0": float(metrics["ann_ret"]),
        "full_dd_0": float(metrics["max_dd"]),
        "sharpe_0": float(metrics["sharpe"]),
        "oos_ann_0": float(metrics["oos_ann"]),
        "oos_sharpe_0": float(metrics["oos_sharpe"]),
        "full_ann_25": float(row_25["ann_ret"]),
        "full_dd_25": float(row_25["max_dd"]),
        "sharpe_25": float(row_25["sharpe"]),
        "oos_ann_25": float(row_25["oos_ann"]),
        "oos_sharpe_25": float(row_25["oos_sharpe"]),
        "annual_turnover_full": annualized_turnover(daily_df),
        "annual_turnover_oos": annualized_turnover(daily_df, start="2024-01-01"),
        "rebalances_per_year": rebalances_per_year(rebalance_df, daily_df),
        "avg_turnover_per_rebalance": average_turnover(rebalance_df),
        "max_turnover_per_rebalance": max_turnover(rebalance_df),
    }


def render_ladder_table(label: str, rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"### {label}",
        "",
        "| cost bps | ann | maxDD | sharpe | OOS ann | OOS sharpe |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['cost_bps']} | {row['ann_ret'] * 100:+.1f}% | {row['max_dd'] * 100:+.1f}% | {row['sharpe']:.2f} | {row['oos_ann'] * 100:+.1f}% | {row['oos_sharpe']:.2f} |"
        )
    return lines


def render_report(
    baseline_params: dict[str, Any],
    candidate_params: dict[str, Any],
    baseline_summary: dict[str, Any],
    candidate_summary: dict[str, Any],
    baseline_ladder: list[dict[str, Any]],
    candidate_ladder: list[dict[str, Any]],
) -> str:
    baseline_25 = rows_to_map(baseline_ladder)[25]
    candidate_25 = rows_to_map(candidate_ladder)[25]
    verdict = pick_preliminary_verdict(baseline_summary, candidate_summary, baseline_25, candidate_25)

    lines = [
        "# V6-A Challenger Turnover / Cost Re-Audit",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        "- Objective: compare current production baseline with the preferred balanced V6-A challenger under the same turnover and cost assumptions.",
        "",
        "## Compared Profiles",
        "",
        f"- Baseline: `{baseline_params['label']}` = `mom{baseline_params['mom_days']} top{baseline_params['top_n']} trend{baseline_params['trend_ma']} mkt{baseline_params['market_ma']} dd{int(round(baseline_params['dd_stop'] * 100)):02d} rebal{baseline_params['rebal']}`",
        f"- Candidate: `{candidate_params['label']}` = `mom{candidate_params['mom_days']} top{candidate_params['top_n']} trend{candidate_params['trend_ma']} mkt{candidate_params['market_ma']} dd{int(round(candidate_params['dd_stop'] * 100)):02d} rebal{candidate_params['rebal']}`",
        "",
        "## Comparison Summary",
        "",
        "| profile | full ann 0bps | full maxDD 0bps | sharpe 0bps | full ann 25bps | OOS sharpe 25bps | annual turnover | rebalances/year | avg turnover/rebalance | max turnover/rebalance |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| baseline | {baseline_summary['full_ann_0'] * 100:+.1f}% | {baseline_summary['full_dd_0'] * 100:+.1f}% | {baseline_summary['sharpe_0']:.2f} | "
            f"{baseline_summary['full_ann_25'] * 100:+.1f}% | {baseline_summary['oos_sharpe_25']:.2f} | {baseline_summary['annual_turnover_full']:.2f} | "
            f"{baseline_summary['rebalances_per_year']:.1f} | {baseline_summary['avg_turnover_per_rebalance']:.3f} | {baseline_summary['max_turnover_per_rebalance']:.3f} |"
        ),
        (
            f"| candidate | {candidate_summary['full_ann_0'] * 100:+.1f}% | {candidate_summary['full_dd_0'] * 100:+.1f}% | {candidate_summary['sharpe_0']:.2f} | "
            f"{candidate_summary['full_ann_25'] * 100:+.1f}% | {candidate_summary['oos_sharpe_25']:.2f} | {candidate_summary['annual_turnover_full']:.2f} | "
            f"{candidate_summary['rebalances_per_year']:.1f} | {candidate_summary['avg_turnover_per_rebalance']:.3f} | {candidate_summary['max_turnover_per_rebalance']:.3f} |"
        ),
        "",
        "## 25 bps Read",
        "",
        f"- Baseline @25bps: `Ann {baseline_25['ann_ret'] * 100:+.1f}% / MaxDD {baseline_25['max_dd'] * 100:+.1f}% / OOS Sharpe {baseline_25['oos_sharpe']:.2f}`",
        f"- Candidate @25bps: `Ann {candidate_25['ann_ret'] * 100:+.1f}% / MaxDD {candidate_25['max_dd'] * 100:+.1f}% / OOS Sharpe {candidate_25['oos_sharpe']:.2f}`",
        "",
        f"- Preliminary verdict: `{verdict}`",
        "",
    ]
    if verdict == "candidate_survives_costs":
        lines.extend(
            [
                "The balanced challenger still looks better after cost assumptions.",
                "",
                "- It retains higher return.",
                "- It retains better or comparable OOS Sharpe.",
                "- Its slower rebalance cadence does not create a turnover penalty that kills the edge.",
                "",
            ]
        )
    elif verdict == "candidate_turnover_too_high":
        lines.extend(
            [
                "The challenger may still have raw performance, but turnover is too aggressive relative to the baseline.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "The challenger loses too much advantage once costs are applied.",
                "",
            ]
        )
    lines.extend(
        [
            "## Cost Ladders",
            "",
            *render_ladder_table("Baseline", baseline_ladder),
            "",
            *render_ladder_table("Balanced Challenger", candidate_ladder),
            "",
            "## Small-Account Notional Reference",
            "",
            "| account | baseline avg rebalance | candidate avg rebalance | baseline worst rebalance | candidate worst rebalance |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for notional in ACCOUNT_NOTIONALS:
        lines.append(
            f"| ${notional:,.0f} | ${baseline_summary['avg_turnover_per_rebalance'] * notional:,.0f} | "
            f"${candidate_summary['avg_turnover_per_rebalance'] * notional:,.0f} | "
            f"${baseline_summary['max_turnover_per_rebalance'] * notional:,.0f} | ${candidate_summary['max_turnover_per_rebalance'] * notional:,.0f} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This is still a synthetic price-only engine read, not live execution proof.",
            "- It is good enough to decide whether the balanced challenger deserves a formal side-by-side board.",
        ]
    )
    return "\n".join(lines) + "\n"


def pick_preliminary_verdict(
    baseline_summary: dict[str, Any],
    candidate_summary: dict[str, Any],
    baseline_25: dict[str, Any],
    candidate_25: dict[str, Any],
) -> str:
    verdict = "candidate_survives_costs"
    if candidate_25["oos_sharpe"] < baseline_25["oos_sharpe"] or candidate_25["ann_ret"] < baseline_25["ann_ret"]:
        verdict = "candidate_needs_more_caution"
    if candidate_summary["annual_turnover_full"] > baseline_summary["annual_turnover_full"] * 1.5:
        verdict = "candidate_turnover_too_high"
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-audit turnover and cost for a V6-A challenger candidate versus the current baseline.")
    parser.add_argument("--results-csv", default=str(DEFAULT_RESULTS_CSV))
    parser.add_argument("--baseline-policy", default=str(DEFAULT_BASELINE_POLICY))
    parser.add_argument("--candidate-label", default="mom60 top3 trend150 mkt200 dd10 rebal10")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    baseline_policy = load_json(Path(args.baseline_policy))
    baseline_params = build_baseline_params(baseline_policy)
    candidate_params = load_candidate_params(Path(args.results_csv), args.candidate_label)

    tickers = sorted(set(REGIME_TICKERS + [ticker for ticker in DEFENSIVE if ticker != "CASH"] + V6A_POOL))
    prices = build_price_matrix(tickers, args.start, args.end)

    baseline_daily, baseline_reb, baseline_metrics = simulate_trace(prices, baseline_params)
    candidate_daily, candidate_reb, candidate_metrics = simulate_trace(prices, candidate_params)
    baseline_ladder = cost_ladder(baseline_daily)
    candidate_ladder = cost_ladder(candidate_daily)

    baseline_summary = build_summary_row("baseline", baseline_metrics, rows_to_map(baseline_ladder), baseline_daily, baseline_reb)
    candidate_summary = build_summary_row("candidate", candidate_metrics, rows_to_map(candidate_ladder), candidate_daily, candidate_reb)
    baseline_25 = rows_to_map(baseline_ladder)[25]
    candidate_25 = rows_to_map(candidate_ladder)[25]
    preliminary_verdict = pick_preliminary_verdict(baseline_summary, candidate_summary, baseline_25, candidate_25)

    report = render_report(
        baseline_params=baseline_params,
        candidate_params=candidate_params,
        baseline_summary=baseline_summary,
        candidate_summary=candidate_summary,
        baseline_ladder=baseline_ladder,
        candidate_ladder=candidate_ladder,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"v6a_challenger_turnover_cost_reaudit_{args.tag}.json"
    md_path = OUT_DIR / f"v6a_challenger_turnover_cost_reaudit_{args.tag}.md"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline_params": baseline_params,
        "candidate_params": candidate_params,
        "baseline_summary": baseline_summary,
        "candidate_summary": candidate_summary,
        "baseline_cost_ladder": baseline_ladder,
        "candidate_cost_ladder": candidate_ladder,
        "preliminary_verdict": preliminary_verdict,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report, encoding="utf-8")
    print(f"JSON:   {json_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
