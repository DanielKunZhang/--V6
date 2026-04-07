#!/usr/bin/env python3
"""
Iron Condor V3 参数扫描回测脚本
====================================
基于AI助手4个优化建议的完整验证：

1. 分位数波动率回测（低/中/高三档IV环境）
2. 止损缓冲对比（buffer=1.0 vs 1.5 vs 2.0）
3. 动态滑点 vs 固定滑点
4. 凯利公式仓位管理 vs 固定仓位

运行方式：
    cd wheel_tencent && python3 param_sweep_v3.py
"""

import sys
import json
import time
from pathlib import Path
from datetime import date

import pandas as pd
import numpy as np

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))
from iron_condor import IronCondorBacktester, fetch_futu_kline


# ──────────────────────────────────────────────
#  V3 参数矩阵
# ──────────────────────────────────────────────

def get_v3_param_matrix():
    """
    返回V3参数扫描矩阵，分为4个对比维度
    
    维度1: 核心参数（基准组 + 最优竞争者）
    维度2: IV过滤模式（固定阈值 vs 分位数）
    维度3: 止损缓冲（不同敏感度）
    维度4: 滑点和凯利模型
    """
    
    matrix = []
    
    # ════════════════════════════════════════════
    #  基准组：V2最优参数（无V3增强）作为对照组
    # ════════════════════════════════════════════
    matrix.append({
        "id": "V2-BASE",
        "group": "基准",
        "label": "V2基线 (5%OTM 8%Wing DTE30 无增强)",
        "params": dict(
            otm_distance=0.05, wing_width=0.08, dte=30,
            stop_loss_buffer=1.0,
            stop_loss_confirm_days=0,
            dynamic_slippage=False,
            iv_filter_mode="fixed",
            kelly_fraction=0.0,
        ),
    })
    
    # ════════════════════════════════════════════
    #  维度A：止损缓冲测试（核心优化 #2）
    # ════════════════════════════════════════════
    for buf in [1.3, 1.5, 1.8, 2.0]:
        matrix.append({
            "id": f"BUF-{buf}",
            "group": "A-止损缓冲",
            "label": f"缓冲{buf}x (5%OTM 8%Wing DTE30)",
            "params": dict(
                otm_distance=0.05, wing_width=0.08, dte=30,
                stop_loss_buffer=buf,
                stop_loss_confirm_days=0,
                dynamic_slippage=True,
                iv_filter_mode="fixed",
                kelly_fraction=0.0,
            ),
        })
    
    # 时间过滤变体
    matrix.append({
        "id": "BUF1.5-C1D",
        "group": "A-止损缓冲",
        "label": f"缓冲1.5x+1天确认 (5%OTM 8%Wing DTE30)",
        "params": dict(
            otm_distance=0.05, wing_width=0.08, dte=30,
            stop_loss_buffer=1.5,
            stop_loss_confirm_days=1,
            dynamic_slippage=True,
            iv_filter_mode="fixed",
            kelly_fraction=0.0,
        ),
    })
    
    # ════════════════════════════════════════════
    #  维度B：分位数波动率回测（核心优化 #1）
    # ════════════════════════════════════════════
    for pct_low, pct_high, name in [
        (0, 40, "低波动(<P40)"),
        (25, 75, "中波动(P25-P75)"),
        (60, 100, "高波动(>P60)"),
    ]:
        matrix.append({
            "id": f"IV-P{pct_low}-{pct_high}",
            "group": "B-IV分位数",
            "label": f"{name} (5%OTM 8%Wing DTE30 缓冲1.5x)",
            "params": dict(
                otm_distance=0.05, wing_width=0.08, dte=30,
                stop_loss_buffer=1.5,
                stop_loss_confirm_days=0,
                dynamic_slippage=True,
                iv_filter_mode="percentile",
                iv_percentile_low=pct_low,
                iv_percentile_high=pct_high,
                kelly_fraction=0.0,
            ),
        })
    
    # ════════════════════════════════════════════
    #  维度C：滑点模型对比（核心优化 #3）
    # ════════════════════════════════════════════
    matrix.append({
        "id": "SLIP-FIXED",
        "group": "C-滑点模型",
        "label": f"固定滑点 (缓冲1.5x)",
        "params": dict(
            otm_distance=0.05, wing_width=0.08, dte=30,
            stop_loss_buffer=1.5,
            dynamic_slippage=False,
            iv_filter_mode="fixed",
            kelly_fraction=0.0,
        ),
    })
    matrix.append({
        "id": "SLIP-DYN",
        "group": "C-滑点模型",
        "label": f"动态滑点 (缓冲1.5x)",
        "params": dict(
            otm_distance=0.05, wing_width=0.08, dte=30,
            stop_loss_buffer=1.5,
            dynamic_slippage=True,
            iv_filter_mode="fixed",
            kelly_fraction=0.0,
        ),
    })
    
    # ════════════════════════════════════════════
    #  维度D：凯利公式仓位管理（核心优化 #4）
    # ════════════════════════════════════════════
    for kelly_pct in [0.25, 0.50, 0.75]:
        matrix.append({
            "id": f"KELLY-{int(kelly_pct*100)}",
            "group": "D-凯利管理",
            "label": f"凯利{kelly_pct:.0%} (缓冲1.5x 动态滑点)",
            "params": dict(
                otm_distance=0.05, wing_width=0.08, dte=30,
                stop_loss_buffer=1.5,
                dynamic_slippage=True,
                iv_filter_mode="fixed",
                kelly_fraction=kelly_pct,
            ),
        })
    
    return matrix


