#!/usr/bin/env python3
"""
复合策略回测 v1.0
═══════════════════════════════════════════════════════════════════

三层架构：
  Layer 1 — IC核心 (65%资金 + 轻杠杆)
    标的: QQQ(60%) + IWM(20%) + GLD(20%)，沿用配置D参数
    改进: 动态滑点（随vol regime升级）+ VIX硬止损（HV20>0.45强平）
    轻杠杆: 1.25x，但HV20>0.25时自动降回1.0x

  Layer 2 — VIX Spike Straddle (7.5%预算)
    触发: QQQ的HV20单周跳升>40%（如0.18→0.25+），或绝对值首次越过0.32
    动作: 买入QQQ ATM跨式，DTE=45
    退出: 盈利100% / 亏损50% / 剩余DTE=21
    预算: 每次$500，最多2张并发

  Layer 3 — Cash Reserve (27.5%)
    收益率: 5%年化（国债/货币基金）
    作用: 极端行情时有子弹，提供流动性缓冲

现实化调整:
  - 动态滑点: 正常0.5% / 高波2.0% / 极端5.0%
  - VIX硬止损时额外+3%滑点（流动性溢价）
  - 轻杠杆: 1.25x，年化融资成本5.5%，极端vol自动解除

对比基准: 配置D纯IC（无杠杆，标准滑点0.3%）

用法:
  python3 composite_backtest.py
  python3 composite_backtest.py --no-straddle      # 仅IC+Cash，无Straddle
  python3 composite_backtest.py --no-leverage       # 无杠杆版本
  python3 composite_backtest.py --leverage 1.5      # 自定义杠杆
"""

import sys, math, argparse
from collections import deque
from pathlib import Path
from datetime import date, timedelta
from typing import Optional, List, Dict, Tuple
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline, bs_option_price, historical_volatility
from iron_condor_us import USIronCondorBacktester, get_us_option_expiries, get_next_expiry, IronCondorPosition

# ═══════════════════════════════════════════════════════════════════
# 全局参数
# ═══════════════════════════════════════════════════════════════════
TOTAL_CAPITAL   = 15_000
START, END      = "2010-01-01", "2025-12-31"
RISK_FREE       = 0.05
MARGIN_RATE     = 0.055         # 融资年利率

IC_RATIO        = 0.65          # IC核心占总资金比
STRADDLE_RATIO  = 0.075         # Straddle预算占总资金比
CASH_RATIO      = 0.275         # 现金储备比

# 动态滑点阈值（Option A：中等波动段不惩罚）
# 注：阈值均为纯HV（无×1.15），与Finviz/富途口径一致
SLIP_NORMAL     = 0.005         # HV20 < 0.30: 0.5%（含中等波动段）
SLIP_ELEVATED   = 0.020         # 0.30 ≤ HV20 < 0.39: 2%
SLIP_EXTREME    = 0.050         # HV20 ≥ 0.39: 5%（对应原0.45/1.15）
SLIP_HARD_STOP  = 0.030         # VIX硬止损额外滑点（叠加在SLIP_EXTREME上）

# VIX代理阈值（用QQQ的纯HV20，与外部工具口径一致）
VIX_HARD_STOP_HV   = 0.39      # 纯HV > 39%: 强制平仓（原0.45/1.15）
VIX_NO_LEVERAGE_HV = 0.22      # 纯HV > 22%: 固定杠杆模式下解除杠杆（原0.25/1.15）

# Vol Targeting 参数
VOL_TARGET_MIN_LEV = 0.50      # 最低杠杆（极高波动时保底仓位）
VOL_TARGET_MAX_LEV = 3.00      # 最高杠杆上限
VOL_TARGET_BASE_HV = 0.13      # 参考纯HV（= 此时使用base leverage，原0.15/1.15）
VIX_COOLDOWN_HV    = 0.28      # 纯HV需降至此阈值才恢复开仓（原0.32/1.15）

# Straddle参数
STRADDLE_TRIGGER_HV_JUMP = 0.40   # HV20单周相对跳升>40%触发
STRADDLE_TRIGGER_HV_ABS  = 0.32   # HV20绝对值首次越过此阈值触发
STRADDLE_BUDGET_PER_TRADE = 500   # 每次买入预算上限 $500
STRADDLE_MAX_CONCURRENT   = 2     # 最多同时持有2张跨式
STRADDLE_DTE              = 45    # 跨式DTE
STRADDLE_EXIT_PROFIT      = 1.00  # 盈利100%平仓
STRADDLE_EXIT_LOSS        = 0.50  # 亏损50%止损
STRADDLE_EXIT_DTE         = 21    # 剩余DTE ≤ 21天平仓

# 配置D各标的参数（GLD版）— 阈值为纯HV（Scenario C，972组扫描最优，QQQ/IWM≤25%, GLD≤18%）
ASSETS_CONFIG = [
    {"ticker": "US.QQQ", "capital_ratio": 9/15, "max_groups": 2, "hv20_threshold": 0.25},   # 纯HV≤25%（Scenario C）
    {"ticker": "US.IWM", "capital_ratio": 3/15, "max_groups": 1, "hv20_threshold": 0.25},   # 纯HV≤25%（Scenario C）
    {"ticker": "US.GLD", "capital_ratio": 3/15, "max_groups": 1, "hv20_threshold": 0.18},   # 纯HV≤18%（Scenario C）
]

# TLT版：将GLD替换为20年期国债ETF（负相关对冲，捕捉利率波动溢价）
ASSETS_CONFIG_TLT = [
    {"ticker": "US.QQQ", "capital_ratio": 9/15, "max_groups": 2, "hv20_threshold": 0.25},   # 纯HV≤25%（Scenario C）
    {"ticker": "US.IWM", "capital_ratio": 3/15, "max_groups": 1, "hv20_threshold": 0.25},   # 纯HV≤25%（Scenario C）
    {"ticker": "US.TLT", "capital_ratio": 3/15, "max_groups": 1, "hv20_threshold": 0.130},  # TLT维持保守（利率债波动特性不同）
]


