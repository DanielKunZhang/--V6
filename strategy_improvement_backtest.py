#!/usr/bin/env python3
"""
策略优化对比回测脚本
对比当前基线策略 vs 4个改进方向：
  A. 基线（当前生产参数）
  B. 50% 止盈目标
  C. 非对称翼宽（Put宽 / Call窄）
  D. HV20 双边过滤（≥15% 才开仓）
  E. DTE45 + 21天提前平仓
  F. 组合最优（B+C+D+E）

数据：富途 API 拉取 QQQ 日K线（2010-2025，16年）
"""

import sys
import math
import calendar
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline, bs_option_price, historical_volatility

logging.basicConfig(level=logging.WARNING)


# ─────────────────────────────────────────────
#  美股标准期权到期日（每月第三个周五）
# ─────────────────────────────────────────────

def us_option_expiry_for_month(year: int, month: int) -> date:
    cal = calendar.monthcalendar(year, month)
    fridays = [week[4] for week in cal if week[4] != 0]
    if len(fridays) >= 3:
        return date(year, month, fridays[2])
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def get_us_option_expiries(start: date, end: date) -> List[date]:
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


# ─────────────────────────────────────────────
#  改进版 Iron Condor 回测器
# ─────────────────────────────────────────────

@dataclass
class ICPosition:
    sell_put_k: float
    buy_put_k: float
    sell_call_k: float
    buy_call_k: float
    net_credit: float      # 开仓时收到的净权利金
    max_credit: float      # 最大权利金（用于止盈计算）
    open_date: date
    expiration: date
    lot_size: int = 100


