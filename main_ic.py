#!/usr/bin/env python3
"""
Iron Condor 自动交易主程序
支持:
- --dry-run: 模拟模式（不下单）
- --once: 执行一次退出
- --daemon: 常驻运行（默认）
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from scipy.stats import norm

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import IRON_CONDOR_CONFIG as CONFIG, STOCK_CONFIG
from data import FutuDataProvider as DataFeed
from ic_strategy import ICStrategy, ICState

# 配置日志
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "ic_bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def black_scholes_premium(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    """
    Black-Scholes 期权定价模型
    简化版：假设无股息
    """
    from math import exp, log, sqrt
    from scipy.stats import norm
    
    if T <= 0:
        return 0
    
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    
    if option_type.upper() == "CALL":
        premium = S * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)
    else:  # PUT
        premium = K * exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    
    return max(premium, 0.01)


def find_ic_options(option_chain, current_price: float, config: Dict) -> Dict:
    """
    从期权链中找到 Iron Condor 的4条腿
    使用 Black-Scholes 估算理论价格
    确保4条腿同一到期日
    """
    import re
    from datetime import datetime
    
    otm = config.get("otm", 0.05)
    wing = config.get("wing", 0.08)
    dte = config.get("dte", 45)  # 2026-04-06回测验证: DTE45全面优于DTE30
    
    # 计算目标行权价（铁鹰：PUT侧在下方，CALL侧在上方）
    # PUT 侧: sell_put @ -5%OTM，buy_put @ -5%OTM-8%Wing = -13%
    # CALL 侧: sell_call @ +5%OTM，buy_call @ +5%OTM+8%Wing = +13%
    sell_put_k  = int(current_price * (1 - otm))           # -5%
    buy_put_k   = int(current_price * (1 - otm - wing))    # -13%
    sell_call_k = int(current_price * (1 + otm))           # +5%  ← 修正（原代码 1+otm-wing 错误）
    buy_call_k  = int(current_price * (1 + otm + wing))    # +13% ← 修正
    
    # === 第一步：从期权链获取所有到期日，选择最接近 DTE 的 ===
    # 港股腾讯期权只有周度和月度到期日，需要从实际存在的日期中选择
    option_chain = option_chain.copy()
    option_chain["exp_code"] = option_chain["code"].apply(
        lambda x: re.search(r'TCH(\d{6})', x).group(1) if re.search(r'TCH(\d{6})', x) else ""
    )
    option_chain["exp_date"] = option_chain["exp_code"].apply(
        lambda x: datetime.strptime(x, "%y%m%d").date() if x else None
    )
    
    # 获取所有唯一到期日
    all_expirations = sorted(option_chain["exp_date"].dropna().unique())
    today = date.today()
    target_dte = today + timedelta(days=dte)
    
    # DEBUG: 打印所有到期日
    logger.info(f"DEBUG 可用到期日: {[str(e) for e in all_expirations[:10]]}")
    
# 选择到期日（选择最接近 DTE 的）
    valid_exps = [e for e in all_expirations if e >= today]
    
    if len(valid_exps) > 0:
        # 找最接近 DTE 的到期日
        target_exp = min(valid_exps, key=lambda e: abs((e - today).days - dte))
    else:
        logger.error(f"⚠️ 没有可用到期日")
        return None
    
    actual_dte = (target_exp - today).days
    logger.info(f"📅 目标到期日: {target_exp} (实际DTE={actual_dte}, 目标DTE={dte})")
    
    # 计算理论参数
    T_years = dte / 365
    r = 0.04  # 4% 利率
    sigma = 0.35  # 35% IV
    
    # 过滤到目标到期日的期权（使用上面新逻辑选择的正确到期日）
    chain = option_chain[option_chain["exp_date"] == target_exp]
    
    if chain.empty:
        logger.warning("无期权数据，使用理论定价")
        return {
            "legs": [], 
            "expiration": target_exp,
            "sell_put_strike": sell_put_k,
            "buy_put_strike": buy_put_k,
            "sell_call_strike": sell_call_k,
            "buy_call_strike": buy_call_k,
        }
    
    # === 第二步：筛选4条腿 ===
    # Iron Condor 结构: Buy Put < Sell Put < 股价 < Sell Call < Buy Call
    legs = []
    
    # PUT 边：Sell Put 必须是价内（行权价 < 股价），Buy Put 必须更虚值（行权价更低）
    puts = chain[chain["option_type"] == "PUT"].copy()
    if not puts.empty:
        # Sell PUT：选价内 Put（行权价 < 股价），且距离目标 sell_put_k 最近
        itm_puts = puts[puts["strike_price"] < current_price].copy()
        if not itm_puts.empty:
            itm_puts["strike_dist"] = abs(itm_puts["strike_price"] - sell_put_k)
            itm_puts = itm_puts.sort_values("strike_dist")
            best_sell = itm_puts.iloc[0]
            logger.info(f"🔍 Sell PUT 候选: {[f'{r['strike_price']}' for _, r in itm_puts.head(5).iterrows()]}, 选中: {best_sell['strike_price']}")
        else:
            # 如果没有价内，选最近的
            puts_copy = puts.copy()
            puts_copy["strike_dist"] = abs(puts_copy["strike_price"] - sell_put_k)
            puts_copy = puts_copy.sort_values("strike_dist")
            best_sell = puts_copy.iloc[0]
            logger.warning(f"⚠️ 无价内Put，选择最近的: {best_sell['strike_price']}")
        
        prem = black_scholes_premium(current_price, best_sell["strike_price"], T_years, r, sigma, "PUT")
        legs.append({
            "type": "PUT", "side": "sell",
            "code": best_sell["code"],
            "strike": float(best_sell["strike_price"]),
            "premium_estimate": prem * 100,
        })
        
        # Buy PUT：选更虚值 Put（行权价 < Sell Put）
        otm_puts = puts[puts["strike_price"] < best_sell["strike_price"]].copy()
        if not otm_puts.empty:
            otm_puts["strike_dist"] = abs(otm_puts["strike_price"] - buy_put_k)
            otm_puts = otm_puts.sort_values("strike_dist")
            best_buy = otm_puts.iloc[0]
            logger.info(f"🔍 Buy PUT 候选: {[f'{r['strike_price']}' for _, r in otm_puts.head(5).iterrows()]}, 选中: {best_buy['strike_price']}")
        else:
            # 如果没有更虚值的，选距离目标 buy_put_k 最近的
            puts_copy = puts.copy()
            puts_copy["strike_dist"] = abs(puts_copy["strike_price"] - buy_put_k)
            puts_copy = puts_copy.sort_values("strike_dist")
            best_buy = puts_copy.iloc[0]
            logger.warning(f"⚠️ 无更虚值Put，选择最近的: {best_buy['strike_price']}")
        
        prem = black_scholes_premium(current_price, best_buy["strike_price"], T_years, r, sigma, "PUT")
        legs.append({
            "type": "PUT", "side": "buy",
            "code": best_buy["code"],
            "strike": float(best_buy["strike_price"]),
            "premium_estimate": prem * 100,
        })
    
    # CALL 边：Sell Call 必须是价内（行权价 > 股价），Buy Call 必须更虚值（行权价更高）
    calls = chain[chain["option_type"] == "CALL"].copy()
    if not calls.empty:
        # Sell CALL：选价内 Call（行权价 > 股价），且距离目标 sell_call_k 最近
        itm_calls = calls[calls["strike_price"] > current_price].copy()
        if not itm_calls.empty:
            itm_calls["strike_dist"] = abs(itm_calls["strike_price"] - sell_call_k)
            itm_calls = itm_calls.sort_values("strike_dist")
            best_sell = itm_calls.iloc[0]
            logger.info(f"🔍 Sell CALL 候选: {[f'{r['strike_price']}' for _, r in itm_calls.head(5).iterrows()]}, 选中: {best_sell['strike_price']}")
        else:
            calls_copy = calls.copy()
            calls_copy["strike_dist"] = abs(calls_copy["strike_price"] - sell_call_k)
            calls_copy = calls_copy.sort_values("strike_dist")
            best_sell = calls_copy.iloc[0]
            logger.warning(f"⚠️ 无价内Call，选择最近的: {best_sell['strike_price']}")
        
        prem = black_scholes_premium(current_price, best_sell["strike_price"], T_years, r, sigma, "CALL")
        legs.append({
            "type": "CALL", "side": "sell",
            "code": best_sell["code"],
            "strike": float(best_sell["strike_price"]),
            "premium_estimate": prem * 100,
        })
        
        # Buy CALL：选更虚值 Call（行权价 > Sell Call）
        otm_calls = calls[calls["strike_price"] > best_sell["strike_price"]].copy()
        if not otm_calls.empty:
            otm_calls["strike_dist"] = abs(otm_calls["strike_price"] - buy_call_k)
            otm_calls = otm_calls.sort_values("strike_dist")
            best_buy = otm_calls.iloc[0]
            logger.info(f"🔍 Buy CALL 候选: {[f'{r['strike_price']}' for _, r in otm_calls.head(5).iterrows()]}, 选中: {best_buy['strike_price']}")
        else:
            calls_copy = calls.copy()
            calls_copy["strike_dist"] = abs(calls_copy["strike_price"] - buy_call_k)
            calls_copy = calls_copy.sort_values("strike_dist")
            best_buy = calls_copy.iloc[0]
            logger.warning(f"⚠️ 无更虚值Call，选择最近的: {best_buy['strike_price']}")
        
        prem = black_scholes_premium(current_price, best_buy["strike_price"], T_years, r, sigma, "CALL")
        legs.append({
            "type": "CALL", "side": "buy",
            "code": best_buy["code"],
            "strike": float(best_buy["strike_price"]),
            "premium_estimate": prem * 100,
        })
    
    return {
        "legs": legs,
        "expiration": target_exp,
        "sell_put_strike": sell_put_k,
        "buy_put_strike": buy_put_k,
        "sell_call_strike": sell_call_k,
        "buy_call_strike": buy_call_k,
    }


class ICTrader:
    """Iron Condor 自动交易员"""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.data = DataFeed()
        self.strategy = ICStrategy()
        self.last_check = 0
        self.check_interval = 300  # 5分钟检查一次

    def connect(self) -> bool:
        """连接数据源"""
        if not self.data.connect():
            logger.error("连接失败")
            return False
        return True

    def get_real_time_prices(self, option_codes: list) -> Dict[str, Dict]:
        """
        获取期权实时盘口价格（bid/ask/mid）
        - mid_price = (bid + ask) / 2，作为首选下单价
        - bid/ask 作为备用（重试时逐步调整）
        返回 {code: {"bid": x, "ask": x, "mid": x, "last": x}}
        """
        prices = {}
        for code in option_codes:
            try:
                # 订阅 ORDER_BOOK + QUOTE
                self.data.quote_ctx.subscribe([code], ["ORDER_BOOK", "QUOTE"])
                time.sleep(0.5)

                ret_ob, ob_data = self.data.quote_ctx.get_order_book(code)
                ret_q,  q_data  = self.data.quote_ctx.get_stock_quote([code])

                bid = 0.0
                ask = 0.0
                last = 0.0

                if ret_ob == 0 and ob_data:
                    bid_list = ob_data.get("Bid", [])
                    ask_list = ob_data.get("Ask", [])
                    if bid_list:
                        bid = float(bid_list[0][0])
                    if ask_list:
                        ask = float(ask_list[0][0])

                if ret_q == 0 and not q_data.empty:
                    last = float(q_data.iloc[0].get("last_price", 0))

                # 中间价：有 bid/ask 就取均值，否则用 last_price
                if bid > 0 and ask > 0:
                    mid = round((bid + ask) / 2, 2)
                elif last > 0:
                    mid = last
                else:
                    mid = 0.0

                prices[code] = {"bid": bid, "ask": ask, "mid": mid, "last": last}
                logger.info(f"  {code}: bid={bid:.2f}  ask={ask:.2f}  mid={mid:.2f}  last={last:.2f}")

            except Exception as e:
                logger.error(f"  {code}: 获取价格失败 - {e}")
                prices[code] = {"bid": 0.0, "ask": 0.0, "mid": 0.0, "last": 0.0}
        return prices

    def open_position(self) -> Dict:
        """
        开仓 Iron Condor
        """
        logger.info("=" * 50)
        logger.info("🆕 开始 Iron Condor 开仓流程")
        logger.info("=" * 50)

        # 1. 获取正股价格
        stock_ticker = STOCK_CONFIG["ticker"]
        stock_price = self.data.get_stock_quote(stock_ticker)
        if not stock_price:
            logger.error("无法获取正股价格")
            return {"success": False, "reason": "无法获取正股价格"}

        current_price = stock_price["last_price"]
        logger.info(f"📈 当前股价: HKD {current_price:.2f}")

        # 2. 获取近期期权链
        option_chain = self.data.get_option_chain(stock_ticker)
        if option_chain is None or option_chain.empty:
            logger.error("无法获取期权链")
            return {"success": False, "reason": "无法获取期权链"}

        logger.info(f"📊 期权链: {len(option_chain)} 条")

        # 3. 找到 Iron Condor 的 4 条腿
        ic_info = find_ic_options(option_chain, current_price, CONFIG)
        legs = ic_info["legs"]

        if len(legs) < 4:
            logger.warning("期权链数据不完整，使用理论定价")
            # 使用 Black-Scholes 估算
            T = CONFIG.get("dte", 7) / 365
            r = 0.04  # 假设 4% 利率
            sigma = 0.35  # 假设 35% IV

            # 计算理论价格
            sell_put_k = ic_info["sell_put_strike"]
            buy_put_k = ic_info["buy_put_strike"]
            sell_call_k = ic_info["sell_call_strike"]
            buy_call_k = ic_info["buy_call_strike"]

            # 使用 find_ic_options 返回的实际到期日（从期权链获取的）
            target_exp = ic_info.get("expiration")
            if target_exp is None:
                # 如果没有返回到期日，从期权链重新获取
                option_chain = self.data.get_option_chain(stock_ticker)
                if option_chain is not None and not option_chain.empty:
                    expirations = option_chain["strike_time"].unique()
                    if len(expirations) > 0:
                        target_exp = min([date.fromisoformat(e) for e in expirations])
                if target_exp is None:
                    target_exp = date.today() + timedelta(days=CONFIG.get("dte", 7))
            
            exp_str = target_exp.strftime("%y%m%d")  # 260429 格式
            
            # 港股期权代码格式：HK.TCH{YYMMDD}{C/P}{行权价×1000}
            legs = [
                {"type": "PUT", "side": "sell", "code": f"HK.TCH{exp_str}P{int(sell_put_k*1000)}", "strike": sell_put_k},
                {"type": "PUT", "side": "buy", "code": f"HK.TCH{exp_str}P{int(buy_put_k*1000)}", "strike": buy_put_k},
                {"type": "CALL", "side": "sell", "code": f"HK.TCH{exp_str}C{int(sell_call_k*1000)}", "strike": sell_call_k},
                {"type": "CALL", "side": "buy", "code": f"HK.TCH{exp_str}C{int(buy_call_k*1000)}", "strike": buy_call_k},
            ]

            # 计算理论权利金
            for leg in legs:
                if leg["type"] == "PUT":
                    premium = black_scholes_premium(current_price, leg["strike"], T, r, sigma, "PUT")
                else:
                    premium = black_scholes_premium(current_price, leg["strike"], T, r, sigma, "CALL")
                leg["premium_estimate"] = premium * 100  # 每手100股

        # 4. 打印候选组合
        logger.info("\n📋 Iron Condor 组合建议:")
        logger.info(f"   股价: HKD {current_price:.2f}")
        logger.info(f"   参数: {CONFIG.get('otm', 0.05)*100:.0f}% OTM ± {CONFIG.get('wing', 0.08)*100:.0f}% Wing, DTE={CONFIG.get('dte', 45)}")

        total_premium = 0
        for leg in legs:
            side_str = "卖出" if leg["side"] == "sell" else "买入"
            if leg["type"] == "PUT":
                logger.info(f"   PUT {side_str}: 行权价 {leg['strike']}, 代码 {leg['code']}")
            else:
                logger.info(f"   CALL {side_str}: 行权价 {leg['strike']}, 代码 {leg['code']}")

            if leg["side"] == "sell":
                total_premium += leg.get("premium_estimate", 0)
            else:
                total_premium -= leg.get("premium_estimate", 0)

        logger.info(f"\n💰 理论净权利金: HKD {total_premium:.0f}")

        # 5. 获取真实价格（如果可用）
        if not self.dry_run:
            option_codes = [leg["code"] for leg in legs]
            logger.info("\n⏳ 获取实时盘口价格（中间价策略）...")

            real_prices = self.get_real_time_prices(option_codes)

            # 用中间价作为首次下单价
            real_net = 0
            all_prices_valid = True
            for leg in legs:
                code = leg["code"]
                p = real_prices.get(code, {})
                mid = p.get("mid", 0)
                bid = p.get("bid", 0)
                ask = p.get("ask", 0)

                if mid > 0:
                    price = mid
                elif leg.get("premium_estimate", 0) > 0:
                    price = round(leg["premium_estimate"] / 100, 2)  # 理论价（元/股→元/张）
                    logger.warning(f"  ⚠️ {code} 无盘口，使用 BS 理论价 {price:.2f}")
                    all_prices_valid = False
                else:
                    price = 0.01
                    all_prices_valid = False

                leg["order_price"] = round(price, 2)
                leg["bid_price"]   = bid
                leg["ask_price"]   = ask

                if leg["side"] == "sell":
                    real_net += price
                else:
                    real_net -= price

            logger.info(f"💰 预计净权利金（中间价）: HKD {real_net * 100:.2f} × 2张 = {real_net * 100 * 2:.2f} HKD/组")

            # 最低权利金检查
            min_premium = CONFIG.get("min_premium", 900)
            if real_net * 100 * 2 < min_premium:
                logger.warning(f"⚠️ 净权利金 {real_net * 100 * 2:.2f} HKD < 最低 {min_premium} HKD，跳过开仓")
                return {"success": False, "reason": f"权利金 {real_net * 100 * 2:.2f} HKD 低于最低 {min_premium} HKD"}
            else:
                logger.info(f"✅ 权利金检查通过: {real_net * 100 * 2:.2f} HKD >= {min_premium} HKD")
        else:
            # 模拟模式，用理论价作为 order_price
            for leg in legs:
                leg["order_price"] = round(leg.get("premium_estimate", 1) / 100, 2)
                leg["bid_price"]   = 0
                leg["ask_price"]   = 0

        # 6. 执行下单
        if self.dry_run:
            logger.info("\n⚠️ 模拟模式，不执行真实下单")
            logger.info("如需真实下单，请使用: python main_ic.py --daemon")
            return {
                "success": True,
                "dry_run": True,
                "legs": legs,
                "net_premium": total_premium,
                "current_price": current_price,
            }
        else:
            return self._execute_orders(legs, total_premium)
    def _execute_orders(self, legs: list, net_premium: float) -> Dict:
        """
        执行4条腿的下单
        
        价格策略（3轮）：
          第1轮：中间价 (bid+ask)/2      → 挂单10分钟
          第2轮：偏激进中间价            → 挂单10分钟  (sell向bid靠，buy向ask靠，各移动价差的25%)
          第3轮：直接 sell→bid, buy→ask  → 挂单10分钟（市场价，确保成交）
        
        每轮10分钟未成交则撤单进入下一轮。
        """
        from config import FUTU_CONFIG
        logger.info("\n🚀 开始执行下单（中间价策略，每轮10分钟）...")

        from futu import OpenSecTradeContext, TrdSide, OrderType, RET_OK, TrdEnv

        trade_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            filter_trdmarket="HK",
            security_firm="FUTUSECURITIES",
        )

        logger.info("✅ 交易通道已连接")

        acc_id = int(FUTU_CONFIG.get("real_acc_id", "281756481449956811"))
        trd_env = TrdEnv.REAL

        logger.info(f"📋 使用账户: {acc_id} (REAL)")
        
        # ========== 改进：顺序提交 + 要么全成要么全撤 ==========
        
        # 准备所有腿的订单信息
        all_legs_order_info = []
        for leg in legs:
            code = leg["code"]
            side = leg["side"]
            qty = 2  # 每组2张期权
            order_side = TrdSide.SELL if side == "sell" else TrdSide.BUY
            
            # 所有腿用中间价下单（按最佳实践），取整到2位小数
            mid = leg.get("order_price", 0.01)
            bid = leg.get("bid_price", 0.0)
            ask = leg.get("ask_price", 0.0)
            
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else leg.get("order_price", 0.01)
            first_price = round(max(mid, 0.01), 2)
            
            all_legs_order_info.append({
                "leg": leg,
                "code": code,
                "side": side,
                "qty": qty,
                "order_side": order_side,
                "first_price": first_price,
                "trd_env": trd_env,
                "acc_id": acc_id,
            })
        
        # 并行提交所有订单（同时下单构成铁鹰策略）
        def submit_single_leg(order_info, trade_ctx, max_retries=5, initial_delay=0.5):
            """提交单个订单，带重试机制处理频率限制错误"""
            leg = order_info["leg"]
            code = order_info["code"]
            order_side = order_info["order_side"]
            qty = order_info["qty"]
            price = order_info["first_price"]
            trd_env = order_info["trd_env"]
            acc_id = order_info["acc_id"]

            import time
            last_error = None
            delay = initial_delay

            for attempt in range(max_retries):
                try:
                    ret, data = trade_ctx.place_order(
                        code=code,
                        price=price,
                        qty=qty,
                        trd_side=order_side,
                        order_type=OrderType.NORMAL,
                        adjust_limit=0,
                        trd_env=trd_env,
                        acc_id=acc_id,
                    )

                    if ret != RET_OK:
                        error_str = str(data)
                        last_error = error_str

                        # 检查是否是"操作过快"错误需要重试
                        if "操作过快" in error_str and attempt < max_retries - 1:
                            logger.warning(f"   ⚠️ {code} 触发频率限制，{delay:.1f}秒后重试 ({attempt+1}/{max_retries})...")
                            time.sleep(delay)
                            # 指数退避：每次延迟翻倍
                            delay *= 2
                            continue
                        else:
                            return {
                                "code": code,
                                "order_id": None,
                                "success": False,
                                "error": error_str,
                            }

                    order_id = data.iloc[0]["order_id"]
                    return {
                        "code": code,
                        "order_id": order_id,
                        "price": price,
                        "success": True,
                    }
                except Exception as e:
                    last_error = str(e)
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2
                        continue
                    return {
                        "code": code,
                        "order_id": None,
                        "success": False,
                        "error": last_error,
                    }

            return {
                "code": code,
                "order_id": None,
                "success": False,
                "error": last_error or "max retries exceeded",
            }
        
        # 步骤1：同时提交所有订单
        logger.info("🚀 同时提交4条腿订单...")
        submitted_results = []
        
        # 检查是否在非交易时段（在非交易时段提交订单会卡在WAITING_SUBMIT）
        import datetime
        now = datetime.datetime.now()
        is_weekday = now.weekday() < 5  # 0-4 = 周一到周五
        hour = now.hour
        is_trading_hours = 9 <= hour < 16
        
        if not (is_weekday and is_trading_hours):
            day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            logger.warning(f"⚠️ 当前时间: {day_names[now.weekday()]} {hour}:00 (非港股交易时段)")
            logger.warning("⚠️ 订单已提交，开盘后请在富途牛牛手动确认成交")
            # 订单已提交但返回警告，让用户手动确认
        
        # 使用单个共享上下文（避免频繁创建连接）
        shared_trade_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            filter_trdmarket="HK",
            security_firm="FUTUSECURITIES",
        )

        import time
        # 先建立连接，等待一小段时间让连接稳定
        time.sleep(0.2)

        # 串行提交（每条腿间隔0.3秒，完全避开频率限制）
        # 注：铁鹰策略的核心是同时成交，串行提交不影响最终同时成交的结果
        logger.info("📝 提交4条腿订单（每条腿间隔0.3秒避开频率限制）...")
        for order_info in all_legs_order_info:
            result = submit_single_leg(order_info, shared_trade_ctx)
            submitted_results.append(result)
            if result["success"]:
                logger.info(f"   ✅ {result['code']} 订单已提交: {result['order_id']} @ HKD {result.get('price', 0):.2f}")
            else:
                logger.error(f"   ❌ {result['code']} 提交失败: {result.get('error', 'unknown')}")
            # 每条腿之间间隔0.3秒，避免触发频率限制
            time.sleep(0.3)

        shared_trade_ctx.close()
        failed_count = sum(1 for r in submitted_results if not r["success"])
        if failed_count > 0:
            logger.warning(f"⚠️ {failed_count}条腿提交失败，撤销已提交的订单...")
            from futu import ModifyOrderOp, RET_OK
            
            cancel_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                filter_trdmarket="HK",
                security_firm="FUTUSECURITIES",
            )
            for r in submitted_results:
                if r["success"] and r.get("order_id"):
                    try:
                        cancel_ctx.modify_order(
                            modify_order_op=ModifyOrderOp.CANCEL,
                            order_id=r["order_id"],
                            qty=0, price=0,
                            trd_env=trd_env,
                            acc_id=acc_id,
                        )
                    except:
                        pass
            cancel_ctx.close()
            return {"success": False, "reason": "部分订单提交失败，已撤销"}
        
        # 步骤2：同时监控所有订单（最多等5分钟）
        logger.info("🔄 同时监控4条腿的成交状态（最多5分钟）...")
        
        # 创建一个新的交易上下文用于查询
        monitor_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            filter_trdmarket="HK",
            security_firm="FUTUSECURITIES",
        )
        
        all_filled = False
        all_order_statuses = []  # 收集所有订单状态
        
        for tick in range(10):  # 最多5分钟（10次×30秒）
            time.sleep(30)
            
            # 同时查询所有订单状态
            filled_count = 0
            partial_count = 0  # 🔧 部分成交计数
            check_complete = True
            
            for r in submitted_results:
                order_id = r["order_id"]
                
                ret, od = monitor_ctx.order_list_query(
                    order_id=order_id,
                    trd_env=trd_env,
                    acc_id=acc_id,
                )
                
                if ret != RET_OK:
                    logger.warning(f"   ⚠️ 查询订单 {order_id} 失败: ret={ret}")
                    check_complete = False
                    continue
                
                if od.empty:
                    logger.warning(f"   ⚠️ 订单 {order_id} 无数据")
                    check_complete = False
                    continue
                
                status = str(od.iloc[0]["order_status"])
                dealt_qty = int(od.iloc[0].get("dealt_qty", 0) or 0)
                expected_qty = r.get("qty", 2)
                
                # 保存状态供后续使用
                all_order_statuses.append({"order_id": order_id, "status": status, "dealt_qty": dealt_qty})
                
                # 对 WAITING_SUBMIT 状态给出更明确的日志
                if status in ["WAITING_SUBMIT", "WAITING", "1"]:
                    logger.info(f"   ⏳ {order_id}: 状态={status} (等待提交中), dealt_qty={dealt_qty}/{expected_qty}")
                else:
                    logger.info(f"   📊 {order_id}: status={status}, dealt_qty={dealt_qty}/{expected_qty}")
                
                # 🔧 修复：严格判断完全成交（必须状态为FILLED_ALL且数量匹配）
                if status in ["FILLED_ALL", "2"] and dealt_qty >= expected_qty:
                    filled_count += 1
                elif dealt_qty > 0 and dealt_qty < expected_qty:
                    # 🔴 部分成交！危险状态
                    partial_count += 1
                    logger.warning(f"   ⚠️ 部分成交: {order_id} ({r.get('code','?')}): {dealt_qty}/{expected_qty}")
                    check_complete = False
                elif status in ["CANCELLED_ALL", "FAILED", "DELETED", "6", "7"]:
                    # CANCELLED_ALL = 撤单成功（订单已取消），不是失败！
                    # 这种情况应该视为"成交失败"（filled_count不增加），继续等待其他订单
                    if status == "CANCELLED_ALL":
                        logger.info(f"   ℹ️ 订单 {order_id} 已取消（撤单成功）")
                    else:
                        logger.warning(f"⚠️ 订单 {order_id} 失败: {status}")
                    # 继续等待其他订单，不直接break
                elif status in ["WAITING_SUBMIT", "WAITING", "1"]:
                    # 订单仍在等待提交，不是成交失败，继续等待
                    check_complete = False
                else:
                    # 仍在等待，继续监控
                    check_complete = False
            
            if check_complete:
                all_filled = (filled_count == len(submitted_results))
                break
            
            # 🔧 部分成交时提前终止等待
            if partial_count > 0:
                logger.warning(f"🔴 发现{partial_count}条腿部分成交，提前终止等待")
                break
            
            logger.info(f"   ⏳ { (tick+1)*30 }s | 已成交: {filled_count}/{len(submitted_results)} | 部分: {partial_count}")
        
        monitor_ctx.close()
        
        # 步骤3：要么全成，要么全撤
        if all_filled:
            logger.info("✅ 4条腿全部成交！铁鹰策略建仓成功")
            for r in submitted_results:
                logger.info(f"   📊 {r['code']} @ HKD {r.get('price', 0):.2f}")
            
            # 计算净权利金
            net_premium = 0
            for i, leg in enumerate(legs):
                side = leg["side"]
                price = submitted_results[i].get("price", 0)
                if side == "sell":
                    net_premium += price * 100  # 卖出收到权利金
                else:
                    net_premium -= price * 100  # 买入付出权利金
            
            return {
                "success": True,
                "legs": legs,
                "net_premium": net_premium,
                "orders": submitted_results,
            }
        else:
            # 有未成交的，全部撤销（增加重试机制）
            # 注意：需要导入 ModifyOrderOp 和 RET_OK
            from futu import ModifyOrderOp, RET_OK
            
            logger.warning("⚠️ 部分订单未成交，全部撤销...")
            
            # 🔧 修复：先查询每个订单最终状态，检测残留头寸
            partial_fills = []
            check_ctx_list = []
            
            for r in submitted_results:
                order_id = r.get("order_id")
                if not order_id:
                    continue
                
                # 查询该订单最终状态
                try:
                    chk = OpenSecTradeContext(
                        host=FUTU_CONFIG["host"],
                        port=FUTU_CONFIG["port"],
                        filter_trdmarket="HK",
                        security_firm="FUTUSECURITIES",
                    )
                    check_ctx_list.append(chk)
                    
                    ret_chk, od = chk.order_list_query(
                        order_id=order_id,
                        trd_env=trd_env,
                        acc_id=acc_id,
                    )
                    
                    if ret_chk == RET_OK and not od.empty:
                        final_status = str(od.iloc[0]["order_status"])
                        final_dealt_qty = int(od.iloc[0].get("dealt_qty", 0) or 0)
                        expected_qty = r.get("qty", 2)
                        
                        if final_dealt_qty > 0:
                            if final_dealt_qty >= expected_qty:
                                logger.warning(f"🔴 {r.get('code','?')} 已完全成交({final_dealt_qty}/{expected_qty})，无法撤销！")
                            else:
                                logger.critical(f"🔴🔴 {r.get('code','?')} 部分成交({final_dealt_qty}/{expected_qty})！不平衡头寸！")
                            
                            partial_fills.append({
                                "code": str(r.get('code', 'unknown')),
                                "dealt_qty": final_dealt_qty,
                                "qty": expected_qty,
                                "order_id": order_id,
                                "status": "FULL_FILLED" if final_dealt_qty >= expected_qty else "PARTIAL_FILLED",
                                "side": r.get("side", "unknown"),
                                "price": r.get("price", 0),
                            })
                except Exception as e:
                    logger.error(f"   ⚠️ 查询订单{order_id}状态失败: {e}")
            
            # 关闭所有检查连接
            for ctx in check_ctx_list:
                try: ctx.close()
                except: pass
            
            cancel_success = 0
            cancel_failed = 0
            
            cancel_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                filter_trdmarket="HK",
                security_firm="FUTUSECURITIES",
            )
            
            for r in submitted_results:
                order_id = r.get("order_id")
                
                # 跳过已成交的腿（无法撤销）
                already_filled_codes = [pf["order_id"] for pf in partial_fills]
                if order_id in already_filled_codes:
                    logger.warning(f"   ⏭️ 跳过 {r.get('code','?')} (已有成交，无法撤销)")
                    continue
                    
                if not order_id:
                    continue
                
                # 最多重试3次撤单
                for retry in range(3):
                    try:
                        ret = cancel_ctx.modify_order(
                            modify_order_op=ModifyOrderOp.CANCEL,
                            order_id=order_id,
                            qty=0, price=0,
                            trd_env=trd_env,
                            acc_id=acc_id,
                        )
                        
                        if ret == RET_OK:
                            logger.info(f"   ✅ 撤单成功: {order_id}")
                            cancel_success += 1
                            break
                        else:
                            # 检查返回的错误信息
                            err_msg = str(ret)
                            if "CANCELLED_ALL" in err_msg or "当前状态为CANCELLED_ALL" in err_msg:
                                # 订单已经是CANCELLED状态，说明之前已经被撤了
                                logger.info(f"   ℹ️ 订单 {order_id} 已经是取消状态（之前已撤单）")
                                cancel_success += 1
                                break
                            logger.warning(f"   ⚠️ 撤单失败 (尝试 {retry+1}/3): {order_id}, ret={ret}")
                            time.sleep(1)  # 等待1秒后重试
                    except Exception as e:
                        logger.warning(f"   ⚠️ 撤单异常 (尝试 {retry+1}/3): {order_id}, error={e}")
                        time.sleep(1)
                else:
                    # 3次都失败
                    logger.error(f"   ❌ 撤单最终失败: {order_id}")
                    cancel_failed += 1
            
            cancel_ctx.close()
            
            logger.info(f"📊 撤单结果: 成功 {cancel_success} 个, 失败 {cancel_failed} 个, 残留 {len(partial_fills)} 个")
            
            # 🔧 残留头寸报告
            if partial_fills:
                logger.critical("=" * 60)
                logger.critical("🚨🚨🚨 存在残留头寸！这不是完整的Iron Condor！")
                for pf in partial_fills:
                    logger.critical(f"  - {pf['code']} ({pf['side']}): 已成交{pf['dealt_qty']}/{pf['qty']}张 @ ${pf['price']} | 状态={pf['status']}")
                logger.critical("请立即在富途牛牛APP中手动处理！")
                logger.critical("=" * 60)
                return {
                    "success": False, 
                    "reason": f"部分订单未成交，{cancel_success}个已撤销，{len(partial_fills)}个残留头寸",
                    "partial_fills": partial_fills,
                }
            
            if cancel_failed > 0:
                logger.warning(f"⚠️ {cancel_failed} 个订单撤单失败，请在富途牛牛手动检查并撤销")
                return {"success": False, "reason": f"部分订单未成交，{cancel_failed}个撤单失败，请手动处理"}
            else:
                # 检查是否是因为非交易时段导致的超时（WAITING_SUBMIT状态超过5分钟）
                waiting_count = sum(1 for r in all_order_statuses if r.get("status") in ["WAITING_SUBMIT", "WAITING"])
                
                if waiting_count > 0:
                    # 非交易时段超时，订单已提交但未成交
                    logger.warning("⚠️ 订单已提交（非交易时段超时），开盘后请确认成交")
                    logger.info("📊 已提交订单号: " + ", ".join([r.get("order_id", "N/A") for r in all_order_statuses if r.get("order_id")]))
                    return {
                        "success": True,  # 订单已提交，开盘后会自动成交
                        "skipped": False, 
                        "warning": "非交易时段订单已提交，开盘后确认",
                        "submitted_order_ids": [r.get("order_id") for r in all_order_statuses if r.get("order_id")]
                    }
                else:
                    # 正常超时撤单
                    logger.info("✅ 所有订单已处理完毕（已成交或已取消）")
                    return {"success": False, "reason": "部分订单未成交，已全部撤销"}


    def _check_existing_positions(self) -> tuple:
        """
        检查当前是否已有铁鹰持仓（腾讯期权）
        返回 (group_count, total_legs) 元组
        """
        from config import FUTU_CONFIG
        from futu import OpenSecTradeContext, TrdEnv

        try:
            trade_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                filter_trdmarket="HK",
                security_firm="FUTUSECURITIES",
            )
            trd_env = TrdEnv.SIMULATE if self.dry_run else TrdEnv.REAL
            acc_id_key = "sim_acc_id" if self.dry_run else "real_acc_id"
            acc_id = int(float(FUTU_CONFIG.get(acc_id_key, "281756481449956811")))
            
            ret, pos_data = trade_ctx.position_list_query(
                code="",
                pl_ratio_min=None,
                pl_ratio_max=None,
                trd_env=trd_env,
                acc_id=acc_id,
                refresh_cache=True,
            )
            trade_ctx.close()
            
            if ret != 0 or pos_data is None or pos_data.empty:
                logger.info("📋 当前无持仓")
                return (0, 0)
            
            # 筛选腾讯期权持仓（代码含 TCH）
            tch_opts = pos_data[pos_data["code"].str.contains("TCH", na=False)]
            leg_count = len(tch_opts)
            group_count = leg_count // 4  # 每4腿算1组 IC
            remainder = leg_count % 4
            
            logger.info(f"📋 当前腾讯期权持仓: {leg_count} 腿 = {group_count} 组 Iron Condor")
            
            # 🔧 不平衡头寸检测
            if remainder != 0:
                logger.critical("🚨🚨🚨 检测到不平衡头寸！")
                logger.critical(f"   总腿数 {leg_count} 不是4的倍数（余{remainder}）")
                if not tch_opts.empty:
                    for _, row in tch_opts.iterrows():
                        logger.critical(f"     🔴 {row['code']}: {row['qty']} 张 | 可卖{row.get('can_sell_qty', 'N/A')} | 成本{row.get('cost_price', 'N/A')}")
                logger.critical("⚠️ 策略将暂停新开仓，请先处理不平衡头寸！")
                
            if not tch_opts.empty:
                for _, row in tch_opts.iterrows():
                    logger.info(f"   {row['code']}: {row['qty']} 张 @ {row.get('cost_price', 'N/A')}")
            
            return (group_count, leg_count)
        except Exception as e:
            logger.error(f"查询持仓失败: {e}")
            return (-1, -1)  # 查询失败时返回特殊值，让调用者暂停开仓

    def _is_today_trading_day(self) -> bool:
        """
        判断今天是否为港股交易日
        - 通过富途 API request_trading_days 查询真实交易日历
        - 如果 API 失败，降级为只判断周一~周五（不知道节假日）
        """
        today = date.today()
        result = self.data.is_hk_trading_day(today)

        if result:
            logger.info(f"📅 今日 {today} 是港股交易日")
        else:
            logger.info(f"🔴 今日 {today} 非港股交易日（节假日或周末），跳过")
        return result

    def _get_positions_with_expiry(self) -> List[Dict]:
        """
        获取腾讯期权持仓，并解析出到期日
        返回 [{"code": ..., "expiry": date, "qty": ..., "side": ..., "unrealized_pl": ..., "cost_price": ...}, ...]
        """
        import re
        from futu import OpenSecTradeContext, TrdEnv
        from config import FUTU_CONFIG

        positions = []
        try:
            trade_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                filter_trdmarket="HK",
                security_firm="FUTUSECURITIES",
            )
            trd_env = TrdEnv.SIMULATE if self.dry_run else TrdEnv.REAL
            acc_id_key = "sim_acc_id" if self.dry_run else "real_acc_id"
            acc_id = int(float(FUTU_CONFIG.get(acc_id_key, "281756481449956811")))
            ret, pos_data = trade_ctx.position_list_query(
                trd_env=trd_env,
                acc_id=acc_id,
                refresh_cache=True,
            )
            trade_ctx.close()

            if ret != 0 or pos_data is None or pos_data.empty:
                return []

            tch_opts = pos_data[pos_data["code"].str.contains("TCH", na=False)]
            for _, row in tch_opts.iterrows():
                code = row["code"]
                m = re.search(r"TCH(\d{6})", code)
                if m:
                    try:
                        expiry = datetime.strptime(m.group(1), "%y%m%d").date()
                    except ValueError:
                        expiry = None
                else:
                    expiry = None
                positions.append({
                    "code": code,
                    "expiry": expiry,
                    "qty": int(row.get("qty", 0)),
                    "side": row.get("position_side", "N/A"),
                    "unrealized_pl": float(row.get("unrealized_pl", 0) or 0),
                    "cost_price": float(row.get("cost_price", 0) or 0),
                    "today_pl": float(row.get("today_pl", 0) or 0),
                })
        except Exception as e:
            logger.error(f"查询持仓失败: {e}")

        return positions

    def _check_stop_loss(self) -> Dict:
        """
        止损检查（文章核心建议）
        
        规则1 - 单组止损：单组亏损 > 2倍权利金时强制平仓
        规则2 - 全局止损：总亏损 > 5% 时全部平仓观望
        
        返回: {"triggered": bool, "reason": str, "details": str}
        """
        from config import IRON_CONDOR_CONFIG
        
        positions = self._get_positions_with_expiry()
        if not positions:
            return {"triggered": False, "reason": "", "details": ""}
        
        # 统计总未实现盈亏和权利金
        total_unrealized_pl = sum(p["unrealized_pl"] for p in positions)
        
        # 估算开仓时收到的权利金（需要从持仓中推断）
        # 按 leg_count 估算：每组4腿，净权利金从配置读取
        leg_count = len(positions)
        group_count = max(1, leg_count // 4)
        # 从配置读取估算权利金，默认3000 HKD
        from config import IRON_CONDOR_CONFIG
        estimated_credit_per_group = IRON_CONDOR_CONFIG.get("estimated_credit_per_group", 3000)
        total_estimated_credit = estimated_credit_per_group * group_count
        
        logger.info(f"📊 止损检查: 未实现亏损={total_unrealized_pl:.0f}HKD, 估算权利金={total_estimated_credit:.0f}HKD")
        
        # 规则1：单组止损（亏损 > 2倍权利金）
        if group_count > 0:
            avg_loss_per_group = abs(total_unrealized_pl) / group_count
            if avg_loss_per_group > estimated_credit_per_group * 2:
                return {
                    "triggered": True,
                    "reason": f"单组亏损 {avg_loss_per_group:.0f}HKD > 2倍权利金 {estimated_credit_per_group * 2}HKD",
                    "details": f"总亏损 {total_unrealized_pl:.0f} HKD，共 {group_count} 组，平均 {avg_loss_per_group:.0f} HKD/组"
                }
        
        # 规则2：全局止损（总亏损 > 5%）
        # 假设初始资金 6万 HKD
        initial_capital = 60000
        total_loss_pct = abs(total_unrealized_pl) / initial_capital
        if total_loss_pct > IRON_CONDOR_CONFIG.get("stop_loss_pct", 0.05):
            return {
                "triggered": True,
                "reason": f"总亏损 {total_loss_pct*100:.1f}% > 止损线 5%",
                "details": f"未实现亏损 {total_unrealized_pl:.0f} HKD，初始资金 {initial_capital} HKD"
            }
        
        return {"triggered": False, "reason": "", "details": ""}

    def _should_close_today(self) -> bool:
        """
        判断今天是否需要触发平仓
        逻辑：
          1. 查询所有腾讯期权持仓，提取每组的到期日
          2. 对每个到期日，用 prev_n_trading_day(expiry, n=early_close_days) 
             计算"距到期第 N 个交易日"
          3. 如果今天 >= 该平仓触发日，触发平仓

        这样无论到期日前的第 N 天是不是节假日，都能在正确的交易日平仓。
        """
        from config import IRON_CONDOR_CONFIG
        early_close_days = IRON_CONDOR_CONFIG.get("early_close_days", 2)  # V7: 到期前2天平仓
        today = date.today()

        positions = self._get_positions_with_expiry()
        if not positions:
            return False

        # 按到期日分组
        expiry_set = set(p["expiry"] for p in positions if p["expiry"])
        for expiry in expiry_set:
            # 计算"到期前第 N 个交易日"
            close_trigger_day = self.data.prev_n_trading_day(expiry, n=early_close_days)
            days_left = (expiry - today).days
            # 实际提前了多少自然日（正常应 = early_close_days，长假时会更大）
            days_advanced = (expiry - close_trigger_day).days

            logger.info(
                f"📋 到期日 {expiry}：平仓触发日 = {close_trigger_day}，"
                f"今天 = {today}，剩余 {days_left} 自然日"
            )

            # ── 长假预警：实际提前超过预期 ────────────────────────
            if days_advanced > early_close_days + 1:
                msg = (
                    f"到期日 {expiry} 前有长假（连续 {days_advanced - early_close_days} 天不可交易），"
                    f"平仓触发日提前至 {close_trigger_day}（提前 {days_advanced} 自然日），"
                    f"预计损失部分 Theta（约 {days_advanced - early_close_days} 天）。"
                    f"如需手动调整，请在 {close_trigger_day} 前处理。"
                )
                logger.warning(f"📅 长假平仓预警: {msg}")
                try:
                    from notifier import notify_alert
                    notify_alert(
                        level="WARNING",
                        message=f"⚠️ 长假平仓预警：{expiry} 到期持仓将提前平仓",
                        details=msg,
                    )
                except Exception as e:
                    logger.error(f"发送预警通知失败: {e}")

            # ── 平仓判断 ─────────────────────────────────────────
            if today >= close_trigger_day:
                logger.warning(
                    f"⚠️ 今天({today}) >= 平仓触发日({close_trigger_day})，"
                    f"需要对 {expiry} 到期的持仓执行平仓！"
                )
                return True

        return False

    def _evaluate_risk(self) -> Dict:
        """
        实时风险评估（集成 ic_risk_monitor）
        
        计算当前持仓的风险指标：
        - 最大盈利/亏损
        - 盈亏平衡点
        - 亏损概率
        - 盈亏比
        
        根据阈值自动触发止损/止盈
        """
        from ic_risk_monitor import calculate_ic_metrics
        
        positions = self._get_positions_with_expiry()
        if not positions:
            return {"triggered": False, "action": "HOLD", "reason": ""}
        
        # 获取当前正股价格
        stock_ticker = STOCK_CONFIG["ticker"]
        stock_price = self.data.get_stock_quote(stock_ticker)
        if not stock_price:
            logger.warning("⚠️ 无法获取正股价格，跳过风险评估")
            return {"triggered": False, "action": "HOLD", "reason": "无法获取股价"}
        
        current_price = stock_price["last_price"]
        
        # 按到期日分组计算每组风险
        from collections import defaultdict
        groups = defaultdict(list)
        for pos in positions:
            if pos["expiry"]:
                groups[pos["expiry"]].append(pos)
        
        total_risk_info = []
        
        for expiry, legs in groups.items():
            if len(legs) < 4:
                continue
            
            # 解析行权价
            strikes = {}
            net_premium_per_share = 0
            
            for leg in legs:
                code = leg["code"]
                # 解析代码获取行权价
                import re
                m = re.search(r'TCH\d{6}([CP])(\d+)', code)
                if m:
                    option_type = m.group(1)
                    strike = int(m.group(2)) / 1000
                    side = "sell" if leg["qty"] > 0 else "buy"  # 正持仓=卖出(做卖方)
                    price = leg.get("cost_price", 0)
                    
                    if option_type == "P":
                        if side == "sell":
                            strikes["sell_put"] = strike
                            net_premium_per_share += price
                        else:
                            strikes["buy_put"] = strike
                            net_premium_per_share -= price
                    else:
                        if side == "sell":
                            strikes["sell_call"] = strike
                            net_premium_per_share += price
                        else:
                            strikes["buy_call"] = strike
                            net_premium_per_share -= price
            
            if len(strikes) >= 4:
                # 计算风险指标
                metrics = calculate_ic_metrics(
                    current_price=current_price,
                    sell_put_strike=strikes.get("sell_put", 0),
                    buy_put_strike=strikes.get("buy_put", 0),
                    sell_call_strike=strikes.get("sell_call", 0),
                    buy_call_strike=strikes.get("buy_call", 0),
                    net_premium_per_share=net_premium_per_share,
                    expiry=expiry,
                    currency="HKD"
                )
                
                total_risk_info.append({
                    "expiry": expiry,
                    "metrics": metrics,
                    "positions": legs,
                })
                
                # 打印风险报告
                m = metrics
                logger.info(f"📊 到期日 {expiry} 风险分析:")
                logger.info(f"   💰 权利金: {m['max_profit']:.0f} HKD")
                logger.info(f"   📈 最大盈利: +{m['max_profit']:.0f} HKD")
                logger.info(f"   📉 最大亏损: -{m['max_loss']:.0f} HKD")
                logger.info(f"   ⚖️ 盈亏比: 1:{m['risk_reward_ratio']:.2f}")
                logger.info(f"   🎯 盈亏平衡: {m['breakeven_lower']:.0f} ~ {m['breakeven_upper']:.0f}")
                logger.info(f"   ⚠️ 亏损概率: {m['loss_probability']:.1f}%")
        
        if not total_risk_info:
            return {"triggered": False, "action": "HOLD", "reason": ""}
        
        # 检查止损/止盈条件
        from config import IRON_CONDOR_CONFIG
        stop_loss_pct = IRON_CONDOR_CONFIG.get("stop_loss_pct", 0.05)  # V7: 5%总回撤止损
        
        # 计算总未实现盈亏
        total_unrealized_pl = sum(p["unrealized_pl"] for pos in positions for p in [pos])
        
        # 获取最大盈利和最大亏损
        max_profit = max(r["metrics"]["max_profit"] for r in total_risk_info)
        max_loss = max(r["metrics"]["max_loss"] for r in total_risk_info)
        
        # 止损检查
        if total_unrealized_pl < 0:
            loss_pct = abs(total_unrealized_pl) / 60000  # 假设初始6万
            if loss_pct > stop_loss_pct:
                return {
                    "triggered": True,
                    "action": "CLOSE_ALL",
                    "reason": f"总亏损 {loss_pct*100:.1f}% > 止损线 {stop_loss_pct*100:.1f}%",
                    "details": f"未实现亏损 {total_unrealized_pl:.0f} HKD"
                }
            
            # 亏损超过最大权利金的2倍
            if abs(total_unrealized_pl) > max_profit * 2:
                return {
                    "triggered": True,
                    "action": "CLOSE_ALL",
                    "reason": f"亏损 {abs(total_unrealized_pl):.0f} > 2倍权利金 {max_profit*2:.0f}",
                    "details": "亏损超过2倍权利金，触发保护性平仓"
                }
        
        # 止盈检查（盈利达到最大盈利的50%）
        if total_unrealized_pl > 0 and max_profit > 0:
            profit_pct = total_unrealized_pl / max_profit
            if profit_pct >= 0.5:
                return {
                    "triggered": True,
                    "action": "PARTIAL_CLOSE",
                    "reason": f"盈利达到 {profit_pct*100:.0f}% (>{50}%)，建议部分平仓",
                    "details": f"盈利 {total_unrealized_pl:.0f} / 最大 {max_profit:.0f}"
                }
        
        # 亏损概率过高警告
        for r in total_risk_info:
            if r["metrics"]["loss_probability"] > 60:
                return {
                    "triggered": True,
                    "action": "PARTIAL_CLOSE",
                    "reason": f"亏损概率 {r['metrics']['loss_probability']:.1f}% 过高",
                    "details": f"到期日 {r['expiry']} 的持仓风险较大"
                }
        
        return {"triggered": False, "action": "HOLD", "reason": ""}

    def close_all_positions(self) -> Dict:
        """
        平仓所有腾讯期权持仓（反向下单）
        卖出方向 → 买入平仓；买入方向 → 卖出平仓
        """
        from futu import OpenSecTradeContext, TrdSide, OrderType, TrdEnv, RET_OK
        from config import FUTU_CONFIG

        # dry_run 模式：不执行真实平仓
        if self.dry_run:
            logger.info("🔧 [模拟] 触发平仓检查，模拟模式不执行真实下单")
            return {"success": True, "dry_run": True, "closed": 0}

        logger.info("=" * 50)
        logger.info("🔴 开始执行平仓")
        logger.info("=" * 50)

        positions = self._get_positions_with_expiry()
        if not positions:
            logger.info("当前无持仓，无需平仓")
            return {"success": True, "closed": 0}

        trade_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            filter_trdmarket="HK",
            security_firm="FUTUSECURITIES",
        )
        trd_env = TrdEnv.REAL
        acc_id = int(float(FUTU_CONFIG.get("real_acc_id", "281756481449956811")))
        closed = 0

        for pos in positions:
            code = pos["code"]
            qty  = abs(pos["qty"])
            if qty == 0:
                continue

            # 确定平仓方向（与持仓反向）
            # position_side: LONG → 卖出平仓；SHORT → 买入平仓
            side_str = str(pos.get("side", "")).upper()
            if "LONG" in side_str:
                close_side = TrdSide.SELL
                side_label = "卖出平仓"
            else:
                close_side = TrdSide.BUY
                side_label = "买入平仓"

            # 获取实时盘口，取中间价；无价格则用市价单
            prices = self.get_real_time_prices([code])
            p = prices.get(code, {})
            mid = p.get("mid", 0.0)

            if mid > 0:
                order_price = round(mid, 2)
                order_type  = OrderType.NORMAL
            else:
                logger.warning(f"⚠️ {code} 无实时价格，改用市价单平仓")
                order_price = 0.0
                order_type  = OrderType.MARKET

            logger.info(f"📤 {side_label} {code}  数量={qty}  价格={'市价' if order_type == OrderType.MARKET else f'HKD {order_price:.2f}'}")

            ret, data = trade_ctx.place_order(
                code=code,
                price=order_price,
                qty=qty,
                trd_side=close_side,
                order_type=order_type,
                adjust_limit=0,
                trd_env=TrdEnv.REAL,
                acc_id=acc_id,
            )
            if ret == RET_OK:
                order_id = data.iloc[0]["order_id"]
                logger.info(f"   ✅ 平仓订单已提交: {order_id}")
                closed += 1
            else:
                logger.error(f"   ❌ 平仓下单失败: {data}")

        trade_ctx.close()
        logger.info(f"🔴 平仓完成：共提交 {closed}/{len(positions)} 腿")
        return {"success": True, "closed": closed, "total": len(positions)}

    def check_and_manage(self) -> Dict:
        """
        检查并管理仓位（每次 daemon 循环调用）

        流程：
          1. 确认今天是港股交易日，否则直接跳过
          2. 风险评估（实时监控盈亏、概率、盈亏比）
          3. 检查是否需要平仓（距到期第 N 个交易日）
          4. 若需平仓，执行平仓
          5. 若无需平仓，检查是否可以开新仓
        """
        # ── 1. 交易日校验 ──────────────────────────────
        if not self._is_today_trading_day():
            return {"success": True, "skipped": True, "reason": "非交易日"}

        # ── 1.5. 风险评估（实时监控）────────────────────────
        risk_result = self._evaluate_risk()
        if risk_result.get("action") == "CLOSE_ALL":
            logger.warning(f"🛑 触发自动止损: {risk_result['reason']}")
            try:
                from notifier import notify_alert
                notify_alert(
                    level="CRITICAL",
                    message=f"🛑 自动止损触发",
                    details=risk_result.get("details", ""),
                )
            except Exception as e:
                logger.error(f"发送止损通知失败: {e}")
            return self.close_all_positions()
        elif risk_result.get("action") == "PARTIAL_CLOSE":
            logger.warning(f"⚠️ 风险预警: {risk_result['reason']}")
            try:
                from notifier import notify_alert
                notify_alert(
                    level="WARNING",
                    message=f"⚠️ 风险预警",
                    details=risk_result.get("details", ""),
                )
            except Exception as e:
                logger.error(f"发送预警通知失败: {e}")

        # ── 2. 止损检查（文章核心建议） ────────────────────
        # 检查是否触发止损规则
        stop_loss_result = self._check_stop_loss()
        if stop_loss_result.get("triggered"):
            logger.warning(f"🛑 触发止损规则: {stop_loss_result['reason']}")
            logger.warning("🔴 执行止损平仓...")
            # 发送止损通知
            try:
                from notifier import notify_alert
                notify_alert(
                    level="CRITICAL",
                    message=f"🛑 触发止损: {stop_loss_result['reason']}",
                    details=stop_loss_result.get("details", ""),
                )
            except Exception as e:
                logger.error(f"发送止损通知失败: {e}")
            return self.close_all_positions()

        # ── 3. 平仓检查 ─────────────────────────────────
        if self._should_close_today():
            logger.info("🔴 触发提前平仓，执行平仓...")
            return self.close_all_positions()

        # ── 3. 开仓检查 ─────────────────────────────────
        logger.info("🔍 检查 Iron Condor 开仓机会...")
        from config import POSITION_CONFIG
        max_trades = POSITION_CONFIG.get("max_simultaneous_trades", 2)
        current_groups, total_legs = self._check_existing_positions()
        
        # 持仓查询失败保护：如果查询失败（返回-1），暂停开仓
        if current_groups == -1 or total_legs == -1:
            logger.critical(f"🛑 持仓查询失败，无法确定当前持仓状态，暂停新开仓！")
            return {"success": False, "skipped": True, "reason": "持仓查询失败，已暂停新开仓"}
        
        # 🔧 不平衡头寸保护：腿数不是4的倍数时禁止开新仓
        if total_legs > 0 and (total_legs % 4 != 0):
            logger.critical(f"🛑 检测到不平衡头寸（{total_legs}条腿），暂停新开仓！")
            return {"success": False, "skipped": True, "reason": f"不平衡头寸({total_legs}条腿)，已暂停"}

        if current_groups >= max_trades:
            logger.info(f"⏸ 已有 {current_groups} 组持仓（上限 {max_trades}），暂不开新仓")
            return {"success": True, "skipped": True, "reason": f"持仓已满 {current_groups}/{max_trades}"}

        logger.info(f"✅ 持仓 {current_groups}/{max_trades}，可以开新仓")
        return self.open_position()

    def run_once(self):
        """执行一次"""
        if not self.connect():
            return {"success": False, "reason": "连接失败"}

        try:
            return self.check_and_manage()
        finally:
            self.data.disconnect()

    def run_daemon(self):
        """常驻运行"""
        logger.info("🔄 启动 Iron Condor 守护进程...")
        logger.info("📝 按 Ctrl+C 停止")

        if not self.connect():
            return 1

        try:
            while True:
                self.check_and_manage()
                logger.info(f"💤 等待 {self.check_interval} 秒...")
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            logger.info("👋 停止守护进程")
            return 0

        finally:
            self.data.disconnect()


def main():
    parser = argparse.ArgumentParser(description="港股 Iron Condor 自动交易")
    parser.add_argument("--dry-run", action="store_true", help="模拟模式，不真实下单")
    parser.add_argument("--once", action="store_true", help="执行一次退出")
    parser.add_argument("--daemon", action="store_true", help="常驻运行（默认）")

    args = parser.parse_args()

    # 默认模式
    if not args.daemon and not args.once:
        args.once = True

    logger.info("="*50)
    logger.info("🦅 港股 Iron Condor 自动交易")
    logger.info("="*50)
    if args.dry_run:
        logger.info("⚠️ 模拟模式")
    else:
        logger.info("✅ 实盘模式")

    trader = ICTrader(dry_run=args.dry_run)

    if args.once:
        result = trader.run_once()
        if result.get("success"):
            expiry = result.get('expiry', 'N/A')
            premium = result.get('net_premium', 0)
            
            if result.get("skipped"):
                logger.info(f"⏭️ 跳过开仓: {result.get('reason', '未知原因')}")
            else:
                logger.info("✅ 执行完成")
            
            # 始终显示基本信息
            logger.info(f"  到期日: {expiry}")
            logger.info(f"  权利金: HK${premium:.2f}")
        else:
            logger.error(f"❌ 执行失败: {result.get('reason')}")
            return 1
    else:
        return trader.run_daemon()

    return 0


if __name__ == "__main__":
    sys.exit(main())