# ═══════════════════════════════════════════════════════════════════
# Layer 1: 增强型IC回测器（动态滑点 + VIX硬止损）
# ═══════════════════════════════════════════════════════════════════
class EnhancedICBacktester(USIronCondorBacktester):
    """
    在USIronCondorBacktester基础上增加：
    1. 动态滑点：根据当前HV20调整滑点
    2. VIX硬止损：HV20 > vix_hard_stop时强制平仓
    3. VIX硬止损后冷却期延长（等待HV20回落）
    """

    # 变动OTM阈值（Option A+）— 纯HV口径
    VAR_OTM_LOW_HV  = 0.13   # 纯HV < 13%: 收窄OTM（原0.15/1.15）
    VAR_OTM_HIGH_HV = 0.22   # 纯HV ≥ 22%: 拓宽OTM（原0.25/1.15）

    def __init__(self, vix_hard_stop_hv=VIX_HARD_STOP_HV,
                 vix_cooldown_hv=VIX_COOLDOWN_HV,
                 use_variable_otm: bool = False,
                 iv_rank_min: float = 0.0,
                 put_otm: float = None,
                 call_otm: float = None,
                 ib_hv_threshold: float = 0.0,
                 **kwargs):
        # 任何动态OTM模式都需开启父类 dynamic_otm 标志
        if use_variable_otm or ib_hv_threshold > 0:
            kwargs["dynamic_otm"] = True
        super().__init__(**kwargs)
        self.vix_hard_stop_hv  = vix_hard_stop_hv
        self.vix_cooldown_hv   = vix_cooldown_hv
        self.use_variable_otm  = use_variable_otm
        self.iv_rank_min       = iv_rank_min
        self.put_otm           = put_otm
        self.call_otm          = call_otm
        self.ib_hv_threshold   = ib_hv_threshold  # HV20 < 此值时切换为Iron Butterfly
        self._hv_history       = deque(maxlen=252)
        self._hard_stopped     = False

    def get_dynamic_params(self, sigma: float) -> dict:
        """优先级：Iron Butterfly > 变动OTM > 固定OTM"""
        # Iron Butterfly：低波时卖ATM价差，权利金5~8x于IC
        if self.ib_hv_threshold > 0 and sigma < self.ib_hv_threshold:
            return {"otm": 0.0, "wing": self.wing_width, "skip": False,
                    "reason": f"HV20={sigma:.1%}<{self.ib_hv_threshold:.0%}，Iron Butterfly(ATM)"}
        if not self.use_variable_otm:
            return super().get_dynamic_params(sigma)
        if sigma < self.VAR_OTM_LOW_HV:
            return {"otm": 0.035, "wing": 0.060, "skip": False,
                    "reason": f"HV20={sigma:.1%}<13%，低波收窄 OTM=3.5%"}
        elif sigma < self.VAR_OTM_HIGH_HV:
            return {"otm": 0.050, "wing": 0.080, "skip": False,
                    "reason": f"HV20={sigma:.1%}∈[13%,22%)，标准 OTM=5%"}
        else:
            return {"otm": 0.065, "wing": 0.100, "skip": False,
                    "reason": f"HV20={sigma:.1%}≥22%，高波拓宽 OTM=6.5%"}

    def _get_dynamic_slippage(self, sigma: float) -> float:
        """根据纯HV regime返回滑点倍数（阈值已换算为纯HV口径）"""
        if sigma >= 0.39:
            return SLIP_EXTREME        # 极端：纯HV≥39%（原45%/1.15）
        elif sigma >= 0.30:
            return SLIP_ELEVATED       # 高波：纯HV≥30%（原35%/1.15）
        else:
            return SLIP_NORMAL         # 正常/中等波动：一律0.5%

    def calculate_ic_prices(self, S: float, sigma: float, dte: int = None,
                            dynamic_otm: float = None, dynamic_wing: float = None):
        """非对称模式：put/call使用不同OTM；对称模式沿用父类"""
        if self.put_otm is None:
            return super().calculate_ic_prices(S, sigma, dte, dynamic_otm, dynamic_wing)

        if dte is None:
            dte = self.dte
        wing = dynamic_wing if dynamic_wing is not None else self.wing_width

        sell_put_k  = round(S * (1 - self.put_otm), 0)
        buy_put_k   = round(S * (1 - self.put_otm - wing), 0)
        sell_call_k = round(S * (1 + self.call_otm), 0)
        buy_call_k  = round(S * (1 + self.call_otm + wing), 0)

        buy_put_k   = min(buy_put_k,  sell_put_k  - 1)
        buy_call_k  = max(buy_call_k, sell_call_k + 1)
        buy_put_k   = max(buy_put_k, 1)

        sp = self.get_option_price_usd(S, sell_put_k,  dte, sigma, "PUT")
        bp = self.get_option_price_usd(S, buy_put_k,   dte, sigma, "PUT")
        sc = self.get_option_price_usd(S, sell_call_k, dte, sigma, "CALL")
        bc = self.get_option_price_usd(S, buy_call_k,  dte, sigma, "CALL")

        net_credit = (sp + sc - bp - bc)
        return sell_put_k, buy_put_k, sell_call_k, buy_call_k, net_credit

    def _close_position_with_slippage(self, pos: IronCondorPosition,
                                       S: float, sigma: float,
                                       current_date: date,
                                       extra_slip: float = 0.0) -> float:
        """平仓并应用动态滑点，返回实际PnL"""
        from backtest_real import bs_option_price
        days_left = max((pos.expiration - current_date).days, 1)

        sp = self.get_option_price_usd(S, pos.sell_put_k,  days_left, sigma, "PUT")
        bp = self.get_option_price_usd(S, pos.buy_put_k,   days_left, sigma, "PUT")
        sc = self.get_option_price_usd(S, pos.sell_call_k, days_left, sigma, "CALL")
        bc = self.get_option_price_usd(S, pos.buy_call_k,  days_left, sigma, "CALL")

        close_cost = sp + sc - bp - bc
        loss = close_cost - pos.net_credit

        slip = self._get_dynamic_slippage(sigma) + extra_slip
        loss *= (1 + slip)
        return -loss   # 正数=盈利，负数=亏损

    def run(self, df: pd.DataFrame, save_prefix: str = "enh_ic") -> dict:
        """重写run()，加入VIX硬止损逻辑"""
        prices = df["Close"]
        start_d = df["date"].iloc[0]
        end_d   = df["date"].iloc[-1]
        if hasattr(start_d, 'date'): start_d = start_d.date()
        if hasattr(end_d,   'date'): end_d   = end_d.date()
        self._expiry_calendar = get_us_option_expiries(
            start_d, end_d + timedelta(days=60))

        for i, row in df.iterrows():
            current_date: date = row["date"]
            S: float = float(row["Close"])
            past_prices = prices.iloc[max(0, i - 20): i + 1]
            hv20   = historical_volatility(past_prices, 20)          # 纯HV，用于入场过滤/VIX控制
            iv_est = hv20 * 1.15                                      # IV估算，用于BS期权定价

            # 每日更新HV历史（用于IV Rank计算，存纯HV）
            self._hv_history.append(hv20)

            # ── VIX硬止损检查（最高优先级）──────────────────────
            if not self._hard_stopped and hv20 >= self.vix_hard_stop_hv and self.positions:
                print(f"  🚨 [{current_date}] VIX硬止损触发！HV20={hv20:.1%}≥{self.vix_hard_stop_hv:.0%}，强平所有IC")
                for pos in self.positions:
                    pnl = self._close_position_with_slippage(
                        pos, S, iv_est, current_date,
                        extra_slip=SLIP_HARD_STOP)
                    self.cash += pnl
                    self.trades.append({
                        "date": str(current_date), "action": "VIX_HARD_STOP",
                        "pnl": round(pnl, 2), "hv20": round(hv20, 3),
                    })
                self.positions = []
                self._hard_stopped = True
                self._stop_date = current_date
                self.stopped = True

            # VIX硬止损恢复条件：HV20回落到冷却阈值以下
            if self._hard_stopped and hv20 < self.vix_cooldown_hv:
                print(f"  ✅ [{current_date}] VIX恢复，HV20={hv20:.1%}<{self.vix_cooldown_hv:.0%}，解除硬止损")
                self._hard_stopped = False
                self.stopped = False
                self._stop_date = None

            # ── 普通冷却期恢复（非硬止损）──────────────────────
            if self.stopped and not self._hard_stopped and self._stop_date:
                days_since_stop = (current_date - self._stop_date).days
                if days_since_stop >= self.cooldown_days:
                    self.stopped = False
                    self._stop_date = None

            # ── 空仓 → 开仓（复用父类逻辑，改动：使用HV20阈值）────
            if len(self.positions) == 0 and not self.stopped:
                can_open = True
                if self.cooldown_days > 0 and self._last_close_date:
                    if (current_date - self._last_close_date).days < self.cooldown_days:
                        can_open = False

                if can_open:
                    actual_dte = self.dte
                    target_expiry = None
                    if self.entry_mode == "pre_expiry":
                        next_exp = get_next_expiry(current_date, self._expiry_calendar)
                        if next_exp:
                            actual_dte = (next_exp - current_date).days
                            target_expiry = next_exp
                            if actual_dte > self.entry_days_before_expiry:
                                can_open = False

                    if can_open and actual_dte >= 7:
                        # ── IV Rank 过滤（基于纯HV历史）────────────
                        if self.iv_rank_min > 0.0 and len(self._hv_history) >= 30:
                            iv_rank = np.mean(np.array(self._hv_history) <= hv20)
                            if iv_rank < self.iv_rank_min:
                                can_open = False  # 当前权利金偏便宜，跳过

                        dyn = self.get_dynamic_params(hv20)   # 入场过滤用纯HV
                        if dyn["skip"]:
                            can_open = False

                        if can_open:
                            # 期权定价用iv_est（更接近市场实际IV）
                            dyn_otm  = dyn["otm"]  if self.dynamic_otm else None
                            dyn_wing = dyn["wing"] if self.dynamic_otm else None
                            sp_k, bp_k, sc_k, bc_k, credit = self.calculate_ic_prices(
                                S, iv_est, actual_dte,
                                dynamic_otm=dyn_otm, dynamic_wing=dyn_wing)
                            net_credit = credit - self.COMMISSION * 4
                            if net_credit >= 50 and sp_k > 0 and sc_k > 0:
                                max_loss = (sp_k - bp_k) * self.LOT_SIZE
                                actual_groups = self._calc_kelly_groups(net_credit, max_loss)
                                required_margin = max_loss * 0.5 * actual_groups
                                if (self.cash + self.initial_capital * 0.5 >= required_margin and
                                        self._last_opened_expiry != str(target_expiry or "")):
                                    exp_date = target_expiry or (current_date + timedelta(days=actual_dte))
                                    self._last_opened_expiry = str(exp_date)
                                    self._last_open_date = current_date
                                    slip = self._get_dynamic_slippage(hv20)  # 滑点基于纯HV regime
                                    entry_credit = net_credit * (1 - slip)
                                    for _ in range(actual_groups):
                                        self.cash += entry_credit
                                        self.positions.append(IronCondorPosition(
                                            sell_put_k=sp_k, buy_put_k=bp_k,
                                            sell_call_k=sc_k, buy_call_k=bc_k,
                                            net_credit=entry_credit,
                                            open_date=current_date, expiration=exp_date,
                                        ))

            # ── 持仓 → 平仓判断 ────────────────────────────────
            remaining = []
            for pos in self.positions:
                days_to_exp = (pos.expiration - current_date).days
                position_mv = self._estimate_position_value(pos, S, iv_est, current_date)
                total_value = self.cash + position_mv

                if total_value > self.peak_value:
                    self.peak_value = total_value

                current_dd = (total_value - self.peak_value) / self.peak_value

                # 普通回撤止损
                if current_dd <= -self.stop_loss_pct and not self.stopped:
                    self.stopped = True
                    self._stop_date = current_date
                    pnl = self._close_position_with_slippage(pos, S, iv_est, current_date)
                    self.cash += pnl
                    self.trades.append({
                        "date": str(current_date), "action": "STOP_LOSS",
                        "pnl": round(pnl, 2),
                    })
                    continue

                # 价格触及止损线
                put_w = pos.sell_put_k - pos.buy_put_k
                call_w = pos.buy_call_k - pos.sell_call_k
                stop_put  = pos.sell_put_k  - put_w  * min(self.stop_loss_buffer - 1.0, 0.8)
                stop_call = pos.sell_call_k + call_w * min(self.stop_loss_buffer - 1.0, 0.8)

                should_close = False
                if S <= stop_put or S >= stop_call:
                    should_close = True
                elif days_to_exp <= self.early_close_days:
                    should_close = True

                if should_close:
                    pnl = self._close_position_with_slippage(pos, S, iv_est, current_date)
                    self.cash += pnl
                    self._last_close_date = current_date
                    self.trades.append({
                        "date": str(current_date), "action": "CLOSE_IC",
                        "pnl": round(pnl, 2),
                    })
                else:
                    remaining.append(pos)

            self.positions = remaining

            # 日记录（sigma字段保留，记录纯HV供外部分析）
            pos_mv = sum(self._estimate_position_value(p, S, iv_est, current_date)
                         for p in self.positions)
            total_v = self.cash + pos_mv
            self.daily_records.append({
                "date": current_date,
                "total_value": total_v,
                "sigma": round(hv20, 4),   # 存纯HV，与外部工具口径一致
            })

        final_v = self.daily_records[-1]["total_value"] if self.daily_records else self.initial_capital
        years = (df["date"].iloc[-1] - df["date"].iloc[0]).days / 365.0 if hasattr(df["date"].iloc[-1], '__sub__') else 16.0

        total_ret = (final_v - self.initial_capital) / self.initial_capital * 100
        ann_ret   = ((1 + total_ret / 100) ** (1 / max(years, 0.1)) - 1) * 100

        tv = pd.Series([r["total_value"] for r in self.daily_records])
        peak = tv.cummax()
        max_dd = ((tv - peak) / peak * 100).min()
        dr = tv.pct_change().dropna()
        rf_d = RISK_FREE / 252
        sharpe = round((dr - rf_d).mean() / (dr - rf_d).std() * math.sqrt(252), 2) if dr.std() > 1e-10 else 0

        return {
            "final": round(final_v, 0),
            "ann_ret": round(ann_ret, 2),
            "max_dd": round(max_dd, 2),
            "sharpe": sharpe,
            "years": round(years, 1),
        }


