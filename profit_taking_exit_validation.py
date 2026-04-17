#!/usr/bin/env python3
"""
止盈退出规则专项回测（Futu/OpenD 实盘成本口径）
================================================

比较：
  A. 当前基准：整组 50% 止盈
  B. 单卖方腿 80% 止盈（partial model）
  C. 单侧价差 80% 止盈（partial model）
  D. 整组 80% 止盈

说明：
  - A/D 使用当前 EnhancedICBacktester 的整组止盈逻辑。
  - B/C 使用专项部分平仓模型，用于判断方向，不直接作为实盘参数。
  - 成本口径沿用 live_cost_validation.py：
      Futu/OpenD 数据、动态滑点、手续费、融资利息、动态组数资金累积。
"""

from __future__ import annotations

import argparse
import io
import math
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline, historical_volatility
from composite_backtest import EnhancedICBacktester, SLIP_HARD_STOP, VIX_COOLDOWN_HV, VIX_HARD_STOP_HV
from dynamic_composite_backtest import ASSETS as NOMINAL_ASSETS, IC_PARAMS
from iron_condor_us import get_next_expiry, get_us_option_expiries
from live_cost_validation import (
    CANDIDATE_YEARS,
    CLOSE_ACTIONS,
    COMMISSION_PER_CONTRACT,
    CONTRACTS_PER_GROUP,
    DELEVERAGE_HV,
    LEVERAGE,
    MARGIN_RATE,
    REAL_CAPITAL,
    RISK_FREE,
    build_actual_equity_curve,
    build_commission_series,
    calc_curve_stats,
    calc_yearly_breakdown,
)


LIVE_ASSETS = [
    {
        "ticker": asset["ticker"],
        "name": asset["name"],
        "capital": asset["capital"] / LEVERAGE,
        "base_groups": asset["base_groups"],
    }
    for asset in NOMINAL_ASSETS
]

SCENARIOS = [
    {"id": "GROUP50", "label": "当前基准：整组50%止盈", "mode": "group", "target": 0.50},
    {"id": "SHORT80", "label": "单卖方腿80%止盈", "mode": "short_leg", "target": 0.80},
    {"id": "SIDE80", "label": "单侧价差80%止盈", "mode": "side_spread", "target": 0.80},
    {"id": "GROUP80", "label": "整组80%止盈", "mode": "group", "target": 0.80},
]


@dataclass
class PartialICPosition:
    sell_put_k: float
    buy_put_k: float
    sell_call_k: float
    buy_call_k: float
    net_credit: float
    open_date: date
    expiration: date
    entry_prices: Dict[str, float]
    closed: Dict[str, bool]