class ImprovedICBacktester:
    """
    改进版 Iron Condor 回测器

    新增参数：
        profit_target_pct:  止盈目标，如 0.5 表示收到50%权利金时平仓（0=不启用）
        put_wing:           PUT 翼宽（可与 call_wing 不同，实现非对称）
        call_wing:          CALL 翼宽
        min_hv20:           HV20 最低门槛，低于此不开仓（0=不启用）
        max_hv20:           HV20 最高门槛（默认0.25）
        early_close_dte:    提前平仓的剩余DTE（如21表示距到期还有21天时平仓）
    """

    LOT_SIZE = 100
    COMMISSION = 0.65       # 单张佣金 USD
    SLIPPAGE_PCT = 0.003    # 滑点
    RISK_FREE_RATE = 0.05

    def __init__(self,
                 ticker: str = "US.QQQ",
                 initial_capital: float = 15_000,
                 otm_distance: float = 0.05,
                 put_wing: float = 0.08,
                 call_wing: float = 0.08,
                 dte: int = 30,
                 max_groups: int = 2,
                 cooldown_days: int = 5,
                 early_close_dte: int = 2,    # 到期前 N 天提前平仓
                 stop_loss_pct: float = 0.05,
                 max_hv20: float = 0.25,
                 min_hv20: float = 0.0,       # 新增：最低HV门槛
                 profit_target_pct: float = 0.0,  # 新增：止盈目标（0=不启用）
                 label: str = "",
                 ):
        self.ticker = ticker
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.otm_distance = otm_distance
        self.put_wing = put_wing
        self.call_wing = call_wing
        self.dte = dte
        self.max_groups = max_groups
        self.cooldown_days = cooldown_days
        self.early_close_dte = early_close_dte
        self.stop_loss_pct = stop_loss_pct
        self.max_hv20 = max_hv20
        self.min_hv20 = min_hv20
        self.profit_target_pct = profit_target_pct
        self.label = label or f"OTM{otm_distance:.0%} PW{put_wing:.0%} CW{call_wing:.0%} DTE{dte} PT{profit_target_pct:.0%}"

        self.trades: List[Dict] = []
        self.daily_records: List[Dict] = []
        self.positions: List[ICPosition] = []
        self.peak_value = initial_capital
        self.stopped = False
        self._stop_date: Optional[date] = None
        self._last_opened_expiry: Optional[str] = None
        self._last_close_date: Optional[date] = None
        self._expiry_calendar: List[date] = []

    def _option_price(self, S, K, T_days, sigma, otype):
        T = max(T_days, 0.5) / 365.0
        per_share = bs_option_price(S, K, T, sigma, option_type=otype)
        per_share *= (1 - self.SLIPPAGE_PCT)
        return per_share * self.LOT_SIZE

    def _calc_ic_prices(self, S, sigma, dte):
        """计算 Iron Condor 的4条腿价格（支持非对称翼宽）"""
        sell_put_k  = round(S * (1 - self.otm_distance), 0)
        buy_put_k   = round(S * (1 - self.otm_distance - self.put_wing), 0)
        sell_call_k = round(S * (1 + self.otm_distance), 0)
        buy_call_k  = round(S * (1 + self.otm_distance + self.call_wing), 0)

        buy_put_k  = max(min(buy_put_k, sell_put_k - 1), 1)
        buy_call_k = max(buy_call_k, sell_call_k + 1)

        sp = self._option_price(S, sell_put_k,  dte, sigma, "PUT")
        bp = self._option_price(S, buy_put_k,   dte, sigma, "PUT")
        sc = self._option_price(S, sell_call_k, dte, sigma, "CALL")
        bc = self._option_price(S, buy_call_k,  dte, sigma, "CALL")

        gross = (sp + sc) - (bp + bc)
        net_credit = gross - self.COMMISSION * 4

        return sell_put_k, buy_put_k, sell_call_k, buy_call_k, net_credit

    def _position_value(self, pos: ICPosition, S, sigma, current_date):
        """估算持仓当前市值（正数=盈利，负数=亏损）"""
        days_left = max((pos.expiration - current_date).days, 0.5)
        sp = self._option_price(S, pos.sell_put_k,  days_left, sigma, "PUT")
        bp = self._option_price(S, pos.buy_put_k,   days_left, sigma, "PUT")
        sc = self._option_price(S, pos.sell_call_k, days_left, sigma, "CALL")
        bc = self._option_price(S, pos.buy_call_k,  days_left, sigma, "CALL")
        # 持仓价值 = 开仓时收到的净权利金 - 当前平仓需付出的成本
        return pos.net_credit - (sp + sc - bp - bc)

    def run(self, df: pd.DataFrame) -> dict:
        print(f"\n{'─'*70}")
        print(f"  [{self.label}]")
        print(f"  OTM={self.otm_distance:.0%}  PutWing={self.put_wing:.0%}  CallWing={self.call_wing:.0%}")
        print(f"  DTE={self.dte}  EarlyClose={self.early_close_dte}d  PT={self.profit_target_pct:.0%}  "
              f"HV20=[{self.min_hv20:.0%},{self.max_hv20:.0%}]")
        print(f"{'─'*70}")

        prices = df["Close"]
        start_d = df["date"].iloc[0]
        end_d   = df["date"].iloc[-1]
        if hasattr(start_d, 'date'): start_d = start_d.date()
        if hasattr(end_d, 'date'):   end_d   = end_d.date()
        self._expiry_calendar = get_us_option_expiries(start_d, end_d + timedelta(days=60))

        for i, row in df.iterrows():
            current_date: date = row["date"]
            S: float = float(row["Close"])

            past_prices = prices.iloc[max(0, i - 20): i + 1]
            sigma = historical_volatility(past_prices, 20)

            # ── 冷却恢复 ──
            if self.stopped and self._stop_date:
                if (current_date - self._stop_date).days >= self.cooldown_days:
                    self.stopped = False
                    self._stop_date = None

            # ── 开仓 ──
            if len(self.positions) == 0 and not self.stopped:
                can_open = True
                if self.cooldown_days > 0 and self._last_close_date:
                    if (current_date - self._last_close_date).days < self.cooldown_days:
                        can_open = False

                if can_open:
                    # 找到下一个到期日
                    for exp in self._expiry_calendar:
                        if exp >= current_date:
                            actual_dte = (exp - current_date).days
                            target_expiry = exp
                            break
                    else:
                        actual_dte, target_expiry = self.dte, current_date + timedelta(days=self.dte)

                    # DTE 窗口过滤（只在 DTE <= 目标DTE 的区间内开仓）
                    if actual_dte > self.dte or actual_dte < 7:
                        can_open = False

                    if can_open:
                        # HV20 双边过滤
                        if sigma > self.max_hv20:
                            can_open = False
                        elif self.min_hv20 > 0 and sigma < self.min_hv20:
                            can_open = False

                    if can_open:
                        sp_k, bp_k, sc_k, bc_k, credit = self._calc_ic_prices(S, sigma, actual_dte)
                        exp_str = str(target_expiry)

                        if credit >= 30.0 and self._last_opened_expiry != exp_str:
                            self._last_opened_expiry = exp_str
                            self._last_close_date = None

                            for _ in range(self.max_groups):
                                self.cash += credit
                                self.positions.append(ICPosition(
                                    sell_put_k=sp_k, buy_put_k=bp_k,
                                    sell_call_k=sc_k, buy_call_k=bc_k,
                                    net_credit=credit, max_credit=credit,
                                    open_date=current_date, expiration=target_expiry,
                                ))
                                self.trades.append({
                                    "date": str(current_date), "action": "OPEN",
                                    "price": S, "sigma": round(sigma, 3),
                                    "credit": round(credit, 2),
                                    "expiration": exp_str, "dte": actual_dte,
                                })

            # ── 持仓管理 ──
            if self.positions:
                remaining = []
                for pos in self.positions:
                    pv = self._position_value(pos, S, sigma, current_date)
                    total_v = self.cash + pv

                    if total_v > self.peak_value:
                        self.peak_value = total_v

                    # 总回撤止损
                    dd = (total_v - self.peak_value) / self.peak_value
                    if dd <= -self.stop_loss_pct and not self.stopped:
                        self.stopped = True
                        self._stop_date = current_date
                        self.cash += pv  # 按市价止损
                        self.trades.append({
                            "date": str(current_date), "action": "STOP_LOSS",
                            "pnl": round(pv, 2), "price": S,
                        })
                        self._last_close_date = current_date
                        continue

                    days_left = (pos.expiration - current_date).days

                    # ── 止盈目标（新功能）──
                    if self.profit_target_pct > 0 and days_left > self.early_close_dte:
                        profit_ratio = pv / pos.max_credit
                        if profit_ratio >= self.profit_target_pct:
                            self.cash += pv
                            self.trades.append({
                                "date": str(current_date), "action": "PROFIT_TARGET",
                                "pnl": round(pv, 2), "profit_ratio": round(profit_ratio, 3),
                                "days_left": days_left, "price": S,
                            })
                            self._last_close_date = current_date
                            continue

                    # ── 破位止损（价格突破卖出行权价）──
                    if S <= pos.sell_put_k or S >= pos.sell_call_k:
                        self.cash += pv
                        self.trades.append({
                            "date": str(current_date), "action": "BREACH_CLOSE",
                            "pnl": round(pv, 2), "price": S,
                            "side": "PUT" if S <= pos.sell_put_k else "CALL",
                        })
                        self._last_close_date = current_date
                        continue

                    # ── 提前平仓（距到期 <= early_close_dte 天）──
                    if days_left <= self.early_close_dte:
                        self.cash += pv
                        self.trades.append({
                            "date": str(current_date), "action": "EARLY_CLOSE",
                            "pnl": round(pv, 2), "price": S, "days_left": days_left,
                        })
                        self._last_close_date = current_date
                        continue

                    # ── 到期结算 ──
                    if current_date >= pos.expiration:
                        bp_k, sp_k = pos.buy_put_k, pos.sell_put_k
                        bc_k, sc_k = pos.buy_call_k, pos.sell_call_k
                        if bp_k < S < sc_k:
                            pnl = pos.net_credit
                            result = "WIN"
                        elif S <= bp_k:
                            loss = (sp_k - bp_k) * self.LOT_SIZE - pos.net_credit
                            pnl = -loss
                            result = "PUT_ASSIGNED"
                        elif S >= bc_k:
                            loss = (bc_k - sc_k) * self.LOT_SIZE - pos.net_credit
                            pnl = -loss
                            result = "CALL_ASSIGNED"
                        else:
                            pnl = pos.net_credit * 0.1  # 部分损耗
                            result = "PARTIAL"
                        self.cash += pnl
                        self.trades.append({
                            "date": str(current_date), "action": "EXPIRED",
                            "result": result, "pnl": round(pnl, 2), "price": S,
                        })
                        self._last_close_date = current_date
                        continue

                    remaining.append(pos)
                self.positions = remaining

            # ── 每日记录 ──
            mv = sum(self._position_value(p, S, sigma, current_date) for p in self.positions)
            tv = self.cash + mv
            self.daily_records.append({
                "date": current_date,
                "price": S,
                "sigma": round(sigma, 4),
                "total_value": round(tv, 2),
            })

        return self._report()

    def _report(self) -> dict:
        df = pd.DataFrame(self.daily_records)
        tf = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

        final_v = df["total_value"].iloc[-1]
        total_ret = (final_v - self.initial_capital) / self.initial_capital * 100
        start_dt, end_dt = df["date"].iloc[0], df["date"].iloc[-1]
        years = (end_dt - start_dt).days / 365.0
        ann_ret = ((1 + total_ret / 100) ** (1 / max(years, 0.1)) - 1) * 100

        df["peak"] = df["total_value"].cummax()
        df["dd"] = (df["total_value"] - df["peak"]) / df["peak"] * 100
        max_dd = df["dd"].min()
        max_dd_date = df.loc[df["dd"].idxmin(), "date"]

        # 夏普
        df["dr"] = df["total_value"].pct_change()
        dr = df["dr"].dropna()
        rf_d = self.RISK_FREE_RATE / 252
        sharpe = round((dr - rf_d).mean() / (dr - rf_d).std() * math.sqrt(252), 2) if dr.std() > 1e-10 else 0

        # 交易统计
        n_open = n_win = n_loss = n_pt = n_breach = n_early = 0
        avg_credit = 0.0
        hold_days_list = []

        if not tf.empty:
            opens = tf[tf.action == "OPEN"]
            n_open = len(opens)
            avg_credit = opens["credit"].mean() if n_open > 0 else 0

            wins  = tf[tf.action == "EXPIRED"]
            if not wins.empty:
                n_win  = (wins["pnl"] > 0).sum()
                n_loss = (wins["pnl"] <= 0).sum()

            n_pt     = (tf.action == "PROFIT_TARGET").sum()
            n_breach = (tf.action == "BREACH_CLOSE").sum()
            n_early  = (tf.action == "EARLY_CLOSE").sum()

            # 平均持仓天数（从 OPEN 到 CLOSE 配对）
            open_dates = opens["date"].tolist()
            close_actions = tf[tf.action.isin(["PROFIT_TARGET","BREACH_CLOSE","EARLY_CLOSE","EXPIRED","STOP_LOSS"])]
            close_dates = close_actions["date"].tolist()
            pairs = min(len(open_dates), len(close_dates))
            for k in range(pairs):
                od = pd.to_datetime(open_dates[k]).date() if isinstance(open_dates[k], str) else open_dates[k]
                cd = pd.to_datetime(close_dates[k]).date() if isinstance(close_dates[k], str) else close_dates[k]
                hold_days_list.append((cd - od).days)

        n_closed = n_win + n_loss + n_pt + n_breach + n_early
        all_closed_pnl = tf[tf.action.isin(["PROFIT_TARGET","BREACH_CLOSE","EARLY_CLOSE","EXPIRED"])]["pnl"] if not tf.empty else pd.Series()
        win_rate = (all_closed_pnl > 0).sum() / max(len(all_closed_pnl), 1) * 100

        avg_hold = sum(hold_days_list) / max(len(hold_days_list), 1)

        return {
            "label": self.label,
            "ann_return": round(ann_ret, 2),
            "total_return": round(total_ret, 2),
            "max_dd": round(max_dd, 2),
            "max_dd_date": str(max_dd_date),
            "sharpe": sharpe,
            "final_value": round(final_v, 0),
            "n_open": n_open,
            "n_win": n_win,
            "n_loss": n_loss,
            "n_pt": n_pt,
            "n_breach": n_breach,
            "n_early": n_early,
            "win_rate": round(win_rate, 1),
            "avg_credit": round(avg_credit, 0),
            "avg_hold_days": round(avg_hold, 1),
            "years": round(years, 1),
            "profit_target_pct": self.profit_target_pct,
            "put_wing": self.put_wing,
            "call_wing": self.call_wing,
            "min_hv20": self.min_hv20,
            "max_hv20": self.max_hv20,
            "early_close_dte": self.early_close_dte,
            "dte": self.dte,
        }


