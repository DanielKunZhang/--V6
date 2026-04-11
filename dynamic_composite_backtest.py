#!/usr/bin/env python3
"""
动态组数 vs 固定组数 对比回测（正式参数版）
=============================================
基于 composite_backtest.py 的 EnhancedICBacktester，
使用与实盘 main_ic_us.py 完全一致的参数：
  - 非对称 OTM: Put 3.0% / Call 6.0%
  - Wing 9%,  DTE 45
  - VIX 硬止损: HV20 ≥ 39% 强制平仓
  - VIX 冷却期: HV20 < 28% 恢复开仓
  - VIX 去杠杆: HV20 > 22% 动态组数减半

资金分配（与实盘对齐）：
  实际本金 $15,000 × 2x 杠杆 = 名义 $30,000
  QQQ: $18,000  base_groups=4  (60%)
  IWM:  $6,000  base_groups=2  (20%)
  GLD:  $6,000  base_groups=2  (20%)

场景：
  A  固定（基线）       max_groups 固定，不随净值扩仓
  C  动态  5x上限       effective_groups = base × (cash/initial), cap = base×5
  D  动态 10x上限       effective_groups = base × (cash/initial), cap = base×10

输出：终端汇总表 + backtest_results/dynamic_composite.html
"""

import sys, json, math
from pathlib import Path
from datetime import date
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline
from composite_backtest import EnhancedICBacktester, VIX_HARD_STOP_HV, VIX_COOLDOWN_HV

START, END = "2010-01-01", "2025-12-31"
RISK_FREE  = 0.05
REAL_CAPITAL = 15_000

# 资金分配与实盘完全对齐
ASSETS = [
    {"ticker": "US.QQQ", "name": "QQQ", "capital": 18_000, "base_groups": 4},
    {"ticker": "US.IWM", "name": "IWM", "capital":  6_000, "base_groups": 2},
    {"ticker": "US.GLD", "name": "GLD", "capital":  6_000, "base_groups": 2},
]

# 与实盘 main_ic_us.py 完全一致的 IC 参数（不得修改）
IC_PARAMS = dict(
    put_otm=0.030,                   # 非对称：卖 Put OTM=3%
    call_otm=0.060,                  # 非对称：卖 Call OTM=6%
    otm_distance=0.05,               # 父类兼容（不实际使用，被 put/call_otm 覆盖）
    wing_width=0.09,
    dte=45,
    stop_loss_pct=0.05,
    stop_loss_buffer=1.5,
    early_close_days=2,
    entry_mode="pre_expiry",
    entry_days_before_expiry=45,
    cooldown_days=5,
    vix_hard_stop_hv=VIX_HARD_STOP_HV,   # 0.39
    vix_cooldown_hv=VIX_COOLDOWN_HV,      # 0.28
    vix_deleverage_hv=0.22,               # 去杠杆阈值
    profit_target_pct=0.50,               # 50%止盈（与实盘对齐）
)

# 场景：动态扩仓上限倍数
SCENARIOS = [
    {"id": "A",  "label": "A  固定（基线）",    "dynamic": False, "cap_mult": 1},
    {"id": "C",  "label": "C  动态  5x上限",   "dynamic": True,  "cap_mult": 5},
    {"id": "D",  "label": "D  动态 10x上限",   "dynamic": True,  "cap_mult": 10},
    {"id": "E",  "label": "E  动态 15x上限",   "dynamic": True,  "cap_mult": 15},
    {"id": "F",  "label": "F  动态 20x上限",   "dynamic": True,  "cap_mult": 20},
]