class PartialExitICBacktester(EnhancedICBacktester):
    """支持卖方单腿/单侧价差提前止盈的专项回测器。"""

    def __init__(self, partial_mode: str, partial_target_pct: float, **kwargs):
        kwargs["profit_target_pct"] = 0.0
        super().__init__(**kwargs)
        self.partial_mode = partial_mode
        self.partial_target_pct = partial_target_pct
        self.partial_exit_count = 0

    def _leg_prices(self, pos: PartialICPosition, S: float, sigma: float, current_date: date) -> Dict[str, float]:
        days_left = max((pos.expiration - current_date).days, 1)
        return {
            "sp": self.get_option_price_usd(S, pos.sell_put_k, days_left, sigma, "PUT"),
            "bp": self.get_option_price_usd(S, pos.buy_put_k, days_left, sigma, "PUT"),
            "sc": self.get_option_price_usd(S, pos.sell_call_k, days_left, sigma, "CALL"),
            "bc": self.get_option_price_usd(S, pos.buy_call_k, days_left, sigma, "CALL"),
        }

    def _active_close_cost(self, pos: PartialICPosition, prices: Dict[str, float]) -> float:
        cost = 0.0
        if not pos.closed.get("sp", False):
            cost += prices["sp"]
        if not pos.closed.get("sc", False):
            cost += prices["sc"]
        if not pos.closed.get("bp", False):
            cost -= prices["bp"]
        if not pos.closed.get("bc", False):
            cost -= prices["bc"]
        return cost

    def _active_entry_credit(self, pos: PartialICPosition) -> float:
        p = pos.entry_prices
        credit = 0.0
        if not pos.closed.get("sp", False):
            credit += p["sp"]
        if not pos.closed.get("sc", False):
            credit += p["sc"]
        if not pos.closed.get("bp", False):
            credit -= p["bp"]
        if not pos.closed.get("bc", False):
            credit -= p["bc"]
        return credit

    def _estimate_position_value(self, pos: PartialICPosition, S: float, sigma: float, current_date: date) -> float:
        prices = self._leg_prices(pos, S, sigma, current_date)
        return self._active_entry_credit(pos) - self._active_close_cost(pos, prices)

    def _close_active_position_with_slippage(
        self,
        pos: PartialICPosition,
        S: float,
        sigma: float,
        current_date: date,
        extra_slip: float = 0.0,
    ) -> float:
        prices = self._leg_prices(pos, S, sigma, current_date)
        close_cost = self._active_close_cost(pos, prices)
        active_credit = self._active_entry_credit(pos)
        loss = close_cost - active_credit
        loss *= 1 + self._get_dynamic_slippage(sigma) + extra_slip
        return -loss

    def _is_fully_closed(self, pos: PartialICPosition) -> bool:
        return all(pos.closed.get(k, False) for k in ("sp", "bp", "sc", "bc"))

    def _maybe_partial_take_profit(
        self,
        pos: PartialICPosition,
        S: float,
        sigma: float,
        current_date: date,
    ) -> List[Dict]:
        if self.partial_mode not in {"short_leg", "side_spread"}:
            return []

        prices = self._leg_prices(pos, S, sigma, current_date)
        slip = self._get_dynamic_slippage(sigma)
        events: List[Dict] = []

        def close_short_leg(key: str, label: str) -> None:
            entry_credit = pos.entry_prices[key]
            if entry_credit <= 0 or pos.closed.get(key, False):
                return
            close_cost = prices[key] * (1 + slip) + COMMISSION_PER_CONTRACT
            profit_ratio = (entry_credit - close_cost) / entry_credit
            if profit_ratio >= self.partial_target_pct:
                pnl = entry_credit - close_cost
                self.cash += pnl
                pos.closed[key] = True
                self.partial_exit_count += 1
                events.append({
                    "date": str(current_date),
                    "action": "PARTIAL_SHORT_LEG_TP",
                    "pnl": round(pnl, 2),
                    "leg": label,
                    "profit_ratio": round(profit_ratio, 3),
                })

        def close_side(short_key: str, long_key: str, label: str) -> None:
            if pos.closed.get(short_key, False) or pos.closed.get(long_key, False):
                return
            entry_credit = pos.entry_prices[short_key] - pos.entry_prices[long_key]
            if entry_credit <= 0:
                return
            close_cost = (prices[short_key] - prices[long_key]) * (1 + slip) + 2 * COMMISSION_PER_CONTRACT
            profit_ratio = (entry_credit - close_cost) / entry_credit
            if profit_ratio >= self.partial_target_pct:
                pnl = entry_credit - close_cost
                self.cash += pnl
                pos.closed[short_key] = True
                pos.closed[long_key] = True
                self.partial_exit_count += 1
                events.append({
                    "date": str(current_date),
                    "action": "PARTIAL_SIDE_SPREAD_TP",
                    "pnl": round(pnl, 2),
                    "leg": label,
                    "profit_ratio": round(profit_ratio, 3),
                })

        if self.partial_mode == "short_leg":
            close_short_leg("sp", "sell_put")
            close_short_leg("sc", "sell_call")
        elif self.partial_mode == "side_spread":
            close_side("sp", "bp", "put_spread")
            close_side("sc", "bc", "call_spread")

        return events

    def _open_partial_position(
        self,
        current_date: date,
        exp_date: date,
        S: float,
        iv_est: float,
        actual_dte: int,
        hv20: float,
        dyn_otm: Optional[float],
        dyn_wing: Optional[float],
    ) -> None:
        sp_k, bp_k, sc_k, bc_k, credit = self.calculate_ic_prices(
            S, iv_est, actual_dte, dynamic_otm=dyn_otm, dynamic_wing=dyn_wing
        )
        net_credit = credit - self.COMMISSION * 4
        if net_credit < 50 or sp_k <= 0 or sc_k <= 0:
            return

        max_loss = (sp_k - bp_k) * self.LOT_SIZE
        if self.dynamic_sizing:
            actual_groups = self._calc_dynamic_groups()
            if hv20 > self.vix_deleverage_hv:
                actual_groups = max(1, actual_groups // 2)
        else:
            actual_groups = self._calc_kelly_groups(net_credit, max_loss)

        required_margin = max_loss * 0.5 * actual_groups
        available_margin = self.cash if self.dynamic_sizing else (self.cash + self.initial_capital * 0.5)
        if available_margin < required_margin or self._last_opened_expiry == str(exp_date):
            return

        prices = {
            "sp": self.get_option_price_usd(S, sp_k, actual_dte, iv_est, "PUT"),
            "bp": self.get_option_price_usd(S, bp_k, actual_dte, iv_est, "PUT"),
            "sc": self.get_option_price_usd(S, sc_k, actual_dte, iv_est, "CALL"),
            "bc": self.get_option_price_usd(S, bc_k, actual_dte, iv_est, "CALL"),
        }
        raw_net = prices["sp"] + prices["sc"] - prices["bp"] - prices["bc"]
        slip = self._get_dynamic_slippage(hv20)
        entry_credit = net_credit * (1 - slip)
        scale = entry_credit / raw_net if raw_net > 0 else 1.0
        entry_prices = {key: value * scale for key, value in prices.items()}

        self._last_opened_expiry = str(exp_date)
        self._last_open_date = current_date
        for _ in range(actual_groups):
            self.cash += entry_credit
            self.positions.append(PartialICPosition(
                sell_put_k=sp_k,
                buy_put_k=bp_k,
                sell_call_k=sc_k,
                buy_call_k=bc_k,
                net_credit=entry_credit,
                open_date=current_date,
                expiration=exp_date,
                entry_prices=entry_prices,
                closed={"sp": False, "bp": False, "sc": False, "bc": False},
            ))

    def run(self, df: pd.DataFrame, save_prefix: str = "partial_exit") -> dict:
        prices = df["Close"]
        start_d = df["date"].iloc[0]
        end_d = df["date"].iloc[-1]
        if hasattr(start_d, "date"):
            start_d = start_d.date()
        if hasattr(end_d, "date"):
            end_d = end_d.date()
        self._expiry_calendar = get_us_option_expiries(start_d, end_d + timedelta(days=60))

        for i, row in df.iterrows():
            current_date: date = row["date"]
            if hasattr(current_date, "date"):
                current_date = current_date.date()
            S = float(row["Close"])
            past_prices = prices.iloc[max(0, i - 20): i + 1]
            hv20 = historical_volatility(past_prices, 20)
            iv_est = hv20 * 1.15
            self._hv_history.append(hv20)

            if not self._hard_stopped and hv20 >= self.vix_hard_stop_hv and self.positions:
                for pos in self.positions:
                    pnl = self._close_active_position_with_slippage(pos, S, iv_est, current_date, extra_slip=SLIP_HARD_STOP)
                    self.cash += pnl
                    self.trades.append({"date": str(current_date), "action": "VIX_HARD_STOP", "pnl": round(pnl, 2), "hv20": round(hv20, 3)})
                self.positions = []
                self._hard_stopped = True
                self._stop_date = current_date
                self.stopped = True

            if self._hard_stopped and hv20 < self.vix_cooldown_hv:
                self._hard_stopped = False
                self.stopped = False
                self._stop_date = None

            if self.stopped and not self._hard_stopped and self._stop_date:
                if (current_date - self._stop_date).days >= self.cooldown_days:
                    self.stopped = False
                    self._stop_date = None

            if len(self.positions) == 0 and not self.stopped:
                can_open = True
                if self.cooldown_days > 0 and self._last_close_date:
                    can_open = (current_date - self._last_close_date).days >= self.cooldown_days
                actual_dte = self.dte
                target_expiry = None
                if can_open and self.entry_mode == "pre_expiry":
                    next_exp = get_next_expiry(current_date, self._expiry_calendar)
                    if next_exp:
                        actual_dte = (next_exp - current_date).days
                        target_expiry = next_exp
                        if actual_dte > self.entry_days_before_expiry:
                            can_open = False
                    else:
                        can_open = False
                if can_open and actual_dte >= 7:
                    dyn = self.get_dynamic_params(hv20)
                    if not dyn.get("skip"):
                        dyn_otm = dyn["otm"] if self.dynamic_otm else None
                        dyn_wing = dyn["wing"] if self.dynamic_otm else None
                        exp_date = target_expiry or (current_date + timedelta(days=actual_dte))
                        self._open_partial_position(current_date, exp_date, S, iv_est, actual_dte, hv20, dyn_otm, dyn_wing)

            remaining = []
            for pos in self.positions:
                days_to_exp = (pos.expiration - current_date).days
                position_mv = self._estimate_position_value(pos, S, iv_est, current_date)
                total_value = self.cash + position_mv
                if total_value > self.peak_value:
                    self.peak_value = total_value
                current_dd = (total_value - self.peak_value) / self.peak_value

                if current_dd <= -self.stop_loss_pct and not self.stopped:
                    self.stopped = True
                    self._stop_date = current_date
                    pnl = self._close_active_position_with_slippage(pos, S, iv_est, current_date)
                    self.cash += pnl
                    self.trades.append({"date": str(current_date), "action": "STOP_LOSS", "pnl": round(pnl, 2)})
                    continue

                for event in self._maybe_partial_take_profit(pos, S, iv_est, current_date):
                    self.trades.append(event)
                if self._is_fully_closed(pos):
                    self._last_close_date = current_date
                    continue

                put_w = pos.sell_put_k - pos.buy_put_k
                call_w = pos.buy_call_k - pos.sell_call_k
                stop_put = pos.sell_put_k - put_w * min(self.stop_loss_buffer - 1.0, 0.8)
                stop_call = pos.sell_call_k + call_w * min(self.stop_loss_buffer - 1.0, 0.8)

                should_close = False
                close_reason = ""
                if (not pos.closed.get("sp", False) and S <= stop_put) or (not pos.closed.get("sc", False) and S >= stop_call):
                    should_close = True
                    close_reason = "PRICE_STOP"
                elif days_to_exp <= self.early_close_days:
                    should_close = True
                    close_reason = "EXPIRY"

                if should_close:
                    pnl = self._close_active_position_with_slippage(pos, S, iv_est, current_date)
                    self.cash += pnl
                    self._last_close_date = current_date
                    self.trades.append({"date": str(current_date), "action": "CLOSE_IC", "pnl": round(pnl, 2), "reason": close_reason})
                else:
                    remaining.append(pos)

            self.positions = remaining
            pos_mv = sum(self._estimate_position_value(p, S, iv_est, current_date) for p in self.positions)
            self.daily_records.append({"date": current_date, "total_value": self.cash + pos_mv, "sigma": round(hv20, 4)})

        final_v = self.daily_records[-1]["total_value"] if self.daily_records else self.initial_capital
        years = (df["date"].iloc[-1] - df["date"].iloc[0]).days / 365.0 if hasattr(df["date"].iloc[-1], "__sub__") else 16.0
        tv = pd.Series([r["total_value"] for r in self.daily_records])
        dr = tv.pct_change().dropna()
        sharpe = 0.0
        if dr.std() > 1e-10:
            sharpe = (dr - RISK_FREE / 252).mean() / (dr - RISK_FREE / 252).std() * math.sqrt(252)
        peak = tv.cummax()
        max_dd = ((tv - peak) / peak * 100).min()
        return {"final": round(final_v, 0), "max_dd": round(max_dd, 2), "sharpe": round(float(sharpe), 2), "years": round(years, 1)}


def fetch_data(start: str, end: str) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    for asset in LIVE_ASSETS:
        print(f"📥 拉取 {asset['name']} ({asset['ticker']}) {start}~{end}...")
        df = fetch_futu_kline(asset["ticker"], start, end)
        if df is None or df.empty:
            print(f"  ⚠️  {asset['name']} 数据不可用")
            continue
        data[asset["ticker"]] = df.copy()
        print(f"  ✅ {len(df)} 天")
    return data


def build_backtester(asset: dict, scenario: dict):
    common_kwargs = dict(
        ticker=asset["ticker"],
        initial_capital=asset["capital"],
        max_groups=asset["base_groups"],
        dynamic_sizing=True,
        groups_cap=asset["base_groups"] * 20,
        label=f"{scenario['id']}-{asset['name']}",
        **{**IC_PARAMS, "profit_target_pct": scenario["target"] if scenario["mode"] == "group" else 0.0},
    )
    if scenario["mode"] == "group":
        return EnhancedICBacktester(**common_kwargs)
    return PartialExitICBacktester(
        partial_mode=scenario["mode"],
        partial_target_pct=scenario["target"],
        **common_kwargs,
    )


def run_asset(asset: dict, df: pd.DataFrame, scenario: dict) -> dict:
    bt = build_backtester(asset, scenario)
    bt.COMMISSION = 0.0
    with redirect_stdout(io.StringIO()):
        bt.run(df, save_prefix=f"profit_exit_{scenario['id']}_{asset['name']}")

    daily = pd.DataFrame(bt.daily_records)[["date", "total_value", "sigma"]].copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.set_index("date")

    trades = pd.DataFrame(bt.trades).copy()
    if not trades.empty:
        trades["date"] = pd.to_datetime(trades["date"])
        trades["ticker"] = asset["ticker"]
        trades["asset"] = asset["name"]
    return {"daily": daily, "trades": trades}


def run_scenario_period(scenario: dict, data: Dict[str, pd.DataFrame], start: str, end: str, label: str) -> dict:
    combined = None
    trades_all: List[pd.DataFrame] = []
    qqq_daily = None

    for asset in LIVE_ASSETS:
        df = data.get(asset["ticker"])
        if df is None or df.empty:
            return {}
        dates = pd.to_datetime(df["date"])
        sliced = df[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))].reset_index(drop=True)
        if len(sliced) < 120:
            return {}
        result = run_asset(asset, sliced, scenario)
        if asset["ticker"] == "US.QQQ":
            qqq_daily = result["daily"]
        renamed = result["daily"][["total_value"]].rename(columns={"total_value": asset["ticker"]})
        combined = renamed if combined is None else combined.join(renamed, how="inner")
        if not result["trades"].empty:
            trades_all.append(result["trades"])

    if combined is None or combined.empty or qqq_daily is None:
        return {}

    raw_portfolio = combined.sum(axis=1)
    qqq_sigma = qqq_daily["sigma"].reindex(raw_portfolio.index).ffill().fillna(0.20)
    trades = pd.concat(trades_all, ignore_index=True) if trades_all else pd.DataFrame(columns=["date", "action", "pnl"])
    commission_series = build_commission_series(trades, raw_portfolio.index)
    eq = build_actual_equity_curve(raw_portfolio, qqq_sigma, commission_series)
    stats = calc_curve_stats(eq, label)
    stats.update({
        "scenario_id": scenario["id"],
        "scenario_label": scenario["label"],
        "equity_curve": eq,
        "trades": trades,
        "yearly_rows": calc_yearly_breakdown(eq, trades, scenario),
        "commission_total": round(float(commission_series.sum()), 2),
    })
    return stats


