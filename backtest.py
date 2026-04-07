"""
腾讯 Wheel 策略回测 - 使用模拟历史数据
基于腾讯真实价格范围模拟
"""

import sys
import math
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path
import random

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from config import WHEEL_CONFIG, RISK_CONFIG, STOCK_CONFIG
from strategy import WheelStrategy, WheelState, Position, StockHolding


class WheelBacktester:
    """Wheel 策略回测器"""

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.strategy = WheelStrategy()
        self.trades = []
        self.daily_records = []

        self.put_config = WHEEL_CONFIG["put"]
        self.call_config = WHEEL_CONFIG["call"]
        self.risk_config = RISK_CONFIG

        random.seed(42)
        np.random.seed(42)

    def generate_synthetic_data(self, start: str, end: str) -> pd.DataFrame:
        """生成模拟历史数据（基于腾讯真实价格范围）"""
        print("📊 生成模拟历史数据（基于腾讯真实价格范围）...")

        start_date = datetime.strptime(start, "%Y-%m-%d")
        end_date = datetime.strptime(end, "%Y-%m-%d")
        dates = pd.date_range(start_date, end_date, freq="B")

        initial_price = 280.0
        prices = [initial_price]
        for i in range(1, len(dates)):
            daily_return = np.random.normal(0.0005, 0.015)
            new_price = prices[-1] * (1 + daily_return)
            new_price = max(200, min(550, new_price))
            prices.append(new_price)

        df = pd.DataFrame({
            "date": dates,
            "Open": prices,
            "High": [p * (1 + abs(np.random.normal(0, 0.005))) for p in prices],
            "Low": [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
            "Close": prices,
            "Volume": [int(1000000 * (0.8 + np.random.random() * 0.4)) for _ in prices]
        })
        df["date"] = df["date"].dt.date

        print(f"✅ 生成 {len(df)} 个交易日数据")
        print(f"   价格范围: {min(prices):.0f} - {max(prices):.0f}")
        print(f"   时间范围: {df['date'].iloc[0]} 至 {df['date'].iloc[-1]}")

        return df

    def estimate_option_price(self, S: float, K: float, T: float,
                               sigma: float = 0.30, option_type: str = "PUT") -> float:
        """简化 Black-Scholes 期权定价"""
        import math
        r = 0.05

        # 计算 d1 和 d2
        d1 = (math.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        # 标准正态分布 CDF
        def norm_cdf(x):
            return 0.5 * (1 + math.erf(x / math.sqrt(2)))

        if option_type == "PUT":
            price = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
        else:
            price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)

        price = max(price, 0.01)
        # 设置合理的价格范围
        if option_type == "PUT":
            # OTM Put: 权利金约为标的价格的 1-5%
            intrinsic = max(0, K - S)
            time_value = S * sigma * math.sqrt(T) * 0.4  # 简化时间价值估算
            price = min(intrinsic + time_value, S * 0.08)
        else:
            intrinsic = max(0, S - K)
            time_value = S * sigma * math.sqrt(T) * 0.4
            price = min(intrinsic + time_value, S * 0.06)

        return max(price, 0.50)  # 最低 0.5 港元

    def find_put_candidates(self, current_price: float) -> list:
        candidates = []
        for delta_pct in [0.05, 0.10, 0.15]:
            strike = current_price * (1 - delta_pct)
            dte = 30
            premium = self.estimate_option_price(S=current_price, K=strike,
                                                   T=dte/365, sigma=0.30, option_type="PUT") * 100
            if premium >= self.put_config["min_premium"]:
                candidates.append({"strike": strike, "premium": premium, "dte": dte, "delta": delta_pct})
        return sorted(candidates, key=lambda x: x["premium"], reverse=True)

    def find_call_candidates(self, current_price: float, cost_basis: float) -> list:
        candidates = []
        for delta_pct in [0.05, 0.10, 0.15]:
            strike = cost_basis * (1 + delta_pct)
            strike = max(strike, current_price)
            dte = 30
            premium = self.estimate_option_price(S=current_price, K=strike,
                                                   T=dte/365, sigma=0.28, option_type="CALL") * 100
            if premium >= self.call_config["min_premium"]:
                candidates.append({"strike": strike, "premium": premium, "dte": dte, "delta": delta_pct})
        return sorted(candidates, key=lambda x: x["premium"], reverse=True)

    def run(self, start_date: str, end_date: str):
        print("=" * 60)
        print("🚀 腾讯 Wheel 策略回测")
        print("=" * 60)

        df = self.generate_synthetic_data(start_date, end_date)
        print("\n📊 开始回测...\n")

        for i, row in df.iterrows():
            current_date = row["date"]
            current_price = row["Close"]

            daily = {
                "date": current_date,
                "price": current_price,
                "state": self.strategy.state.value,
                "cash": self.cash,
                "premium_collected": self.strategy.total_premium_collected,
            }

            # IDLE: 卖 Put
            if self.strategy.state == WheelState.IDLE:
                candidates = self.find_put_candidates(current_price)
                if candidates:
                    best = candidates[0]
                    self.cash += best["premium"]
                    self.strategy.option_position = Position(
                        code="SIM_PUT", type="PUT", strike=best["strike"], quantity=1,
                        premium=best["premium"], open_date=current_date,
                        expiration=current_date + timedelta(days=best["dte"]), cost_basis=0
                    )
                    self.strategy.state = WheelState.SELL_PUT
                    self.strategy.record_premium(best["premium"])
                    self.trades.append({
                        "date": current_date, "action": "SELL_PUT",
                        "strike": best["strike"], "premium": best["premium"],
                        "dte": best["dte"], "price_at_open": current_price
                    })

            # SELL_PUT
            elif self.strategy.state == WheelState.SELL_PUT:
                opt = self.strategy.option_position
                if opt and current_date >= opt.expiration:
                    if current_price <= opt.strike:
                        self.strategy.stock_holding = StockHolding(
                            ticker="0700.HK", quantity=100, cost_basis=opt.strike,
                            acquired_date=current_date
                        )
                        self.cash -= opt.strike * 100
                        self.strategy.state = WheelState.HOLD_STOCK
                        self.trades.append({
                            "date": current_date, "action": "PUT_ASSIGNED",
                            "strike": opt.strike, "price": current_price,
                            "premium_collected": opt.premium
                        })
                        print(f"  ⚡ PUT 被行权! strike={opt.strike}, price={current_price:.2f}")
                    else:
                        self.trades.append({
                            "date": current_date, "action": "PUT_EXPIRED",
                            "strike": opt.strike, "premium": opt.premium
                        })
                        print(f"  ✅ PUT 过期作废, 收取权利金 HKD {opt.premium:.0f}")
                        self.strategy.state = WheelState.IDLE  # 回到空闲状态
                    self.strategy.option_position = None

            # HOLD_STOCK: 卖 Call
            elif self.strategy.state == WheelState.HOLD_STOCK:
                if self.strategy.option_position is None:
                    candidates = self.find_call_candidates(current_price, self.strategy.stock_holding.cost_basis)
                    if candidates:
                        best = candidates[0]
                        self.cash += best["premium"]
                        self.strategy.option_position = Position(
                            code="SIM_CALL", type="CALL", strike=best["strike"], quantity=1,
                            premium=best["premium"], open_date=current_date,
                            expiration=current_date + timedelta(days=best["dte"]),
                            cost_basis=self.strategy.stock_holding.cost_basis
                        )
                        self.strategy.state = WheelState.SELL_CALL
                        self.strategy.record_premium(best["premium"])
                        self.trades.append({
                            "date": current_date, "action": "SELL_CALL",
                            "strike": best["strike"], "premium": best["premium"],
                            "dte": best["dte"], "cost_basis": self.strategy.stock_holding.cost_basis
                        })

            # SELL_CALL
            elif self.strategy.state == WheelState.SELL_CALL:
                opt = self.strategy.option_position
                if opt and current_date >= opt.expiration:
                    if current_price >= opt.strike:
                        proceeds = opt.strike * 100
                        self.cash += proceeds
                        if self.strategy.stock_holding:
                            cost = self.strategy.stock_holding.cost_basis * 100
                            self.trades.append({
                                "date": current_date, "action": "CALL_ASSIGNED",
                                "strike": opt.strike, "cost": cost, "proceeds": proceeds,
                                "pnl": proceeds - cost, "premium_collected": opt.premium
                            })
                        self.strategy.stock_holding = None
                        self.strategy.state = WheelState.IDLE
                    else:
                        self.trades.append({
                            "date": current_date, "action": "CALL_EXPIRED",
                            "strike": opt.strike, "premium": opt.premium
                        })
                        self.strategy.state = WheelState.HOLD_STOCK
                    self.strategy.option_position = None

            stock_value = self.strategy.stock_holding.quantity * current_price if self.strategy.stock_holding else 0
            total_value = self.cash + stock_value
            daily.update({
                "stock_value": stock_value,
                "total_value": total_value,
                "return_pct": (total_value - self.initial_capital) / self.initial_capital * 100
            })
            self.daily_records.append(daily)

            if (i + 1) % 50 == 0 or i == len(df) - 1:
                print(f"  {current_date} | 股价: {current_price:.2f} | 状态: {self.strategy.state.value} | "
                      f"总价值: {total_value:,.0f} | 收益: {daily['return_pct']:.1f}%")

        self.print_results(df)

    def print_results(self, df: pd.DataFrame):
        df_result = pd.DataFrame(self.daily_records)
        df_trades = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

        final_value = df_result["total_value"].iloc[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        total_premium = self.strategy.total_premium_collected

        start_date = df_result["date"].iloc[0]
        end_date = df_result["date"].iloc[-1]
        years = (end_date - start_date).days / 365

        print("\n" + "=" * 60)
        print("📈 回测结果")
        print("=" * 60)

        print(f"""
📊 基本信息
   初始资金:         HKD {self.initial_capital:,.0f}
   最终价值:         HKD {final_value:,.0f}
   总收益:           HKD {final_value - self.initial_capital:,.0f}
   总收益率:         {total_return:.2f}%
   年化收益率:       {total_return / max(years, 0.1):.2f}% (约 {years:.1f} 年)
""")

        if not df_trades.empty:
            sell_put = len(df_trades[df_trades["action"] == "SELL_PUT"])
            put_expired = len(df_trades[df_trades["action"] == "PUT_EXPIRED"])
            put_assigned = len(df_trades[df_trades["action"] == "PUT_ASSIGNED"])
            sell_call = len(df_trades[df_trades["action"] == "SELL_CALL"])
            call_expired = len(df_trades[df_trades["action"] == "CALL_EXPIRED"])
            call_assigned = len(df_trades[df_trades["action"] == "CALL_ASSIGNED"])

            put_premiums = df_trades[df_trades["action"].isin(["PUT_EXPIRED", "PUT_ASSIGNED"])]["premium"].sum()
            call_premiums = df_trades[df_trades["action"].isin(["CALL_EXPIRED", "CALL_ASSIGNED"])]["premium"].sum()

            print(f"""💰 权利金统计
   累计权利金:       HKD {total_premium:,.2f}
   Put 权利金:       HKD {put_premiums:,.2f} ({put_expired + put_assigned} 次)
   Call 权利金:      HKD {call_premiums:,.2f} ({call_expired + call_assigned} 次)
   权利金收益率:     {total_premium / self.initial_capital * 100:.2f}%

📋 交易统计
   卖出 Put:         {sell_put} 次
   Put 过期作废:     {put_expired} 次 ({put_expired/max(sell_put,1)*100:.0f}%)
   Put 被行权:       {put_assigned} 次 ({put_assigned/max(sell_put,1)*100:.0f}%)
   卖出 Call:        {sell_call} 次
   Call 过期作废:    {call_expired} 次 ({call_expired/max(sell_call,1)*100:.0f}%)
   Call 被行权:      {call_assigned} 次 ({call_assigned/max(sell_call,1)*100:.0f}%)
""")

        df_result["peak"] = df_result["total_value"].cummax()
        df_result["drawdown"] = (df_result["total_value"] - df_result["peak"]) / df_result["peak"] * 100
        max_drawdown = df_result["drawdown"].min()
        max_drawdown_date = df_result.loc[df_result["drawdown"].idxmin(), "date"]

        print(f"""📉 风险指标
   最大回撤:         {max_drawdown:.2f}% (发生在 {max_drawdown_date})
""")

        df_result["month"] = pd.to_datetime(df_result["date"]).dt.to_period("M")
        monthly = df_result.groupby("month").agg({"return_pct": "last"}).reset_index()
        monthly["monthly_return"] = monthly["return_pct"].diff()

        print("📅 月度收益:")
        for _, row in monthly.iterrows():
            month_str = str(row["month"])
            ret = row["monthly_return"]
            emoji = "🟢" if ret >= 0 else "🔴"
            print(f"   {month_str}: {emoji} {ret:+6.2f}%")

        if not df_trades.empty:
            put_wins = put_expired
            call_wins = call_expired
            print(f"""
🎯 胜率分析
   Put 胜率:         {put_wins}/{sell_put} = {put_wins/max(sell_put,1)*100:.0f}%
   Call 胜率:        {call_wins}/{sell_call} = {call_wins/max(sell_call,1)*100:.0f}%
   综合胜率:         {(put_wins + call_wins)}/{sell_put + sell_call} = {(put_wins + call_wins)/max(sell_put + sell_call,1)*100:.0f}%
""")

        output_dir = Path(__file__).parent / "backtest_results"
        output_dir.mkdir(exist_ok=True)
        df_result.to_csv(output_dir / "daily_records.csv", index=False)
        if not df_trades.empty:
            df_trades.to_csv(output_dir / "trades.csv", index=False)
        print(f"\n✅ 结果已保存至 {output_dir}/")


def main():
    parser = argparse.ArgumentParser(description="腾讯 Wheel 策略回测")
    parser.add_argument("--capital", type=float, default=100000)
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-03-31")
    args = parser.parse_args()

    backtester = WheelBacktester(initial_capital=args.capital)
    backtester.run(start_date=args.start, end_date=args.end)


if __name__ == "__main__":
    main()
