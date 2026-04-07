#!/usr/bin/env python3
"""步骤1: 获取价格+波动率+到期日（不含期权链）"""
from futu import *
import numpy as np
from datetime import datetime, timedelta

quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)

ret, snap = quote_ctx.get_market_snapshot(['HK.00700'])
S = float(snap.iloc[0]['last_price'])

result = quote_ctx.request_history_kline('HK.00700',
    start=(datetime.now()-timedelta(days=40)).strftime('%Y-%m-%d'),
    end=datetime.now().strftime('%Y-%m-%d'), ktype=KLType.K_DAY, autype=AuType.QFQ)
ret_k, kline, _ = result

ann_vol = 0.28
if ret_k == RET_OK and len(kline) >= 20:
    c = kline['close'].values[-20:]
    ann_vol = np.std(np.diff(c)/c[:-1], ddof=1) * np.sqrt(252)
sigma = S * ann_vol * np.sqrt(25/252)

print(f"S={S:.2f} VOL={ann_vol*100:.1f}% 1SIG={sigma:.1f}")
print(f"1RANGE=[{S-sigma:.1f},{S+sigma:.1f}]")
print(f"2RANGE=[{S-2*sigma:.1f},{S+2*sigma:.1f}]")

ret_e, exp_df = quote_ctx.get_option_expiration_date('HK.00700')
if ret_e == RET_OK:
    for _, row in exp_df.iterrows():
        try:
            dte=(datetime.strptime(str(row['strike_time']),'%Y-%m-%d')-datetime.now()).days
            if 0 < dte < 120: print(f"EXP {row['strike_time']} DTE={dte}")
        except: pass
quote_ctx.close()
print("DONE")
