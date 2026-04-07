"""
Wheel 策略核心逻辑
状态机：IDLE → SELL_PUT → HOLD_STOCK → SELL_CALL → IDLE
"""

import logging
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from config import WHEEL_CONFIG, RISK_CONFIG, STOCK_CONFIG

logger = logging.getLogger(__name__)


class WheelState(Enum):
    """Wheel 策略状态"""
    IDLE = "idle"                    # 空闲，等待机会
    SELL_PUT = "sell_put"            # 持有卖 Put 仓位
    HOLD_STOCK = "hold_stock"        # 持有正股（被行权后）
    SELL_CALL = "sell_call"          # 持有卖 Covered Call


@dataclass
class Position:
    """持仓记录"""
    code: str                         # 期权代码
    type: str                         # "PUT" or "CALL"
    strike: float                     # 行权价
    quantity: int                    # 合约数量
    premium: float                    # 收取的权利金
    open_date: date                  # 开仓日期
    expiration: date                 # 到期日
    cost_basis: float = 0.0         # 对应正股成本（如有）

    @property
    def dte(self) -> int:
        """剩余天数"""
        return (self.expiration - date.today()).days

    @property
    def is_expired(self) -> bool:
        return self.dte <= 0


@dataclass
class StockHolding:
    """正股持仓"""
    ticker: str                      # 股票代码
    quantity: int                    # 持股数量
    cost_basis: float                # 成本价
    acquired_date: date              # 买入日期

    @property
    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.cost_basis) * self.quantity

    @property
    def unrealized_pnl_pct(self, current_price: float) -> float:
        if self.cost_basis == 0:
            return 0
        return (current_price - self.cost_basis) / self.cost_basis * 100


