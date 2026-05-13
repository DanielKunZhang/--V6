#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import alpha_cash_enhancement_search as alpha
import attack_engine_search as atk
from v6b_profile_parameter_search import build_baseline_params
from v6b_synthetic_historical import DEFENSIVE, REGIME_TICKERS, V6A_POOL, build_price_matrix, load_json


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "v6_strategy_lab" / "configs" / "v6a_core_replay_bridge_v1.json"
DEFAULT_BASELINE_POLICY = ROOT / "v6_strategy_lab" / "configs" / "v6_engine_profile_selector_v1.json"
OUT_DIR = ROOT / "backtest_results" / "v6a_core_replay"


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    label: str
    params: dict[str, Any]
    source: str


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def fmt_pct(value: Any) -> str:
    number = as_float(value)
    if math.isnan(number):
        return ""
    return f"{number:.2f}%"


def clean_weights(weights: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value), 8) for key, value in weights.items() if abs(float(value)) > 1e-10}


def one_way_turnover(old_weights: dict[str, float], new_weights: dict[str, float]) -> float:
    keys = set(old_weights) | set(new_weights)
    return 0.5 * sum(abs(old_weights.get(key, 0.0) - new_weights.get(key, 0.0)) for key in keys)


def ensure_cash(weights: dict[str, float]) -> dict[str, float]:
    out = {key: float(value) for key, value in weights.items() if abs(float(value)) > 1e-12}
    if "CASH" not in out:
        out["CASH"] = max(0.0, 1.0 - sum(value for key, value in out.items() if key != "CASH"))
    return out


def load_candidates(config: dict[str, Any], baseline_policy_path: Path) -> list[Candidate]:
    baseline_policy = load_json(baseline_policy_path)
    baseline_params = build_baseline_params(baseline_policy)
    out: list[Candidate] = []
    for row in config.get("candidates", []):
        source = str(row.get("source", "explicit"))
        if source == "baseline_policy":
            params = dict(baseline_params)
        else:
            params = {
                "top_n": int(row["params"]["top_n"]),
                "mom_days": int(row["params"]["mom_days"]),
                "trend_ma": int(row["params"]["trend_ma"]),
                "market_ma": int(row["params"]["market_ma"]),
                "dd_stop": float(row["params"]["dd_stop"]),
                "rebal": int(row["params"]["rebal"]),
                "label": str(row.get("label") or row["candidate_id"]),
            }
        if "label" in row:
            params["label"] = str(row["label"])
        out.append(
            Candidate(
                candidate_id=str(row["candidate_id"]),
                label=str(params["label"]),
                params=params,
                source=source,
            )
        )
    return out


def rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def pick_target_weights(
    prices: pd.DataFrame,
    dt: pd.Timestamp,
    params: dict[str, Any],
    stopped: bool,
    trend: pd.Series,
    slow: pd.Series,
) -> tuple[dict[str, float], bool, list[str], str]:
    qqq_ok = pd.notna(trend.loc[dt]) and prices.loc[dt, "US.QQQ"] > trend.loc[dt]
    spy_ok = pd.notna(slow.loc[dt]) and prices.loc[dt, "US.SPY"] > slow.loc[dt]
    risk_on = (not stopped) and qqq_ok and spy_ok
    if not risk_on:
        return ensure_cash(dict(DEFENSIVE)), False, [], "defensive"

    scores: dict[str, float] = {}
    for ticker in V6A_POOL:
        if ticker not in prices.columns:
            continue
        hist = prices.loc[:dt, ticker].dropna()
        if len(hist) <= params["mom_days"]:
            continue
        base = float(hist.iloc[-params["mom_days"] - 1])
        if base <= 0:
            continue
        scores[ticker] = float(hist.iloc[-1] / base - 1.0)

    ranked = sorted(scores, key=scores.get, reverse=True)
    chosen = [ticker for ticker in ranked if scores[ticker] > 0][: params["top_n"]]
    if not chosen:
        return ensure_cash(dict(DEFENSIVE)), False, [], "risk_on_no_positive_momentum"

    weight = 1.0 / len(chosen)
    target = {ticker: weight for ticker in chosen}
    return ensure_cash(target), True, chosen, "risk_on"


