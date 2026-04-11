#!/usr/bin/env python3
"""
样本外验证 + 参数鲁棒性测试 + 手续费冲击分析
针对 Scenario C 最优参数（P3.0%/C6.0%/W9%/DTE45）

测试维度：
  1. OOS分割验证：样本内 2010-2017 vs 样本外 2018-2025
  2. 参数鲁棒性网格：±1步调整 put_otm / call_otm / wing / dte
  3. 手续费冲击：$0 / $0.65 / $1.00 每张合约
  4. 扩展数据测试：2006-2009（含GFC 2008，覆盖VIX≥80极端场景）

用法：
  python3 oos_validation.py                  # 全部验证
  python3 oos_validation.py --oos-only       # 仅OOS分割
  python3 oos_validation.py --robust-only    # 仅鲁棒性
  python3 oos_validation.py --commission     # 仅手续费冲击
  python3 oos_validation.py --gfc            # 仅GFC扩展
  python3 oos_validation.py --workers 4      # 多进程
"""

import sys, math, io, argparse, time, itertools
from pathlib import Path
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import multiprocessing as mp

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline, historical_volatility
from composite_backtest import EnhancedICBacktester, VIX_HARD_STOP_HV, VIX_COOLDOWN_HV
from ic_param_sweep import SweepICBacktester

# ═══════════════════════════════════════════════════════════════════
#  全局参数（与实盘/sweep保持一致）
# ═══════════════════════════════════════════════════════════════════
REAL_CAPITAL  = 15_000
LEVERAGE      = 2.0
MARGIN_RATE   = 0.055
RISK_FREE     = 0.05
VIX_DELEVERAGE = 0.22    # 纯HV > 22% 降1x（与ic_param_sweep一致）

# Scenario C（最优场景）
HV_SCENE_C = {"QQQ": 0.25, "IWM": 0.25, "GLD": 0.18}

# Scenario C 最优参数（972组扫描第1名）
OPTIMAL = {"put_otm": 0.030, "call_otm": 0.060, "wing": 0.09, "dte": 45}

ASSETS = [
    {"ticker": "US.QQQ", "capital_ratio": 9/15, "max_groups": 2},
    {"ticker": "US.IWM", "capital_ratio": 3/15, "max_groups": 1},
    {"ticker": "US.GLD", "capital_ratio": 3/15, "max_groups": 1},
]

# 4条腿 × $0.65/合约（默认Futu/Schwab）
COMMISSION_CONTRACTS_PER_GROUP = 4   # 每组IC = 4张合约（每腿1张）
COMMISSION_DEFAULT = 0.65            # 每张合约美元

