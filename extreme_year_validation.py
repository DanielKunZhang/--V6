#!/usr/bin/env python3
"""
随机黑天鹅年份验证（当前实盘参数版）
================================

目的：
  1. 用当前实盘参数 `P3% / C6% / Wing9% / DTE45`
  2. 用资金累积 + 动态组数方式验证极端年份
  3. 对比 D/E/F 三档动态 cap，判断当前 `F=20x` 是否仍是最佳实盘配置

说明：
  - 收益路径与 `dynamic_composite_backtest.py` 保持一致
  - 数据来自 Futu OpenD / `fetch_futu_kline()`
  - 默认从候选危机年份中做可复现随机抽样

用法：
  python3 extreme_year_validation.py
  python3 extreme_year_validation.py --sample-size 5 --seed 20260412
  python3 extreme_year_validation.py --all
"""

import io
import sys
import random
import argparse
from pathlib import Path
from contextlib import redirect_stdout
from typing import Dict, List

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline
from dynamic_composite_backtest import ASSETS, IC_PARAMS, calc_portfolio_stats
from composite_backtest import EnhancedICBacktester


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


def fetch_data(start: str, end: str) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    for asset in ASSETS:
        ticker = asset["ticker"]
        name = asset["name"]
        print(f"📥 拉取 {name} ({ticker}) {start}~{end}...")
        df = fetch_futu_kline(ticker, start, end)
        if df is None or df.empty:
            print(f"  ⚠️  {name} 数据不可用")
            continue
        data[ticker] = df.copy()
        print(f"  ✅ {len(df)} 天")
    return data


def run_asset_quiet(asset: dict, df: pd.DataFrame, cap_mult: int, scenario_id: str) -> dict:
    groups_cap = asset["base_groups"] * cap_mult
    bt = EnhancedICBacktester(
        ticker=asset["ticker"],
        initial_capital=asset["capital"],
        max_groups=asset["base_groups"],
        dynamic_sizing=True,
        groups_cap=groups_cap,
        label=f"{scenario_id}-{asset['name']}",
        **IC_PARAMS,
    )
    with redirect_stdout(io.StringIO()):
        bt.run(df, save_prefix=f"extreme_{scenario_id}_{asset['name']}")
    daily = pd.DataFrame(bt.daily_records)[["date", "total_value"]].set_index("date")
    daily.index = pd.to_datetime(daily.index)
    return {"daily": daily}


def run_year_scenario(
    year_info: dict,
    scenario: dict,
    data: Dict[str, pd.DataFrame],
    window_years: int,
) -> dict:
    year = year_info["year"]
    start_year = max(2006, year - window_years + 1)
    start = pd.Timestamp(f"{start_year}-01-01")
    end = pd.Timestamp(f"{year}-12-31")
    asset_series = []
    total_init = 0

    for asset in ASSETS:
        ticker = asset["ticker"]
        full_df = data.get(ticker)
        if full_df is None or full_df.empty:
            return {}
        date_series = pd.to_datetime(full_df["date"])
        year_df = full_df[(date_series >= start) & (date_series <= end)].reset_index(drop=True)
        if len(year_df) < 120:
            return {}
        result = run_asset_quiet(asset, year_df, scenario["cap_mult"], scenario["id"])
        asset_series.append(result["daily"]["total_value"].rename(asset["name"]))
        total_init += asset["capital"]

    portfolio_tv = pd.concat(asset_series, axis=1, sort=False).dropna().sum(axis=1)
    stats = calc_portfolio_stats(
        portfolio_tv=portfolio_tv,
        total_init=total_init,
        label=f"{year_info['label']} | {scenario['label']} | {start_year}-{year}",
    )

    crisis_start = pd.Timestamp(f"{year}-01-01")
    crisis_end = pd.Timestamp(f"{year}-12-31")
    crisis_tv = portfolio_tv[(portfolio_tv.index >= crisis_start) & (portfolio_tv.index <= crisis_end)]
    crisis_peak = crisis_tv.cummax() if not crisis_tv.empty else crisis_tv
    crisis_dd = ((crisis_tv - crisis_peak) / crisis_peak * 100).min() if len(crisis_tv) > 1 else 0.0
    crisis_ret = ((crisis_tv.iloc[-1] / crisis_tv.iloc[0]) - 1) * 100 if len(crisis_tv) > 1 else 0.0
    monthly = crisis_tv.resample("ME").last().pct_change().dropna()
    worst_month = monthly.min() * 100 if not monthly.empty else 0.0

    return {
        "year": year,
        "year_label": year_info["label"],
        "window_start_year": start_year,
        "window_label": f"{start_year}-{year}",
        "scenario_id": scenario["id"],
        "scenario_label": scenario["label"],
        "ann_ret": stats["ann_ret"],
        "max_dd": stats["max_dd"],
        "sharpe": stats["sharpe"],
        "final": stats["final"],
        "crisis_ret": round(float(crisis_ret), 2),
        "crisis_dd": round(float(crisis_dd), 2),
        "worst_month": round(float(worst_month), 2),
    }


