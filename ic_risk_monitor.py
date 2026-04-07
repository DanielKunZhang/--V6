"""
Iron Condor 风险监控模块
功能：
1. 实时计算持仓的盈亏、风险指标
2. 估算盈利概率、盈亏比
3. 自动化止损策略介入
"""

import logging
from datetime import date
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RiskMetrics:
    """风险指标数据类"""
    # 基本信息
    current_price: float          # 当前正股价格
    net_premium: float            # 净权利金收入
    strikes: Dict                 # 行权价 {"sell_put": x, "buy_put": x, ...}
    expiry: date                  # 到期日
    dte: int                      # 距离到期天数
    
    # 盈亏计算
    max_profit: float             # 最大盈利
    max_loss: float               # 最大亏损
    breakeven_lower: float        # 下轨盈亏平衡点
    breakeven_upper: float        # 上轨盈亏平衡点
    
    # 风险指标
    profit_zone_pct: float         # 盈利区间占比 (%)
    loss_probability: float       # 亏损概率估算 (%)
    risk_reward_ratio: float      # 盈亏比 (reward/risk)
    
    # 当前状态
    unrealized_pl: float          # 未实现盈亏
    distance_to_loss: float       # 距最大亏损的空间 (%)


class ICRiskMonitor:
    """Iron Condor 风险监控器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # 止损配置（从 config 读取或用默认值）
        self.stop_loss_pct = self.config.get("stop_loss_pct", 0.20)      # 总亏损20%止损
        self.max_loss_multiple = self.config.get("max_loss_multiple", 2.0)  # 亏损超过2倍权利金止损
        self.profit_take_pct = self.config.get("profit_take_pct", 0.50)   # 盈利50%时部分平仓
    
    def calculate_metrics(
        self,
        current_price: float,
        strikes: Dict,
        net_premium: float,
        expiry: date,
        volatility: float = 0.35
    ) -> RiskMetrics:
        """
        计算铁鹰策略的风险指标
        
        Args:
            current_price: 当前正股价格
            strikes: 行权价 {"sell_put": 460, "buy_put": 420, "sell_call": 510, "buy_call": 550}
            net_premium: 净权利金（每股）
            expiry: 到期日
            volatility: 年化波动率（默认35%）
        
        Returns:
            RiskMetrics 对象
        """
        from datetime import date
        
        today = date.today()
        dte = (expiry - today).days if expiry else 0
        
        # 提取行权价
        sell_put_k = strikes.get("sell_put", 0)
        buy_put_k = strikes.get("buy_put", 0)
        sell_call_k = strikes.get("sell_call", 0)
        buy_call_k = strikes.get("buy_call", 0)
        
        # === 1. 最大盈利/亏损计算 ===
        # 最大盈利 = 净权利金（股价在盈利区间内到期）
        # 最大亏损 = 翼宽 - 净权利金
        wing_put = sell_put_k - buy_put_k      # Put 侧翼宽
        wing_call = buy_call_k - sell_call_k   # Call 侧翼宽
        wing = min(wing_put, wing_call)        # 取小值（铁鹰是对称结构）
        
        max_profit = net_premium * 100 * 2     # 2张合约
        max_loss = (wing * 100 * 2) - max_profit
        
        # === 2. 盈亏平衡点 ===
        # 下轨 = Sell Put 行权价 - 净权利金
        # 上轨 = Sell Call 行权价 + 净权利金
        breakeven_lower = sell_put_k - net_premium
        breakeven_upper = sell_call_k + net_premium
        
        # === 3. 盈利区间占比（基于正态分布）===
        # 假设股价服从正态分布
        daily_vol = volatility / (365 ** 0.5)
        period_vol = daily_vol * (dte ** 0.5) if dte > 0 else 0
        
        # 计算盈利区间宽度占正股价格的比例
        profit_zone_width = breakeven_upper - breakeven_lower
        profit_zone_pct = (profit_zone_width / current_price) * 100 if current_price > 0 else 0
        
        # === 4. 亏损概率估算 ===
        # 基于 Black-Scholes 和正态分布假设
        if period_vol > 0 and current_price > 0:
            # 股价低于下轨的概率
            z_lower = (breakeven_lower - current_price) / (current_price * period_vol)
            # 股价高于上轨的概率  
            z_upper = (breakeven_upper - current_price) / (current_price * period_vol)
            
            from scipy.stats import norm
            prob_below = norm.cdf(z_lower)
            prob_above = norm.cdf(z_upper)
            loss_probability = (prob_below + prob_above) * 100
        else:
            loss_probability = 50.0  # 默认50%
        
        # === 5. 盈亏比 ===
        risk_reward_ratio = abs(max_profit / max_loss) if max_loss != 0 else 0
        
        # === 6. 当前未实现盈亏（简化估算）===
        # 需要实时期权价格来精确计算，这里用简化方法
        unrealized_pl = 0.0
        distance_to_loss = 0.0
        
        # 距最大亏损的空间（假设股价向不利方向移动）
        if current_price > 0:
            # 计算当前股价相对于盈利区间的位置
            if current_price < breakeven_lower:
                # 低于下轨，向最大亏损方向移动
                pct_to_loss = (breakeven_lower - current_price) / current_price * 100
            elif current_price > breakeven_upper:
                # 高于上轨，向最大亏损方向移动
                pct_to_loss = (current_price - breakeven_upper) / current_price * 100
            else:
                pct_to_loss = 0.0
            distance_to_loss = pct_to_loss
        
        return RiskMetrics(
            current_price=current_price,
            net_premium=net_premium,
            strikes=strikes,
            expiry=expiry,
            dte=dte,
            max_profit=max_profit,
            max_loss=max_loss,
            breakeven_lower=breakeven_lower,
            breakeven_upper=breakeven_upper,
            profit_zone_pct=profit_zone_pct,
            loss_probability=loss_probability,
            risk_reward_ratio=risk_reward_ratio,
            unrealized_pl=unrealized_pl,
            distance_to_loss=distance_to_loss,
        )
    
    def check_stop_loss(
        self,
        metrics: RiskMetrics,
        positions: List[Dict],
        initial_capital: float = 60000
    ) -> Dict:
        """
        检查是否触发止损规则
        
        规则1: 单组亏损 > 2倍权利金
        规则2: 总亏损 > 初始资金的 X%
        规则3: 股价突破盈利区间 20% 以上
        
        Returns:
            {"triggered": bool, "reason": str, "action": str}
        """
        # 计算总未实现盈亏
        total_unrealized_pl = sum(p.get("unrealized_pl", 0) for p in positions)
        
        # 估算权利金收入（如果有记录）
        if metrics.net_premium > 0:
            estimated_credit = metrics.net_premium * 100 * 2
            leg_count = len(positions)
            group_count = max(1, leg_count // 4)
            total_credit = estimated_credit * group_count
            
            # 规则1: 单组亏损 > 2倍权利金
            if group_count > 0:
                avg_loss_per_group = abs(total_unrealized_pl) / group_count
                if avg_loss_per_group > estimated_credit * self.max_loss_multiple:
                    return {
                        "triggered": True,
                        "reason": f"单组亏损 {avg_loss_per_group:.0f} > 2倍权利金 {estimated_credit * 2:.0f}",
                        "action": "CLOSE_ALL",
                        "details": f"总亏损 {total_unrealized_pl:.0f}，共 {group_count} 组"
                    }
        
        # 规则2: 总亏损 > X% 初始资金
        loss_pct = abs(total_unrealized_pl) / initial_capital if initial_capital > 0 else 0
        if loss_pct > self.stop_loss_pct:
            return {
                "triggered": True,
                "reason": f"总亏损 {loss_pct*100:.1f}% > 止损线 {self.stop_loss_pct*100:.1f}%",
                "action": "CLOSE_ALL",
                "details": f"亏损 {total_unrealized_pl:.0f} HKD，初始资金 {initial_capital} HKD"
            }
        
        # 规则3: 股价距亏损区间太近
        if metrics.distance_to_loss > 15:  # 距离最大亏损超过15%
            return {
                "triggered": True,
                "reason": f"股价距最大亏损区域仅 {metrics.distance_to_loss:.1f}%",
                "action": "PARTIAL_CLOSE",
                "details": "建议部分平仓降低风险"
            }
        
        return {"triggered": False, "reason": "", "action": "HOLD"}
    
    def check_take_profit(
        self,
        metrics: RiskMetrics,
        positions: List[Dict]
    ) -> Dict:
        """
        检查是否触发止盈规则
        
        规则: 盈利达到最大盈利的 X% 时，部分平仓
        """
        if not positions or metrics.max_profit <= 0:
            return {"triggered": False, "reason": ""}
        
        total_pl = sum(p.get("unrealized_pl", 0) for p in positions)
        
        if total_pl > 0:
            profit_pct = total_pl / metrics.max_profit
            if profit_pct >= self.profit_take_pct:
                return {
                    "triggered": True,
                    "reason": f"盈利达到 {profit_pct*100:.0f}% > 止盈线 {self.profit_take_pct*100:.0f}%",
                    "action": "PARTIAL_CLOSE",
                    "details": f"盈利 {total_pl:.0f} / 最大盈利 {metrics.max_profit:.0f}"
                }
        
        return {"triggered": False, "reason": ""}
    
    def format_risk_report(self, metrics: RiskMetrics) -> str:
        """生成风险报告文本"""
        report = f"""