# ═══════════════════════════════════════════════════════════════════
#  核心运行函数（支持任意日期区间 + 手续费）
# ═══════════════════════════════════════════════════════════════════
def run_period(
    put_otm: float,
    call_otm: float,
    wing: float,
    dte: int,
    hv_scenario: dict,
    start: str,
    end: str,
    dfs: dict,
    qqq_sigmas: dict,
    commission_per_contract: float = 0.0,
    label: str = "",
) -> dict:
    """
    运行一组参数在指定区间上的回测，返回指标字典。
    commission_per_contract: 每张合约手续费（USD），默认0（兼容旧行为）
    """
    start_dt = pd.Timestamp(start)
    end_dt   = pd.Timestamp(end)

    asset_daily: Dict[str, pd.DataFrame] = {}
    trade_counts: Dict[str, int] = {}

    for asset in ASSETS:
        ticker   = asset["ticker"]
        capital  = REAL_CAPITAL * asset["capital_ratio"]
        name     = ticker.split(".")[-1]
        hv_entry = hv_scenario[name]

        # 切片到指定时间区间（fetch_futu_kline 返回 RangeIndex + 'date' 列）
        df_full = dfs.get(ticker)
        if df_full is None or df_full.empty:
            return {}
        date_series = pd.to_datetime(df_full["date"])
        mask = (date_series >= start_dt) & (date_series <= end_dt)
        df_slice = df_full[mask].reset_index(drop=True)
        if len(df_slice) < 100:
            return {}

        bt = SweepICBacktester(
            hv20_entry       = hv_entry,
            ticker           = ticker,
            initial_capital  = capital,
            otm_distance     = 0.05,
            wing_width       = wing,
            dte              = dte,
            max_groups       = asset["max_groups"],
            cooldown_days    = 5,
            stop_loss_pct    = 0.05,
            stop_loss_buffer = 1.5,
            early_close_days = 2,
            entry_mode       = "pre_expiry",
            entry_days_before_expiry = dte,
            vix_hard_stop_hv = VIX_HARD_STOP_HV,
            vix_cooldown_hv  = VIX_COOLDOWN_HV,
            put_otm          = put_otm,
            call_otm         = call_otm,
        )

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            bt.run(df_slice, save_prefix="oos_tmp")
        except Exception:
            sys.stdout = old_stdout
            return {}
        finally:
            sys.stdout = old_stdout

        daily = pd.DataFrame(bt.daily_records)[["date", "total_value"]].copy()
        daily["date"] = pd.to_datetime(daily["date"])
        daily = daily.set_index("date")
        asset_daily[ticker] = daily

        # 统计手续费所需的成交次数（len(bt.trades) = 关闭的IC组数）
        trade_counts[ticker] = len(bt.trades)

    # ── 合并组合 ──────────────────────────────────────────────
    combined = None
    for asset in ASSETS:
        t = asset["ticker"]
        if t not in asset_daily:
            return {}
        renamed = asset_daily[t].rename(columns={"total_value": t})
        combined = renamed if combined is None else combined.join(renamed, how="inner")

    if combined is None or combined.empty:
        return {}

    ic_portfolio = sum(combined[a["ticker"]] for a in ASSETS)

    # ── 2x 杠杆（高波自动降1x）+ 手续费 ──────────────────────
    equity     = float(REAL_CAPITAL)
    base_ret   = ic_portfolio.pct_change().fillna(0)
    eq_curve: List[Tuple] = []

    # 精确手续费：len(trades) × 4合约 × 2边 × $0.65
    total_trade_days = sum(trade_counts.values())
    total_commission = total_trade_days * COMMISSION_CONTRACTS_PER_GROUP * 2 * commission_per_contract

    # 按交易日平摊手续费（避免一次性冲击）
    n_days       = len(base_ret)
    daily_comm   = total_commission / max(n_days, 1)

    for dt, ret in base_ret.items():
        d = dt.date() if hasattr(dt, "date") else dt
        sigma_today = qqq_sigmas.get(d, 0.20)
        eff_lev     = 1.0 if sigma_today > VIX_DELEVERAGE else LEVERAGE
        eff_borrow  = REAL_CAPITAL * max(eff_lev - 1.0, 0.0)
        eff_int     = MARGIN_RATE / 252 * eff_borrow
        equity      = equity * (1.0 + float(ret) * eff_lev) - eff_int - daily_comm
        equity      = max(equity, 0.0)
        eq_curve.append((dt, equity))

    eq = pd.Series(dict(eq_curve))
    if len(eq) < 50:
        return {}

    # ── 统计指标 ──────────────────────────────────────────────
    years   = (eq.index[-1] - eq.index[0]).days / 365.0
    tot_ret = (eq.iloc[-1] - REAL_CAPITAL) / REAL_CAPITAL * 100
    ann_ret = ((1 + tot_ret / 100) ** (1 / max(years, 0.1)) - 1) * 100

    peak   = eq.cummax()
    dd     = (eq - peak) / peak * 100
    max_dd = dd.min()

    dr     = eq.pct_change().dropna()
    rf_d   = RISK_FREE / 252
    sharpe = (dr - rf_d).mean() / (dr - rf_d).std() * math.sqrt(252) if dr.std() > 1e-10 else 0.0
    calmar = ann_ret / abs(max_dd) if max_dd < 0 else 0.0

    # 危机期回撤（仅包含在当前区间内的）
    eq.index = pd.to_datetime(eq.index)
    all_crises = {
        "2008GFC": ("2007-10-01", "2009-03-31"),
        "2018Q4":  ("2018-10-01", "2018-12-31"),
        "2020":    ("2020-02-15", "2020-04-30"),
        "2022":    ("2022-01-01", "2022-12-31"),
        "2025":    ("2025-03-01", "2025-06-30"),
    }
    c_dd: Dict[str, float] = {}
    for name, (cs, ce) in all_crises.items():
        seg = eq[cs:ce]
        if len(seg) >= 5:
            sp = seg.cummax()
            c_dd[name] = round(((seg - sp) / sp * 100).min(), 2)

    return {
        "label":      label or f"P{put_otm:.1%}/C{call_otm:.1%} W{wing:.0%} D{dte}",
        "period":     f"{start[:7]}~{end[:7]}",
        "years":      round(years, 1),
        "put_otm":    put_otm,
        "call_otm":   call_otm,
        "wing":       wing,
        "dte":        dte,
        "ann_ret":    round(ann_ret, 2),
        "max_dd":     round(max_dd, 2),
        "sharpe":     round(sharpe, 2),
        "calmar":     round(calmar, 2),
        "final":      round(eq.iloc[-1], 0),
        "commission_total": round(total_commission, 0),
        "n_trades":   total_trade_days,
        **{f"dd_{k}": v for k, v in c_dd.items()},
    }