def print_year_tables(results: List[dict]):
    print("\n" + "=" * 96)
    print("  🎯 随机黑天鹅年份验证（动态组数 + 资金累积）")
    print("=" * 96)

    grouped: Dict[int, List[dict]] = {}
    for row in results:
        grouped.setdefault(row["year"], []).append(row)

    for year in sorted(grouped):
        rows = sorted(grouped[year], key=lambda item: item["scenario_id"])
        best_sharpe = max(r["sharpe"] for r in rows)
        best_final = max(r["final"] for r in rows)
        best_crisis_dd = max(r["crisis_dd"] for r in rows)
        print(f"\n  [{rows[0]['year_label']}]  滚动窗口: {rows[0]['window_label']}")
        print(f"  {'场景':<24} {'年化':>8} {'全期回撤':>10} {'夏普':>6} {'危机年回撤':>12} {'最差月':>8} {'期末':>12}")
        print("  " + "─" * 92)
        for row in rows:
            markers = []
            if row["sharpe"] == best_sharpe:
                markers.append("Sharpe优")
            if row["final"] == best_final:
                markers.append("收益优")
            if row["crisis_dd"] == best_crisis_dd:
                markers.append("危机优")
            marker = f" [{' / '.join(markers)}]" if markers else ""
            print(
                f"  {row['scenario_label']:<24} {row['ann_ret']:>+7.2f}% {row['max_dd']:>9.2f}% "
                f"{row['sharpe']:>6.2f} {row['crisis_dd']:>11.2f}% {row['worst_month']:>7.2f}% "
                f"${row['final']:>11,.0f}{marker}"
            )


def count_wins(df: pd.DataFrame, metric: str, prefer_higher: bool = True) -> Dict[str, int]:
    wins: Dict[str, int] = {}
    for _, sub in df.groupby("year"):
        target = sub[metric].max() if prefer_higher else sub[metric].min()
        winners = sub[sub[metric] == target]["scenario_id"].tolist()
        for sid in winners:
            wins[sid] = wins.get(sid, 0) + 1
    return wins


def print_summary(results: List[dict], selected_years: List[dict], seed: int):
    df = pd.DataFrame(results)
    if df.empty:
        return

    sharpe_wins = count_wins(df, "sharpe", prefer_higher=True)
    final_wins = count_wins(df, "final", prefer_higher=True)
    dd_wins = count_wins(df, "crisis_dd", prefer_higher=True)

    agg = (
        df.groupby(["scenario_id", "scenario_label"], as_index=False)
        .agg(
            avg_ann_ret=("ann_ret", "mean"),
            avg_max_dd=("max_dd", "mean"),
            avg_sharpe=("sharpe", "mean"),
            avg_crisis_dd=("crisis_dd", "mean"),
            avg_crisis_ret=("crisis_ret", "mean"),
            avg_worst_month=("worst_month", "mean"),
            avg_final=("final", "mean"),
        )
        .sort_values(["avg_sharpe", "avg_ann_ret"], ascending=[False, False])
    )

    print("\n" + "=" * 96)
    print(f"  📌 汇总结论 | 抽样年份={','.join(str(item['year']) for item in selected_years)} | seed={seed}")
    print("=" * 96)
    print(f"  {'场景':<24} {'平均年化':>10} {'平均夏普':>10} {'平均危机回撤':>14} {'平均危机收益':>14} {'平均期末':>14}")
    print("  " + "─" * 88)
    for _, row in agg.iterrows():
        sid = row["scenario_id"]
        print(
            f"  {row['scenario_label']:<24} {row['avg_ann_ret']:>+9.2f}% {row['avg_sharpe']:>10.2f} "
            f"{row['avg_crisis_dd']:>13.2f}% {row['avg_crisis_ret']:>13.2f}% ${row['avg_final']:>13,.0f}  "
            f"(Sharpe胜场={sharpe_wins.get(sid, 0)}, 收益胜场={final_wins.get(sid, 0)}, 危机年胜场={dd_wins.get(sid, 0)})"
        )

    best_sharpe_row = agg.sort_values(["avg_sharpe", "avg_ann_ret"], ascending=[False, False]).iloc[0]
    best_return_row = agg.sort_values(["avg_final", "avg_ann_ret"], ascending=[False, False]).iloc[0]
    safest_row = agg.sort_values(["avg_max_dd", "avg_sharpe"], ascending=[False, False]).iloc[0]

    print("\n  结论口径：")
    print(
        f"  - 风险调整后最佳：{best_sharpe_row['scenario_label']} "
        f"(平均夏普 {best_sharpe_row['avg_sharpe']:.2f})"
    )
    print(
        f"  - 绝对收益最佳：{best_return_row['scenario_label']} "
        f"(平均期末 ${best_return_row['avg_final']:,.0f})"
    )
    print(
        f"  - 回撤最稳健：{safest_row['scenario_label']} "
        f"(平均危机年回撤 {safest_row['avg_crisis_dd']:.2f}%)"
    )


