#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import v6ab_classifier_bridge_backtest as bridge
import v6b_theme_rotation_backtest as bt
from v6ab_sleeve_blend_backtest import benchmark_equity, dynamic_b_sizing_equity, load_v6a_composite


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_continuous_defense_experiment"
DEFAULT_V6A_DAILY = bridge.DEFAULT_V6A_DAILY


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value * 100:+.2f}%"


def max_drawdown_window(eq: pd.Series) -> dict[str, Any]:
    series = eq.dropna().sort_index()
    peak = series.cummax()
    dd = series / peak - 1.0
    trough = dd.idxmin()
    peak_date = series.loc[:trough].idxmax()
    return {"peak": str(pd.Timestamp(peak_date).date()), "trough": str(pd.Timestamp(trough).date()), "max_dd": float(dd.loc[trough])}


def risk_state(
    frame: pd.DataFrame,
    rets: pd.DataFrame,
    base_ret: pd.Series,
    base_eq: pd.Series,
    dt: pd.Timestamp,
    prev: pd.Timestamp,
    *,
    vol_threshold: float,
    dd_threshold: float,
) -> dict[str, Any]:
    spy_ma = frame["SPY"].rolling(200).mean()
    qqq_ma = frame["QQQ"].rolling(200).mean()
    gld_ma = frame["GLD"].rolling(126).mean()
    ief_ma = frame["IEF"].rolling(126).mean()
    spy_63 = frame["SPY"].pct_change(63)
    qqq_63 = frame["QQQ"].pct_change(63)
    gld_63 = frame["GLD"].pct_change(63)
    ief_63 = frame["IEF"].pct_change(63)
    base_vol = base_ret.rolling(63).std() * np.sqrt(252)
    base_dd = base_eq / base_eq.cummax() - 1.0
    market_bad = (
        pd.notna(spy_ma.loc[prev])
        and pd.notna(qqq_ma.loc[prev])
        and (frame.loc[prev, "SPY"] < spy_ma.loc[prev] or frame.loc[prev, "QQQ"] < qqq_ma.loc[prev])
    )
    vol_bad = bool(pd.notna(base_vol.loc[prev]) and base_vol.loc[prev] >= vol_threshold)
    dd_bad = bool(pd.notna(base_dd.loc[prev]) and base_dd.loc[prev] <= dd_threshold)
    trend_bad = bool((pd.notna(spy_63.loc[prev]) and spy_63.loc[prev] < -0.03) or (pd.notna(qqq_63.loc[prev]) and qqq_63.loc[prev] < -0.03))
    gld_ok = bool(pd.notna(gld_ma.loc[prev]) and frame.loc[prev, "GLD"] >= gld_ma.loc[prev] and pd.notna(gld_63.loc[prev]) and gld_63.loc[prev] > -0.02)
    ief_ok = bool(pd.notna(ief_ma.loc[prev]) and frame.loc[prev, "IEF"] >= ief_ma.loc[prev] and pd.notna(ief_63.loc[prev]) and ief_63.loc[prev] > -0.02)
    trigger_count = sum([market_bad, vol_bad, dd_bad, trend_bad])
    return {
        "market_bad": market_bad,
        "vol_bad": vol_bad,
        "dd_bad": dd_bad,
        "trend_bad": trend_bad,
        "trigger_count": trigger_count,
        "gld_ok": gld_ok,
        "ief_ok": ief_ok,
    }


