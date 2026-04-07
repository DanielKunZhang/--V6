#!/usr/bin/env python3
"""
生成 Iron Condor V6 修复版详细回测报告（HTML）
修复内容：
1. 总回撤止损从"永久停止"改为"冷却暂停"
2. 冷却期后自动恢复交易
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
import math, json
from datetime import date
from pathlib import Path

from iron_condor import IronCondorBacktester
from backtest_real import fetch_futu_kline

# === 回测参数 ===
CONFIG = {
    "ticker": "HK.00700",
    "capital": 100000,
    "otm": 0.05,
    "wing": 0.08,
    "dte": 30,
    "start": "2020-01-01",
    "end": "2025-12-31",
    "stop_loss_pct": 0.05,     # 总回撤5%止损（冷却恢复）
    "cooldown_days": 30,        # 冷却30天
    "stop_loss_buffer": 1.5,   # 单笔止损缓冲
}

print("=" * 60)
print("  🦅 Iron Condor V6 回测（冷却恢复机制）")
print("=" * 60)
print(f"  标的: {CONFIG['ticker']} | DTE={CONFIG['dte']}")
print(f"  OTM={CONFIG['otm']*100}% | Wing={CONFIG['wing']*100}%")
print(f"  止损: {CONFIG['stop_loss_pct']*100}%总回撤 → 暂停{CONFIG['cooldown_days']}天")
print()

# 1. 获取数据
df = fetch_futu_kline(CONFIG["ticker"], CONFIG["start"], CONFIG["end"])
if df is None:
    print("❌ 无法获取数据"); sys.exit(1)

# 2. 运行回测
bt = IronCondorBacktester(
    initial_capital=CONFIG["capital"],
    otm_distance=CONFIG["otm"],
    wing_width=CONFIG["wing"],
    dte=CONFIG["dte"],
    stop_loss_pct=CONFIG["stop_loss_pct"],
    cooldown_days=CONFIG["cooldown_days"],
    stop_loss_buffer=CONFIG["stop_loss_buffer"],
    label=f"V6修复_DTE{CONFIG['dte']}",
)
bt.run(df)
result = bt.print_report(save_prefix="ic_v6_fix")

# 3. 构建详细HTML
daily_df = pd.DataFrame(bt.daily_records)
trades_df = pd.DataFrame(bt.trades) if bt.trades else pd.DataFrame()

# 计算年度收益
daily_df["peak"] = daily_df["total_value"].cummax()
daily_df["drawdown"] = (daily_df["total_value"] - daily_df["peak"]) / daily_df["peak"] * 100
daily_df["year"] = pd.to_datetime(daily_df["date"]).dt.year

# 年度统计
yearly_stats = []
for year, grp in daily_df.groupby("year"):
    start_val = grp.iloc[0]["total_value"]
    end_val = grp.iloc[-1]["total_value"]
    ret = (end_val / start_val - 1) * 100
    max_dd = grp["drawdown"].min()
    n_trades = len(trades_df[(trades_df["date"].str.startswith(str(year))) & (trades_df["action"]=="OPEN_IC")])
    yearly_stats.append({"year": year, "return": round(ret, 2), "max_dd": round(max_dd, 2), "trades": n_trades})

# 月度收益率
daily_df["month"] = pd.to_datetime(daily_df["date"]).dt.to_period("M")
monthly_ret = daily_df.groupby("month").apply(
    lambda g: (g.iloc[-1]["total_value"] / g.iloc[0]["total_value"] - 1) * 100 if len(g) > 1 else 0
).reset_index()
monthly_ret.columns = ["month", "return"]
monthly_ret["month_str"] = monthly_ret["month"].astype(str)

# 交易明细
trade_details = []
if not trades_df.empty:
    for _, t in trades_df.iterrows():
        trade_details.append({
            "date": t.get("date", ""),
            "action": t.get("action", ""),
            "pnl": t.get("pnl", 0),
            "result": t.get("result", ""),
        })

# 停止/恢复事件
events = [t for t in trade_details if t["action"] == "STOP_LOSS"]
recoveries = []  # 从日志提取冷却恢复事件

# 生成HTML
dates = [str(d) for d in daily_df["date"]]
values = [round(float(v), 0) for v in daily_df["total_value"]]
dd_values = [round(float(v), 2) for v in daily_df["drawdown"]]
price_vals = [round(float(v), 1) for v in daily_df["price"]]

yearly_json = json.dumps(yearly_stats, ensure_ascii=False)
monthly_json = json.dumps([{"m": r["month_str"], "v": round(r["return"], 2)} for _, r in monthly_ret.iterrows()], ensure_ascii=False)
trades_json = json.dumps(trade_details[:200], ensure_ascii=False)  # 最多200条

html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Iron Condor V6 详细回测报告 - 腾讯00700</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,'SF Pro','Helvetica Neue',Arial,sans-serif; background:#0f172a; color:#e2e8f0; }}
.header {{ background:linear-gradient(135deg,#1e293b 0%,#334155 100%); padding:30px 20px; text-align:center; border-bottom:3px solid #6366f1; }}
.header h1 {{ font-size:26px; color:#fff; }}
.header .sub {{ font-size:14px; color:#94a3b8; margin-top:8px; }}
.header .badge {{ display:inline-block; background:#22c55e; color:#000; font-size:11px; font-weight:bold; padding:2px 10px; border-radius:10px; margin-left:8px; }}
.container {{ max-width:1200px; margin:20px auto; padding:0 15px; }}

/* 指标卡片 */
.metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-bottom:25px; }}
.card {{ background:#1e293b; border-radius:12px; padding:18px; border:1px solid #334155; }}
.card-metric {{ font-size:28px; font-weight:bold; color:#6366f1; }}
.card-label {{ font-size:12px; color:#94a3b8; text-transform:uppercase; letter-spacing:1px; }}
.card-sub {{ font-size:13px; color:#cbd5e1; margin-top:4px; }}
.green {{ color:#22c55e; }} .red {{ color:#ef4444; }} .yellow {{ color:#f59e0b; }}

/* 图表 */
.chart-box {{ background:#1e293b; border-radius:12px; padding:20px; margin-bottom:20px; border:1px solid #334155; }}
.chart-title {{ font-size:16px; font-weight:600; color:#e2e8f0; margin-bottom:12px; }}

/* 表格 */
.table-wrap {{ overflow-x:auto; margin-bottom:20px; }}
table {{ width:100%; border-collapse:collapse; background:#1e293b; border-radius:12px; overflow:hidden; }}
th {{ background:#334155; color:#e2e8f0; padding:10px 14px; text-align:left; font-size:13px; white-space:nowrap; }}
td {{ padding:8px 14px; border-bottom:1px solid #1e293b; font-size:13px; }}
tr:hover td {{ background:#283548; }}

.section-title {{ font-size:18px; font-weight:700; color:#fff; margin:25px 0 15px; padding-left:10px; border-left:4px solid #6366f1; }}

.fix-log {{ background:#1e293b; border-radius:12px; padding:20px; margin-bottom:20px; border-left:4px solid #22c55e; }}
.fix-log h3 {{ color:#22c55e; font-size:16px; margin-bottom:10px; }}
.fix-item {{ padding:6px 0; font-size:14px; line-height:1.6; }}
.fix-before {{ color:#ef4444; text-decoration:line-through; opacity:0.7; }}
.fix-after {{ color:#22c55e; font-weight:600; }}

.event-list {{ list-style:none; padding:0; }}
.event-list li {{ padding:8px 12px; border-bottom:1px solid #1e293b; font-size:13px; display:flex; justify-content:space-between; }}
</style>
</head>
<body>

<div class="header">
  <h1>🦅 Iron Condor V6 回测报告 <span class="badge">已修复</span></h1>
  <div class="sub">腾讯控股 (00700.HK) · {CONFIG['start']} ~ {CONFIG['end']} · 初始资金 HKD {CONFIG['capital']:,}</div>
  <div class="sub">OTM={CONFIG['otm']*100}% | Wing={CONFIG['wing']*100}% | DTE={CONFIG['dte']} | 止损={CONFIG['stop_loss_pct']*100}%→暂停{CONFIG['cooldown_days']}天</div>
</div>

<div class="container">

<!-- 核心指标 -->
<div class="metrics">
  <div class="card"><div class="card-label">年化收益</div><div class="card-metric {'green' if result['ann_return']>0 else 'red'}">{result['ann_return']:+.2f}%</div><div class="card-sub">共{result.get('years',6):.1f}年</div></div>
  <div class="card"><div class="card-label">总收益</div><div class="card-metric {'green' if result['total_return']>0 else 'red'}">{result['total_return']:+.2f}%</div><div class="card-sub">{result.get('total_pnl',0):>+,.0f} HKD</div></div>
  <div class="card"><div class="card-label">最大回撤</div><div class="card-metric red">{result['max_dd']:.2f}%</div><div class="card-sub">{result.get('max_dd_date','')}</div></div>
  <div class="card"><div class="card-label">夏普比率</div><div class="card-metric {'green' if result.get('sharpe_ratio',0)>0 else 'red'}">{result.get('sharpe_ratio',0):.2f}</div><div class="card-sub">风险调整后</div></div>
  <div class="card"><div class="card-label">开仓次数</div><div class="card-metric">{result['n_open']}</div><div class="card-sub">均次权利金 {result.get('avg_credit',0):,.0f} HKD</div></div>
  <div class="card"><div class="card-label">胜率</div><div class="card-metric yellow">{result['win_rate']:.0f}%</div><div class="card-sub">到期{result.get('n_expired',0)} / 提前平仓{result.get('n_early_close',0)}</div></div>
</div>

<!-- V6修复说明 -->
<div class="fix-log">
  <h3>🔧 V6 修复内容（本次改动）</h3>
  <div class="fix-item"><span class="fix-before">Bug: 触发回撤止损后永久停止交易 (stopped=True)</span></div>
  <div class="fix-item"><span class="fix-after">✅ 修复: 改为临时冷却暂停，{CONFIG['cooldown_days']}天后自动恢复交易</span></div>
  <div style="margin-top:10px;font-size:13px;color:#94a3b8;">
    效果：2020年3月暴跌触发止损后，原代码6年不再交易（年化-0.31%），
    修复后冷却30天恢复，继续捕捉后续行情（年化+{result['ann_return']:.2f}%）
  </div>
</div>

<!-- 资金曲线 -->
<div class="chart-box">
  <div class="chart-title">📈 资金曲线 vs 股价</div>
  <canvas id="mainChart" height="350"></canvas>
</div>

<!-- 回撤曲线 -->
<div class="chart-box">
  <div class="chart-title">📉 回撤曲线</div>
  <canvas id="ddChart" height="200"></canvas>
</div>

<!-- 年度统计 -->
<div class="section-title">📊 年度收益分解</div>
<div class="table-wrap">
<table>
<tr><th>年份</th><th>收益率</th><th>最大回撤</th><th>开仓次数</th><th>评价</th></tr>
"""
for y in yearly_stats:
    color = "green" if y["return"] > 0 else ("yellow" if y["return"] > -5 else "red")
    emoji = "🟢" if y["return"] > 5 else ("🟡" if y["return"] > 0 else ("🔴" if y["return"] < -3 else "⚪"))
    html += f'<tr><td>{y["year"]}</td><td class="{color}">{y["return"]:+.2f}%</td><td>{y["max_dd"]:.2f}%</td><td>{y["trades"]}</td><td>{emoji}</td></tr>'