def simulate_candidate(prices: pd.DataFrame, candidate: Candidate) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    params = candidate.params
    needed = REGIME_TICKERS + [ticker for ticker in DEFENSIVE if ticker != "CASH"] + V6A_POOL
    sub = prices.copy().dropna(subset=needed)
    if len(sub) < 260:
        raise RuntimeError(f"insufficient price coverage for {candidate.candidate_id}")

    rets = sub.pct_change().fillna(0.0)
    qqq = sub["US.QQQ"]
    spy = sub["US.SPY"]
    trend = qqq.rolling(params["trend_ma"]).mean()
    slow = spy.rolling(params["market_ma"]).mean()

    equity = float(alpha.INITIAL_CAPITAL)
    peak = equity
    stopped = False
    current_weights = {"CASH": 1.0}
    curve: list[float] = []
    daily_rows: list[dict[str, Any]] = []
    rebalance_rows: list[dict[str, Any]] = []

    for idx, dt in enumerate(sub.index):
        start_equity = equity
        day_ret = current_weights.get("CASH", 0.0) * (alpha.RISK_FREE / alpha.TRADING_DAYS)
        for ticker, weight in current_weights.items():
            if ticker == "CASH":
                continue
            if ticker in rets.columns and pd.notna(rets.loc[dt, ticker]):
                day_ret += weight * float(rets.loc[dt, ticker])
        equity = max(equity * (1.0 + day_ret), 0.0)

        peak = max(peak, equity)
        dd = equity / peak - 1.0 if peak > 0 else 0.0
        if dd <= -params["dd_stop"]:
            stopped = True
        if stopped and pd.notna(trend.loc[dt]) and qqq.loc[dt] > trend.loc[dt]:
            stopped = False
            peak = equity

        rebalanced = False
        turnover = 0.0
        chosen: list[str] = []
        risk_on = False
        rebalance_reason = "hold"

        if idx % params["rebal"] == 0:
            new_weights, risk_on, chosen, rebalance_reason = pick_target_weights(sub, dt, params, stopped, trend, slow)
            turnover = one_way_turnover(current_weights, new_weights)
            current_weights = new_weights
            rebalanced = True
            rebalance_rows.append(
                {
                    "date": dt.date().isoformat(),
                    "candidate_id": candidate.candidate_id,
                    "candidate_label": candidate.label,
                    "reason": rebalance_reason,
                    "risk_on": bool(risk_on),
                    "stopped": bool(stopped),
                    "chosen": "|".join(chosen) if chosen else "DEFENSIVE",
                    "turnover": round(float(turnover), 6),
                    "equity": round(float(equity), 2),
                    "drawdown": round(float(dd), 6),
                    "qqq_above_trend": bool(pd.notna(trend.loc[dt]) and qqq.loc[dt] > trend.loc[dt]),
                    "spy_above_slow": bool(pd.notna(slow.loc[dt]) and spy.loc[dt] > slow.loc[dt]),
                    "weights_json": json.dumps(clean_weights(current_weights), sort_keys=True),
                }
            )

        gross = sum(abs(weight) for ticker, weight in current_weights.items() if ticker != "CASH")
        net = sum(weight for ticker, weight in current_weights.items() if ticker != "CASH")
        qqq_ok = bool(pd.notna(trend.loc[dt]) and qqq.loc[dt] > trend.loc[dt])
        spy_ok = bool(pd.notna(slow.loc[dt]) and spy.loc[dt] > slow.loc[dt])
        holdings = sorted(key for key, value in current_weights.items() if key != "CASH" and abs(value) > 1e-12)
        daily_rows.append(
            {
                "date": dt.date().isoformat(),
                "candidate_id": candidate.candidate_id,
                "candidate_label": candidate.label,
                "equity": round(float(equity), 2),
                "daily_return": round(float(equity / start_equity - 1.0), 8) if start_equity else 0.0,
                "drawdown": round(float(equity / peak - 1.0), 8) if peak else 0.0,
                "rebalanced": bool(rebalanced),
                "turnover": round(float(turnover), 6),
                "gross_exposure": round(float(gross), 6),
                "net_exposure": round(float(net), 6),
                "cash_weight": round(float(current_weights.get("CASH", 0.0)), 6),
                "stopped": bool(stopped),
                "qqq_above_trend": qqq_ok,
                "spy_above_slow": spy_ok,
                "risk_on_state": bool((not stopped) and qqq_ok and spy_ok),
                "holdings": "|".join(holdings) if holdings else "CASH",
                "weights_json": json.dumps(clean_weights(current_weights), sort_keys=True),
            }
        )
        curve.append(equity)

    daily = pd.DataFrame(daily_rows)
    rebalances = pd.DataFrame(rebalance_rows)
    eq = pd.Series(curve, index=pd.to_datetime(daily["date"])).sort_index()
    return eq, daily, rebalances


