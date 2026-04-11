#!/usr/bin/env python3
"""
三标的（QQQ + IWM + GLD）动态组数 vs 固定组数 对比回测
=========================================================
在单标的动态回测（dynamic_sizing_backtest.py）基础上，
验证多标的低相关分散 + 动态扩仓的组合效果。

资金分配（与实盘 main_ic_us.py 一致）：
  实际本金 $15,000  ×2 杠杆 = 名义 $30,000
  QQQ: $18,000  max_groups=4  (60%)
  IWM:  $6,000  max_groups=2  (20%)
  GLD:  $6,000  max_groups=2  (20%)

场景（groups_cap 按"组数上限倍数"统一设定）：
  A  固定（基线）          QQQ G4 / IWM G2 / GLD G2          无动态
  B  动态 3x上限           QQQ cap=12 / IWM cap=6 / GLD cap=6
  C  动态 5x上限（推荐）   QQQ cap=20 / IWM cap=10/ GLD cap=10
  D  动态 10x上限          QQQ cap=40 / IWM cap=20/ GLD cap=20
  E  动态无上限            QQQ cap=999/ IWM cap=999/GLD cap=999

输出：
  终端汇总表 + backtest_results/multi_asset_dynamic.html
"""

import sys, json, math
from pathlib import Path
from datetime import date
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline
from iron_condor_us import USIronCondorBacktester

START, END = "2010-01-01", "2025-12-31"
RISK_FREE  = 0.05
REAL_CAPITAL = 15_000  # 实际本金

# 资金分配与实盘对齐
ASSETS = [
    {"ticker": "US.QQQ", "name": "QQQ", "capital": 18_000, "base_groups": 4},
    {"ticker": "US.IWM", "name": "IWM", "capital":  6_000, "base_groups": 2},
    {"ticker": "US.GLD", "name": "GLD", "capital":  6_000, "base_groups": 2},
]

# 与 dynamic_sizing_backtest.py 对齐的策略参数
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

# 场景定义：cap_multiplier = max_groups 允许扩大的倍数
SCENARIOS = [
    {"id": "A", "label": "A  固定（基线）",         "dynamic": False, "cap_mult": 1},
    {"id": "B", "label": "B  动态  3x上限",         "dynamic": True,  "cap_mult": 3},
    {"id": "C", "label": "C  动态  5x上限（推荐）", "dynamic": True,  "cap_mult": 5},
    {"id": "D", "label": "D  动态 10x上限",         "dynamic": True,  "cap_mult": 10},
    {"id": "E", "label": "E  动态 无上限",           "dynamic": True,  "cap_mult": 999},
]


def run_asset(asset: dict, df: pd.DataFrame, dynamic: bool, cap_mult: int, sc_id: str) -> dict:
    """运行单个标的回测，返回含每日净值的结果字典"""
    groups_cap = asset["base_groups"] * cap_mult
    bt = USIronCondorBacktester(
        ticker=asset["ticker"],
        initial_capital=asset["capital"],
        max_groups=asset["base_groups"],
        dynamic_sizing=dynamic,
        groups_cap=groups_cap,
        label=f"{sc_id}-{asset['name']}",
        **IC_PARAMS,
    )
    r = bt.run(df, save_prefix=f"mad_{sc_id}_{asset['name']}")
    daily = pd.DataFrame(bt.daily_records)[["date", "total_value"]].set_index("date")
    daily.index = pd.to_datetime(daily.index)
    r["daily"] = daily
    r["bt"] = bt
    return r


def combine_portfolio(asset_results: list, assets: list) -> pd.Series:
    """
    合并多标的每日净值为组合净值。
    方法：各标的 total_value 直接相加（各自独立账户，现金不跨账户）
    """
    frames = {}
    for r, a in zip(asset_results, assets):
        frames[a["name"]] = r["daily"]["total_value"]
    df = pd.DataFrame(frames)
    df = df.dropna()
    return df.sum(axis=1)


def calc_portfolio_stats(portfolio_tv: pd.Series, total_init: float, label: str) -> dict:
    tv = portfolio_tv
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

    # 逐年收益率
    yearly_end = tv.resample("YE").last()
    yearly_ret = [(yearly_end.iloc[0] - total_init) / total_init * 100]
    for i in range(1, len(yearly_end)):
        pct = (yearly_end.iloc[i] - yearly_end.iloc[i-1]) / yearly_end.iloc[i-1] * 100
        yearly_ret.append(pct)
    yearly_years = list(yearly_end.index.year)

    return {
        "label": label,
        "initial": total_init,
        "final": round(final_v, 0),
        "ann_ret": round(ann_ret, 2),
        "max_dd": round(max_dd, 2),
        "sharpe": sharpe,
        "years": round(years, 1),
        "yearly_returns": yearly_ret,
        "yearly_years": yearly_years,
        "yearly_std": round(float(np.std(yearly_ret)), 1),
        "tv": tv,
    }


def run_scenario(sc: dict, data: dict) -> dict:
    print(f"\n  ▶ 场景 {sc['id']}: {sc['label']}")
    asset_results = []
    for a in ASSETS:
        if a["ticker"] not in data:
            print(f"    ⚠️  {a['name']} 无数据，跳过")
            continue
        r = run_asset(a, data[a["ticker"]], sc["dynamic"], sc["cap_mult"], sc["id"])
        asset_results.append((r, a))
        print(f"    {a['name']}: 年化{r['ann_return']:+.1f}%  回撤{r['max_dd']:.1f}%")

    results_list = [x[0] for x in asset_results]
    assets_list  = [x[1] for x in asset_results]

    total_init = sum(a["capital"] for _, a in asset_results)
    portfolio_tv = combine_portfolio(results_list, assets_list)

    stats = calc_portfolio_stats(portfolio_tv, total_init, sc["label"])
    stats["id"] = sc["id"]
    stats["asset_results"] = asset_results
    return stats


