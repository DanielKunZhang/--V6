#!/usr/bin/env python3
"""
动态组数 vs 固定组数 对比回测
==============================
验证问题：固定 max_groups 是否随本金增大而年化衰减？
动态组数（等比线性扩仓）能否维持稳定年化？

场景：
  A  固定 G4（基线）                     groups_cap=N/A
  B  动态 base=4  无上限                  groups_cap=999
  C  动态 base=4  cap=50                  groups_cap=50
  D  动态 base=4  cap=20                  groups_cap=20
  E  动态 base=2  无上限                  groups_cap=999
  F  动态 base=2  cap=50                  groups_cap=50

输出：
  - 终端汇总表（CAGR / 最大回撤 / 夏普 / 逐年收益率标准差 / 峰值组数 / 最终净值）
  - backtest_results/dynamic_sizing_comparison.html
"""

import sys, json, math
from pathlib import Path
from datetime import date
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline
from iron_condor_us import USIronCondorBacktester

TICKER   = "US.QQQ"
START    = "2010-01-01"
END      = "2025-12-31"
CAPITAL  = 15_000
RISK_FREE = 0.05

# ── 场景定义 ──────────────────────────────────────────────
SCENARIOS = [
    {"id": "A", "label": "A  固定 G4（基线）",         "dynamic": False, "base_groups": 4, "cap": 200},
    {"id": "B", "label": "B  动态 base=4  无上限",     "dynamic": True,  "base_groups": 4, "cap": 999},
    {"id": "C", "label": "C  动态 base=4  cap=50",    "dynamic": True,  "base_groups": 4, "cap": 50},
    {"id": "D", "label": "D  动态 base=4  cap=20",    "dynamic": True,  "base_groups": 4, "cap": 20},
    {"id": "E", "label": "E  动态 base=2  无上限",     "dynamic": True,  "base_groups": 2, "cap": 999},
    {"id": "F", "label": "F  动态 base=2  cap=50",    "dynamic": True,  "base_groups": 2, "cap": 50},
]

# 固定策略参数（与主策略 main_ic_us.py 对齐）
IC_PARAMS = dict(
    otm_distance=0.05,
    wing_width=0.09,
    dte=45,
    stop_loss_pct=0.05,
    stop_loss_buffer=1.5,
    early_close_days=2,
    entry_mode="pre_expiry",
    entry_days_before_expiry=45,
    cooldown_days=5,
)


def run_scenario(sc: dict, df: pd.DataFrame) -> dict:
    bt = USIronCondorBacktester(
        ticker=TICKER,
        initial_capital=CAPITAL,
        max_groups=sc["base_groups"],
        dynamic_sizing=sc["dynamic"],
        groups_cap=sc["cap"],
        label=sc["label"],
        **IC_PARAMS,
    )
    r = bt.run(df, save_prefix=f"dyn_{sc['id']}")

    # 逐年收益率
    daily_df = pd.DataFrame(bt.daily_records)
    daily_df["date"] = pd.to_datetime(daily_df["date"])
    daily_df = daily_df.set_index("date")
    yearly = (
        daily_df["total_value"]
        .resample("YE")
        .last()
        .pct_change()
        .dropna()
        * 100
    )
    # 第一年：用初始资本作基准
    first_year_end = daily_df["total_value"].resample("YE").last().iloc[0]
    first_year_ret = (first_year_end - CAPITAL) / CAPITAL * 100
    yearly_all = [first_year_ret] + list(yearly.values)
    yearly_years = (
        [daily_df["total_value"].resample("YE").last().index[0].year]
        + list(yearly.index.year)
    )

    # 峰值组数（从trades里统计单次最大groups）
    trades_df = pd.DataFrame(bt.trades) if bt.trades else pd.DataFrame()
    peak_groups = 0
    if not trades_df.empty and "groups" in trades_df.columns:
        peak_groups = int(trades_df["groups"].max())

    return {
        "id": sc["id"],
        "label": sc["label"],
        "dynamic": sc["dynamic"],
        "base_groups": sc["base_groups"],
        "cap": sc["cap"],
        "ann_return": r["ann_return"],
        "max_dd": r["max_dd"],
        "sharpe": r["sharpe_ratio"],
        "final_value": r["final_value"],
        "years": r["years"],
        "yearly_returns": yearly_all,
        "yearly_years": yearly_years,
        "yearly_std": float(np.std(yearly_all)),
        "peak_groups": peak_groups,
        "daily_df": daily_df,
    }


