#!/usr/bin/env python3
"""
实盘成本口径参数验证（Futu / OpenD）
=================================

目标：
  1. 固定结构参数：P3% / C6% / Wing9% / DTE45
  2. 比较动态组数 cap：D=10x / E=15x / F=20x
  3. 全程使用 Futu/OpenD 历史数据
  4. 成本口径对齐到更接近实盘：
     - 动态滑点：沿用 EnhancedICBacktester
     - 往返手续费：$0.65 / 合约，按实际成交日期扣除
     - 融资利息：5.5% 年化，HV20 > 22% 去杠杆日不计融资
  5. 输出：
     - 全周期汇总
     - 逐年回报 / 最大回撤 / Sharpe / 最差月 / 最差日 / 单组最大亏损
     - 黑天鹅滚动窗口压力测试
"""

import io
import sys
import math
import argparse
from pathlib import Path
from contextlib import redirect_stdout
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline
from dynamic_composite_backtest import ASSETS as NOMINAL_ASSETS, IC_PARAMS
from composite_backtest import EnhancedICBacktester


REAL_CAPITAL = 15_000.0
LEVERAGE = 2.0
MARGIN_RATE = 0.055
RISK_FREE = 0.05
COMMISSION_PER_CONTRACT = 0.65
CONTRACTS_PER_GROUP = 4
DELEVERAGE_HV = 0.22

COMPARE_SCENARIOS = [
    {"id": "D", "label": "D 动态10x", "cap_mult": 10},
    {"id": "E", "label": "E 动态15x", "cap_mult": 15},
    {"id": "F", "label": "F 动态20x（当前实盘）", "cap_mult": 20},
]

CANDIDATE_YEARS = [
    {"year": 2008, "label": "2008 金融危机"},
    {"year": 2011, "label": "2011 欧债危机"},
    {"year": 2015, "label": "2015 中国股灾"},
    {"year": 2018, "label": "2018 Q4 暴跌年"},
    {"year": 2020, "label": "2020 COVID 熔断"},
    {"year": 2022, "label": "2022 加息熊市"},
    {"year": 2025, "label": "2025 关税战"},
]

LIVE_ASSETS = [
    {
        "ticker": asset["ticker"],
        "name": asset["name"],
        "capital": asset["capital"] / LEVERAGE,
        "base_groups": asset["base_groups"],
    }
    for asset in NOMINAL_ASSETS
]

CLOSE_ACTIONS = {"CLOSE_IC", "STOP_LOSS", "EARLY_CLOSE", "IC_EXPIRED", "VIX_HARD_STOP"}


def fetch_data(start: str, end: str) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    for asset in LIVE_ASSETS:
        print(f"📥 拉取 {asset['name']} ({asset['ticker']}) {start}~{end}...")
        df = fetch_futu_kline(asset["ticker"], start, end)
        if df is None or df.empty:
            print(f"  ⚠️  {asset['name']} 数据不可用")
            continue
        data[asset["ticker"]] = df.copy()
        print(f"  ✅ {len(df)} 天")
    return data


def run_asset(asset: dict, df: pd.DataFrame, scenario: dict) -> dict:
    bt = EnhancedICBacktester(
        ticker=asset["ticker"],
        initial_capital=asset["capital"],
        max_groups=asset["base_groups"],
        dynamic_sizing=True,
        groups_cap=asset["base_groups"] * scenario["cap_mult"],
        label=f"{scenario['id']}-{asset['name']}",
        **IC_PARAMS,
    )
    bt.COMMISSION = 0.0

    with redirect_stdout(io.StringIO()):
        bt.run(df, save_prefix=f"live_cost_{scenario['id']}_{asset['name']}")

    daily = pd.DataFrame(bt.daily_records)[["date", "total_value", "sigma"]].copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.set_index("date")

    trades = pd.DataFrame(bt.trades).copy()
    if not trades.empty:
        trades["date"] = pd.to_datetime(trades["date"])
        trades["ticker"] = asset["ticker"]
        trades["asset"] = asset["name"]
    return {"daily": daily, "trades": trades}


