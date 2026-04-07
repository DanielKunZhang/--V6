#!/usr/bin/env python3
"""
年化收益提升扫描 —— 使用原始回测引擎（iron_condor_us.py）
基线：G2 OTM5% Wing8% DTE30 HV≤25% → +15.95%

测试方向：
  1. 增加组数 G3/G4
  2. 更宽翼宽（10%/12%）
  3. 放宽 HV20 上限（28% / 30%）
  4. 缩短冷却期（3天）
  5. 组合最优
"""

import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backtest_real import fetch_futu_kline
from iron_condor_us import USIronCondorBacktester

CAPITAL = 15_000
TICKER  = "US.QQQ"
START, END = "2010-01-01", "2025-12-31"

# ── HV20 阈值在 USIronCondorBacktester 里是通过 dynamic_otm 控制的
# 原始引擎：HV > VIX_HIGH(0.30) 时跳过，HV 20-30% 用 OTM_MID_VOL(8%)
# 要改阈值，需要子类化或 patch，我们用 dynamic_otm=False + 在外层过滤

# 简化方法：用 monkey-patch VIX_HIGH 临时改阈值
import iron_condor_us as ic_mod

def run_bt(label, otm, wing, dte, groups, cooldown,
           vix_high_override=None, stop_loss_pct=0.05):
    """
    运行一次回测。
    vix_high_override: 修改 VIX_HIGH 阈值（None=默认0.30，但实盘用0.25）
    注意：原始引擎的 dynamic_otm=False 时，HV过滤完全禁用；
         dynamic_otm=True 时用 VIX_HIGH。
         我们直接用 dynamic_otm=False + stop_loss_pct 来控制。
    """
    # 临时 patch VIX_HIGH（动态 OTM 阈值）
    original_vix_high = ic_mod.USIronCondorBacktester.VIX_HIGH
    if vix_high_override is not None:
        ic_mod.USIronCondorBacktester.VIX_HIGH = vix_high_override

    bt = ic_mod.USIronCondorBacktester(
        ticker=TICKER,
        initial_capital=CAPITAL,
        otm_distance=otm,
        wing_width=wing,
        dte=dte,
        max_groups=groups,
        cooldown_days=cooldown,
        stop_loss_pct=stop_loss_pct,
        stop_loss_buffer=1.5,
        early_close_days=2,
        entry_mode="pre_expiry",
        entry_days_before_expiry=dte,
        dynamic_otm=(vix_high_override is not None),  # 开 dynamic_otm 才能用 VIX_HIGH
        label=label,
    )
    r = bt.run(df, save_prefix=f"boost_{label.replace(' ','_')[:30]}")

    # 恢复
    ic_mod.USIronCondorBacktester.VIX_HIGH = original_vix_high
    return r


CONFIGS = [
    # ── 基线（已知 +15.95%）──
    dict(label="A  基线  G2 W8% HV≤25%", otm=0.05, wing=0.08, dte=30, groups=2, cooldown=5),

    # ── 1. 更多组数 ──
    dict(label="B1 G3    W8% HV≤25%",    otm=0.05, wing=0.08, dte=30, groups=3, cooldown=5),
    dict(label="B2 G4    W8% HV≤25%",    otm=0.05, wing=0.08, dte=30, groups=4, cooldown=5),

    # ── 2. 更宽翼宽 ──
    dict(label="C1 G2 W10% HV≤25%",      otm=0.05, wing=0.10, dte=30, groups=2, cooldown=5),
    dict(label="C2 G2 W12% HV≤25%",      otm=0.05, wing=0.12, dte=30, groups=2, cooldown=5),
    dict(label="C3 G3 W10% HV≤25%",      otm=0.05, wing=0.10, dte=30, groups=3, cooldown=5),

    # ── 3. 放宽 HV20 上限（用 dynamic_otm 模式）──
    # dynamic_otm=True: HV<20% OTM5%W8%, HV20-VIX_HIGH: OTM8%W12%, HV>VIX_HIGH: 暂停
    # patch VIX_HIGH = 0.28 → 允许 HV 最高 28%
    dict(label="D1 G2 W8% HV≤28%",       otm=0.05, wing=0.08, dte=30, groups=2, cooldown=5,
         vix_high_override=0.28),
    dict(label="D2 G2 W8% HV≤30%",       otm=0.05, wing=0.08, dte=30, groups=2, cooldown=5,
         vix_high_override=0.30),
    dict(label="D3 G3 W8% HV≤28%",       otm=0.05, wing=0.08, dte=30, groups=3, cooldown=5,
         vix_high_override=0.28),

    # ── 4. 缩短冷却期 ──
    dict(label="E1 G2 W8% CD=3 HV≤25%",  otm=0.05, wing=0.08, dte=30, groups=2, cooldown=3),
    dict(label="E2 G3 W8% CD=3 HV≤25%",  otm=0.05, wing=0.08, dte=30, groups=3, cooldown=3),

    # ── 5. 组合 ──
    dict(label="F1 G3 W10% CD=3 HV≤25%", otm=0.05, wing=0.10, dte=30, groups=3, cooldown=3),
    dict(label="F2 G3 W10% CD=3 HV≤28%", otm=0.05, wing=0.10, dte=30, groups=3, cooldown=3,
         vix_high_override=0.28),
    dict(label="F3 G4 W10% CD=3 HV≤28%", otm=0.05, wing=0.10, dte=30, groups=4, cooldown=3,
         vix_high_override=0.28),
    dict(label="F4 G3 W12% CD=3 HV≤28%", otm=0.05, wing=0.12, dte=30, groups=3, cooldown=3,
         vix_high_override=0.28),

    # ── 6. 更激进 OTM（更靠近价格，更多权利金但风险更大）──
    dict(label="G1 OTM3% G2 W8%",         otm=0.03, wing=0.08, dte=30, groups=2, cooldown=5),
    dict(label="G2 OTM3% G3 W10%",        otm=0.03, wing=0.10, dte=30, groups=3, cooldown=5),
]