📊 Iron Condor 风险分析
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 权利金: {metrics.net_premium:.2f} USD/股 × 200 = {metrics.net_profit:.0f} USD
📈 最大盈利: +{metrics.max_profit:.0f} USD
📉 最大亏损: -{metrics.max_loss:.0f} USD
⚖️ 盈亏比: 1 : {abs(metrics.risk_reward_ratio):.2f}

📍 盈亏平衡点:
   下轨: {metrics.breakeven_lower:.2f}
   上轨: {metrics.breakeven_upper:.2f}

🎯 风险指标:
   盈利区间: {metrics.profit_zone_pct:.1f}% 股价范围
   亏损概率: {metrics.loss_probability:.1f}%
   DTE: {metrics.dte} 天

💡 建议: {"持有" if metrics.loss_probability < 40 else "关注"} | 盈亏比 {"优" if metrics.risk_reward_ratio > 1.5 else "一般"}
"""
        return report


def calculate_ic_metrics(
    current_price: float,
    sell_put_strike: float,
    buy_put_strike: float,
    sell_call_strike: float,
    buy_call_strike: float,
    net_premium_per_share: float,
    expiry: date,
    currency: str = "HKD"
) -> Dict:
    """
    快速计算 Iron Condor 风险指标（简化版）
    
    Returns:
        dict with keys: max_profit, max_loss, breakeven_lower, breakeven_upper,
                       loss_probability, risk_reward_ratio, profit_zone_pct
    """
    from datetime import date
    from scipy.stats import norm
    
    # DTE
    today = date.today()
    dte = (expiry - today).days if expiry else 30
    
    # 翼宽
    wing_put = sell_put_strike - buy_put_strike
    wing_call = buy_call_strike - sell_call_strike
    wing = min(wing_put, wing_call)
    
    # 合约乘数
    multiplier = 100 * 2  # 100股/张 × 2张
    
    # 最大盈亏
    max_profit = net_premium_per_share * multiplier
    max_loss = wing * multiplier - max_profit
    
    # 盈亏平衡点
    breakeven_lower = sell_put_strike - net_premium_per_share
    breakeven_upper = sell_call_strike + net_premium_per_share
    
    # 盈利区间
    profit_zone = breakeven_upper - breakeven_lower
    profit_zone_pct = (profit_zone / current_price) * 100 if current_price > 0 else 0
    
    # 亏损概率（假设正态分布，波动率35%）
    volatility = 0.35
    daily_vol = volatility / (365 ** 0.5)
    period_vol = daily_vol * (dte ** 0.5) if dte > 0 else 0
    
    if period_vol > 0 and current_price > 0:
        z_lower = (breakeven_lower - current_price) / (current_price * period_vol)
        z_upper = (breakeven_upper - current_price) / (current_price * period_vol)
        prob_below = norm.cdf(z_lower)
        prob_above = norm.cdf(z_upper)
        loss_probability = (prob_below + prob_above) * 100
    else:
        loss_probability = 50.0
    
    # 盈亏比
    risk_reward_ratio = abs(max_profit / max_loss) if max_loss != 0 else 0
    
    return {
        "currency": currency,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven_lower": breakeven_lower,
        "breakeven_upper": breakeven_upper,
        "profit_zone_pct": profit_zone_pct,
        "loss_probability": loss_probability,
        "risk_reward_ratio": risk_reward_ratio,
        "dte": dte,
        "wing": wing,
    }