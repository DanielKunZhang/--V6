#!/usr/bin/env python3
"""
Iron Condor 多参数扫描回测
基于futuapi真实数据，测试OTM/Wing/DTE的最优组合
数据来源: 富途API历史K线 (HK.00700)
"""
import sys, math, logging, json
from datetime import datetime, date, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from iron_condor import IronCondorBacktester, fetch_futu_kline, bs_option_price

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger(__name__)


def run_single_backtest(
    otm: float,
    wing: float,
    dte: int,
    initial_capital: float = 60_000,
    label: str = ""
) -> dict:
    """运行单组参数的Iron Condor回测"""
    bt = IronCondorBacktester(
        initial_capital=initial_capital,
        otm_distance=otm,
        wing_width=wing,
        dte=dte,
        early_close_days=1,
        max_loss_pct=0.15,
        stop_loss_pct=0.20,
        max_groups=2,
        entry_mode="dte",
        label=label or f"OTM={otm:.0%} Wing={wing:.0%} DTE={dte}",
    )
    
    # 获取历史K线数据（用futuapi）
    kline_df = fetch_futu_kline('HK.00700', start='2020-01-01', end='2025-12-31')
    if kline_df is None or len(kline_df) < 100:
        return {"error": "K线数据不足"}
    
    # 运行回测
    bt.run(kline_df)
    
    # 调用print_report获取完整统计
    # print_report会自动打印报告，我们只需要返回的dict
    stats = bt.print_report(save_prefix=f"swp_o{int(otm*100)}_w{int(wing*100)}_d{dte}")
    
    # 计算夏普比率 (简化版)
    daily_df = stats.get("daily_df", pd.DataFrame())
    sharpe = 0.0
    if not daily_df.empty and "total_value" in daily_df.columns:
        returns = daily_df["total_value"].pct_change().dropna()
        if len(returns) > 10 and returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252)
    
    return {
        "label": bt.label,
        "params": {"otm": otm, "wing": wing, "dte": dte},
        "n_trades": stats.get("n_open", 0),
        "win_rate": stats.get("win_rate", 0) / 100,   # 转为小数
        "total_return_pct": stats.get("total_return", 0),
        "max_drawdown_pct": abs(stats.get("max_dd", 0)),
        "annualized_return": stats.get("ann_return", 0),
        "sharpe_ratio": round(sharpe, 2),
        "avg_credit": stats.get("avg_credit", 0),
        "final_value": stats.get("final_value", 0),
        "n_loss": stats.get("n_loss", 0),
        "years": stats.get("years", 1),
    }