def defense_weights(policy: str, state: dict[str, Any], hedge_max: float) -> dict[str, float]:
    trigger_count = int(state["trigger_count"])
    if policy == "baseline_discrete":
        hedge = hedge_max if trigger_count >= 2 else (hedge_max * 0.5 if trigger_count == 1 else 0.0)
        asset = "GLD" if state["gld_ok"] else "BIL"
        return {asset: hedge} if hedge > 0 else {}
    if policy == "continuous_score_bil_gld":
        hedge = min(hedge_max, hedge_max * trigger_count / 4.0)
        if hedge <= 0:
            return {}
        gld_share = 0.35 if state["gld_ok"] else 0.0
        return {"BIL": hedge * (1.0 - gld_share), "GLD": hedge * gld_share}
    if policy == "continuous_score_bil_only_crash":
        hedge = min(hedge_max, hedge_max * trigger_count / 4.0)
        if hedge <= 0:
            return {}
        if state["market_bad"] and state["vol_bad"]:
            return {"BIL": hedge}
        gld_share = 0.35 if state["gld_ok"] else 0.0
        return {"BIL": hedge * (1.0 - gld_share), "GLD": hedge * gld_share}
    if policy == "continuous_multi_asset":
        hedge = min(hedge_max, hedge_max * trigger_count / 4.0)
        if hedge <= 0:
            return {}
        gld_share = 0.25 if state["gld_ok"] else 0.0
        ief_share = 0.25 if state["ief_ok"] else 0.0
        bil_share = max(0.0, 1.0 - gld_share - ief_share)
        return {"BIL": hedge * bil_share, "GLD": hedge * gld_share, "IEF": hedge * ief_share}
    if policy == "cash_first_high_hedge":
        hedge = min(0.45, 0.15 * trigger_count)
        return {"BIL": hedge} if hedge > 0 else {}
    raise ValueError(f"unknown policy: {policy}")


