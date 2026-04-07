"""
Iron Condor 策略回测 - 震荡市收租神器
数据来源：富途 OpenD API
期权定价：Black-Scholes + 历史波动率
"""

import sys
import math
import logging
import argparse
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline, bs_option_price, historical_volatility

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  港股期权月度到期日辅助函数
# ─────────────────────────────────────────────

def hk_option_expiry_for_month(year: int, month: int) -> date:
    """
    计算港股期权当月到期日：当月最后一个交易日的前一个交易日。
    简化实现：忽略节假日，取当月倒数第二个工作日（周一~周五）。
    港交所实际规则：月份合约在该月最后交易日（交易所公告）到期。
    此处保守估算：取最后一周的倒数第二个工作日。
    """
    # 找当月最后一天
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    
    # 往前数，找到工作日
    workdays_found = 0
    while True:
        if d.weekday() < 5:  # 周一~周五
            workdays_found += 1
            if workdays_found == 2:  # 倒数第二个工作日
                return d
        d -= timedelta(days=1)


def get_hk_option_expiries(start: date, end: date) -> List[date]:
    """获取区间内所有月度到期日"""
    expiries = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        exp = hk_option_expiry_for_month(y, m)
        if start <= exp <= end:
            expiries.append(exp)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return expiries


def get_next_expiry(current: date, expiries: List[date]) -> Optional[date]:
    """返回 current 之后（含当天）的下一个到期日"""
    for exp in expiries:
        if exp >= current:
            return exp
    return None


# ─────────────────────────────────────────────
#  Iron Condor 策略
# ─────────────────────────────────────────────

@dataclass
class IronCondorPosition:
    """Iron Condor 持仓"""
    sell_put_k: float       # 卖出的PUT行权价
    buy_put_k: float        # 买入的PUT行权价（更虚值）
    sell_call_k: float      # 卖出的CALL行权价
    buy_call_k: float       # 买入的CALL行权价（更虚值）
    net_credit: float       # 收到的净权利金（4条腿合计）
    open_date: date
    expiration: date
    lot_size: int = 100