def build_commission_series(trades: pd.DataFrame, index: pd.Index) -> pd.Series:
    if trades.empty:
        return pd.Series(0.0, index=index)
    trade_counts = trades.groupby("date").size().reindex(index, fill_value=0)
    return trade_counts.astype(float) * CONTRACTS_PER_GROUP * 2 * COMMISSION_PER_CONTRACT


def build_actual_equity_curve(
    raw_portfolio: pd.Series,
    qqq_sigma: pd.Series,
    commission_series: pd.Series,
) -> pd.Series:
    raw_ret = raw_portfolio.pct_change().fillna(0.0)
    equity = REAL_CAPITAL
    records: List[Tuple[pd.Timestamp, float]] = []

    for dt, ret in raw_ret.items():
        sigma_today = float(qqq_sigma.get(dt, 0.20))
        borrowed = equity if sigma_today <= DELEVERAGE_HV else 0.0
        interest = borrowed * MARGIN_RATE / 252
        commission = float(commission_series.get(dt, 0.0))
        equity = max(equity * (1.0 + float(ret)) - interest - commission, 0.0)
        records.append((dt, equity))

    return pd.Series(dict(records)).sort_index()


def calc_curve_stats(eq: pd.Series, label: str) -> dict:
    years = max((eq.index[-1] - eq.index[0]).days / 365.0, 0.1)
    total_ret = (eq.iloc[-1] - REAL_CAPITAL) / REAL_CAPITAL * 100
    ann_ret = ((eq.iloc[-1] / REAL_CAPITAL) ** (1 / years) - 1) * 100
    peak = eq.cummax()
    dd = (eq - peak) / peak * 100
    max_dd = float(dd.min())
    daily_ret = eq.pct_change().dropna()
    rf_d = RISK_FREE / 252
    sharpe = 0.0
    if daily_ret.std() > 1e-10:
        sharpe = float((daily_ret - rf_d).mean() / (daily_ret - rf_d).std() * math.sqrt(252))
    calmar = ann_ret / abs(max_dd) if max_dd < 0 else 0.0
    monthly = eq.resample("ME").last().pct_change().dropna()
    worst_month = float(monthly.min() * 100) if not monthly.empty else 0.0
    worst_day = float(daily_ret.min() * 100) if not daily_ret.empty else 0.0
    return {
        "label": label,
        "final": round(float(eq.iloc[-1]), 0),
        "ann_ret": round(float(ann_ret), 2),
        "total_ret": round(float(total_ret), 2),
        "max_dd": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "calmar": round(float(calmar), 2),
        "worst_month": round(worst_month, 2),
        "worst_day": round(worst_day, 2),
        "years": round(years, 1),
    }


def calc_yearly_breakdown(eq: pd.Series, trades: pd.DataFrame, scenario: dict) -> List[dict]:
    rows: List[dict] = []
    year_ends = eq.resample("YE").last()
    prev_end = REAL_CAPITAL
    rf_d = RISK_FREE / 252

    for i, (dt, end_val) in enumerate(year_ends.items()):
        year = int(dt.year)
        seg = eq[eq.index.year == year]
        if seg.empty:
            continue
        year_ret = (float(end_val) / prev_end - 1) * 100
        prev_end = float(end_val)

        pk = seg.cummax()
        max_dd = float(((seg - pk) / pk * 100).min()) if len(seg) > 1 else 0.0
        day_ret = seg.pct_change().dropna()
        sharpe = 0.0
        if day_ret.std() > 1e-10:
            sharpe = float((day_ret - rf_d).mean() / (day_ret - rf_d).std() * math.sqrt(252))
        monthly = seg.resample("ME").last().pct_change().dropna()
        worst_month = float(monthly.min() * 100) if not monthly.empty else 0.0
        worst_day = float(day_ret.min() * 100) if not day_ret.empty else 0.0

        year_trades = trades[trades["date"].dt.year == year] if not trades.empty else pd.DataFrame()
        close_trades = year_trades[year_trades["action"].isin(CLOSE_ACTIONS)] if not year_trades.empty else pd.DataFrame()
        commission = float(len(year_trades) * CONTRACTS_PER_GROUP * 2 * COMMISSION_PER_CONTRACT)
        worst_trade = 0.0
        if not close_trades.empty and "pnl" in close_trades.columns:
            net_trade = close_trades["pnl"].astype(float) - (CONTRACTS_PER_GROUP * COMMISSION_PER_CONTRACT * 2)
            worst_trade = float(net_trade.min())

        rows.append({
            "scenario_id": scenario["id"],
            "scenario_label": scenario["label"],
            "year": year,
            "year_ret": round(year_ret, 2),
            "year_max_dd": round(max_dd, 2),
            "year_sharpe": round(sharpe, 2),
            "worst_month": round(worst_month, 2),
            "worst_day": round(worst_day, 2),
            "worst_trade": round(worst_trade, 2),
            "year_end_equity": round(float(end_val), 0),
            "trade_count": int(len(year_trades)),
            "commission": round(commission, 2),
        })
    return rows