# ──────────────────────────────────────────────
#  回测执行器
# ──────────────────────────────────────────────

def run_single_backtest(cfg: dict, df: pd.DataFrame, capital: float = 100_000) -> dict:
    """运行单个回测配置"""
    params = cfg["params"]
    
    bt = IronCondorBacktester(
        initial_capital=capital,
        otm_distance=params.get("otm_distance", 0.05),
        wing_width=params.get("wing_width", 0.08),
        dte=params.get("dte", 30),
        label=cfg["label"],
        min_iv=0.20,           # 固定模式下用20%
        early_close_days=2,
        max_loss_pct=0.02,
        stop_loss_pct=0.10,     # 总回撤10%止损（比之前宽松一点）
        max_groups=2,           # 最多2组
        entry_mode="dte",
        # V3参数
        stop_loss_buffer=params.get("stop_loss_buffer", 1.0),
        stop_loss_confirm_days=params.get("stop_loss_confirm_days", 0),
        dynamic_slippage=params.get("dynamic_slippage", False),
        iv_filter_mode=params.get("iv_filter_mode", "fixed"),
        iv_percentile_low=params.get("iv_percentile_low", 25),
        iv_percentile_high=params.get("iv_percentile_high", 75),
        kelly_fraction=params.get("kelly_fraction", 0.0),
    )
    
    bt.run(df)
    result = bt.print_report(save_prefix=f"v3_{cfg['id']}")
    result["config_id"] = cfg["id"]
    result["group"] = cfg["group"]
    return result


# ──────────────────────────────────────────────
#  主流程
# ──────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  🦅 Iron Condor V3 参数扫描回测")
    print("     验证: 止损缓冲 / IV分位数 / 动态滑点 / 凯利公式")
    print("=" * 70)
    
    # 获取数据
    print("\n📥 获取腾讯历史K线数据...")
    df = fetch_futu_kline("HK.00700", "2020-01-01", "2025-12-31")
    if df is None or df.empty:
        print("❌ 无法获取数据")
        sys.exit(1)
    
    print(f"  📈 数据范围: {df['date'].iloc[0]} ~ {df['date'].iloc[-1]} ({len(df)}个交易日)")
    print(f"  💰 价格范围: HKD {df['Close'].min():.1f} ~ {df['Close'].max():.1f}")
    
    # 获取参数矩阵
    param_matrix = get_v3_param_matrix()
    print(f"\n🔬 共 {len(param_matrix)} 组参数待测试\n")
    
    # 执行所有回测
    results = []
    total_start = time.time()
    
    for i, cfg in enumerate(param_matrix):
        group = cfg["group"]
        label = cfg["label"]
        
        print(f"\n{'━'*70}")
        print(f"  [{i+1}/{len(param_matrix)}] [{group}] {label}")
        print(f"{'━'*70}")
        
        t0 = time.time()
        try:
            r = run_single_backtest(cfg, df, capital=100_000)
            elapsed = time.time() - t0
            r["elapsed_sec"] = round(elapsed, 1)
            results.append(r)
            
            print(f"  ⏱️  耗时 {elapsed:.1f}s | "
                  f"年化{r['ann_return']:+.1f}% | "
                  f"回撤{r['max_dd']:.2f}% | "
                  f"胜率{r['win_rate']:.0f}% | "
                  f"开仓{r['n_open']}次")
        except Exception as e:
            print(f"  ❌ 回测失败: {e}")
            import traceback
            traceback.print_exc()
    
    total_elapsed = time.time() - total_start
    
    # 过滤有效结果
    valid_results = [r for r in results if r.get('ann_return') is not None]
    print(f"\n✅ 完成: {len(valid_results)}/{len(param_matrix)} 组成功, 总耗时 {total_elapsed:.1f}s")
    
    # 保存原始结果JSON
    out_dir = Path(__file__).parent / "backtest_results"
    out_dir.mkdir(exist_ok=True)
    
    # 序列化结果（去掉不能JSON化的DataFrame）
    json_results = []
    for r in valid_results:
        jr = {k: v for k, v in r.items() 
              if k not in ('daily_df', 'trades_df')}
        json_results.append(jr)
    
    with open(out_dir / "param_sweep_v3.json", "w") as f:
        json.dump(json_results, f, ensure_ascii=False, indent=2, default=str)
    
    # 生成报告
    generate_v3_report(valid_results, out_dir)
    
    return valid_results


