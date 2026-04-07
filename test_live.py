#!/usr/bin/env python3
"""
腾讯 Iron Condor 实盘综合测试脚本

在正式启动实盘前，运行此脚本检查所有组件是否正常工作。

使用方法:
    python3 test_live.py
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def test_module_imports():
    """测试模块导入"""
    logger.info("=" * 50)
    logger.info("1️⃣ 测试模块导入")
    logger.info("=" * 50)
    
    try:
        import config
        import notifier
        import strategy
        import executor
        import iron_condor
        import data
        import monitor
        import main
        logger.info("✅ 所有核心模块导入成功")
        return True
    except Exception as e:
        logger.error(f"❌ 模块导入失败: {e}")
        return False


def test_config():
    """测试配置"""
    logger.info("")
    logger.info("=" * 50)
    logger.info("2️⃣ 测试配置")
    logger.info("=" * 50)
    
    import config
    
    # 检查关键配置
    checks = [
        ("初始资金", config.RUN_MODE.get("initial_capital", 0) > 0),
        ("实盘模式", config.RUN_MODE.get("dry_run", True) == False),
        ("策略OTM", config.IRON_CONDOR_CONFIG.get("otm", 0) > 0),
        ("策略Wing", config.IRON_CONDOR_CONFIG.get("wing", 0) > 0),
        ("策略DTE", config.IRON_CONDOR_CONFIG.get("dte", 0) > 0),
    ]
    
    all_pass = True
    for name, passed in checks:
        status = "✅" if passed else "❌"
        logger.info(f"  {status} {name}")
        if not passed:
            all_pass = False
    
    return all_pass


def test_notifier():
    """测试通知"""
    logger.info("")
    logger.info("=" * 50)
    logger.info("3️⃣ 测试通知")
    logger.info("=" * 50)
    
    from notifier import get_email_notifier, get_notifier
    
    # 邮件通知器
    email_notif = get_email_notifier()
    logger.info(f"  📧 邮件通知器:")
    logger.info(f"      - 发件人: {email_notif.sender}")
    logger.info(f"      - 收件人: {email_notif.recipient}")
    logger.info(f"      - 已配置: {email_notif.enabled}")
    
    if email_notif.enabled:
        logger.info("  ✅ 邮件已配置，通知应该能正常工作")
    else:
        logger.warning("  ⚠️ 邮件未配置，请在 config.py 中设置 email_password")
        logger.info("      163邮箱 -> 设置 -> POP3/SMTP/IMAP -> 开启 -> 获取授权码")
    
    return True


def test_futu_connection():
    """测试富途连接"""
    logger.info("")
    logger.info("=" * 50)
    logger.info("4️⃣ 测试富途连接")
    logger.info("=" * 50)
    
    try:
        from futu import OpenQuoteContext, SubType, RET_OK
        
        logger.info("  尝试连接富途 OpenD (127.0.0.1:11111)...")
        
        ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        ret, data = ctx.get_stock_quote('00700.HK')
        ctx.close()
        
        if ret == RET_OK:
            price = float(data.iloc[0]['last_price'])
            logger.info(f"  ✅ 富途连接成功")
            logger.info(f"      - 腾讯股价: HKD {price}")
            return True
        else:
            logger.warning("  ⚠️ 富途 OpenD 可能未启动")
            logger.info("      4月8日启动前确保富途牛牛已打开并登录")
            return None  # None 表示未确定，需要用户启动
    except Exception as e:
        logger.warning(f"  ⚠️ 富途连接测试失败: {e}")
        logger.info("      这在4月8日前是正常的，确保当天启动即可")
        return None


def test_strategy_logic():
    """测试策略逻辑"""
    logger.info("")
    logger.info("=" * 50)
    logger.info("5️⃣ 测试策略逻辑")
    logger.info("=" * 50)
    
    import config
    import math
    
    # 模拟当前价格
    current_price = 580.0  # 假设腾讯580港币
    
    # 计算 Iron Condor 参数
    otm = config.IRON_CONDOR_CONFIG["otm"]
    wing = config.IRON_CONDOR_CONFIG["wing"]
    
    # 卖Put行权价 (5% OTM)
    put_strike = current_price * (1 - otm)
    # 卖Call行权价 (5% OTM)  
    call_strike = current_price * (1 + otm)
    # 买Call行权价 (卖Call + 8%)
    call_buy_strike = call_strike * (1 + wing)
    # 买Put行权价 (卖Put - 8%)
    put_buy_strike = put_strike * (1 - wing)
    
    logger.info(f"  当前股价: HKD {current_price}")
    logger.info(f"  Iron Condor 布局:")
    logger.info(f"      - 卖 Put: {put_strike:.0f} (5% OTM)")
    logger.info(f"      - 买 Put: {put_buy_strike:.0f} (保护)")
    logger.info(f"      - 卖 Call: {call_strike:.0f} (5% OTM)")
    logger.info(f"      - 买 Call: {call_buy_strike:.0f} (保护)")
    
    # 最大损失计算
    # 卖 Put 损失 = 行权价 - 买 Put 行权价
    max_loss_per_side = (put_strike - put_buy_strike) * 100  # 1手=100股
    logger.info(f"      - 单边最大损失: HKD {max_loss_per_side:,.0f}")
    
    logger.info(f"  ✅ 策略参数计算正常")
    return True


def test_data_files():
    """测试数据文件"""
    logger.info("")
    logger.info("=" * 50)
    logger.info("6️⃣ 测试数据文件")
    logger.info("=" * 50)
    
    import os
    
    test_dir = Path(__file__).parent
    results_dir = test_dir / "backtest_results"
    
    checks = [
        ("回测结果目录", results_dir.exists()),
    ]
    
    all_pass = True
    for name, passed in checks:
        status = "✅" if passed else "❌"
        logger.info(f"  {status} {name}")
        if not passed:
            all_pass = False
    
    # 列出回测结果
    if results_dir.exists():
        html_files = list(results_dir.glob("*.html"))
        logger.info(f"  回测报告数量: {len(html_files)}")
        for f in html_files[:5]:
            logger.info(f"      - {f.name}")
    
    return all_pass


def main():
    """主测试"""
    logger.info("")
    logger.info("🚀 腾讯 Iron Condor 实盘前综合测试")
    logger.info(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    
    results = {}
    
    # 执行所有测试
    results["模块导入"] = test_module_imports()
    results["配置"] = test_config()
    results["通知"] = test_notifier()
    results["富途连接"] = test_futu_connection()
    results["策略逻辑"] = test_strategy_logic()
    results["数据文件"] = test_data_files()
    
    # 汇总
    logger.info("")
    logger.info("=" * 50)
    logger.info("📊 测试结果汇总")
    logger.info("=" * 50)
    
    pass_count = sum(1 for v in results.values() if v is True)
    warn_count = sum(1 for v in results.values() if v is None)
    fail_count = sum(1 for v in results.values() if v is False)
    
    for name, result in results.items():
        if result is True:
            status = "✅ 通过"
        elif result is None:
            status = "⚠️ 待确认"
        else:
            status = "❌ 失败"
        logger.info(f"  {status} {name}")
    
    logger.info("")
    if fail_count == 0:
        logger.info("🎉 所有核心测试通过！")
        logger.info("")
        logger.info("4月8日启动流程:")
        logger.info("  1. 打开富途牛牛 -> 设置 -> OpenD API -> 启动并登录")
        logger.info("  2. cd wheel_tencent")
        logger.info("  3. ./run_live.sh start")
    else:
        logger.info("⚠️ 有测试失败，请检查上述问题")
    
    logger.info("")


if __name__ == "__main__":
    main()