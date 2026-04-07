#!/usr/bin/env python3
"""
多标的分散化回测
对比：单 QQQ G2  vs  QQQ+IWM  vs  QQQ+GLD  vs  QQQ+IWM+GLD
目标：在不增加风险的前提下提升夏普比率

原理：多个低相关标的同时运行 IC，权益曲线叠加后回撤互相抵消
"""

import sys, json, math
from pathlib import Path
from datetime import date
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline
from iron_condor_us import USIronCondorBacktester

CAPITAL_TOTAL = 15_000
START, END = "2010-01-01", "2025-12-31"
RISK_FREE = 0.05


# ── 各标的单独回测（每标的独立分配资金）──────────────────────────
def run_single(ticker: str, capital: float, groups: int, label: str, df: pd.DataFrame) -> dict:
    bt = USIronCondorBacktester(
        ticker=ticker,
        initial_capital=capital,
        otm_distance=0.05,
        wing_width=0.08,
        dte=30,
        max_groups=groups,
        cooldown_days=5,
        stop_loss_pct=0.05,
        stop_loss_buffer=1.5,
        early_close_days=2,
        entry_mode="pre_expiry",
        entry_days_before_expiry=30,
        label=label,
    )
    r = bt.run(df, save_prefix=f"multi_{ticker.split('.')[1]}_{groups}g")
    # 附上每日净值序列
    r["daily"] = pd.DataFrame(bt.daily_records)[["date", "total_value"]].set_index("date")
    r["daily_raw"] = bt.daily_records
    return r


def calc_portfolio_stats(dfs: dict, capitals: dict, label: str) -> dict:
    """
    合并多个标的的每日净值，计算组合统计指标。
    dfs: {ticker: daily_df}  daily_df.index=date, columns=[total_value]
    capitals: {ticker: initial_capital}
    """
    # 对齐日期（取交集）
    combined = None
    for ticker, df in dfs.items():
        df = df.rename(columns={"total_value": ticker})
        combined = df if combined is None else combined.join(df, how="inner")

    # 各标的收益率
    total_init = sum(capitals.values())
    weights = {t: capitals[t] / total_init for t in capitals}

    # 组合每日总价值
    combined["portfolio"] = sum(
        combined[t] * (capitals[t] / capitals[t].iloc[0] if hasattr(capitals[t], 'iloc') else 1)
        / (total_init / capitals[t])
        * capitals[t]
        for t in dfs
    )

    # 更简单：直接按初始资金比例加权
    combined["portfolio"] = sum(
        combined[t] * weights[t] / (combined[t].iloc[0] / capitals[t])
        for t in dfs
    )
    # 修正：portfolio 单位是"总资金"
    combined["portfolio"] = sum(combined[t] * (capitals[t] / combined[t].iloc[0]) for t in dfs)

    tv = combined["portfolio"]
    final_v = tv.iloc[-1]
    total_ret = (final_v - total_init) / total_init * 100
    years = (tv.index[-1] - tv.index[0]).days / 365.0
    ann_ret = ((1 + total_ret / 100) ** (1 / max(years, 0.1)) - 1) * 100

    peak = tv.cummax()
    dd = (tv - peak) / peak * 100
    max_dd = dd.min()

    dr = tv.pct_change().dropna()
    rf_d = RISK_FREE / 252
    sharpe = round((dr - rf_d).mean() / (dr - rf_d).std() * math.sqrt(252), 2) if dr.std() > 1e-10 else 0

    return {
        "label": label,
        "initial": total_init,
        "final": round(final_v, 0),
        "total_ret": round(total_ret, 2),
        "ann_ret": round(ann_ret, 2),
        "max_dd": round(max_dd, 2),
        "sharpe": sharpe,
        "years": round(years, 1),
        "combined": combined,
    }