def main():
    print("=" * 70)
    print("  Iron Condor 多参数最优解搜索")
    print("  数据来源: 富途API HK.00700 历史K线 (2020-2025)")
    print("=" * 70, flush=True)
    
    # 参数网格 - 基于分析报告的建议范围
    param_grid = [
        # === 当前参数 (基准线) ===
        (0.05, 0.08, 30),   # 原始: OTM=5% Wing=8% DTE=30
        
        # === 优化组1: 减小Wing (提升资金效率) ===
        (0.05, 0.04, 30),   # Wing减半 → 20HKD左右
        (0.05, 0.03, 30),   # Wing更小 → ~15HKD
        (0.06, 0.04, 30),   # OTM稍大+Wing小
        (0.07, 0.04, 30),   # 接近1σ OTM+Wing小
        
        # === 优化组2: 动态DTE ===
        (0.05, 0.04, 25),   # 更短周期
        (0.05, 0.04, 45),   # 月度标准
        (0.10, 0.04, 25),   # 1σ OTM + 短DTE + 小Wing
        (0.10, 0.04, 45),   # 1σ OTM + 长DTE + 小Wing
        
        # === 优化组3: 对称性修正 (卖Put OTM > 卖Call OTM) ===
        # 注意: 当前代码不支持不对称OTM，这里用更大的整体OTM模拟
        (0.08, 0.04, 30),   # 更大OTM保护下跌端
        
        # === 优化组4: 极端保守 vs 激进 ===
        (0.15, 0.04, 30),   # 超宽OTM (2σ外) - 最保守
        (0.03, 0.02, 30),   # 窄OTM窄Wing - 高收益高风险
        (0.10, 0.08, 30),   # 宽OTM+原Wing
    ]
    
    results = []
    total = len(param_grid)
    
    for i, (otm, wing, dte) in enumerate(param_grid):
        label = f"OTM={otm:.0%} Wing={wing:.0%} DTE={dte}"
        print(f"\n[{i+1}/{total}] {label}...", flush=True)
        
        try:
            result = run_single_backtest(otm, wing, dte, initial_capital=60_000, label=label)
            result["index"] = i + 1
            
            if "error" not in result:
                n = result.get("n_trades", 0)
                wr = result.get("win_rate", 0) * 100
                ret = result.get("total_return_pct", 0)
                dd = result.get("max_drawdown_pct", 0)
                sharpe = result.get("sharpe_ratio", 0)
                print(f"    开仓:{n}次 | 胜率:{wr:.1f}% | 收益:{ret:+.1f}% | 回撤:{dd:.1f}% | 夏普:{sharpe:.2f}", flush=True)
            
            results.append(result)
        except Exception as e:
            print(f"    错误: {e}", flush=True)
            results.append({"label": label, "error": str(e), "index": i+1})
        
        sys.stdout.flush()
    
    # ── 结果排序和展示 ──
    valid_results = [r for r in results if "error" not in r]
    
    if not valid_results:
        print("\n所有参数组合都失败了!", flush=True)
        return
    
    # 按夏普比率排序
    by_sharpe = sorted(valid_results, key=lambda x: x.get("sharpe_ratio", -999), reverse=True)
    # 按年化收益排序  
    by_return = sorted(valid_results, key=lambda x: x.get("total_return_pct", -999), reverse=True)
    # 按收益/回撤比排序 (Calmar-like)
    for r in valid_results:
        dd = max(abs(r.get("max_drawdown_pct", 1)), 0.1)
        r["calmar"] = r.get("total_return_pct", 0) / dd
    by_calmar = sorted(valid_results, key=lambda x: x["calmar"], reverse=True)
    
    print("\n" + "=" * 70)
    print("  🏆 最优参数排名")
    print("=" * 70, flush=True)
    
    print(f"\n{'排名':>4} {'参数':>28} {'开仓':>5} {'胜率':>6} {'总收益':>8} {'最大回撤':>8} {'夏普':>6}")
    print("-" * 75, flush=True)
    
    for i, r in enumerate(by_sharpe[:10]):
        label = r["label"].replace("Iron Condor ","").replace(" DTE=", " D=")[:26]
        print(f"{i+1:>4} {label:>28} {r['n_trades']:>4}次 {r['win_rate']*100:>5.1f}% {r['total_return_pct']:>+7.1f}% {r['max_drawdown_pct']:>7.1f}% {r['sharpe_ratio']:>6.2f}", flush=True)
    
    best = by_sharpe[0]
    print(f"\n🥇 最优解 (夏普比率最高):", flush=True)
    print(f"   参数: OTM={best['params']['otm']:.0%}, Wing={best['params']['wing']:.0%}, DTE={best['params']['dte']}", flush=True)
    print(f"   年化收益: {best['annualized_return']:+.2f}%", flush=True)
    print(f"   最大回撤: {best['max_drawdown_pct']:.2f}%", flush=True)
    print(f"   胜率: {best['win_rate']*100:.1f}%", flush=True)
    print(f"   开仓次数: {best['n_trades']}次", flush=True)
    print(f"   夏普比率: {best['sharpe_ratio']:.2f}", flush=True)
    
    # 保存结果
    output_dir = Path(__file__).parent / "backtest_results"
    output_dir.mkdir(exist_ok=True)
    
    out_file = output_dir / "param_sweep.json"
    with open(out_file, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n详细结果已保存到: {out_file}", flush=True)


if __name__ == "__main__":
    main()
