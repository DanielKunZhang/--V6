"""
美股 Iron Condor 策略回测
数据来源：富途 OpenD API（美股 SPY/QQQ 日K线）
期权定价：Black-Scholes + 历史波动率
到期日：美股标准期权 = 每月第三个周五

基于 iron_condor.py 港股回测引擎改造，适配美股市场特征。
"""

import sys
import math
import logging
import argparse
import json
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
#  美股标准期权到期日（每月第三个周五）
# ─────────────────────────────────────────────

def us_option_expiry_for_month(year: int, month: int) -> date:
    """
    计算美股标准期权当月到期日：每月第三个周五。
    简化实现，不考虑节假日（大部分月份第三个周五就是交易日）。
    """
    # 找到该月所有周五
    cal = calendar.monthcalendar(year, month)
    # calendar 返回: [[0,0,1,2,3,4,5], ...]  周一=0, 周五=4
    fridays = [week[4] for week in cal if week[4] != 0]
    
    if len(fridays) >= 3:
        return date(year, month, fridays[2])  # 第三个周五
    else:
        # 极端情况（不应该发生），取最后一天
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, last_day)


def get_us_option_expiries(start: date, end: date) -> List[date]:
    """获取区间内所有月度到期日（每月第三个周五）"""
    expiries = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        exp = us_option_expiry_for_month(y, m)
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
#  美股 Iron Condor 策略
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


