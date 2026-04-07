#!/usr/bin/env python3
import sys
sys.path.append('.')
from backtest_real import historical_volatility
import pandas as pd
import numpy as np

# 创建模拟数据
dates = pd.date_range('2026-01-01', periods=30, freq='D')
closes = pd.Series([100 + i * 0.5 for i in range(30)], index=dates)
print('closes type:', type(closes))
print('closes shape:', closes.shape)
print('closes head:', closes.head())

# 调用函数
try:
    result = historical_volatility(closes, window=20)
    print('result:', result)
    print('type(result):', type(result))
except Exception as e:
    print('error:', e)
    import traceback
    traceback.print_exc()