def precompute_qqq_sigmas(qqq_df: pd.DataFrame, start: str, end: str) -> dict:
    """预计算给定区间的 QQQ HV20 用于杠杆控制"""
    df = qqq_df.copy()
    # fetch_futu_kline 返回 RangeIndex + 'date' 列（字符串）
    close_col = "Close" if "Close" in df.columns else "close"
    date_col  = "date"
    df[date_col] = pd.to_datetime(df[date_col])
    df = df[(df[date_col] >= pd.Timestamp(start)) & (df[date_col] <= pd.Timestamp(end))]
    closes = pd.Series(df[close_col].values, index=df[date_col].values)
    sigmas = {}
    for i in range(len(closes)):
        d = pd.Timestamp(closes.index[i]).date()
        past = closes.iloc[max(0, i-25):i+1]
        sigmas[d] = historical_volatility(past, min(20, len(past))) if len(past) >= 5 else 0.20
    return sigmas


# ═══════════════════════════════════════════════════════════════════
#  1. OOS分割验证
# ═══════════════════════════════════════════════════════════════════
def run_oos_split(dfs: dict, full_sigmas: dict, workers: int = 4) -> List[dict]:
    """
    训练期 2010-2017（8年）vs 验证期 2018-2025（8年）vs 全程 2010-2025（16年）
    使用 Scenario C 最优参数，展示 OOS 是否稳定。
    """
    print("\n" + "="*70)
    print("  🔬  OOS分割验证  |  训练 2010-2017 vs 验证 2018-2025")
    print("="*70)

    periods = [
        ("全程（完整样本）",  "2010-01-01", "2025-12-31"),
        ("训练集 2010-2017",  "2010-01-01", "2017-12-31"),
        ("验证集 2018-2025",  "2018-01-01", "2025-12-31"),
    ]

    results = []
    for lbl, s, e in periods:
        print(f"\n  [{lbl}] {s} ~ {e}...", flush=True)
        # 根据区间切片sigma
        period_sigmas = {k: v for k, v in full_sigmas.items()
                         if pd.Timestamp(s).date() <= k <= pd.Timestamp(e).date()}
        r = run_period(
            **OPTIMAL,
            hv_scenario=HV_SCENE_C,
            start=s, end=e,
            dfs=dfs, qqq_sigmas=period_sigmas,
            commission_per_contract=0.0,   # 先不含手续费，单独比较
            label=lbl,
        )
        if r:
            results.append(r)
            print(f"     年化={r['ann_ret']:+.2f}%  回撤={r['max_dd']:.2f}%  "
                  f"夏普={r['sharpe']:.2f}  Calmar={r['calmar']:.2f}  期末=${r['final']:,.0f}")
        else:
            print("     ⚠️  无结果")

    return results


