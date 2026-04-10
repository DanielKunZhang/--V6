#!/usr/bin/env python3
"""
杠杆回测：配置D（QQQ $9k + IWM $3k + GLD $3k）在不同杠杆倍率下的表现

杠杆模型：
  - 实际资本 REAL_CAPITAL = $15,000
  - 杠杆 L 倍：名义资本 = L × $15k，借贷 = (L-1) × $15k
  - 融资利息：MARGIN_RATE 年化（按日计提）
  - 强制平仓（Margin Call）：权益跌破借款额 × MAINT_MARGIN_RATIO 时，
    当日强制平仓，记录为最大损失并停止该杠杆场景

测试杠杆：1x / 1.5x / 2x / 2.5x / 3x
"""

import sys, math
from pathlib import Path
from datetime import date
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline
from iron_condor_us import USIronCondorBacktester

# ── 参数 ────────────────────────────────────────────────────────────
REAL_CAPITAL   = 15_000          # 实际投入资本
START, END     = "2010-01-01", "2025-12-31"
RISK_FREE      = 0.05
MARGIN_RATE    = 0.055           # 融资年利率 5.5%（当前IBKR/富途保证金利率）
MAINT_MARGIN   = 0.30            # 维持保证金率：权益 < 借款 × 30% 触发margin call

# 配置D：各标的分配
ASSETS = [
    {"ticker": "US.QQQ", "capital_ratio": 9/15, "max_groups": 2, "hv20_threshold": 0.25},
    {"ticker": "US.IWM", "capital_ratio": 3/15, "max_groups": 1, "hv20_threshold": 0.25},
    {"ticker": "US.GLD", "capital_ratio": 3/15, "max_groups": 1, "hv20_threshold": 0.18},
]

LEVERAGE_LIST = [1.0, 1.5, 2.0, 2.5, 3.0]


def run_asset(ticker: str, capital: float, groups: int, df: pd.DataFrame) -> pd.DataFrame:
    """跑单个标的回测，返回每日净值 DataFrame"""
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
    )
    bt.run(df, save_prefix=f"lev_{ticker.split('.')[1]}")
    daily = pd.DataFrame(bt.daily_records)[["date", "total_value"]].copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.set_index("date")
    return daily


def apply_leverage(portfolio_daily: pd.Series, leverage: float) -> dict:
    """
    将无杠杆组合净值序列转换为杠杆后的权益曲线。

    模型：固定杠杆（每日重新平衡到 leverage 倍）
      - 每日PnL = 无杠杆日收益率 × leverage × REAL_CAPITAL - 融资利息
      - 融资利息每日按 borrowed = (leverage-1) × REAL_CAPITAL 计提
      - Margin Call：累计权益跌破 borrowed × MAINT_MARGIN 时触发
    """
    borrowed       = REAL_CAPITAL * (leverage - 1)
    daily_interest = MARGIN_RATE / 252 * borrowed  # 每日利息（固定，基于初始借款）

    # 无杠杆每日收益率（去掉第一行NaN）
    daily_ret = portfolio_daily.pct_change().dropna()

    equity           = REAL_CAPITAL
    equity_curve     = [(portfolio_daily.index[0], equity)]  # 第0天：初始权益
    margin_call_date = None

    for dt, ret in daily_ret.items():
        # 复利：当日权益按杠杆放大的收益率增长，再扣固定融资利息
        equity = equity * (1 + ret * leverage) - daily_interest

        if borrowed > 0 and equity < borrowed * MAINT_MARGIN:
            margin_call_date = dt
            equity = max(equity, 0.0)
            equity_curve.append((dt, equity))
            break

        equity_curve.append((dt, equity))

    eq_series = pd.Series(dict(equity_curve))

    if eq_series.empty or len(eq_series) < 2:
        return {
            "leverage": leverage,
            "margin_call": margin_call_date,
            "ann_ret": float("-inf"),
            "max_dd": -100.0,
            "sharpe": 0.0,
            "final": 0.0,
        }

    final_v  = eq_series.iloc[-1]
    years    = (eq_series.index[-1] - eq_series.index[0]).days / 365.0
    total_ret = (final_v - REAL_CAPITAL) / REAL_CAPITAL
    ann_ret  = ((1 + total_ret) ** (1 / max(years, 0.1)) - 1) * 100

    peak     = eq_series.cummax()
    dd       = (eq_series - peak) / peak * 100
    max_dd   = round(dd.min(), 2)

    dr       = eq_series.pct_change().dropna()
    rf_d     = RISK_FREE / 252
    sharpe   = round((dr - rf_d).mean() / (dr - rf_d).std() * math.sqrt(252), 2) if dr.std() > 1e-10 else 0.0

    return {
        "leverage": leverage,
        "margin_call": margin_call_date,
        "ann_ret": round(ann_ret, 2),
        "max_dd": max_dd,
        "sharpe": sharpe,
        "final": round(final_v, 0),
        "equity": eq_series,
    }