def print_summary(results: list):
    print(f"\n\n{'='*110}")
    print(f"  📊 动态组数 vs 固定组数 对比回测  —  QQQ  ${CAPITAL:,} 初始资本  {START[:4]}–{END[:4]}")
    print(f"{'='*110}")
    hdr = (
        f"  {'场景':<32}  {'年化':>8}  {'最大回撤':>9}  {'夏普':>6}  "
        f"{'逐年STD':>8}  {'峰值组数':>8}  {'最终净值':>12}"
    )
    print(hdr)
    print("  " + "─" * 105)

    for r in results:
        marker = " ★" if r["sharpe"] == max(x["sharpe"] for x in results) else "  "
        print(
            f"{marker}{r['label']:<34}  {r['ann_return']:>+7.2f}%  "
            f"{r['max_dd']:>8.2f}%  {r['sharpe']:>6.2f}  "
            f"{r['yearly_std']:>7.1f}%  {r['peak_groups']:>8}  "
            f"${r['final_value']:>11,.0f}"
        )
    print("  " + "─" * 105)

    # 打印逐年收益率对比
    print(f"\n  📅 逐年收益率（%）对比：")
    # 取所有年份
    all_years = sorted(set(y for r in results for y in r["yearly_years"]))
    header = f"  {'年份':>6}" + "".join(f"  {r['id']:>8}" for r in results)
    print(header)
    print("  " + "─" * (8 + 10 * len(results)))
    for yr in all_years:
        row = f"  {yr:>6}"
        for r in results:
            if yr in r["yearly_years"]:
                idx = r["yearly_years"].index(yr)
                val = r["yearly_returns"][idx]
                row += f"  {val:>+7.1f}%"
            else:
                row += f"  {'N/A':>8}"
        print(row)
    print(f"\n  逐年STD：年化收益率的标准差，越低代表收益率越稳定")
    print(f"  峰值组数：回测期内单次最多开仓组数（动态扩仓后的峰值）")
    print(f"{'='*110}")


