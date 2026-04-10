#!/usr/bin/env python3
"""
非对称铁鹰参数全扫描  QQQ+IWM+GLD  2x杠杆
═══════════════════════════════════════════════
基准：P3.5%/C7.5%  Wing=8%  DTE=30

扫描维度：
  put_otm    : 2.5% / 3.0% / 3.5% / 4.0% / 4.5% / 5.0%
  call_otm   : 5.0% / 6.0% / 7.5% / 9.0% / 10.0% / 12.0%
  wing_width : 7% / 8% / 9%
  dte        : 21 / 30 / 45

固定风控（与实盘一致）：
  HV20入场阈值: QQQ/IWM≤25%  GLD≤18%
  VIX硬止损  : HV20≥45% 强平，< 32% 恢复
  杠杆调节   : HV20>25% 时自动降为1x（降低高波风险）
  止损缓冲   : 1.5x Wing
  早平       : 到期前2天
  冷却期     : 5天

资金：
  实际资本 $15,000  ×  2.0x杠杆  =  名义 $30,000
  融资利率 5.5%/年（富途）

用法：
  python3 ic_param_sweep.py
  python3 ic_param_sweep.py --quick   # 仅扫描 OTM（固定 Wing=8% DTE=30）
  python3 ic_param_sweep.py --workers 4  # 多进程加速
"""

import sys, math, io, os, argparse, time, itertools
from pathlib import Path
from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional
import multiprocessing as mp

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline, historical_volatility
from composite_backtest import EnhancedICBacktester, VIX_HARD_STOP_HV, VIX_COOLDOWN_HV
from iron_condor_us import get_us_option_expiries, get_next_expiry

# ═══════════════════════════════════════════════════════
#  全局参数
# ═══════════════════════════════════════════════════════
REAL_CAPITAL     = 15_000
LEVERAGE         = 2.0
MARGIN_RATE      = 0.055          # 融资年利率
RISK_FREE        = 0.05
START, END       = "2010-01-01", "2025-12-31"
VIX_DELEVERAGE   = 0.25           # HV20 > 25% 时降为1x杠杆

ASSETS = [
    {"ticker": "US.QQQ", "capital_ratio": 9/15, "max_groups": 2, "hv20_entry": 0.25},
    {"ticker": "US.IWM", "capital_ratio": 3/15, "max_groups": 1, "hv20_entry": 0.25},
    {"ticker": "US.GLD", "capital_ratio": 3/15, "max_groups": 1, "hv20_entry": 0.18},
]

# 基准参数（用于标注）
BASELINE = {"put_otm": 0.035, "call_otm": 0.075, "wing": 0.08, "dte": 30}

# ═══════════════════════════════════════════════════════
#  扫描网格
# ═══════════════════════════════════════════════════════
FULL_GRID = {
    "put_otm":  [0.025, 0.030, 0.035, 0.040, 0.045, 0.050],
    "call_otm": [0.050, 0.060, 0.075, 0.090, 0.100, 0.120],
    "wing":     [0.07, 0.08, 0.09],
    "dte":      [21, 30, 45],
}

# quick模式：仅扫描 OTM，固定 Wing=8% DTE=30
QUICK_GRID = {
    "put_otm":  [0.025, 0.030, 0.035, 0.040, 0.045, 0.050],
    "call_otm": [0.050, 0.060, 0.075, 0.090, 0.100, 0.120],
    "wing":     [0.08],
    "dte":      [30],
}


# ═══════════════════════════════════════════════════════
#  带HV20入场过滤的回测器（继承 EnhancedICBacktester）
# ═══════════════════════════════════════════════════════
class SweepICBacktester(EnhancedICBacktester):
    """在 EnhancedICBacktester 基础上增加 HV20 入场阈值过滤"""

    def __init__(self, hv20_entry: float = 0.25, **kwargs):
        self._hv20_entry = hv20_entry
        super().__init__(**kwargs)

    def get_dynamic_params(self, sigma: float) -> dict:
        """优先检查 HV20 入场阈值，再走父类逻辑"""
        if sigma >= self._hv20_entry:
            return {
                "otm": self.otm_distance, "wing": self.wing_width,
                "skip": True,
                "reason": f"HV20={sigma:.1%} >= 入场阈值 {self._hv20_entry:.0%}，暂停开仓",
            }
        return super().get_dynamic_params(sigma)