def print_results(results: list):
    print(f"\n{'='*85}")
    print(f"  📊 铁鹰策略杠杆回测  —  配置D  QQQ+IWM+GLD  $15,000实际资本  {START[:4]}-{END[:4]}")
    print(f"  融资利率: {MARGIN_RATE*100:.1f}%/年   维持保证金: {MAINT_MARGIN*100:.0f}%")
    print(f"{'='*85}")
    hdr = f"  {'杠杆':<8} {'年化收益':>9} {'最大回撤':>10} {'夏普':>7} {'最终权益':>12} {'Margin Call':>14}"
    print(hdr)
    print("  " + "─" * 80)

    for r in results:
        lev_str   = f"{r['leverage']:.1f}x"
        ann_str   = f"{r['ann_ret']:.2f}%" if r['ann_ret'] != float('-inf') else "N/A"
        dd_str    = f"{r['max_dd']:.2f}%"
        sharpe_str = f"{r['sharpe']:.2f}"
        final_str = f"${r['final']:,.0f}" if r['final'] > 0 else "$0"
        mc_str    = str(r['margin_call'])[:10] if r['margin_call'] else "—"

        flag = " ✅" if r['leverage'] == 1.0 else (
               " ⚠️" if r['max_dd'] > -15 and not r['margin_call'] else
               " 🔴" if r['margin_call'] else
               " ⚠️")

        print(f"  {lev_str:<8} {ann_str:>9} {dd_str:>10} {sharpe_str:>7} {final_str:>12} {mc_str:>14}{flag}")

    print(f"{'='*85}")
    print(f"\n  说明：")
    print(f"  - 年化收益/最大回撤/夏普均基于实际资本 ${REAL_CAPITAL:,} 计算")
    print(f"  - 借贷成本 {MARGIN_RATE*100:.1f}%/年 已扣除")
    print(f"  - Margin Call = 权益跌破借款额 {MAINT_MARGIN*100:.0f}% 时强制平仓，权益归零\n")


def main():
    print("📥 拉取历史K线数据...")
    dfs = {}
    for asset in ASSETS:
        ticker = asset["ticker"]
        print(f"   {ticker}...", end="", flush=True)
        df = fetch_futu_kline(ticker, START, END)
        if df is None or df.empty:
            print(f" ❌ 拉取失败，退出")
            return
        dfs[ticker] = df
        print(f" ✅ {len(df)} 条")

    print("\n🔄 运行无杠杆基准回测（配置D）...")
    base_capitals = {a["ticker"]: REAL_CAPITAL * a["capital_ratio"] for a in ASSETS}
    daily_by_asset = {}
    for asset in ASSETS:
        ticker = asset["ticker"]
        print(f"   {ticker} 回测中...", end="", flush=True)
        daily = run_asset(ticker, base_capitals[ticker], asset["max_groups"], dfs[ticker])
        daily_by_asset[ticker] = daily
        print(" ✅")

    # 合并组合净值（各标的绝对净值相加）
    combined = None
    for ticker, daily in daily_by_asset.items():
        daily_renamed = daily.rename(columns={"total_value": ticker})
        combined = daily_renamed if combined is None else combined.join(daily_renamed, how="inner")

    portfolio = sum(combined[a["ticker"]] for a in ASSETS)  # 总净值

    # 无杠杆基准验证
    years_base = (portfolio.index[-1] - portfolio.index[0]).days / 365.0
    tr_base = (portfolio.iloc[-1] - REAL_CAPITAL) / REAL_CAPITAL
    ann_base = ((1 + tr_base) ** (1 / max(years_base, 0.1)) - 1) * 100
    peak_b = portfolio.cummax()
    dd_b = (portfolio - peak_b) / peak_b * 100
    dr_b = portfolio.pct_change().dropna()
    rf_d = RISK_FREE / 252
    sharpe_base = round((dr_b - rf_d).mean() / (dr_b - rf_d).std() * math.sqrt(252), 2)

    print(f"\n  基准验证：年化 {ann_base:.2f}%，最大回撤 {dd_b.min():.2f}%，夏普 {sharpe_base:.2f}")
    print(f"  （预期：年化~18.93%，回撤~-5.20%，夏普~2.34）\n")

    print("📊 计算各杠杆场景...")
    results = []
    for lev in LEVERAGE_LIST:
        r = apply_leverage(portfolio, lev)
        results.append(r)
        mc = f"margin call {r['margin_call']}" if r['margin_call'] else "无margin call"
        print(f"   {lev:.1f}x → 年化 {r['ann_ret']:.2f}%，回撤 {r['max_dd']:.2f}%，夏普 {r['sharpe']:.2f}，{mc}")

    print_results(results)


if __name__ == "__main__":
    main()