def run_asset(asset: dict, df: pd.DataFrame, dynamic: bool, cap_mult: int, sc_id: str) -> dict:
    """运行单标的回测，返回含每日净值的结果字典"""
    groups_cap = asset["base_groups"] * cap_mult
    bt = EnhancedICBacktester(
        ticker=asset["ticker"],
        initial_capital=asset["capital"],
        max_groups=asset["base_groups"],
        dynamic_sizing=dynamic,
        groups_cap=groups_cap,
        label=f"{sc_id}-{asset['name']}",
        **IC_PARAMS,
    )
    bt.run(df, save_prefix=f"dcmp_{sc_id}_{asset['name']}")
    daily = pd.DataFrame(bt.daily_records)[["date", "total_value"]].set_index("date")
    daily.index = pd.to_datetime(daily.index)

    # 计算单标的年化、回撤（供打印参考）
    tv = daily["total_value"]
    years = (tv.index[-1] - tv.index[0]).days / 365.0
    total_ret = (tv.iloc[-1] - asset["capital"]) / asset["capital"] * 100
    ann_ret = ((1 + total_ret / 100) ** (1 / max(years, 0.1)) - 1) * 100
    peak = tv.cummax()
    max_dd = ((tv - peak) / peak * 100).min()

    return {
        "daily": daily,
        "ann_return": round(ann_ret, 1),
        "max_dd": round(max_dd, 1),
    }


def combine_portfolio(asset_results: list, assets: list) -> pd.Series:
    """合并各标的每日净值（各自独立账户，直接求和）"""
    frames = {a["name"]: r["daily"]["total_value"]
              for r, a in zip(asset_results, assets)}
    return pd.DataFrame(frames).dropna().sum(axis=1)


