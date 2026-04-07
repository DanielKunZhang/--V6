#!/usr/bin/env python3
"""完整获取腾讯数据 - 适配新版SDK"""
import sys
from futu import *
import numpy as np
from datetime import datetime, timedelta

print("连接中...", flush=True)
quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)

# 1. 腾讯价格
ret, snap = quote_ctx.get_market_snapshot(['HK.00700'])
S = float(snap.iloc[0]['last_price'])

# 2. K线
result = quote_ctx.request_history_kline(
    'HK.00700',
    start=(datetime.now()-timedelta(days=40)).strftime('%Y-%m-%d'),
    end=datetime.now().strftime('%Y-%m-%d'),
    ktype=KLType.K_DAY, autype=AuType.QFQ
)
if len(result) == 3:
    ret_k, kline, _pk = result
else:
    ret_k, kline = result[0], result[1]

ann_vol = 0.28
sigma_hkd = S * ann_vol * np.sqrt(25/252)
if ret_k == RET_OK and len(kline) >= 20:
    closes = kline['close'].values[-20:]
    rets = np.diff(closes) / closes[:-1]
    ann_vol = np.std(rets, ddof=1) * np.sqrt(252)
    sigma_hkd = S * ann_vol * np.sqrt(25/252)

# 3. 到期日 (列名是strike_time)
ret_e, exp_df = quote_ctx.get_option_expiration_date('HK.00700')

print("=" * 55, flush=True)
print(f"  腾讯 HK.00700 实时数据 (futuapi)", flush=True)
print("=" * 55, flush=True)
print(f"  当前价: {S:.2f} HKD", flush=True)
print(f"  20日年化波动率: {ann_vol*100:.2f}%", flush=True)
print(f"  DTE=25的1σ波动: +/-{sigma_hkd:.2f} HKD ({sigma_hkd/S*100:.1f}%)", flush=True)
print(f"  1σ区间: [{S-sigma_hkd:.2f}, {S+sigma_hkd:.2f}]", flush=True)
print(f"  2σ区间: [{S-2*sigma_hkd:.2f}, {S+2*sigma_hkd:.2f}]", flush=True)
print(f"\n  期权到期日:", flush=True)

exp_list = []
if ret_e == RET_OK:
    for _, row in exp_df.iterrows():
        try:
            dte = (datetime.strptime(str(row['strike_time']), '%Y-%m-%d') - datetime.now()).days
            if dte > 0 and dte < 120:
                print(f"    {row['strike_time']} DTE={dte}", flush=True)
                exp_list.append((row['strike_time'], dte))
        except Exception as e:
            print(f"    解析失败: {e}, row={dict(row)}", flush=True)

# 4. 取最近两个到期日的期权链
if len(exp_list) >= 2:
    # 4月和5月到期
    for exp_str, dte in exp_list[:2]:
        ret_c, chain = quote_ctx.get_option_chain('HK.00700', start=exp_str, end=exp_str)
        if ret_c == RET_OK and not chain.empty:
            # 筛选行权价在合理范围
            near = chain[(chain['strike_price'] >= int(S-sigma_hkd*1.5)) & 
                        (chain['strike_price'] <= int(S+sigma_hkd*1.5))].copy()
            codes = near['code'].tolist()
            if codes:
                ret_p, prices = quote_ctx.get_market_snapshot(codes[:30])  # 限制数量避免超时
                if ret_p == RET_OK:
                    merged = near.merge(prices[['code','last_price','bid_price','ask_price']], on='code')
                    label = "4月" if dte < 35 else ("5月" if dte < 70 else str(dte))
                    print(f"\n  {label}到期 ({exp_str}) DTE={dte}:", flush=True)
                    print(f'  {"行权价":>6} {"类型":>4} {"Bid":>7} {"Ask":>7} {"Last":>7}', flush=True)
                    for _, row in sorted(merged.iterrows(), key=lambda x: x[0]['strike_price']):
                        t = 'Call' if row['option_type']=='CALL' else 'Put '
                        bid = row['bid_price'] if row['bid_price'] > 0 else 0
                        ask = row['ask_price'] if row['ask_price'] > 0 else 0
                        last = row['last_price']
                        print(f"  {row['strike_price']:6.0f}   {t} {bid:7.2f} {ask:7.2f} {last:7.2f}", flush=True)

quote_ctx.close()
print("\nDONE!", flush=True)