# ═══════════════════════════════════════════════════════════════════
#  2. 参数鲁棒性网格
# ═══════════════════════════════════════════════════════════════════
ROBUSTNESS_GRID = {
    "put_otm":  [0.025, 0.030, 0.035, 0.040],
    "call_otm": [0.050, 0.060, 0.075, 0.090],
    "wing":     [0.07, 0.08, 0.09],
    "dte":      [30, 45],
}


def _run_robust_combo(args):
    put_otm, call_otm, wing, dte, dfs, sigmas = args
    return run_period(
        put_otm=put_otm, call_otm=call_otm, wing=wing, dte=dte,
        hv_scenario=HV_SCENE_C,
        start="2010-01-01", end="2025-12-31",
        dfs=dfs, qqq_sigmas=sigmas,
        commission_per_contract=0.65,
        label=f"P{put_otm:.1%}/C{call_otm:.1%} W{wing:.0%} D{dte}",
    )


def run_robustness(dfs: dict, sigmas: dict, workers: int = 4) -> List[dict]:
    """
    ±1步调整各维度，验证最优点附近是否平坦（无断崖）。
    所有组合均含 $0.65/合约手续费。
    """
    print("\n" + "="*70)
    print("  🔬  参数鲁棒性网格（Scenario C，含$0.65手续费）")
    print("="*70)

    combos = list(itertools.product(
        ROBUSTNESS_GRID["put_otm"],
        ROBUSTNESS_GRID["call_otm"],
        ROBUSTNESS_GRID["wing"],
        ROBUSTNESS_GRID["dte"],
    ))
    n = len(combos)
    print(f"  共 {n} 组参数组合...", flush=True)

    task_args = [(p, c, w, d, dfs, sigmas) for p, c, w, d in combos]

    results = []
    t0 = time.time()
    if workers > 1:
        ctx = mp.get_context("spawn")
        with ctx.Pool(workers) as pool:
            for i, r in enumerate(pool.imap_unordered(_run_robust_combo, task_args), 1):
                elapsed = time.time() - t0
                eta = elapsed / i * (n - i)
                print(f"\r  进度: {i:3d}/{n}  耗时: {elapsed:.0f}s  预计剩余: {eta:.0f}s",
                      end="", flush=True)
                if r:
                    results.append(r)
    else:
        for i, args in enumerate(task_args, 1):
            r = _run_robust_combo(args)
            elapsed = time.time() - t0
            eta = elapsed / i * (n - i)
            print(f"\r  进度: {i:3d}/{n}  耗时: {elapsed:.0f}s  预计剩余: {eta:.0f}s",
                  end="", flush=True)
            if r:
                results.append(r)

    print(f"\n  ✅ 完成 {len(results)} 组")
    return results


# ═══════════════════════════════════════════════════════════════════
#  3. 手续费冲击
# ═══════════════════════════════════════════════════════════════════
def run_commission_sensitivity(dfs: dict, sigmas: dict) -> List[dict]:
    """
    相同参数，对比 $0 / $0.65 / $1.00 / $1.50 每张合约手续费的影响。
    """
    print("\n" + "="*70)
    print("  🔬  手续费冲击分析（Scenario C 最优参数）")
    print("="*70)

    scenarios = [
        (0.00,  "无手续费（当前回测）"),
        (0.65,  "$0.65/合约（Futu/Schwab标准）"),
        (1.00,  "$1.00/合约（IB高频层级）"),
        (1.50,  "$1.50/合约（保守估计）"),
    ]

    results = []
    for fee, lbl in scenarios:
        print(f"  [{lbl}]...", flush=True)
        r = run_period(
            **OPTIMAL,
            hv_scenario=HV_SCENE_C,
            start="2010-01-01", end="2025-12-31",
            dfs=dfs, qqq_sigmas=sigmas,
            commission_per_contract=fee,
            label=lbl,
        )
        if r:
            results.append(r)
            print(f"     年化={r['ann_ret']:+.2f}%  回撤={r['max_dd']:.2f}%  "
                  f"夏普={r['sharpe']:.2f}  手续费总计=${r['commission_total']:,.0f}  "
                  f"成交组数={r['n_trades']}")

    return results