@dataclass
class WheelStrategy:
    """Wheel 策略状态机"""

    state: WheelState = WheelState.IDLE
    stock_holding: Optional[StockHolding] = None
    option_position: Optional[Position] = None
    total_premium_collected: float = 0.0
    total_trades: int = 0
    pnl_history: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        self.put_config = WHEEL_CONFIG["put"]
        self.call_config = WHEEL_CONFIG["call"]
        self.position_config = WHEEL_CONFIG["position"]
        self.risk_config = RISK_CONFIG

    def get_target_expiration(self, target_dte: int = None) -> str:
        """计算目标到期日"""
        if target_dte is None:
            target_dte = self.put_config["dte_target"]

        # 找到最近的月末或指定天数后的到期日
        today = date.today()

        # 尝试找月末
        if target_dte <= 7:
            # 周到期
            target_date = today + timedelta(days=target_dte)
        else:
            # 找最近一个月的月末
            if today.month == 12:
                next_month = date(today.year + 1, 1, 1)
            else:
                next_month = date(today.year, today.month + 1, 1)
            month_end = next_month - timedelta(days=1)

            if month_end >= today + timedelta(days=target_dte):
                target_date = month_end
            else:
                # 下个月末
                if next_month.month == 12:
                    following = date(next_month.year + 1, 1, 1)
                else:
                    following = date(next_month.year, next_month.month + 1, 1)
                target_date = following - timedelta(days=1)

        return target_date.strftime("%Y-%m-%d")

    def should_sell_put(
        self,
        current_price: float,
        put_candidates: List[Dict]
    ) -> tuple[bool, Optional[Dict]]:
        """
        判断是否应该卖 Put

        Returns:
            (should_sell, selected_option)
        """
        # 状态检查
        if self.state != WheelState.IDLE:
            return False, None

        # 没有候选
        if not put_candidates:
            logger.info("没有合适的 Put 候选期权")
            return False, None

        # 流动性检查
        best_put = put_candidates[0]
        if best_put["volume"] < 5:  # 至少5张成交量
            logger.warning(f"最佳 Put {best_put['code']} 成交量不足: {best_put['volume']}")
            return False, None

        # 权利金检查
        if best_put["premium"] < self.put_config["min_premium"]:
            logger.info(f"最佳 Put 权利金不足: {best_put['premium']} < {self.put_config['min_premium']}")
            return False, None

        # 行权价距离检查
        strike_pct_below = (current_price - best_put["strike"]) / current_price
        if strike_pct_below < 0.05:  # 至少低于现价 5%
            logger.info(f"Put 行权价距离太近: {strike_pct_below:.1%}")
            return False, None

        return True, best_put

    def should_sell_call(
        self,
        current_price: float,
        call_candidates: List[Dict]
    ) -> tuple[bool, Optional[Dict]]:
        """
        判断是否应该卖 Covered Call

        Returns:
            (should_sell, selected_option)
        """
        # 状态检查
        if not self.stock_holding:
            return False, None

        if not call_candidates:
            logger.info("没有合适的 Call 候选期权")
            return False, None

        # 流动性检查
        best_call = call_candidates[0]
        if best_call["volume"] < 5:
            logger.warning(f"最佳 Call {best_call['code']} 成交量不足: {best_call['volume']}")
            return False, None

        # 权利金检查
        if best_call["premium"] < self.call_config["min_premium"]:
            logger.info(f"最佳 Call 权利金不足")
            return False, None

        # 行权价检查 - 应该高于成本价
        if best_call["strike"] <= self.stock_holding.cost_basis:
            logger.info(f"Call 行权价不高于成本价，跳过")
            return False, None

        return True, best_call

    def should_close_position(
        self,
        current_price: float,
        option_quote: Dict,
        position: Position
    ) -> tuple[bool, str]:
        """
        判断是否应该平仓

        Returns:
            (should_close, reason)
            reason: "profit_taken" | "stop_loss" | "rolled"
        """
        if not position:
            return False, ""

        # 到期处理
        if position.is_expired:
            if position.type == "PUT":
                return True, "expired_put"
            else:
                return True, "expired_call"

        # 止损检查
        if position.type == "PUT":
            # 卖 Put 的止损：股价跌破行权价太多
            distance_below_strike = (position.strike - current_price) / position.strike
            if distance_below_strike >= self.risk_config["stop_loss_pct"]:
                return True, "stop_loss"

        elif position.type == "CALL":
            # 卖 Call 的止损：股价涨破行权价太多
            distance_above_strike = (current_price - position.strike) / position.strike
            if distance_above_strike >= self.risk_config["stop_loss_pct"]:
                return True, "stop_loss"

        # 利润了结（Theta 收割）
        # 当权利金已经消耗了 70% 以上，可以考虑平仓
        remaining_premium = option_quote.get("bid", 0) * 100
        premium_consumed = position.premium - remaining_premium
        if position.premium > 0:
            consumed_pct = premium_consumed / position.premium
            if consumed_pct >= 0.70 and position.dte <= 7:
                return True, "profit_taken"

        # 展期检查
        if position.dte <= 5:
            return True, "rolled"

        return False, ""

    def on_put_assigned(
        self,
        strike: float,
        quantity: int,
        current_price: float
    ) -> StockHolding:
        """
        Put 被行权，转换为持有正股
        """
        logger.info(f"🟢 Put 被行权！以 {strike} 买入 {quantity} 股")

        self.stock_holding = StockHolding(
            ticker=STOCK_CONFIG["ticker"],
            quantity=quantity,
            cost_basis=strike,  # 成本 = 行权价
            acquired_date=date.today()
        )

        self.state = WheelState.HOLD_STOCK

        return self.stock_holding

    def on_call_assigned(
        self,
        strike: float,
        quantity: int
    ) -> float:
        """
        Call 被行权，卖出正股
        返回卖出总价
        """
        logger.info(f"🔴 Call 被行权！以 {strike} 卖出 {quantity} 股")

        if not self.stock_holding:
            logger.error("没有正股持仓，但 Call 被行权！")
            return 0

        sale_proceeds = strike * quantity

        # 记录 P&L
        cost = self.stock_holding.cost_basis * self.stock_holding.quantity
        stock_pnl = sale_proceeds - cost
        self.pnl_history.append({
            "date": date.today(),
            "type": "call_assigned",
            "cost": cost,
            "proceeds": sale_proceeds,
            "pnl": stock_pnl
        })

        self.stock_holding = None
        self.option_position = None
        self.state = WheelState.IDLE

        return sale_proceeds

    def record_premium(self, premium: float):
        """记录收取的权利金"""
        self.total_premium_collected += premium
        self.total_trades += 1
        logger.info(f"💰 已累计收取权利金: HKD {self.total_premium_collected:,.2f}")

    def get_status(self) -> Dict:
        """获取策略状态摘要"""
        status = {
            "state": self.state.value,
            "total_premium": self.total_premium_collected,
            "total_trades": self.total_trades,
        }

        if self.option_position:
            status["option"] = {
                "code": self.option_position.code,
                "type": self.option_position.type,
                "strike": self.option_position.strike,
                "dte": self.option_position.dte,
                "premium": self.option_position.premium,
            }

        if self.stock_holding:
            status["stock"] = {
                "quantity": self.stock_holding.quantity,
                "cost_basis": self.stock_holding.cost_basis,
                "acquired_date": self.stock_holding.acquired_date,
            }

        return status
