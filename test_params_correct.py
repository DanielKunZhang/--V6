#!/usr/bin/env python3
"""
使用正确的保护参数重新测试 Iron Condor 策略
对比有无风控措施的结果差异
"""

import sys
import math
import logging
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline, bs_option_price, historical_volatility
from iron_condor import IronCondorBacktester, get_hk_option_expiries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_hk_ic_with_protection():
    """港股 Iron Condor - 带完整保护参数"""
    print("\n" + "="*60)
    print("📊 港股 Iron Condor 回测 - 带完整保护")
    print("参数: 本金5万HKD, OTM=5%, Wing=8%, pre_expiry=7天, IV>=20%")
    print("="*60)
    
    # 获取腾讯历史数据
    df = fetch_futu_kline("00700.HK", "2019-01-01", "2025-12-31", ktype="D")
    if df is None or df.empty:
        print("❌ 获取数据失败")
        return
    
    df = df.rename(columns={"time_key": "date"})
    df['date'] = pd.to_datetime(df['date']).dt.date
    print(f"📈 获取 {len(df)} 条数据 ({df['date'].min()} ~ {df['date'].max()})")
    
    # 使用保护参数
    tester = IronCondorBacktester(
        initial_capital=50_000,
        otm_distance=0.05,      # 5% OTM
        wing_width=0.08,        # 8% wing
        dte=25,
        entry_mode="pre_expiry",      # 到期前N天入场
        entry_days_before_expiry=7,   # 到期前7天
        early_close_days=2,            # 到期前2天平仓
        min_iv=0.20,                  # IV >= 20% 才开仓
        max_loss_pct=0.02,            # 单笔最大亏损 2%
        stop_loss_pct=0.10,           # 总回撤 10% 止损
        max_groups=2,                  # 最多2组
    )
    
    tester.run(df)
    stats = tester.print_report("hk_ic_protected")
    return stats


def test_hk_ic_no_protection():
    """港股 Iron Condor - 无保护参数（对比组）"""
    print("\n" + "="*60)
    print("📊 港股 Iron Condor 回测 - 无保护（对比组）")
    print("参数: 本金5万HKD, OTM=5%, Wing=8%, DTE=25, 无IV过滤/无提前平仓")
    print("="*60)
    
    df = fetch_futu_kline("00700.HK", "2019-01-01", "2025-12-31", ktype="D")
    if df is None or df.empty:
        print("❌ 获取数据失败")
        return
    
    df = df.rename(columns={"time_key": "date"})
    df['date'] = pd.to_datetime(df['date']).dt.date
    
    # 无保护参数
    tester = IronCondorBacktester(
        initial_capital=50_000,
        otm_distance=0.05,
        wing_width=0.08,
        dte=25,
        entry_mode="dte",              # 固定 DTE
        min_iv=0,                     # 无 IV 过滤
        early_close_days=0,           # 无提前平仓
        max_loss_pct=1.0,             # 不限制
        stop_loss_pct=1.0,            # 不止损
        max_groups=1,
    )
    
    tester.run(df)
    stats = tester.print_report("hk_ic_no_protection")
    return stats


def test_hk_ic_wider_otm():
    """港股 - 更宽 OTM 距离（更保守）"""
    print("\n" + "="*60)
    print("📊 港股 Iron Condor 回测 - 保守参数")
    print("参数: OTM=8%, Wing=10%, pre_expiry=7天")
    print("="*60)
    
    df = fetch_futu_kline("00700.HK", "2019-01-01", "2025-12-31", ktype="D")
    if df is None or df.empty:
        print("❌ 获取数据失败")
        return
    
    df = df.rename(columns={"time_key": "date"})
    df['date'] = pd.to_datetime(df['date']).dt.date
    
    tester = IronCondorBacktester(
        initial_capital=50_000,
        otm_distance=0.08,      # 8% OTM - 更宽
        wing_width=0.10,        # 10% wing - 更宽
        dte=25,
        entry_mode="pre_expiry",
        entry_days_before_expiry=7,
        early_close_days=2,
        min_iv=0.15,            # IV >= 15%
        max_loss_pct=0.015,     # 更严格的单笔限制
        stop_loss_pct=0.08,     # 8% 总回撤
        max_groups=2,
    )
    
    tester.run(df)
    stats = tester.print_report("hk_ic_conservative")
    return stats


def test_hk_ic_pre_expiry_10days():
    """港股 - 到期前10天入场"""
    print("\n" + "="*60)
    print("📊 港股 Iron Condor - 到期前10天入场")
    print("="*60)
    
    df = fetch_futu_kline("00700.HK", "2019-01-01", "2025-12-31", ktype="D")
    if df is None or df.empty:
        print("❌ 获取数据失败")
        return
    
    df = df.rename(columns={"time_key": "date"})
    df['date'] = pd.to_datetime(df['date']).dt.date
    
    tester = IronCondorBacktester(
        initial_capital=50_000,
        otm_distance=0.05,
        wing_width=0.08,
        dte=25,
        entry_mode="pre_expiry",
        entry_days_before_expiry=10,  # 到期前10天
        early_close_days=3,            # 到期前3天平仓
        min_iv=0.20,
        max_loss_pct=0.02,
        stop_loss_pct=0.10,
        max_groups=2,
    )
    
    tester.run(df)
    stats = tester.print_report("hk_ic_pre10")
    return stats


def compare_results():
    """汇总对比结果"""
    print("\n" + "="*60)
    print("📊 不同参数配置对比")
    print("="*60)
    
    # 读取之前保存的结果
    results = []
    
    for name, prefix in [
        ("保护参数 (pre_expiry=7)", "hk_ic_protected"),
        ("无保护对比组", "hk_ic_no_protection"),
        ("保守参数 (OTM=8%)", "hk_ic_conservative"),
        ("到期前10天入场", "hk_ic_pre10"),
    ]:
        csv_path = Path(f"backtest_results/{prefix}_trades.csv")
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            if 'return_pct' in df.columns or 'total_return' in df.columns:
                final_file = Path(f"backtest_results/{prefix}_summary.txt")
                if final_file.exists():
                    with open(final_file) as f:
                        content = f.read()
                        # 解析关键指标
                        ann = ""
                        mdd = ""
                        for line in content.split('\n'):
                            if '年化收益' in line:
                                ann = line.split(':')[-1].strip()
                            if '最大回撤' in line:
                                mdd = line.split(':')[-1].strip()
                        results.append({
                            'name': name,
                            'ann': ann,
                            'mdd': mdd,
                        })
    
    # 打印对比表
    print(f"\n{'配置':<25} {'年化收益':<15} {'最大回撤':<10}")
    print("-"*50)
    for r in results:
        print(f"{r['name']:<25} {r['ann']:<15} {r['mdd']:<10}")
    
    return results


if __name__ == "__main__":
    import os
    os.makedirs("backtest_results", exist_ok=True)
    
    # 运行各项测试
    test_hk_ic_with_protection()
    test_hk_ic_no_protection()
    test_hk_ic_wider_otm()
    test_hk_ic_pre_expiry_10days()
    
    # 对比结果
    compare_results()