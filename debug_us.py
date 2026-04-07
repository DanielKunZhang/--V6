#!/usr/bin/env python3
"""调试美股周度IC开仓"""
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline, bs_option_price
from datetime import date, timedelta
import math

# 手动实现完整回测
df = fetch_futu_kline('US.SPY', '2024-01-01', '2024-01-31')
df = df.copy()
df['Returns'] = df['Close'].pct_change()
df['HV20'] = df['Returns'].rolling(20).std() * math.sqrt(252)
df['HV20'] = df['HV20'].fillna(0.20).clip(0.10, 1.0)

# 获取周度到期日
expiries = []
d = df['date'].min()
while d.weekday() != 4:
    d += timedelta(days=1)
while d <= df['date'].max():
    expiries.append(d)
    d += timedelta(days=7)

print('到期日:', expiries)
print()

# 简化回测 - 每周四入场
otm = 0.05
wing = 0.08

for i, row in df.iterrows():
    current_date = row['date']
    S = row['Close']
    sigma = row['HV20']
    
    if pd.isna(S):
        continue
    
    # 找这个周四的下一个周五
    next_exp = None
    for exp in expiries:
        if exp >= current_date:
            next_exp = exp
            break
    
    if next_exp is None:
        continue
    
    days_to_expiry = (next_exp - current_date).days
    
    # 周四入场 (days_to_expiry == 1)
    if days_to_expiry == 1:
        print(f'{current_date}: S={S:.2f}, days_to_expiry={days_to_expiry}')
        
        # 计算权利金
        sk = S * (1 - otm + wing)  # 卖PUT
        bpk = S * (1 - otm)        # 买PUT
        sck = S * (1 + otm - wing) # 卖CALL
        bck = S * (1 + otm)       # 买CALL
        
        T = 1 / 365.0
        
        sell_put_price = bs_option_price(S, sk, T, sigma, 0.04, 'PUT') * 100 * 0.99
        buy_put_price = bs_option_price(S, bpk, T, sigma, 0.04, 'PUT') * 100 * 0.99
        sell_call_price = bs_option_price(S, sck, T, sigma, 0.04, 'CALL') * 100 * 0.99
        buy_call_price = bs_option_price(S, bck, T, sigma, 0.04, 'CALL') * 100 * 0.99
        
        net_credit = (sell_put_price + sell_call_price) - (buy_put_price + buy_call_price)
        
        print(f'  权利金: 卖PUT ${sell_put_price:.0f} + 卖CALL ${sell_call_price:.0f} - 买PUT ${buy_put_price:.0f} - 买CALL ${buy_call_price:.0f} = 净${net_credit:.0f}')
        
        if net_credit > 0:
            print(f'  开仓成功!')
        else:
            print(f'  权利金 <= 0')
        break