# ─────────────────────────────────────────────
#  主对比实验
# ─────────────────────────────────────────────

CONFIGS = [
    # ── A. 基线（当前生产配置）──
    {
        "label": "A-基线(当前生产)",
        "otm_distance": 0.05, "put_wing": 0.08, "call_wing": 0.08,
        "dte": 30, "early_close_dte": 2,
        "profit_target_pct": 0.0, "min_hv20": 0.0, "max_hv20": 0.25,
        "max_groups": 2, "cooldown_days": 5,
    },
    # ── B. 50%止盈目标 ──
    {
        "label": "B-止盈50%",
        "otm_distance": 0.05, "put_wing": 0.08, "call_wing": 0.08,
        "dte": 30, "early_close_dte": 2,
        "profit_target_pct": 0.50, "min_hv20": 0.0, "max_hv20": 0.25,
        "max_groups": 2, "cooldown_days": 5,
    },
    # ── B2. 25%止盈目标（更激进回收）──
    {
        "label": "B2-止盈25%",
        "otm_distance": 0.05, "put_wing": 0.08, "call_wing": 0.08,
        "dte": 30, "early_close_dte": 2,
        "profit_target_pct": 0.25, "min_hv20": 0.0, "max_hv20": 0.25,
        "max_groups": 2, "cooldown_days": 5,
    },
    # ── C. 非对称翼宽（Put宽/Call窄）──
    {
        "label": "C-非对称翼宽(P12%C6%)",
        "otm_distance": 0.05, "put_wing": 0.12, "call_wing": 0.06,
        "dte": 30, "early_close_dte": 2,
        "profit_target_pct": 0.0, "min_hv20": 0.0, "max_hv20": 0.25,
        "max_groups": 2, "cooldown_days": 5,
    },
    # ── D. HV20 双边过滤（15%≤HV≤25%）──
    {
        "label": "D-HV双边过滤(15-25%)",
        "otm_distance": 0.05, "put_wing": 0.08, "call_wing": 0.08,
        "dte": 30, "early_close_dte": 2,
        "profit_target_pct": 0.0, "min_hv20": 0.15, "max_hv20": 0.25,
        "max_groups": 2, "cooldown_days": 5,
    },
    # ── E. DTE45 + 21天提前平仓 ──
    {
        "label": "E-DTE45提前21天平仓",
        "otm_distance": 0.05, "put_wing": 0.08, "call_wing": 0.08,
        "dte": 45, "early_close_dte": 21,
        "profit_target_pct": 0.0, "min_hv20": 0.0, "max_hv20": 0.25,
        "max_groups": 2, "cooldown_days": 5,
    },
    # ── E2. DTE45 + 50%止盈 ──
    {
        "label": "E2-DTE45+止盈50%",
        "otm_distance": 0.05, "put_wing": 0.08, "call_wing": 0.08,
        "dte": 45, "early_close_dte": 5,
        "profit_target_pct": 0.50, "min_hv20": 0.0, "max_hv20": 0.25,
        "max_groups": 2, "cooldown_days": 5,
    },
    # ── F. 组合最优（B+C+D）──
    {
        "label": "F-组合(止盈50%+非对称+双边HV)",
        "otm_distance": 0.05, "put_wing": 0.12, "call_wing": 0.06,
        "dte": 30, "early_close_dte": 2,
        "profit_target_pct": 0.50, "min_hv20": 0.15, "max_hv20": 0.25,
        "max_groups": 2, "cooldown_days": 5,
    },
    # ── F2. 完全组合（B+C+D+E）──
    {
        "label": "F2-完全组合(止盈50%+非对称+双边HV+DTE45)",
        "otm_distance": 0.05, "put_wing": 0.12, "call_wing": 0.06,
        "dte": 45, "early_close_dte": 5,
        "profit_target_pct": 0.50, "min_hv20": 0.15, "max_hv20": 0.25,
        "max_groups": 2, "cooldown_days": 5,
    },
]