class IronCondorBacktester:
    """Iron Condor 策略回测器 - V3增强版
    
    V3新增功能：
    1. 止损缓冲（stop_loss_buffer）- 避免过于敏感的止损
    2. 动态滑点模型 - 根据期权虚实值程度调整滑点
    3. 波动率过滤模式 - 支持分位数波动率回测
    4. 凯利公式仓位管理
    """
    
    LOT_SIZE = 100          # 港股期权每手
    COMMISSION = 40          # 单张期权佣金 HKD
    SLIPPAGE_PCT = 0.005    # 基础滑点（从0.3%提高到0.5%，更真实）
    
    # 优化参数（带默认值）
    def __init__(self, 
                 initial_capital: float = 100_000,
                 wing_width: float = 0.05,    # 价差宽度：5% = 5个行权价间距
                 otm_distance: float = 0.05,   # OTM距离：5% = 离现价5%
                 dte: int = 45,                # 到期天数（entry_mode="dte"时使用）
                 label: str = "",
                 # 新增优化参数
                 min_iv: float = 0.20,         # 最低IV阈值（20%）
                 early_close_days: int = 2,    # 到期前N天平仓
                 max_loss_pct: float = 0.02,   # 单笔最大亏损2%
                 stop_loss_pct: float = 0.05,  # 总回撤5%止损
                 max_groups: int = 1,          # 最多同时开仓组数
                 # 新增：入场模式
                 entry_mode: str = "dte",      # "dte"=固定DTE | "pre_expiry"=到期前N天入场
                 entry_days_before_expiry: int = 7,  # entry_mode="pre_expiry"时，距到期日几天入场
                 # === V4 修复参数（默认值已调整） ===
                 stop_loss_buffer: float = 1.5,  # 止损缓冲倍数（V4: 1.0=卖Strike, 1.5=向内移50%翼宽, 2.0=接近买Strike）
                 stop_loss_confirm_days: int = 0,  # 止损确认天数（0=立即止损，1=连续N天才止损）
                 dynamic_slippage: bool = True,    # 是否启用动态滑点模型
                 iv_filter_mode: str = "fixed",    # IV过滤模式："fixed"固定阈值 | "percentile"分位数
                 iv_percentile_low: float = 25,    # 分位数模式下最低IV百分位
                 iv_percentile_high: float = 75,   # 分位数模式下最高IV百分位
                 kelly_fraction: float = 0.0,      # 凯利公式比例（0=不使用凯利，>0用半凯利的该比例）
                 cooldown_days: int = 5,            # V5: 止损后冷却期天数（与实盘对齐）
                 ):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.wing_width = wing_width
        self.otm_distance = otm_distance
        self.dte = dte
        
        # 优化参数
        self.min_iv = min_iv
        self.early_close_days = early_close_days
        self.max_loss_pct = max_loss_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_groups = max_groups
        
        # 入场模式
        self.entry_mode = entry_mode
        self.entry_days_before_expiry = entry_days_before_expiry
        self._expiry_calendar: List[date] = []  # 在 run() 时填充
        
        # === V3 新参数初始化 ===
        self.stop_loss_buffer = stop_loss_buffer  # 止损缓冲倍数
        self.stop_loss_confirm_days = stop_loss_confirm_days  # 止损确认天数
        self.dynamic_slippage = dynamic_slippage  # 动态滑点开关
        self.iv_filter_mode = iv_filter_mode  # IV过滤模式
        self.iv_percentile_low = iv_percentile_low
        self.iv_percentile_high = iv_percentile_high
        self.kelly_fraction = kelly_fraction  # 凯利比例
        self.cooldown_days = cooldown_days  # V5: 止损冷却期天数
        
        # 止损确认追踪（用于时间过滤）
        self._days_in_stop_zone: Dict[int, int] = {}  # position index -> 连续破位天数
        self._last_close_date: Optional[date] = None   # V5: 最后平仓日期（用于冷却期）
        
        # 自动生成标签
        if label:
            self.label = label
        elif entry_mode == "pre_expiry":
            self.label = f"Iron Condor {otm_distance:.0%}±{wing_width:.0%} 到期前{entry_days_before_expiry}天入场"
        else:
            self.label = f"Iron Condor {otm_distance:.0%}±{wing_width:.0%} DTE={dte}"
        
        self.trades: List[Dict] = []
        self.daily_records: List[Dict] = []
        self._last_trade_month: Optional[str] = None
        self._last_opened_expiry: Optional[str] = None
        
        # 持仓列表（支持多组同时开仓）
        self.positions: List[IronCondorPosition] = []
        
        # 统计
        self.peak_value = initial_capital
        self.stopped = False
        self._stop_date = None  # V6: 记录停止日期，用于冷却恢复
    
    @property
    def position(self):
        """兼容旧代码，返回第一个持仓"""
        return self.positions[0] if self.positions else None
    
    @property
    def n_active_positions(self):
        """当前活跃持仓组数"""
        return len(self.positions)
    
    def get_option_price_hkd(self, S: float, K: float, T_days: float,
                              sigma: float, option_type: str) -> float:
        """计算单张期权价格（HKD）"""
        T = T_days / 365.0
        per_share = bs_option_price(S, K, T, sigma, option_type=option_type)
        per_share *= (1 - self.SLIPPAGE_PCT)
        return per_share * self.LOT_SIZE
    
    def calculate_ic_prices(self, S: float, sigma: float) -> Tuple[float, float, float, float, float]:
        """
        计算 Iron Condor 的4条腿价格（卖方价差，收取净权利金）
        
        正确的卖方价差结构：
        - 卖出更接近价内的期权（更高权利金）
        - 买入更虚值的期权（更低权利金）
        - 收到净权利金
        """
        # ETF 使用更宽的 wing
        wing = self.wing_width
        if S < 20:  # 低价ETF
            wing = max(wing, 0.10)  # 至少10%
        
        # PUT 边：卖出更接近价内的PUT，买入更虚值PUT（卖方价差）
        # V5修复（与实盘对齐）: 确保wing>otm时sell_put_k始终是OTM（低于现价）
        # 实盘验证公式: sell_put @ -otm%, buy_put @ -(otm+wing)%
        sell_put_k = S * (1 - self.otm_distance)           # OTM（低于现价）
        buy_put_k = S * (1 - self.otm_distance - wing)     # 更虚值（更低）
        
        # CALL 边：卖出更虚值CALL，买入更虚值CALL（卖方价差）
        # V5修复（与实盘对齐）: 确保wing>otm时sell_call_k始终是OTM
        # 实盘验证公式: sell_call @ +otm%, buy_call @ +(otm+wing)%
        sell_call_k = S * (1 + self.otm_distance)           # OTM（高于现价）
        buy_call_k = S * (1 + self.otm_distance + wing)    # 更虚值（更高）
        
        # 4条腿的价格
        sell_put_price = self.get_option_price_hkd(S, sell_put_k, self.dte, sigma, "PUT")
        buy_put_price = self.get_option_price_hkd(S, buy_put_k, self.dte, sigma, "PUT")
        sell_call_price = self.get_option_price_hkd(S, sell_call_k, self.dte, sigma, "CALL")
        buy_call_price = self.get_option_price_hkd(S, buy_call_k, self.dte, sigma, "CALL")
        
        # 净权利金（卖出的 - 买入的）
        net_credit = (sell_put_price + sell_call_price) - (buy_put_price + buy_call_price)
        
        return sell_put_k, buy_put_k, sell_call_k, buy_call_k, net_credit
    
    def calculate_ic_prices_with_dte(self, S: float, sigma: float, dte: int) -> Tuple[float, float, float, float, float]:
        """与 calculate_ic_prices 相同，但使用传入的 dte（用于 pre_expiry 模式）"""
        wing = self.wing_width
        if S < 20:
            wing = max(wing, 0.10)
        
        # V5修复（与实盘对齐）: PUT边公式同 calculate_ic_prices
        sell_put_k = S * (1 - self.otm_distance)           # OTM（低于现价）
        buy_put_k = S * (1 - self.otm_distance - wing)     # 更虚值（更低）
        sell_call_k = S * (1 + self.otm_distance)           # OTM（高于现价）
        buy_call_k = S * (1 + self.otm_distance + wing)    # 更虚值（更高）
        
        # 使用传入的 dte 计算价格
        T_days = max(dte, 1)
        sell_put_price  = self.get_option_price_hkd(S, sell_put_k,  T_days, sigma, "PUT")
        buy_put_price   = self.get_option_price_hkd(S, buy_put_k,   T_days, sigma, "PUT")
        sell_call_price = self.get_option_price_hkd(S, sell_call_k, T_days, sigma, "CALL")
        buy_call_price  = self.get_option_price_hkd(S, buy_call_k,  T_days, sigma, "CALL")
        
        net_credit = (sell_put_price + sell_call_price) - (buy_put_price + buy_call_price)
        return sell_put_k, buy_put_k, sell_call_k, buy_call_k, net_credit
    
    def calculate_max_loss(self, S: float) -> float:
        """计算单组最大亏损"""
        # PUT 边最大亏损：K_sell - K_buy
        put_risk = (self.position.sell_put_k - self.position.buy_put_k) * self.LOT_SIZE
        # CALL 边最大亏损：K_buy - K_sell  
        call_risk = (self.position.buy_call_k - self.position.sell_call_k) * self.LOT_SIZE
        return max(put_risk, call_risk)
    
    def _estimate_position_value(self, pos: 'IronCondorPosition', S: float, sigma: float, 
                                  current_date=None) -> float:
        """
        估算Iron Condor持仓的当前市场价值（含浮盈/亏）
        
        修复前：total_value只算cash，导致回撤永远是0%
        修复后：加入持仓市值，真实反映浮盈/亏
        """
        # 计算剩余到期天数
        if current_date:
            days_left = max((pos.expiration - current_date).days, 1)
        else:
            days_left = max(self.dte // 2, 1)  # fallback: 假设过了一半时间
        T = max(days_left / 365.0, 0.003)
        if T < 0.001:
            T = 0.003
        
        # 计算四条腿的当前价格（注意：bs_option_price的第5个参数是r，option_type在第6位）
        sell_put_now = bs_option_price(S, pos.sell_put_k, T, sigma, option_type="PUT") * self.LOT_SIZE
        buy_put_now = bs_option_price(S, pos.buy_put_k, T, sigma, option_type="PUT") * self.LOT_SIZE
        sell_call_now = bs_option_price(S, pos.sell_call_k, T, sigma, option_type="CALL") * self.LOT_SIZE
        buy_call_now = bs_option_price(S, pos.buy_call_k, T, sigma, option_type="CALL") * self.LOT_SIZE
        
        # Iron Condor当前价值 = 收到的权利金 - 当前平仓成本
        # 卖出的期权需要花更多钱买回（如果价格不利），买入的期权有剩余价值
        current_mv = pos.net_credit \
                    - (sell_put_now - buy_put_now) \
                    - (sell_call_now - buy_call_now)
        
        return current_mv
    
    def _get_dynamic_slippage(self, pos: 'IronCondorPosition', S: float) -> float:
        """
        V3动态滑点模型：根据期权虚实值程度调整滑点
        
        实盘逻辑：
        - 平值期权（ATM）流动性最好 → 滑点10%
        - 虚值5%期权（OTM 5%）流动性中等 → 滑点20%
        - 虚值10%期权（OTM 10%）流动性差 → 滑点50%
        - 止损时市场恐慌，所有期权滑点额外加成
        """
        if not self.dynamic_slippage:
            return self.SLIPPAGE_PCT
        
        # 计算卖PUT端的虚值程度（取两边更危险的一侧）
        if S <= pos.sell_put_k:
            # PUT端被突破，看PUT腿的虚值程度
            otm_pct = (pos.sell_put_k - S) / S
        elif S >= pos.sell_call_k:
            # CALL端被突破，看CALL腿的虚值程度  
            otm_pct = (S - pos.sell_call_k) / S
        else:
            # 未破位，正常情况
            otm_pct = min(
                abs(S - pos.sell_put_k) / S,
                abs(pos.sell_call_k - S) / S
            )
        
        # 根据虚值程度确定基础滑点
        if otm_pct <= 0.02:      # 接近平值或价内
            base_slippage = 0.10   # 10%
        elif otm_pct <= 0.05:     # 浅虚值（<5%）
            base_slippage = 0.20   # 20%
        elif otm_pct <= 0.10:     # 中虚值（5-10%）
            base_slippage = 0.35   # 35%
        else:                     # 深虚值（>10%）
            base_slippage = 0.50   # 50%
        
        return base_slippage
    
    def _calculate_stop_loss(self, pos: 'IronCondorPosition', S: float, sigma: float) -> float:
        """
        计算破位止损时的实际亏损（包含V3动态滑点惩罚）
        
        修复前：提前平仓永远按 net_credit * 0.85 计算，即使破位了也是正收入
        V2修复：根据实际破位程度计算亏损，加入固定滑点惩罚
        V3增强：动态滑点——深虚值期权在行情突变时滑点更大
        """
        # 计算破位程度
        if S <= pos.sell_put_k:
            # PUT端被突破，亏损 = 翼宽 * 合约单位 + 滑点惩罚
            intrinsic_loss = (pos.sell_put_k - S) * self.LOT_SIZE
            wing_loss = (pos.sell_put_k - pos.buy_put_k) * self.LOT_SIZE
            loss = min(intrinsic_loss, wing_loss)  # 最大不超过翼宽
        else:
            # CALL端被突破
            intrinsic_loss = (S - pos.sell_call_k) * self.LOT_SIZE
            wing_loss = (pos.buy_call_k - pos.sell_call_k) * self.LOT_SIZE
            loss = min(intrinsic_loss, wing_loss)
        
        # V3：使用动态滑点替代固定滑点
        dyn_slippage = self._get_dynamic_slippage(pos, S)
        slippage_penalty = loss * dyn_slippage
        
        # 最终PnL = 权利金收入 - 亏损 - 滑点
        pnl = pos.net_credit - loss - slippage_penalty
        return pnl
    
    def _time_value_ratio(self, days_to_expire: int) -> float:
        """
        计算正常提前平仓时的时间价值比例
        
        修复前：固定85%，不合理
        修复后：基于剩余时间动态计算——剩余时间越多，保留的权利金比例越低
        （因为买方还要支付剩余时间价值才能平掉我们的仓位）
        """
        if days_to_expire <= 1:
            return 0.95  # 到期前一天，几乎全收
        elif days_to_expire <= self.early_close_days + 2:
            return 0.90  # 剩2-3天
        elif days_to_expire <= 5:
            return 0.80  # 剩4-5天
        elif days_to_expire <= 10:
            return 0.65  # 剩一周左右
        else:
            # 更早平仓，剩余时间价值更高（我们收回的比例更低）
            return max(0.50, 0.90 - days_to_expire * 0.03)
    
    def _calc_kelly_groups(self, net_credit: float, max_loss: float) -> int:
        """
        V3：凯利公式计算最优开仓组数
        
        Kelly公式：f* = (p*b - (1-p)) / b
        - p = 胜率（基于历史数据估算，铁鹰策略约60-80%持有到期率）
        - b = 盈亏比（平均盈利 / 平均亏损）
        
        实盘用半凯利避免过度自信：
        - kelly_fraction=0 → 不使用凯利，回退到 max_groups
        - kelly_fraction=0.5 → 使用半凯利
        - kelly_fraction=1.0 → 全凯利（不推荐）
        """
        if self.kelly_fraction <= 0:
            return self.max_groups
        
        # 基于当前策略参数估算胜率和盈亏比
        # 铁鹰策略的"胜率"≈ 持有到期不破位的概率
        # 用正态分布估算：假设价格服从对数正态分布，落在OTM区间的概率
        # 简化模型：wing越宽胜率越高，OTM越宽胜率越高
        estimated_win_rate = 0.65 + min(self.wing_width * 2, 0.20)  # 基础65% + wing加成
        
        # 盈亏比 = 平均权利金收入 / 最大潜在亏损
        profit_loss_ratio = net_credit / max(max_loss, 1)
        
        # 凯利公式
        kelly_f = (estimated_win_rate * profit_loss_ratio - (1 - estimated_win_rate)) / max(profit_loss_ratio, 0.01)
        
        # 限制凯利比例在合理范围 [0, 0.5]
        kelly_f = max(0, min(kelly_f, 0.5))
        
        # 应用用户指定的凯利比例（半凯利等）
        adjusted_kelly = kelly_f * self.kelly_fraction
        
        # 计算可用资金能开的组数
        available_capital = self.cash + self.initial_capital * 0.5
        margin_per_group = max_loss * 0.5
        max_by_capital = int(available_capital / max(margin_per_group, 1))
        
        # 取凯利建议、资金上限、配置上限的最小值
        kelly_groups = max(1, int(adjusted_kelly * available_capital / max(margin_per_group, 1)))
        result = min(kelly_groups, max_by_capital, self.max_groups)
        
        return max(result, 1)  # 至少开1组
    
    def run(self, df: pd.DataFrame, save_prefix: str = "ic"):
        print("\n📊 开始 Iron Condor 回测（V4修复版）...")
        prices = df["Close"]
        
        # pre_expiry 模式：预先生成到期日历
        start_d = df["date"].iloc[0]
        end_d = df["date"].iloc[-1]
        # 转换为date对象（处理Timestamp或date类型）
        if hasattr(start_d, 'date'):
            start_d = start_d.date()
        if hasattr(end_d, 'date'):
            end_d = end_d.date()
        self._expiry_calendar = get_hk_option_expiries(start_d, end_d + timedelta(days=60))
        
        # === V3：分位数波动率预计算 ===
        self._iv_percentile_low_val = 0.0
        self._iv_percentile_high_val = 1.0
        if self.iv_filter_mode == "percentile":
            # 预计算全序列的20日波动率，取分位数作为过滤阈值
            all_sigmas = []
            for i in range(20, len(prices)):
                past_p = prices.iloc[i - 20: i + 1]
                sig = historical_volatility(past_p, 20)
                all_sigmas.append(sig)
            if all_sigmas:
                self._iv_percentile_low_val = float(np.percentile(all_sigmas, self.iv_percentile_low))
                self._iv_percentile_high_val = float(np.percentile(all_sigmas, self.iv_percentile_high))
                print(f"  📊 IV分位数过滤: 低阈值={self._iv_percentile_low_val:.2%} ({self.iv_percentile_low}th), "
                      f"高阈值={self._iv_percentile_high_val:.2%} ({self.iv_percentile_high}th)")
        
        for i, row in df.iterrows():
            current_date: date = row["date"]
            S: float = float(row["Close"])
            
            # 计算历史波动率
            past_prices = prices.iloc[max(0, i - 20): i + 1]
            sigma = historical_volatility(past_prices, 20)
            
            # V3：IV分位数过滤（替代固定阈值模式）
            iv_pass = True
            if self.iv_filter_mode == "percentile":
                iv_pass = (self._iv_percentile_low_val <= sigma <= self._iv_percentile_high_val)
            
            # ── 空仓 → 开仓 ─────────────────────
            # V6: 冷却恢复机制 - 暂停超过cooldown_days后自动恢复
            if self.stopped and self._stop_date:
                days_since_stop = (current_date - self._stop_date).days
                if days_since_stop >= self.cooldown_days:
                    print(f"  ✅ [{current_date}] 冷却期结束（已过{days_since_stop}天），恢复交易")
                    self.stopped = False
                    self._stop_date = None
            
            if len(self.positions) == 0 and not self.stopped:
                
                if self.entry_mode == "pre_expiry":
                    # ── pre_expiry 模式：找下一个到期日，判断今天是否是入场窗口 ──
                    next_exp = get_next_expiry(current_date, self._expiry_calendar)
                    if next_exp is None:
                        pass
                    else:
                        days_to_exp = (next_exp - current_date).days
                        # 入场窗口：距到期恰好 entry_days_before_expiry 天（±1天容错）
                        should_enter = (days_to_exp <= self.entry_days_before_expiry and
                                        days_to_exp > self.early_close_days)
                        
                        if should_enter:
                            # 避免同一到期日重复开仓
                            cur_exp_str = str(next_exp)
                            if not hasattr(self, '_last_opened_expiry'):
                                self._last_opened_expiry = None
                            
                            if self._last_opened_expiry != cur_exp_str:
                                actual_dte = days_to_exp  # 实际剩余天数
                                sp_k, bp_k, sc_k, bc_k, credit = self.calculate_ic_prices_with_dte(S, sigma, actual_dte)
                                net_credit = credit - self.COMMISSION * 4
                                
                                min_credit = max(30, S * 0.001) if iv_pass else 0
                                
                                if (iv_pass and net_credit >= min_credit and
                                        sp_k > 0 and bp_k > 0 and sc_k > 0 and bc_k > 0):
                                    max_loss = (sp_k - bp_k) * self.LOT_SIZE
                                    loss_pct = max_loss / (self.cash + self.initial_capital)
                                    
                                    # V3：凯利公式动态调整max_groups
                                    actual_groups = self._calc_kelly_groups(net_credit, max_loss)
                                    
                                    if loss_pct <= self.max_loss_pct:
                                        required_margin = max_loss * 0.5 * actual_groups
                                        if self.cash + self.initial_capital * 0.5 >= required_margin:
                                            self._last_opened_expiry = cur_exp_str
                                            self._last_open_date = current_date  # V4: 精确日期防重复
                                            
                                            for g in range(actual_groups):
                                                self.cash += net_credit
                                                self.positions.append(IronCondorPosition(
                                                    sell_put_k=sp_k,
                                                    buy_put_k=bp_k,
                                                    sell_call_k=sc_k,
                                                    buy_call_k=bc_k,
                                                    net_credit=net_credit,
                                                    open_date=current_date,
                                                    expiration=next_exp,
                                                ))
                                                # V4修复: 每个独立仓位都记录一次OPEN
                                                self.trades.append({
                                                    "date": str(current_date),
                                                    "action": "OPEN_IC",
                                                    "price": S,
                                                    "sigma": round(sigma, 3),
                                                    "sell_put": sp_k,
                                                    "buy_put": bp_k,
                                                    "sell_call": sc_k,
                                                    "buy_call": bc_k,
                                                    "credit": round(net_credit, 0),
                                                    "expiration": str(next_exp),
                                                    "days_to_exp": days_to_exp,
                                                })
                                            
                                            print(f"  🦅 [{current_date}] 到期前{days_to_exp}天入场 → 到期日 {next_exp} ×{actual_groups}组")
                                            print(f"      PUT: 卖 {sp_k:.1f} / 买 {bp_k:.1f}")
                                            print(f"      CALL: 卖 {sc_k:.1f} / 买 {bc_k:.1f}")
                                            print(f"      净权利金: HKD {net_credit:.0f}")
                                            
                                            # V4: OPEN记录已移入循环内，每组独立记录
                
                else:
                    # ── dte 模式（每月度周期开仓） ──
                    # V4修复: 用精确日期而非月份来防止重复开仓
                    cur_month = current_date.strftime("%Y-%m")
                    
                    # 防重复: 同一月份只开一次 OR 距上次开仓不足DTE的60%不开
                    # V5新增：冷却期检查 — 止损平仓后至少等 cooldown_days 天才能重新开仓
                    can_open = False
                    if self._last_trade_month != cur_month:
                        can_open = True
                    elif hasattr(self, '_last_open_date') and self._last_open_date:
                        days_since_last = (current_date - self._last_open_date).days
                        if days_since_last >= max(self.dte // 2, 7):  # 至少过半DTE或7天才允许重开
                            can_open = True
                    
                    # V5: 冷却期检查（止损后冷却，避免频繁交易吃手续费）
                    if can_open and self.cooldown_days > 0 and self._last_close_date:
                        days_since_close = (current_date - self._last_close_date).days
                        if days_since_close < self.cooldown_days:
                            can_open = False
                    
                    if can_open:
                        # 计算开仓价格
                        sp_k, bp_k, sc_k, bc_k, credit = self.calculate_ic_prices(S, sigma)
                        net_credit = credit - self.COMMISSION * 4  # 4条腿的佣金
                        
                        # V3/V4：IV过滤（支持分位数模式）
                        if not iv_pass:
                            min_credit = 999999  # 不开仓
                        else:
                            min_credit = max(30, S * 0.001)  # 至少0.1%股价
                    
                    if iv_pass and net_credit >= min_credit and sp_k > 0 and bp_k > 0 and sc_k > 0 and bc_k > 0:
                            # 计算单笔最大亏损
                            max_loss = (sp_k - bp_k) * self.LOT_SIZE
                            loss_pct = max_loss / (self.cash + self.initial_capital)
                            
                            # V3：凯利公式动态调整max_groups
                            actual_groups = self._calc_kelly_groups(net_credit, max_loss)
                            
                            # 单笔亏损限制
                            if loss_pct <= self.max_loss_pct:
                                # 检查保证金是否足够
                                required_margin = max_loss * 0.5 * actual_groups
                                
                                if self.cash + self.initial_capital * 0.5 >= required_margin:
                                    self._last_trade_month = cur_month
                                    self._last_open_date = current_date  # V4: 精确日期防重复
                                    
                                    # 根据凯利公式调整后的组数开仓
                                    for g in range(actual_groups):
                                        self.cash += net_credit
                                        exp_date = current_date + timedelta(days=self.dte)
                                        
                                        self.positions.append(IronCondorPosition(
                                            sell_put_k=sp_k,
                                            buy_put_k=bp_k,
                                            sell_call_k=sc_k,
                                            buy_call_k=bc_k,
                                            net_credit=net_credit,
                                            open_date=current_date,
                                            expiration=exp_date,
                                        ))
                                        # V4修复: 每个独立仓位都记录一次OPEN
                                        self.trades.append({
                                            "date": str(current_date),
                                            "action": "OPEN_IC",
                                            "price": S,
                                            "sigma": round(sigma, 3),
                                            "sell_put": sp_k,
                                            "buy_put": bp_k,
                                            "sell_call": sc_k,
                                            "buy_call": bc_k,
                                            "credit": round(net_credit, 0),
                                            "expiration": str(exp_date)
                                        })
                                
                                print(f"  🦅 [{current_date}] Iron Condor 开仓 ×{actual_groups}组")
                                print(f"      PUT: 卖 {sp_k:.1f} / 买 {bp_k:.1f}")
                                print(f"      CALL: 卖 {sc_k:.1f} / 买 {bc_k:.1f}")
                                print(f"      净权利金: HKD {net_credit:.0f}")
            
            # ── 持仓 → 到期判断 ─────────────────
            if self.positions:
                # 遍历所有持仓，检查是否需要平仓
                remaining_positions = []
                for pos in self.positions:
                    # 计算总资产 = 现金 + 持仓浮动价值（修复：必须包含浮盈/亏）
                    position_mv = self._estimate_position_value(pos, S, sigma, current_date)
                    total_value = self.cash + position_mv
                    
                    # 更新峰值
                    if total_value > self.peak_value:
                        self.peak_value = total_value
                    
                    # 检查总回撤止损（V6修复: 改为临时冷却而非永久停止）
                    current_dd = (total_value - self.peak_value) / self.peak_value
                    if current_dd <= -self.stop_loss_pct and not self.stopped:
                        print(f"  🛑 [{current_date}] 触发总回撤止损 {current_dd*100:.1f}%，暂停交易{self.cooldown_days}天")
                        self.stopped = True
                        self._stop_date = current_date  # 记录停止日期
                        # 平仓离场
                        self.cash += pos.net_credit
                        self.trades.append({
                            "date": str(current_date),
                            "action": "STOP_LOSS",
                            "result": f"总回撤{int(self.stop_loss_pct*100)}%_暂停{self.cooldown_days}天",
                            "pnl": round(pos.net_credit, 0),
                        })
                        continue
                    
                    # 提前平仓：到期前N天 或 股价突破OTM区间（止损）
                    days_to_expire = (pos.expiration - current_date).days
                    
                    # === V4修复：合理的止损逻辑 ===
                    # 之前V3的bug: 用"盈亏平衡点"做止损线，距离现价仅1.5-2%，
                    #   导致97.6%的交易都触发止损，胜率仅2.4%
                    # V4修复: 止损线设在卖方行权价的外侧（买方行权价方向）
                    #   - PUT端: 跌破卖PUT行权价 → 开始亏损（但还没到最大亏损）
                    #   - 真正危险的是跌破买PUT行权价（翼宽全部亏完）
                    #   - 合理止损: 突破卖方行权价一定幅度后止损（给正常波动留空间）
                    
                    # 卖方行权价（OTM边界）
                    sell_put_k = pos.sell_put_k
                    sell_call_k = pos.sell_call_k
                    # 买方行权价（最大亏损边界）
                    buy_put_k = pos.buy_put_k
                    buy_call_k = pos.buy_call_k
                    
                    # V4: 止损线 = 卖方向外推一定比例（默认在卖Strike外侧）
                    # put_wing_width 和 call_wing_width 是翼宽（绝对值）
                    put_wing_width = sell_put_k - buy_put_k
                    call_wing_width = buy_call_k - sell_call_k
                    
                    # 止损触发条件:
                    # 方案A: 跌破卖PUT行权价（进入亏损区域）
                    # 方案B: 跌破卖PUT - 翼宽*buffer%（接近买PUT时才止损）
                    if self.stop_loss_buffer >= 1.0:
                        # buffer>=1: 止损线从卖Strike向内移（越保守越靠近买Strike）
                        stop_put = sell_put_k - put_wing_width * min(self.stop_loss_buffer - 1.0, 0.8)
                        stop_call = sell_call_k + call_wing_width * min(self.stop_loss_buffer - 1.0, 0.8)
                    else:
                        # buffer<1: 直接用卖Strike作为止损线
                        stop_put = sell_put_k
                        stop_call = sell_call_k
                    
                    # 止损条件：股价突破止损线，或距到期不足N天
                    should_close_early = False
                    close_reason = "到期前平仓"
                    
                    if S <= stop_put:
                        # 跌破PUT端缓冲止损线 → 检查时间过滤
                        if self.stop_loss_confirm_days > 0:
                            # 需要连续N天确认才止损
                            pos_id = id(pos)
                            self._days_in_stop_zone[pos_id] = self._days_in_stop_zone.get(pos_id, 0) + 1
                            if self._days_in_stop_zone[pos_id] >= self.stop_loss_confirm_days:
                                should_close_early = True
                                close_reason = f"跌破PUT止损线(连续{self.stop_loss_confirm_days}天确认)"
                            else:
                                close_reason = f"跌破PUT区域(第{self._days_in_stop_zone[pos_id]}天,需{self.stop_loss_confirm_days}天确认)"
                        else:
                            should_close_early = True
                            close_reason = "跌破PUT止损线"
                    elif S >= stop_call:
                        # 涨破CALL端缓冲止损线 → 检查时间过滤
                        if self.stop_loss_confirm_days > 0:
                            pos_id = id(pos)
                            self._days_in_stop_zone[pos_id] = self._days_in_stop_zone.get(pos_id, 0) + 1
                            if self._days_in_stop_zone[pos_id] >= self.stop_loss_confirm_days:
                                should_close_early = True
                                close_reason = f"涨破CALL止损线(连续{self.stop_loss_confirm_days}天确认)"
                            else:
                                close_reason = f"涨破CALL区域(第{self._days_in_stop_zone[pos_id]}天,需{self.stop_loss_confirm_days}天确认)"
                        else:
                            should_close_early = True
                            close_reason = "涨破CALL止损线"
                    else:
                        # 价格在正常范围内，重置确认计数器
                        pos_id = id(pos)
                        if pos_id in self._days_in_stop_zone:
                            del self._days_in_stop_zone[pos_id]
                        
                        if days_to_expire <= self.early_close_days:
                            # 到期前N天正常平仓
                            should_close_early = True
                            close_reason = f"到期前{self.early_close_days}天"
                    
                    if should_close_early:
                        # V5: 记录最后平仓日期（用于冷却期）
                        self._last_close_date = current_date
                        
                        if S <= stop_put or S >= stop_call:
                            # 破位止损：按最大亏损的一定比例计算亏损
                            # 加入滑点惩罚：实际亏损比理论更大
                            loss_amount = self._calculate_stop_loss(pos, S, sigma)
                            self.cash += loss_amount
                            self.trades.append({
                                "date": str(current_date),
                                "action": "EARLY_CLOSE",
                                "price": S,
                                "pnl": round(loss_amount, 0),
                                "result": close_reason,
                            })
                            print(f"  ⚠️  [{current_date}] {close_reason} PnL=HKD{loss_amount:.0f} (S={S:.1f})")
                        else:
                            # 正常提前平仓，收取剩余时间价值（修复：不再固定85%）
                            early_credit = pos.net_credit * self._time_value_ratio(days_to_expire)
                            self.cash += early_credit
                            self.trades.append({
                                "date": str(current_date),
                                "action": "EARLY_CLOSE",
                                "price": S,
                                "pnl": round(early_credit, 0),
                                "result": close_reason,
                            })
                            print(f"  📅 [{current_date}] {close_reason} PnL=HKD{early_credit:.0f}")
                        continue
                    
                    # 检查是否到期
                    if current_date >= pos.expiration:
                        # V5: 记录最后平仓日期（用于冷却期）
                        self._last_close_date = current_date
                        # 到期结算
                        if pos.buy_put_k < S < pos.sell_call_k:
                            # 价格落在盈利区间，全部归零
                            pnl = pos.net_credit
                            result = "盈利"
                        elif S <= pos.buy_put_k:
                            # 跌破 PUT 边，被行权
                            loss = (pos.sell_put_k - pos.buy_put_k) * self.LOT_SIZE - pos.net_credit
                            pnl = -loss
                            result = "PUT被行权"
                        elif S >= pos.sell_call_k:
                            # 突破 CALL 边，被行权
                            loss = (pos.buy_call_k - pos.sell_call_k) * self.LOT_SIZE - pos.net_credit
                            pnl = -loss
                            result = "CALL被行权"
                        else:
                            pnl = pos.net_credit  # 理论上不会到这里
                            result = "盈利"
                        
                        self.cash += pnl
                        self.trades.append({
                            "date": str(current_date),
                            "action": "IC_EXPIRED",
                            "price": S,
                            "result": result,
                            "pnl": round(pnl, 0),
                        })
                        print(f"  📅 [{current_date}] Iron Condor 到期: {result} PnL=HKD{pnl:.0f}")
                        continue
                    
                    # 未平仓，继续持有
                    remaining_positions.append(pos)
                
                # 更新持仓列表
                self.positions = remaining_positions
            
            # ── 日志记录 ───────────────────────
            # 修复V4: total_value 必须包含持仓浮动价值，否则回撤和夏普比率都是错的
            position_total_mv = 0.0
            if self.positions:
                for pos in self.positions:
                    position_total_mv += self._estimate_position_value(pos, S, sigma, current_date)
            total_value = self.cash + position_total_mv
            ret_pct = (total_value - self.initial_capital) / self.initial_capital * 100
            
            self.daily_records.append({
                "date": current_date,
                "price": S,
                "sigma": round(sigma, 4),
                "cash": round(self.cash, 0),
                "total_value": round(total_value, 0),
                "return_pct": round(ret_pct, 4),
                "position": "持有" if self.position else "空仓",
            })
    
    def print_report(self, save_prefix: str = "ic") -> dict:
        df = pd.DataFrame(self.daily_records)
        tf = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()
        
        final_value = df["total_value"].iloc[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        total_pnl = final_value - self.initial_capital
        
        start_dt = df["date"].iloc[0]
        end_dt = df["date"].iloc[-1]
        years = (end_dt - start_dt).days / 365.0
        
        ann_return = ((1 + total_return / 100) ** (1 / max(years, 0.1)) - 1) * 100
        
        df["peak"] = df["total_value"].cummax()
        df["drawdown"] = (df["total_value"] - df["peak"]) / df["peak"] * 100
        max_dd = df["drawdown"].min()
        max_dd_date = df.loc[df["drawdown"].idxmin(), "date"]
        
        # 交易统计
        n_open = n_expired = n_loss = n_early_close = 0
        avg_credit = 0.0
        if not tf.empty:
            n_open = len(tf[tf.action == "OPEN_IC"])
            n_expired = len(tf[tf.action == "IC_EXPIRED"])
            n_early_close = len(tf[tf.action == "EARLY_CLOSE"])
            
            credits = tf[tf.action == "OPEN_IC"]["credit"]
            if len(credits) > 0:
                avg_credit = credits.mean()
            
            # 统计亏损次数（IC_EXPIRED 中 pnl < 0）
            losses = tf[tf.action == "IC_EXPIRED"]
            if not losses.empty:
                n_loss = (losses["pnl"] < 0).sum()
        
        # 胜率：盈利笔数 / 总平仓笔数（修复：分母必须用平仓次数，不能用开仓次数）
        n_closed = n_expired + n_early_close
        # 盈利的平仓 = 到期盈利 + 提前平仓中pnl>0的
        profitable_closes = n_expired - n_loss  # 到期结算中的盈利笔数
        # 提前平仓的盈利笔数
        early_trades = tf[tf.action == "EARLY_CLOSE"]
        if not early_trades.empty:
            n_early_win = (early_trades["pnl"] > 0).sum()
            profitable_closes += int(n_early_win)
        
        if n_closed > 0:
            win_rate = (profitable_closes / n_closed) * 100  # 修复后：最大100%
        elif n_open > 0:
            win_rate = 100.0  # 还没平仓，暂时算全胜（保守）
        else:
            win_rate = 0.0
        
        # === V5: 夏普比率计算（修复V4全部为0的Bug） ===
        sharpe_ratio = 0.0
        if len(df) > 10 and years > 0.1:
            df["daily_return"] = df["total_value"].pct_change()  # 日收益率
            daily_returns = df["daily_return"].dropna()
            if len(daily_returns) > 5 and daily_returns.std() > 1e-10:
                # 年化收益率 / (日收益率标准差 * √252)
                # 无风险利率用2.5%（香港1年期国债近似值）
                rf_daily = 0.025 / 252
                excess_return = daily_returns - rf_daily
                sharpe_ratio = round(excess_return.mean() / excess_return.std() * math.sqrt(252), 2)
        
        print(f"\n{'='*64}")
        print(f"  🦅  [{self.label}]  Iron Condor 策略回测报告")
        print(f"{'='*64}")
        print(f"""
  初始资金   HKD {self.initial_capital:>10,.0f}   →   最终 HKD {final_value:>10,.0f}
  总收益率   {total_return:+.2f}%   年化 {ann_return:+.2f}%   共 {years:.1f} 年
  总盈亏     HKD {total_pnl:>+10,.0f}
  最大回撤   {max_dd:.2f}%  ({max_dd_date})
  夏普比率   {sharpe_ratio:.2f}
  开仓次数   {n_open} 次（均值权利金 {avg_credit:.0f} HKD）
  到期结算   {n_expired} 次  /  提前平仓 {n_early_close} 次
  亏损次数   {n_loss} 次
  胜率       {win_rate:.0f}%（基于全部平仓笔数 {n_closed}）
        """)
        
        # 保存 CSV
        out = Path(__file__).parent / "backtest_results"
        out.mkdir(exist_ok=True)
        df.to_csv(out / f"{save_prefix}_daily.csv", index=False)
        if not tf.empty:
            tf.to_csv(out / f"{save_prefix}_trades.csv", index=False)
        
        return {
            "label": self.label,
            "wing_width": self.wing_width,
            "otm_distance": self.otm_distance,
            "dte": self.dte,
            "final_value": round(final_value, 0),
            "total_return": round(total_return, 2),
            "ann_return": round(ann_return, 2),
            "total_pnl": round(total_pnl, 0),
            "max_dd": round(max_dd, 2),
            "max_dd_date": str(max_dd_date),
            "sharpe_ratio": sharpe_ratio,   # V5: 新增夏普比率（修复V4全部为0的Bug）
            "n_open": n_open,
            "n_expired": n_expired,
            "n_early_close": n_early_close,
            "n_closed": n_closed,
            "n_loss": n_loss,
            "avg_credit": round(avg_credit, 0),
            "win_rate": round(win_rate, 1),
            "years": round(years, 1),
            "daily_df": df,
            "trades_df": tf,
        }


def main():
    parser = argparse.ArgumentParser(description="Iron Condor 策略回测")
    parser.add_argument("--capital", type=float, default=100_000, help="初始资金")
    parser.add_argument("--start", default="2020-01-01", help="开始日期")
    parser.add_argument("--end", default="2025-12-31", help="结束日期")
    parser.add_argument("--ticker", default="HK.00700", help="标的代码")
    parser.add_argument("--otm", type=float, default=0.05, help="OTM距离 (如 0.05=5%%)")
    parser.add_argument("--wing", type=float, default=0.05, help="价差宽度 (如 0.05=5%%)")
    parser.add_argument("--dte", type=int, default=45, help="到期天数")
    parser.add_argument("--min-iv", type=float, default=0.20, help="最低IV阈值 (默认20%%)")
    parser.add_argument("--early-close", type=int, default=2, help="到期前N天提前平仓")
    parser.add_argument("--max-loss", type=float, default=0.02, help="单笔最大亏损比例")
    parser.add_argument("--stop-loss", type=float, default=0.05, help="总回撤止损比例")
    parser.add_argument("--groups", type=int, default=1, help="最多同时开仓组数")
    parser.add_argument("--compare", action="store_true", help="多组对比")
    parser.add_argument("--tickers", nargs="+", default=None, help="多标的对比")
    parser.add_argument("--entry-mode", default="dte", choices=["dte", "pre_expiry"],
                        help="入场模式：dte=固定天数 | pre_expiry=到期前N天入场")
    parser.add_argument("--entry-days", type=int, default=7,
                        help="pre_expiry 模式：距到期日几天入场（默认7）")
    parser.add_argument("--cooldown", type=int, default=5,
                        help="止损后冷却期天数（默认5，与实盘对齐）")
    args = parser.parse_args()
    
    print("=" * 64)
    print("  🦅  Iron Condor 策略回测（震荡市收租神器）")
    print("=" * 64)
    
    # 多标的对比模式
    if args.tickers:
        _run_multi_tickers(args)
        return
    
    # 单标的模式
    ticker_map = {"HK.00700": "HK.00700"}
    ticker = ticker_map.get(args.ticker, args.ticker)
    
    df = fetch_futu_kline(ticker, args.start, args.end)
    if df is None or df.empty:
        print("\n❌ 无法获取数据")
        sys.exit(1)
    
    if args.compare:
        # 多组对比：DTE固定模式 vs 到期前7天入场模式
        print("\n🔬 对比实验：DTE=25 / DTE=30 / 到期前7天 / 到期前5天\n")
        
        # 固定DTE方案
        dte_configs = [
            dict(otm_distance=0.05, wing_width=0.08, dte=25,
                 label="DTE=25 (5%OTM 8%翼)", entry_mode="dte"),
            dict(otm_distance=0.05, wing_width=0.08, dte=30,
                 label="DTE=30 (5%OTM 8%翼)", entry_mode="dte"),
        ]
        # 到期前N天入场方案
        pre_configs = [
            dict(otm_distance=0.05, wing_width=0.08, dte=30,
                 label="到期前7天入场 (5%OTM 8%翼)",
                 entry_mode="pre_expiry", entry_days_before_expiry=7),
            dict(otm_distance=0.05, wing_width=0.08, dte=30,
                 label="到期前5天入场 (5%OTM 8%翼)",
                 entry_mode="pre_expiry", entry_days_before_expiry=5),
        ]
        all_configs = dte_configs + pre_configs
        
        results = []
        for cfg in all_configs:
            label = cfg["label"]
            print(f"\n{'─'*64}")
            print(f"  ▶  {label}")
            print(f"{'─'*64}")
            bt = IronCondorBacktester(
                initial_capital=args.capital,
                otm_distance=cfg["otm_distance"],
                wing_width=cfg["wing_width"],
                dte=cfg["dte"],
                label=label,
                min_iv=args.min_iv,
                early_close_days=args.early_close,
                max_loss_pct=args.max_loss,
                stop_loss_pct=args.stop_loss,
                max_groups=args.groups,
                entry_mode=cfg.get("entry_mode", "dte"),
                entry_days_before_expiry=cfg.get("entry_days_before_expiry", 7),
                cooldown_days=args.cooldown,   # V5: 冷却期
            )
            bt.run(df)
            safe_label = label.replace(" ", "_").replace("/", "-").replace("(", "").replace(")", "").replace("%", "pct")
            r = bt.print_report(save_prefix=f"ic_{safe_label}")
            results.append(r)
        
        # 生成对比HTML
        _write_comparison_html(results, df)
    else:
        # 单组回测
        bt = IronCondorBacktester(
            initial_capital=args.capital,
            otm_distance=args.otm,
            wing_width=args.wing,
            dte=args.dte,
            min_iv=args.min_iv,
            early_close_days=args.early_close,
            max_loss_pct=args.max_loss,
            stop_loss_pct=args.stop_loss,
            max_groups=args.groups,
            entry_mode=args.entry_mode,
            entry_days_before_expiry=args.entry_days,
            cooldown_days=args.cooldown,   # V5: 冷却期
        )
        bt.run(df)
        bt.print_report()


def _write_comparison_html(results: list, price_df: pd.DataFrame):
    """生成对比 HTML 报告"""
    import json
    from pathlib import Path
    
    colors = ["#6366f1", "#10b981", "#f59e0b", "#ef4444"]
    
    # 构建数据
    series_data = []
    for i, r in enumerate(results):
        ddf = r["daily_df"]
        dates = [str(d) for d in ddf["date"]]
        vals = [round(v, 0) for v in ddf["total_value"]]
        series_data.append({
            "label": r["label"],
            "color": colors[i % len(colors)],
            "dates": dates,
            "values": vals,
        })
    
    # 指标卡片
    cards_html = ""
    for r, color in zip(results, colors):
        cards_html += f"""
      <div class="card" style="border-top: 3px solid {color}">
        <div class="card-label">{r['label']}</div>
        <div class="card-metric" style="color:{color}">{r['ann_return']:+.2f}%</div>
        <div class="card-sub">年化收益</div>
        <div class="card-row"><span>总收益</span><span>{r['total_return']:+.2f}%</span></div>
        <div class="card-row"><span>最大回撤</span><span style="color:#ef4444">{r['max_dd']:.2f}%</span></div>
        <div class="card-row"><span>开仓次数</span><span>{r['n_open']}</span></div>
        <div class="card-row"><span>均次权利金</span><span>HKD {r['avg_credit']:,.0f}</span></div>
        <div class="card-row"><span>胜率</span><span>{r['win_rate']:.0f}%</span></div>
        <div class="card-row"><span>提前平仓</span><span>{r.get('n_early_close', 0)} 次</span></div>
      </div>"""
    
    # 汇总表
    rows = ""
    for r in results:
        rows += f"""<tr>
          <td>{r['label']}</td>
          <td>{r['n_open']}</td>
          <td>HKD {r['avg_credit']:,.0f}</td>
          <td>{r['win_rate']:.0f}%</td>
          <td>{r['ann_return']:+.2f}%</td>
          <td>{r['max_dd']:.2f}%</td>
        </tr>"""
    
    series_json = json.dumps(series_data, ensure_ascii=False)
    price_dates = [str(d) for d in price_df["date"]]
    price_vals = [round(float(v), 1) for v in price_df["Close"]]
    
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Iron Condor 策略对比报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        background:#0f1117;color:#e2e8f0;min-height:100vh}}
  .header{{background:linear-gradient(135deg,#1e1b4b 0%,#1a1a2e 100%);
            padding:40px 24px 32px;text-align:center;
            border-bottom:1px solid rgba(255,255,255,.08)}}
  .header h1{{font-size:2rem;font-weight:700;
              background:linear-gradient(90deg,#818cf8,#34d399);
              -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
  .header p{{color:#94a3b8;margin-top:8px;font-size:.95rem}}
  .container{{max-width:1280px;margin:0 auto;padding:24px}}
  .section-title{{font-size:1.1rem;font-weight:600;color:#818cf8;
                  margin:32px 0 16px;letter-spacing:.05em;text-transform:uppercase}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}
  .card{{background:rgba(255,255,255,.04);border-radius:12px;padding:20px;
          transition:transform .2s;backdrop-filter:blur(8px)}}
  .card:hover{{transform:translateY(-2px)}}
  .card-label{{font-size:.8rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em}}
  .card-metric{{font-size:2.4rem;font-weight:700;margin:8px 0 4px}}
  .card-sub{{font-size:.75rem;color:#64748b;margin-bottom:16px}}
  .card-row{{display:flex;justify-content:space-between;font-size:.85rem;
              padding:4px 0;border-bottom:1px solid rgba(255,255,255,.05)}}
  .card-row span:last-child{{font-weight:600}}
  .chart-box{{background:rgba(255,255,255,.03);border-radius:14px;padding:24px;
              margin-bottom:24px;border:1px solid rgba(255,255,255,.06)}}
  .chart-title{{font-size:1rem;font-weight:600;margin-bottom:16px;color:#cbd5e1}}
  .compare-table{{width:100%;border-collapse:collapse;font-size:.9rem}}
  .compare-table th{{background:rgba(99,102,241,.2);padding:10px 14px;
                      text-align:left;font-weight:600;color:#818cf8}}
  .compare-table td{{padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.06)}}
  .compare-table tr:hover td{{background:rgba(255,255,255,.03)}}
</style>
</head>
<body>
<div class="header">
  <h1>Iron Condor 策略对比报告</h1>
  <p>震荡市收租神器 · 牛熊通吃 · 纯现金操作</p>
</div>

<div class="container">
  <div class="section-title">📊 各方案指标对比</div>
  <div class="cards">{cards_html}</div>

  <div class="section-title">📈 资金曲线对比</div>
  <div class="chart-box">
    <div class="chart-title">组合总资产 (HKD)</div>
    <canvas id="equityChart" height="300"></canvas>
  </div>

  <div class="section-title">🔢 关键指标汇总</div>
  <div class="chart-box">
    <table class="compare-table">
      <thead><tr>
        <th>方案</th><th>开仓次数</th><th>均次权利金</th>
        <th>胜率</th><th>年化收益</th><th>最大回撤</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>

<script>
const seriesData = {series_json};
const priceDates = {json.dumps(price_dates)};
const priceVals  = {json.dumps(price_vals)};

const eqCtx = document.getElementById('equityChart').getContext('2d');
new Chart(eqCtx, {{
  type: 'line',
  data: {{
    labels: seriesData[0].dates,
    datasets: seriesData.map(s => ({{
      label: s.label,
      data: s.values,
      borderColor: s.color,
      backgroundColor: s.color + '15',
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.3,
      fill: false,
    }}))
  }},
  options: {{
    responsive: true,
    interaction: {{mode:'index', intersect:false}},
    plugins: {{legend:{{position:'top',labels:{{color:'#94a3b8', boxWidth:12}}}}}},
    scales: {{
      x: {{ticks:{{color:'#64748b',maxTicksLimit:12}}, grid:{{color:'rgba(255,255,255,.04)'}}}},
      y: {{ticks:{{color:'#64748b',callback:v=>'HKD '+v.toLocaleString()}}, grid:{{color:'rgba(255,255,255,.06)'}}}}
    }}
  }}
}});
</script>
</body>
</html>"""
    
    out_path = Path(__file__).parent / "backtest_results" / "iron_condor_comparison.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"\n  📊 对比报告已生成 → {out_path}")


def _run_multi_tickers(args):
    """多标的对比"""
    # 标的名称映射
    ticker_names = {
        'HK.02800': '盈富基金',
        'HK.03188': '华夏沪深300',
        'HK.02822': '南方A50',
        'HK.00700': '腾讯',
    }
    
    # 使用用户指定的参数或更宽的参数
    otm = args.otm if args.otm else 0.10
    wing = args.wing if args.wing else 0.15
    dte = args.dte if args.dte else 30
    configs = [
        (otm, wing, dte, f"IC {int(otm*100)}%OTM {int(wing*100)}%翼 DTE{dte}"),
    ]
    
    all_results = []
    all_prices = {}
    
    for ticker in args.tickers:
        name = ticker_names.get(ticker, ticker)
        print(f"\n{'='*64}")
        print(f"  📊 标的: {ticker} ({name})")
        print(f"{'='*64}")
        
        # 获取数据
        df = fetch_futu_kline(ticker, args.start, args.end)
        if df is None or df.empty:
            print(f"  ⚠️  无法获取 {ticker} 数据，跳过")
            continue
        
        print(f"  📈 价格范围: {df['Close'].min():.2f} ~ {df['Close'].max():.2f}")
        
        # 保存价格数据用于图表
        all_prices[ticker] = df
        
        # 运行回测
        for otm, wing, dte, label in configs:
            full_label = f"{name} {label}"
            bt = IronCondorBacktester(
                initial_capital=args.capital,
                otm_distance=otm,
                wing_width=wing,
                dte=dte,
                label=full_label,
                cooldown_days=args.cooldown,   # V5: 冷却期
            )
            bt.run(df)
            r = bt.print_report(save_prefix=f"ic_{ticker}_{otm*100}_{wing*100}_dte{dte}")
            r['ticker'] = ticker
            r['name'] = name
            all_results.append(r)
    
    if not all_results:
        print("❌ 没有有效的回测结果")
        return
    
    # 生成多标的对比HTML
    _write_multi_ticker_html(all_results, all_prices)


def _write_multi_ticker_html(results: list, price_dfs: dict):
    """生成多标的对比HTML报告"""
    import json
    from pathlib import Path
    
    colors = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"]
    
    # 构建数据
    series_data = []
    for i, r in enumerate(results):
        ddf = r["daily_df"]
        dates = [str(d) for d in ddf["date"]]
        vals = [round(v, 0) for v in ddf["total_value"]]
        series_data.append({
            "label": f"{r['name']} ({r['label']})",
            "color": colors[i % len(colors)],
            "dates": dates,
            "values": vals,
        })
    
    # 指标卡片
    cards_html = ""
    for i, (r, color) in enumerate(zip(results, colors * 3)):
        cards_html += f"""
      <div class="card" style="border-top: 3px solid {color}">
        <div class="card-label">{r['name']}</div>
        <div class="card-metric" style="color:{color}">{r['ann_return']:+.2f}%</div>
        <div class="card-sub">年化收益</div>
        <div class="card-row"><span>总收益</span><span>{r['total_return']:+.2f}%</span></div>
        <div class="card-row"><span>最大回撤</span><span style="color:#ef4444">{r['max_dd']:.2f}%</span></div>
        <div class="card-row"><span>开仓次数</span><span>{r['n_open']}</span></div>
        <div class="card-row"><span>胜率</span><span>{r['win_rate']:.0f}%</span></div>
      </div>"""
    
    # 汇总表
    rows = ""
    for r in results:
        rows += f"""<tr>
          <td>{r['name']}</td>
          <td>{r['n_open']}</td>
          <td>HKD {r['avg_credit']:,.0f}</td>
          <td>{r['win_rate']:.0f}%</td>
          <td>{r['ann_return']:+.2f}%</td>
          <td>{r['max_dd']:.2f}%</td>
          <td>{r['total_pnl']:+.0f}</td>
        </tr>"""
    
    series_json = json.dumps(series_data, ensure_ascii=False)
    
    # 股价图表数据（只显示第一个标的的）
    first_ticker = list(price_dfs.keys())[0]
    price_df = price_dfs[first_ticker]
    price_dates = [str(d) for d in price_df["date"]]
    price_vals = [round(float(v), 2) for v in price_df["Close"]]
    price_name = results[0]['name']
    
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Iron Condor 多标的对比报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        background:#0f1117;color:#e2e8f0;min-height:100vh}}
  .header{{background:linear-gradient(135deg,#1e1b4b 0%,#1a1a2e 100%);
            padding:40px 24px 32px;text-align:center;
            border-bottom:1px solid rgba(255,255,255,.08)}}
  .header h1{{font-size:2rem;font-weight:700;
              background:linear-gradient(90deg,#818cf8,#34d399);
              -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
  .header p{{color:#94a3b8;margin-top:8px;font-size:.95rem}}
  .container{{max-width:1280px;margin:0 auto;padding:24px}}
  .section-title{{font-size:1.1rem;font-weight:600;color:#818cf8;
                  margin:32px 0 16px;letter-spacing:.05em;text-transform:uppercase}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}
  .card{{background:rgba(255,255,255,.04);border-radius:12px;padding:20px;
          transition:transform .2s;backdrop-filter:blur(8px)}}
  .card:hover{{transform:translateY(-2px)}}
  .card-label{{font-size:.8rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em}}
  .card-metric{{font-size:2.4rem;font-weight:700;margin:8px 0 4px}}
  .card-sub{{font-size:.75rem;color:#64748b;margin-bottom:16px}}
  .card-row{{display:flex;justify-content:space-between;font-size:.85rem;
              padding:4px 0;border-bottom:1px solid rgba(255,255,255,.05)}}
  .card-row span:last-child{{font-weight:600}}
  .chart-box{{background:rgba(255,255,255,.03);border-radius:14px;padding:24px;
              margin-bottom:24px;border:1px solid rgba(255,255,255,.06)}}
  .chart-title{{font-size:1rem;font-weight:600;margin-bottom:16px;color:#cbd5e1}}
  .compare-table{{width:100%;border-collapse:collapse;font-size:.9rem}}
  .compare-table th{{background:rgba(99,102,241,.2);padding:10px 14px;
                      text-align:left;font-weight:600;color:#818cf8}}
  .compare-table td{{padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.06)}}
  .compare-table tr:hover td{{background:rgba(255,255,255,.03)}}
  .winner{{background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3)}}
</style>
</head>
<body>
<div class="header">
  <h1>Iron Condor 多标的对比报告</h1>
  <p>震荡市收租神器 · 参数: 5%OTM 5%翼 DTE=30 · 初始资金 HKD 100,000</p>
</div>

<div class="container">
  <div class="section-title">📊 各标的收益对比</div>
  <div class="cards">{cards_html}</div>

  <div class="section-title">📈 资金曲线对比</div>
  <div class="chart-box">
    <div class="chart-title">组合总资产 (HKD)</div>
    <canvas id="equityChart" height="300"></canvas>
  </div>

  <div class="section-title">🔢 关键指标汇总</div>
  <div class="chart-box">
    <table class="compare-table">
      <thead><tr>
        <th>标的</th><th>开仓次数</th><th>均次权利金</th>
        <th>胜率</th><th>年化收益</th><th>最大回撤</th><th>总盈亏</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>

<script>
const seriesData = {series_json};
const priceDates = {json.dumps(price_dates)};
const priceVals  = {json.dumps(price_vals)};

const eqCtx = document.getElementById('equityChart').getContext('2d');
new Chart(eqCtx, {{
  type: 'line',
  data: {{
    labels: seriesData[0].dates,
    datasets: seriesData.map(s => ({{
      label: s.label,
      data: s.values,
      borderColor: s.color,
      backgroundColor: s.color + '15',
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.3,
      fill: false,
    }}))
  }},
  options: {{
    responsive: true,
    interaction: {{mode:'index', intersect:false}},
    plugins: {{legend:{{position:'top',labels:{{color:'#94a3b8', boxWidth:12}}}}}},
    scales: {{
      x: {{ticks:{{color:'#64748b',maxTicksLimit:12}}, grid:{{color:'rgba(255,255,255,.04)'}}}},
      y: {{ticks:{{color:'#64748b',callback:v=>'HKD '+v.toLocaleString()}}, grid:{{color:'rgba(255,255,255,.06)'}}}}
    }}
  }}
}});
</script>
</body>
</html>"""
    
    out_path = Path(__file__).parent / "backtest_results" / "iron_condor_multi_ticker.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"\n  📊 多标的对比报告已生成 → {out_path}")


if __name__ == "__main__":
    main()