def calc_portfolio_stats(portfolio_tv: pd.Series, total_init: float, label: str) -> dict:
    tv = portfolio_tv
    years = (tv.index[-1] - tv.index[0]).days / 365.0
    total_ret = (tv.iloc[-1] - total_init) / total_init * 100
    ann_ret = ((1 + total_ret / 100) ** (1 / max(years, 0.1)) - 1) * 100

    peak = tv.cummax()
    dd = (tv - peak) / peak * 100
    max_dd = dd.min()

    dr = tv.pct_change().dropna()
    rf_d = RISK_FREE / 252
    sharpe = round((dr - rf_d).mean() / (dr - rf_d).std() * math.sqrt(252), 2) \
        if dr.std() > 1e-10 else 0

    # 逐年收益率
    yearly_end = tv.resample("YE").last()
    yearly_ret = [(yearly_end.iloc[0] - total_init) / total_init * 100]
    for i in range(1, len(yearly_end)):
        pct = (yearly_end.iloc[i] - yearly_end.iloc[i-1]) / yearly_end.iloc[i-1] * 100
        yearly_ret.append(pct)
    yearly_years = list(yearly_end.index.year)

    # 年内最大回撤（逐年）
    yearly_maxdd = []
    for yr in yearly_years:
        seg = tv[tv.index.year == yr]
        if len(seg) < 2:
            yearly_maxdd.append(0.0)
            continue
        pk = seg.cummax()
        yearly_maxdd.append(round(((seg - pk) / pk * 100).min(), 1))

    return {
        "label": label,
        "initial": total_init,
        "final": round(tv.iloc[-1], 0),
        "ann_ret": round(ann_ret, 2),
        "max_dd": round(max_dd, 2),
        "sharpe": sharpe,
        "years": round(years, 1),
        "yearly_returns": yearly_ret,
        "yearly_years": yearly_years,
        "yearly_maxdd": yearly_maxdd,
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
    print(f"\n\n{'='*120}")
    print(f"  📊 动态组数对比（正式参数）— Put3%/Call6% W9% DTE45 VIX止损 — QQQ+IWM+GLD")
    print(f"  实际本金${REAL_CAPITAL:,}（2x杠杆=$30K）  {START[:4]}–{END[:4]}")
    print(f"{'='*120}")
    hdr = (f"  {'场景':<36}  {'年化':>8}  {'最大回撤':>9}  {'夏普':>6}  "
           f"{'逐年STD':>8}  {'最终净值':>14}")
    print(hdr)
    print("  " + "─" * 115)
    for r in results:
        marker = " ★" if r["sharpe"] == max(x["sharpe"] for x in results) else "  "
        print(f"{marker}{r['label']:<38}  {r['ann_ret']:>+7.2f}%  "
              f"{r['max_dd']:>8.2f}%  {r['sharpe']:>6.2f}  "
              f"{r['yearly_std']:>7.1f}%  ${r['final']:>13,.0f}")
    print("  " + "─" * 115)

    # 逐年收益率 + 年内最大回撤对比
    all_years = sorted(set(y for r in results for y in r["yearly_years"]))

    # 市场背景注释（仅供参考）
    mkt = {
        2010: "正常牛市", 2011: "欧债危机", 2012: "正常牛市", 2013: "低VIX牛市",
        2014: "低VIX牛市", 2015: "中国股灾", 2016: "英国脱欧/特朗普",
        2017: "低VIX牛市⚠️", 2018: "Q4大跌/贸易战⚠️", 2019: "低VIX牛市⚠️",
        2020: "COVID⚠️", 2021: "牛市+通胀", 2022: "加息熊市⚠️",
        2023: "AI反弹", 2024: "AI牛市", 2025: "关税战⚠️",
    }

    print(f"\n  📅 逐年收益（%）+ 年内最大回撤（括号内）：")
    ids = [r["id"] for r in results]
    header = f"  {'年份':>6}" + "".join(f"  {id_:>10}({'DD':>5})" for id_ in ids) + "  市场背景"
    print(header)
    print("  " + "─" * (8 + 19 * len(results) + 12))
    for yr in all_years:
        row = f"  {yr:>6}"
        for r in results:
            if yr in r["yearly_years"]:
                idx = r["yearly_years"].index(yr)
                ret = r["yearly_returns"][idx]
                dd  = r["yearly_maxdd"][idx]
                row += f"  {ret:>+9.1f}%({dd:>5.1f}%)"
            else:
                row += f"  {'N/A':>16}"
        row += f"  {mkt.get(yr, '')}"
        print(row)

    print(f"\n  逐年STD：越低代表收益越稳定，越适合实盘心态")
    print(f"  最大回撤（全期）: " + "  ".join(f"{r['id']}={r['max_dd']:.1f}%" for r in results))
    print(f"{'='*120}")


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

    col_headers = "".join(f"<th>{r['id']}收益</th><th>{r['id']}年内DD</th>" for r in results)
    year_rows = ""
    for yr in all_years:
        row = f"<tr><td>{yr}</td>"
        for r in results:
            if yr in r["yearly_years"]:
                idx = r["yearly_years"].index(yr)
                ret = r["yearly_returns"][idx]
                dd  = r["yearly_maxdd"][idx]
                color = "#22c55e" if ret >= 0 else "#ef4444"
                row += f'<td style="color:{color}">{ret:+.1f}%</td>'
                row += f'<td style="color:#f87171">{dd:.1f}%</td>'
            else:
                row += "<td>—</td><td>—</td>"
        row += "</tr>"
        year_rows += row

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
<title>动态组数对比回测（正式参数）</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:20px; }}
  h1 {{ color:#f8fafc; text-align:center; margin-bottom:4px; }}
  h2 {{ color:#94a3b8; font-size:13px; text-align:center; margin-top:0; }}
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
<h1>动态组数对比回测（正式参数版）</h1>
<h2>Put3%/Call6% · Wing9% · DTE45 · VIX硬止损39%/冷却28%/去杠杆22% · QQQ+IWM+GLD · $15,000本金 · {START[:4]}–{END[:4]}</h2>

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
  <h3>逐年收益率（%）+ 年内最大回撤</h3>
  <table>
    <tr><th>年份</th>{col_headers}</tr>
    {year_rows}
  </table>
</div>

<script>
const data = {json.dumps(equity_series, ensure_ascii=False)};
const colors = ['#94a3b8','#34d399','#fbbf24'];
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
    print("=" * 70)
    print("  🚀 动态组数对比回测（正式参数 Put3%/Call6% VIX控制）")
    print("=" * 70)

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

    out = Path(__file__).parent / "backtest_results" / "dynamic_composite.html"
    generate_html(results, out)