def print_summary(results: list):
    total_init = sum(a["capital"] for a in ASSETS)
    print(f"\n\n{'='*115}")
    print(f"  📊 三标的动态扩仓对比  —  QQQ+IWM+GLD  实际本金${REAL_CAPITAL:,}（2x杠杆=$30K）  {START[:4]}–{END[:4]}")
    print(f"{'='*115}")
    hdr = (f"  {'场景':<36}  {'年化':>8}  {'最大回撤':>9}  {'夏普':>6}  "
           f"{'逐年STD':>8}  {'最终净值':>14}")
    print(hdr)
    print("  " + "─" * 110)
    for r in results:
        marker = " ★" if r["sharpe"] == max(x["sharpe"] for x in results) else "  "
        print(f"{marker}{r['label']:<38}  {r['ann_ret']:>+7.2f}%  "
              f"{r['max_dd']:>8.2f}%  {r['sharpe']:>6.2f}  "
              f"{r['yearly_std']:>7.1f}%  ${r['final']:>13,.0f}")
    print("  " + "─" * 110)

    # 逐年收益率对比
    all_years = sorted(set(y for r in results for y in r["yearly_years"]))
    print(f"\n  📅 逐年收益率（%）对比：")
    header = f"  {'年份':>6}" + "".join(f"  {r['id']:>10}" for r in results)
    print(header)
    print("  " + "─" * (8 + 12 * len(results)))
    for yr in all_years:
        row = f"  {yr:>6}"
        for r in results:
            if yr in r["yearly_years"]:
                idx = r["yearly_years"].index(yr)
                val = r["yearly_returns"][idx]
                row += f"  {val:>+9.1f}%"
            else:
                row += f"  {'N/A':>10}"
        print(row)
    print(f"\n  逐年STD：越低代表收益越稳定，越适合实盘心态")
    print(f"{'='*115}")


def generate_html(results: list, out_path: Path):
    total_init = sum(a["capital"] for a in ASSETS)
    all_years = sorted(set(y for r in results for y in r["yearly_years"]))

    summary_rows = ""
    for r in results:
        summary_rows += (
            f"<tr><td>{r['label']}</td>"
            f"<td>{r['ann_ret']:+.2f}%</td>"
            f"<td>{r['max_dd']:.2f}%</td>"
            f"<td>{r['sharpe']:.2f}</td>"
            f"<td>{r['yearly_std']:.1f}%</td>"
            f"<td>${r['final']:,.0f}</td></tr>"
        )

    col_headers = "".join(f"<th>{r['id']}</th>" for r in results)
    year_rows = ""
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
        year_rows += row

    # 净值曲线
    equity_series = {}
    for r in results:
        equity_series[r["id"]] = {
            "label": r["label"],
            "dates": [str(d.date()) for d in r["tv"].index[::5]],
            "values": [round(v, 0) for v in r["tv"].values[::5].tolist()],
        }

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>三标的动态扩仓对比回测</title>
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
  canvas {{ max-height:440px; }}
</style>
</head>
<body>
<h1>三标的动态扩仓对比回测</h1>
<h2>QQQ + IWM + GLD · 实际本金 ${REAL_CAPITAL:,}（2x杠杆=$30K）· {START[:4]}–{END[:4]}</h2>

<div class="section">
  <h3>汇总指标</h3>
  <table>
    <tr><th>场景</th><th>年化</th><th>最大回撤</th><th>夏普</th><th>逐年STD</th><th>最终净值</th></tr>
    {summary_rows}
  </table>
</div>

<div class="section">
  <h3>组合净值曲线</h3>
  <canvas id="equityChart"></canvas>
</div>

<div class="section">
  <h3>逐年收益率（%）</h3>
  <table>
    <tr><th>年份</th>{col_headers}</tr>
    {year_rows}
  </table>
</div>

<script>
const data = {json.dumps(equity_series, ensure_ascii=False)};
const colors = ['#94a3b8','#60a5fa','#34d399','#fbbf24','#f87171'];
const ctx = document.getElementById('equityChart').getContext('2d');
new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: Object.values(data)[0].dates,
    datasets: Object.entries(data).map(([id, s], i) => ({{
      label: s.label,
      data: s.values,
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
    print("=" * 65)
    print("  🌍 三标的动态扩仓对比回测")
    print("=" * 65)

    # 拉取数据
    data = {}
    for a in ASSETS:
        print(f"\n📥 拉取 {a['name']} ({a['ticker']}) {START}~{END}...")
        df = fetch_futu_kline(a["ticker"], START, END)
        if df is None or df.empty:
            print(f"  ⚠️  {a['name']} 数据获取失败，跳过")
        else:
            data[a["ticker"]] = df
            print(f"  ✅ {len(df)} 天  ${df['Close'].min():.0f}~${df['Close'].max():.0f}")

    if "US.QQQ" not in data:
        print("❌ QQQ 数据不可用，退出")
        sys.exit(1)

    # 运行各场景
    results = []
    for sc in SCENARIOS:
        r = run_scenario(sc, data)
        results.append(r)
        print(f"  → 组合: 年化{r['ann_ret']:+.2f}%  回撤{r['max_dd']:.2f}%  "
              f"夏普{r['sharpe']:.2f}  逐年STD={r['yearly_std']}%  最终${r['final']:,.0f}")

    print_summary(results)

    out = Path(__file__).parent / "backtest_results" / "multi_asset_dynamic.html"
    generate_html(results, out)
