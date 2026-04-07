"""
腾讯 Wheel 策略主程序
全天候期权自动化交易机器人

使用方法:
    python main.py                    # 正常运行
    python main.py --dry-run          # 模拟模式（不真实下单）
    python main.py --once             # 单次执行（用于测试）
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from config import RUN_MODE, LOG_CONFIG, STOCK_CONFIG, WHEEL_CONFIG
from data import get_data_provider
from executor import get_executor
from strategy import WheelStrategy, WheelState, Position
from monitor import get_monitor, PositionMonitor
from notifier import get_notifier, notify_trade, notify_alert, notify_status


def setup_logging():
    """配置日志"""
    log_dir = Path(LOG_CONFIG["file"]).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # 使用 RotatingFileHandler (Python 3.12 兼容)
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(
        LOG_CONFIG["file"],
        maxBytes=LOG_CONFIG["max_bytes"],
        backupCount=LOG_CONFIG["backup_count"]
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    logging.basicConfig(
        level=getattr(logging, LOG_CONFIG["level"]),
        handlers=[handler, logging.StreamHandler()]
    )
    return logging.getLogger(__name__)


def is_market_open() -> bool:
    """检查是否在交易时段"""
    now = datetime.now()

    # 香港时间 9:30 - 16:00
    if now.hour < 9 or now.hour >= 16:
        return False
    if now.hour == 9 and now.minute < 30:
        return False

    # 周末
    if now.weekday() >= 5:
        return False

    return True


class WheelBot:
    """Wheel 策略执行机器人"""

    def __init__(self, dry_run: bool = None):
        self.logger = logging.getLogger(__name__)

        # 配置覆盖
        if dry_run is not None:
            RUN_MODE["dry_run"] = dry_run

        # 初始化组件
        self.data = get_data_provider()
        self.executor = get_executor()
        self.notifier = get_notifier()

        # 策略状态
        self.strategy = WheelStrategy()
        self.monitor: PositionMonitor = None

        self.logger.info("🚀 Wheel Bot 初始化完成")

    def connect(self) -> bool:
        """连接所有服务"""
        if not self.data.connect():
            return False
        if not self.executor.connect():
            return False
        return True

    def disconnect(self):
        """断开所有连接"""
        self.data.disconnect()
        self.executor.disconnect()

    def run_cycle(self) -> bool:
        """
        执行一个监控周期
        返回: 是否继续运行
        """
        ticker = STOCK_CONFIG["ticker"]
        ticker_name = STOCK_CONFIG["name"]

        # 获取当前股价
        quote = self.data.get_stock_quote(ticker)
        if not quote:
            self.logger.error("无法获取股价")
            return True

        current_price = quote["last_price"]
        self.logger.info(f"📈 {ticker_name} 当前价格: HKD {current_price:.2f}")

        # 初始化监控器
        if self.monitor is None:
            self.monitor = get_monitor(self.strategy)

        # ===== 状态机逻辑 =====

        # IDLE 状态：寻找卖 Put 机会
        if self.strategy.state == WheelState.IDLE:
            self._handle_idle_state(current_price)

        # SELL_PUT 状态：监控 Put 持仓
        elif self.strategy.state == WheelState.SELL_PUT:
            self._handle_sell_put_state(current_price)

        # HOLD_STOCK 状态：监控正股，寻找卖 Call 机会
        elif self.strategy.state == WheelState.HOLD_STOCK:
            self._handle_hold_stock_state(current_price)

        # SELL_CALL 状态：监控 Covered Call 持仓
        elif self.strategy.state == WheelState.SELL_CALL:
            self._handle_sell_call_state(current_price)

        # 检查警报
        risk = self.monitor.get_risk_metrics(current_price)
        should_alert, level, message = self.monitor.should_trigger_alert(current_price)
        if should_alert:
            notify_alert(level=level, message=message, details=str(risk))

        return True

    def _handle_idle_state(self, current_price: float):
        """处理空闲状态：寻找卖 Put 机会"""
        self.logger.info("🔍 寻找卖 Put 机会...")

        # 获取目标到期日
        expiration = self.strategy.get_target_expiration()

        # 寻找候选 Put
        candidates = self.data.find_put_candidates(
            current_price=current_price,
            config=WHEEL_CONFIG["put"],
            expiration=expiration
        )

        if not candidates:
            self.logger.info("今日暂无合适的 Put 候选")
            return

        # 判断是否应该卖
        should_sell, selected = self.strategy.should_sell_put(
            current_price=current_price,
            put_candidates=candidates
        )

        if not should_sell:
            return

        self.logger.info(f"✅ 选中 Put: {selected['code']}, 行权价 {selected['strike']}, 权利金 {selected['premium']}")

        # 执行卖 Put
        result = self.executor.sell_put(
            option_code=selected["code"],
            strike=selected["strike"],
            quantity=1,
            price=selected["bid"]
        )

        if result.get("success"):
            # 更新策略状态
            self.strategy.option_position = Position(
                code=selected["code"],
                type="PUT",
                strike=selected["strike"],
                quantity=1,
                premium=selected["premium"],
                open_date=date.today(),
                expiration=date.fromisoformat(selected["expiration"])
            )
            self.strategy.state = WheelState.SELL_PUT
            self.strategy.record_premium(selected["premium"])

            # 发送通知
            notify_trade(
                action="SELL_PUT",
                option_code=selected["code"],
                strike=selected["strike"],
                premium=selected["premium"],
                expiration=selected["expiration"]
            )
        else:
            self.logger.error(f"卖 Put 失败: {result.get('error')}")

    def _handle_sell_put_state(self, current_price: float):
        """处理卖 Put 状态：监控 Put 仓位"""
        if not self.strategy.option_position:
            self.strategy.state = WheelState.IDLE
            return

        opt = self.strategy.option_position
        self.logger.info(f"📋 监控 Put: {opt.code}, 剩余 {opt.dte} 天, 行权价 {opt.strike}")

        # 获取期权实时报价
        option_quote = self.data.get_option_quote(opt.code)

        # 检查是否应该平仓
        if option_quote:
            should_close, reason = self.strategy.should_close_position(
                current_price=current_price,
                option_quote=option_quote,
                position=opt
            )

            if should_close:
                self.logger.info(f"🔄 平仓原因: {reason}")

                # 执行平仓
                result = self.executor.close_position(
                    option_code=opt.code,
                    quantity=opt.quantity,
                    price=option_quote.get("ask")
                )

                if result.get("success"):
                    if reason == "expired_put":
                        # Put 过期未行权，策略完成
                        self.logger.info(f"✅ Put 到期作废，收取权利金 HKD {opt.premium:,.2f}")
                        self.strategy.option_position = None
                        self.strategy.state = WheelState.IDLE
                    elif reason in ["stop_loss", "profit_taken"]:
                        # 其他原因平仓
                        self.strategy.option_position = None
                        self.strategy.state = WheelState.IDLE

        # 检查是否被行权（仅在到期日且价内时触发，避免每次循环误触）
        if opt.is_expired and current_price <= opt.strike:
            self.logger.info(f"⚡ Put 被行权！股价 {current_price} <= 行权价 {opt.strike}")

            # 转换为持有正股
            self.strategy.on_put_assigned(
                strike=opt.strike,
                quantity=100,  # 1 张 = 100 股
                current_price=current_price
            )

            notify_trade(
                action="ASSIGNED",
                option_code=opt.code,
                strike=opt.strike,
                premium=opt.premium,
                expiration=str(opt.expiration)
            )

    def _handle_hold_stock_state(self, current_price: float):
        """处理持有正股状态：寻找卖 Call 机会"""
        if not self.strategy.stock_holding:
            self.strategy.state = WheelState.IDLE
            return

        stock = self.strategy.stock_holding
        self.logger.info(f"🏦 持有正股: {stock.quantity} 股, 成本 {stock.cost_basis}")

        # 获取目标到期日
        expiration = self.strategy.get_target_expiration()

        # 寻找候选 Call
        candidates = self.data.find_call_candidates(
            cost_basis=stock.cost_basis,
            current_price=current_price,
            config=WHEEL_CONFIG["call"],
            expiration=expiration
        )

        if not candidates:
            self.logger.info("今日暂无合适的 Call 候选")
            return

        # 判断是否应该卖
        should_sell, selected = self.strategy.should_sell_call(
            current_price=current_price,
            call_candidates=candidates
        )

        if not should_sell:
            return

        self.logger.info(f"✅ 选中 Call: {selected['code']}, 行权价 {selected['strike']}, 权利金 {selected['premium']}")

        # 执行卖 Call
        result = self.executor.sell_call(
            option_code=selected["code"],
            strike=selected["strike"],
            quantity=1,
            price=selected["bid"]
        )

        if result.get("success"):
            # 更新策略状态
            self.strategy.option_position = Position(
                code=selected["code"],
                type="CALL",
                strike=selected["strike"],
                quantity=1,
                premium=selected["premium"],
                open_date=date.today(),
                expiration=date.fromisoformat(selected["expiration"]),
                cost_basis=stock.cost_basis
            )
            self.strategy.state = WheelState.SELL_CALL
            self.strategy.record_premium(selected["premium"])

            # 发送通知
            notify_trade(
                action="SELL_CALL",
                option_code=selected["code"],
                strike=selected["strike"],
                premium=selected["premium"],
                expiration=selected["expiration"]
            )
        else:
            self.logger.error(f"卖 Call 失败: {result.get('error')}")

    def _handle_sell_call_state(self, current_price: float):
        """处理卖 Covered Call 状态：监控 Call 仓位"""
        if not self.strategy.option_position:
            self.strategy.state = WheelState.IDLE
            return

        if not self.strategy.stock_holding:
            # 没有正股了，清理期权
            self.strategy.option_position = None
            self.strategy.state = WheelState.IDLE
            return

        opt = self.strategy.option_position
        self.logger.info(f"📋 监控 Call: {opt.code}, 剩余 {opt.dte} 天, 行权价 {opt.strike}")

        # 获取期权实时报价
        option_quote = self.data.get_option_quote(opt.code)

        # 检查是否应该平仓
        if option_quote:
            should_close, reason = self.strategy.should_close_position(
                current_price=current_price,
                option_quote=option_quote,
                position=opt
            )

            if should_close:
                self.logger.info(f"🔄 平仓原因: {reason}")

                result = self.executor.close_position(
                    option_code=opt.code,
                    quantity=opt.quantity,
                    price=option_quote.get("ask")
                )

                if result.get("success"):
                    self.strategy.option_position = None
                    if reason == "expired_call":
                        # Call 过期未行权，继续持有正股
                        self.logger.info(f"✅ Call 到期作废，继续持有正股")
                        self.strategy.state = WheelState.HOLD_STOCK
                    elif reason in ["stop_loss", "profit_taken", "rolled"]:
                        self.strategy.state = WheelState.HOLD_STOCK

        # 检查是否被行权（仅在到期日且价内时触发，避免每次循环误触）
        if opt.is_expired and current_price >= opt.strike:
            self.logger.info(f"⚡ Call 被行权！股价 {current_price} >= 行权价 {opt.strike}")

            sale_proceeds = self.strategy.on_call_assigned(
                strike=opt.strike,
                quantity=self.strategy.stock_holding.quantity if self.strategy.stock_holding else 100
            )

            # 如果没有正股了，回到 IDLE
            if not self.strategy.stock_holding:
                self.strategy.state = WheelState.IDLE

            notify_trade(
                action="ASSIGNED",
                option_code=opt.code,
                strike=opt.strike,
                premium=opt.premium,
                expiration=str(opt.expiration)
            )

    def run(self):
        """主循环"""
        self.logger.info("=" * 50)
        self.logger.info("🚀 腾讯 Wheel 策略机器人启动")
        self.logger.info(f"模式: {'🔧 模拟交易' if RUN_MODE['dry_run'] else '💰 真实交易'}")
        self.logger.info("=" * 50)

        # 连接
        if not self.connect():
            self.logger.error("连接失败，退出")
            return

        try:
            while True:
                # 检查是否在交易时段
                if RUN_MODE["market_open_check"] and not is_market_open():
                    self.logger.info("⏰ 非交易时段，等待...")
                    time.sleep(RUN_MODE["check_interval"])
                    continue

                # 执行一个周期
                try:
                    self.run_cycle()
                except Exception as e:
                    self.logger.error(f"执行周期异常: {e}", exc_info=True)

                # 等待
                time.sleep(RUN_MODE["check_interval"])

        except KeyboardInterrupt:
            self.logger.info("👋 用户中断，退出")
        finally:
            self.disconnect()
            self.logger.info("🏁 机器人已停止")


def main():
    """入口"""
    parser = argparse.ArgumentParser(description="腾讯 Wheel 策略机器人")
    parser.add_argument("--dry-run", action="store_true", help="模拟模式（不真实下单）")
    parser.add_argument("--once", action="store_true", help="单次执行（用于测试）")
    args = parser.parse_args()

    # 设置日志
    logger = setup_logging()

    # 创建并运行机器人
    bot = WheelBot(dry_run=args.dry_run or RUN_MODE["dry_run"])

    if args.once:
        # 单次执行
        if bot.connect():
            bot.run_cycle()
            bot.disconnect()
    else:
        # 持续运行
        bot.run()


if __name__ == "__main__":
    main()
