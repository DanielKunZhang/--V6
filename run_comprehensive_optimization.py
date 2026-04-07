#!/usr/bin/env python3
"""
综合参数优化回测
1. QQQ 长周期回测（2010-2025）+ 1-5组对比 + 动态OTM
2. 港股腾讯 5%/8%/10% OTM 长周期回测（2020-2025）
3. 综合对比报告
"""
import sys
import json
import time
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))

def run_qqq_tests():
    """QQQ 长周期回测：固定 vs 动态OTM + 1-5组对比"""
    from iron_condor_us import USIronCondorBacktester, fetch_futu_kline
    
    print("=" * 80)
    print("  📊 QQQ 长周期回测 (2010-2025) + 组数对比 + 动态OTM")
    print("=" * 80)
    
    # 获取 QQW 数据（尽量长周期）
    print("\n📡 获取 QQQ 历史K线...")
    df = fetch_futu_kline("US.QQQ", "2010-01-01", "2025-12-31")
    if df is None or df.empty:
        print("❌ 无法获取 QQQ 数据，尝试 2020-2025")
        df = fetch_futu_kline("US.QQQ", "2020-01-01", "2025-12-31")
    if df is None or df.empty:
        print("❌ 无法获取数据")
        return []
    
    print(f"✅ 获取 {len(df)} 个交易日: {df['date'].iloc[0]} → {df['date'].iloc[-1]}")
    
    configs = [
        # === 固定参数 vs 动态 OTM ===
        {"label": "QQQ 固定5%OTM G1",     "otm": 0.05, "wing": 0.08, "groups": 1, "dynamic": False},
        {"label": "QQQ 动态OTM G1",        "otm": 0.05, "wing": 0.08, "groups": 1, "dynamic": True},
        
        # === 组数对比（固定参数）===
        {"label": "QQQ 固定5%OTM G2",     "otm": 0.05, "wing": 0.08, "groups": 2, "dynamic": False},
        {"label": "QQQ 固定5%OTM G3",     "otm": 0.05, "wing": 0.08, "groups": 3, "dynamic": False},
        {"label": "QQQ 固定5%OTM G5",     "otm": 0.05, "wing": 0.08, "groups": 5, "dynamic": False},
        
        # === 组数对比（动态 OTM）===
        {"label": "QQQ 动态OTM G2",        "otm": 0.05, "wing": 0.08, "groups": 2, "dynamic": True},
        {"label": "QQQ 动态OTM G3",        "otm": 0.05, "wing": 0.08, "groups": 3, "dynamic": True},
        {"label": "QQQ 动态OTM G5",        "otm": 0.05, "wing": 0.08, "groups": 5, "dynamic": True},
        
        # === 不同 DTE 对比 ===
        {"label": "QQQ 固定5%OTM G1 DTE21",  "otm": 0.05, "wing": 0.08, "groups": 1, "dte": 21, "dynamic": False},
        {"label": "QQQ 固定5%OTM G1 DTE45",  "otm": 0.05, "wing": 0.08, "groups": 1, "dte": 45, "dynamic": False},
    ]
    
    results = []
    for idx, cfg in enumerate(configs):
        label = cfg["label"]
        print(f"\n{'─'*60}")
        print(f"  ▶ [{idx+1}/{len(configs)}] {label}")
        print(f"{'─'*60}")
        
        bt = USIronCondorBacktester(
            ticker="US.QQQ",
            initial_capital=10_000,
            otm_distance=cfg["otm"],
            wing_width=cfg["wing"],
            dte=cfg.get("dte", 30),
            max_groups=cfg["groups"],
            cooldown_days=5,
            early_close_days=2,
            stop_loss_pct=0.05,
            entry_mode="pre_expiry",
            entry_days_before_expiry=cfg.get("dte", 30),
            dynamic_otm=cfg["dynamic"],
            label=label,
        )
        
        r = bt.run(df, save_prefix=f"qqq_opt_{idx}")
        results.append({**r, "dynamic": cfg["dynamic"]})
        time.sleep(0.5)
    
    return results


