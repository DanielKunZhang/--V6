"""
执行层 - 富途交易接口
处理订单下单、修改、取消等操作
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from futu import (
    OpenSecTradeContext, TrdMarket, SecurityFirm, TrdEnv, TrdSide,
    OrderType, RET_OK,
)

from config import FUTU_CONFIG, RUN_MODE

logger = logging.getLogger(__name__)


class FutuExecutor:
    """富途交易执行器"""

    def __init__(self):
        self.trade_ctx: Optional[OpenSecTradeContext] = None
        self.is_connected = False
        self.dry_run = RUN_MODE["dry_run"]

    def connect(self) -> bool:
        """连接交易通道"""
        try:
            self.trade_ctx = OpenSecTradeContext(
                filter_trdmarket=TrdMarket.HK,
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                security_firm=SecurityFirm.FUTUSECURITIES,
            )
            self.is_connected = True

            if self.dry_run:
                logger.info("🔧 运行模式: 模拟交易（不真实下单）")
            else:
                logger.info("✅ 富途交易通道已连接")

            return True
        except Exception as e:
            logger.error(f"❌ 连接富途交易通道失败: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """断开交易连接"""
        if self.trade_ctx:
            self.trade_ctx.close()
            self.is_connected = False
            logger.info("富途交易通道已断开")

    def _get_trade_env(self) -> TrdEnv:
        """获取交易环境"""
        return TrdEnv.SIMULATE if self.dry_run else TrdEnv.REAL

    def _get_acc_id(self) -> int:
        """获取账户 ID（大整数用 int(float()) 避免精度丢失）"""
        if self.dry_run:
            return int(float(FUTU_CONFIG["sim_acc_id"]))
        return int(float(FUTU_CONFIG["real_acc_id"]))

    def _place_order(
        self,
        code: str,
        trd_side: TrdSide,
        quantity: int,
        price: Optional[float],
    ) -> tuple:
        """底层下单（有价格用限价单，无价格用市价单）"""
        if price is not None and price > 0:
            order_type = OrderType.NORMAL
            order_price = price
        else:
            order_type = OrderType.MARKET
            order_price = 0.0  # 市价单 price 传 0

        return self.trade_ctx.place_order(
            code=code,
            price=order_price,
            qty=quantity,
            trd_side=trd_side,
            order_type=order_type,
            trd_env=self._get_trade_env(),
            acc_id=self._get_acc_id(),
        )

    def sell_put(
        self,
        option_code: str,
        strike: float,
        quantity: int,
        price: float = None,
        expiration: str = None
    ) -> Dict[str, Any]:
        """卖出看跌期权（开仓）"""
        if self.dry_run:
            logger.info(f"🔧 [模拟] 卖出 Put: {option_code}, 行权价 {strike}, 数量 {quantity} 张")
            return {
                "success": True,
                "模拟": True,
                "order_id": f"DRY_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "code": option_code,
                "side": "SELL",
                "quantity": quantity,
                "price": price or "MARKET",
            }

        if not self.is_connected and not self.connect():
            return {"success": False, "error": "连接失败"}

        try:
            ret, data = self._place_order(option_code, TrdSide.SELL, quantity, price)
            if ret == RET_OK:
                order_id = data.iloc[0]["order_id"]
                logger.info(f"✅ 卖出 Put 成功: {option_code}, 订单ID {order_id}")
                return {
                    "success": True,
                    "order_id": order_id,
                    "code": option_code,
                    "side": "SELL",
                    "quantity": quantity,
                }
            else:
                logger.error(f"❌ 卖出 Put 失败: {data}")
                return {"success": False, "error": data}
        except Exception as e:
            logger.error(f"❌ 卖出 Put 异常: {e}")
            return {"success": False, "error": str(e)}

    def sell_call(
        self,
        option_code: str,
        strike: float,
        quantity: int,
        price: float = None,
        expiration: str = None
    ) -> Dict[str, Any]:
        """卖出备兑看涨期权（开仓，需要先持有正股）"""
        if self.dry_run:
            logger.info(f"🔧 [模拟] 卖出 Covered Call: {option_code}, 行权价 {strike}, 数量 {quantity} 张")
            return {
                "success": True,
                "模拟": True,
                "order_id": f"DRY_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "code": option_code,
                "side": "SELL",
                "quantity": quantity,
                "price": price or "MARKET",
            }

        if not self.is_connected and not self.connect():
            return {"success": False, "error": "连接失败"}

        try:
            ret, data = self._place_order(option_code, TrdSide.SELL, quantity, price)
            if ret == RET_OK:
                order_id = data.iloc[0]["order_id"]
                logger.info(f"✅ 卖出 Covered Call 成功: {option_code}, 订单ID {order_id}")
                return {
                    "success": True,
                    "order_id": order_id,
                    "code": option_code,
                    "side": "SELL",
                    "quantity": quantity,
                }
            else:
                logger.error(f"❌ 卖出 Covered Call 失败: {data}")
                return {"success": False, "error": data}
        except Exception as e:
            logger.error(f"❌ 卖出 Covered Call 异常: {e}")
            return {"success": False, "error": str(e)}

    def close_position(
        self,
        option_code: str,
        quantity: int,
        price: float = None
    ) -> Dict[str, Any]:
        """平仓（买回期权）"""
        if self.dry_run:
            logger.info(f"🔧 [模拟] 平仓: {option_code}, 数量 {quantity} 张")
            return {
                "success": True,
                "模拟": True,
                "order_id": f"DRY_CLOSE_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            }

        if not self.is_connected and not self.connect():
            return {"success": False, "error": "连接失败"}

        try:
            ret, data = self._place_order(option_code, TrdSide.BUY, quantity, price)
            if ret == RET_OK:
                order_id = data.iloc[0]["order_id"]
                logger.info(f"✅ 平仓成功: {option_code}, 订单ID {order_id}")
                return {"success": True, "order_id": order_id}
            else:
                logger.error(f"❌ 平仓失败: {data}")
                return {"success": False, "error": data}
        except Exception as e:
            logger.error(f"❌ 平仓异常: {e}")
            return {"success": False, "error": str(e)}

    def get_positions(self) -> Dict[str, Any]:
        """获取当前持仓"""
        if not self.is_connected and not self.connect():
            return {"success": False, "error": "连接失败"}

        try:
            ret, data = self.trade_ctx.position_list_query(
                trd_env=self._get_trade_env(),
                acc_id=self._get_acc_id(),
                refresh_cache=True,
            )
            if ret == RET_OK:
                return {
                    "success": True,
                    "positions": data.to_dict("records") if not data.empty else [],
                }
            return {"success": False, "error": data}
        except Exception as e:
            logger.error(f"❌ 获取持仓失败: {e}")
            return {"success": False, "error": str(e)}

    def get_orders(self, status: str = None) -> Dict[str, Any]:
        """获取今日订单列表"""
        if not self.is_connected and not self.connect():
            return {"success": False, "error": "连接失败"}

        try:
            ret, data = self.trade_ctx.order_list_query(
                trd_env=self._get_trade_env(),
                acc_id=self._get_acc_id(),
                refresh_cache=True,
            )
            if ret == RET_OK:
                return {
                    "success": True,
                    "orders": data.to_dict("records") if not data.empty else [],
                }
            return {"success": False, "error": data}
        except Exception as e:
            logger.error(f"❌ 获取订单失败: {e}")
            return {"success": False, "error": str(e)}


# 全局单例
_executor: Optional[FutuExecutor] = None


def get_executor() -> FutuExecutor:
    global _executor
    if _executor is None:
        _executor = FutuExecutor()
    return _executor