def run_crisis_windows(scenarios: List[dict], data: Dict[str, pd.DataFrame], window_years: int) -> List[dict]:
    rows: List[dict] = []
    for year_info in CANDIDATE_YEARS:
        start_year = max(2006, year_info["year"] - window_years + 1)
        start = f"{start_year}-01-01"
        end = f"{year_info['year']}-12-31"
        for scenario in scenarios:
            result = run_scenario_period(scenario, data, start, end, f"{year_info['label']} | {scenario['label']}")
            if not result:
                continue
            eq = result["equity_curve"]
            crisis_seg = eq[eq.index.year == year_info["year"]]
            crisis_peak = crisis_seg.cummax() if not crisis_seg.empty else crisis_seg
            crisis_dd = float(((crisis_seg - crisis_peak) / crisis_peak * 100).min()) if len(crisis_seg) > 1 else 0.0
            crisis_ret = float((crisis_seg.iloc[-1] / crisis_seg.iloc[0] - 1) * 100) if len(crisis_seg) > 1 else 0.0
            rows.append({
                "year": year_info["year"],
                "year_label": year_info["label"],
                "window_label": f"{start_year}-{year_info['year']}",
                "scenario_id": scenario["id"],
                "scenario_label": scenario["label"],
                "ann_ret": result["ann_ret"],
                "max_dd": result["max_dd"],
                "sharpe": result["sharpe"],
                "crisis_ret": round(crisis_ret, 2),
                "crisis_dd": round(crisis_dd, 2),
                "final": result["final"],
            })
    return rows