def save_csv(results: List[dict], seed: int) -> Path:
    out_path = Path(__file__).parent / "backtest_results" / f"extreme_year_validation_seed_{seed}.csv"
    out_path.parent.mkdir(exist_ok=True)
    pd.DataFrame(results).sort_values(["year", "scenario_id"]).to_csv(out_path, index=False)
    return out_path


def select_years(all_years: bool, sample_size: int, seed: int) -> List[dict]:
    if all_years or sample_size >= len(CANDIDATE_YEARS):
        return list(CANDIDATE_YEARS)
    rng = random.Random(seed)
    return sorted(rng.sample(CANDIDATE_YEARS, sample_size), key=lambda item: item["year"])


def main():
    parser = argparse.ArgumentParser(description="随机黑天鹅年份验证")
    parser.add_argument("--seed", type=int, default=20260412, help="随机种子，默认 20260412")
    parser.add_argument("--sample-size", type=int, default=5, help="随机抽样年份数量，默认 5")
    parser.add_argument("--window-years", type=int, default=5, help="每次回测滚动窗口年数，默认 5")
    parser.add_argument("--all", action="store_true", help="跑全部候选黑天鹅年份")
    args = parser.parse_args()

    selected_years = select_years(args.all, args.sample_size, args.seed)
    start = f"{min(max(2006, item['year'] - args.window_years + 1) for item in selected_years)}-01-01"
    end = f"{max(item['year'] for item in selected_years)}-12-31"

    print("=" * 96)
    print("  🚨 当前实盘配置黑天鹅年份验证")
    print("  参数: P3.0% / C6.0% / Wing9% / DTE45 / 动态组数 / 资金累积")
    print("=" * 96)
    print(f"  候选年份: {', '.join(str(item['year']) for item in CANDIDATE_YEARS)}")
    print(f"  本次抽样: {', '.join(str(item['year']) for item in selected_years)}  (seed={args.seed})")
    print(f"  滚动窗口: {args.window_years} 年")

    data = fetch_data(start, end)
    if "US.QQQ" not in data:
        print("❌ QQQ 数据不可用，退出")
        sys.exit(1)

    results: List[dict] = []
    for year_info in selected_years:
        for scenario in COMPARE_SCENARIOS:
            print(f"\n▶ 运行 {year_info['label']} | {scenario['label']} ...")
            row = run_year_scenario(year_info, scenario, data, args.window_years)
            if not row:
                print("  ⚠️  结果为空，跳过")
                continue
            results.append(row)
            print(
                f"  年化={row['ann_ret']:+.2f}%  全期回撤={row['max_dd']:.2f}%  "
                f"危机年回撤={row['crisis_dd']:.2f}%  夏普={row['sharpe']:.2f}  期末=${row['final']:,.0f}"
            )

    if not results:
        print("❌ 没有生成有效结果")
        sys.exit(1)

    print_year_tables(results)
    print_summary(results, selected_years, args.seed)
    out_path = save_csv(results, args.seed)
    print(f"\n📁 结果已保存: {out_path}")


if __name__ == "__main__":
    main()
