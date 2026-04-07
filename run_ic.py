"""
Iron Condor 策略模拟运行脚本
参数: 5%OTM + 8%翼 + DTE=7
用于通过富途模拟盘测试
"""

import sys
import math
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, List

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  参数配置
# ─────────────────────────────────────────────

CONFIG = {
    "ticker": "HK.00700",         # 腾讯
    "otm": 0.05,                  # 5% OTM
    "wing": 0.08,                 # 8% 翼宽
    "dte": 7,                     # 7天到期
    "min_premium": 1000,          # 最低权利金 HKD
    "dry_run": True,              # 模拟模式
}


# ─────────────────────────────────────────────
#  富途数据拉取
# ─────────────────────────────────────────────

def fetch_current_price(ticker: str) -> Optional[float]:
    """获取当前股价"""
    try:
        from futu import OpenQuoteContext, SubType, RET_OK
        ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        ctx.subscribe([ticker], [SubType.BASIC])
        ret, data = ctx.get_stock_quote(ticker)
        ctx.close()
        if ret == RET_OK:
            return float(data.iloc[0]['last_price'])
        return None
    except Exception as e:
        logger.error(f"获取股价失败: {e}")
        return None


def fetch_option_chain(ticker: str, expiry: str) -> Optional[Dict]:
    """获取期权链"""
    try:
        from futu import OpenOptionChain, RET_OK
        
        # 转换标的代码
        stock_code = ticker.replace("HK.", "")
        
        ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        ret, data = ctx.get_option_chain(
            code=ticker,
            start_date=expiry,
            end_date=expiry,
            type=0,  # 0=全部
        )
        ctx.close()
        
        if ret == RET_OK:
            return data
        return None
    except Exception as e:
        logger.error(f"获取期权链失败: {e}")
        return None


# ─────────────────────────────────────────────
#  Black-Scholes 期权定价
# ─────────────────────────────────────────────

def bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """BS看涨期权定价"""
    if T <= 0:
        return max(0, S - K)
    d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * math.exp(-r*T) * norm_cdf(d2)


def bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """BS看跌期权定价"""
    if T <= 0:
        return max(0, K - S)
    d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r*T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def norm_cdf(x: float) -> float:
    """标准正态分布累积函数"""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ─────────────────────────────────────────────
#  Iron Condor 策略
# ─────────────────────────────────────────────

def calculate_iron_condor(
    current_price: float,
    otm: float,
    wing: float,
    dte: int,
    iv: float = None
) -> Optional[Dict]:
    """
    计算 Iron Condor 开仓参数
    """
    # 估算 IV（如果未提供）
    if iv is None:
        iv = 0.30  # 默认30%波动率
    
    # 计算行权价
    call_strike = current_price * (1 + otm)      # 卖CALL行权价
    buy_call_strike = call_strike * (1 + wing)    # 买CALL行权价
    put_strike = current_price * (1 - otm)       # 卖PUT行权价  
    buy_put_strike = put_strike * (1 - wing)     # 买PUT行权价
    
    # 计算到期时间（年化）
    T = dte / 365
    r = 0.04  # 无风险利率
    
    # 计算权利金（BS模型）
    sell_call_premium = bs_call_price(current_price, call_strike, T, r, iv) * 100
    buy_call_premium = bs_call_price(current_price, buy_call_strike, T, r, iv) * 100
    sell_put_premium = bs_put_price(current_price, put_strike, T, r, iv) * 100
    buy_put_premium = bs_put_price(current_price, buy_put_strike, T, r, iv) * 100
    
    # 净权利金
    net_credit = sell_call_premium + sell_put_premium - buy_call_premium - buy_put_premium
    
    return {
        "sell_call_strike": round(call_strike, 2),
        "buy_call_strike": round(buy_call_strike, 2),
        "sell_put_strike": round(put_strike, 2),
        "buy_put_strike": round(buy_put_strike, 2),
        "sell_call_premium": round(sell_call_premium, 2),
        "buy_call_premium": round(buy_call_premium, 2),
        "sell_put_premium": round(sell_put_premium, 2),
        "buy_put_premium": round(buy_put_premium, 2),
        "net_credit": round(net_credit, 2),
        "expiry": (date.today() + timedelta(days=dte)).isoformat(),
    }


# ─────────────────────────────────────────────
#  主程序
# ─────────────────────────────────────────────

def main():
    ticker = CONFIG["ticker"]
    otm = CONFIG["otm"]
    wing = CONFIG["wing"]
    dte = CONFIG["dte"]
    
    logger.info(f"🔧 Iron Condor 策略模拟")
    logger.info(f"   标的: {ticker}")
    logger.info(f"   参数: OTM={otm*100}% Wing={wing*100}% DTE={dte}天")
    
    # 获取当前股价
    logger.info(f"📡 获取腾讯当前股价...")
    current_price = fetch_current_price(ticker)
    
    if current_price is None:
        logger.error("❌ 无法获取股价，请检查富途OpenD是否启动")
        # 使用模拟价格
        current_price = 580.0
        logger.info(f"   使用模拟价格: {current_price} HKD")
    
    logger.info(f"   当前股价: {current_price} HKD")
    
    # 计算Iron Condor参数
    result = calculate_iron_condor(current_price, otm, wing, dte)
    
    if result and result["net_credit"] >= CONFIG["min_premium"]:
        logger.info(f"✅ Iron Condor 开仓信号")
        logger.info(f"   卖PUT行权价: {result['sell_put_strike']} HKD")
        logger.info(f"   买PUT行权价: {result['buy_put_strike']} HKD")
        logger.info(f"   卖CALL行权价: {result['sell_call_strike']} HKD")
        logger.info(f"   买CALL行权价: {result['buy_call_strike']} HKD")
        logger.info(f"   💰 净权利金: {result['net_credit']} HKD")
        logger.info(f"   到期日: {result['expiry']}")
        
        if CONFIG["dry_run"]:
            logger.info(f"   🔧 模拟模式: 不会真实下单")
        
        return result
    else:
        logger.warning(f"⚠️  权利金不足 (需>{CONFIG['min_premium']}HKD)")
        return None


if __name__ == "__main__":
    main()