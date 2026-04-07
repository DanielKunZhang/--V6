import sys
sys.path.insert(0, '/Users/zhangkun/WorkBuddy/20260402141752/wheel_tencent')

# 强制重新加载
for mod in list(sys.modules.keys()):
    if 'backtest_real' in mod:
        del sys.modules[mod]

from backtest_real import bs_option_price, historical_volatility, fetch_futu_kline
import pandas as pd

# 测试
result = bs_option_price(24.75, 23.5, 30/365, 0.3, 'PUT')
print(f'bs_option_price test: {result}')

# 测试历史波动率
df = fetch_futu_kline('HK.02800', '2020-01-01', '2020-03-31')
prices = df['Close'].iloc[:20]
sigma = historical_volatility(prices, 20)
print(f'sigma: {sigma}, type: {type(sigma)}')

# 测试完整流程
S = float(df.iloc[10]['Close'])
result2 = bs_option_price(S, 23.5, 30/365, sigma, 'PUT')
print(f'Full test result: {result2}')