# ═══════════════════════════════════════════════════════════════════
#  4. 扩展数据 — 含GFC 2006-2009
# ═══════════════════════════════════════════════════════════════════
def run_gfc_extension(workers: int = 4) -> Optional[List[dict]]:
    """
    尝试从2006年拉取历史数据，覆盖GFC（2008，VIX最高89）。
    如果数据不足则跳过。
    """
    print("\n" + "="*70)
    print("  🔬  GFC扩展测试  |  尝试拉取2006-2009数据")
    print("="*70)

    GFC_START = "2006-01-01"
    GFC_END   = "2009-12-31"

    dfs_gfc = {}
    for a in ASSETS:
        ticker = a["ticker"]
        print(f"  拉取 {ticker} ({GFC_START}~{GFC_END})...", flush=True)
        df = fetch_futu_kline(ticker, GFC_START, GFC_END)
        if df is None or df.empty or len(df) < 200:
            print(f"  ⚠️  {ticker} 数据不足（{len(df) if df is not None else 0}条），跳过GFC测试")
            return None
        print(f"  ✅ {ticker}: {len(df)}条 ({df.index[0]} ~ {df.index[-1]})")
        dfs_gfc[ticker] = df

    qqq_df = dfs_gfc["US.QQQ"]
    gfc_sigmas = precompute_qqq_sigmas(qqq_df, GFC_START, GFC_END)

    results = []
    sub_periods = [
        ("GFC全程 2006-2009", GFC_START, GFC_END),
        ("GFC峰值 2008",      "2008-01-01", "2008-12-31"),
        ("GFC高峰 2008Q4",    "2008-10-01", "2008-12-31"),
        ("GFC后 2009",        "2009-01-01", "2009-12-31"),
    ]

    for lbl, s, e in sub_periods:
        print(f"\n  [{lbl}] {s} ~ {e}...", flush=True)
        r = run_period(
            **OPTIMAL,
            hv_scenario=HV_SCENE_C,
            start=s, end=e,
            dfs=dfs_gfc,
            qqq_sigmas={k: v for k, v in gfc_sigmas.items()
                        if pd.Timestamp(s).date() <= k <= pd.Timestamp(e).date()},
            commission_per_contract=0.65,
            label=lbl,
        )
        if r:
            results.append(r)
            print(f"     年化={r['ann_ret']:+.2f}%  回撤={r['max_dd']:.2f}%  "
                  f"夏普={r['sharpe']:.2f}  期末=${r['final']:,.0f}")

    return results


# ═══════════════════════════════════════════════════════════════════
#  打印汇总表
# ═══════════════════════════════════════════════════════════════════
def print_oos_table(results: List[dict]):
    if not results:
        return
    print(f"\n  {'标签':<30} {'区间':>14} {'年化':>8} {'回撤':>8} {'夏普':>6} "
          f"{'Calmar':>7} {'期末':>12}")
    print("  " + "─" * 92)
    for r in results:
        lbl   = r.get("label", "")[:30]
        per   = r.get("period", "")
        an    = r.get("ann_ret", 0)
        dd    = r.get("max_dd", 0)
        sh    = r.get("sharpe", 0)
        ca    = r.get("calmar", 0)
        fin   = r.get("final", 0)
        ok    = " ✅" if sh >= 2.0 and ca >= 3.0 else (" ⚠️ " if sh >= 1.5 else " ❌")
        print(f"  {lbl:<30} {per:>14} {an:>+7.2f}% {dd:>7.2f}% {sh:>6.2f} {ca:>7.2f} "
              f"${fin:>10,.0f}{ok}")