def max_consecutive_loss_days(daily_returns: pd.Series) -> int:
    best = 0
    current = 0
    for value in daily_returns:
        if value < 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def summarize_candidate(candidate: Candidate, eq: pd.Series, daily: pd.DataFrame, rebalances: pd.DataFrame) -> dict[str, Any]:
    metrics = atk.evaluate_equity(eq, include_rolling=True)
    if not metrics:
        raise RuntimeError(f"failed to compute metrics for {candidate.candidate_id}")

    dr = pd.to_numeric(daily["daily_return"], errors="coerce")
    gross = pd.to_numeric(daily["gross_exposure"], errors="coerce")
    turnover = pd.to_numeric(rebalances["turnover"], errors="coerce") if not rebalances.empty else pd.Series(dtype=float)
    worst_idx = dr.idxmin()
    risk_on_rebalances = rebalances[rebalances["risk_on"] == True] if not rebalances.empty else pd.DataFrame()
    unique_assets = sorted(
        {
            asset
            for chosen in risk_on_rebalances.get("chosen", pd.Series(dtype=str)).astype(str)
            for asset in chosen.split("|")
            if asset and asset != "DEFENSIVE"
        }
    )
    latest_row = daily.iloc[-1]
    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
    summary = {
        "candidate_id": candidate.candidate_id,
        "candidate_label": candidate.label,
        "profile_source": candidate.source,
        "description": (
            f"mom{candidate.params['mom_days']} top{candidate.params['top_n']} "
            f"trend{candidate.params['trend_ma']} mkt{candidate.params['market_ma']} "
            f"dd{int(round(candidate.params['dd_stop'] * 100)):02d} rebal{candidate.params['rebal']}"
        ),
        "daily_rows": int(len(daily)),
        "rebalance_count": int(len(rebalances)),
        "risk_on_rebalance_count": int(len(risk_on_rebalances)),
        "defensive_rebalance_count": int((rebalances.get("reason", pd.Series(dtype=str)).astype(str) == "defensive").sum()) if not rebalances.empty else 0,
        "unique_risk_assets": "|".join(unique_assets),
        "avg_turnover_on_rebalance": round(float(turnover.mean()), 4) if not turnover.empty else 0.0,
        "median_turnover_on_rebalance": round(float(turnover.median()), 4) if not turnover.empty else 0.0,
        "max_turnover_on_rebalance": round(float(turnover.max()), 4) if not turnover.empty else 0.0,
        "annualized_turnover_proxy": round(float(turnover.sum() / years), 2) if not turnover.empty else 0.0,
        "rebalances_per_year": round(float(len(rebalances) / years), 2) if years > 0 else 0.0,
        "avg_gross_exposure": round(float(gross.mean()), 4),
        "max_gross_exposure": round(float(gross.max()), 4),
        "leveraged_day_pct": round(float((gross > 1.0001).mean() * 100), 2),
        "cash_only_day_pct": round(float((gross < 0.0001).mean() * 100), 2),
        "worst_daily_return": round(float(dr.min() * 100), 2),
        "worst_daily_date": str(daily.loc[worst_idx, "date"]) if len(daily) else "",
        "best_daily_return": round(float(dr.max() * 100), 2),
        "max_consecutive_loss_days": max_consecutive_loss_days(dr),
        "latest_date": str(latest_row["date"]),
        "latest_equity": round(float(eq.iloc[-1]), 2) if not eq.empty else 0.0,
        "latest_holdings": str(latest_row["holdings"]),
        "latest_weights_json": str(latest_row["weights_json"]),
        **metrics,
    }
    return summary