def run_dynamic_b_with_policy(
    curves: dict[str, pd.Series],
    *,
    b_key: str,
    policy: str,
    start: str,
    end: str,
) -> pd.Series:
    if policy == "baseline_discrete":
        eq, _ = dynamic_b_sizing_equity(
            curves,
            b_key=b_key,
            b_low=0.05,
            b_mid=0.30,
            b_high=0.45,
            b_strong_126d=0.08,
            b_weak_63d=-0.08,
            hedge_max=0.30,
            vol_threshold=0.28,
            corr_threshold=0.60,
            dd_threshold=-0.12,
            start=start,
            end=end,
        )
        return eq
    frame = pd.DataFrame(curves).sort_index().ffill().dropna()
    frame = frame[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
    rets = frame.pct_change().fillna(0.0)
    b_mom_63 = frame[b_key].pct_change(63)
    b_mom_126 = frame[b_key].pct_change(126)
    spy_ma = frame["SPY"].rolling(200).mean()
    qqq_ma = frame["QQQ"].rolling(200).mean()
    ab_corr = rets["V6A"].rolling(63).corr(rets[b_key])
    equity = bt.INITIAL_CAPITAL
    records: list[tuple[pd.Timestamp, float]] = []
    base_equity = 1.0
    base_peak = 1.0
    for i, dt in enumerate(frame.index):
        if i == 0:
            b_weight = 0.30
            weights = {"V6A": 0.70, b_key: 0.30}
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
            b_weight = 0.30
            if pd.notna(b_mom_126.loc[prev]) and b_mom_126.loc[prev] >= 0.08 and market_ok:
                b_weight = 0.45
            if pd.notna(b_mom_63.loc[prev]) and b_mom_63.loc[prev] <= -0.08:
                b_weight = 0.05
            if market_bad and pd.notna(ab_corr.loc[prev]) and ab_corr.loc[prev] >= 0.60:
                b_weight = min(b_weight, 0.05)
            a_weight = 1.0 - b_weight
            base_ret_today = a_weight * float(rets.loc[dt, "V6A"]) + b_weight * float(rets.loc[dt, b_key])
            base_equity *= 1.0 + base_ret_today
            base_peak = max(base_peak, base_equity)
            blend_ret = a_weight * rets["V6A"] + b_weight * rets[b_key]
            blend_eq = (1.0 + blend_ret).cumprod()
            state = risk_state(
                frame,
                rets,
                blend_ret,
                blend_eq,
                dt,
                prev,
                vol_threshold=0.28,
                dd_threshold=-0.12,
            )
            state["dd_bad"] = base_equity / base_peak - 1.0 <= -0.12
            state["trigger_count"] = sum([state["market_bad"], state["vol_bad"], state["dd_bad"], state["trend_bad"]])
            hedge = defense_weights(policy, state, 0.30)
            hedge_weight = sum(hedge.values())
            weights = {"V6A": a_weight * (1.0 - hedge_weight), b_key: b_weight * (1.0 - hedge_weight), **hedge}
        day_ret = sum(float(rets.loc[dt, key]) * weight for key, weight in weights.items() if key in rets.columns)
        equity *= 1.0 + day_ret
        records.append((dt, equity))
    return pd.Series([value for _, value in records], index=[dt for dt, _ in records])


def period_stats(eq: pd.Series, start: str, end: str) -> dict[str, float]:
    part = eq[(eq.index >= pd.Timestamp(start)) & (eq.index <= pd.Timestamp(end))]
    return bt.stats(part) if len(part) > 2 else {}


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB Continuous Defense Experiment",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 回测区间：`{payload['start']} -> {payload['end']}`",
        "- 目的：离线验证防守层连续化是否能突破 2020 流动性冲击 MaxDD。",
        "- 注意：本实验不改变模拟盘，不构成晋级。",
        "",
        "## Verdict",
        "",
        f"- decision：`{payload['verdict']['decision']}`",
        f"- reason：{payload['verdict']['reason']}",
        "",
        "## Results",
        "",
        "| policy | ann | maxDD | Sharpe | 2020 ann | DD window |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["rows"]:
        s = row["stats"]
        w = row["maxdd_window"]
        p2020 = row["periods"]["2020"]
        lines.append(
            f"| `{row['policy']}` | {fmt_pct(s.get('ann_ret'))} | {fmt_pct(s.get('max_dd'))} | {s.get('sharpe', 0):.2f} | "
            f"{fmt_pct(p2020.get('ann_ret'))} | {w['peak']} -> {w['trough']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- 若连续防守降低 MaxDD 但明显牺牲年化/2020 修复速度，不能直接推广。",
            "- 若只是把 GLD 改成 BIL 改善 2020 crash，说明问题是 crash 期 GLD 相关性失效，而不是一定要复杂多资产。",
            "- 若多资产连续化改善有限，说明 Deepseek 的 P0 只能作为研究线，不应替代 PIT evidence / forward WATCH 主线。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline continuous defense experiments for V6AB.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--v6a-daily", type=Path, default=DEFAULT_V6A_DAILY)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    v6a = load_v6a_composite(args.v6a_daily)
    prices = bt.build_price_matrix(bridge.required_tickers(bt.THEMES), args.start, args.end).ffill(limit=3)
    baseline_b, _ = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    curves = {
        "V6A": v6a,
        "baseline_v2": baseline_b,
        "GLD": benchmark_equity(prices, "US.GLD"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "IEF": benchmark_equity(prices, "US.IEF"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
    }
    policies = [
        "baseline_discrete",
        "continuous_score_bil_gld",
        "continuous_score_bil_only_crash",
        "continuous_multi_asset",
        "cash_first_high_hedge",
    ]
    rows = []
    for policy in policies:
        eq = run_dynamic_b_with_policy(curves, b_key="baseline_v2", policy=policy, start=args.start, end=args.end)
        rows.append(
            {
                "policy": policy,
                "stats": bt.stats(eq),
                "periods": {"2020": period_stats(eq, "2020-01-01", "2020-12-31")},
                "maxdd_window": max_drawdown_window(eq),
            }
        )
    base = next(row for row in rows if row["policy"] == "baseline_discrete")
    best = sorted(rows, key=lambda row: (row["stats"].get("sharpe", 0), row["stats"].get("ann_ret", 0)), reverse=True)[0]
    if best["policy"] != "baseline_discrete" and best["stats"].get("max_dd", 0) >= base["stats"].get("max_dd", 0) + 0.02:
        verdict = {
            "decision": "PROMOTE_TO_RESEARCH_CANDIDATE_REVIEW",
            "reason": f"{best['policy']} materially improves drawdown with comparable Sharpe; next step is full candidate gate and PIT/forward constraints.",
        }
    elif best["policy"] != "baseline_discrete":
        verdict = {
            "decision": "WATCH_ONLY",
            "reason": f"{best['policy']} improves some metric but not enough for promotion; keep as offline diagnostic.",
        }
    else:
        verdict = {
            "decision": "NO_DEFENSE_PROMOTION",
            "reason": "Baseline discrete defense remains best or close enough; do not add complexity.",
        }
    payload = {"asof": args.asof, "start": args.start, "end": args.end, "verdict": verdict, "rows": rows}
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md + "\n", encoding="utf-8")
    (REPORT_ROOT / "V6AB_Continuous_Defense_Experiment_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (REPORT_ROOT / "V6AB_Continuous_Defense_Experiment_LATEST.md").write_text(md + "\n", encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