def run_scenario_period(
    scenario: dict,
    data: Dict[str, pd.DataFrame],
    start: str,
    end: str,
    label: str,
) -> dict:
    asset_results = []
    combined = None
    trades_all = []

    for asset in LIVE_ASSETS:
        df = data.get(asset["ticker"])
        if df is None or df.empty:
            return {}
        date_series = pd.to_datetime(df["date"])
        sliced = df[(date_series >= pd.Timestamp(start)) & (date_series <= pd.Timestamp(end))].reset_index(drop=True)
        if len(sliced) < 120:
            return {}
        result = run_asset(asset, sliced, scenario)
        asset_results.append((asset, result))
        renamed = result["daily"][["total_value"]].rename(columns={"total_value": asset["ticker"]})
        combined = renamed if combined is None else combined.join(renamed, how="inner")
        if not result["trades"].empty:
            trades_all.append(result["trades"])

    if combined is None or combined.empty:
        return {}

    raw_portfolio = combined.sum(axis=1)
    qqq_daily = next(result["daily"] for asset, result in asset_results if asset["ticker"] == "US.QQQ")
    qqq_sigma = qqq_daily["sigma"].reindex(raw_portfolio.index).ffill().fillna(0.20)
    trades = pd.concat(trades_all, ignore_index=True) if trades_all else pd.DataFrame(columns=["date", "action", "pnl"])
    commission_series = build_commission_series(trades, raw_portfolio.index)
    eq = build_actual_equity_curve(raw_portfolio, qqq_sigma, commission_series)

    stats = calc_curve_stats(eq, label)
    yearly_rows = calc_yearly_breakdown(eq, trades, scenario)
    stats.update({
        "scenario_id": scenario["id"],
        "scenario_label": scenario["label"],
        "equity_curve": eq,
        "raw_portfolio": raw_portfolio,
        "trades": trades,
        "yearly_rows": yearly_rows,
        "commission_total": round(float(commission_series.sum()), 2),
    })
    return stats


def print_full_summary(results: List[dict]):
    print("\n" + "=" * 116)
    print("  📊 全周期实盘成本口径对比（Futu/OpenD + 动态滑点 + 往返手续费 + 融资利息）")
    print("=" * 116)
    print(f"  {'场景':<24} {'年化':>8} {'总回报':>8} {'回撤':>8} {'夏普':>6} {'Calmar':>7} {'最差月':>8} {'期末':>13}")
    print("  " + "─" * 102)
    best_sharpe = max(r["sharpe"] for r in results)
    best_final = max(r["final"] for r in results)
    for row in results:
        marks = []
        if row["sharpe"] == best_sharpe:
            marks.append("Sharpe优")
        if row["final"] == best_final:
            marks.append("收益优")
        mark = f" [{' / '.join(marks)}]" if marks else ""
        print(
            f"  {row['scenario_label']:<24} {row['ann_ret']:>+7.2f}% {row['total_ret']:>+7.2f}% "
            f"{row['max_dd']:>7.2f}% {row['sharpe']:>6.2f} {row['calmar']:>7.2f} "
            f"{row['worst_month']:>7.2f}% ${row['final']:>12,.0f}{mark}"
        )