def print_summary_table(results: List[dict]):
    print(f"\n\n{'='*110}")
    print(f"  📊 策略优化对比汇总  —  QQQ 2010-2025  ×  $15,000 初始资金")
    print(f"{'='*110}")
    hdr = (f"{'配置':<42}  {'年化':>7}  {'最大回撤':>9}  {'夏普':>6}  "
           f"{'开仓':>5}  {'胜率':>6}  {'均天':>5}  {'止盈触发':>8}  {'最终资金':>10}")
    print(hdr)
    print("─" * 110)

    baseline = next((r for r in results if r["label"].startswith("A")), None)

    for r in sorted(results, key=lambda x: x["ann_return"], reverse=True):
        diff = f"(+{r['ann_return']-baseline['ann_return']:.1f}%)" if baseline and r != baseline else ""
        ann_str = f"{r['ann_return']:+.2f}%"
        dd_str  = f"{r['max_dd']:.2f}%"
        pt_str  = f"{r['n_pt']}次" if r["profit_target_pct"] > 0 else "─"

        # 标注最优
        marker = " ★" if r["ann_return"] == max(x["ann_return"] for x in results) else "  "
        print(f"{marker}{r['label']:<42}  {ann_str:>7}  {dd_str:>9}  "
              f"{r['sharpe']:>6.2f}  {r['n_open']:>4}次  {r['win_rate']:>5.1f}%  "
              f"{r['avg_hold_days']:>4.0f}d  {pt_str:>8}  ${r['final_value']:>9,.0f}  {diff}")

    print("─" * 110)
    if baseline:
        print(f"  基线: A-基线  年化={baseline['ann_return']:+.2f}%  回撤={baseline['max_dd']:.2f}%  夏普={baseline['sharpe']:.2f}")
    print(f"{'='*110}")