def run_tencent_tests():
    """港股腾讯 5%/8%/10% OTM 对比"""
    from iron_condor import IronCondorBacktester, fetch_futu_kline
    
    print("\n\n" + "=" * 80)
    print("  📊 港股腾讯 OTM 对比 (2020-2025)")
    print("=" * 80)
    
    print("\n📡 获取腾讯历史K线...")
    df = fetch_futu_kline("HK.00700", "2020-01-01", "2025-12-31")
    if df is None or df.empty:
        print("❌ 无法获取腾讯数据")
        return []
    
    print(f"✅ 获取 {len(df)} 个交易日: {df['date'].iloc[0]} → {df['date'].iloc[-1]}")
    
    configs = [
        {"label": "腾讯 OTM5% W8% DTE30", "otm_distance": 0.05, "wing_width": 0.08, "dte": 30},
        {"label": "腾讯 OTM8% W8% DTE30", "otm_distance": 0.08, "wing_width": 0.08, "dte": 30},
        {"label": "腾讯 OTM10% W8% DTE30", "otm_distance": 0.10, "wing_width": 0.08, "dte": 30},
        {"label": "腾讯 OTM8% W12% DTE30", "otm_distance": 0.08, "wing_width": 0.12, "dte": 30},
        {"label": "腾讯 OTM10% W12% DTE30", "otm_distance": 0.10, "wing_width": 0.12, "dte": 30},
        {"label": "腾讯 OTM5% W8% DTE45", "otm_distance": 0.05, "wing_width": 0.08, "dte": 45},
        {"label": "腾讯 OTM8% W8% DTE45", "otm_distance": 0.08, "wing_width": 0.08, "dte": 45},
        {"label": "腾讯 OTM10% W8% DTE45", "otm_distance": 0.10, "wing_width": 0.08, "dte": 45},
    ]
    
    results = []
    for idx, cfg in enumerate(configs):
        label = cfg["label"]
        print(f"\n{'─'*60}")
        print(f"  ▶ [{idx+1}/{len(configs)}] {label}")
        print(f"{'─'*60}")
        
        bt = IronCondorBacktester(
            otm_distance=cfg["otm_distance"],
            wing_width=cfg["wing_width"],
            dte=cfg["dte"],
            initial_capital=100_000,  # 10万 HKD
            stop_loss_pct=0.05,
            max_groups=1,
            cooldown_days=15,
            early_close_days=2,
            stop_loss_buffer=1.5,
            label=label,
        )
        
        bt.run(df, save_prefix=f"tencent_otm_{idx}")
        r = bt.print_report(save_prefix=f"tencent_otm_{idx}")
        results.append(r)
        time.sleep(0.5)
    
    return results