def print_yearly_table(yearly_rows: List[dict]):
    print("\n" + "=" * 132)
    print("  📅 逐年分解（回报 / 年内最大回撤 / Sharpe / 最差月 / 最差日 / 单组最大亏损）")
    print("=" * 132)
    df = pd.DataFrame(yearly_rows).sort_values(["year", "scenario_id"])
    for year in sorted(df["year"].unique()):
        sub = df[df["year"] == year]
        print(f"\n  [{year}]")
        print(f"  {'场景':<24} {'回报':>8} {'回撤':>8} {'夏普':>6} {'最差月':>8} {'最差日':>8} {'单组最大亏损':>14} {'期末净值':>12}")
        print("  " + "─" * 108)
        for _, row in sub.iterrows():
            print(
                f"  {row['scenario_label']:<24} {row['year_ret']:>+7.2f}% {row['year_max_dd']:>7.2f}% "
                f"{row['year_sharpe']:>6.2f} {row['worst_month']:>7.2f}% {row['worst_day']:>7.2f}% "
                f"${row['worst_trade']:>13,.0f} ${row['year_end_equity']:>11,.0f}"
            )


def run_crisis_windows(
    scenarios: List[dict],
    data: Dict[str, pd.DataFrame],
    window_years: int,
) -> List[dict]:
    rows: List[dict] = []
    for year_info in CANDIDATE_YEARS:
        start_year = max(2006, year_info["year"] - window_years + 1)
        start = f"{start_year}-01-01"
        end = f"{year_info['year']}-12-31"
        for scenario in scenarios:
            result = run_scenario_period(
                scenario=scenario,
                data=data,
                start=start,
                end=end,
                label=f"{year_info['label']} | {scenario['label']} | {start_year}-{year_info['year']}",
            )
            if not result:
                continue
            eq = result["equity_curve"]
            crisis_seg = eq[eq.index.year == year_info["year"]]
            crisis_peak = crisis_seg.cummax() if not crisis_seg.empty else crisis_seg
            crisis_dd = float(((crisis_seg - crisis_peak) / crisis_peak * 100).min()) if len(crisis_seg) > 1 else 0.0
            crisis_ret = float((crisis_seg.iloc[-1] / crisis_seg.iloc[0] - 1) * 100) if len(crisis_seg) > 1 else 0.0
            crisis_monthly = crisis_seg.resample("ME").last().pct_change().dropna()
            worst_month = float(crisis_monthly.min() * 100) if not crisis_monthly.empty else 0.0
            rows.append({
                "year": year_info["year"],
                "year_label": year_info["label"],
                "window_label": f"{start_year}-{year_info['year']}",
                "scenario_id": scenario["id"],
                "scenario_label": scenario["label"],
                "ann_ret": result["ann_ret"],
                "max_dd": result["max_dd"],
                "sharpe": result["sharpe"],
                "crisis_ret": round(crisis_ret, 2),
                "crisis_dd": round(crisis_dd, 2),
                "worst_month": round(worst_month, 2),
                "final": result["final"],
            })
    return rows


def print_crisis_table(rows: List[dict]):
    print("\n" + "=" * 116)
    print("  🚨 黑天鹅滚动窗口压力测试（全候选年份）")
    print("=" * 116)
    df = pd.DataFrame(rows).sort_values(["year", "scenario_id"])
    for year in sorted(df["year"].unique()):
        sub = df[df["year"] == year]
        print(f"\n  [{sub.iloc[0]['year_label']}]  窗口={sub.iloc[0]['window_label']}")
        print(f"  {'场景':<24} {'年化':>8} {'全期回撤':>10} {'夏普':>6} {'危机收益':>10} {'危机回撤':>10} {'最差月':>8} {'期末':>12}")
        print("  " + "─" * 102)
        for _, row in sub.iterrows():
            print(
                f"  {row['scenario_label']:<24} {row['ann_ret']:>+7.2f}% {row['max_dd']:>9.2f}% "
                f"{row['sharpe']:>6.2f} {row['crisis_ret']:>+9.2f}% {row['crisis_dd']:>9.2f}% "
                f"{row['worst_month']:>7.2f}% ${row['final']:>11,.0f}"
            )

    agg = (
        df.groupby(["scenario_id", "scenario_label"], as_index=False)
        .agg(
            avg_ann_ret=("ann_ret", "mean"),
            avg_sharpe=("sharpe", "mean"),
            avg_crisis_ret=("crisis_ret", "mean"),
            avg_crisis_dd=("crisis_dd", "mean"),
            avg_final=("final", "mean"),
        )
        .sort_values(["avg_sharpe", "avg_ann_ret"], ascending=[False, False])
    )
    print("\n  压力测试均值：")
    print(f"  {'场景':<24} {'平均年化':>10} {'平均夏普':>10} {'平均危机收益':>14} {'平均危机回撤':>14} {'平均期末':>14}")
    print("  " + "─" * 90)
    for _, row in agg.iterrows():
        print(
            f"  {row['scenario_label']:<24} {row['avg_ann_ret']:>+9.2f}% {row['avg_sharpe']:>10.2f} "
            f"{row['avg_crisis_ret']:>13.2f}% {row['avg_crisis_dd']:>13.2f}% ${row['avg_final']:>13,.0f}"
        )


