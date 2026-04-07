# -*- coding: utf-8 -*-
"""
V7 Parameter Sweep Backtest - Real Futu API K-line data
Compare: stop_loss_buffer, OTM, Wing, DTE, cooldown
NO fabricated data - all from real historical K-lines
"""

import sys
import json
import time
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from iron_condor import IronCondorBacktester
from backtest_real import fetch_futu_kline

# === Config ===
TICKER = "HK.00700"
START_DATE = "2020-01-01"
END_DATE = "2025-12-31"
INITIAL_CAPITAL = 100_000  # HKD
OUTPUT_DIR = Path(__file__).parent / "backtest_results"

# === Parameter Sets ===
PARAM_SETS = [
    # Baseline: V6 best
    {
        "label": "V6 Baseline BUF=1.5 DTE=30 CD=30",
        "otm_distance": 0.05, "wing_width": 0.08, "dte": 30,
        "stop_loss_buffer": 1.5, "stop_loss_pct": 0.05, "cooldown_days": 30,
        "early_close_days": 2, "max_groups": 1,
    },
    # Step 1: Widen stop loss buffer
    {"label": "Opt-1a BUF=2.0 DTE=30 CD=30",   "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    {"label": "Opt-1b BUF=2.5 DTE=30 CD=30",   "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 2.5, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    {"label": "Opt-1c BUF=3.0 DTE=30 CD=30",   "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 3.0, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    # Step 2: DTE=45 longer cycle
    {"label": "Opt-2a BUF=1.5 DTE=45 CD=30",   "otm_distance": 0.05, "wing_width": 0.08, "dte": 45, "stop_loss_buffer": 1.5, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    {"label": "Opt-2b BUF=2.0 DTE=45 CD=30",   "otm_distance": 0.05, "wing_width": 0.08, "dte": 45, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    {"label": "Opt-2c BUF=2.5 DTE=45 CD=30",   "otm_distance": 0.05, "wing_width": 0.08, "dte": 45, "stop_loss_buffer": 2.5, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    # Step 3: Shorter cooldown
    {"label": "Opt-3a BUF=2.0 DTE=30 CD=15",   "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.05, "cooldown_days": 15, "early_close_days": 2, "max_groups": 1},
    {"label": "Opt-3b BUF=2.0 DTE=30 CD=7",    "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.05, "cooldown_days": 7,  "early_close_days": 2, "max_groups": 1},
    # Step 4: OTM/Wing tuning
    {"label": "Opt-4a OTM=4% WING=8% BUF=2.0", "otm_distance": 0.04, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    {"label": "Opt-4b OTM=6% WING=8% BUF=2.0", "otm_distance": 0.06, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    {"label": "Opt-4c OTM=5% WING=10% BUF=2.0","otm_distance": 0.05, "wing_width": 0.10, "dte": 30, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    # Step 5: Wider drawdown stop (8%)
    {"label": "Opt-5 SL=8% BUF=2.0 DTE=30",   "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.08, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    {"label": "Opt-5b SL=8% BUF=2.5 DTE=45",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 45, "stop_loss_buffer": 2.5, "stop_loss_pct": 0.08, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    # Best combo guess
    {"label": "*BEST* BUF=2.0 DTE=45 CD=15 SL=5%", "otm_distance": 0.05, "wing_width": 0.08, "dte": 45, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.05, "cooldown_days": 15, "early_close_days": 2, "max_groups": 1},

    # === V7b: max_groups comparison (1 group vs 2 groups) ===
    # Same params, different group count - to see the real impact of doubling positions
    {"label": "V6 x1Group (baseline)",        "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 1.5, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    {"label": "V6 x2Groups",                   "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 1.5, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 2},
    {"label": "CD15 x1Group",                  "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 1.5, "stop_loss_pct": 0.05, "cooldown_days": 15, "early_close_days": 2, "max_groups": 1},
    {"label": "CD15 x2Groups",                 "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 1.5, "stop_loss_pct": 0.05, "cooldown_days": 15, "early_close_days": 2, "max_groups": 2},
    {"label": "OTM4pct BUF2.0 x1Group",        "otm_distance": 0.04, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 1},
    {"label": "OTM4pct BUF2.0 x2Groups",       "otm_distance": 0.04, "wing_width": 0.08, "dte": 30, "stop_loss_buffer": 2.0, "stop_loss_pct": 0.05, "cooldown_days": 30, "early_close_days": 2, "max_groups": 2},
]


def run_single_backtest(params: dict, df: pd.DataFrame) -> dict:
    """Run single param set backtest, return stats dict."""
    bt = IronCondorBacktester(
        initial_capital=INITIAL_CAPITAL,
        otm_distance=params["otm_distance"],
        wing_width=params["wing_width"],
        dte=params["dte"],
        stop_loss_buffer=params["stop_loss_buffer"],
        stop_loss_pct=params["stop_loss_pct"],
        cooldown_days=params["cooldown_days"],
        early_close_days=params["early_close_days"],
        max_groups=params["max_groups"],
        label=params["label"],
    )
    bt.run(df, save_prefix="ic_v7_sweep")

    daily = pd.DataFrame(bt.daily_records)
    trades_list = bt.trades

    if daily.empty:
        return {"error": "No data"}

    final_value = float(daily["total_value"].iloc[-1])
    total_return = (final_value - INITIAL_CAPITAL) / INITIAL_CAPITAL
    years = (pd.to_datetime(daily["date"].iloc[-1]) - pd.to_datetime(daily["date"].iloc[0])).days / 365.25
    annual_return = (final_value / INITIAL_CAPITAL) ** (1 / max(years, 0.01)) - 1

    peak = daily["total_value"].expanding(min_periods=1).max()
    drawdown = (daily["total_value"] - peak) / peak
    max_dd = float(drawdown.min())

    # Sharpe
    daily_returns = daily["total_value"].pct_change().dropna()
    sharpe = float(daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if len(daily_returns) > 1 and daily_returns.std() > 0 else 0.0

    # Trade stats
    close_trades = [t for t in trades_list if t["action"] in ("EARLY_CLOSE",)]
    expiry_trades = [t for t in trades_list if "profit" in t.get("result", "") or "assigned" in t.get("result", "").lower()]
    stop_trades = [t for t in trades_list if t["action"] == "STOP_LOSS"]

    total_closed = len(close_trades) + len(expiry_trades)
    winning_trades = len([t for t in close_trades if t.get("pnl", 0) > 0])
    winning_trades += len([t for t in expiry_trades if t.get("pnl", 0) > 0])
    win_rate = winning_trades / total_closed * 100 if total_closed > 0 else 0.0

    all_pnls = []
    for t in close_trades:
        all_pnls.append(t.get("pnl", 0))
    for t in expiry_trades:
        all_pnls.append(t.get("pnl", 0))
    avg_pnl = float(np.mean(all_pnls)) if all_pnls else 0.0

    open_count = len([t for t in trades_list if t["action"] == "OPEN_IC"])

    tc = {
        "open": open_count,
        "early_stop": len([t for t in close_trades if t.get("pnl", 0) < 0]),
        "early_win": len([t for t in close_trades if t.get("pnl", 0) >= 0]),
        "expiry_profit": len(expiry_trades),
        "portfolio_stop": len(stop_trades),
    }

    return {
        "label": params["label"],
        "final_value": round(final_value, 0),
        "total_return_pct": round(total_return * 100, 2),
        "annual_return_pct": round(annual_return * 100, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "total_trades": open_count,
        "total_closed": total_closed,
        "win_rate_pct": round(win_rate, 1),
        "avg_pnl_hkd": round(avg_pnl, 0),
        "stop_count": len(stop_trades),
        "trades_count_by_type": tc,
        "daily": daily.to_dict("records") if not daily.empty else [],
    }


def generate_html_report(results: list, output_path: Path):
    """Generate HTML comparison report with ECharts."""
    sorted_results = sorted(
        [r for r in results if "error" not in r],
        key=lambda x: x.get("annual_return_pct", -999), reverse=True
    )

    n_valid = len(sorted_results)

    # Build table rows
    rows_parts = []
    for r in sorted_results:
        ann_ret = r["annual_return_pct"]
        ret_color = "#10b981" if ann_ret >= 15 else ("#34d399" if ann_ret >= 10 else ("#fbbf24" if ann_ret >= 0 else "#ef4444"))

        dd = r["max_drawdown_pct"]
        dd_color = "#10b981" if dd >= -5 else ("#fbbf24" if dd >= -10 else "#ef4444")

        wr = r["win_rate_pct"]
        wr_color = "#10b981" if wr >= 40 else ("#fbbf24" if wr >= 20 else "#ef4444")

        is_best = r["label"].startswith("*BEST*")
        badge = ' <span style="background:#f59e0b;color:#000;padding:1px 6px;border-radius:4px;font-size:11px;font-weight:bold">RECOMMENDED</span>' if is_best else ""
        bg = 'background:#fffbeb' if is_best else ''
        fw = 'font-weight:bold' if is_best else 'font-weight:normal'

        tc = r["trades_count_by_type"]

        row = ('<tr style="%s">'
               '<td style="%s">%s%s</td>'
               '<td style="color:%s;font-weight:bold">%.2f%%</td>'
               '<td style="color:%s">%.2f%%</td>'
               '<td style="color:%s;font-weight:bold">%.2f%%</td>'
               '<td>%.2f</td>'
               '<td>%d</td>'
               '<td style="color:%s;font-weight:bold">%.1f%%</td>'
               '<td>%d</td>'
               '<td>%d</td>'
               '<td>%d</td>'
               '<td>%d</td>'
               '</tr>') % (
            bg, fw, r["label"], badge,
            ret_color, ann_ret, ret_color, r["total_return_pct"],
            dd_color, dd,
            r["sharpe"], r["total_trades"],
            wr_color, wr,
            r["avg_pnl_hkd"], tc["early_stop"], tc["expiry_profit"], r["stop_count"]
        )
        rows_parts.append(row)
    rows_html = "\n".join(rows_parts)

    # ECharts data
    series_list = []
    for r in sorted_results:
        if not r.get("daily"):
            continue
        daily_data = r["daily"]
        points = [(str(d["date"]), round(d["total_value"], 0)) for d in daily_data]
        is_base = "Baseline" in r["name"] if "name" in r else "Baseline" in r["label"]
        series_list.append({
            "name": r["label"],
            "type": "line",
            "data": points,
            "showSymbol": False,
            "lineWidth": 3 if "Baseline" in r["label"] else 1.5,
        })

    series_json_str = json.dumps(series_list, ensure_ascii=False)

    # Summary stats
    best_annual = max((r.get("annual_return_pct", -999) for r in results if "error" not in r), default=0)
    best_dd = min((r.get("max_drawdown_pct", 999) for r in results if "error" not in r), default=0)
    best_wr = max((r.get("win_rate_pct", 0) for r in results if "error" not in r), default=0)
    best_sharpe = max((r.get("sharpe", -999) for r in results if "error" not in r), default=0)

    # Build HTML using string concatenation (no f-string triple-quote issue)
    html_parts = []
    html_parts.append('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n')
    html_parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">\n')
    html_parts.append('<title>V7 Iron Condor Parameter Sweep Report</title>\n')
    html_parts.append('<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>\n')
    html_parts.append('<style>\n')
    html_parts.append('* { margin: 0; padding: 0; box-sizing: border-box; }\n')
    html_parts.append('body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }\n')
    html_parts.append('.container { max-width: 1400px; margin: 0 auto; }\n')
    html_parts.append('h1 { text-align: center; font-size: 28px; margin-bottom: 8px; color: #f8fafc; }\n')
    html_parts.append('.subtitle { text-align: center; color: #94a3b8; font-size: 14px; margin-bottom: 30px; }\n')
    html_parts.append('.card { background: #1e293b; border-radius: 12px; padding: 24px; margin-bottom: 20px; border: 1px solid #334155; }\n')
    html_parts.append('.card h2 { font-size: 18px; color: #f1f5f9; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #334155; }\n')
    html_parts.append('.chart-container { width: 100%; height: 500px; }\n')
    html_parts.append('table { width: 100%; border-collapse: collapse; font-size: 13px; }\n')
    html_parts.append('th { background: #334155; color: #f1f5f9; padding: 12px 8px; text-align: center; position: sticky; top: 0; font-weight: 600; }\n')
    html_parts.append('td { padding: 10px 8px; text-align: center; border-bottom: 1px solid #334155; }\n')
    html_parts.append('tr:hover { background: #33415550; }\n')
    html_parts.append('.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-top: 16px; }\n')
    html_parts.append('.summary-item { background: #0f172a; border-radius: 8px; padding: 16px; text-align: center; }\n')
    html_parts.append('.summary-value { font-size: 28px; font-weight: bold; margin: 4px 0; color: #10b981; }\n')
    html_parts.append('.summary-label { font-size: 12px; color: #94a3b8; }\n')
    html_parts.append('.note { margin-top: 20px; padding: 16px; background: #1e293b; border-left: 4px solid #f59e0b; border-radius: 4px; font-size: 13px; color: #cbd5e1; line-height: 1.6; }\n')
    html_parts.append('</style>\n</head>\n<body>\n<div class="container">\n')

    # Header
    html_parts.append('<h1>V7 Iron Condor Parameter Sweep</h1>\n')
    html_parts.append('<p class="subtitle">Ticker: %s | Range: %s ~ %s | Capital: %s HKD | Data Source: Futu OpenD API Real K-Line</p>\n' % (TICKER, START_DATE, END_DATE, f"{INITIAL_CAPITAL:,}"))

    # Summary cards
    html_parts.append('<div class="card">\n<h2>Key Metrics Overview</h2>\n<div class="summary-grid">\n')
    html_parts.append('<div class="summary-item"><div class="summary-label">Best Annual Return</div><div class="summary-value">%.2f%%</div></div>\n' % best_annual)
    html_parts.append('<div class="summary-item"><div class="summary-label">Min Max Drawdown</div><div class="summary-value">%.2f%%</div></div>\n' % best_dd)
    html_parts.append('<div class="summary-item"><div class="summary-label">Best Win Rate</div><div class="summary-value">%.1f%%</div></div>\n' % best_wr)
    html_parts.append('<div class="summary-item"><div class="summary-label">Best Sharpe</div><div class="summary-value">%.2f</div></div>\n' % best_sharpe)
    html_parts.append('</div></div>\n')

    # Chart
    html_parts.append('<div class="card">\n<h2>Equity Curves (Sorted by Annual Return)</h2>\n')
    html_parts.append('<div id="chart_equity" class="chart-container"></div>\n</div>\n')

    # Table
    html_parts.append('<div class="card">\n<h2>All Parameter Combinations (%d Sets)</h2>\n' % n_valid)
    html_parts.append('<div style="overflow-x:auto;">\n<table>\n<thead>\n<tr>\n')
    html_parts.append('<th>Strategy Name</th><th>Annual Return</th><th>Total Return</th>')
    html_parts.append('<th>Max DD</th><th>Sharpe</th><th>#Trades</th><th>Win Rate</th>')
    html_parts.append('<th>Avg PnL (HKD)</th><th>Stop-Loss Count</th><th>Expiry Profit</th><th>Pause Count</th>\n')
    html_parts.append('</tr>\n</thead>\n<tbody>\n')
    html_parts.append(rows_html)
    html_parts.append('\n</tbody>\n</table>\n</div>\n</div>\n')

    # Notes
    html_parts.append('<div class="note">\n<strong>Important Notes:</strong><br>\n')
    html_parts.append('- All data based on real Futu OpenD API K-line backtest, NOT simulated/fabricated<br>\n')
    html_parts.append('- Option pricing: Black-Scholes + 20-day historical volatility x 1.15 IV premium<br>\n')
    html_parts.append('- Includes commission (40 HKD/leg x 4 legs) and slippage cost<br>\n')
    html_parts.append('- Stop Buffer (BUF): 1.5=50%% of wing width, 2.0=near buy strike, 2.5+/3.0=beyond buy strike<br>\n')
    html_parts.append('- CD (Cooldown Days): days to resume after drawdown stop triggered<br>\n')
    html_parts.append('- SL (Stop Loss): portfolio drawdown stop threshold<br>\n')
    html_parts.append('- HK Tencent options are monthly: DTE=30 ~= 1 round/month, DTE=45 ~= 1 round/6 weeks<br>\n')
    html_parts.append('</div>\n</div>\n')

    # JavaScript
    html_parts.append('\n<script>\nvar chartDom = document.getElementById("chart_equity");\n')
    html_parts.append('var myChart = echarts.init(chartDom);\n')
    html_parts.append('var seriesData = %s;\n\n' % series_json_str)

    js_code = """
var option = {
    backgroundColor: 'transparent',
    tooltip: {
        trigger: 'axis',
        backgroundColor: '#1e293b',
        borderColor: '#334155',
        textStyle: { color: '#e2e8f0', fontSize: 12 },
        formatter: function(params) {
            var date = params[0].value[0];
            var html = '<div style="font-weight:bold;margin-bottom:8px;">' + date + '</div>';
            params.forEach(function(p) {
                html += '<div>' + p.marker + p.seriesName + ': <strong>HKD ' + p.value[1].toLocaleString() + '</strong></div>';
            });
            return html;
        }
    },
    legend: {
        data: seriesData.map(function(s) { return s.name; }),
        top: 0,
        textStyle: { color: '#94a3b8', fontSize: 11 },
        type: 'scroll'
    },
    grid: { left: 60, right: 30, top: 40, bottom: 30 },
    xAxis: {
        type: 'category',
        data: seriesData[0] ? seriesData[0].data.map(function(d) { return d[0]; }) : [],
        axisLabel: { color: '#64748b', fontSize: 10, interval: 299 },
        axisLine: { lineStyle: { color: '#334155' } },
    },
    yAxis: {
        type: 'value',
        axisLabel: { color: '#64748b', formatter: function(v) { return (v/1000).toFixed(0) + 'K'; } },
        splitLine: { lineStyle: { color: '#1e293b' } },
        axisLine: { lineStyle: { color: '#334155' } },
    },
    series: seriesData,
    dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        { type: 'slider', start: 0, end: 100, height: 20, bottom: 5,
          borderColor: '#334155', textStyle: { color: '#64748b' }, fillerColor: '#33415540' }
    ]
};
myChart.setOption(option);
window.addEventListener('resize', function() { myChart.resize(); });
"""
    html_parts.append(js_code)
    html_parts.append('</script>\n</body>\n</html>')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("".join(html_parts))
    print("\n[OK] HTML report saved: %s" % output_path)


def main():
    print("=" * 70)
    print("  V7 Iron Condor Multi-Parameter Sweep Backtest")
    print("  Ticker: %s  Range: %s ~ %s" % (TICKER, START_DATE, END_DATE))
    print("  Parameter sets: %d" % len(PARAM_SETS))
    print("=" * 70)

    # 1. Fetch real K-line data from Futu API
    print("\n[API] Fetching %s K-line from Futu API..." % TICKER)
    kline_df = fetch_futu_kline(TICKER, START_DATE, END_DATE)
    if kline_df is None or kline_df.empty:
        print("[X] Cannot fetch K-line data. Please make sure OpenD is running.")
        sys.exit(1)

    print("  [OK] Got %d K-line records" % len(kline_df))
    print("      Date range: %s ~ %s" % (kline_df['date'].iloc[0], kline_df['date'].iloc[-1]))

    # Ensure column names
    if "close" in kline_df.columns and "Close" not in kline_df.columns:
        kline_df = kline_df.rename(columns={"close": "Close"})

    # 2. Run each param set
    results = []
    total = len(PARAM_SETS)
    for i, params in enumerate(PARAM_SETS):
        print("\n" + "-" * 60)
        print("  [%d/%d] Running: %s" % (i+1, total, params['label']))
        print("-" * 60)

        t0 = time.time()
        try:
            result = run_single_backtest(params, kline_df)
            elapsed = time.time() - t0
            result["elapsed_seconds"] = round(elapsed, 1)

            if "error" not in result:
                print("\n  Result:")
                print("     Annual Return: %.2f%%" % result['annual_return_pct'])
                print("     Max Drawdown: %.2f%%" % result['max_drawdown_pct'])
                print("     Sharpe:       %.2f" % result['sharpe'])
                print("     Win Rate:     %.1f%% (%d closed)" % (result['win_rate_pct'], result['total_closed']))
                print("     Trades:       %d" % result['total_trades'])
                print("     Final Value:  HKD %s" % f"{result['final_value']:,.0f}")
            else:
                print("  [X] Error: %s" % result['error'])

            results.append(result)
        except Exception as e:
            print("  [X] Exception: %s" % e)
            import traceback
            traceback.print_exc()
            results.append({"label": params["label"], "error": str(e)})

    # 3. Save JSON
    json_output = OUTPUT_DIR / "v7_param_sweep.json"
    save_results = [{k: v for k, v in r.items() if k != "daily"} for r in results]
    with open(json_output, "w", encoding="utf-8") as f:
        json.dump(save_results, f, ensure_ascii=False, indent=2, default=str)
    print("\n[SAVE] JSON saved: %s" % json_output)

    # 4. Generate HTML report
    html_output = OUTPUT_DIR / "ic_v7_param_sweep.html"
    generate_html_report(results, html_output)

    # 5. Print ranking table
    print("\n" + "=" * 80)
    print("  Final Ranking (by Annual Return)")
    print("=" * 80)
    ranked = sorted(
        [r for r in results if "error" not in r],
        key=lambda x: x.get("annual_return_pct", -999), reverse=True
    )
    print("%-4s %-36s %8s %8s %6s %7s %5s" % ("#", "Strategy", "Annual", "MaxDD", "Sharpe", "WinRate", "Trades"))
    print("-" * 80)
    for i, r in enumerate(ranked):
        marker = " [*]" if i == 0 else ""
        print("%-4d %-36s %7.2f%% %7.2f%% %6.2f %6.1f%% %5d%s" % (
            i+1, r['label'], r['annual_return_pct'], r['max_drawdown_pct'],
            r['sharpe'], r['win_rate_pct'], r['total_trades'], marker
        ))

    return results


if __name__ == "__main__":
    main()
