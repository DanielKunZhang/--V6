"""
Iron Condor 策略状态机
震荡市收租神器 - 同时卖出 Put 和 Call，锁定上下行风险

Iron Condor 结构（卖方价差）：
- 卖出 PUT (更价内) + 买入 PUT (更虚值) = PUT 价差
- 卖出 CALL (更价内) + 买入 CALL (更虚值) = CALL 价差

盈亏分析：
- 股价在中部 → 收取全部权利金
- 股价跌破 PUT 边 → 亏损有限（价差）
- 股价涨破 CALL 边 → 亏损有限（价差）
"""

# 导入 pandas
import pandas as pd

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum

from config import IRON_CONDOR_CONFIG, POSITION_CONFIG, RUN_MODE


class ICState(Enum):
    """Iron Condor 状态"""
    IDLE = "IDLE"                    # 空仓，等待开仓
    OPENING = "OPENING"              # 开仓中（正在下4条单）
    OPENED = "OPENED"               # 已开仓，监控中
    CLOSING = "CLOSING"             # 平仓中
    CLOSED = "CLOSED"               # 已平仓（结算完成）


@dataclass
class ICLeg:
    """单条腿"""
    code: str                      # 期权代码
    type: str                    # PUT or CALL
    side: str                    # BUY or SELL
    strike: float                 # 行权价
    price: float                # 开仓价格（HKD）
    quantity: int = 1           # 数量
    open_date: date = None      # 开仓日期
    
    @property
    def is_sold(self) -> bool:
        return self.side == "SELL"
    
    @property
    def is_put(self) -> bool:
        return self.type == "PUT"


@dataclass
class ICPosition:
    """Iron Condor 持仓（4条腿）"""
    # PUT 边
    sell_put: ICLeg              # 卖出的 PUT（更价内）
    buy_put: ICLeg               # 买入的 PUT（更虚值）
    
    # CALL 边
    sell_call: ICLeg             # 卖出的 CALL（更价内）
    buy_call: ICLeg              # 买入的 CALL（更虚值）
    
    # 组合信息
    net_credit: float           # 净权利金（收到的 - 支出的）
    open_date: date
    expiration: date
    
    @property
    def n_days_to_expire(self) -> int:
        """剩余天数"""
        return (self.expiration - date.today()).days
    
    @property
    def max_loss(self) -> float:
        """单组最大亏损（HKD）"""
        # PUT 边最大亏损
        put_risk = (self.sell_put.strike - self.buy_put.strike) * 100
        # CALL 边最大亏损
        call_risk = (self.buy_call.strike - self.sell_call.strike) * 100
        return max(put_risk, call_risk)
    
    def get_strike_range(self) -> tuple:
        """获取安全边界"""
        return (self.buy_put.strike, self.sell_call.strike)
    
    def check_risk(self, current_price: float) -> dict:
        """检查风险状态"""
        lower_bound = self.buy_put.strike
        upper_bound = self.sell_call.strike
        
        # 价格在安全区间
        if lower_bound < current_price < upper_bound:
            return {"status": "safe", "message": "价格在安全区间"}
        
        # 价格跌破 PUT 边界
        if current_price <= lower_bound:
            loss = (self.sell_put.strike - self.buy_put.strike) * 100 - self.net_credit
            return {
                "status": "risk",
                "message": f"PUT 被行权风险",
                "pnl": -loss,
                "side": "PUT"
            }
        
        # 价格突破 CALL 边界
        if current_price >= upper_bound:
            loss = (self.buy_call.strike - self.sell_call.strike) * 100 - self.net_credit
            return {
                "status": "risk", 
                "message": f"CALL 被行权风险",
                "pnl": -loss,
                "side": "CALL"
            }
        
        return {"status": "unknown", "message": "未知状态"}