class USIronCondorBacktester:
    """美股 Iron Condor 策略回测器
    
    基于港股 iron_condor.py 引擎改造：
    - 美股期权到期日：每月第三个周五
    - 美股佣金：约 $0.65/张
    - 美股无风险利率：5%（2024-2026区间）
    - 支持多组开仓（max_groups）+ 凯利公式
    
    核心区别：
    - 港股标的 ~$500HKD，美股 SPY ~$500USD, QQQ ~$450USD
    - 美股期权流动性更好，滑点更低
    - 美股保证金要求不同（SPY/QQQ 宽基ETF保证金较宽松）
    """
    
    LOT_SIZE = 100          # 美股期权每手100股
    COMMISSION = 0.65       # 单张期权佣金 USD（富途收费）
    SLIPPAGE_PCT = 0.003    # 基础滑点（美股流动性好，0.3%比港股0.5%低）
    RISK_FREE_RATE = 0.05   # 美股无风险利率（5%，2024-2026区间）
    
    # VIX 动态调参阈值（用 HV20 作为 VIX 代理）
    VIX_LOW = 0.20       # HV20 < 20%: 低波动，用基础 OTM
    VIX_HIGH = 0.30      # HV20 > 30%: 高波动，暂停开仓
    OTM_LOW_VOL = 0.05   # 低波动时 OTM = 5%
    OTM_MID_VOL = 0.08   # 中波动时 OTM = 8%（HV 20-30%）
    WING_MID_VOL = 0.12  # 中波动时 Wing = 12%（配合更宽 OTM）
    
    def __init__(self,
                 ticker: str = "US.SPY",
                 initial_capital: float = 10_000,
                 wing_width: float = 0.08,
                 otm_distance: float = 0.05,
                 dte: int = 30,
                 label: str = "",
                 min_iv: float = 0.0,
                 early_close_days: int = 2,
                 stop_loss_pct: float = 0.05,
                 max_groups: int = 1,
                 stop_loss_buffer: float = 1.5,
                 cooldown_days: int = 5,
                 entry_mode: str = "pre_expiry",
                 entry_days_before_expiry: int = 30,
                 kelly_fraction: float = 0.0,
                 dynamic_otm: bool = False,
                 ):
        self.ticker = ticker
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.wing_width = wing_width
        self.otm_distance = otm_distance
        self.dte = dte
        self.min_iv = min_iv
        self.early_close_days = early_close_days
        self.stop_loss_pct = stop_loss_pct
        self.max_groups = max_groups
        self.stop_loss_buffer = stop_loss_buffer
        self.cooldown_days = cooldown_days
        self.entry_mode = entry_mode
        self.entry_days_before_expiry = entry_days_before_expiry
        self.kelly_fraction = kelly_fraction
        self.dynamic_otm = dynamic_otm
        
        dyn_tag = " [动态OTM]" if dynamic_otm else ""
        self.label = label or f"US Iron Condor {otm_distance:.0%}±{wing_width:.0%} DTE={dte} ×{max_groups}组{dyn_tag}"
        
        self.trades: List[Dict] = []
        self.daily_records: List[Dict] = []
        self._last_opened_expiry: Optional[str] = None
        self._last_open_date: Optional[date] = None
        self._last_close_date: Optional[date] = None
        self._last_trade_month: Optional[str] = None
        
        self.positions: List[IronCondorPosition] = []
        
        # 止损/回撤追踪
        self.peak_value = initial_capital
        self.stopped = False
        self._stop_date: Optional[date] = None
        self._days_in_stop_zone: Dict[int, int] = {}
        self._expiry_calendar: List[date] = []
    
    @property
    def n_active_positions(self):
        return len(self.positions)
    
    def get_option_price_usd(self, S: float, K: float, T_days: float,
                              sigma: float, option_type: str) -> float:
        """计算单张期权价格（USD）"""
        T = T_days / 365.0
        per_share = bs_option_price(S, K, T, sigma, option_type=option_type)
        per_share *= (1 - self.SLIPPAGE_PCT)
        return per_share * self.LOT_SIZE
    
    def get_dynamic_params(self, sigma: float) -> dict:
        """
        VIX 动态调参：根据当前波动率调整 OTM 和 Wing。
        使用 HV20（20日历史波动率）作为 VIX 代理。
        
        返回:
            {"otm": float, "wing": float, "skip": bool, "reason": str}
        
        规则:
            HV20 < 20%  → OTM=5%,  Wing=8%  (低波动，标准参数)
            HV20 20-30% → OTM=8%,  Wing=12% (中波动，放宽)
            HV20 > 30%  → 暂停开仓          (高波动，观望)
        """
        if not self.dynamic_otm:
            return {"otm": self.otm_distance, "wing": self.wing_width, "skip": False, "reason": ""}
        
        if sigma > self.VIX_HIGH:
            return {
                "otm": self.OTM_MID_VOL,
                "wing": self.WING_MID_VOL,
                "skip": True,
                "reason": f"HV20={sigma:.1%} > 30%，高波动暂停开仓",
            }
        elif sigma >= self.VIX_LOW:
            return {
                "otm": self.OTM_MID_VOL,
                "wing": self.WING_MID_VOL,
                "skip": False,
                "reason": f"HV20={sigma:.1%} ∈ [20%,30%]，OTM放宽到8%，Wing=12%",
            }
        else:
            return {
                "otm": self.OTM_LOW_VOL,
                "wing": self.wing_width,
                "skip": False,
                "reason": f"HV20={sigma:.1%} < 20%，标准参数",
            }
    
    def calculate_ic_prices(self, S: float, sigma: float, dte: int = None,
                            dynamic_otm: float = None, dynamic_wing: float = None) -> Tuple[float, float, float, float, float]:
        """
        计算 Iron Condor 的4条腿价格
        
        行权价计算：
        - sell_put_k = S * (1 - OTM)
        - buy_put_k = S * (1 - OTM - wing)
        - sell_call_k = S * (1 + OTM)
        - buy_call_k = S * (1 + OTM + wing)
        
        美股行权价 round 到最近的整数（或 $0.50 刻度）。
        
        Args:
            dynamic_otm: 如果提供，覆盖 self.otm_distance（动态调参用）
            dynamic_wing: 如果提供，覆盖 self.wing_width（动态调参用）
        """
        if dte is None:
            dte = self.dte
        
        otm = dynamic_otm if dynamic_otm is not None else self.otm_distance
        wing = dynamic_wing if dynamic_wing is not None else self.wing_width
        
        # 计算行权价（先 round，再保证结构正确）
        sell_put_k = round(S * (1 - otm), 0)
        buy_put_k = round(S * (1 - otm - wing), 0)
        sell_call_k = round(S * (1 + otm), 0)
        buy_call_k = round(S * (1 + otm + wing), 0)
        
        # 确保结构正确：buy_put < sell_put < S < sell_call < buy_call
        buy_put_k = min(buy_put_k, sell_put_k - 1)  # 至少差1
        buy_call_k = max(buy_call_k, sell_call_k + 1)  # 至少差1
        
        # 确保都是正数
        buy_put_k = max(buy_put_k, 1)
        
        # 4条腿价格
        sell_put_price = self.get_option_price_usd(S, sell_put_k, dte, sigma, "PUT")
        buy_put_price = self.get_option_price_usd(S, buy_put_k, dte, sigma, "PUT")
        sell_call_price = self.get_option_price_usd(S, sell_call_k, dte, sigma, "CALL")
        buy_call_price = self.get_option_price_usd(S, buy_call_k, dte, sigma, "CALL")
        
        net_credit = (sell_put_price + sell_call_price) - (buy_put_price + buy_call_price)
        
        return sell_put_k, buy_put_k, sell_call_k, buy_call_k, net_credit
    
    def _estimate_position_value(self, pos: IronCondorPosition, S: float, sigma: float, current_date: date) -> float:
        """估算持仓当前市值"""
        days_left = max((pos.expiration - current_date).days, 1)
        
        # 计算当前4条腿的价格
        sp_price = self.get_option_price_usd(S, pos.sell_put_k, days_left, sigma, "PUT")
        bp_price = self.get_option_price_usd(S, pos.buy_put_k, days_left, sigma, "PUT")
        sc_price = self.get_option_price_usd(S, pos.sell_call_k, days_left, sigma, "CALL")
        bc_price = self.get_option_price_usd(S, pos.buy_call_k, days_left, sigma, "CALL")
        
        # 当前持仓价值 = (卖方腿已收的权利金) - (当前买回4条腿的成本)
        # 更准确：卖方腿 = -当前价格（空头），买方腿 = +当前价格（多头）
        current_value = pos.net_credit - (sp_price + sc_price) + (bp_price + bc_price)
        return current_value
    
    def _calculate_stop_loss(self, pos: IronCondorPosition, S: float, sigma: float, current_date: date) -> float:
        """计算止损时的实际亏损"""
        days_left = max((pos.expiration - current_date).days, 1)
        
        # 止损时，卖方腿亏损严重，买方腿可能还有一点残值
        sp_price = self.get_option_price_usd(S, pos.sell_put_k, days_left, sigma, "PUT")
        bp_price = self.get_option_price_usd(S, pos.buy_put_k, days_left, sigma, "PUT")
        sc_price = self.get_option_price_usd(S, pos.sell_call_k, days_left, sigma, "CALL")
        bc_price = self.get_option_price_usd(S, pos.buy_call_k, days_left, sigma, "CALL")
        
        # 实际亏损 = 买入平仓成本 - 收到的权利金
        close_cost = sp_price + sc_price - bp_price - bc_price  # 卖方腿平仓是买回，买方腿平仓是卖出
        loss = close_cost - pos.net_credit
        
        # 加上滑点惩罚
        loss *= (1 + self.SLIPPAGE_PCT)
        
        return -loss
    
    def _time_value_ratio(self, days_to_expire: int) -> float:
        """计算剩余时间价值比例（到期前平仓时使用）"""
        if days_to_expire <= 0:
            return 1.0
        # 使用平方根衰减模型（更符合期权时间价值衰减）
        original_dte = self.dte
        ratio = (days_to_expire / original_dte) ** 0.5
        # 保底80%，因为大部分时间价值在前半段已经衰减
        return max(ratio, 0.80)
    
    def _calc_kelly_groups(self, net_credit: float, max_loss: float) -> int:
        """凯利公式计算最优开仓组数"""
        if self.kelly_fraction <= 0:
            return self.max_groups
        
        estimated_win_rate = 0.65 + min(self.wing_width * 2, 0.20)
        profit_loss_ratio = net_credit / max(max_loss, 1)
        kelly_f = (estimated_win_rate * profit_loss_ratio - (1 - estimated_win_rate)) / max(profit_loss_ratio, 0.01)
        kelly_f = max(0, min(kelly_f, 0.5))
        adjusted_kelly = kelly_f * self.kelly_fraction
        
        available_capital = self.cash + self.initial_capital * 0.5
        margin_per_group = max_loss * 0.5
        max_by_capital = int(available_capital / max(margin_per_group, 1))
        
        kelly_groups = max(1, int(adjusted_kelly * available_capital / max(margin_per_group, 1)))
        result = min(kelly_groups, max_by_capital, self.max_groups)
        
        return max(result, 1)
    
    def run(self, df: pd.DataFrame, save_prefix: str = "ic_us") -> dict:
        """运行回测"""
        print(f"\n📊 开始美股 Iron Condor 回测 [{self.ticker}]...")
        print(f"   参数: OTM={self.otm_distance:.0%}, Wing={self.wing_width:.0%}, "
              f"DTE={self.dte}, Groups={self.max_groups}, CD={self.cooldown_days}d")
        prices = df["Close"]
        
        # 预生成到期日历
        start_d = df["date"].iloc[0]
        end_d = df["date"].iloc[-1]
        if hasattr(start_d, 'date'):
            start_d = start_d.date()
        if hasattr(end_d, 'date'):
            end_d = end_d.date()
        self._expiry_calendar = get_us_option_expiries(start_d, end_d + timedelta(days=60))
        
        for i, row in df.iterrows():
            current_date: date = row["date"]
            S: float = float(row["Close"])
            
            # 计算历史波动率
            past_prices = prices.iloc[max(0, i - 20): i + 1]
            sigma = historical_volatility(past_prices, 20)
            
            # 冷却恢复机制
            if self.stopped and self._stop_date:
                days_since_stop = (current_date - self._stop_date).days
                if days_since_stop >= self.cooldown_days:
                    print(f"  ✅ [{current_date}] 冷却期结束（已过{days_since_stop}天），恢复交易")
                    self.stopped = False
                    self._stop_date = None
            
            # ── 空仓 → 开仓 ─────────────────────
            if len(self.positions) == 0 and not self.stopped:
                # 冷却期检查
                can_open = True
                if self.cooldown_days > 0 and self._last_close_date:
                    days_since_close = (current_date - self._last_close_date).days
                    if days_since_close < self.cooldown_days:
                        can_open = False
                
                if can_open:
                    # 确定实际DTE
                    actual_dte = self.dte
                    target_expiry = None
                    
                    if self.entry_mode == "pre_expiry":
                        next_exp = get_next_expiry(current_date, self._expiry_calendar)
                        if next_exp:
                            actual_dte = (next_exp - current_date).days
                            target_expiry = next_exp
                            # 只有DTE在目标范围附近才开仓
                            if actual_dte > self.entry_days_before_expiry:
                                can_open = False
                    
                    if can_open and actual_dte >= 7:  # 至少7天
                        # IV过滤
                        iv_pass = sigma >= self.min_iv if self.min_iv > 0 else True
                        
                        # VIX 动态调参
                        dyn = self.get_dynamic_params(sigma)
                        if dyn["skip"]:
                            # 高波动暂停开仓，不记录 trade，直接跳过
                            can_open = False
                        
                        if iv_pass and can_open:
                            dyn_otm = dyn["otm"] if self.dynamic_otm else None
                            dyn_wing = dyn["wing"] if self.dynamic_otm else None
                            sp_k, bp_k, sc_k, bc_k, credit = self.calculate_ic_prices(
                                S, sigma, actual_dte,
                                dynamic_otm=dyn_otm, dynamic_wing=dyn_wing,
                            )
                            net_credit = credit - self.COMMISSION * 4  # 4条腿佣金
                            
                            # 最低权利金检查
                            min_credit = 50.0  # 美股最低 $50 权利金
                            
                            if (net_credit >= min_credit and
                                    sp_k > 0 and bp_k > 0 and sc_k > 0 and bc_k > 0):
                                # 单笔最大亏损 = 翼宽 × 100股
                                max_loss = (sp_k - bp_k) * self.LOT_SIZE
                                loss_pct = max_loss / max(self.cash + self.initial_capital, 1)
                                
                                # 凯利公式调整组数
                                actual_groups = self._calc_kelly_groups(net_credit, max_loss)
                                
                                # 保证金检查
                                required_margin = max_loss * 0.5 * actual_groups
                                if self.cash + self.initial_capital * 0.5 >= required_margin:
                                    exp_date = target_expiry or (current_date + timedelta(days=actual_dte))
                                    cur_exp_str = str(exp_date)
                                    
                                    if self._last_opened_expiry != cur_exp_str:
                                        self._last_opened_expiry = cur_exp_str
                                        self._last_open_date = current_date
                                        self._last_trade_month = current_date.strftime("%Y-%m")
                                        
                                        for g in range(actual_groups):
                                            self.cash += net_credit
                                            self.positions.append(IronCondorPosition(
                                                sell_put_k=sp_k,
                                                buy_put_k=bp_k,
                                                sell_call_k=sc_k,
                                                buy_call_k=bc_k,
                                                net_credit=net_credit,
                                                open_date=current_date,
                                                expiration=exp_date,
                                            ))
                                            self.trades.append({
                                                "date": str(current_date),
                                                "action": "OPEN_IC",
                                                "price": S,
                                                "sigma": round(sigma, 3),
                                                "sell_put": sp_k,
                                                "buy_put": bp_k,
                                                "sell_call": sc_k,
                                                "buy_call": bc_k,
                                                "credit": round(net_credit, 2),
                                                "expiration": str(exp_date),
                                                "days_to_exp": actual_dte,
                                                "dynamic_reason": dyn.get("reason", ""),
                                            })
                                        
                                        print(f"  🦅 [{current_date}] IC开仓 ×{actual_groups}组 DTE={actual_dte}")
                                        print(f"      PUT: 卖 {sp_k:.0f} / 买 {bp_k:.0f}  "
                                              f"CALL: 卖 {sc_k:.0f} / 买 {bc_k:.0f}")
                                        print(f"      净权利金: ${net_credit:.0f} × {actual_groups}组 = ${net_credit*actual_groups:.0f}")
            
            # ── 持仓 → 平仓判断 ─────────────────
            if self.positions:
                remaining_positions = []
                for pos in self.positions:
                    position_mv = self._estimate_position_value(pos, S, sigma, current_date)
                    total_value = self.cash + position_mv
                    
                    if total_value > self.peak_value:
                        self.peak_value = total_value
                    
                    # 总回撤止损
                    current_dd = (total_value - self.peak_value) / self.peak_value
                    if current_dd <= -self.stop_loss_pct and not self.stopped:
                        print(f"  🛑 [{current_date}] 总回撤{current_dd*100:.1f}%，暂停{self.cooldown_days}天")
                        self.stopped = True
                        self._stop_date = current_date
                        # 止损平仓
                        stop_loss = self._estimate_position_value(pos, S, sigma, current_date)
                        self.cash -= abs(stop_loss)
                        self.trades.append({
                            "date": str(current_date),
                            "action": "STOP_LOSS",
                            "result": f"总回撤{int(self.stop_loss_pct*100)}%_暂停{self.cooldown_days}天",
                            "pnl": round(-abs(stop_loss), 2),
                        })
                        continue
                    
                    # 提前平仓 / 止损检查
                    days_to_expire = (pos.expiration - current_date).days
                    
                    # 止损线计算
                    sell_put_k = pos.sell_put_k
                    sell_call_k = pos.sell_call_k
                    buy_put_k = pos.buy_put_k
                    buy_call_k = pos.buy_call_k
                    
                    put_wing_width = sell_put_k - buy_put_k
                    call_wing_width = buy_call_k - sell_call_k
                    
                    if self.stop_loss_buffer >= 1.0:
                        stop_put = sell_put_k - put_wing_width * min(self.stop_loss_buffer - 1.0, 0.8)
                        stop_call = sell_call_k + call_wing_width * min(self.stop_loss_buffer - 1.0, 0.8)
                    else:
                        stop_put = sell_put_k
                        stop_call = sell_call_k
                    
                    should_close = False
                    close_reason = "到期前平仓"
                    
                    if S <= stop_put:
                        should_close = True
                        close_reason = "跌破PUT止损线"
                    elif S >= stop_call:
                        should_close = True
                        close_reason = "涨破CALL止损线"
                    elif days_to_expire <= self.early_close_days:
                        should_close = True
                        close_reason = f"到期前{self.early_close_days}天"
                    
                    if should_close:
                        self._last_close_date = current_date
                        
                        if S <= stop_put or S >= stop_call:
                            # 破位止损
                            loss_val = self._estimate_position_value(pos, S, sigma, current_date)
                            self.cash += loss_val  # loss_val 是负数
                            pnl = loss_val
                            self.trades.append({
                                "date": str(current_date),
                                "action": "EARLY_CLOSE",
                                "price": S,
                                "pnl": round(pnl, 2),
                                "result": close_reason,
                            })
                            print(f"  ⚠️  [{current_date}] {close_reason} PnL=${pnl:.0f} (S=${S:.1f})")
                        else:
                            # 正常提前平仓
                            early_credit = pos.net_credit * self._time_value_ratio(days_to_expire)
                            self.cash += early_credit
                            self.trades.append({
                                "date": str(current_date),
                                "action": "EARLY_CLOSE",
                                "price": S,
                                "pnl": round(early_credit, 2),
                                "result": close_reason,
                            })
                            print(f"  📅 [{current_date}] {close_reason} PnL=${early_credit:.0f}")
                        continue
                    
                    # 到期结算
                    if current_date >= pos.expiration:
                        self._last_close_date = current_date
                        if buy_put_k < S < sell_call_k:
                            pnl = pos.net_credit
                            result = "盈利"
                        elif S <= buy_put_k:
                            loss = (sell_put_k - buy_put_k) * self.LOT_SIZE - pos.net_credit
                            pnl = -loss
                            result = "PUT被行权"
                        elif S >= sell_call_k:
                            loss = (buy_call_k - sell_call_k) * self.LOT_SIZE - pos.net_credit
                            pnl = -loss
                            result = "CALL被行权"
                        else:
                            pnl = pos.net_credit
                            result = "盈利"
                        
                        self.cash += pnl
                        self.trades.append({
                            "date": str(current_date),
                            "action": "IC_EXPIRED",
                            "price": S,
                            "result": result,
                            "pnl": round(pnl, 2),
                        })
                        print(f"  📅 [{current_date}] 到期: {result} PnL=${pnl:.0f}")
                        continue
                    
                    # 未平仓，继续持有
                    remaining_positions.append(pos)
                
                self.positions = remaining_positions
            
            # ── 每日记录 ───────────────────────
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
                "cash": round(self.cash, 2),
                "total_value": round(total_value, 2),
                "return_pct": round(ret_pct, 4),
                "position": "持有" if self.positions else "空仓",
            })
        
        return self.print_report(save_prefix)
    
    def print_report(self, save_prefix: str = "ic_us") -> dict:
        """生成回测报告"""
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
            
            losses = tf[tf.action == "IC_EXPIRED"]
            if not losses.empty:
                n_loss = (losses["pnl"] < 0).sum()
        
        n_closed = n_expired + n_early_close
        profitable_closes = n_expired - n_loss
        early_trades = tf[tf.action == "EARLY_CLOSE"]
        if not early_trades.empty:
            n_early_win = (early_trades["pnl"] > 0).sum()
            profitable_closes += int(n_early_win)
        
        win_rate = (profitable_closes / n_closed * 100) if n_closed > 0 else (100.0 if n_open > 0 else 0.0)
        
        # 夏普比率
        sharpe_ratio = 0.0
        if len(df) > 10 and years > 0.1:
            df["daily_return"] = df["total_value"].pct_change()
            daily_returns = df["daily_return"].dropna()
            if len(daily_returns) > 5 and daily_returns.std() > 1e-10:
                rf_daily = self.RISK_FREE_RATE / 252
                excess_return = daily_returns - rf_daily
                sharpe_ratio = round(excess_return.mean() / excess_return.std() * math.sqrt(252), 2)
        
        print(f"\n{'='*64}")
        print(f"  🦅  [{self.label}]")
        print(f"{'='*64}")
        print(f"""
  初始资金   ${self.initial_capital:>10,.0f}   →   最终 ${final_value:>10,.0f}
  总收益率   {total_return:+.2f}%   年化 {ann_return:+.2f}%   共 {years:.1f} 年
  总盈亏     ${total_pnl:>+10,.0f}
  最大回撤   {max_dd:.2f}%  ({max_dd_date})
  夏普比率   {sharpe_ratio:.2f}
  开仓次数   {n_open} 次（均值权利金 ${avg_credit:.0f}）
  到期结算   {n_expired} 次  /  提前平仓 {n_early_close} 次
  亏损次数   {n_loss} 次
  胜率       {win_rate:.0f}%（{n_closed}笔平仓）
        """)
        
        # 保存 CSV
        out = Path(__file__).parent / "backtest_results"
        out.mkdir(exist_ok=True)
        df.to_csv(out / f"{save_prefix}_daily.csv", index=False)
        if not tf.empty:
            tf.to_csv(out / f"{save_prefix}_trades.csv", index=False)
        
        return {
            "label": self.label,
            "ticker": self.ticker,
            "wing_width": self.wing_width,
            "otm_distance": self.otm_distance,
            "dte": self.dte,
            "max_groups": self.max_groups,
            "cooldown_days": self.cooldown_days,
            "final_value": round(final_value, 0),
            "total_return": round(total_return, 2),
            "ann_return": round(ann_return, 2),
            "total_pnl": round(total_pnl, 0),
            "max_dd": round(max_dd, 2),
            "max_dd_date": str(max_dd_date),
            "sharpe_ratio": sharpe_ratio,
            "n_open": n_open,
            "n_expired": n_expired,
            "n_early_close": n_early_close,
            "n_closed": n_closed,
            "n_loss": n_loss,
            "avg_credit": round(avg_credit, 0),
            "win_rate": round(win_rate, 1),
            "years": round(years, 1),
        }


