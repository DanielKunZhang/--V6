#!/usr/bin/env python3
"""
V4 综合参数扫描 - 修复止损线Bug后的完整对比
===============================================
修复内容:
  1. Bug1: max_groups重复记录 → 每组独立记录OPEN_IC
  2. Bug2: 止损线从盈亏平衡点改为卖Strike外侧（默认buffer=1.5）

数据源: 富途API真实K线 (HK.00700 腾讯)
"""

import sys, os, json, time
from datetime import date
from pathlib import Path

# 确保能import本目录模块
sys.path.insert(0, str(Path(__file__).parent))
from iron_condor import IronCondorBacktester, get_hk_option_expiries, fetch_futu_kline

def run_sweep():
    out_dir = Path(__file__).parent / "backtest_results"
    out_dir.mkdir(exist_ok=True)

    # 获取真实K线
    print("📥 获取腾讯 HK.00700 历史K线...")
    df = fetch_futu_kline("HK.00700", start="2019-01-01", end="2025-12-31")
    
    # 过滤交易日（港股）
    from futu import OpenQuoteContext
    quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
    ret, trading_days = quote_ctx.request_trading_days(market=0, start='2019-01-01', end='2025-12-31')
    quote_ctx.close()
    
    if ret == 0:
        trading_set = set([str(d) for d in trading_days['time'].tolist()])
        df = df[df['date'].astype(str).isin(trading_set)]
        print(f"  ✅ 筛选后 {len(df)} 个交易日")

    results = []
    total_configs = 0

    # === 核心参数矩阵 ===
    configs = [
        # ===== A组: OTM × Wing 组合（核心对比）=====
        {"label": "A1: OTM3%Wing4%DTE30", "otm": 0.03, "wing": 0.04, "dte": 30, "groups": 1},
        {"label": "A2: OTM3%Wing8%DTE30", "otm": 0.03, "wing": 0.08, "dte": 30, "groups": 1},
        {"label": "A3: OTM5%Wing4%DTE30", "otm": 0.05, "wing": 0.04, "dte": 30, "groups": 1},
        {"label": "A4: OTM5%Wing6%DTE30", "otm": 0.05, "wing": 0.06, "dte": 30, "groups": 1},
        {"label": "A5: OTM5%Wing8%DTE30★", "otm": 0.05, "wing": 0.08, "dte": 30, "groups": 1},  # 当前最优
        {"label": "A6: OTM5%Wing10%DTE30","otm": 0.05, "wing": 0.10, "dte": 30, "groups": 1},
        {"label": "A7: OTM7%Wing8%DTE30", "otm": 0.07, "wing": 0.08, "dte": 30, "groups": 1},
        {"label": "A8: OTM10%Wing8%DTE30","otm": 0.10, "wing": 0.08, "dte": 30, "groups": 1},

        # ===== B组: DTE 对比 =====
        {"label": "B1: OTM5%Wing8%DTE21", "otm": 0.05, "wing": 0.08, "dte": 21, "groups": 1},
        {"label": "B2: OTM5%Wing8%DTE45", "otm": 0.05, "wing": 0.08, "dte": 45, "groups": 1},

        # ===== C组: 止损缓冲对比（用最优OTM/Wing/DTE）=====
        {"label": "C1: Buf1.0(卖Strike)", "otm": 0.05, "wing": 0.08, "dte": 30, "groups": 1, "buf": 1.0},
        {"label": "C2: Buf1.3",            "otm": 0.05, "wing": 0.08, "dte": 30, "groups": 1, "buf": 1.3},
        {"label": "C3: Buf1.5(V4默认)★",   "otm": 0.05, "wing": 0.08, "dte": 30, "groups": 1, "buf": 1.5},
        {"label": "C4: Buf1.8",            "otm": 0.05, "wing": 0.08, "dte": 30, "groups": 1, "buf": 1.8},
        {"label": "C5: Buf2.0(近买Strike)", "otm": 0.05, "wing": 0.08, "dte": 30, "groups": 1, "buf": 2.0},

        # ===== D组: 多组对比 =====
        {"label": "D1: OTM5%Wing8%×2组",   "otm": 0.05, "wing": 0.08, "dte": 30, "groups": 2},
        {"label": "D2: OTM7%Wing10%×2组",  "otm": 0.07, "wing": 0.10, "dte": 30, "groups": 2},
        
        # ===== E组: 宽翼+长DTE（保守型）=====
        {"label": "E1: OTM7%Wing10%DTE45",  "otm": 0.07, "wing": 0.10, "dte": 45, "groups": 1},
        {"label": "E2: OTM10%Wing10%DTE45", "otm": 0.10, "wing": 0.10, "dte": 45, "groups": 1},

        # ===== F组: 窄翼+短DTE（激进型）=====
        {"label": "F1: OTM3%Wing4%DTE21",   "otm": 0.03, "wing": 0.04, "dte": 21, "groups": 1},
        {"label": "F2: OTM5%Wing4%DTE21",   "otm": 0.05, "wing": 0.04, "dte": 21, "groups": 1},
    ]

    total_configs = len(configs)
    print(f"\n{'='*70}")
    print(f"  🦅 V4 综合参数扫描 — 共 {total_configs} 组配置")
    print(f"  数据范围: {df['date'].iloc[0]} ~ {df['date'].iloc[-1]} ({len(df)}个交易日)")
    print(f"{'='*70}")

    for idx, cfg in enumerate(configs):
        label = cfg["label"]
        otm = cfg["otm"]
        wing = cfg["wing"]
        dte = cfg["dte"]
        groups = cfg.get("groups", 1)
        buf = cfg.get("buf", 1.5)  # V4默认1.5
        
        prefix = f"v4_{idx:02d}_{label.split(':')[0]}"
        t0 = time.time()

        bt = IronCondorBacktester(
            initial_capital=100_000,
            wing_width=wing,
            otm_distance=otm,
            dte=dte,
            label=label,
            min_iv=0.15,           # 降低IV门槛，让更多交易入场
            early_close_days=2,
            max_loss_pct=0.02,
            stop_loss_pct=0.15,     # V4放宽到15%（避免被单次极端行情永久停止）
            max_groups=groups,
            stop_loss_buffer=buf,   # V4修复后的缓冲参数
            dynamic_slippage=False, # 关闭动态滑点（V3已验证固定滑点更好）
            kelly_fraction=0.0,     # 不使用凯利
        )

        bt.run(df, save_prefix=prefix)  # 执行回测
        stats = bt.print_report(save_prefix=prefix)  # 生成并返回统计

        elapsed = time.time() - t0
        if stats:
            stats["config"] = {
                "otm": otm, "wing": wing, "dte": dte, 
                "groups": groups, "stop_buf": buf
            }
            results.append(stats)

            wr = stats.get('win_rate', 0)
            ann = stats.get('ann_return', 0)
            dd = stats.get('max_dd', 0)
            n_o = stats.get('n_open', 0)
            n_e = stats.get('n_expired', 0)
            n_ec = stats.get('n_early_close', 0)
            
            print(f"  [{idx+1}/{total_configs}] {label:28s} | 年化{ann:+6.1f}% | "
                  f"回撤{dd:6.2f}% | 胜率{wr:5.1f}% | 开{n_o:>4} 到期{n_e:>3} 提前{n_ec:>4} | {elapsed:.1f}s")
        else:
            print(f"  [{idx+1}/{total_configs}] {label:28s} | ❌ 无结果 | {elapsed:.1f}s")
            results.append({
                "label": label, "ann_return": None, "max_dd": None,
                "win_rate": 0, "n_open": 0, "error": True
            })

    # 保存JSON
    with open(out_dir / "param_sweep_v4.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    # === 生成HTML报告 ===
    valid = [r for r in results if r.get("ann_return") is not None and not r.get("error")]
    valid.sort(key=lambda x: x.get("sharpe_ratio", -999), reverse=True)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>V4 Iron Condor 参数扫描</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,'SF Pro','Helvetica Neue',Arial; background:#0a0e17; color:#e0e0e0; padding:20px; }}
  h1 {{ font-size:22px; color:#fff; margin-bottom:5px; }}
  .subtitle {{ color:#888; font-size:13px; margin-bottom:20px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:12px; }}
  .card {{ background:linear-gradient(135deg,#141b2d,#1a2332); border-radius:12px; padding:16px; border:1px solid rgba(255,255,255,06); position:relative; overflow:hidden; }}
  .card.rank-1 {{ border-color:#ffd70055; background:linear-gradient(135deg,#1a1e0d,#252a12); }}
  .card.rank-2 {{ border-color:#c0c0c044; }}
  .card.rank-3 {{ border-color:#cd7f3244; }}
  .rank-badge {{ position:absolute; top:10px; right:10px; font-size:20px; }}
  .card-title {{ font-size:14px; font-weight:600; color:#fff; margin-bottom:10px; }}
  .card-row {{ display:flex; justify-content:space-between; font-size:13px; padding:3px 0; color:#aaa; }}
  .card-row span:last-child {{ font-weight:600; color:#e0e0e0; }}
  .card-row.positive {{ color:#4ade80; }}
  .card-row.negative {{ color:#f87171; }}
  table {{ width:100%; border-collapse:collapse; margin-top:20px; font-size:13px; }}
  th {{ background:#1a2332; padding:8px 10px; text-align:left; color:#888; border-bottom:1px solid #333; white-space:nowrap; }}
  td {{ padding:8px 10px; border-bottom:1px solid #1a1a1a; }}
  tr:hover td {{ background:#1a2030; }}
  .pos {{ color:#4ade80; }} .neg {{ color:#f87171; }} .warn {{ color:#fbbf24; }}
  .section {{ margin-top:30px; }}
  h2 {{ font-size:18px; color:#fff; margin-bottom:12px; border-left:3px solid #3b82f6; padding-left:10px; }}
  .highlight {{ background:#1e293b; border-radius:8px; padding:14px; margin:15px 0; font-size:13px; line-height:1.7; }}
  .tag {{ display:inline-block; font-size:10px; padding:2px 6px; border-radius:4px; margin-right:4px; }}
  .tag-a {{ background:#3b82f633; color:#60a5fa; }}
  .tag-b {{ background:#8b5cf633; color:#a78bfa; }}
  .tag-c {{ background:#f59e0b33; color:#fbbf24; }}
  .tag-d {{ background:#10b98133; color:#34d399; }}
  .tag-e {{ background:#6366f133; color:#818cf8; }}
  .tag-f {{ background:#ef444433; color:#f87171; }}
</style></head><body>

<h1>🦅 Iron Condor V4 — 修复后综合参数扫描</h1>
<p class="subtitle">修复Bug: ①max_groups重复记录 ②止损线从盈亏平衡点→卖Strike外侧 | 
腾讯 HK.00700 | 2019-2025 | {len(valid)}组有效配置</p>

<div class="highlight">
<b>🔧 V4关键修复:</b><br>
• <b>Bug1</b>: max_groups>1时每笔仓位独立记录OPEN_IC（不再1154次平仓/577次开仓）<br>
• <b>Bug2</b>: 止损线从「盈亏平衡点(距现价仅1.5%)」改为「卖Strike + 翼宽×buffer」<br>
&nbsp;&nbsp;- buffer=1.0 → 止损线在卖方行权价<br>
&nbsp;&nbsp;- buffer=1.5 → 向内移50%翼宽（V4默认）<br>
&nbsp;&nbsp;- buffer=2.0 → 接近买方行权价<br>
• 总回撤止损线从10%放宽到15%（避免2020年3月股灾永久停策略）
</div>

<h2 class="section">🏆 排名（按夏普比率）</h2>
<div class="grid">
"""

    for i, r in enumerate(valid[:20]):
        rank = i + 1
        badge = ["🥇","🥈","🥉"][i] if i < 3 else f"#{rank}"
        cls = f"rank-{rank}" if rank <= 3 else ""
        tag_type = (r.get("label","").split(":")[0] if ":" in r.get("label","") else "x").strip()
        tag_map = {"A":"tag-a","B":"tag-b","C":"tag-c","D":"tag-d","E":"tag-e","F":"tag-f"}
        tag_cls = tag_map.get(tag_type[0], "")
        
        ann = r.get('ann_return', 0)
        dd = r.get('max_dd', 0)
        cls_ann = "positive" if ann > 0 else "negative"
        cls_dd = "negative" if dd < -5 else ("warn" if dd < -2 else "")
        
        html += f"""<div class="card {cls}">
<span class="rank-badge">{badge}</span>
<div class="card-title"><span class="tag {tag_cls}">{r['label'].split(':')[0] if ':' in r['label'] else ''}</span> {r['label']}</div>
<div class="card-row {cls_ann}"><span>年化收益</span><span>{ann:+.1f}%</span></div>
<div class="card-row {cls_dd}"><span>最大回撤</span><span>{dd:.2f}%</span></div>
<div class="card-row"><span>胜率</span><span>{r.get('win_rate',0):.1f}%</span></div>
<div class="card-row"><span>夏普比率</span><span>{r.get('sharpe_ratio',0):.2f}</span></div>
<div class="card-row"><span>开仓/到期/提前</span><span>{r.get('n_open',0)}/{r.get('n_expired',0)}/{r.get('n_early_close',0)}</span></div>
<div class="card-row"><span>亏损次数</span><span>{r.get('n_loss',0)}</span></div>
<div class="card-row"><span>均次权利金</span><span>{r.get('avg_credit',0):.0f} HKD</span></div>
</div>\n"""

    html += """</div>

<h2 class="section">📊 详细数据表</h2>
<table><tr><th>#</th><th>配置</th><th>OTM</th><th>Wing</th><th>DTE</th><th>组数</th><th>Buf</th>
<th>年化</th><th>回撤</th><th>夏普</th><th>胜率</th><th>开仓</th><th>到期</th><th>提前平仓</th><th>亏损</th></tr>
"""

    for i, r in enumerate(valid):
        cfg = r.get("config", {})
        ann = r.get('ann_return', 0)
        dd = r.get('max_dd', 0)
        wr = r.get('win_rate', 0)
        html += f"""<tr><td>{i+1}</td><td>{r['label']}</td>
<td>{cfg.get('otm',0):.0%}</td><td>{cfg.get('wing',0):.0%}</td><td>{cfg.get('dte',0)}</td>
<td>{cfg.get('groups',1)}</td><td>{cfg.get('stop_buf',1.5)}</td>
<td class="{'pos' if ann > 0 else 'neg'}">{ann:+.1f}%</td>
<td class="{'neg' if dd < -5 else 'warn' if dd < -2 else ''}">{dd:.2f}%</td>
<td>{r.get('sharpe_ratio',0):.2f}</td>
<td>{wr:.1f}%</td><td>{r.get('n_open',0)}</td><td>{r.get('n_expired',0)}</td>
<td>{r.get('n_early_close',0)}</td><td>{r.get('n_loss',0)}</td></tr>\n"""

    html += """</table>

<h2 class="section">📋 分组分析</h2>
"""

    # 分组统计
    for group_name, group_tag in [("A: OTM×Wing组合", "A"), ("B: DTE对比", "B"), 
                                   ("C: 止损缓冲", "C"), ("D: 多组", "D"),
                                   ("E: 宽翼保守", "E"), ("F: 窄翼激进", "F")]:
        group_results = [r for r in valid if r.get("label","").startswith(group_tag)]
        if group_results:
            best = max(group_results, key=lambda x: x.get("sharpe_ratio", -999))
            avg_wr = sum(r.get("win_rate",0) for r in group_results) / len(group_results)
            avg_ann = sum(r.get("ann_return",0) for r in group_results) / len(group_results)
            html += f"""<div class="highlight">
<b>{group_name}</b> ({len(group_results)}组) | 
最佳: <b>{best['label']}</b> 年化{best.get('ann_return',0):+.1f}% 回撤{best.get('max_dd',0):.2f}% 胜率{best.get('win_rate',0):.1f}% |
平均胜率: {avg_wr:.1f}% | 平均年化: {avg_ann:+.1f}%
</div>\n"""

    html += """
<h2 class="section">💡 关键发现</h2>
<div class="highlight">
待运行完成后填充...
</div>
</body></html>"""

    report_path = out_dir / "param_sweep_report_v4.html"
    with open(report_path, "w") as f:
        f.write(html)
    print(f"\n✅ 报告已生成: {report_path}")
    return results


if __name__ == "__main__":
    run_sweep()