# ═══════════════════════════════════════════════════════════════════
# Layer 2: VIX Spike Straddle
# ═══════════════════════════════════════════════════════════════════
class StraddleLayer:
    """
    监测vol spike，买入ATM跨式期权对冲IC尾部风险，同时获取额外收益。
    使用QQQ的HV20作为VIX代理。
    """

    def __init__(self, budget: float, qqq_df: pd.DataFrame):
        self.total_budget   = budget
        self.remaining      = budget
        self.positions: List[Dict] = []
        self.daily_records: List[Dict] = []
        self._last_trigger_date: Optional[date] = None
        self._cooldown_days = 30     # 触发后30天内不重复触发

        prices = qqq_df["Close"].values
        dates  = qqq_df["date"].values

        # 预计算QQQ每日HV20和HV5（5日波动率用于捕捉spike）
        self.hv20_by_date: Dict[date, float] = {}
        self.hv5_by_date:  Dict[date, float] = {}
        for i in range(len(dates)):
            d = dates[i]
            if hasattr(d, 'date'): d = d.date()
            hv20 = historical_volatility(pd.Series(prices[max(0,i-20):i+1]), 20)
            hv5  = historical_volatility(pd.Series(prices[max(0,i-5):i+1]),  5)
            self.hv20_by_date[d] = hv20
            self.hv5_by_date[d]  = hv5

        self.qqq_price_by_date: Dict[date, float] = {}
        for _, row in qqq_df.iterrows():
            d = row["date"]
            if hasattr(d, 'date'): d = d.date()
            self.qqq_price_by_date[d] = float(row["Close"])

    def _bs_straddle_price(self, S: float, sigma: float, dte: int) -> float:
        """ATM跨式价格（Call + Put，均ATM）× 100股"""
        T = dte / 365.0
        r = RISK_FREE
        call_p = bs_option_price(S, S, T, r, sigma, "CALL")
        put_p  = bs_option_price(S, S, T, r, sigma, "PUT")
        return (call_p + put_p) * 100

    def _spike_triggered(self, current_date: date) -> bool:
        """检测vol spike：HV5突破0.35或HV20单周跳升40%"""
        hv20 = self.hv20_by_date.get(current_date, 0)
        hv5  = self.hv5_by_date.get(current_date, 0)

        # 冷却期检查
        if self._last_trigger_date:
            if (current_date - self._last_trigger_date).days < self._cooldown_days:
                return False

        # 条件1：HV5（短期波动）突破0.35
        if hv5 >= 0.35:
            return True

        # 条件2：HV20绝对值首次越过0.32（从低于0.25的基础）
        # 需要比较10天前的HV20
        ten_days_ago = current_date - timedelta(days=10)
        hv20_prev = None
        for delta in range(10, 16):
            d_prev = current_date - timedelta(days=delta)
            if d_prev in self.hv20_by_date:
                hv20_prev = self.hv20_by_date[d_prev]
                break

        if hv20_prev is not None and hv20_prev < 0.25 and hv20 >= STRADDLE_TRIGGER_HV_ABS:
            return True

        return False

    def update(self, current_date: date) -> float:
        """更新当日状态，返回当日持仓市值（相对初始预算的PnL）"""
        hv20 = self.hv20_by_date.get(current_date, 0.20)
        S    = self.qqq_price_by_date.get(current_date, None)
        if S is None:
            self.daily_records.append({"date": current_date, "pnl": 0})
            return 0.0

        # ── 检查现有持仓是否需要平仓 ──────────────────────────────
        remaining = []
        realized_pnl_today = 0.0
        for pos in self.positions:
            dte_left = (pos["expiry"] - current_date).days
            # 当前跨式价值
            current_val = self._bs_straddle_price(S, hv20 * 1.1, max(dte_left, 1))
            pnl_pct = (current_val - pos["cost"]) / pos["cost"]

            close = False
            reason = ""
            if pnl_pct >= STRADDLE_EXIT_PROFIT:
                close  = True
                reason = f"盈利{pnl_pct:.0%}"
            elif pnl_pct <= -STRADDLE_EXIT_LOSS:
                close  = True
                reason = f"止损{pnl_pct:.0%}"
            elif dte_left <= STRADDLE_EXIT_DTE:
                close  = True
                reason = f"DTE={dte_left}"

            if close:
                pnl = current_val - pos["cost"]
                self.remaining += pos["cost"] + pnl
                realized_pnl_today += pnl
                print(f"  📐 [{current_date}] Straddle平仓（{reason}），PnL=${pnl:+.0f}")
            else:
                pos["current_val"] = current_val
                remaining.append(pos)

        self.positions = remaining

        # ── 检查是否触发新的spike买入 ─────────────────────────────
        if (len(self.positions) < STRADDLE_MAX_CONCURRENT and
                self.remaining >= STRADDLE_BUDGET_PER_TRADE and
                self._spike_triggered(current_date)):

            # 用VIX spike时偏高的IV（HV20 × 1.15买入，模拟付出IV溢价）
            entry_sigma = max(hv20 * 1.15, 0.20)
            expiry = current_date + timedelta(days=STRADDLE_DTE)
            cost   = self._bs_straddle_price(S, entry_sigma, STRADDLE_DTE)
            # 实际预算约束
            contracts = max(1, int(STRADDLE_BUDGET_PER_TRADE / max(cost, 1)))
            contracts = min(contracts, 1)  # 限制最多1张（$500预算）
            total_cost = cost * contracts

            if self.remaining >= total_cost:
                self.remaining  -= total_cost
                self._last_trigger_date = current_date
                self.positions.append({
                    "open_date":   current_date,
                    "expiry":      expiry,
                    "strike":      S,
                    "cost":        total_cost,
                    "current_val": total_cost,
                    "contracts":   contracts,
                })
                print(f"  📐 [{current_date}] Straddle开仓 S={S:.0f}, "
                      f"DTE={STRADDLE_DTE}, IV={entry_sigma:.0%}, 成本=${total_cost:.0f}")

        # 当日持仓市值
        unrealized = sum(p["current_val"] - p["cost"] for p in self.positions)
        total_mv   = self.remaining + sum(p["current_val"] for p in self.positions)
        pnl_total  = total_mv - self.total_budget

        self.daily_records.append({
            "date":        current_date,
            "total_value": total_mv,
            "pnl":         pnl_total,
        })
        return total_mv