def save_outputs(full_results: List[dict], yearly_rows: List[dict], crisis_rows: List[dict]) -> List[Path]:
    out_dir = Path(__file__).parent / "backtest_results"
    out_dir.mkdir(exist_ok=True)
    full_path = out_dir / "profit_taking_exit_full_summary.csv"
    yearly_path = out_dir / "profit_taking_exit_yearly_breakdown.csv"
    crisis_path = out_dir / "profit_taking_exit_crisis_windows.csv"

    pd.DataFrame([
        {
            "scenario_id": row["scenario_id"],
            "scenario_label": row["scenario_label"],
            "ann_ret": row["ann_ret"],
            "total_ret": row["total_ret"],
            "max_dd": row["max_dd"],
            "sharpe": row["sharpe"],
            "calmar": row["calmar"],
            "worst_month": row["worst_month"],
            "worst_day": row["worst_day"],
            "final": row["final"],
            "commission_total": row["commission_total"],
        }
        for row in full_results
    ]).to_csv(full_path, index=False)
    pd.DataFrame(yearly_rows).to_csv(yearly_path, index=False)
    pd.DataFrame(crisis_rows).to_csv(crisis_path, index=False)
    return [full_path, yearly_path, crisis_path]


def print_summary(full_results: List[dict], crisis_rows: List[dict]) -> None:
    print("\n" + "=" * 118)
    print("  📊 止盈退出规则专项回测 | F=20x | 实盘成本口径")
    print("=" * 118)
    print(f"  {'场景':<28} {'年化':>8} {'总回报':>9} {'回撤':>8} {'Sharpe':>7} {'Calmar':>7} {'最差月':>8} {'期末':>12}")
    print("  " + "─" * 104)
    for row in full_results:
        print(
            f"  {row['scenario_label']:<28} {row['ann_ret']:>+7.2f}% {row['total_ret']:>+8.2f}% "
            f"{row['max_dd']:>7.2f}% {row['sharpe']:>7.2f} {row['calmar']:>7.2f} "
            f"{row['worst_month']:>7.2f}% ${row['final']:>11,.0f}"
        )

    if crisis_rows:
        df = pd.DataFrame(crisis_rows)
        agg = df.groupby(["scenario_id", "scenario_label"], as_index=False).agg(
            avg_ann_ret=("ann_ret", "mean"),
            avg_sharpe=("sharpe", "mean"),
            avg_crisis_ret=("crisis_ret", "mean"),
            avg_crisis_dd=("crisis_dd", "mean"),
        )
        print("\n  🚨 黑天鹅窗口均值：")
        print(f"  {'场景':<28} {'平均年化':>10} {'平均Sharpe':>12} {'危机收益':>10} {'危机回撤':>10}")
        print("  " + "─" * 78)
        for _, row in agg.iterrows():
            print(
                f"  {row['scenario_label']:<28} {row['avg_ann_ret']:>+9.2f}% {row['avg_sharpe']:>12.2f} "
                f"{row['avg_crisis_ret']:>9.2f}% {row['avg_crisis_dd']:>9.2f}%"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="止盈退出规则专项回测")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--window-years", type=int, default=5)
    args = parser.parse_args()

    print("=" * 118)
    print("  🚀 止盈退出规则专项回测")
    print("  参数固定: P3.0% / C6.0% / Wing9% / DTE45 / F=20x / 动态组数 / 实盘成本口径")
    print("=" * 118)
    data = fetch_data(args.start, args.end)
    if len(data) < 3:
        print("❌ 数据不足，退出")
        sys.exit(1)

    full_results: List[dict] = []
    yearly_rows: List[dict] = []
    for scenario in SCENARIOS:
        print(f"\n▶ 全周期运行 {scenario['label']} ...")
        result = run_scenario_period(scenario, data, args.start, args.end, f"{scenario['label']} | {args.start[:4]}-{args.end[:4]}")
        if not result:
            print("  ⚠️  结果为空，跳过")
            continue
        full_results.append(result)
        yearly_rows.extend(result["yearly_rows"])
        print(f"  年化={result['ann_ret']:+.2f}%  回撤={result['max_dd']:.2f}%  Sharpe={result['sharpe']:.2f}  期末=${result['final']:,.0f}")

    crisis_rows = run_crisis_windows(SCENARIOS, data, args.window_years)
    print_summary(full_results, crisis_rows)
    out_paths = save_outputs(full_results, yearly_rows, crisis_rows)
    print("\n📁 输出文件：")
    for path in out_paths:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