def print_robustness_table(results: List[dict], top_n: int = 20):
    if not results:
        return
    df = pd.DataFrame(results)
    df = df.dropna(subset=["sharpe", "ann_ret"]).sort_values("sharpe", ascending=False)

    print(f"\n  ── 鲁棒性网格 Top {top_n}（含$0.65手续费，按夏普排序）──")
    print(f"  {'参数':<28} {'年化':>8} {'回撤':>8} {'夏普':>6} {'Calmar':>7} {'期末':>12}")
    print("  " + "─" * 80)
    for _, row in df.head(top_n).iterrows():
        opt_marker = " ← 最优" if (
            abs(row["put_otm"] - OPTIMAL["put_otm"]) < 0.001 and
            abs(row["call_otm"] - OPTIMAL["call_otm"]) < 0.001 and
            abs(row["wing"] - OPTIMAL["wing"]) < 0.001 and
            row["dte"] == OPTIMAL["dte"]
        ) else ""
        print(f"  {row['label']:<28} {row['ann_ret']:>+7.2f}% {row['max_dd']:>7.2f}% "
              f"{row['sharpe']:>6.2f} {row['calmar']:>7.2f} ${row['final']:>10,.0f}{opt_marker}")

    # 断崖检测：最优参数 vs ±1步邻居
    print(f"\n  ── 最优点邻域分析（夏普范围：是否有断崖？）──")
    opt_sharpe = df[
        (abs(df["put_otm"] - OPTIMAL["put_otm"]) < 0.001) &
        (abs(df["call_otm"] - OPTIMAL["call_otm"]) < 0.001) &
        (abs(df["wing"] - OPTIMAL["wing"]) < 0.001) &
        (df["dte"] == OPTIMAL["dte"])
    ]["sharpe"].values
    opt_sh = opt_sharpe[0] if len(opt_sharpe) > 0 else 0

    print(f"  最优参数夏普: {opt_sh:.2f}")
    for dim, vals in [("put_otm", ROBUSTNESS_GRID["put_otm"]),
                      ("call_otm", ROBUSTNESS_GRID["call_otm"]),
                      ("wing", ROBUSTNESS_GRID["wing"]),
                      ("dte", ROBUSTNESS_GRID["dte"])]:
        neighbors = []
        for v in vals:
            mask = pd.Series([True] * len(df))
            for d2, ov in [("put_otm", OPTIMAL["put_otm"]), ("call_otm", OPTIMAL["call_otm"]),
                            ("wing", OPTIMAL["wing"]), ("dte", OPTIMAL["dte"])]:
                if d2 == dim:
                    mask &= (abs(df[d2] - v) < 0.001) if isinstance(v, float) else (df[d2] == v)
                else:
                    mask &= (abs(df[d2] - ov) < 0.001) if isinstance(ov, float) else (df[d2] == ov)
            sub = df[mask]
            if not sub.empty:
                sh_val = sub["sharpe"].values[0]
                an_val = sub["ann_ret"].values[0]
                neighbors.append(f"{v:.1%}→夏普{sh_val:.2f}" if isinstance(v, float)
                                  else f"D{v}→夏普{sh_val:.2f}")
        print(f"  {dim:12s}: " + "  |  ".join(neighbors))


def print_commission_table(results: List[dict]):
    if not results:
        return
    base = results[0]
    print(f"\n  {'手续费场景':<30} {'年化':>8} {'夏普':>6} {'Calmar':>7} {'年化影响':>10} "
          f"{'总手续费':>12} {'成交组数':>8}")
    print("  " + "─" * 90)
    for r in results:
        delta = r["ann_ret"] - base["ann_ret"]
        print(f"  {r['label']:<30} {r['ann_ret']:>+7.2f}% {r['sharpe']:>6.2f} "
              f"{r['calmar']:>7.2f} {delta:>+9.2f}% ${r['commission_total']:>10,.0f} "
              f"{r['n_trades']:>8d}")