def generate_html(results: list, out_path: Path):
    all_years = sorted(set(y for r in results for y in r["yearly_years"]))

    # 逐年数据表格行
    rows = ""
    for yr in all_years:
        row = f"<tr><td>{yr}</td>"
        for r in results:
            if yr in r["yearly_years"]:
                idx = r["yearly_years"].index(yr)
                val = r["yearly_returns"][idx]
                color = "#22c55e" if val >= 0 else "#ef4444"
                row += f'<td style="color:{color}">{val:+.1f}%</td>'
            else:
                row += "<td>—</td>"
        row += "</tr>"
        rows += row

    # 汇总表格行
    summary_rows = ""
    for r in results:
        summary_rows += (
            f"<tr>"
            f"<td>{r['label']}</td>"
            f"<td>{r['ann_return']:+.2f}%</td>"
            f"<td>{r['max_dd']:.2f}%</td>"
            f"<td>{r['sharpe']:.2f}</td>"
            f"<td>{r['yearly_std']:.1f}%</td>"
            f"<td>{r['peak_groups']}</td>"
            f"<td>${r['final_value']:,.0f}</td>"
            f"</tr>"
        )

    # 净值曲线数据（JSON）
    equity_series = {}
    for r in results:
        equity_series[r["id"]] = {
            "label": r["label"],
            "dates": [str(d.date()) for d in r["daily_df"].index],
            "values": [round(v, 2) for v in r["daily_df"]["total_value"].tolist()],
        }

    col_headers = "".join(f"<th>{r['id']}</th>" for r in results)

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>动态组数 vs 固定组数 对比回测</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:20px; }}
  h1 {{ color:#f8fafc; text-align:center; margin-bottom:4px; }}
  h2 {{ color:#94a3b8; font-size:14px; text-align:center; margin-top:0; }}
  .section {{ background:#1e293b; border-radius:12px; padding:20px; margin:20px 0; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ background:#334155; color:#94a3b8; padding:8px 12px; text-align:right; }}
  th:first-child {{ text-align:left; }}
  td {{ padding:7px 12px; text-align:right; border-bottom:1px solid #334155; }}
  td:first-child {{ text-align:left; }}
  tr:hover {{ background:#334155; }}
  canvas {{ max-height:420px; }}
  .star {{ color:#fbbf24; }}
</style>
</head>
<body>
<h1>动态组数 vs 固定组数 对比回测</h1>
<h2>QQQ · ${CAPITAL:,} 初始资本 · {START[:4]}–{END[:4]}</h2>

<div class="section">
  <h3>汇总指标</h3>
  <table>
    <tr><th>场景</th><th>年化</th><th>最大回撤</th><th>夏普</th><th>逐年STD</th><th>峰值组数</th><th>最终净值</th></tr>
    {summary_rows}
  </table>
</div>

<div class="section">
  <h3>净值曲线</h3>
  <canvas id="equityChart"></canvas>
</div>

<div class="section">
  <h3>逐年收益率（%）</h3>
  <table>
    <tr><th>年份</th>{col_headers}</tr>
    {rows}
  </table>
</div>

<script>
const data = {json.dumps(equity_series, ensure_ascii=False)};
const colors = ['#60a5fa','#34d399','#fbbf24','#f87171','#a78bfa','#fb923c'];
const ctx = document.getElementById('equityChart').getContext('2d');
new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: Object.values(data)[0].dates.filter((_,i)=>i%5===0),
    datasets: Object.entries(data).map(([id, s], i) => ({{
      label: s.label,
      data: s.values.filter((_,j)=>j%5===0),
      borderColor: colors[i % colors.length],
      backgroundColor: 'transparent',
      borderWidth: id === 'A' ? 2 : 1.5,
      borderDash: id === 'A' ? [6,3] : [],
      pointRadius: 0,
    }}))
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ labels: {{ color:'#e2e8f0' }} }} }},
    scales: {{
      x: {{ ticks: {{ color:'#94a3b8', maxTicksLimit:15 }}, grid: {{ color:'#334155' }} }},
      y: {{ ticks: {{ color:'#94a3b8', callback: v => '$'+v.toLocaleString() }}, grid: {{ color:'#334155' }} }}
    }}
  }}
}});
</script>
</body>
</html>"""

    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"\n📁 HTML 报告已保存: {out_path}")


if __name__ == "__main__":
    print("=" * 60)
    print("  🚀 动态组数回测对比")
    print("=" * 60)

    print(f"\n📥 拉取 QQQ 数据 {START} ~ {END}...")
    df = fetch_futu_kline(TICKER, START, END)
    if df is None or df.empty:
        print("❌ 数据获取失败，退出")
        sys.exit(1)
    print(f"  ✅ {len(df)} 天  ${df['Close'].min():.0f}~${df['Close'].max():.0f}")

    results = []
    for sc in SCENARIOS:
        print(f"\n▶ 场景 {sc['id']}: {sc['label']}...")
        r = run_scenario(sc, df)
        results.append(r)
        print(
            f"   年化{r['ann_return']:+.2f}%  回撤{r['max_dd']:.2f}%  "
            f"夏普{r['sharpe']:.2f}  逐年STD={r['yearly_std']:.1f}%  "
            f"峰值组数={r['peak_groups']}  最终${r['final_value']:,.0f}"
        )

    print_summary(results)

    out = Path(__file__).parent / "backtest_results" / "dynamic_sizing_comparison.html"
    generate_html(results, out)
