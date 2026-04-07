"""
持仓监控层
实时监控仓位希腊字母、保证金、风险指标
"""

import logging
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import pandas as pd

from config import RISK_CONFIG, STOCK_CONFIG, WHEEL_CONFIG
from data import get_data_provider
from strategy import WheelStrategy, WheelState

logger = logging.getLogger(__name__)


@dataclass
class Greeks:
    """期权希腊字母"""
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    implied_volatility: float = 0.0


@dataclass
class PositionMonitor:
    """仓位监控器"""

    strategy: WheelStrategy
    greeks: Greeks = None

    def calculate_greeks(
        self,
        option_quote: Dict,
        underlying_price: float,
        strike: float,
        dte: int,
        option_type: str  # "CALL" or "PUT"
    ) -> Greeks:
        """
        估算希腊字母
        注意：精确计算需要 Black-Scholes，这里用简化模型
        """
        import math

        # 简化 IV 计算
        iv = option_quote.get("implied_volatility", 0.20)
        if iv <= 0:
            iv = 0.20  # 默认 20% IV

        # 简化计算
        T = dte / 365
        if T <= 0:
            T = 1 / 365

        # moneyness
        if option_type == "CALL":
            moneyness = underlying_price / strike
        else:
            moneyness = strike / underlying_price

        # 简化 Delta
        if option_type == "CALL":
            if moneyness > 1.05:
                delta = 0.8
            elif moneyness < 0.95:
                delta = 0.2
            else:
                delta = 0.5
        else:
            if moneyness < 0.95:
                delta = -0.8
            elif moneyness > 1.05:
                delta = -0.2
            else:
                delta = -0.5

        # 简化 Gamma（ATM 附近最大）
        atm_distance = abs(moneyness - 1.0)
        gamma = 0.05 * (1 - atm_distance * 10)
        gamma = max(0.001, gamma)

        # Theta（每天消耗的价值）
        option_price = option_quote.get("last_price", 0)
        theta = option_price / max(dte, 1) * (-0.5)

        # Vega（IV 变化影响）
        vega = option_price * 0.1

        self.greeks = Greeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            implied_volatility=iv
        )

        return self.greeks

    def get_risk_metrics(
        self,
        current_price: float,
        option_quote: Dict = None
    ) -> Dict[str, Any]:
        """
        计算风险指标
        """
        metrics = {
            "portfolio_pnl": 0,
            "daily_theta_collected": 0,
            "max_risk": 0,
            "risk_level": "NORMAL",
        }

        if not self.strategy.stock_holding:
            return metrics

        stock = self.strategy.stock_holding
        stock_value = stock.quantity * current_price
        cost_basis_total = stock.cost_basis * stock.quantity

        # 账面盈亏
        metrics["stock_value"] = stock_value
        metrics["cost_basis"] = cost_basis_total
        metrics["unrealized_pnl"] = stock_value - cost_basis_total
        metrics["unrealized_pnl_pct"] = (
            (current_price - stock.cost_basis) / stock.cost_basis * 100
        )

        # 如果有期权持仓
        if self.strategy.option_position and option_quote:
            opt = self.strategy.option_position
            greeks = self.calculate_greeks(
                option_quote,
                current_price,
                opt.strike,
                opt.dte,
                opt.type
            )

            metrics["daily_theta"] = greeks.theta * 100 * opt.quantity
            metrics["position_delta"] = greeks.delta * 100 * opt.quantity
            metrics["implied_volatility"] = greeks.implied_volatility

            if opt.type == "PUT":
                # 卖 Put 的最大风险 = 跌到 0
                metrics["max_risk"] = stock_value
            else:
                # 卖 Call 的最大风险 = 无限（理论上）
                metrics["max_risk"] = stock_value

        # 风险等级
        if stock.cost_basis > 0:
            drawdown = (current_price - stock.cost_basis) / stock.cost_basis

            if drawdown <= -RISK_CONFIG["emergency_exit"]:
                metrics["risk_level"] = "CRITICAL"
            elif drawdown <= -RISK_CONFIG["stop_loss_pct"]:
                metrics["risk_level"] = "WARNING"
            else:
                metrics["risk_level"] = "NORMAL"

        return metrics

    def should_trigger_alert(
        self,
        current_price: float,
        daily_loss: float = 0
    ) -> tuple[bool, str, str]:
        """
        检查是否触发警报

        Returns:
            (should_alert, alert_level, message)
            alert_level: "INFO" | "WARNING" | "CRITICAL"
        """
        # 检查日亏损
        if daily_loss >= RISK_CONFIG["max_daily_loss"]:
            return True, "WARNING", f"日亏损超过 HKD {daily_loss:,.0f}"

        # 检查风险等级
        if self.strategy.stock_holding:
            stock = self.strategy.stock_holding
            if stock.cost_basis > 0:
                drawdown = (current_price - stock.cost_basis) / stock.cost_basis

                if drawdown <= -RISK_CONFIG["emergency_exit"]:
                    return True, "CRITICAL", f"触及紧急止损线 ({drawdown:.1%})"
                elif drawdown <= -RISK_CONFIG["stop_loss_pct"]:
                    return True, "WARNING", f"触及止损线 ({drawdown:.1%})"

        # 检查期权即将到期
        if self.strategy.option_position:
            opt = self.strategy.option_position
            if opt.dte <= 3:
                return True, "INFO", f"期权即将到期 ({opt.dte}天)"

        return False, "", ""

    def generate_status_report(
        self,
        current_price: float,
        option_quote: Dict = None
    ) -> str:
        """
        生成状态报告文本
        """
        status = self.strategy.get_status()
        risk = self.get_risk_metrics(current_price, option_quote)

        lines = [
            f"📊 腾讯 Wheel 策略状态",
            f"=" * 30,
            f"🟢 状态: {status['state'].upper()}",
            f"💰 累计权利金: HKD {status['total_premium']:,.2f}",
            f"📈 交易次数: {status['total_trades']}",
            "",
        ]

        if status.get("option"):
            opt = status["option"]
            lines.extend([
                f"📋 期权持仓:",
                f"   代码: {opt['code']}",
                f"   类型: {opt['type']}",
                f"   行权价: HKD {opt['strike']:.2f}",
                f"   剩余天数: {opt['dte']} 天",
                f"   权利金: HKD {opt['premium']:,.2f}",
                "",
            ])

        if status.get("stock"):
            stock = status["stock"]
            lines.extend([
                f"🏦 正股持仓:",
                f"   数量: {stock['quantity']} 股",
                f"   成本: HKD {stock['cost_basis']:.2f}",
                f"   当前价: HKD {current_price:.2f}",
                f"   账面盈亏: HKD {risk.get('unrealized_pnl', 0):,.2f} ({risk.get('unrealized_pnl_pct', 0):.1f}%)",
                "",
            ])

        lines.extend([
            f"⚠️ 风险等级: {risk['risk_level']}",
        ])

        return "\n".join(lines)


def get_monitor(strategy: WheelStrategy) -> PositionMonitor:
    return PositionMonitor(strategy=strategy)