# ═══════════════════════════════════════════════════════════════════
# 主回测引擎
# ═══════════════════════════════════════════════════════════════════
def run_composite(leverage: float = 1.25,
                  use_straddle: bool = True,
                  ic_ratio: float = IC_RATIO,
                  use_variable_otm: bool = False,
                  iv_rank_min: float = 0.0,
                  put_otm: float = None,
                  call_otm: float = None,
                  vol_targeting: bool = False,
                  ib_hv_threshold: float = 0.0,
                  assets_config: list = None,
                  verbose: bool = True) -> dict:
    """
    运行复合策略回测。
    leverage      : 固定杠杆倍数（vol_targeting=False时使用）
                    vol_targeting=True时作为"参考HV=15%时的目标杠杆"
    ic_ratio      : IC占总资金比例（1.0=全仓）
    use_variable_otm: True=变动OTM
    iv_rank_min   : HV Rank最低门槛（0=不过滤）
    put_otm/call_otm: 非对称IC两侧OTM（None=对称）
    vol_targeting : True=波动率目标仓位管理（动态杠杆）
    """
    # 全仓IC时强制关闭Straddle
    if ic_ratio >= 1.0:
        use_straddle = False

    if put_otm and call_otm:
        otm_str = f"非对称P{put_otm:.1%}C{call_otm:.1%}"
    elif use_variable_otm:
        otm_str = "变动OTM"
    else:
        otm_str = "固定OTM"
    rank_str  = f" IVR>{iv_rank_min:.0%}" if iv_rank_min > 0 else ""
    ib_str    = f"+IB<{ib_hv_threshold:.0%}" if ib_hv_threshold > 0 else ""
    cfg = assets_config or ASSETS_CONFIG          # 支持传入 TLT 等自定义资产
    third_ticker = cfg[2]["ticker"].split(".")[1]  # GLD 或 TLT
    lev_str   = f"VolTgt(base{leverage:.1f}x)" if vol_targeting else f"{leverage:.2f}x"
    mode_str  = ("全仓IC" if ic_ratio >= 1.0 else f"IC{ic_ratio:.0%}+现金") + f" {otm_str}{ib_str}{rank_str}"
    print(f"\n{'='*70}")
    print(f"  🏗️  复合策略回测  |  本金${TOTAL_CAPITAL:,}  |  杠杆={lev_str}  |"
          f"  模式={mode_str} [{third_ticker}]  Straddle={'开启' if use_straddle else '关闭'}")
    print(f"{'='*70}")

    # ── 拉取数据 ─────────────────────────────────────────────────
    print("\n📥 拉取历史K线...")
    dfs = {}
    for a in cfg:
        t = a["ticker"]
        print(f"   {t}...", end="", flush=True)
        df = fetch_futu_kline(t, START, END)
        if df is None or df.empty:
            print(f" ❌ 失败")
            return {}
        dfs[t] = df
        print(f" ✅ {len(df)}条")

    qqq_df = dfs["US.QQQ"]

    # ── Layer 3: Cash（先算，固定收益）──────────────────────────
    cash_capital  = TOTAL_CAPITAL * max(0.0, 1.0 - ic_ratio - (STRADDLE_RATIO if use_straddle else 0.0))
    years_total   = (pd.to_datetime(END) - pd.to_datetime(START)).days / 365.0

    # ── Layer 2: Straddle ──────────────────────────────────────
    straddle_budget = TOTAL_CAPITAL * STRADDLE_RATIO if use_straddle else 0.0
    straddle_layer  = StraddleLayer(straddle_budget, qqq_df) if use_straddle else None

    # ── Layer 1: IC核心 ─────────────────────────────────────────
    ic_real_capital = TOTAL_CAPITAL * ic_ratio                  # 实际投入IC的资本
    ic_notional     = ic_real_capital * leverage                # 名义资本（含杠杆）
    borrowed        = ic_real_capital * (leverage - 1)          # 借款
    daily_interest  = MARGIN_RATE / 252 * borrowed              # 每日融资成本

    ic_capitals = {
        a["ticker"]: ic_notional * a["capital_ratio"]
        for a in cfg
    }

    print(f"\n💰 资金分配:")
    print(f"   IC核心: ${ic_real_capital:,.0f} × {leverage:.2f}x = ${ic_notional:,.0f} 名义")
    print(f"   Straddle预算: ${straddle_budget:,.0f}")
    print(f"   现金储备: ${cash_capital:,.0f} @ {RISK_FREE:.0%}/年")
    if borrowed > 0:
        print(f"   融资成本: ${borrowed:,.0f} × {MARGIN_RATE:.1%}/年 = ${daily_interest*252:,.0f}/年")

    print("\n🔄 运行IC回测...")
    ic_daily_by_asset = {}
    ic_sigma_by_date  = {}   # 记录QQQ sigma用于杠杆控制

    for a in cfg:
        ticker = a["ticker"]
        capital = ic_capitals[ticker]
        print(f"   {ticker} (${capital:,.0f})...", end="", flush=True)
        bt = EnhancedICBacktester(
            ticker=ticker,
            initial_capital=capital,
            otm_distance=0.05,
            wing_width=0.09,                    # Scenario C 最优: Wing=9%
            dte=45,                             # Scenario C 最优: DTE=45
            max_groups=a["max_groups"],
            cooldown_days=5,
            stop_loss_pct=0.05,
            stop_loss_buffer=1.5,
            early_close_days=2,
            entry_mode="pre_expiry",
            entry_days_before_expiry=45,        # Scenario C 最优: DTE=45
            vix_hard_stop_hv=VIX_HARD_STOP_HV,
            vix_cooldown_hv=VIX_COOLDOWN_HV,
            use_variable_otm=use_variable_otm,
            iv_rank_min=iv_rank_min,
            put_otm=put_otm,
            call_otm=call_otm,
            ib_hv_threshold=ib_hv_threshold,
        )
        bt.run(dfs[ticker], save_prefix=f"cmp_{ticker.split('.')[1]}")
        daily = pd.DataFrame(bt.daily_records)[["date", "total_value", "sigma"]].copy()
        daily["date"] = pd.to_datetime(daily["date"])
        daily = daily.set_index("date")
        ic_daily_by_asset[ticker] = daily
        print(" ✅")

        if ticker == "US.QQQ":
            for _, row in daily.iterrows():
                d = row.name
                if hasattr(d, 'date'): d = d.date()
                ic_sigma_by_date[d] = row["sigma"]

    # ── 合并IC每日净值 ────────────────────────────────────────────
    combined_ic = None
    for ticker, daily in ic_daily_by_asset.items():
        renamed = daily[["total_value"]].rename(columns={"total_value": ticker})
        combined_ic = renamed if combined_ic is None else combined_ic.join(renamed, how="inner")

    ic_portfolio = sum(combined_ic[a["ticker"]] for a in cfg)

    # ── 应用杠杆（固定 or Vol Targeting）────────────────────────
    equity_ic    = ic_real_capital
    equity_curve = []
    base_ret     = ic_portfolio.pct_change().fillna(0)

    dates_list = ic_portfolio.index.tolist()
    for i, dt in enumerate(dates_list):
        d = dt.date() if hasattr(dt, 'date') else dt
        sigma_today = ic_sigma_by_date.get(d, VOL_TARGET_BASE_HV)

        if vol_targeting:
            # 动态杠杆：leverage 参数作为 HV20_BASE 时的目标杠杆
            # eff_lev = leverage × (HV20_BASE / HV20_today)，夹在[0.5, 3.0]
            raw_lev = leverage * (VOL_TARGET_BASE_HV / max(sigma_today, 0.05))
            eff_lev = min(max(raw_lev, VOL_TARGET_MIN_LEV), VOL_TARGET_MAX_LEV)
            # VIX硬止损触发时降到最低仓位
            if sigma_today >= VIX_HARD_STOP_HV:
                eff_lev = VOL_TARGET_MIN_LEV
        else:
            # 固定杠杆：高波时降至1.0x
            eff_lev = 1.0 if (sigma_today > VIX_NO_LEVERAGE_HV) else leverage

        eff_borrowed = ic_real_capital * max(eff_lev - 1, 0)
        eff_interest = MARGIN_RATE / 252 * eff_borrowed

        ret = base_ret.iloc[i]
        equity_ic = equity_ic * (1 + ret * eff_lev) - eff_interest
        equity_ic = max(equity_ic, 0)
        equity_curve.append((dt, equity_ic))

    ic_equity = pd.Series(dict(equity_curve))

    # ── 组合Straddle层 ────────────────────────────────────────────
    straddle_daily_values = {}
    if use_straddle:
        print("\n📐 运行Straddle层...")
        for dt in dates_list:
            d = dt.date() if hasattr(dt, 'date') else dt
            val = straddle_layer.update(d)
            straddle_daily_values[dt] = val
        straddle_series = pd.Series(straddle_daily_values)
    else:
        straddle_series = pd.Series(
            {dt: straddle_budget for dt in dates_list})

    # ── 组合Cash层 ────────────────────────────────────────────────
    cash_series = pd.Series(
        {dt: cash_capital * (1 + RISK_FREE) ** (i / 252)
         for i, dt in enumerate(dates_list)}
    )

    # ── 总组合净值 ────────────────────────────────────────────────
    portfolio = ic_equity + straddle_series.reindex(ic_equity.index, fill_value=straddle_budget) \
              + cash_series.reindex(ic_equity.index, fill_value=cash_capital)

    # ── 计算统计指标 ──────────────────────────────────────────────
    final_v   = portfolio.iloc[-1]
    years     = (portfolio.index[-1] - portfolio.index[0]).days / 365.0
    total_ret = (final_v - TOTAL_CAPITAL) / TOTAL_CAPITAL * 100
    ann_ret   = ((1 + total_ret / 100) ** (1 / max(years, 0.1)) - 1) * 100

    peak  = portfolio.cummax()
    dd    = (portfolio - peak) / peak * 100
    max_dd = dd.min()

    dr    = portfolio.pct_change().dropna()
    rf_d  = RISK_FREE / 252
    sharpe = round((dr - rf_d).mean() / (dr - rf_d).std() * math.sqrt(252), 2) if dr.std() > 1e-10 else 0

    # ── 危机期专项分析 ────────────────────────────────────────────
    crises = {
        "2011 美债危机": ("2011-07-01", "2011-10-31"),
        "2015 中国崩盘": ("2015-08-01", "2015-10-31"),
        "2018 Q4 暴跌": ("2018-10-01", "2018-12-31"),
        "2020 COVID":   ("2020-02-15", "2020-04-30"),
        "2022 加息熊市":("2022-01-01", "2022-12-31"),
        "2025 贸易战":  ("2025-03-01", "2025-06-30"),
    }
    crisis_stats = {}
    portfolio.index = pd.to_datetime(portfolio.index)
    for name, (cs, ce) in crises.items():
        seg = portfolio[cs:ce]
        if len(seg) < 5:
            continue
        seg_peak = seg.cummax()
        seg_dd   = ((seg - seg_peak) / seg_peak * 100).min()
        seg_ret  = (seg.iloc[-1] - seg.iloc[0]) / seg.iloc[0] * 100
        crisis_stats[name] = {"ret": round(seg_ret, 2), "max_dd": round(seg_dd, 2)}

    result = {
        "label":       (f"{'全仓IC' if ic_ratio >= 1.0 else '复合策略'} "
                        f"{f'VolTgt(base{leverage:.1f}x)' if vol_targeting else f'{leverage:.2f}x'} "
                        f"{f'非对称P{put_otm:.0%}C{call_otm:.0%}' if put_otm else ('变OTM' if use_variable_otm else '固定OTM')}"
                        f"{f'+IB<{ib_hv_threshold:.0%}' if ib_hv_threshold > 0 else ''}"
                        f"{f'[{third_ticker}]' if third_ticker != 'GLD' else ''}"
                        f"{f' IVR>{iv_rank_min:.0%}' if iv_rank_min > 0 else ''}"
                        f"{' Straddle' if use_straddle else ''}").rstrip(),
        "final":       round(final_v, 0),
        "ann_ret":     round(ann_ret, 2),
        "max_dd":      round(max_dd, 2),
        "sharpe":      sharpe,
        "years":       round(years, 1),
        "total_ret":   round(total_ret, 2),
        "crises":      crisis_stats,
        "portfolio":   portfolio,
    }
    return result