html += """
</table>
</div>

<!-- 最近交易记录 -->
<div class="section-title">📋 交易记录（最近50笔）</div>
<div class="table-wrap">
<table>
<tr><th>日期</th><th>操作</th><th>盈亏(HKD)</th><th>备注</th></tr>
"""
recent_trades = trade_details[-50:]
for t in recent_trades:
    pnl_color = "green" if t["pnl"] > 0 else ("red" if t["pnl"] < 0 else "")
    pnl_str = f"{t['pnl']:>+,.0f}" if t["pnl"] != 0 else "-"
    action_map = {"OPEN_IC": "🦅开仓", "IC_EXPIRED": "📅到期", "EARLY_CLOSE": "⚠️提前平仓", "STOP_LOSS": "🛑止损暂停"}
    action_label = action_map.get(t["action"], t["action"])
    html += f'<tr><td>{t["date"]}</td><td>{action_label}</td><td class="{pnl_color}">{pnl_str}</td><td>{t["result"]}</td></tr>'
html += """</table>
</div>

</div>

<script>
// 主图表
const mainCtx = document.getElementById('mainChart').getContext('2d');
new Chart(mainCtx, {{
  type: 'line',
  data: {{
    labels: {json.dumps(dates)},
    datasets: [
      {{ label: '组合资产 (HKD)', data: {json.stringify(values)}, borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.05)', fill: true, yAxisID: 'y', pointRadius: 0, borderWidth: 1.5 }},
      {{ label: '股价', data: {json.stringify(price_vals)}, borderColor: '#f59e0b', yAxisID: 'y1', pointRadius: 0, borderWidth: 1, borderDash: [5,3] }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    scales: {{
      y: {{ type: 'linear', position: 'left', title: {{ display:true, text:'组合资产(HKD)' }}, grid: {{ color:'#1e293b' }}, ticks: {{ color:'#94a3b8' }} }},
      y1: {{ type: 'linear', position: 'right', title: {{ display:true, text:'股价' }}, grid: {{ drawOnChart:false }}, ticks: {{ color:'#94a3b8' }} }},
      x: {{ grid: {{ color:'#1e293b' }}, ticks: {{ color:'#94a3b8', maxTicksLimit: 20 }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color:'#cbd5e1' }} }} }}
  }}
}});

// 回撤图
const ddCtx = document.getElementById('ddChart').getContext('2d');
new Chart(ddCtx, {{
  type: 'area',
  data: {{
    labels: {json.dumps(dates)},
    datasets: [{{
      label: '回撤 %',
      data: {json.dumps(dd_values)},
      borderColor: '#ef4444',
      backgroundColor: (ctx) => {{
        const c = ctx.chart.ctx;
        const gradient = c.createLinearGradient(0,0,0,300);
        gradient.addColorStop(0, 'rgba(239,68,68,0.3)');
        gradient.addColorStop(1, 'rgba(239,68,68,0.02)');
        return gradient;
      }},
      fill: true, pointRadius: 0, borderWidth: 1
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      y: {{ reverse: true, title: {{ display:true, text:'回撤%' }}, grid: {{ color:'#1e293b' }}, ticks: {{ color:'#94a3b8', callback:v=>v+'%' }} }},
      x: {{ grid: {{ color:'#1e293b' }}, ticks: {{ color:'#94a3b8', maxTicksLimit: 20 }} }}
    }},
    plugins: {{ legend: {{ display:false }} }}
  }}
}});
</script>
</body>
</html>"""

out_path = Path(__file__).parent / "backtest_results" / "ic_v6_detailed_report.html"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(html, encoding="utf-8")
print(f"\n📊 详细报告已生成 → {out_path}")