def save_outputs(full_results: List[dict], yearly_rows: List[dict], crisis_rows: List[dict]) -> List[Path]:
    out_dir = Path(__file__).parent / "backtest_results"
    out_dir.mkdir(exist_ok=True)

    full_path = out_dir / "live_cost_full_summary.csv"
    yearly_path = out_dir / "live_cost_yearly_breakdown.csv"
    crisis_path = out_dir / "live_cost_crisis_windows.csv"

    pd.DataFrame([
        {
            "scenario_id": row["scenario_id"],
            "scenario_label": row["scenario_label"],
            "ann_ret": row["ann_ret"],
            "total_ret": row["total_ret"],
            "max_dd": row["max_dd"],
            "sharpe": row["sharpe"],
            "calmar": row["calmar"],
            "worst_month": row["worst_month"],
            "worst_day": row["worst_day"],
            "final": row["final"],
            "commission_total": row["commission_total"],
        }
        for row in full_results
    ]).to_csv(full_path, index=False)

    pd.DataFrame(yearly_rows).to_csv(yearly_path, index=False)
    pd.DataFrame(crisis_rows).to_csv(crisis_path, index=False)
    return [full_path, yearly_path, crisis_path]


def main():
    parser = argparse.ArgumentParser(description="实盘成本口径参数验证")
    parser.add_argument("--start", default="2006-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--window-years", type=int, default=5)
    args = parser.parse_args()

    print("=" * 116)
    print("  🚀 实盘成本口径参数验证")
    print("  参数固定: P3.0% / C6.0% / Wing9% / DTE45")
    print("  比较对象: D=10x / E=15x / F=20x")
    print("  数据来源: Futu / OpenD")
    print("=" * 116)

    data = fetch_data(args.start, args.end)
    if len(data) < 3:
        print("❌ 数据不足，退出")
        sys.exit(1)

    full_results = []
    yearly_rows: List[dict] = []
    for scenario in COMPARE_SCENARIOS:
        print(f"\n▶ 全周期运行 {scenario['label']} ...")
        result = run_scenario_period(
            scenario=scenario,
            data=data,
            start=args.start,
            end=args.end,
            label=f"{scenario['label']} | {args.start[:4]}-{args.end[:4]}",
        )
        if not result:
            print("  ⚠️  结果为空，跳过")
            continue
        full_results.append(result)
        yearly_rows.extend(result["yearly_rows"])
        print(
            f"  年化={result['ann_ret']:+.2f}%  回撤={result['max_dd']:.2f}%  "
            f"夏普={result['sharpe']:.2f}  最差月={result['worst_month']:.2f}%  "
            f"期末=${result['final']:,.0f}  手续费=${result['commission_total']:,.0f}"
        )

    if not full_results:
        print("❌ 未生成有效全周期结果")
        sys.exit(1)

    crisis_rows = run_crisis_windows(COMPARE_SCENARIOS, data, args.window_years)

    print_full_summary(full_results)
    print_yearly_table(yearly_rows)
    print_crisis_table(crisis_rows)

    out_paths = save_outputs(full_results, yearly_rows, crisis_rows)
    print("\n📁 输出文件：")
    for path in out_paths:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
