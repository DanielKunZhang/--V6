"""
数据层 - 腾讯期权实时行情
使用富途 OpenD API 获取数据
"""

import time
import logging
import signal
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from futu import *

from config import FUTU_CONFIG, STOCK_CONFIG, IRON_CONDOR_CONFIG


class TimeoutException(Exception):
    """超时异常"""
    pass


def timeout_handler(signum, frame):
    raise TimeoutException("操作超时")


# 设置默认超时（秒）
DEFAULT_TIMEOUT = 10

logger = logging.getLogger(__name__)


class FutuDataProvider:
    """富途行情数据提供者"""

    def __init__(self):
        self.quote_ctx: Optional[OpenQuoteContext] = None
        self.is_connected = False

    def connect(self, max_retries: int = 3) -> bool:
        """连接富途 OpenD，带重试机制"""
        logger.info("🔌 连接富途 OpenD...")
        for attempt in range(max_retries):
            try:
                self.quote_ctx = OpenQuoteContext(
                    host=FUTU_CONFIG["host"],
                    port=FUTU_CONFIG["port"],
                )
                self.is_connected = True
                logger.info(f"✅ 已连接")
                return True
            except Exception as e:
                logger.warning(f"⚠️ 连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # 重试前等待1秒
        
        logger.error(f"❌ 连接失败，已重试 {max_retries} 次")
        return False
        self.is_connected = False
        return False

    def disconnect(self):
        """断开连接"""
        if self.quote_ctx:
            self.quote_ctx.close()
            self.is_connected = False
            logger.info("富途行情通道已断开")

    def get_stock_quote(self, ticker: str = None) -> Optional[Dict]:
        """获取股票实时报价"""
        if ticker is None:
            ticker = STOCK_CONFIG.get("ticker", "HK.00700")

        # 统一格式为 HK.XXX
        if not ticker.startswith("HK.") and not ticker.startswith("US."):
            ticker = f"HK.{ticker.replace('.HK', '').replace('HK', '')}"

        if not self.is_connected:
            if not self.connect():
                return None

        # 先订阅
        self.quote_ctx.subscribe([ticker], [SubType.QUOTE])
        time.sleep(0.1)  # 等待订阅生效

        ret, data = self.quote_ctx.get_stock_quote([ticker])
        if ret == RET_OK:
            row = data.iloc[0]
            return {
                "ticker": ticker,
                "name": row.get("name", ""),
                "last_price": float(row.get("last_price", 0)),
                "open_price": float(row.get("open_price", 0)),
                "high_price": float(row.get("high_price", 0)),
                "low_price": float(row.get("low_price", 0)),
                "volume": int(row.get("volume", 0)),
                "turnover": float(row.get("turnover", 0)),
                "change_pct": float(row.get("change_ratio", 0)) * 100,
                "update_time": row.get("update_time", ""),
            }
        else:
            logger.error(f"获取报价失败: {data}")
            return None

    def get_option_expirations(self, ticker: str = None) -> Optional[List]:
        """
        获取所有可用到期日列表
        
        Args:
            ticker: 股票代码
            
        Returns:
            到期日列表（date对象）
        """
        if ticker is None:
            ticker = STOCK_CONFIG["ticker"]
            
        if not self.is_connected:
            if not self.connect():
                return None
                
        ret, expirations = self.quote_ctx.get_option_expiration_date(ticker)
        if ret != RET_OK:
            logger.error(f"获取到期日列表失败: {expirations}")
            return None
            
        if isinstance(expirations, pd.DataFrame) and not expirations.empty:
            dates = [date.fromisoformat(e) for e in expirations['strike_time']]
            return dates
        return None

    def get_option_chain(self, ticker: str = None, expiration: str = None) -> Optional[pd.DataFrame]:
        """
        获取期权链

        Args:
            ticker: 股票代码，默认腾讯
            expiration: 到期日 YYYY-MM-DD，不传则自动选择最接近 DTE=25 的到期日

        Returns:
            DataFrame with option chain data
        """
        if ticker is None:
            ticker = STOCK_CONFIG["ticker"]

        if not self.is_connected:
            if not self.connect():
                return None

        # 先获取到期日列表
        ret, expirations = self.quote_ctx.get_option_expiration_date(ticker)
        if ret != RET_OK:
            logger.error(f"获取到期日列表失败: {expirations}")
            return None

        # 选择目标到期日
        today = date.today()
        
        if expiration:
            # 如果指定了到期日，直接使用
            target_exp = expiration
        else:
            # 自动选择最接近目标 DTE 的到期日
            target_dte = IRON_CONDOR_CONFIG.get("dte", 25)
            dte_min, dte_max = 10, 60
            
            if isinstance(expirations, pd.DataFrame) and not expirations.empty:
                valid_exps = []
                for e in expirations['strike_time']:
                    exp_date = date.fromisoformat(e)
                    if exp_date >= today:
                        dte = (exp_date - today).days
                        if dte_min <= dte <= dte_max:
                            valid_exps.append((exp_date, dte))
                
                if valid_exps:
                    # 选择最接近目标 DTE 的到期日（而不是最远的）
                    target_exp = min(valid_exps, key=lambda x: abs(x[1] - target_dte))[0]
                    logger.info(f"🎯 选择到期日 {target_exp} (DTE={dict(valid_exps).get(target_exp, 'N/A')}, 目标DTE={target_dte})")
                else:
                    # 如果范围内没有，放宽到所有有效到期日中选择最远的
                    all_valid = [(date.fromisoformat(e), (date.fromisoformat(e) - today).days) 
                               for e in expirations['strike_time'] if date.fromisoformat(e) >= today]
                    if all_valid:
                        target_exp = max(all_valid, key=lambda x: x[1])[0]
                    else:
                        logger.error("无可用到期日")
                        return None
            else:
                logger.error("无可用到期日")
                return None

        # 获取期权链（针对特定到期日，时间跨度小于30天）
        ret, data = self.quote_ctx.get_option_chain(
            code=ticker,
            option_type='ALL',
            start=target_exp.strftime('%Y-%m-%d'),
            end=target_exp.strftime('%Y-%m-%d')  # 只获取某一天的期权
        )

        if ret != RET_OK:
            logger.error(f"获取期权链失败: {data}")
            return None

        # 新API返回的是期权标的列表，不是实时价格
        # 需要添加价格信息（使用默认值，或者通过实时报价获取）
        return data

    def get_hk_trading_days(self, start: date, end: date) -> List[date]:
        """
        通过富途 API 获取港股实际交易日历（排除节假日）

        Args:
            start: 开始日期
            end:   结束日期（含）

        Returns:
            交易日列表（升序）
        """
        if not self.is_connected:
            if not self.connect():
                return []

        ret, data = self.quote_ctx.request_trading_days(
            market=TradeDateMarket.HK,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
        )

        if ret != RET_OK:
            logger.warning(f"获取港股交易日历失败: {data}，降级使用自然日")
            return []

        trading_days = []
        # data 可能是列表（[{'time': '2026-04-07', ...}]）或 DataFrame
        rows = data if isinstance(data, list) else (
            data.to_dict("records") if hasattr(data, "to_dict") else []
        )
        for row in rows:
            try:
                t = row.get("time") or row.get("TIME") or row.get(0)
                if t:
                    trading_days.append(
                        datetime.strptime(str(t)[:10], "%Y-%m-%d").date()
                    )
            except Exception:
                pass

        return sorted(set(trading_days))

    def is_hk_trading_day(self, d: date) -> bool:
        """
        判断某天是否为港股交易日

        Returns:
            True=交易日，False=节假日/周末
        """
        days = self.get_hk_trading_days(d, d)
        return len(days) > 0 and days[0] == d

    def prev_n_trading_day(self, ref_date: date, n: int = 1) -> date:
        """
        从 ref_date 往前数第 n 个交易日

        例如：ref_date = 2026-04-29（到期日），n=1
          → 返回 2026-04-28（若为交易日），
            若28日是节假日则继续往前找到 27日……

        这解决了"到期前1天可能是非交易日"的问题。
        """
        # 向前查询最多60个自然日，足够覆盖任何节假日情况
        look_back = 60
        start = ref_date - timedelta(days=look_back)
        end   = ref_date - timedelta(days=1)     # 不含 ref_date 本身

        trading_days = self.get_hk_trading_days(start, end)

        if not trading_days:
            # API 失败时降级：往前数 n 个自然日
            logger.warning("交易日历获取失败，降级使用自然日")
            return ref_date - timedelta(days=n)

        # 取倒数第 n 个（n=1 → 最后一个 = 紧邻到期日之前的最近交易日）
        if len(trading_days) >= n:
            return trading_days[-n]
        else:
            return trading_days[0]

    def get_option_quote(self, option_code: str) -> Optional[Dict]:
        """获取单个期权报价（使用 get_market_snapshot，无需订阅，直接返回 bid/ask）"""
        if not self.is_connected:
            if not self.connect():
                return None

        ret, data = self.quote_ctx.get_market_snapshot([option_code])
        if ret == RET_OK and not data.empty:
            row = data.iloc[0]
            return {
                "code": option_code,
                "last_price": float(row.get("last_price", 0)),
                "bid": float(row.get("bid_price", 0)),
                "ask": float(row.get("ask_price", 0)),
                "open_price": float(row.get("open_price", 0)),
                "high_price": float(row.get("high_price", 0)),
                "low_price": float(row.get("low_price", 0)),
                "volume": int(row.get("volume", 0)),
                "implied_volatility": float(row.get("implied_volatility", 0)),
                "delta": float(row.get("delta", 0)),
                "gamma": float(row.get("gamma", 0)),
                "theta": float(row.get("theta", 0)),
                "vega": float(row.get("vega", 0)),
                "update_time": row.get("update_time", ""),
            }
        else:
            logger.error(f"获取期权报价失败: {data}")
            return None

    def find_put_candidates(
        self,
        current_price: float,
        config: Dict,
        expiration: str = None
    ) -> List[Dict]:
        """
        寻找合适的卖 Put 候选期权

        Returns:
            List of put options sorted by premium
        """
        chain = self.get_option_chain(expiration=expiration)
        if chain is None or chain.empty:
            return []

        # 过滤 Put
        puts = chain[chain["call_put"] == "PUT"].copy()

        if puts.empty:
            return []

        # 计算目标行权价范围
        min_strike = current_price * (1 - config["max_strike_below_current"])
        max_strike = current_price * (1 - config["strike_delta"])

        # 过滤行权价
        puts = puts[
            (puts["strike_price"] >= min_strike) &
            (puts["strike_price"] <= max_strike)
        ]

        # 计算权利金（需要乘以合约乘数）
        puts["premium_total"] = puts["bid_price"] * 100  # 港股期权每手100股

        # 过滤最低权利金
        puts = puts[puts["premium_total"] >= config["min_premium"]]

        # 按权利金排序
        puts = puts.sort_values("premium_total", ascending=False)

        # 转换为列表
        candidates = []
        for _, row in puts.iterrows():
            candidates.append({
                "code": row["code"],
                "strike": float(row["strike_price"]),
                "bid": float(row["bid_price"]),
                "ask": float(row["ask_price"]),
                "last": float(row["last_price"]),
                "premium": float(row["premium_total"]),
                "volume": int(row.get("volume", 0) or 0),
                "expiration": row["expiration_date"],
                "open_interest": int(row.get("open_interest", 0) or 0),
            })

        return candidates

    def find_call_candidates(
        self,
        cost_basis: float,
        current_price: float,
        config: Dict,
        expiration: str = None
    ) -> List[Dict]:
        """
        寻找合适的卖 Covered Call 候选期权
        用于持有正股后的备兑看涨
        """
        chain = self.get_option_chain(expiration=expiration)
        if chain is None or chain.empty:
            return []

        # 过滤 Call
        calls = chain[chain["call_put"] == "CALL"].copy()

        if calls.empty:
            return []

        # 目标行权价 = 成本价 + 10% 到 15%
        min_strike = cost_basis * (1 + config["strike_delta"] * 0.5)
        max_strike = cost_basis * (1 + config["strike_delta"] * 1.5)

        # 也参考当前价格
        min_strike = max(min_strike, current_price * 1.0)
        max_strike = max(max_strike, current_price * 1.1)

        # 过滤行权价
        calls = calls[
            (calls["strike_price"] >= min_strike) &
            (calls["strike_price"] <= max_strike)
        ]

        # 计算权利金
        calls["premium_total"] = calls["bid_price"] * 100

        # 过滤最低权利金
        calls = calls[calls["premium_total"] >= config["min_premium"]]

        # 按权利金排序
        calls = calls.sort_values("premium_total", ascending=False)

        # 转换为列表
        candidates = []
        for _, row in calls.iterrows():
            candidates.append({
                "code": row["code"],
                "strike": float(row["strike_price"]),
                "bid": float(row["bid_price"]),
                "ask": float(row["ask_price"]),
                "last": float(row["last_price"]),
                "premium": float(row["premium_total"]),
                "volume": int(row.get("volume", 0) or 0),
                "expiration": row["expiration_date"],
                "open_interest": int(row.get("open_interest", 0) or 0),
            })

        return candidates


# 全局单例
_data_provider: Optional[FutuDataProvider] = None


def get_data_provider() -> FutuDataProvider:
    global _data_provider
    if _data_provider is None:
        _data_provider = FutuDataProvider()
    return _data_provider