# ──────────────────────────────────────────────
#  V3 HTML 报告生成器
# ──────────────────────────────────────────────

def generate_v3_report(results: list, out_dir: Path):
    """生成V3增强版HTML报告，包含4个维度的详细分析"""
    
    import json as json_mod
    
    if not results:
        print("⚠️  无有效结果，跳过报告生成")
        return
    
    # 按分组组织
    groups = {}
    for r in results:
        g = r.get("group", "未分组")
        if g not in groups:
            groups[g] = []
        groups[g].append(r)
    
    # 计算夏普比率（简化版：年化 / 最大回撤绝对值）
    for r in results:
        dd = abs(r.get("max_dd", 0.01))
        if dd > 0.001:
            r["sharpe"] = round(r["ann_return"] / dd, 2)
        else:
            r["sharpe"] = 0.0
        
        # 盈亏比
        trades_df = r.get("trades_df")
        if trades_df is not None and not trades_df.empty:
            early_trades = trades_df[trades_df.action == "EARLY_CLOSE"]
            if not early_trades.empty:
                wins = early_trades[early_trades.pnl > 0]["pnl"]
                losses = early_trades[early_trades.pnl <= 0]["pnl"]
                avg_win = wins.mean() if len(wins) > 0 else 0
                avg_loss = abs(losses.mean()) if len(losses) > 0 else 1
                r["profit_ratio"] = round(avg_win / max(avg_loss, 1), 2)
            else:
                r["profit_ratio"] = 0
        else:
            r["profit_ratio"] = 0
    
    # 找出每组最优
    group_winners = {}
    for gname, grp in groups.items():
        best = max(grp, key=lambda x: x.get("sharpe", -999))
        group_winners[gname] = best["config_id"]
    
    # 全局最优（按夏普排序）
    sorted_results = sorted(results, key=lambda x: x.get("sharpe", -999), reverse=True)
    global_best = sorted_results[0] if sorted_results else None
    
    # 构建图表数据
    series_data = []
    colors_map = {
        "基准": "#6366f1",
        "A-止损缓冲": "#10b981",
        "B-IV分位数": "#f59e0b",
        "C-滑点模型": "#ef4444",
        "D-凯利管理": "#8b5cf6",
    }
    
    for i, r in enumerate(sorted_results):
        ddf = r.get("daily_df")
        if ddf is not None and not ddf.empty:
            dates = [str(d) for d in ddf["date"]]
            vals = [round(v, 0) for v in ddf["total_value"]]
            grp_color = colors_map.get(r.get("group", ""), "#94a3b8")
            series_data.append({
                "label": r["label"],
                "color": grp_color,
                "dates": dates,
                "values": vals,
                "sharpe": r.get("sharpe", 0),
                "group": r.get("group", ""),
            })
    
    # === 生成 HTML ===
    
    # 指标卡片
    cards_html = ""
    top_n = 6  # 显示前6名
    for r in sorted_results[:top_n]:
        is_winner = r["config_id"] == (global_best["config_id"] if global_best else "")
        badge = " 🏆" if is_winner else ""
        grp = r.get("group", "")
        color = colors_map.get(grp, "#94a3b8")
        border_style = f"border-top:3px solid {color}"
        if is_winner:
            cards_html += f'''
      <div class="card winner-card" style="{border_style}">
        <div class="card-badge">TOP{sorted_results.index(r)+1}{badge}</div>
        <div class="card-label">{r['label']}</div>
        <div class="card-metric" style="color:{color}">{r['ann_return']:+.2f}%</div>
        <div class="card-sub">年化 · 夏普={r.get('sharpe', 0):.2f}</div>
        <div class="card-row"><span>总收益</span><span>{r['total_return']:+.2f}%</span></div>
        <div class="card-row"><span>最大回撤</span><span style="color:#ef4444">{r['max_dd']:.2f}%</span></div>
        <div class="card-row"><span>开仓/胜率</span><span>{r['n_open']}次/{r['win_rate']:.0f}%</span></div>
        <div class="card-row"><span>均次权利金</span><span>HKD {r['avg_credit']:,.0f}</span></div>
        <div class="card-row"><span>盈亏比</span><span>{r.get('profit_ratio', 0):.2f}</span></div>
      </div>'''
        else:
            cards_html += f'''
      <div class="card" style="{border_style}">
        <div class="card-badge">TOP{sorted_results.index(r)+1}</div>
        <div class="card-label">{r['label']}</div>
        <div class="card-metric" style="color:{color}">{r['ann_return']:+.2f}%</div>
        <div class="card-sub">年化 · 夏普={r.get('sharpe', 0):.2f}</div>
        <div class="card-row"><span>总收益</span><span>{r['total_return']:+.2f}%</span></div>
        <div class="card-row"><span>最大回撤</span><span style="color:#ef4444">{r['max_dd']:.2f}%</span></div>
        <div class="card-row"><span>开仓/胜率</span><span>{r['n_open']}次/{r['win_rate']:.0f}%</span></div>
        <div class="card-row"><span>均次权利金</span><span>HKD {r['avg_credit']:,.0f}</span></div>
        <div class="card-row"><span>盈亏比</span><span>{r.get('profit_ratio', 0):.2f}</span></div>
      </div>'''
    
    # 完整汇总表
    rows = ""
    for rank, r in enumerate(sorted_results, 1):
        is_winner = rank == 1
        row_class = ' class="winner-row"' if is_winner else ''
        medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else ""))
        rows += f'''<tr{row_class}>
          <td>{rank}{medal}</td>
          <td>{r['label']}</td>
          <td>{r['group']}</td>
          <td>{r['n_open']}</td>
          <td>HKD {r['avg_credit']:,.0f}</td>
          <td>{r['win_rate']:.0f}%</td>
          <td style="color:#10b981;font-weight:600">{r['ann_return']:+.2f}%</td>
          <td style="color:#ef4444;font-weight:600">{r['max_dd']:.2f}%</td>
          <td style="color:#818cf8;font-weight:600">{r.get('sharpe', 0):.2f}</td>
          <td>{r.get('profit_ratio', 0):.2f}</td>
          <td>{r.get('n_early_close', 0)}</td>
          <td>{r.get('n_loss', 0)}</td>
        </tr>'''
    
    # 分组分析表格
    group_analysis_html = ""
    for gname, grp in groups.items():
        best_in_grp = max(grp, key=lambda x: x.get("sharpe", -999))
        worst_in_grp = min(grp, key=lambda x: x.get("sharpe", -999))
        avg_ann = np.mean([r["ann_return"] for r in grp])
        avg_dd = np.mean([abs(r["max_dd"]) for r in grp])
        color = colors_map.get(gname, "#94a3b8")
        
        group_analysis_html += f'''
      <tr>
        <td style="color:{color};font-weight:600">{gname}</td>
        <td>{len(grp)} 组</td>
        <td style="color:#10b981">{best_in_grp['ann_return']:+.2f}%</td>
        <td style="color:#ef4444">{best_in_grp['max_dd']:.2f}%</td>
        <td style="color:#818cf8">{best_in_grp.get('sharpe', 0):.2f}</td>
        <td>{best_in_grp['label'][:35]}</td>
        <td style="color:#ef4444">{worst_in_grp['max_dd']:.2f}%</td>
      </tr>'''
    
    series_json = json_mod.dumps(series_data, ensure_ascii=False)
    
    html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Iron Condor V3 增强回测报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        background:#0f1117;color:#e2e8f0;line-height:1.6}}
  
  /* Header */
  .header{{background:linear-gradient(135deg,#1e1b4b 0%,#0f172a 50%,#1a0a2e 100%);
            padding:48px 24px 36px;text-align:center;border-bottom:1px solid rgba(139,92,246,.2)}}
  .header h1{{font-size:2.2rem;font-weight:700;
              background:linear-gradient(90deg,#818cf8,#c084fc,#34d399);
              -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px}}
  .header p{{color:#94a3b8;font-size:.95rem;max-width:700px;margin:0 auto}}
  .header .meta{{margin-top:16px;display:flex;justify-content:center;gap:24px;flex-wrap:wrap}}
  .header .meta span{{background:rgba(255,255,255,.06);padding:4px 14px;border-radius:20px;font-size:.82rem;color:#a78bfa}}
  
  /* Container */
  .container{{max-width:1360px;margin:0 auto;padding:24px}}
  .section-title{{font-size:1rem;font-weight:600;color:#a78bfa;
                  margin:32px 0 16px;padding-left:12px;border-left:3px solid #8b5cf6;
                  letter-spacing:.06em;text-transform:uppercase}}
  .section-desc{{color:#64748b;font-size:.88rem;margin-bottom:16px;padding-left:12px}}
  
  /* Cards */
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
  .card{{background:rgba(255,255,255,.03);border-radius:14px;padding:20px;
          transition:all .25s ease;border:1px solid rgba(255,255,255,.06);position:relative}}
  .card:hover{{transform:translateY(-3px);box-shadow:0 8px 32px rgba(139,92,246,.15);border-color:rgba(139,92,246,.3)}}
  .winner-card{{background:linear-gradient(135deg,rgba(139,92,246,.08),rgba(16,185,129,.04));
               border:1px solid rgba(16,185,129,.25)!important;box-shadow:0 0 24px rgba(16,185,129,.08)}}
  .card-badge{{position:absolute;top:-10px;right:16px;background:linear-gradient(135deg,#8b5cf6,#6366f1);
               color:white;font-size:.72rem;font-weight:700;padding:3px 10px;border-radius:10px}}
  .winner-card .card-badge{{background:linear-gradient(135deg,#10b981,#059669)}}
  .card-label{{font-size:.78rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;padding-right:40px}}
  .card-metric{{font-size:2.2rem;font-weight:700;margin:6px 0}}
  .card-sub{{font-size:.75rem;color:#64748b;margin-bottom:14px}}
  .card-row{{display:flex;justify-content:space-between;font-size:.83rem;
              padding:4px 0;border-bottom:1px solid rgba(255,255,255,.04);color:#94a3b8}}
  .card-row span:last-child{{font-weight:600;color:#e2e8f0}}
  
  /* Tables */
  .chart-box{{background:rgba(255,255,255,.02);border-radius:14px;padding:24px;
              margin-bottom:24px;border:1px solid rgba(255,255,255,.05)}}
  .chart-title{{font-size:.95rem;font-weight:600;margin-bottom:16px;color:#cbd5e1;display:flex;align-items:center;gap:8px}}
  .table-wrapper{{overflow-x:auto}}
  .compare-table{{width:100%;border-collapse:collapse;font-size:.85rem}}
  .compare-table th{{background:rgba(139,92,246,.15);padding:11px 14px;
                      text-align:left;font-weight:600;color:#a78bfa;white-space:nowrap;border-bottom:2px solid rgba(139,92,246,.2)}}
  .compare-table td{{padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.04)}}
  .compare-table tr:hover td{{background:rgba(139,92,246,.05)}}
  .winner-row{{background:rgba(16,185,129,.06)!important}}
  .winner-row td{{color:#e2e8f0!important}}
  
  /* Insight boxes */
  .insight-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-bottom:24px}}
  .insight-box{{background:rgba(255,255,255,.03);border-radius:12px;padding:20px;
                border-left:3px solid #8b5cf6}}
  .insight-box h3{{font-size:.9rem;color:#a78bfa;margin-bottom:8px}}
  .insight-box p{{font-size:.85rem;color:#94a3b8;line-height:1.7}}
  .insight-box .highlight{{color:#34d399;font-weight:600}}
  .insight-box .warn{{color:#f59e0b;font-weight:600}}
  .insight-box .danger{{color:#ef4444;font-weight:600}}

  /* Legend */
  .legend{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;font-size:.82rem}}
  .legend-item{{display:flex;align-items:center;gap:5px}}
  .legend-dot{{width:10px;height:10px;border-radius:50%}}
  
  @media(max-width:768px){{.cards{{grid-template-columns:1fr}}}}
</style>
</head>
<body>

<div class="header">
  <h1>🦅 Iron Condor V3 增强回测报告</h1>
  <p>验证 AI 助手提出的4项核心优化：止损缓冲 / IV分位数过滤 / 动态滑点 / 凯利公式仓位管理<br>
     基于 2020-2025 腾讯(HK.00700) 富途API真实数据 · 初始资金 HKD 100,000</p>
  <div class="meta">
    <span>📅 2020~2025 (6年)</span>
    <span>🔧 {len(results)} 组参数</span>
    <span>🏆 最佳夏普: {(global_best.get('sharpe', 0) if global_best else 0):.2f}</span>
  </div>
</div>

<div class="container">

  <!-- 核心发现 -->
  <div class="section-title">💡 核心发现</div>
  <div class="insight-grid">
    <div class="insight-box">
      <h3>🏆 最优策略组合</h3>
      <p>{f"<span class='highlight'>{global_best['label']}</span>" if global_best else "N/A"}<br>
         年化 <span class='highlight'>{global_best.get('ann_return', 0):+.2f}%</span> · 
         最大回撤 <span class="{'highlight' if (global_best.get('max_dd', 0) > -5) else 'warn'}">{global_best.get('max_dd', 0):.2f}%</span><br>
         夏普比率 <span class='highlight'>{global_best.get('sharpe', 0):.2f}</span> · 
         胜率 <span class='highlight'>{global_best.get('win_rate', 0):.0f}%</span></p>
    </div>
    <div class="insight-box">
      <h3>📊 V3 vs V2 对比</h3>
      <p>V2基线（无任何增强）的表现在下方表格中可以找到。<br>
         关键看点：<br>
         • 止损缓冲是否降低了最大回撤？<br>
         • 动态滑点是否更贴近实盘？<br>
         • 分位数IV过滤在哪个区间最稳定？</p>
    </div>
    <div class="insight-box">
      <h3>⚠️ 实盘注意事项</h3>
      <p>• 回测使用BS理论价定价期权，实际期权价格可能偏离<br>
         • 动态滑点模型是估算，真实滑点取决于市场深度<br>
         • 分位数IV是基于历史数据的统计边界<br>
         • <span class="warn">建议先用模拟盘验证1个月再考虑实盘</span></p>
    </div>
  </div>

  <!-- TOP排名卡片 -->
  <div class="section-title">🏆 TOP 策略排名（按夏普比率）</div>
  <div class="section-desc">综合年化收益、最大回撤、胜率的加权排名</div>
  <div class="cards">{cards_html}</div>

  <!-- 资金曲线 -->
  <div class="section-title">📈 资金曲线对比</div>
  <div class="chart-box">
    <canvas id="equityChart" height="350"></canvas>
  </div>

  <!-- 完整汇总表 -->
  <div class="section-title">🔢 完整参数对比表</div>
  <div class="chart-box">
    <div class="table-wrapper">
      <table class="compare-table">
        <thead><tr>
          <th>#</th><th>策略</th><th>分组</th><th>开仓</th><th>均次权利金</th>
          <th>胜率</th><th>年化</th><th>最大回撤</th><th>夏普</th><th>盈亏比</th><th>提前平仓</th><th>到期亏损</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </div>

  <!-- 分组分析 -->
  <div class="section-title">📊 分维度分析</div>
  <div class="chart-box">
    <div class="table-wrapper">
      <table class="compare-table">
        <thead><tr>
          <th>维度</th><th>组数</th><th>最佳年化</th><th>最佳回撤</th><th>最佳夏普</th><th>最佳方案</th><th>最差回撤</th>
        </tr></thead>
        <tbody>{group_analysis_html}</tbody>
      </table>
    </div>
  </div>

  <!-- V2 vs V3 差异说明 -->
  <div class="section-title">🔄 V3 增强内容详解</div>
  <div class="insight-grid">
    <div class="insight-box" style="border-left-color:#10b981">
      <h3>① 止损缓冲 (Stop Loss Buffer)</h3>
      <p>V2问题：价格刚突破盈亏平衡就立即止损，可能被假突破洗出去。<br><br>
         V3改进：设置 buffer=1.5x 时，只有价格突破正常止损线的 <span class="highlight">1.5倍距离</span>才触发止损。
         可选加时间过滤（如连续1天确认），避免单日 spike 触发。</p>
    </div>
    <div class="insight-box" style="border-left-color:#f59e0b">
      <h3>② 分位数 IV 过滤</h3>
      <p>V2问题：用固定IV阈值（如20%）一刀切，忽略了不同市场阶段。<br><br>
         V3改进：计算全序列IV的<span class="highlight">分位数分布</span>，
         只在特定百分位区间（如 P25-P75）内开仓。可分别测试低/中/高波环境的稳定性。</p>
    </div>
    <div class="insight-box" style="border-left-color:#ef4444">
      <h3>③ 动态滑点模型</h3>
      <p>V2问题：所有场景统一0.5%+5倍固定滑点。<br><br>
         V3改进：<span class="highlight">根据期权虚实值程度</span>动态调整：
         平值期权滑点10%，浅虚值20%，深虚值50%。更接近实盘中流动性差异的真实表现。</p>
    </div>
    <div class="insight-box" style="border-left-color:#8b5cf6">
      <h3>④ 凯利公式仓位管理</h3>
      <p>V2问题：固定开仓组数，不随资金量或策略状态调整。<br><br>
         V3改进：用<span class="highlight">Kelly公式 f*=(pb-(1-p))/b</span> 动态计算最优仓位。
         支持半凯利（kelly=0.5）等比例，自动适配资金规模变化。</p>
    </div>
  </div>

</div>

<script>
const seriesData = {series_json};

// 图例颜色映射
const legendColors = {{
  '基准': '#6366f1',
  'A-止损缓冲': '#10b981',
  'B-IV分位数': '#f59e0b',
  'C-滑点模型': '#ef4444',
  'D-凯利管理': '#8b5cf6'
}};

// 资金曲线图
const eqCtx = document.getElementById('equityChart').getContext('2d');
new Chart(eqCtx, {{
  type: 'line',
  data: {{
    labels: seriesData[0]?.dates || [],
    datasets: seriesData.map(s => ({{
      label: s.label,
      data: s.values,
      borderColor: s.color,
      backgroundColor: s.color + '12',
      borderWidth: s.sharpe === Math.max(...seriesData.map(x=>x.sharpe)) ? 3 : 1.5,
      pointRadius: 0,
      tension: 0.3,
      fill: false,
      hidden: s.sharpe < Math.max(...seriesData.map(x=>x.sharpe)) * 0.3, // 隐藏太差的曲线
    }}))
  }},
  options: {{
    responsive: true,
    interaction: {{mode:'index', intersect:false}},
    plugins: {{
      legend: {{
        position: 'top',
        labels: {{color:'#94a3b8', boxWidth:12, font:{{size:11}}, 
                  filter: function(item, chart) {{ return !item.hidden; }} }}
      }},
      tooltip: {{
        callbacks: {{
          title: function(items) {{ return items[0].label; }},
          label: function(ctx) {{
            const ds = ctx.dataset;
            const val = ctx.parsed.y;
            const sharpe = seriesData.find(s => s.label === ds.label)?.sharpe;
            return ds.label + ': HKD ' + val.toLocaleString() + (sharpe ? ' (夏普:' + sharpe + ')' : '');
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ticks:{{color:'#64748b',maxTicksLimit:16}}, grid:{{color:'rgba(255,255,255,.03)'}}}},
      y: {{ticks:{{color:'#64748b',callback:v=>'HKD '+Math.round(v).toLocaleString()}}, grid:{{color:'rgba(255,255,255,.05)'}}}}
    }}
  }}
}});
</script>

</body>
</html>'''
    
    out_path = out_dir / "param_sweep_report_v3.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\n  📊 V3报告已生成 → {out_path}")


if __name__ == "__main__":
    main()
