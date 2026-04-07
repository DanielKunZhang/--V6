#!/usr/bin/env python3
"""SPY Iron Condor 多参数回测"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from futu import *

# ============ 配置 ============
CAPITAL = 10000  # 起始资金
OPTIONS_PER_TRADE = 1  # 每组几手

# 参数组合
PARAM_COMBOS = [
    # (OTM%, Wing%, DTE)
    (5, 5, 7),
    (5, 8, 7),
    (10, 8, 7),
    (10, 10, 7),
    (5, 5, 14),
    (5, 8, 14),
    (10, 8, 14),
    (10, 10, 14),
    (5, 5, 21),
    (5, 8, 21),
    (10, 8, 21),
    (10, 10, 21),
]

def get_spy_data():
    """获取 SPY 数据"""
    quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
    
    years = [('2020-01-01', '2020-12-31'), ('2021-01-01', '2021-12-31'),
            ('2022-01-01', '2022-12-31'), ('2023-01-01', '2023-12-31'),
            ('2024-01-01', '2024-12-31'), ('2025-01-01', '2025-12-31')]
    
    all_data = []
    for start, end in years:
        ret, data = quote_ctx.request_history_kline('US.SPY', start=start, end=end, 
                                               ktype=KLType.K_DAY, max_count=500)
        if ret == RET_OK and isinstance(data, pd.DataFrame):
            all_data.append(data)
        import time; time.sleep(0.3)
    
    quote_ctx.close()
    
    if not all_data:
        return None
    
    df = pd.concat(all_data, ignore_index=True)
    df = df[['time_key', 'close']].copy()
    df.columns = ['date', 'price']
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df.sort_values('date').reset_index(drop=True)

def get_option_expiry(dte):
    """模拟美股周度到期日"""
    # 简化：每周五到期
    if dte == 7:
        return 7
    elif dte == 14:
        return 14
    elif dte == 21:
        return 21
    return dte

def simulate_ic(price, otm, wing, dte):
    """模拟 Iron Condor 收益"""
    # 简化：基于波动率估算权利金
    sigma = 0.20  # 假设 20% 年化波动率
    daily_sigma = sigma / np.sqrt(252)
    
    # 卖出期权收入 (OTM%)
    sell_width = price * otm / 100
    # 买入期权支出 (Wing%)
    buy_width = price * wing / 100
    
    # 简化的权利金估算
    sell_premium = price * otm / 100 * 0.3  # 简化
    buy_premium = price * wing / 100 * 0.1
    
    net_premium = sell_premium * 2 - buy_premium * 2  # 4条腿
    return net_premium * OPTIONS_PER_TRADE

def run_backtest(df, otm, wing, dte):
    """运行回测"""
    cash = CAPITAL
    position = None
    trades = []
    
    for i in range(dte, len(df)):
        date = df.iloc[i]['date']
        price = df.iloc[i]['price']
        
        if position is None:
            # 开仓
            premium = simulate_ic(price, otm, wing, dte)
            position = {
                'entry_date': date,
                'entry_price': price,
                'premium': premium,
                'dte': dte
            }
        else:
            # 检查到期
            hold_days = (date - position['entry_date']).days
            if hold_days >= position['dte']:
                # 到期结算
                exit_price = price
                
                # 计算盈亏
                if exit_price < position['entry_price'] * (1 - otm/100):
                    # PUT 被行权，亏损
                    pnl = position['premium'] - (position['entry_price'] * otm/100 * price/position['entry_price'])
                elif exit_price > position['entry_price'] * (1 + otm/100):
                    # CALL 被行权，亏损
                    pnl = position['premium'] - (exit_price - position['entry_price'] * (1 + otm/100))
                else:
                    # 区间内盈利
                    pnl = position['premium']
                
                cash += pnl
                trades.append({
                    'date': date,
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'return': pnl / cash * 100
                })
                position = None
    
    if not trades:
        return {'ann_return': 0, 'win_rate': 0, 'num_trades': 0}
    
    pnls = [t['pnl'] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    
    start_date = df['date'].iloc[0]
    end_date = df['date'].iloc[-1]
    years = (end_date - start_date).days / 365
    
    total_return = (cash - CAPITAL) / CAPITAL
    ann_return = (total_return / years) * 100 if years > 0 else 0
    
    return {
        'ann_return': ann_return,
        'win_rate': wins / len(trades) * 100,
        'num_trades': len(trades),
        'total_pnl': sum(pnls),
        'max_dd': min(pnls) if pnls else 0
    }

def main():
    print("获取 SPY 数据...")
    df = get_spy_data()
    if df is None:
        print("获取数据失败")
        return
    
    print(f"数据: {len(df)} 条 ({df['date'].min()} ~ {df['date'].max()})")
    
    results = []
    for otm, wing, dte in PARAM_COMBOS:
        print(f"测试 参数: OTM={otm}%, Wing={wing}%, DTE={dte}...", end='', flush=True)
        result = run_backtest(df, otm, wing, dte)
        print(f" 年化={result['ann_return']:.1f}%, 胜率={result['win_rate']:.0f}%, 交易数={result['num_trades']}")
        results.append({
            'OTM': otm,
            'Wing': wing,
            'DTE': dte,
            **result
        })
    
    # 保存结果
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('ann_return', ascending=False)
    results_df.to_csv('backtest_results/spy_multi_param_results.csv', index=False)
    print(f"\n最佳参数: {results_df.iloc[0].to_dict()}")
    print("结果已保存到 backtest_results/spy_multi_param_results.csv")

if __name__ == '__main__':
    main()