def run_param_sweep(ticker: str = "US.SPY", capital: float = 10_000):
    """运行参数扫描（DTE × OTM × max_groups 组合）"""
    print("=" * 64)
    print(f"  🦅  美股 Iron Condor 参数扫描 [{ticker}]")
    print(f"  初始资金: ${capital:,.0f}")
    print("=" * 64)
    
    # 获取历史K线
    df = fetch_futu_kline(ticker, "2020-01-01", "2025-12-31")
    if df is None or df.empty:
        print("❌ 无法获取数据")
        return []
    
    print(f"\n📊 数据: {len(df)} 个交易日, {df['date'].iloc[0]} → {df['date'].iloc[-1]}")
    
    # 参数组合设计
    configs = [
        # === 基线对比：不同 DTE ===
        {"label": "DTE=30 OTM5% W8% G1",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 5},
        {"label": "DTE=21 OTM5% W8% G1",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 21, "max_groups": 1, "cooldown_days": 5},
        {"label": "DTE=45 OTM5% W8% G1",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 45, "max_groups": 1, "cooldown_days": 5},
        
        # === 不同 OTM ===
        {"label": "DTE=30 OTM3% W8% G1",  "otm_distance": 0.03, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 5},
        {"label": "DTE=30 OTM5% W5% G1",  "otm_distance": 0.05, "wing_width": 0.05, "dte": 30, "max_groups": 1, "cooldown_days": 5},
        {"label": "DTE=30 OTM5% W8% G1",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 5},
        {"label": "DTE=30 OTM10% W8% G1", "otm_distance": 0.10, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 5},
        
        # === max_groups 对比（1组 vs 多组，看$10,000能撑几组）===
        {"label": "DTE=30 OTM5% W8% G1 CD5",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 5},
        {"label": "DTE=30 OTM5% W8% G2 CD5",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 2, "cooldown_days": 5},
        {"label": "DTE=30 OTM5% W8% G3 CD5",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 3, "cooldown_days": 5},
        {"label": "DTE=30 OTM5% W8% G5 CD5",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 5, "cooldown_days": 5},
        
        # === 冷却期对比 ===
        {"label": "DTE=30 OTM5% W8% G1 CD0",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 0},
        {"label": "DTE=30 OTM5% W8% G1 CD5",  "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 5},
        {"label": "DTE=30 OTM5% W8% G1 CD15", "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 15},
        
        # === 止损缓冲对比 ===
        {"label": "DTE=30 OTM5% W8% G1 BUF1.0", "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 5, "stop_loss_buffer": 1.0},
        {"label": "DTE=30 OTM5% W8% G1 BUF1.5", "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 5, "stop_loss_buffer": 1.5},
        {"label": "DTE=30 OTM5% W8% G1 BUF2.0", "otm_distance": 0.05, "wing_width": 0.08, "dte": 30, "max_groups": 1, "cooldown_days": 5, "stop_loss_buffer": 2.0},
    ]
    
    results = []
    for idx, cfg in enumerate(configs):
        label = cfg["label"]
        print(f"\n{'─'*64}")
        print(f"  ▶  [{idx+1}/{len(configs)}] {label}")
        print(f"{'─'*64}")
        
        bt = USIronCondorBacktester(
            ticker=ticker,
            initial_capital=capital,
            otm_distance=cfg["otm_distance"],
            wing_width=cfg["wing_width"],
            dte=cfg["dte"],
            max_groups=cfg["max_groups"],
            cooldown_days=cfg.get("cooldown_days", 5),
            stop_loss_buffer=cfg.get("stop_loss_buffer", 1.5),
            early_close_days=2,
            stop_loss_pct=0.05,
            entry_mode="pre_expiry",
            entry_days_before_expiry=cfg["dte"],
            label=label,
        )
        
        r = bt.run(df, save_prefix=f"ic_us_{ticker.split('.')[1]}_{idx}")
        results.append(r)
    
    # 汇总对比表
    print(f"\n\n{'='*100}")
    print(f"  📊 参数扫描汇总 [{ticker}] - ${capital:,.0f} 本金")
    print(f"{'='*100}")
    print(f"{'配置':<35} {'年化':>8} {'最大回撤':>10} {'夏普':>6} {'开仓':>6} {'胜率':>6} {'最终资金':>10}")
    print(f"{'-'*100}")
    
    for r in sorted(results, key=lambda x: x["ann_return"], reverse=True):
        print(f"{r['label']:<35} {r['ann_return']:>+7.2f}% {r['max_dd']:>9.2f}% "
              f"{r['sharpe_ratio']:>6.2f} {r['n_open']:>5}次 {r['win_rate']:>5.0f}% "
              f"${r['final_value']:>9,.0f}")
    
    # 保存结果
    out = Path(__file__).parent / "backtest_results"
    out.mkdir(exist_ok=True)
    
    # JSON 结果
    with open(out / f"ic_us_{ticker.split('.')[1]}_sweep.json", "w") as f:
        # 移除 daily_df 和 trades_df（不能序列化）
        json_results = [{k: v for k, v in r.items() if k not in ("daily_df", "trades_df")} for r in results]
        json.dump(json_results, f, indent=2, default=str)
    
    # HTML 报告
    _generate_html_report(results, ticker, capital, out)
    
    return results


def _generate_html_report(results: list, ticker: str, capital: float, out_dir: Path):
    """生成 HTML 对比报告"""
    ticker_name = ticker.split(".")[1]
    
    # 按年化排序
    sorted_results = sorted(results, key=lambda x: x["ann_return"], reverse=True)
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>美股 Iron Condor 参数扫描 - {ticker_name}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #eee; }}
h1 {{ color: #00d2ff; text-align: center; }}
h2 {{ color: #7f5af0; margin-top: 40px; }}
table {{ width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; }}
th {{ background: #16213e; color: #00d2ff; padding: 12px 8px; text-align: center; position: sticky; top: 0; }}
td {{ padding: 10px 8px; text-align: center; border-bottom: 1px solid #2a2a4a; }}
tr:hover {{ background: #16213e; }}
.positive {{ color: #00ff88; }}
.negative {{ color: #ff4444; }}
.best {{ background: #0a3d2a; font-weight: bold; }}
.summary {{ background: #16213e; padding: 20px; border-radius: 10px; margin: 20px 0; }}
.metric {{ display: inline-block; margin: 10px 20px; }}
.metric-value {{ font-size: 24px; font-weight: bold; }}
.metric-label {{ color: #888; font-size: 12px; }}
</style>
</head>
<body>
<h1>🦅 美股 Iron Condor 参数扫描</h1>
<div class="summary" style="text-align: center;">
<p style="font-size: 18px;">标的: <strong>{ticker}</strong> | 本金: <strong>${capital:,.0f}</strong> | 数据: 2020-2025 富途API真实K线</p>
</div>

<h2>📊 全部参数组合（按年化收益排序）</h2>
<table>
<tr>
<th>配置</th><th>年化收益</th><th>总收益</th><th>最大回撤</th><th>夏普比率</th>
<th>开仓次数</th><th>胜率</th><th>均次权利金</th><th>最终资金</th>
</tr>"""
    
    for i, r in enumerate(sorted_results):
        row_class = "best" if i == 0 else ""
        ann_cls = "positive" if r["ann_return"] > 0 else "negative"
        dd_cls = "negative" if r["max_dd"] < -5 else ""
        
        html += f"""<tr class="{row_class}">
<td style="text-align:left; padding-left: 15px;">{r['label']}</td>
<td class="{ann_cls}">{r['ann_return']:+.2f}%</td>
<td class="{ann_cls}">{r['total_return']:+.2f}%</td>
<td class="{dd_cls}">{r['max_dd']:.2f}%</td>
<td>{r['sharpe_ratio']:.2f}</td>
<td>{r['n_open']}次</td>
<td>{r['win_rate']:.0f}%</td>
<td>${r['avg_credit']:.0f}</td>
<td>${r['final_value']:,.0f}</td>
</tr>"""
    
    html += """</table>
<h2>🏆 最优配置推荐</h2>
<div class="summary">"""
    
    if sorted_results:
        best = sorted_results[0]
        html += f"""
<p>根据回测数据，<strong>{best['label']}</strong> 表现最佳：</p>
<ul>
<li>年化收益: <span class="positive">{best['ann_return']:+.2f}%</span></li>
<li>最大回撤: {best['max_dd']:.2f}%</li>
<li>夏普比率: {best['sharpe_ratio']:.2f}</li>
<li>开仓次数: {best['n_open']}次，胜率: {best['win_rate']:.0f}%</li>
<li>初始 ${capital:,.0f} → 最终 ${best['final_value']:,.0f}</li>
</ul>"""
    
    html += """</div>
<p style="text-align: center; color: #666; margin-top: 40px;">
数据来源：富途 OpenD API 真实日K线 | 期权定价：Black-Scholes + 20日历史波动率<br>
生成时间：""" + datetime.now().strftime("%Y-%m-%d %H:%M") + """
</p>
</body></html>"""
    
    html_path = out_dir / f"ic_us_{ticker_name}_param_sweep.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"\n📄 报告已保存: {html_path}")


def main():
    parser = argparse.ArgumentParser(description="美股 Iron Condor 策略回测")
    parser.add_argument("--capital", type=float, default=10_000, help="初始资金 (默认$10,000)")
    parser.add_argument("--start", default="2020-01-01", help="开始日期")
    parser.add_argument("--end", default="2025-12-31", help="结束日期")
    parser.add_argument("--ticker", default="US.SPY", help="标的代码 (US.SPY / US.QQQ)")
    parser.add_argument("--otm", type=float, default=0.05, help="OTM距离")
    parser.add_argument("--wing", type=float, default=0.08, help="翼宽")
    parser.add_argument("--dte", type=int, default=30, help="DTE")
    parser.add_argument("--groups", type=int, default=1, help="最多开仓组数")
    parser.add_argument("--cooldown", type=int, default=5, help="冷却期天数")
    parser.add_argument("--dynamic-otm", action="store_true", help="启用VIX动态调参（HV20代理VIX）")
    parser.add_argument("--sweep", action="store_true", help="运行参数扫描")
    args = parser.parse_args()
    
    if args.sweep:
        run_param_sweep(ticker=args.ticker, capital=args.capital)
        return
    
    # 单次回测
    df = fetch_futu_kline(args.ticker, args.start, args.end)
    if df is None or df.empty:
        print("❌ 无法获取数据")
        sys.exit(1)
    
    bt = USIronCondorBacktester(
        ticker=args.ticker,
        initial_capital=args.capital,
        otm_distance=args.otm,
        wing_width=args.wing,
        dte=args.dte,
        max_groups=args.groups,
        cooldown_days=args.cooldown,
        entry_mode="pre_expiry",
        entry_days_before_expiry=args.dte,
        dynamic_otm=args.dynamic_otm,
    )
    bt.run(df)


if __name__ == "__main__":
    main()