def print_comparison(results: list):
    print(f"\n\n{'='*90}")
    print(f"  📊 多标的分散化对比  —  $15,000 初始资金  2010-2025")
    print(f"{'='*90}")
    hdr = f"  {'配置':<38}  {'年化':>8}  {'最大回撤':>9}  {'夏普':>6}  {'最终资金':>10}  {'夏普提升':>8}"
    print(hdr)
    print("  " + "─" * 85)

    base_sharpe = next(r["sharpe"] for r in results if "基线" in r["label"])

    for r in sorted(results, key=lambda x: x["sharpe"], reverse=True):
        sharpe_delta = r["sharpe"] - base_sharpe
        delta_s = f"+{sharpe_delta:.2f}" if sharpe_delta >= 0 else f"{sharpe_delta:.2f}"
        marker = " ★" if r["sharpe"] == max(x["sharpe"] for x in results) else "  "
        print(f"{marker}{r['label']:<40}  {r['ann_ret']:>+7.2f}%  "
              f"{r['max_dd']:>8.2f}%  {r['sharpe']:>6.2f}  "
              f"${r['final']:>9,.0f}  {delta_s:>8}")

    print("  " + "─" * 85)
    print(f"\n  夏普比率说明：每承担1单位风险获得的超额收益，越高越好")
    print(f"  分散化收益：多标的组合通过低相关性互相对冲，无需增加风险即可提升夏普")
    print(f"{'='*90}")


