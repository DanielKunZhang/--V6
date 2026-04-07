#!/usr/bin/env python3
"""仅获取4月29日Put+Call各5个行权价"""
from futu import *

S = 489.2
quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
ret, chain = quote_ctx.get_option_chain('HK.00700', start='2026-04-29', end='2026-04-29')
if ret == RET_OK:
    # 只取Put: 420,440,460,480,500 和 Call: 510,530,550,570,590
    strikes = [420,440,460,480,500,510,530,550,570,590]
    near = chain[chain['strike_price'].isin(strikes)].copy()
    codes = near['code'].tolist()
    if codes:
        r2, p = quote_ctx.get_market_snapshot(codes)
        if r2 == RET_OK:
            m = near.merge(p[['code','last_price','bid_price','ask_price']], on='code')
            for _r in sorted(m.iterrows(), key=lambda x: x[0]['strike_price']):
                row=_r[1]; t='C' if row['option_type']=='CALL' else 'P'
                b=row['bid_price'] if row['bid_price']>0 else 0
                a=row['ask_price'] if row['ask_price']>0 else 0
                otm=((row['strike_price']-S)/S*100) if t=='C' else ((S-row['strike_price'])/S*100)
                print(f"{row['strike_price']:5.0f}{t} B{b:6.2f} A{a:6.2f} L{row['last_price']:6.2f} OTM{otm:+5.1f}%")
quote_ctx.close()
print("DONE")