# ═══════════════════════════════════════════════════════════════════
#  主程序
# ═══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oos-only",        action="store_true")
    parser.add_argument("--robust-only",     action="store_true")
    parser.add_argument("--commission",      action="store_true")
    parser.add_argument("--gfc",             action="store_true")
    parser.add_argument("--workers",         type=int, default=4)
    args = parser.parse_args()

    run_all = not any([args.oos_only, args.robust_only, args.commission, args.gfc])

    print("=" * 70)
    print("  📐  OOS验证 / 鲁棒性 / 手续费  |  Scenario C 最优参数")
    print(f"  最优参数: P{OPTIMAL['put_otm']:.1%}/C{OPTIMAL['call_otm']:.1%} "
          f"W{OPTIMAL['wing']:.0%} DTE{OPTIMAL['dte']}")
    print(f"  HV阈值: QQQ/IWM≤{HV_SCENE_C['QQQ']:.0%}  GLD≤{HV_SCENE_C['GLD']:.0%}  "
          f"(Scenario C，纯HV口径)")
    print("=" * 70)

    # ── 拉取历史K线（2010-2025）────────────────────────────────
    print("\n📥 拉取历史K线（2010-01-01 → 2025-12-31）...")
    dfs = {}
    for a in ASSETS:
        t = a["ticker"]
        print(f"   {t}...", end="", flush=True)
        df = fetch_futu_kline(t, "2010-01-01", "2025-12-31")
        if df is None or df.empty:
            print(f" ❌ 失败，退出")
            sys.exit(1)
        dfs[t] = df
        print(f" ✅ {len(df)}条")

    # 预计算 QQQ HV20 sigma
    print("\n📐 预计算 QQQ HV20 sigma...", end="", flush=True)
    qqq_df = dfs["US.QQQ"]
    full_sigmas = precompute_qqq_sigmas(qqq_df, "2010-01-01", "2025-12-31")
    print(f" ✅ {len(full_sigmas)}天")

    # ── 1. OOS分割 ──────────────────────────────────────────────
    if run_all or args.oos_only:
        oos_results = run_oos_split(dfs, full_sigmas, workers=args.workers)
        print("\n\n" + "="*70)
        print("  📊  OOS分割验证结果汇总")
        print("="*70)
        print("  判断标准: OOS验证集夏普≥2.0、Calmar≥3.0 → 策略具备OOS稳定性")
        print_oos_table(oos_results)

        # OOS一致性判断
        oos_r = [r for r in oos_results if "2018" in r.get("period", "")]
        if oos_r:
            r = oos_r[0]
            if r["sharpe"] >= 2.0 and r["calmar"] >= 3.0:
                print(f"\n  ✅ OOS验证通过：夏普={r['sharpe']:.2f}≥2.0，Calmar={r['calmar']:.2f}≥3.0")
            elif r["sharpe"] >= 1.5:
                print(f"\n  ⚠️  OOS表现尚可但需注意：夏普={r['sharpe']:.2f}（目标≥2.0）")
            else:
                print(f"\n  ❌ OOS验证未通过：夏普={r['sharpe']:.2f}<1.5，存在过拟合风险")

    # ── 2. 鲁棒性网格 ────────────────────────────────────────────
    if run_all or args.robust_only:
        robust_results = run_robustness(dfs, full_sigmas, workers=args.workers)
        print_robustness_table(robust_results)

    # ── 3. 手续费冲击 ────────────────────────────────────────────
    if run_all or args.commission:
        comm_results = run_commission_sensitivity(dfs, full_sigmas)
        print("\n\n" + "="*70)
        print("  📊  手续费冲击分析结果")
        print("="*70)
        print_commission_table(comm_results)

    # ── 4. GFC扩展 ────────────────────────────────────────────────
    if run_all or args.gfc:
        gfc_results = run_gfc_extension(workers=args.workers)
        if gfc_results:
            print("\n\n" + "="*70)
            print("  📊  GFC扩展测试结果（含VIX≥80极端场景）")
            print("="*70)
            print_oos_table(gfc_results)
        else:
            print("\n  ⚠️  GFC数据不足，建议手动验证2008年极端行情下的策略表现")

    print("\n" + "="*70)
    print("  验证完成")
    print("="*70)


if __name__ == "__main__":
    main()