def print_correlation_analysis(single_results: dict):
    """分析各标的日收益率相关性"""
    print(f"\n\n{'='*60}")
    print(f"  📈 各标的策略收益相关性分析")
    print(f"{'='*60}")

    daily_returns = {}
    for ticker, r in single_results.items():
        df = pd.DataFrame(r["daily_raw"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        daily_returns[ticker] = df["total_value"].pct_change().dropna()

    ret_df = pd.DataFrame(daily_returns).dropna()
    corr = ret_df.corr()

    print("\n  相关系数矩阵（越低代表分散效果越好）：")
    tickers = list(daily_returns.keys())
    header = f"  {'':>6}" + "".join(f"{t:>8}" for t in tickers)
    print(header)
    for t1 in tickers:
        row = f"  {t1:>6}"
        for t2 in tickers:
            v = corr.loc[t1, t2]
            row += f"  {v:>6.3f}"
        print(row)

    print(f"\n  解读：")
    for i, t1 in enumerate(tickers):
        for t2 in tickers[i+1:]:
            v = corr.loc[t1, t2]
            level = "高度相关" if v > 0.7 else ("中度相关" if v > 0.4 else ("低相关" if v > 0.2 else "负/零相关"))
            print(f"    {t1} vs {t2}: {v:.3f} → {level}")


if __name__ == "__main__":
    print("=" * 60)
    print("  🌍 多标的分散化回测")
    print("=" * 60)

    # 拉取所有标的数据
    tickers = {
        "US.QQQ": "QQQ（纳斯达克100）",
        "US.IWM": "IWM（罗素2000小盘）",
        "US.GLD": "GLD（黄金ETF）",
    }

    data = {}
    for ticker, name in tickers.items():
        print(f"\n📥 拉取 {name}...")
        df = fetch_futu_kline(ticker, START, END)
        if df is None or df.empty:
            print(f"  ⚠️ {ticker} 数据获取失败，跳过")
        else:
            data[ticker] = df
            print(f"  ✅ {len(df)} 天  ${df['Close'].min():.0f}~${df['Close'].max():.0f}")

    if "US.QQQ" not in data:
        print("❌ QQQ 数据获取失败，退出")
        sys.exit(1)

    # ── 单标的回测（用于相关性分析和资金分配参考）──────────────
    print(f"\n\n{'─'*60}")
    print("  运行单标的回测（分析基础数据）...")
    print(f"{'─'*60}")

    single = {}
    for ticker in data:
        cap = CAPITAL_TOTAL  # 各自独立满额资金（用于相关性分析）
        label = f"{ticker.split('.')[1]} 独立 G2"
        print(f"  {label}...")
        r = run_single(ticker, cap, 2, label, data[ticker])
        single[ticker] = r
        print(f"    年化{r['ann_return']:+.2f}%  回撤{r['max_dd']:.2f}%  夏普{r['sharpe_ratio']:.2f}")

    # 相关性分析
    print_correlation_analysis(single)

    # ── 组合回测（按资金分配）──────────────────────────────────
    print(f"\n\n{'─'*60}")
    print("  运行组合回测...")
    print(f"{'─'*60}")

    # 资金分配方案（基于保证金需求）
    # QQQ G2: ~$9,400 max margin
    # IWM G1: ~$1,680 max margin (IWM ~$210 × 8% × 100)
    # GLD G1: ~$2,000 max margin (GLD ~$250 × 8% × 100)
    # 按保证金需求比例分配15K

    portfolio_results = []

    # 基线：纯 QQQ G2
    print("\n  A. 基线：纯 QQQ G2 $15,000...")
    r_qqq_base = run_single("US.QQQ", 15_000, 2, "A 基线 QQQ G2", data["US.QQQ"])
    portfolio_results.append({
        "label": "A 基线 纯QQQ G2",
        "ann_ret": r_qqq_base["ann_return"],
        "max_dd": r_qqq_base["max_dd"],
        "sharpe": r_qqq_base["sharpe_ratio"],
        "final": r_qqq_base["final_value"],
        "initial": 15_000,
        "years": r_qqq_base["years"],
    })

    available_tickers = list(data.keys())

    # 组合 B：QQQ + IWM（如果都有数据）
    if "US.IWM" in data:
        print("\n  B. QQQ $10,000 G2  +  IWM $5,000 G1...")
        r_qqq_b = run_single("US.QQQ", 10_000, 2, "B-QQQ", data["US.QQQ"])
        r_iwm_b = run_single("US.IWM", 5_000,  1, "B-IWM", data["US.IWM"])

        stats_b = calc_portfolio_stats(
            {"US.QQQ": r_qqq_b["daily"], "US.IWM": r_iwm_b["daily"]},
            {"US.QQQ": 10_000, "US.IWM": 5_000},
            "B QQQ($10K G2) + IWM($5K G1)"
        )
        portfolio_results.append(stats_b)

    # 组合 C：QQQ + GLD（如果都有数据）
    if "US.GLD" in data:
        print("\n  C. QQQ $10,000 G2  +  GLD $5,000 G1...")
        r_qqq_c = run_single("US.QQQ", 10_000, 2, "C-QQQ", data["US.QQQ"])
        r_gld_c = run_single("US.GLD", 5_000,  1, "C-GLD", data["US.GLD"])

        stats_c = calc_portfolio_stats(
            {"US.QQQ": r_qqq_c["daily"], "US.GLD": r_gld_c["daily"]},
            {"US.QQQ": 10_000, "US.GLD": 5_000},
            "C QQQ($10K G2) + GLD($5K G1)"
        )
        portfolio_results.append(stats_c)

    # 组合 D：QQQ + IWM + GLD（三标的）
    if "US.IWM" in data and "US.GLD" in data:
        print("\n  D. QQQ $9,000 G2  +  IWM $3,000 G1  +  GLD $3,000 G1...")
        r_qqq_d = run_single("US.QQQ", 9_000, 2, "D-QQQ", data["US.QQQ"])
        r_iwm_d = run_single("US.IWM", 3_000, 1, "D-IWM", data["US.IWM"])
        r_gld_d = run_single("US.GLD", 3_000, 1, "D-GLD", data["US.GLD"])

        stats_d = calc_portfolio_stats(
            {"US.QQQ": r_qqq_d["daily"], "US.IWM": r_iwm_d["daily"], "US.GLD": r_gld_d["daily"]},
            {"US.QQQ": 9_000, "US.IWM": 3_000, "US.GLD": 3_000},
            "D QQQ($9K G2)+IWM($3K)+GLD($3K)"
        )
        portfolio_results.append(stats_d)

    # 组合 E：均等分配（$5K × 3）
    if "US.IWM" in data and "US.GLD" in data:
        print("\n  E. 均等分配 QQQ $5,000 G1 + IWM $5,000 G1 + GLD $5,000 G1...")
        r_qqq_e = run_single("US.QQQ", 5_000, 1, "E-QQQ", data["US.QQQ"])
        r_iwm_e = run_single("US.IWM", 5_000, 1, "E-IWM", data["US.IWM"])
        r_gld_e = run_single("US.GLD", 5_000, 1, "E-GLD", data["US.GLD"])

        stats_e = calc_portfolio_stats(
            {"US.QQQ": r_qqq_e["daily"], "US.IWM": r_iwm_e["daily"], "US.GLD": r_gld_e["daily"]},
            {"US.QQQ": 5_000, "US.IWM": 5_000, "US.GLD": 5_000},
            "E 均等 QQQ+IWM+GLD ($5K×3)"
        )
        portfolio_results.append(stats_e)

    # 打印汇总
    print_comparison(portfolio_results)

    # 保存结果
    out = Path(__file__).parent / "backtest_results" / "multi_asset.json"
    out.parent.mkdir(exist_ok=True)
    save_data = [{k: v for k, v in r.items() if k != "combined"} for r in portfolio_results]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, default=str, ensure_ascii=False)
    print(f"\n📁 结果已保存: {out}")