def print_table(results):
    print(f"\n\n{'='*105}")
    print(f"  📊 年化收益提升扫描  —  QQQ 2010-2025  ×  $15,000 初始资金（原始引擎）")
    print(f"{'='*105}")
    hdr = (f"  {'配置':<38}  {'年化':>8}  {'最大回撤':>9}  {'夏普':>6}  "
           f"{'开仓':>5}  {'胜率':>6}  {'均权利金':>9}  {'最终资金':>10}")
    print(hdr)
    print("  " + "─" * 100)

    base_ann = next(r["ann_return"] for r in results if r["label"].startswith("A"))

    for r in sorted(results, key=lambda x: x["ann_return"], reverse=True):
        diff = r["ann_return"] - base_ann
        marker = " ★" if diff == max(x["ann_return"] - base_ann for x in results) else "  "
        diff_s = f"(+{diff:.1f}%)" if diff > 0 else f"({diff:.1f}%)"
        print(f"{marker}{r['label']:<40}  {r['ann_return']:>+7.2f}%  "
              f"{r['max_dd']:>8.2f}%  {r['sharpe_ratio']:>6.2f}  "
              f"{r['n_open']:>4}次  {r['win_rate']:>5.0f}%  "
              f"${r['avg_credit']:>8,.0f}  ${r['final_value']:>9,.0f}  {diff_s}")

    print("  " + "─" * 100)
    base = next(r for r in results if r["label"].startswith("A"))
    print(f"  基线 A: 年化{base['ann_return']:+.2f}%  回撤{base['max_dd']:.2f}%  "
          f"夏普{base['sharpe_ratio']:.2f}  最终${base['final_value']:,.0f}")
    print(f"{'='*105}")


def print_risk_analysis(results):
    print(f"\n\n{'='*75}")
    print("  ⚠️  高收益配置风险分析（年化超过基线2%以上）")
    print(f"{'='*75}")
    base_ann = next(r["ann_return"] for r in results if r["label"].startswith("A"))
    base_dd  = next(r["max_dd"]     for r in results if r["label"].startswith("A"))

    candidates = [r for r in results if r["ann_return"] > base_ann + 2.0]
    candidates.sort(key=lambda x: x["ann_return"], reverse=True)

    for r in candidates:
        dd_change = r["max_dd"] - base_dd
        dd_flag = "🔴" if dd_change < -3 else ("🟡" if dd_change < -1 else "🟢")
        print(f"\n  {r['label']}")
        print(f"    年化: {r['ann_return']:+.2f}%  vs 基线 {base_ann:+.2f}%  → 超额 +{r['ann_return']-base_ann:.1f}%")
        print(f"    最大回撤: {r['max_dd']:.2f}%  vs 基线 {base_dd:.2f}%  {dd_flag}")
        print(f"    夏普: {r['sharpe_ratio']:.2f}  开仓: {r['n_open']}次  胜率: {r['win_rate']:.0f}%")

        # 保证金估算
        # 每组保证金 ≈ (sell_put - buy_put) × 100 × 0.5 ≈ wing × price × 100 × 0.5
        # 但简单估算：每组保证金约 $3000-$4000（QQQ @$400-600, wing 8%）
        margin_per_group = 2500  # 保守估算
        total_margin = margin_per_group * r.get("max_groups", 2)
        print(f"    保证金估算: ~${total_margin:,} / $15,000 = {total_margin/15000*100:.0f}% 资金占用")


if __name__ == "__main__":
    print("=" * 75)
    print("  🚀 年化收益提升扫描")
    print("  使用原始回测引擎（iron_condor_us.py）")
    print("=" * 75)

    df = fetch_futu_kline(TICKER, START, END)
    if df is None or df.empty:
        print("❌ 无法获取数据")
        sys.exit(1)
    print(f"✅ 数据: {len(df)} 天  {df['date'].iloc[0]} → {df['date'].iloc[-1]}\n")

    results = []
    for i, cfg in enumerate(CONFIGS):
        vix_override = cfg.pop("vix_high_override", None)
        r = run_bt(**cfg, vix_high_override=vix_override)
        r["max_groups"] = cfg["groups"]  # 保存组数供后续分析
        results.append(r)
        print(f"  [{i+1}/{len(CONFIGS)}] {r['label']:<40} 年化{r['ann_return']:>+7.2f}%  回撤{r['max_dd']:>7.2f}%")

    print_table(results)
    print_risk_analysis(results)

    out = Path(__file__).parent / "backtest_results" / "return_boost.json"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)
    print(f"\n📁 结果已保存: {out}")