# ═══════════════════════════════════════════════════════════════════
# 基准回测：配置D纯IC（无任何改动，用于对比）
# ═══════════════════════════════════════════════════════════════════
def run_baseline() -> dict:
    """运行配置D基准（沿用multi_asset_backtest逻辑）"""
    print(f"\n{'='*70}")
    print(f"  📊 基准回测：配置D纯IC（无杠杆，标准滑点0.3%）")
    print(f"{'='*70}")
    from multi_asset_backtest import run_single, calc_portfolio_stats, CAPITAL_TOTAL

    dfs = {}
    for a in ASSETS_CONFIG:
        t = a["ticker"]
        df = fetch_futu_kline(t, START, END)
        dfs[t] = df

    assets_cfg = [
        ("US.QQQ", 9_000, 2, "QQQ"),
        ("US.IWM", 3_000, 1, "IWM"),
        ("US.GLD", 3_000, 1, "GLD"),
    ]
    daily_by = {}
    caps     = {}
    for ticker, cap, grp, name in assets_cfg:
        r = run_single(ticker, cap, grp, name, dfs[ticker])
        daily_by[ticker] = r["daily"]
        caps[ticker]     = cap

    stats = calc_portfolio_stats(daily_by, caps, "配置D基准")
    stats["label"] = "配置D基准（1x，标准滑点0.3%）"

    # 危机期分析
    portfolio = stats["combined"]["portfolio"]
    portfolio.index = pd.to_datetime(portfolio.index)
    crises = {
        "2011 美债危机": ("2011-07-01", "2011-10-31"),
        "2015 中国崩盘": ("2015-08-01", "2015-10-31"),
        "2018 Q4 暴跌": ("2018-10-01", "2018-12-31"),
        "2020 COVID":   ("2020-02-15", "2020-04-30"),
        "2022 加息熊市":("2022-01-01", "2022-12-31"),
        "2025 贸易战":  ("2025-03-01", "2025-06-30"),
    }
    crisis_stats = {}
    for name, (cs, ce) in crises.items():
        seg = portfolio[cs:ce]
        if len(seg) < 5: continue
        seg_peak = seg.cummax()
        seg_dd   = ((seg - seg_peak) / seg_peak * 100).min()
        seg_ret  = (seg.iloc[-1] - seg.iloc[0]) / seg.iloc[0] * 100
        crisis_stats[name] = {"ret": round(seg_ret, 2), "max_dd": round(seg_dd, 2)}

    stats["crises"] = crisis_stats
    return stats