def print_improvement_analysis(results: List[dict]):
    """分析每个改进维度的净贡献"""
    r = {x["label"]: x for x in results}
    base_key = "A-基线(当前生产)"
    if base_key not in r:
        return

    base = r[base_key]
    print(f"\n\n{'='*70}")
    print("  🔍 各改进维度净贡献分析")
    print(f"{'='*70}")
    print(f"  基线: 年化{base['ann_return']:+.2f}%  回撤{base['max_dd']:.2f}%  夏普{base['sharpe']:.2f}\n")

    improvements = [
        ("B-止盈50%",               "↪ 50%止盈目标"),
        ("B2-止盈25%",              "↪ 25%止盈目标"),
        ("C-非对称翼宽(P12%C6%)",   "↪ 非对称翼宽 (Put宽/Call窄)"),
        ("D-HV双边过滤(15-25%)",    "↪ HV20双边过滤 (≥15%)"),
        ("E-DTE45提前21天平仓",     "↪ DTE45+21天提前平仓"),
        ("E2-DTE45+止盈50%",        "↪ DTE45+50%止盈"),
        ("F-组合(止盈50%+非对称+双边HV)", "↪ 组合B+C+D"),
        ("F2-完全组合(止盈50%+非对称+双边HV+DTE45)", "↪ 完全组合B+C+D+E"),
    ]

    for key, desc in improvements:
        if key in r:
            x = r[key]
            ann_d  = x["ann_return"]  - base["ann_return"]
            dd_d   = x["max_dd"]      - base["max_dd"]
            sh_d   = x["sharpe"]      - base["sharpe"]
            ann_s  = f"{ann_d:+.2f}%"
            dd_s   = f"{dd_d:+.2f}%"
            sh_s   = f"{sh_d:+.2f}"
            flag = "✅" if ann_d > 0.5 or sh_d > 0.1 else ("⚠️" if ann_d < -0.5 else "〰️")
            print(f"  {flag} {desc:<42} 年化{ann_s:>8}  回撤{dd_s:>8}  夏普{sh_s:>6}")