# ═══════════════════════════════════════════════════════
#  单组合回测
# ═══════════════════════════════════════════════════════
def run_combo(args) -> dict:
    """
    运行一组参数，返回指标字典。
    args = (put_otm, call_otm, wing, dte, dfs, qqq_sigmas)
    """
    put_otm, call_otm, wing, dte, dfs, qqq_sigmas = args

    asset_daily: Dict[str, pd.DataFrame] = {}

    for asset in ASSETS:
        ticker   = asset["ticker"]
        capital  = REAL_CAPITAL * asset["capital_ratio"]
        hv_entry = asset["hv20_entry"]

        bt = SweepICBacktester(
            hv20_entry       = hv_entry,
            ticker           = ticker,
            initial_capital  = capital,
            otm_distance     = 0.05,               # fallback（不在非对称模式中生效）
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

        # 压制 verbose 输出
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            bt.run(dfs[ticker], save_prefix="sweep_tmp")
        finally:
            sys.stdout = old_stdout

        daily = pd.DataFrame(bt.daily_records)[["date", "total_value"]].copy()
        daily["date"] = pd.to_datetime(daily["date"])
        daily = daily.set_index("date")
        asset_daily[ticker] = daily

    # ── 合并组合 ──────────────────────────────────────────────
    combined = None
    for asset in ASSETS:
        t = asset["ticker"]
        renamed = asset_daily[t].rename(columns={"total_value": t})
        combined = renamed if combined is None else combined.join(renamed, how="inner")

    if combined is None or combined.empty:
        return {}

    ic_portfolio = sum(combined[a["ticker"]] for a in ASSETS)

    # ── 应用 2x 杠杆（高波自动降 1x）────────────────────────
    equity      = float(REAL_CAPITAL)
    base_ret    = ic_portfolio.pct_change().fillna(0)
    eq_curve: List[Tuple] = []

    for dt, ret in base_ret.items():
        d = dt.date() if hasattr(dt, "date") else dt
        sigma_today = qqq_sigmas.get(d, 0.20)

        eff_lev     = 1.0 if sigma_today > VIX_DELEVERAGE else LEVERAGE
        eff_borrow  = REAL_CAPITAL * max(eff_lev - 1.0, 0.0)
        eff_int     = MARGIN_RATE / 252 * eff_borrow

        equity = equity * (1.0 + float(ret) * eff_lev) - eff_int
        equity = max(equity, 0.0)
        eq_curve.append((dt, equity))

    eq = pd.Series(dict(eq_curve))
    if len(eq) < 100:
        return {}

    # ── 统计指标 ──────────────────────────────────────────────
    years    = (eq.index[-1] - eq.index[0]).days / 365.0
    tot_ret  = (eq.iloc[-1] - REAL_CAPITAL) / REAL_CAPITAL * 100
    ann_ret  = ((1 + tot_ret / 100) ** (1 / max(years, 0.1)) - 1) * 100

    peak   = eq.cummax()
    dd     = (eq - peak) / peak * 100
    max_dd = dd.min()

    dr     = eq.pct_change().dropna()
    rf_d   = RISK_FREE / 252
    sharpe = (dr - rf_d).mean() / (dr - rf_d).std() * math.sqrt(252) if dr.std() > 1e-10 else 0.0

    calmar = ann_ret / abs(max_dd) if max_dd < 0 else 0.0

    # ── 危机期回撤 ────────────────────────────────────────────
    eq.index = pd.to_datetime(eq.index)
    crises = {
        "2018Q4": ("2018-10-01", "2018-12-31"),
        "2020":   ("2020-02-15", "2020-04-30"),
        "2022":   ("2022-01-01", "2022-12-31"),
        "2025":   ("2025-03-01", "2025-06-30"),
    }
    c_dd: Dict[str, float] = {}
    for name, (cs, ce) in crises.items():
        seg = eq[cs:ce]
        if len(seg) >= 5:
            sp  = seg.cummax()
            c_dd[name] = round(((seg - sp) / sp * 100).min(), 2)

    return {
        "put_otm":  put_otm,
        "call_otm": call_otm,
        "wing":     wing,
        "dte":      dte,
        "ann_ret":  round(ann_ret, 2),
        "max_dd":   round(max_dd, 2),
        "sharpe":   round(sharpe, 2),
        "calmar":   round(calmar, 2),
        "final":    round(eq.iloc[-1], 0),
        **{f"dd_{k}": v for k, v in c_dd.items()},
    }


# ═══════════════════════════════════════════════════════
#  打印结果
# ═══════════════════════════════════════════════════════
def print_results(results: List[dict], top_n: int = 30):
    if not results:
        print("无结果")
        return

    df = pd.DataFrame(results)
    df = df.dropna(subset=["sharpe", "ann_ret", "max_dd"])

    # 标记基准
    def is_baseline(r):
        return (abs(r["put_otm"] - BASELINE["put_otm"]) < 1e-4 and
                abs(r["call_otm"] - BASELINE["call_otm"]) < 1e-4 and
                abs(r["wing"]     - BASELINE["wing"])     < 1e-4 and
                r["dte"] == BASELINE["dte"])

    df["is_baseline"] = df.apply(is_baseline, axis=1)

    # 综合得分（Sharpe 40% + 年化 40% + 回撤 20%）
    # 年化标准化到 ~[0,1] 用 /25；回撤惩罚
    df["score"] = (0.40 * df["sharpe"] / 3.0 +
                   0.40 * df["ann_ret"] / 25.0 +
                   0.20 * (1.0 + df["max_dd"] / 10.0))

    df_sorted = df.sort_values("sharpe", ascending=False).reset_index(drop=True)

    # ── 表头 ────────────────────────────────────────────────
    crisis_cols = [c for c in df.columns if c.startswith("dd_")]
    crisis_names = [c.replace("dd_", "") for c in crisis_cols]

    hdr = (f"  {'标记':<4}  {'P-OTM':>6} {'C-OTM':>6} {'Wing':>5} {'DTE':>4}"
           f"  {'年化收益':>8} {'最大回撤':>9} {'夏普':>6} {'Calmar':>7} {'期末':>10}")
    for cn in crisis_names:
        hdr += f"  {cn:>8}"

    sep = "  " + "─" * (len(hdr) - 2)

    print(f"\n{'='*90}")
    print(f"  🏆  非对称铁鹰参数扫描结果  （QQQ+IWM+GLD  2x杠杆  2010-2025）")
    print(f"  基准：P3.5%/C7.5%  Wing=8%  DTE=30  |  共 {len(df)} 组")
    print(f"{'='*90}")
    print(f"\n  按夏普比率排序（Top {min(top_n, len(df_sorted))}）：")
    print(hdr)
    print(sep)

    shown = 0
    baseline_printed = False
    for _, r in df_sorted.iterrows():
        if shown >= top_n and not (r["is_baseline"] and not baseline_printed):
            if r["is_baseline"] and not baseline_printed:
                pass
            else:
                continue
        if r["is_baseline"]:
            baseline_printed = True
            marker = "★基准"
        else:
            marker = f"#{shown+1:3d}"

        row = (f"  {marker:<4}  "
               f"{r['put_otm']:>5.1%} {r['call_otm']:>6.1%} {r['wing']:>5.0%} {r['dte']:>4.0f}"
               f"  {r['ann_ret']:>7.2f}% {r['max_dd']:>8.2f}% {r['sharpe']:>6.2f}"
               f"  {r['calmar']:>7.2f}  ${r['final']:>9,.0f}")
        for cn in crisis_cols:
            v = r.get(cn, float("nan"))
            row += f"  {v:>8.2f}%" if not math.isnan(v) else f"  {'N/A':>8}"
        print(row)
        shown += 1

    # 基准若未在 top_n 内输出，补充打印
    if not baseline_printed:
        brow = df_sorted[df_sorted["is_baseline"]]
        if not brow.empty:
            r = brow.iloc[0]
            rank = df_sorted.index[df_sorted["is_baseline"]].tolist()[0] + 1
            print(sep)
            row = (f"  {'★基准':<4}  "
                   f"{r['put_otm']:>5.1%} {r['call_otm']:>6.1%} {r['wing']:>5.0%} {r['dte']:>4.0f}"
                   f"  {r['ann_ret']:>7.2f}% {r['max_dd']:>8.2f}% {r['sharpe']:>6.2f}"
                   f"  {r['calmar']:>7.2f}  ${r['final']:>9,.0f}")
            for cn in crisis_cols:
                v = r.get(cn, float("nan"))
                row += f"  {v:>8.2f}%" if not math.isnan(v) else f"  {'N/A':>8}"
            row += f"  (全局排名第 {rank} / {len(df)})"
            print(row)

    # ── Top5 分项对比 ────────────────────────────────────────
    print(f"\n\n{'='*90}")
    print(f"  📊  Top 5 vs 基准  详细对比")
    print(f"{'='*90}")
    top5_idx = df_sorted[~df_sorted["is_baseline"]].head(5).index.tolist()
    if df_sorted["is_baseline"].any():
        base_idx = df_sorted[df_sorted["is_baseline"]].index[0]
        top5_idx = [base_idx] + top5_idx

    metrics = ["ann_ret", "max_dd", "sharpe", "calmar"] + crisis_cols
    metric_labels = {
        "ann_ret": "年化收益",
        "max_dd":  "最大回撤",
        "sharpe":  "夏普比率",
        "calmar":  "Calmar",
        **{c: c.replace("dd_", "危机") for c in crisis_cols},
    }
    fmt = {
        "ann_ret": "{:>+8.2f}%",
        "max_dd":  "{:>8.2f}%",
        "sharpe":  "{:>8.2f}",
        "calmar":  "{:>8.2f}",
        **{c: "{:>8.2f}%" for c in crisis_cols},
    }

    # 列头
    col_w = 18
    header = f"  {'指标':<12}"
    for idx in top5_idx:
        r = df_sorted.loc[idx]
        tag = "基准" if r["is_baseline"] else f"P{r['put_otm']:.1%}/C{r['call_otm']:.1%}"
        col_label = f"{tag} W{r['wing']:.0%} D{r['dte']:.0f}"
        header += f"  {col_label:>{col_w}}"
    print(header)
    print("  " + "─" * (14 + (col_w + 2) * len(top5_idx)))

    for m in metrics:
        row = f"  {metric_labels.get(m, m):<12}"
        for idx in top5_idx:
            r = df_sorted.loc[idx]
            v = r.get(m, float("nan"))
            if math.isnan(v):
                row += f"  {'N/A':>{col_w}}"
            else:
                try:
                    row += f"  {fmt[m].format(v):>{col_w}}"
                except Exception:
                    row += f"  {v:>{col_w}.2f}"
        print(row)

    # ── 最优推荐 ────────────────────────────────────────────
    best = df_sorted.iloc[0]
    print(f"\n\n{'='*90}")
    print(f"  🥇  综合最优推荐")
    print(f"{'='*90}")
    b_tag = "（即当前基准）" if best["is_baseline"] else ""
    print(f"  Put OTM  = {best['put_otm']:.1%}   Call OTM = {best['call_otm']:.1%}"
          f"   Wing = {best['wing']:.0%}   DTE = {best['dte']:.0f}  {b_tag}")
    print(f"  年化收益 {best['ann_ret']:+.2f}%  |  最大回撤 {best['max_dd']:.2f}%"
          f"  |  夏普 {best['sharpe']:.2f}  |  Calmar {best['calmar']:.2f}")
    print(f"  $15k 期末 → ${best['final']:,.0f}  （2010-2025，16年）")

    # 与基准差值
    base_rows = df[df["is_baseline"]]
    if not base_rows.empty:
        b = base_rows.iloc[0]
        print(f"\n  对比基准（P3.5%/C7.5%）：")
        print(f"    年化  {b['ann_ret']:+.2f}% → {best['ann_ret']:+.2f}%   差值 {best['ann_ret']-b['ann_ret']:+.2f}%")
        print(f"    夏普  {b['sharpe']:.2f}  → {best['sharpe']:.2f}    差值 {best['sharpe']-b['sharpe']:+.2f}")
        print(f"    回撤  {b['max_dd']:.2f}% → {best['max_dd']:.2f}%   差值 {best['max_dd']-b['max_dd']:+.2f}%")


# ═══════════════════════════════════════════════════════
#  主函数
# ═══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick",   action="store_true", help="仅扫描OTM（固定Wing=8% DTE=30）")
    parser.add_argument("--workers", type=int, default=1,  help="并行进程数（默认1，建议4-8）")
    parser.add_argument("--top",     type=int, default=30, help="显示前N名（默认30）")
    args = parser.parse_args()

    grid = QUICK_GRID if args.quick else FULL_GRID
    combos = list(itertools.product(
        grid["put_otm"], grid["call_otm"], grid["wing"], grid["dte"]
    ))
    n_total = len(combos)

    print(f"\n{'='*70}")
    print(f"  🔬  非对称铁鹰参数扫描  QQQ+IWM+GLD  2x杠杆")
    print(f"{'='*70}")
    print(f"  模式      : {'快速(仅OTM)' if args.quick else '全量扫描'}")
    print(f"  组合总数  : {n_total}")
    print(f"  并行进程  : {args.workers}")
    print(f"  基准      : P3.5%/C7.5%  Wing=8%  DTE=30")
    print(f"  资金      : ${REAL_CAPITAL:,} × {LEVERAGE}x 杠杆 = 名义${REAL_CAPITAL*LEVERAGE:,.0f}")
    print(f"  融资利率  : {MARGIN_RATE:.1%}/年  (${REAL_CAPITAL*(LEVERAGE-1)*MARGIN_RATE:,.0f}/年)")
    print(f"  回测区间  : {START} ~ {END}（16年）")

    # ── 拉取数据（仅一次）────────────────────────────────────
    print(f"\n{'─'*70}")
    print("  📥  拉取历史K线（仅一次）...")
    dfs: Dict[str, pd.DataFrame] = {}
    for asset in ASSETS:
        ticker = asset["ticker"]
        print(f"     {ticker}...", end="", flush=True)
        df = fetch_futu_kline(ticker, START, END)
        if df is None or df.empty:
            print(f" ❌ 失败，退出")
            return
        dfs[ticker] = df
        print(f" ✅ {len(df)} 条")

    # ── 预计算 QQQ sigma（用于杠杆调节）────────────────────
    print("  📐  预计算 QQQ HV20...", end="", flush=True)
    qqq_df = dfs["US.QQQ"]
    qqq_sigmas: Dict[date, float] = {}
    prices_arr = qqq_df["Close"].values
    dates_arr  = qqq_df["date"].values
    for i in range(len(prices_arr)):
        past = prices_arr[max(0, i-20): i+1]
        sigma = historical_volatility(pd.Series(past), min(20, len(past)))
        d = dates_arr[i]
        if hasattr(d, "date"):
            d = d.date()
        qqq_sigmas[d] = sigma
    print(f" ✅ {len(qqq_sigmas)} 天")

    # ── 运行扫描 ─────────────────────────────────────────────
    print(f"\n  🚀  开始扫描 {n_total} 组参数...\n")
    t0 = time.time()

    task_args = [(p, c, w, d, dfs, qqq_sigmas) for p, c, w, d in combos]

    results = []
    if args.workers > 1:
        # 多进程模式
        with mp.Pool(processes=args.workers) as pool:
            for i, r in enumerate(pool.imap_unordered(run_combo, task_args), 1):
                if r:
                    results.append(r)
                elapsed = time.time() - t0
                eta = elapsed / i * (n_total - i) if i > 0 else 0
                print(f"\r  进度: {i:4d}/{n_total}  耗时: {elapsed:.0f}s  预计剩余: {eta:.0f}s   ", end="", flush=True)
    else:
        # 单进程模式（便于调试）
        for i, task in enumerate(task_args, 1):
            r = run_combo(task)
            if r:
                results.append(r)
            elapsed = time.time() - t0
            eta = elapsed / i * (n_total - i) if i > 0 else 0
            p, c, w, d = task[0], task[1], task[2], task[3]
            print(f"\r  进度: {i:4d}/{n_total}  P{p:.1%}/C{c:.1%} W{w:.0%} D{d}"
                  f"  耗时: {elapsed:.0f}s  ETA: {eta:.0f}s   ", end="", flush=True)

    elapsed_total = time.time() - t0
    print(f"\n\n  ✅  扫描完成！{len(results)}/{n_total} 组成功  总耗时 {elapsed_total:.0f}s")

    # ── 输出结果 ─────────────────────────────────────────────
    print_results(results, top_n=args.top)


if __name__ == "__main__":
    main()