def composite_from_daily(all_daily: pd.DataFrame) -> tuple[pd.Series, dict[str, Any]]:
    wide = all_daily.pivot(index="date", columns="candidate_id", values="equity").sort_index()
    wide.index = pd.to_datetime(wide.index)
    returns = wide.pct_change().dropna()
    equal = (1.0 + returns.mean(axis=1)).cumprod() * alpha.INITIAL_CAPITAL
    metrics = atk.evaluate_equity(equal, include_rolling=True)
    latest_weights = {}
    if not all_daily.empty:
        latest_rows = all_daily.sort_values("date").groupby("candidate_id", sort=False).tail(1)
        for weights_json in latest_rows["weights_json"]:
            weights = json.loads(weights_json)
            for ticker, weight in weights.items():
                latest_weights[ticker] = latest_weights.get(ticker, 0.0) + float(weight) / len(latest_rows)
    row = {
        "candidate_id": "V6A_CORE_EQUAL_DIAG",
        "candidate_label": "equal_diag",
        "profile_source": "diagnostic_only",
        "description": "Equal-weight diagnostic composite across replay bridge candidates.",
        "latest_date": str(all_daily["date"].max()),
        "latest_weights_json": json.dumps(clean_weights(latest_weights), sort_keys=True),
        **metrics,
    }
    return equal, row