class ICStrategy:
    """Iron Condor 策略"""
    
    # 策略参数
    ticker = IRON_CONDOR_CONFIG.get("ticker", "HK.00700")
    otm = IRON_CONDOR_CONFIG.get("otm", 0.05)           # 5% OTM
    wing = IRON_CONDOR_CONFIG.get("wing", 0.08)         # 8% Wing
    dte = IRON_CONDOR_CONFIG.get("dte", 7)              # 7天到期
    min_premium = IRON_CONDOR_CONFIG.get("min_premium", 1000)  # 最低权利金
    early_close_days = IRON_CONDOR_CONFIG.get("early_close_days", 1)  # 提前1天平仓
    
    # 仓位限制
    max_simultaneous = POSITION_CONFIG.get("max_simultaneous_trades", 2)
    min_days_between = POSITION_CONFIG.get("min_days_between_trades", 3)
    
    def __init__(self):
        self.state = ICState.IDLE
        self.position: Optional[ICPosition] = None
        
        # 统计
        self.total_premiums = 0.0
        self.n_trades = 0
        self.last_open_date: Optional[date] = None
    
    @property
    def is_idle(self) -> bool:
        return self.state == ICState.IDLE
    
    @property
    def is_opened(self) -> bool:
        return self.state == ICState.OPENED
    
    def can_open(self) -> bool:
        """是否可以开仓"""
        if not self.is_idle:
            return False
        
        # 检查开仓间隔
        if self.last_open_date:
            days_since = (date.today() - self.last_open_date).days
            if days_since < self.min_days_between:
                return False
        
        return True
    
    def get_target_expiration(self) -> date:
        """获取目标到期日"""
        return date.today() + timedelta(days=self.dte)
    
    def calculate_strikes(self, current_price: float) -> Dict[str, float]:
        """
        计算 Iron Condor 的 4 个行权价
        
        结构：
        - sell_put: 卖出 PUT，更接近价内（行权价 = S * (1 - otm)）
        - buy_put: 买入 PUT，更虚值（行权价 = S * (1 - otm - wing)）
        - sell_call: 卖出 CALL，更接近价内（行权价 = S * (1 + otm - wing)）
        - buy_call: 买入 CALL，更虚值（行权价 = S * (1 + otm)）
        """
        otm = self.otm
        wing = self.wing
        
        # PUT 边
        buy_put_k = current_price * (1 - otm)         # 更虚值
        sell_put_k = current_price * (1 - otm + wing)   # 更接近价内
        
        # CALL 边  
        sell_call_k = current_price * (1 + otm - wing)  # 更接近价内
        buy_call_k = current_price * (1 + otm)          # 更虚值
        
        return {
            "sell_put": sell_put_k,
            "buy_put": buy_put_k,
            "sell_call": sell_call_k,
            "buy_call": buy_call_k,
        }
    
    def should_open(self, current_price: float, option_chain: pd.DataFrame, estimated_credit: float) -> bool:
        """
        判断是否应该开仓
        
        Returns:
            (should_open, legs_info)
        """
        if not self.can_open():
            return False, None
        
        # 检查最低权利金
        if estimated_credit < self.min_premium:
            return False, None
        
        # 检查价格合理性
        strikes = self.calculate_strikes(current_price)
        
        # TODO: 检查期权链是否有流动性
        # 暂时先返回 True
        
        return True, strikes
    
    def should_close(self, current_price: float) -> tuple:
        """
        判断是否应该平仓
        
        Returns:
            (should_close, reason)
        """
        if not self.is_opened or not self.position:
            return False, ""
        
        # 提前平仓：到期前 N 天
        if self.position.n_days_to_expire <= self.early_close_days:
            return True, f"到期前{self.early_close_days}天平仓"
        
        # 价格突破边界
        risk_info = self.position.check_risk(current_price)
        if risk_info["status"] == "risk":
            return True, risk_info["message"]
        
        return False, ""
    
    def record_open(self, net_credit: float):
        """记录开仓"""
        self.last_open_date = date.today()
        self.total_premiums += net_credit
        self.n_trades += 1
    
    def record_close(self, pnl: float):
        """记录平仓"""
        self.state = ICState.IDLE
        self.position = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于通知）"""
        if self.position:
            return {
                "state": self.state.value,
                "sell_put": f"{self.position.sell_put.code} @ {self.position.sell_put.strike}",
                "buy_put": f"{self.position.buy_put.code} @ {self.position.buy_put.strike}",
                "sell_call": f"{self.position.sell_call.code} @ {self.position.sell_call.strike}",
                "buy_call": f"{self.position.buy_call.code} @ {self.position.buy_call.strike}",
                "net_credit": self.position.net_credit,
                "expiration": str(self.position.expiration),
                "days_to_expire": self.position.n_days_to_expire,
            }
        return {
            "state": self.state.value,
            "position": None,
        }