def generate_comparison_report(qqq_results, tencent_results):
    """生成综合 HTML 对比报告"""
    from datetime import datetime
    
    out = Path(__file__).parent / "backtest_results"
    out.mkdir(exist_ok=True)
    
    # 找出最优
    valid_qqq = [r for r in qqq_results if r is not None]
    valid_tencent = [r for r in tencent_results if r is not None]
    qqq_best = max(valid_qqq, key=lambda x: x["ann_return"]) if valid_qqq else None
    tencent_best = max(valid_tencent, key=lambda x: x["ann_return"]) if valid_tencent else None
    
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Iron Condor 综合参数优化报告</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; background: #0f0f1a; color: #eee; }
h1 { color: #00d2ff; text-align: center; }
h2 { color: #7f5af0; margin-top: 40px; border-bottom: 1px solid #333; padding-bottom: 10px; }
h3 { color: #00d2ff; }
table { width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 13px; }
th { background: #1a1a2e; color: #00d2ff; padding: 10px 6px; text-align: center; position: sticky; top: 0; }
td { padding: 8px 6px; text-align: center; border-bottom: 1px solid #1a1a2e; }
tr:hover { background: #1a1a2e; }
.positive { color: #00ff88; }
.negative { color: #ff4444; }
.best { background: #0a3d2a; font-weight: bold; }
.warn { background: #3d2a0a; }
.summary { background: #1a1a2e; padding: 20px; border-radius: 10px; margin: 20px 0; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.card { background: #1a1a2e; padding: 20px; border-radius: 10px; }
.insight { color: #ffaa00; font-weight: bold; }
</style>
</head>
<body>
<h1>🦅 Iron Condor 综合参数优化报告</h1>
<div class="summary" style="text-align: center;">
<p>生成时间：""" + datetime.now().strftime("%Y-%m-%d %H:%M") + """ | 数据来源：富途 OpenD API 真实日K线</p>
</div>

<div class="grid">
<div class="card">
<h3>📊 美股 QQQ 回测</h3>
<p>标的: QQQ (纳斯达克100 ETF) | 本金: $10,000</p>
"""
    if qqq_best:
        html += f"""
<p class="positive">🏆 最优: {qqq_best['label']}</p>
<ul>
<li>年化: <span class="positive">{qqq_best['ann_return']:+.2f}%</span></li>
<li>最大回撤: {qqq_best['max_dd']:.2f}%</li>
<li>夏普: {qqq_best['sharpe_ratio']:.2f}</li>
<li>胜率: {qqq_best['win_rate']:.0f}% ({qqq_best['n_open']}次开仓)</li>
<li>${10_000:,.0f} → ${qqq_best['final_value']:,.0f}</li>
</ul>"""
    html += """</div>
<div class="card">
<h3>🇭🇰 港股腾讯回测</h3>
<p>标的: 腾讯 (00700.HK) | 本金: HKD 100,000</p>
"""
    if tencent_best:
        html += f"""
<p class="positive">🏆 最优: {tencent_best['label']}</p>
<ul>
<li>年化: <span class="positive">{tencent_best['ann_return']:+.2f}%</span></li>
<li>最大回撤: {tencent_best['max_dd']:.2f}%</li>
<li>夏普: {tencent_best['sharpe_ratio']:.2f}</li>
<li>胜率: {tencent_best['win_rate']:.0f}% ({tencent_best['n_open']}次开仓)</li>
<li>HKD 100,000 → HKD {tencent_best['final_value']:,.0f}</li>
</ul>"""
    html += """</div></div>

<h2>📊 QQQ 全部参数对比</h2>
<table>
<tr>
<th>配置</th><th>动态OTM</th><th>年化</th><th>总收益</th><th>最大回撤</th><th>夏普</th>
<th>开仓</th><th>胜率</th><th>均次权利金</th><th>最终资金</th>
</tr>"""
    
    for i, r in enumerate(sorted(valid_qqq, key=lambda x: x["ann_return"], reverse=True)):
        row_class = "best" if i == 0 else ""
        dyn = "✅" if r.get("dynamic") else "—"
        ann_cls = "positive" if r["ann_return"] > 0 else "negative"
        dd_cls = "negative" if r["max_dd"] < -10 else ("warn" if r["max_dd"] < -5 else "")
        
        html += f"""<tr class="{row_class}">
<td style="text-align:left; padding-left:10px;">{r['label']}</td>
<td>{dyn}</td>
<td class="{ann_cls}">{r['ann_return']:+.2f}%</td>
<td class="{ann_cls}">{r['total_return']:+.2f}%</td>
<td class="{dd_cls}">{r['max_dd']:.2f}%</td>
<td>{r['sharpe_ratio']:.2f}</td>
<td>{r['n_open']}次</td>
<td>{r['win_rate']:.0f}%</td>
<td>${r['avg_credit']:.0f}</td>
<td>${r['final_value']:,.0f}</td>
</tr>"""
    
    html += """</table>

<h2>🇭🇰 港股腾讯 OTM 参数对比</h2>
<table>
<tr>
<th>配置</th><th>年化</th><th>总收益</th><th>最大回撤</th><th>夏普</th>
<th>开仓</th><th>胜率</th><th>均次权利金</th><th>最终资金</th>
</tr>"""
    
    for i, r in enumerate(sorted(valid_tencent, key=lambda x: x["ann_return"], reverse=True)):
        row_class = "best" if i == 0 else ""
        ann_cls = "positive" if r["ann_return"] > 0 else "negative"
        
        html += f"""<tr class="{row_class}">
<td style="text-align:left; padding-left:10px;">{r['label']}</td>
<td class="{ann_cls}">{r['ann_return']:+.2f}%</td>
<td class="{ann_cls}">{r['total_return']:+.2f}%</td>
<td>{r['max_dd']:.2f}%</td>
<td>{r['sharpe_ratio']:.2f}</td>
<td>{r['n_open']}次</td>
<td>{r['win_rate']:.0f}%</td>
<td>HKD {r['avg_credit']:.0f}</td>
<td>HKD {r['final_value']:,.0f}</td>
</tr>"""
    
    html += """</table>

<h2>💡 关键发现</h2>
<div class="summary">
<ul>
"""
    
    # 动态 OTM 分析
    fixed_results = [r for r in valid_qqq if not r.get("dynamic")]
    dynamic_results = [r for r in valid_qqq if r.get("dynamic")]
    
    if fixed_results and dynamic_results:
        fixed_best = max(fixed_results, key=lambda x: x["ann_return"])
        dyn_best = max(dynamic_results, key=lambda x: x["ann_return"])
        fixed_best_g1 = max([r for r in fixed_results if "G1" in r["label"] and "DTE21" not in r["label"] and "DTE45" not in r["label"]], key=lambda x: x["ann_return"]) if any("G1" in r["label"] for r in fixed_results) else fixed_best
        
        if dyn_best["ann_return"] > fixed_best_g1["ann_return"]:
            html += f'<li class="positive">✅ 动态OTM有效：G1最优动态={dyn_best["ann_return"]:+.2f}% vs 固定={fixed_best_g1["ann_return"]:+.2f}%</li>\n'
        else:
            html += f'<li class="warn">⚠️ 动态OTM效果有限：G1最优动态={dyn_best["ann_return"]:+.2f}% vs 固定={fixed_best_g1["ann_return"]:+.2f}%</li>\n'
    
    # 组数分析
    for groups in [1, 2, 3, 5]:
        g_results = [r for r in valid_qqq if f"G{groups}" in r["label"] and "DTE21" not in r["label"] and "DTE45" not in r["label"]]
        if g_results:
            g_best = max(g_results, key=lambda x: x["ann_return"])
            html += f'<li>G{groups} 最优: {g_best["label"]} → 年化 {g_best["ann_return"]:+.2f}%, 最大回撤 {g_best["max_dd"]:.2f}%, 最终 ${g_best["final_value"]:,.0f}</li>\n'
    
    # 腾讯 OTM 分析
    if valid_tencent:
        tenc_best = max(valid_tencent, key=lambda x: x["ann_return"])
        html += f'<li class="positive">🏆 腾讯最优: {tenc_best["label"]} → 年化 {tenc_best["ann_return"]:+.2f}%, 胜率 {tenc_best["win_rate"]:.0f}%</li>\n'
        
        # OTM 对胜率的影响
        for r in sorted(valid_tencent, key=lambda x: x["otm_distance"]):
            html += f'<li>OTM={r["otm_distance"]:.0%} DTE30: 胜率 {r["win_rate"]:.0f}%, 年化 {r["ann_return"]:+.2f}%, 回撤 {r["max_dd"]:.2f}%</li>\n'
    
    html += """</ul>
</div>

<p style="text-align: center; color: #555; margin-top: 40px;">
数据来源：富途 OpenD API 真实日K线 | 期权定价：Black-Scholes + 20日历史波动率<br>
VIX 动态调参使用 HV20（20日历史波动率）作为 VIX 代理<br>
HV20 < 20%: OTM=5% Wing=8% | HV20 20-30%: OTM=8% Wing=12% | HV20 > 30%: 暂停开仓
</p>
</body></html>"""
    
    html_path = out / "ic_comprehensive_optimization.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"\n📄 综合报告已保存: {html_path}")
    return str(html_path)


def main():
    # 1. QQQ 测试
    qqq_results = run_qqq_tests()
    
    # 2. 腾讯测试
    tencent_results = run_tencent_tests()
    
    # 3. 综合报告
    if qqq_results or tencent_results:
        report_path = generate_comparison_report(qqq_results, tencent_results)
        print(f"\n\n{'='*80}")
        print(f"  ✅ 全部回测完成！报告: {report_path}")
        print(f"{'='*80}")
        
        # 打印最终推荐
        print("\n" + "=" * 80)
        print("  🏆 最终参数推荐")
        print("=" * 80)
        
        if qqq_results:
            # 按 G1 vs G2 vs G3 vs G5 分别找最优
            print("\n📊 美股 QQQ ($10,000 本金):")
            for g in [1, 2, 3, 5]:
                g_list = [r for r in qqq_results if f"G{g}" in r["label"] and "DTE21" not in r["label"] and "DTE45" not in r["label"]]
                if g_list:
                    best = max(g_list, key=lambda x: x["ann_return"])
                    dyn_tag = " [动态]" if best.get("dynamic") else " [固定]"
                    print(f"  G{g} 最优{dyn_tag}: {best['label']} → 年化{best['ann_return']:+.2f}%, 回撤{best['max_dd']:.2f}%, 夏普{best['sharpe_ratio']:.2f}, 胜率{best['win_rate']:.0f}%")
            
            # 找 $10K 最优组数
            all_g1_plus = [r for r in qqq_results if any(f"G{g}" in r["label"] for g in [1,2,3,5]) and "DTE21" not in r["label"] and "DTE45" not in r["label"]]
            if all_g1_plus:
                # 按风险调整后收益排序（年化/最大回撤绝对值）
                best_risk_adj = max(all_g1_plus, key=lambda x: x["ann_return"] / max(abs(x["max_dd"]), 1))
                print(f"\n  ⭐ 风险调整最优: {best_risk_adj['label']} → 年化/回撤比 = {best_risk_adj['ann_return']/max(abs(best_risk_adj['max_dd']),1):.2f}")
        
        valid_tencent_list = [r for r in tencent_results if r is not None]
        if valid_tencent_list:
            print("\n🇭🇰 港股腾讯 (HKD 100,000 本金):")
            best_tenc = max(valid_tencent_list, key=lambda x: x["ann_return"])
            print(f"  最优: {best_tenc['label']} → 年化{best_tenc['ann_return']:+.2f}%, 回撤{best_tenc['max_dd']:.2f}%, 胜率{best_tenc['win_rate']:.0f}%")


if __name__ == "__main__":
    main()
