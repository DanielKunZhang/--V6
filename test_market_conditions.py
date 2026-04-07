#!/usr/bin/env python3
"""
测试市场条件检查（HV20过滤 + 慢熊检测）
"""

import sys
sys.path.insert(0, str(sys.path[0]))

from main_ic_us import IronCondorTraderUS, FutuDataUS
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

def test_market_conditions():
    """测试市场条件检查逻辑"""
    print("🔍 测试市场条件检查...")
    
    # 连接数据源
    data = FutuDataUS()
    if not data.connect():
        print("❌ 无法连接富途 OpenD，请确保 OpenD 正在运行")
        return
    
    try:
        trader = IronCondorTraderUS(data)
        trader.dry_run = True
        
        # 调用市场条件检查
        result = trader._check_market_conditions()
        
        print("📊 市场条件检查结果:")
        print(f"   能否开仓: {result['can_open']}")
        print(f"   调整OTM: {result['adjust_otm']}")
        print(f"   原因: {result['reason']}")
        print(f"   HV20: {result['hv20']:.3f}")
        print(f"   20日累计收益率: {result['cumulative_20d']:.3%}")
        
        # 测试配置参数
        print("\n⚙️ 当前配置参数:")
        print(f"   hv20_threshold: {trader.config.get('hv20_threshold', '未设置')}")
        print(f"   slow_bear_threshold_20d: {trader.config.get('slow_bear_threshold_20d', '未设置')}")
        print(f"   slow_bear_defense: {trader.config.get('slow_bear_defense', '未设置')}")
        print(f"   slow_bear_otm_increase: {trader.config.get('slow_bear_otm_increase', '未设置')}")
        
        # 模拟开仓流程（不实际下单）
        if result['can_open']:
            print("\n✅ 市场条件允许开仓")
            if result['adjust_otm'] > 0:
                print(f"   需要调整OTM至: {result['adjust_otm']:.0%}")
                # 测试 calculate_strikes 使用调整后的OTM
                price = trader.get_current_price()
                if price:
                    strikes = trader.calculate_strikes(price, 30, otm=result['adjust_otm'])
                    print(f"   调整后的行权价: PUT {strikes['buy_put_k']}/{strikes['sell_put_k']} | CALL {strikes['sell_call_k']}/{strikes['buy_call_k']}")
        else:
            print(f"\n❌ 市场条件不允许开仓: {result['reason']}")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        data.close()

if __name__ == "__main__":
    test_market_conditions()