def write_report(path: Path, config_path: Path, summary: pd.DataFrame, composite: dict[str, Any]) -> None:
    lines = [
        "# V6-A Core Deterministic Replay Bridge",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Config: `{config_path}`",
        "- Purpose: bridge the V6-A core baseline/challenger research lane into runner-compatible replay artifacts without touching the live ATTACK pilot.",
        "",
        "## Candidates",
        "",
        "| candidate | source | full ann | full maxDD | full sharpe | OOS ann | OOS sharpe | ann turnover | rebalances/yr | latest holdings |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["candidate_id"]),
                    str(row["profile_source"]),
                    fmt_pct(row.get("full_ann_ret")),
                    fmt_pct(row.get("full_max_dd")),
                    f"{as_float(row.get('full_sharpe')):.2f}",
                    fmt_pct(row.get("oos_ann_ret")),
                    f"{as_float(row.get('oos_sharpe')):.2f}",
                    f"{as_float(row.get('annualized_turnover_proxy')):.2f}x",
                    f"{as_float(row.get('rebalances_per_year')):.2f}",
                    str(row.get("latest_holdings", "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Diagnostic Composite",
            "",
            "| candidate | full ann | full maxDD | full sharpe | OOS ann | OOS sharpe | latest weights |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
            "| "
            + " | ".join(
                [
                    str(composite["candidate_id"]),
                    fmt_pct(composite.get("full_ann_ret")),
                    fmt_pct(composite.get("full_max_dd")),
                    f"{as_float(composite.get('full_sharpe')):.2f}",
                    fmt_pct(composite.get("oos_ann_ret")),
                    f"{as_float(composite.get('oos_sharpe')):.2f}",
                    str(composite.get("latest_weights_json", "")),
                ]
            )
            + " |",
            "",
            "## Interpretation",
            "",
            "- This bridge does not alter the current live ATTACK pilot. It creates a parallel, auditable production-path artifact set for the V6-A core engine lane.",
            "- Each candidate also emits single-candidate daily/summary/composite files so a future guarded runner policy can point at one profile without averaging multiple sleeves together.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_single_candidate_artifacts(tag: str, daily: pd.DataFrame, rebalances: pd.DataFrame, summary_row: dict[str, Any]) -> dict[str, str]:
    candidate_id = str(summary_row["candidate_id"])
    safe_id = candidate_id.lower()
    single_daily = OUT_DIR / f"v6a_core_replay_daily_{tag}_{safe_id}.csv"
    single_rebalances = OUT_DIR / f"v6a_core_replay_rebalances_{tag}_{safe_id}.csv"
    single_summary = OUT_DIR / f"v6a_core_replay_summary_{tag}_{safe_id}.csv"
    single_composite = OUT_DIR / f"v6a_core_replay_composite_{tag}_{safe_id}.csv"
    single_report = OUT_DIR / f"v6a_core_replay_report_{tag}_{safe_id}.md"
    daily.to_csv(single_daily, index=False)
    rebalances.to_csv(single_rebalances, index=False)
    pd.DataFrame([summary_row]).to_csv(single_summary, index=False)
    pd.DataFrame([summary_row]).to_csv(single_composite, index=False)
    single_report.write_text(
        "\n".join(
            [
                f"# {candidate_id}",
                "",
                f"- Candidate label: `{summary_row['candidate_label']}`",
                f"- Description: `{summary_row['description']}`",
                f"- Latest date: `{summary_row['latest_date']}`",
                f"- Latest holdings: `{summary_row['latest_holdings']}`",
                f"- Latest weights: `{summary_row['latest_weights_json']}`",
                "",
                "This file set is runner-compatible in shape but still research-only until governance explicitly promotes it.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "daily": str(single_daily.relative_to(ROOT)),
        "rebalances": str(single_rebalances.relative_to(ROOT)),
        "summary": str(single_summary.relative_to(ROOT)),
        "composite": str(single_composite.relative_to(ROOT)),
        "report": str(single_report.relative_to(ROOT)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic replay bridge for V6-A core baseline/challenger profiles.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--baseline-policy", default=str(DEFAULT_BASELINE_POLICY))
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    candidates = load_candidates(config, Path(args.baseline_policy).resolve())
    sample = config["sample"]
    prices = build_price_matrix(sorted(set(REGIME_TICKERS + [ticker for ticker in DEFENSIVE if ticker != "CASH"] + V6A_POOL)), sample["start"], sample["end"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_daily = []
    all_rebalances = []
    summary_rows = []
    singles: dict[str, dict[str, str]] = {}

    for candidate in candidates:
        eq, daily, rebalances = simulate_candidate(prices, candidate)
        summary = summarize_candidate(candidate, eq, daily, rebalances)
        singles[candidate.candidate_id] = write_single_candidate_artifacts(args.tag, daily, rebalances, summary)
        all_daily.append(daily)
        all_rebalances.append(rebalances)
        summary_rows.append(summary)

    if not all_daily:
        raise SystemExit("No replay output generated.")

    daily_df = pd.concat(all_daily, ignore_index=True)
    rebalance_df = pd.concat(all_rebalances, ignore_index=True) if all_rebalances else pd.DataFrame()
    summary_df = pd.DataFrame(summary_rows).sort_values(["full_sharpe", "full_ann_ret"], ascending=[False, False])
    _, composite_row = composite_from_daily(daily_df)

    daily_path = OUT_DIR / f"v6a_core_replay_daily_{args.tag}.csv"
    rebalances_path = OUT_DIR / f"v6a_core_replay_rebalances_{args.tag}.csv"
    summary_path = OUT_DIR / f"v6a_core_replay_summary_{args.tag}.csv"
    composite_path = OUT_DIR / f"v6a_core_replay_composite_{args.tag}.csv"
    report_path = OUT_DIR / f"v6a_core_replay_report_{args.tag}.md"
    manifest_path = OUT_DIR / f"v6a_core_replay_manifest_{args.tag}.json"

    daily_df.to_csv(daily_path, index=False)
    rebalance_df.to_csv(rebalances_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    pd.DataFrame([composite_row]).to_csv(composite_path, index=False)
    write_report(report_path, config_path, summary_df, composite_row)
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "config": rel(config_path),
                "sample": sample,
                "artifacts": {
                    "daily": rel(daily_path),
                    "rebalances": rel(rebalances_path),
                    "summary": rel(summary_path),
                    "composite": rel(composite_path),
                    "report": rel(report_path),
                },
                "single_candidate_artifacts": singles,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print("== V6-A Core Deterministic Replay Bridge ==")
    print(f"Daily:      {daily_path}")
    print(f"Rebalances: {rebalances_path}")
    print(f"Summary:    {summary_path}")
    print(f"Composite:  {composite_path}")
    print(f"Report:     {report_path}")
    print(f"Manifest:   {manifest_path}")


if __name__ == "__main__":
    main()
