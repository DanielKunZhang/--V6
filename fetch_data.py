#!/usr/bin/env python3
"""获取腾讯实时数据用于Iron Condor参数优化"""
import sys
from futu import *
import numpy as np
from datetime import datetime, timedelta

print("连接futuapi...", flush=True)
quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)

# 1. 腾讯当前价格
ret, snap = quote_ctx.get_market_snapshot(['HK.00700'])
if ret != RET_OK:
    print("获取快照失败:", snap)
    sys.exit(1)
S = float(snap.iloc[0]['last_price'])

# 2. 20日K线计算波动率（新版SDK返回3个值：ret, kline, page_key）
result = quote_ctx.request_history_kline(
    'HK.00700',
    start=(datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d'),
    end=datetime.now().strftime('%Y-%m-%d'),
    ktype=KLType.K_DAY,
    autype=AuType.QFQ
)
ret, kline, _page_key = result
if ret == RET_OK and len(kline) >= 20:
    closes = kline['close'].values[-20:]
    returns = np.diff(closes) / closes[:-1]
    daily_vol = np.std(returns, ddof=1)  # 样本标准差
    annual_vol = daily_vol * np.sqrt(252)
else:
    annual_vol = 0.28

# 3. 计算关键区间
sigma_25d = annual_vol * np.sqrt(25/252)
sigma_hkd = S * sigma_25d

print(f'=== 腾讯实时数据 (futuapi) ===')
print(f'S={S:.2f}')
print(f'20D年化波动率: {annual_vol*100:.2f}%')
print(f'DTE=25的1sigma波动: +/-{sigma_hkd:.2f} HKD')
print(f'1sigma下沿: {S-sigma_hkd:.2f} ({(S-sigma_hkd)/S*100:.1f}%)')
print(f'1sigma上沿: {S+sigma_hkd:.2f} ({(S+sigma_hkd)/S*100:.1f}%)')
print(f'2sigma下沿: {S-2*sigma_hkd:.2f}')
print(f'2sigma上沿: {S+2*sigma_hkd:.2f}')

# 4. 获取期权到期日
ret, exp_dates = quote_ctx.get_option_expiration_date('HK.00700')
if ret == RET_OK:
    print(f'\n=== 期权到期日 ===')
    for _, row in exp_dates.iterrows():
        try:
            dte = (datetime.strptime(str(row['expiry_date']), '%Y-%m-%d') - datetime.now()).days
            if dte > 0 and dte < 120:
                print(f"  {row['expiry_date']} DTE={dte}")
        except:
            pass

# 5. 获取4月29日和5月28日到期的期权链（行权价400-580区间）
for exp_str, label in [('2026-04-29', '4月'), ('2026-05-28', '5月')]:
    ret, chain = quote_ctx.get_option_chain('HK.00700', start=exp_str, end=exp_str)
    if ret == RET_OK and not chain.empty:
        near = chain[(chain['strike_price'] >= 400) & (chain['strike_price'] <= 580)].copy()
        codes = near['code'].tolist()
        if codes:
            ret2, prices = quote_ctx.get_market_snapshot(codes)
            if ret2 == RET_OK:
                merged = near.merge(prices[['code','last_price','bid_price','ask_price']], on='code')
                print(f'\n=== {label}到期 ({exp_str}) 期权价格 ===')
                print(f'{"行权价":>6} {"类型":>4} {"Bid":>7} {"Ask":>7} {"Last":>7} {"OTM%":>7}')
                for _, row in sorted(merged.iterrows(), key=lambda x: x[0]['strike_price']):
                    t = 'Call' if row['option_type']=='CALL' else 'Put'
                    bid = row['bid_price'] if row['bid_price'] > 0 else 0
                    ask = row['ask_price'] if row['ask_price'] > 0 else 0
                    last = row['last_price']
                    otm_pct = (row['strike_price'] - S) / S * 100 if row['option_type']=='CALL' else (S - row['strike_price']) / S * 100
                    print(f"{row['strike_price']:6.0f} {t:>4} {bid:7.2f} {ask:7.2f} {last:7.2f} {otm_pct:+7.1f}%")

quote_ctx.close()
print("\n完成!")
