"""
腾讯 Wheel 策略回测 - 真实历史数据版
数据来源：富途 OpenD API（腾讯 00700.HK 日K线）
期权定价：Black-Scholes + 历史波动率
"""

import sys
import math
import logging
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from strategy import WheelStrategy, WheelState, Position, StockHolding

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  富途历史数据拉取
# ─────────────────────────────────────────────

def fetch_futu_kline(ticker: str, start: str, end: str,
                     host: str = "127.0.0.1", port: int = 11111) -> Optional[pd.DataFrame]:
    """
    从富途 OpenD 拉取日 K 线历史数据（支持分页，自动拼接）
    返回 DataFrame: date(date), Open, High, Low, Close, Volume
    """
    try:
        from futu import OpenQuoteContext, KLType, AuType, RET_OK, KL_FIELD
    except ImportError:
        print("⚠️  futu-api 未安装，请运行: pip install futu-api")
        return None

    print(f"🔌 连接富途 OpenD ({host}:{port})...")
    try:
        ctx = OpenQuoteContext(host=host, port=port)
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        print("   请确认 FutuOpenD 已启动")
        return None

    print(f"📥 拉取 {ticker} 历史K线 {start} → {end} ...")
    all_data = []
    page_key = None

    while True:
        ret, df, page_key = ctx.request_history_kline(
            code=ticker,
            start=start,
            end=end,
            ktype=KLType.K_DAY,
            autype=AuType.QFQ,          # 前复权
            fields=[KL_FIELD.DATE_TIME, KL_FIELD.OPEN, KL_FIELD.HIGH,
                    KL_FIELD.LOW, KL_FIELD.CLOSE, KL_FIELD.TRADE_VOL],
            max_count=1000,
            page_req_key=page_key,
        )
        if ret != RET_OK:
            print(f"❌ 拉取失败: {df}")
            ctx.close()
            return None

        all_data.append(df)
        if page_key is None:
            break  # 没有更多数据

    ctx.close()

    result = pd.concat(all_data, ignore_index=True)
    result = result.drop_duplicates(subset="time_key")
    result["date"] = pd.to_datetime(result["time_key"]).dt.date
    result = result.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume"
    })
    result = result[["date", "Open", "High", "Low", "Close", "Volume"]].sort_values("date").reset_index(drop=True)

    print(f"✅ 获取 {len(result)} 个交易日  |  价格范围: {result['Close'].min():.2f} – {result['Close'].max():.2f}")
    return result


# ─────────────────────────────────────────────
#  Black-Scholes 期权定价
# ─────────────────────────────────────────────

def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_option_price(S: float, K: float, T: float, sigma: float,
                    r: float = 0.04, option_type: str = "PUT") -> float:
    """
    Black-Scholes 欧式期权定价
    S: 标的现价  K: 行权价  T: 到期时间(年)
    sigma: 年化波动率  r: 无风险利率
    返回: 单股期权价格（港元）
    """
    # 确保输入是数值类型
    S = float(S)
    K = float(K)
    T = float(T)
    sigma = float(sigma)
    r = float(r)
    
    if T <= 0 or sigma <= 0:
        intrinsic = max(K - S, 0) if option_type == "PUT" else max(S - K, 0)
        return intrinsic
    
    # 保护：确保 S/K 为正数
    ratio = S / K
    if ratio <= 0:
        ratio = 0.0001
    
    sqrt_term = sigma * math.sqrt(T)
    if sqrt_term < 1e-10:  # 防止除以接近0的数
        sqrt_term = 1e-10
    
    d1 = (math.log(ratio) + (r + 0.5 * sigma ** 2) * T) / sqrt_term
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "PUT":
        price = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    else:
        price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)

    return max(price, 0.01)


def historical_volatility(prices: pd.Series, window: int = 20, iv_premium: float = 1.0) -> float:
    """
    计算历史波动率（年化）
    window:     交易日窗口（默认20日）
    iv_premium: IV溢价系数（默认1.0 = 纯HV，与Finviz/富途口径一致）
                港股/HK期权定价时传入 1.15（腾讯IV通常比HV高10-20%）
                美股IC策略入场过滤用默认1.0，期权定价处调用方自行乘以1.15
    """
    if len(prices) <= window:
        return 0.30  # 默认30%

    log_returns = np.log(prices / prices.shift(1)).dropna()
    vol = log_returns.tail(window).std() * math.sqrt(252)
    return float(vol * iv_premium)


