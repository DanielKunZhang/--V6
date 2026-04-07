#!/usr/bin/env python3
"""获取 SPY 历史 K 线数据用于回测"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '.workbuddy', 'skills', 'futuapi', 'scripts'))
from common import create_quote_context, RET_OK, KLType
import pandas as pd

def get_spy_history():
    quote_ctx = create_quote_context()
    if not quote_ctx:
        print("无法创建行情上下文")
        return None
    
    # 分段获取数据（每年500条，避免超限）
    years = [
        ('2020-01-01', '2020-12-31'),
        ('2021-01-01', '2021-12-31'),
        ('2022-01-01', '2022-12-31'),
        ('2023-01-01', '2023-12-31'),
        ('2024-01-01', '2024-12-31'),
        ('2025-01-01', '2025-12-31'),
    ]
    
    all_data = []
    for start, end in years:
        print(f"获取 {start[:4]} 年...", end='', flush=True)
        ret, data = quote_ctx.request_history_kline('US.SPY', start=start, end=end, 
                                                ktype=KLType.K_DAY, max_count=500)
        if ret == RET_OK and isinstance(data, pd.DataFrame):
            all_data.append(data)
            print(f" {len(data)} 条")
        else:
            print(f" 失败")
        import time; time.sleep(0.5)
    
    quote_ctx.close()
    
    if not all_data:
        return None
    
    df = pd.concat(all_data, ignore_index=True)
    df = df[['time_key', 'open', 'high', 'low', 'close', 'volume']]
    df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df

if __name__ == '__main__':
    df = get_spy_history()
    if df is not None:
        output_path = 'backtest_results/spy_daily_2020_2025.csv'
        df.to_csv(output_path, index=False)
        print(f"\n已保存到 {output_path}")
        print(f"总计 {len(df)} 条 ({df['date'].min()} ~ {df['date'].max()})")