def main():
    print("=" * 70)
    print("  🦅 QQQ Iron Condor 策略优化对比回测")
    print("  数据来源：富途 OpenD API（2010-2025，16年）")
    print("=" * 70)

    # 拉取历史数据（一次性，所有配置共用）
    df = fetch_futu_kline("US.QQQ", "2010-01-01", "2025-12-31")
    if df is None or df.empty:
        print("❌ 无法获取数据，请确认富途 OpenD 已启动")
        sys.exit(1)

    print(f"\n✅ 数据: {len(df)} 个交易日  {df['date'].iloc[0]} → {df['date'].iloc[-1]}")
    print(f"   QQQ 价格区间: ${df['Close'].min():.0f} ~ ${df['Close'].max():.0f}")

    results = []
    for cfg in CONFIGS:
        bt = ImprovedICBacktester(
            ticker="US.QQQ",
            initial_capital=15_000,
            **cfg
        )
        r = bt.run(df)
        results.append(r)

    # 汇总表
    print_summary_table(results)

    # 维度分析
    print_improvement_analysis(results)

    # 保存 JSON 结果
    out_dir = Path(__file__).parent / "backtest_results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "strategy_improvements.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)
    print(f"\n📁 详细结果已保存: {out_path}")


if __name__ == "__main__":
    main()