# ═══════════════════════════════════════════════════════════════════
# 输出对比报告
# ═══════════════════════════════════════════════════════════════════
def print_report(baseline: dict, results: List[dict]):
    all_results = [baseline] + results

    # ── 汇总表 ────────────────────────────────────────────────────
    print(f"\n\n{'='*95}")
    print(f"  📊 策略对比报告  |  $15,000初始资金  |  {START[:4]}-{END[:4]}")
    print(f"{'='*95}")
    hdr = f"  {'策略':<36} {'年化':>8} {'最大回撤':>10} {'夏普':>7} {'16年最终':>12} {'总收益':>8}"
    print(hdr)
    print("  " + "─" * 86)
    for r in all_results:
        ann  = r.get("ann_ret", 0)
        dd   = r.get("max_dd", 0)
        sh   = r.get("sharpe", 0)
        fin  = r.get("final", 0)
        tr   = r.get("total_ret", (fin - TOTAL_CAPITAL) / TOTAL_CAPITAL * 100)
        lbl  = r.get("label", "")
        flag = " ✅" if "基准" in lbl else " 🆕"
        print(f"  {lbl:<36} {ann:>7.2f}% {dd:>9.2f}% {sh:>7.2f} ${fin:>10,.0f} {tr:>7.1f}%{flag}")

    # ── 危机期：最大回撤 ──────────────────────────────────────────
    crisis_names = list(baseline.get("crises", {}).keys())
    col_w = 11

    print(f"\n{'='*95}")
    print(f"  🔍 危机期分析 ① — 最大回撤（越小越好）")
    print(f"{'='*95}")
    hdr2 = f"  {'策略':<32} " + "".join(f" {n[:9]:>{col_w}}" for n in crisis_names)
    print(hdr2)
    print("  " + "─" * (32 + (col_w + 1) * len(crisis_names)))
    for r in all_results:
        row = f"  {r.get('label',''):<32} "
        for name in crisis_names:
            cs = r.get("crises", {}).get(name, {})
            val = cs.get("max_dd", 0)
            row += f" {val:>+{col_w}.1f}%"
        print(row)

    # ── 危机期：期间总收益 ────────────────────────────────────────
    print(f"\n{'='*95}")
    print(f"  🔍 危机期分析 ② — 期间总收益（越高越好）")
    print(f"{'='*95}")
    print(hdr2)
    print("  " + "─" * (32 + (col_w + 1) * len(crisis_names)))
    for r in all_results:
        row = f"  {r.get('label',''):<32} "
        for name in crisis_names:
            cs = r.get("crises", {}).get(name, {})
            val = cs.get("ret", 0)
            row += f" {val:>+{col_w}.1f}%"
        print(row)

    print(f"\n  说明：")
    print(f"  ① 最大回撤 = 危机窗口内从峰值的最大跌幅")
    print(f"  ② 期间总收益 = 危机窗口首日→末日的总损益（正数表示整段仍盈利）\n")


# ═══════════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-straddle",  action="store_true")
    parser.add_argument("--no-leverage",  action="store_true")
    parser.add_argument("--leverage",     type=float, default=1.25)
    args = parser.parse_args()

    leverage = 1.0 if args.no_leverage else args.leverage

    # 基准
    baseline = run_baseline()

    # 复合策略变体
    results = []

    # ① 非对称P3.0%C6.0% W9% DTE45 2x — GLD版（Scenario C 972组最优，2026-04-11确认）
    r = run_composite(leverage=2.0, use_straddle=False, ic_ratio=1.0,
                      put_otm=0.030, call_otm=0.060)
    if r: results.append(r)

    # ② 非对称P3.0%C6.0% W9% DTE45 2x — TLT替换GLD
    r = run_composite(leverage=2.0, use_straddle=False, ic_ratio=1.0,
                      put_otm=0.030, call_otm=0.060,
                      assets_config=ASSETS_CONFIG_TLT)
    if r: results.append(r)

    print_report(baseline, results)


if __name__ == "__main__":
    main()
