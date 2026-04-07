"""
修复后的Iron Condor参数扫描 - 修复了2个核心bug：
1. 胜率公式：分母从n_open改为n_closed，最大100%
2. 最大回撤=0%：加入持仓市值估算 + 破位止损逻辑 + 滑点惩罚

运行: python3 param_sweep_v2.py
超时控制: 脚本内部用signal alarm
"""

import sys
import signal
import json
import traceback
from pathlib import Path

# ─── 超时保护（macOS兼容）───
def timeout_handler(signum, frame):
    raise TimeoutError("脚本执行超过180秒")

try:
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(180)  # 3分钟总超时
except:
    pass  # Windows不支持SIGALRM

sys.path.insert(0, str(Path(__file__).parent))
from iron_condor import IronCondorBacktester
from backtest_real import fetch_futu_kline


def run_single(otm, wing, dte, capital=60_000):
    """运行单组参数"""
    label = f"OTM={otm:.0%} Wing={wing:.0%} DTE={dte}"
    
    bt = IronCondorBacktester(
        initial_capital=capital,
        otm_distance=otm,
        wing_width=wing,
        dte=dte,
        early_close_days=1,
        max_loss_pct=0.15,
        stop_loss_pct=0.20,
        max_groups=2,
        entry_mode="dte",
        label=label,
    )
    
    kline_df = fetch_futu_kline('HK.00700', start='2020-01-01', end='2025-12-31')
    if kline_df is None or len(kline_df) < 100:
        return {"error": "K线数据不足"}
    
    bt.run(kline_df)
    stats = bt.print_report(save_prefix=f"v2_o{int(otm*100)}_w{int(wing*100)}_d{dte}")
    
    return {
        "label": label,
        "params": {"otm": otm, "wing": wing, "dte": dte},
        **stats,
    }


def main():
    print("=" * 70)
    print("  🔧 Iron Condor 参数扫描 V2（修复后）")
    print("  修复项：胜率公式 + 持仓市值 + 破位止损 + 滑点惩罚")
    print("=" * 70)
    
    # 参数组合
    param_grid = [
        # (OTM, Wing, DTE)  - 核心对比
        # 原始参数
        (0.05, 0.08, 30),
        
        # 最优候选（之前V1的结果）
        (0.05, 0.04, 25),
        (0.05, 0.04, 30),
        
        # OTM变化
        (0.03, 0.04, 25),
        (0.07, 0.04, 25),
        (0.10, 0.04, 25),
        
        # Wing微调
        (0.05, 0.03, 25),
        (0.05, 0.05, 25),
        (0.05, 0.06, 25),
        
        # DTE对比
        (0.05, 0.04, 20),
        (0.05, 0.04, 45),
        
        # 高OTM + 小Wing
        (0.10, 0.06, 25),
        (0.10, 0.08, 25),
        
        # 低OTM
        (0.03, 0.02, 30),
        (0.05, 0.02, 30),
    ]
    
    results = []
    for i, (otm, wing, dte) in enumerate(param_grid):
        try:
            print(f"\n[{i+1}/{len(param_grid)}] 测试: OTM={otm:.0%} Wing={wing:.0%} DTE={dte}")
            result = run_single(otm, wing, dte)
            if "error" not in result:
                results.append(result)
                print(f"  ✓ 年化 {result.get('ann_return', 0):+.1f}% | "
                      f"回撤 {result.get('max_dd', 0):.2f}% | "
                      f"胜率 {result.get('win_rate', 0):.1f}% | "
                      f"夏普 待算")
            else:
                print(f"  ✗ {result['error']}")
                results.append({
                    "label": f"OTM={otm:.0%} Wing={wing:.0%} DTE={dte}",
                    "error": result["error"]
                })
        except Exception as e:
            print(f"  ✗ 异常: {e}")
            traceback.print_exc()
    
    # 排序
    valid_results = [r for r in results if "error" not in r]
    if valid_results:
        valid_results.sort(key=lambda x: x.get('ann_return', 0), reverse=True)
    
    # 保存JSON
    out_dir = Path(__file__).parent / "backtest_results"
    out_dir.mkdir(exist_ok=True)
    
    with open(out_dir / "param_sweep_v2.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    # 打印排名表
    print("\n" + "=" * 80)
    print("  📊 修复后参数扫描结果（按年化收益排序）")
    print("=" * 80)
    print(f"{'排名':^4} {'参数':^28} {'年化收益':>8} {'最大回撤':>8} {'胜率':>7} {'开仓':>5} {'均次权利金':>9}")
    print("-" * 80)
    
    for i, r in enumerate(valid_results):
        rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}"
        ann_r = r.get('ann_return', 0)
        max_dd = r.get('max_dd', 0)
        wr = r.get('win_rate', 0)
        n_open = r.get('n_open', 0)
        credit = r.get('avg_credit', 0)
        print(f"{rank_emoji:^4} {r['label']:^28} {ann_r:>+7.1f}% {max_dd:>8.2f}% {wr:>6.1f}% {n_open:>5} {credit:>8.0f}")
    
    # 计算简化夏普比率
    import numpy as np
    import pandas as pd
    for r in valid_results:
        daily_df = r.get("daily_df")
        if hasattr(r.get('daily_df'), '__len__') and len(r.get('daily_df', [])) > 10:
            try:
                df = r["daily_df"]
                returns = df["total_value"].pct_change().dropna()
                if len(returns) > 10 and returns.std() > 0:
                    r["sharpe"] = round((returns.mean() / returns.std()) * np.sqrt(252), 2)
                else:
                    r["sharpe"] = 0.0
            except:
                r["sharpe"] = 0.0
        else:
            r["sharpe"] = 0.0
    
    # 按夏普重排
    valid_results.sort(key=lambda x: x.get('sharpe', 0), reverse=True)
    
    print(f"\n{'=' * 80}")
    print(f"  📊 按夏普比率排序（单位风险收益）")
    print(f"{'=' * 80}")
    print(f"{'排名':^4} {'参数':^28} {'夏普':>6} {'年化':>8} {'回撤':>7} {'胜率':>7}")
    print("-" * 65)
    
    for i, r in enumerate(valid_results[:10]):
        rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}"
        print(f"{rank_emoji:^4} {r['label']:^28} {r.get('sharpe', 0):>6.2f} {r.get('ann_return', 0):>+7.1f}% {r.get('max_dd', 0):>6.2f}% {r.get('win_rate', 0):>6.1f}%")
    
    print(f"\n✅ 完成！结果保存在 backtest_results/param_sweep_v2.json")


if __name__ == "__main__":
    main()