# ─────────────────────────────────────────────
#  回测引擎
# ─────────────────────────────────────────────

class RealDataBacktester:
    """使用真实富途数据的 Wheel 策略回测器"""

    LOT_SIZE = 100          # 港股期权每手 100 股
    COMMISSION = 30         # 单张期权佣金 HKD（保守估计）
    SLIPPAGE_PCT = 0.003    # 滑点 0.3%

    def __init__(self, initial_capital: float = 100_000,
                 iv_filter: float = 0.0,
                 strike_otm: float = 0.05,   # Put 行权价偏移：0.05 = -5%，0.10 = -10%
                 dte: int = 30,              # 到期天数（与实盘一致）
                 min_premium: float = 900,   # 最低权利金（与实盘一致）
                 label: str = ""):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.strategy = WheelStrategy()
        self.trades: List[Dict] = []
        self.daily_records: List[Dict] = []

        # 自动生成标签
        iv_tag    = f"IV>{iv_filter:.0%}" if iv_filter > 0 else "无IV过滤"
        otm_tag   = f"-{strike_otm:.0%}行权"
        dte_tag   = f"DTE={dte}"
        self.label = label or f"{iv_tag} {otm_tag} {dte_tag}"

        # 策略参数
        # Put 行权价候选：以 strike_otm 为基准向外延伸 3 档
        self.put_strike_pcts  = [
            round(1 - strike_otm, 3),
            round(1 - strike_otm - 0.03, 3),
            round(1 - strike_otm - 0.05, 3),
        ]
        self.call_strike_pct  = 1.08   # Call 行权价 = 成本价 × 1.08（+8%）
        self.dte              = dte     # 目标到期日天数（与实盘一致）
        self.min_premium     = min_premium  # 最低权利金（与实盘一致，900 HKD）
        self.vol_window       = 20    # 历史波动率窗口（天）
        self.iv_filter        = iv_filter
        self.strike_otm       = strike_otm
        self._last_trade_month: Optional[str] = None

    # ── 期权定价工具 ────────────────────────────

    def get_option_price_hkd(self, S: float, K: float, T_days: float,
                              sigma: float, option_type: str) -> float:
        """返回单张期权总价值（HKD），已乘以手数"""
        T = T_days / 365.0
        per_share = bs_option_price(S, K, T, sigma, option_type=option_type)
        # 成交以 mid price 估算（bid/ask 中间价），再扣滑点
        per_share *= (1 - self.SLIPPAGE_PCT)
        return per_share * self.LOT_SIZE

    # ── 主循环 ───────────────────────────────────

    def run(self, df: pd.DataFrame):
        print("\n📊 开始回测...\n")
        prices = df["Close"]

        for i, row in df.iterrows():
            current_date: date = row["date"]
            S: float = float(row["Close"])

            # 计算历史波动率（用前 vol_window 天）
            past_prices = prices.iloc[max(0, i - self.vol_window): i + 1]
            sigma = historical_volatility(past_prices, self.vol_window, iv_premium=1.15)  # HK: IV通常比HV高15%

            # ── IDLE → SELL_PUT ─────────────────────
            if self.strategy.state == WheelState.IDLE:
                # 每月只开一次仓（避免月中频繁开仓）
                cur_month = current_date.strftime("%Y-%m")
                # IV 过滤器：波动率不够高时跳过
                iv_ok = (self.iv_filter == 0) or (sigma >= self.iv_filter)
                if cur_month != self._last_trade_month and iv_ok:
                    # 扫描多个行权价候选，选权利金最高的
                    best_candidate = None
                    for pct in self.put_strike_pcts:
                        K_put = S * pct
                        premium = self.get_option_price_hkd(S, K_put, self.dte, sigma, "PUT")
                        if premium >= self.min_premium:
                            if best_candidate is None or premium > best_candidate["premium"]:
                                best_candidate = {"K": K_put, "premium": premium, "pct": pct}

                    if best_candidate:
                        K_put = best_candidate["K"]
                        net_premium = best_candidate["premium"] - self.COMMISSION
                        exp_date = current_date + timedelta(days=self.dte)
                        self.cash += net_premium
                        self._last_trade_month = cur_month

                        self.strategy.option_position = Position(
                            code=f"PUT_{current_date}",
                            type="PUT", strike=K_put, quantity=1,
                            premium=net_premium, open_date=current_date,
                            expiration=exp_date, cost_basis=0
                        )
                        self.strategy.state = WheelState.SELL_PUT
                        self.strategy.record_premium(net_premium)

                        self.trades.append({
                            "date": str(current_date), "action": "SELL_PUT",
                            "price": S, "strike": round(K_put, 2),
                            "sigma": round(sigma, 3), "premium": round(net_premium, 0),
                            "expiration": str(exp_date)
                        })
                        print(f"  📤 [{current_date}] SELL_PUT  S={S:.1f}  K={K_put:.1f}(-{1-best_candidate['pct']:.0%})  σ={sigma:.1%}  权利金=HKD{net_premium:.0f}")

            # ── SELL_PUT → 到期判断 ─────────────────
            elif self.strategy.state == WheelState.SELL_PUT:
                opt = self.strategy.option_position
                if opt and current_date >= opt.expiration:
                    if S <= opt.strike:
                        # 被行权，接盘
                        cost = opt.strike * self.LOT_SIZE
                        self.cash -= cost
                        self.strategy.stock_holding = StockHolding(
                            ticker="0700.HK", quantity=self.LOT_SIZE,
                            cost_basis=opt.strike, acquired_date=current_date
                        )
                        self.strategy.state = WheelState.HOLD_STOCK
                        self.trades.append({
                            "date": str(current_date), "action": "PUT_ASSIGNED",
                            "price": S, "strike": round(opt.strike, 2),
                            "cost": round(cost, 0), "premium_kept": round(opt.premium, 0)
                        })
                        print(f"  ⚡ [{current_date}] PUT 被行权!  S={S:.1f}  K={opt.strike:.1f}  接盘成本 HKD{cost:.0f}")
                    else:
                        # 过期作废，保留权利金
                        self.strategy.state = WheelState.IDLE
                        self.trades.append({
                            "date": str(current_date), "action": "PUT_EXPIRED",
                            "price": S, "strike": round(opt.strike, 2),
                            "premium_kept": round(opt.premium, 0)
                        })
                        print(f"  ✅ [{current_date}] PUT 作废    S={S:.1f}  K={opt.strike:.1f}  入袋 HKD{opt.premium:.0f}")
                    self.strategy.option_position = None

            # ── HOLD_STOCK → SELL_CALL ──────────────
            elif self.strategy.state == WheelState.HOLD_STOCK:
                if self.strategy.option_position is None and self.strategy.stock_holding:
                    cur_month = current_date.strftime("%Y-%m")
                    if cur_month != self._last_trade_month:
                        cost_basis = self.strategy.stock_holding.cost_basis
                        # 扫描多个 Call 行权价
                        best_call = None
                        for call_pct in [1.05, 1.08, 1.10, 1.12]:
                            K_call = max(cost_basis * call_pct, S * 1.02)
                            premium = self.get_option_price_hkd(S, K_call, self.dte, sigma, "CALL")
                            if premium >= self.min_premium:
                                if best_call is None or premium > best_call["premium"]:
                                    best_call = {"K": K_call, "premium": premium}

                        if best_call:
                            K_call = best_call["K"]
                            net_premium = best_call["premium"] - self.COMMISSION
                            self.cash += net_premium
                            exp_date = current_date + timedelta(days=self.dte)
                            self._last_trade_month = cur_month

                            self.strategy.option_position = Position(
                                code=f"CALL_{current_date}",
                                type="CALL", strike=K_call, quantity=1,
                                premium=net_premium, open_date=current_date,
                                expiration=exp_date,
                                cost_basis=cost_basis
                            )
                            self.strategy.state = WheelState.SELL_CALL
                            self.strategy.record_premium(net_premium)

                            self.trades.append({
                                "date": str(current_date), "action": "SELL_CALL",
                                "price": S, "strike": round(K_call, 2),
                                "cost_basis": round(cost_basis, 2),
                                "sigma": round(sigma, 3), "premium": round(net_premium, 0),
                                "expiration": str(exp_date)
                            })
                            print(f"  📤 [{current_date}] SELL_CALL S={S:.1f}  K={K_call:.1f}  σ={sigma:.1%}  权利金=HKD{net_premium:.0f}")

            # ── SELL_CALL → 到期判断 ────────────────
            elif self.strategy.state == WheelState.SELL_CALL:
                opt = self.strategy.option_position
                if opt and current_date >= opt.expiration:
                    sh = self.strategy.stock_holding
                    if S >= opt.strike:
                        # Call 被行权，卖出股票
                        proceeds = opt.strike * self.LOT_SIZE
                        self.cash += proceeds
                        stock_pnl = (opt.strike - sh.cost_basis) * self.LOT_SIZE
                        self.trades.append({
                            "date": str(current_date), "action": "CALL_ASSIGNED",
                            "price": S, "strike": round(opt.strike, 2),
                            "cost_basis": round(sh.cost_basis, 2),
                            "proceeds": round(proceeds, 0),
                            "stock_pnl": round(stock_pnl, 0),
                            "premium_kept": round(opt.premium, 0)
                        })
                        print(f"  🏁 [{current_date}] CALL 被行权 S={S:.1f}  K={opt.strike:.1f}  股票盈亏 HKD{stock_pnl:.0f}")
                        self.strategy.stock_holding = None
                        self.strategy.state = WheelState.IDLE
                    else:
                        # Call 过期作废，继续持股
                        self.trades.append({
                            "date": str(current_date), "action": "CALL_EXPIRED",
                            "price": S, "strike": round(opt.strike, 2),
                            "premium_kept": round(opt.premium, 0)
                        })
                        print(f"  ✅ [{current_date}] CALL 作废   S={S:.1f}  K={opt.strike:.1f}  入袋 HKD{opt.premium:.0f}")
                        self.strategy.state = WheelState.HOLD_STOCK
                    self.strategy.option_position = None

            # ── 日内组合价值统计 ────────────────────
            stock_value = (self.strategy.stock_holding.quantity * S
                           if self.strategy.stock_holding else 0.0)
            total_value = self.cash + stock_value
            ret_pct = (total_value - self.initial_capital) / self.initial_capital * 100

            self.daily_records.append({
                "date": current_date,
                "price": S,
                "sigma": round(sigma, 4),
                "state": self.strategy.state.value,
                "cash": round(self.cash, 0),
                "stock_value": round(stock_value, 0),
                "total_value": round(total_value, 0),
                "return_pct": round(ret_pct, 4),
                "cum_premium": round(self.strategy.total_premium_collected, 0),
            })

    # ── 打印报告 & 返回摘要 ──────────────────────

    def print_report(self, save_prefix: str = "real") -> dict:
        df = pd.DataFrame(self.daily_records)
        tf = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

        final_value  = df["total_value"].iloc[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        total_premium = self.strategy.total_premium_collected

        start_dt = df["date"].iloc[0]
        end_dt   = df["date"].iloc[-1]
        years    = (end_dt - start_dt).days / 365.0

        ann_return = ((1 + total_return / 100) ** (1 / max(years, 0.1)) - 1) * 100

        df["peak"]     = df["total_value"].cummax()
        df["drawdown"] = (df["total_value"] - df["peak"]) / df["peak"] * 100
        max_dd         = df["drawdown"].min()
        max_dd_date    = df.loc[df["drawdown"].idxmin(), "date"]

        df_m = df.copy()
        df_m["month"] = pd.to_datetime(df_m["date"]).dt.to_period("M")
        monthly = (df_m.groupby("month")["total_value"]
                   .last().pct_change() * 100).reset_index()
        monthly.columns = ["month", "monthly_ret"]
        monthly = monthly.dropna()

        # 交易统计
        n_sell_put = n_put_expired = n_put_assign = 0
        n_sell_call = n_call_expired = n_call_assign = 0
        avg_put_premium = avg_call_premium = 0.0
        if not tf.empty:
            n_sell_put     = len(tf[tf.action == "SELL_PUT"])
            n_put_expired  = len(tf[tf.action == "PUT_EXPIRED"])
            n_put_assign   = len(tf[tf.action == "PUT_ASSIGNED"])
            n_sell_call    = len(tf[tf.action == "SELL_CALL"])
            n_call_expired = len(tf[tf.action == "CALL_EXPIRED"])
            n_call_assign  = len(tf[tf.action == "CALL_ASSIGNED"])
            if n_sell_put > 0:
                avg_put_premium = tf[tf.action == "SELL_PUT"]["premium"].mean()
            if n_sell_call > 0:
                avg_call_premium = tf[tf.action == "SELL_CALL"]["premium"].mean()

        win_rate = (n_put_expired + n_call_expired) / max(n_sell_put + n_sell_call, 1) * 100

        label = self.label

        print(f"\n{'='*64}")
        print(f"  📈  [{label}]  腾讯 Wheel 策略回测报告")
        print(f"{'='*64}")
        print(f"""
  初始资金   HKD {self.initial_capital:>10,.0f}   →   最终 HKD {final_value:>10,.0f}
  总收益率   {total_return:+.2f}%   年化 {ann_return:+.2f}%   共 {years:.1f} 年
  累计权利金 HKD {total_premium:>10,.0f}
  最大回撤   {max_dd:.2f}%  ({max_dd_date})
  交易次数   Put {n_sell_put} 次（均值 {avg_put_premium:.0f} HKD）
             Call {n_sell_call} 次（均值 {avg_call_premium:.0f} HKD）
  综合胜率   {win_rate:.0f}%
        """)

        pos_months = (monthly["monthly_ret"] >= 0).sum()
        neg_months = (monthly["monthly_ret"] < 0).sum()
        print(f"  盈利月 {pos_months}  亏损月 {neg_months}")

        # 保存 CSV
        out = Path(__file__).parent / "backtest_results"
        out.mkdir(exist_ok=True)
        df.to_csv(out / f"{save_prefix}_daily.csv", index=False)
        if not tf.empty:
            tf.to_csv(out / f"{save_prefix}_trades.csv", index=False)

        return {
            "label":           label,
            "iv_filter":       self.iv_filter,
            "final_value":     round(final_value, 0),
            "total_return":    round(total_return, 2),
            "ann_return":      round(ann_return, 2),
            "total_premium":   round(total_premium, 0),
            "max_dd":          round(max_dd, 2),
            "max_dd_date":     str(max_dd_date),
            "n_sell_put":      n_sell_put,
            "n_put_expired":   n_put_expired,
            "n_put_assign":    n_put_assign,
            "n_sell_call":     n_sell_call,
            "n_call_expired":  n_call_expired,
            "n_call_assign":   n_call_assign,
            "avg_put_premium": round(avg_put_premium, 0),
            "avg_call_premium":round(avg_call_premium, 0),
            "win_rate":        round(win_rate, 1),
            "pos_months":      int(pos_months),
            "neg_months":      int(neg_months),
            "years":           round(years, 1),
            "daily_df":        df,
            "trades_df":       tf,
            "monthly_df":      monthly,
        }


# ─────────────────────────────────────────────
#  入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="腾讯 Wheel 策略真实数据回测")
    parser.add_argument("--capital",    type=float, default=100_000, help="初始资金 HKD")
    parser.add_argument("--start",      default="2020-01-01",        help="回测开始日期")
    parser.add_argument("--end",        default="2025-12-31",        help="回测结束日期")
    parser.add_argument("--host",       default="127.0.0.1",         help="OpenD 地址")
    parser.add_argument("--port",       type=int, default=11111,      help="OpenD 端口")
    parser.add_argument("--iv-filter",  type=float, default=0.0,
                        help="IV 过滤阈值（默认0=无过滤，与实盘一致）")
    parser.add_argument("--strike-otm", type=float, default=0.05,
                        help="Put 行权价 OTM 幅度（默认5%%，与实盘一致）")
    parser.add_argument("--dte", type=int, default=30,
                        help="到期天数（默认30，与实盘一致）")
    parser.add_argument("--compare",    action="store_true",
                        help="强制跑多组 IV×行权价 全对比")
    args = parser.parse_args()

    print("=" * 64)
    print("  🚀  腾讯 Wheel 策略回测（真实富途数据）")
    print("=" * 64)

    df = fetch_futu_kline(
        ticker="HK.00700",
        start=args.start,
        end=args.end,
        host=args.host,
        port=args.port,
    )

    if df is None or df.empty:
        print("\n❌ 无法获取数据，退出")
        sys.exit(1)

    # 构建对比矩阵
    if args.compare:
        # 完整矩阵：IV×行权价
        configs = [
            (0.0,  0.05, "无过滤 -5%",   "no_iv_otm5"),
            (0.0,  0.10, "无过滤 -10%",  "no_iv_otm10"),
            (0.35, 0.05, "IV>35% -5%",  "iv35_otm5"),
            (0.35, 0.10, "IV>35% -10%", "iv35_otm10"),
        ]
    elif args.iv_filter is not None and args.strike_otm is not None:
        # 单组参数（默认值与实盘一致）
        lbl = f"IV>{args.iv_filter:.0%} -{args.strike_otm:.0%}"
        pfx = f"iv{int(args.iv_filter*100)}_otm{int(args.strike_otm*100)}"
        configs = [(args.iv_filter, args.strike_otm, lbl, pfx)]
    elif args.strike_otm is not None:
        # 固定行权价，对比 IV
        otm = args.strike_otm
        configs = [
            (0.0,  otm, f"无IV过滤 -{otm:.0%}", f"no_iv_otm{int(otm*100)}"),
            (0.25, otm, f"IV>25% -{otm:.0%}",  f"iv25_otm{int(otm*100)}"),
            (0.35, otm, f"IV>35% -{otm:.0%}",  f"iv35_otm{int(otm*100)}"),
            (0.45, otm, f"IV>45% -{otm:.0%}",  f"iv45_otm{int(otm*100)}"),
        ]
    else:
        # 默认单组：与实盘一致（无IV过滤，OTM=5%）
        configs = [
            (0.0,  0.05, "无过滤 -5%行权（与实盘一致）", "no_iv_otm5"),
        ]

    results = []
    for iv_val, otm_val, label, prefix in configs:
        print(f"\n{'─'*64}")
        print(f"  ▶  运行组：{label}")
        print(f"{'─'*64}")
        bt = RealDataBacktester(
            initial_capital=args.capital,
            iv_filter=iv_val,
            strike_otm=otm_val,
            dte=args.dte,              # 与实盘一致
            min_premium=900,           # 与实盘一致（900 HKD）
            label=label,
        )
        bt.run(df)
        r = bt.print_report(save_prefix=prefix)
        results.append(r)

    # 生成对比 HTML 报告（多组时）
    if len(results) > 1:
        out_html = Path(__file__).parent / "backtest_results" / "comparison.html"
        _write_comparison_html(results, df, out_html)



def _write_comparison_html(results: list, price_df: pd.DataFrame, out_path: Path):
    """生成多组 IV 对比的 HTML 报告"""
    import json

    # 颜色方案
    colors = ["#6366f1", "#10b981", "#f59e0b", "#ef4444"]

    # 构建 equity curve 数据
    series_data = []
    for i, r in enumerate(results):
        ddf = r["daily_df"]
        dates_js = [str(d) for d in ddf["date"]]
        vals_js   = [round(v, 0) for v in ddf["total_value"]]
        sigma_js  = [round(float(s) * 100, 1) for s in ddf["sigma"]]
        series_data.append({
            "label": r["label"],
            "color": colors[i % len(colors)],
            "dates": dates_js,
            "values": vals_js,
            "sigma": sigma_js,
        })

    # 交易表格 HTML
    trade_tables = ""
    for r in results:
        tf = r["trades_df"]
        if tf.empty:
            continue
        rows = ""
        for _, row in tf.iterrows():
            action = row.get("action", "")
            icon = {"SELL_PUT": "📤", "PUT_EXPIRED": "✅", "PUT_ASSIGNED": "⚡",
                    "SELL_CALL": "📤", "CALL_EXPIRED": "✅", "CALL_ASSIGNED": "🏁"}.get(action, "")
            premium = row.get("premium", row.get("premium_kept", ""))
            sigma_val = row.get("sigma", "")
            sigma_str = f"{float(sigma_val):.1%}" if sigma_val != "" else "-"
            rows += f"""<tr>
              <td>{row.get('date','')}</td>
              <td>{icon} {action}</td>
              <td>{row.get('price','')}</td>
              <td>{row.get('strike','')}</td>
              <td>{sigma_str}</td>
              <td>HKD {premium}</td>
            </tr>"""
        trade_tables += f"""
        <div class="trade-section" id="trades-{r['label'].replace('>','').replace('%','')}">
          <h3>{r['label']} 交易明细</h3>
          <table class="trade-table">
            <thead><tr><th>日期</th><th>操作</th><th>现价</th><th>行权价</th><th>σ</th><th>权利金</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    # 指标卡片
    cards_html = ""
    for r, color in zip(results, colors):
        ann = r["ann_return"]
        dd  = r["max_dd"]
        wr  = r["win_rate"]
        sp  = r["n_sell_put"]
        pm  = r["total_premium"]
        avg_p = r["avg_put_premium"]
        cards_html += f"""
      <div class="card" style="border-top: 3px solid {color}">
        <div class="card-label">{r['label']}</div>
        <div class="card-metric" style="color:{color}">{ann:+.2f}%</div>
        <div class="card-sub">年化收益</div>
        <div class="card-row"><span>总收益</span><span>{r['total_return']:+.2f}%</span></div>
        <div class="card-row"><span>最大回撤</span><span style="color:#ef4444">{dd:.2f}%</span></div>
        <div class="card-row"><span>综合胜率</span><span>{wr:.0f}%</span></div>
        <div class="card-row"><span>卖Put次数</span><span>{sp}</span></div>
        <div class="card-row"><span>累计权利金</span><span>HKD {pm:,.0f}</span></div>
        <div class="card-row"><span>均次Put权利金</span><span>HKD {avg_p:,.0f}</span></div>
        <div class="card-row"><span>最终资产</span><span>HKD {r['final_value']:,.0f}</span></div>
      </div>"""

    # IV 过滤效果表格
    iv_compare_rows = ""
    for r in results:
        iv_compare_rows += f"""<tr>
          <td>{r['label']}</td>
          <td>{r['n_sell_put']}</td>
          <td>HKD {r['avg_put_premium']:,.0f}</td>
          <td>{r['win_rate']:.0f}%</td>
          <td>{r['ann_return']:+.2f}%</td>
          <td>{r['max_dd']:.2f}%</td>
          <td>HKD {r['total_premium']:,.0f}</td>
        </tr>"""

    series_json = json.dumps(series_data, ensure_ascii=False)
    price_dates = [str(d) for d in price_df["date"]]
    price_vals  = [round(float(v), 1) for v in price_df["Close"]]

    # 先拼好 tabs_html（避免 f-string 里嵌套引号语法错误）
    tabs_parts = []
    for i, r in enumerate(results):
        tab_id = r["label"].replace(">", "").replace("%", "")
        active_cls = " active" if i == 0 else ""
        tabs_parts.append(
            f'<button class="tab{active_cls}" onclick="showTab(this,\'trades-{tab_id}\')">'
            f'{r["label"]}</button>'
        )
    tabs_html = "\n    ".join(tabs_parts)

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>腾讯 Wheel 策略 IV 过滤对比报告</title>
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
  /* 指标卡片 */
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
  /* 图表 */
  .chart-box{{background:rgba(255,255,255,.03);border-radius:14px;padding:24px;
              margin-bottom:24px;border:1px solid rgba(255,255,255,.06)}}
  .chart-title{{font-size:1rem;font-weight:600;margin-bottom:16px;color:#cbd5e1}}
  /* 对比表格 */
  .compare-table{{width:100%;border-collapse:collapse;font-size:.9rem}}
  .compare-table th{{background:rgba(99,102,241,.2);padding:10px 14px;
                      text-align:left;font-weight:600;color:#818cf8}}
  .compare-table td{{padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.06)}}
  .compare-table tr:hover td{{background:rgba(255,255,255,.03)}}
  /* 交易明细 */
  .trade-section{{margin-bottom:32px}}
  .trade-section h3{{font-size:1rem;color:#94a3b8;margin-bottom:12px}}
  .trade-table{{width:100%;border-collapse:collapse;font-size:.82rem}}
  .trade-table th{{background:rgba(255,255,255,.06);padding:8px 12px;text-align:left}}
  .trade-table td{{padding:7px 12px;border-bottom:1px solid rgba(255,255,255,.04)}}
  .trade-table tr:hover td{{background:rgba(255,255,255,.02)}}
  /* 标签页 */
  .tabs{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}}
  .tab{{padding:6px 16px;border-radius:20px;cursor:pointer;font-size:.85rem;
         background:rgba(255,255,255,.06);color:#94a3b8;border:none;transition:all .2s}}
  .tab.active{{background:rgba(99,102,241,.3);color:#a5b4fc}}
  .tab-content{{display:none}}.tab-content.active{{display:block}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.75rem;
           background:rgba(99,102,241,.2);color:#a5b4fc;margin-left:6px}}
</style>
</head>
<body>
<div class="header">
  <h1>腾讯 Wheel 策略 ─ IV 过滤器对比报告</h1>
  <p>HK.00700 · 2020-01-01 → 2025-12-31 · Black-Scholes 定价 · 富途 OpenD 数据 · DTE=45</p>
</div>

<div class="container">
  <!-- 指标卡片 -->
  <div class="section-title">📊 各方案指标对比</div>
  <div class="cards">{cards_html}</div>

  <!-- 资金曲线图 -->
  <div class="section-title">📈 资金曲线对比</div>
  <div class="chart-box">
    <div class="chart-title">组合总资产 (HKD)</div>
    <canvas id="equityChart" height="300"></canvas>
  </div>

  <!-- 腾讯股价 + 波动率 -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px">
    <div class="chart-box">
      <div class="chart-title">腾讯股价 (HKD)</div>
      <canvas id="priceChart" height="250"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">历史波动率 σ (%)</div>
      <canvas id="sigmaChart" height="250"></canvas>
    </div>
  </div>

  <!-- 对比表 -->
  <div class="section-title">🔢 关键指标汇总</div>
  <div class="chart-box">
    <table class="compare-table">
      <thead><tr>
        <th>方案</th><th>卖Put次数</th><th>均次权利金</th>
        <th>胜率</th><th>年化收益</th><th>最大回撤</th><th>累计权利金</th>
      </tr></thead>
      <tbody>{iv_compare_rows}</tbody>
    </table>
  </div>

  <!-- 交易明细标签页 -->
  <div class="section-title">📋 交易明细</div>
  <div class="tabs" id="tradeTabs">
    {tabs_html}
  </div>
  {trade_tables}
</div>

<script>
const seriesData = {series_json};
const priceDates = {json.dumps(price_dates)};
const priceVals  = {json.dumps(price_vals)};

// 资金曲线
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
    plugins: {{legend:{{position:'top',labels:{{color:'#94a3b8', boxWidth:12}}}},
               tooltip:{{callbacks:{{label:ctx=>`${{ctx.dataset.label}}: HKD ${{ctx.parsed.y.toLocaleString()}}`}}}}}},
    scales: {{
      x: {{ticks:{{color:'#64748b',maxTicksLimit:12}}, grid:{{color:'rgba(255,255,255,.04)'}}}},
      y: {{ticks:{{color:'#64748b',callback:v=>'HKD '+v.toLocaleString()}}, grid:{{color:'rgba(255,255,255,.06)'}}}}
    }}
  }}
}});

// 腾讯股价
const prCtx = document.getElementById('priceChart').getContext('2d');
new Chart(prCtx, {{
  type: 'line',
  data: {{
    labels: priceDates,
    datasets: [{{
      label: '腾讯股价',
      data: priceVals,
      borderColor: '#f59e0b',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
    }}]
  }},
  options: {{
    responsive:true, plugins:{{legend:{{display:false}}}},
    scales: {{
      x:{{ticks:{{color:'#64748b',maxTicksLimit:8}}, grid:{{color:'rgba(255,255,255,.04)'}}}},
      y:{{ticks:{{color:'#64748b'}}, grid:{{color:'rgba(255,255,255,.06)'}}}}
    }}
  }}
}});

// 波动率
const sgCtx = document.getElementById('sigmaChart').getContext('2d');
new Chart(sgCtx, {{
  type: 'line',
  data: {{
    labels: seriesData[0].dates,
    datasets: [
      {{
        label: 'σ (%)',
        data: seriesData[0].sigma,
        borderColor: '#818cf8',
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
      }},
      {{
        label: 'IV 35% 线',
        data: Array(seriesData[0].dates.length).fill(35),
        borderColor: '#ef4444',
        borderWidth: 1,
        borderDash: [4,4],
        pointRadius: 0,
        fill: false,
      }},
      {{
        label: 'IV 25% 线',
        data: Array(seriesData[0].dates.length).fill(25),
        borderColor: '#f59e0b',
        borderWidth: 1,
        borderDash: [4,4],
        pointRadius: 0,
        fill: false,
      }}
    ]
  }},
  options: {{
    responsive:true,
    plugins:{{legend:{{position:'top',labels:{{color:'#94a3b8',boxWidth:12}}}}}},
    scales: {{
      x:{{ticks:{{color:'#64748b',maxTicksLimit:8}}, grid:{{color:'rgba(255,255,255,.04)'}}}},
      y:{{ticks:{{color:'#64748b',callback:v=>v+'%'}}, grid:{{color:'rgba(255,255,255,.06)'}}}}
    }}
  }}
}});

// 交易明细标签页
function showTab(btn, id) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.trade-section').forEach(t => t.style.display = 'none');
  btn.classList.add('active');
  const el = document.getElementById(id);
  if (el) el.style.display = 'block';
}}
// 初始化：只显示第一个
document.querySelectorAll('.trade-section').forEach((el, i) => {{
  el.style.display = i === 0 ? 'block' : 'none';
}});
</script>
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"\n  📊 对比报告已生成 → {out_path}")


if __name__ == "__main__":
    main()
