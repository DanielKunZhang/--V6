#!/usr/bin/env python3
"""
SPY Iron Condor 15年回测脚本
使用富途API获取真实股票数据 + 模拟期权定价
"""

from scipy.stats import norm
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '/Users/zhangkun/.workbuddy/skills/futuapi/scripts')
from common import create_quote_context, RET_OK

def get_spy_data():
    """获取SPY历史数据"""
    csv_path = 'backtest_results/spy_daily_2010_2025.csv'
    try:
        df = pd.read_csv(csv_path)
        df['date'] = pd.to_datetime(df['time']).dt.date
        print(f"从文件加载: {len(df)} 条 ({df['date'].min()} ~ {df['date'].max()})")
        return df
    except:
        pass
    
    # 重新获取
    quote_ctx = create_quote_context()
    if not quote_ctx:
        print("无法创建行情上下文")
        return None
    
    # 分段获取
    years = [('2010-01-01', '2010-12-31'), ('2011-01-01', '2011-12-31'),
             ('2012-01-01', '2012-12-31'), ('2013-01-01', '2013-12-31'),
             ('2014-01-01', '2014-12-31'), ('2015-01-01', '2015-12-31'),
             ('2016-01-01', '2016-12-31'), ('2017-01-01', '2017-12-31'),
             ('2018-01-01', '2018-12-31'), ('2019-01-01', '2019-12-31'),
             ('2020-01-01', '2020-12-31'), ('2021-01-01', '2021-12-31'),
             ('2022-01-01', '2022-12-31'), ('2023-01-01', '2023-12-31'),
             ('2024-01-01', '2024-12-31'), ('2025-01-01', '2025-12-31')]
    
    all_data = []
    for start, end in years:
        ret, data = quote_ctx.request_history_kline('US.SPY', start=start, end=end,
                                                      ktype=1, max_count=500)
        if ret == RET_OK and isinstance(data, pd.DataFrame):
            all_data.append(data)
            print(f"{start[:4]}: {len(data)} 条")
        import time; time.sleep(0.3)
    
    if all_data:
        df = pd.concat(all_data, ignore_index=True)
        df = df[['time_key', 'open', 'high', 'low', 'close', 'volume']]
        df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        df['date'] = pd.to_datetime(df['date']).dt.date
        df.to_csv(csv_path, index=False)
        print(f"总计: {len(df)} 条")
    
    quote_ctx.close()
    return df

def bs_option_price(S, K, T, r, sigma, option_type='CALL'):
    """Black-Scholes期权定价"""
    if T <= 0:
        return 0
    
    # 避免除零
    if sigma * np.sqrt(T) < 1e-10:
        if option_type == 'CALL':
            return max(S - K, 0)
        else:
            return max(K - S, 0)
    
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == 'CALL':
        price = S * norm.cdf(d1) - K * np.exp(-r*T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r*T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    
    return price

def get_implied_volatility(df, date_idx, window=20):
    """从历史数据估算隐含波动率"""
    if date_idx < window:
        return 0.20  # 默认20% IV
    
    # 使用历史收益率的标准差作为波动率估算
    prices = df.iloc[date_idx-window:date_idx]['close'].values
    returns = np.diff(np.log(prices))
    return max(np.std(returns) * np.sqrt(252), 0.10)  # 年化，最低10%

def simulate_iron_condor(df, otm_pct, wing_pct, dte, 
                         initial_capital=10000, min_premium=200,
                         cooldown_days=5, early_close=1):
    """
    模拟 Iron Condor 策略
    
    参数:
    - otm_pct: OTM百分比 (如 0.10 = 10%)
    - wing_pct: Wing宽度百分比
    - dte: 到期天数
    - min_premium: 最低权利金 (USD)
    - cooldown_days: 冷却期天数
    - early_close: 到期前N天强制平仓
    """
    cash = initial_capital
    positions = []
    trades = []
    
    r = 0.04  # 无风险利率 4%
    
    print(f"\n参数: OTM={otm_pct*100:.0f}%, Wing={wing_pct*100:.0f}%, DTE={dte}")
    
    for i in range(dte + early_close, len(df)):
        current_date = df.iloc[i]['date']
        current_price = df.iloc[i]['close']
        
        # 获取历史波动率
        iv = get_implied_volatility(df, i)
        
        # 检查是否有持仓需要平仓
        new_positions = []
        for pos in positions:
            days_held = (current_date - pos['open_date']).days
            days_to_expiry = pos['dte'] - days_held
            
            # 检查是否到期或提前平仓
            should_close = False
            close_reason = ""
            
            if days_to_expiry <= early_close:
                should_close = True
                close_reason = f"到期前{early_close}天"
            
            # 检查价格是否突破行权价（风险检查）
            if current_price < pos['buy_put_strike'] * 0.95 or \
               current_price > pos['buy_call_strike'] * 1.05:
                # 价格大幅突破，买入/卖出对冲
                should_close = True
                close_reason = "价格突破风控线"
            
            if should_close:
                # 计算平仓时的期权价值
                sell_call_val = bs_option_price(current_price, pos['sell_call_strike'],
                                                 days_to_expiry/365, r, iv, 'CALL')
                sell_put_val = bs_option_price(current_price, pos['sell_put_strike'],
                                                days_to_expiry/365, r, iv, 'PUT')
                buy_call_val = bs_option_price(current_price, pos['buy_call_strike'],
                                                days_to_expiry/365, r, iv, 'CALL')
                buy_put_val = bs_option_price(current_price, pos['buy_put_strike'],
                                               days_to_expiry/365, r, iv, 'PUT')
                
                # 平仓盈亏 = 收取权利金 - 支付平仓成本
                close_cost = (sell_call_val + sell_put_val - buy_call_val - buy_put_val) * 100
                profit = pos['net_premium'] - close_cost
                cash += profit
                
                trades.append({
                    'open_date': pos['open_date'],
                    'close_date': current_date,
                    'open_price': pos['open_price'],
                    'close_price': current_price,
                    'dte': pos['dte'],
                    'days_held': days_held,
                    'net_premium': pos['net_premium'],
                    'close_cost': close_cost,
                    'profit': profit,
                    'close_reason': close_reason,
                    'otm_pct': otm_pct,
                    'wing_pct': wing_pct
                })
            else:
                new_positions.append(pos)
        
        positions = new_positions
        
        # 检查冷却期
        if trades:
            days_since_close = (current_date - trades[-1]['close_date']).days
            if days_since_close < cooldown_days:
                continue
        
        # 检查是否需要开仓（最多1组）
        if len(positions) == 0:
            # 计算行权价
            sell_call_strike = current_price * (1 + otm_pct)
            sell_put_strike = current_price * (1 - otm_pct)
            buy_call_strike = sell_call_strike * (1 + wing_pct)
            buy_put_strike = sell_put_strike * (1 - wing_pct)
            
            # 估算开仓时的权利金
            sell_call_price = bs_option_price(current_price, sell_call_strike, dte/365, r, iv, 'CALL')
            sell_put_price = bs_option_price(current_price, sell_put_strike, dte/365, r, iv, 'PUT')
            buy_call_price = bs_option_price(current_price, buy_call_strike, dte/365, r, iv, 'CALL')
            buy_put_price = bs_option_price(current_price, buy_put_strike, dte/365, r, iv, 'PUT')
            
            net_premium = (sell_call_price + sell_put_price - buy_call_price - buy_put_price) * 100
            
            # 检查最低权利金
            if net_premium >= min_premium:
                positions.append({
                    'open_date': current_date,
                    'open_price': current_price,
                    'dte': dte,
                    'sell_call_strike': sell_call_strike,
                    'sell_put_strike': sell_put_strike,
                    'buy_call_strike': buy_call_strike,
                    'buy_put_strike': buy_put_strike,
                    'net_premium': net_premium,
                    'iv': iv
                })
    
    # 统计结果
    total_trades = len(trades)
    if total_trades == 0:
        return {
            'trades': 0, 'wins': 0, 'win_rate': 0,
            'total_profit': 0, 'annual_return': 0,
            'max_drawdown': 0, 'final_capital': initial_capital
        }
    
    wins = sum(1 for t in trades if t['profit'] > 0)
    win_rate = wins / total_trades * 100
    
    # 计算收益
    years = (df['date'].max() - df['date'].min()).days / 365
    total_return = (cash - initial_capital) / initial_capital * 100
    annual_return = ((cash / initial_capital) ** (1/years) - 1) * 100
    
    # 计算最大回撤
    peak = initial_capital
    max_dd = 0
    running = initial_capital
    for t in trades:
        running += t['profit']
        if running > peak:
            peak = running
        dd = (peak - running) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    return {
        'trades': total_trades,
        'wins': wins,
        'win_rate': win_rate,
        'total_profit': cash - initial_capital,
        'annual_return': annual_return,
        'max_drawdown': max_dd,
        'final_capital': cash,
        'trades_detail': trades
    }

def main():
    print("="*80)
    print("SPY Iron Condor 15年回测 (2010-2025)")
    print("="*80)
    
    # 获取数据
    df = get_spy_data()
    if df is None:
        print("无法获取数据")
        return
    
    print(f"\n数据: {len(df)} 条 ({df['date'].min()} ~ {df['date'].max()})")
    
    # 测试参数组合
    params = [
        (0.05, 0.05, 7),
        (0.05, 0.08, 7),
        (0.10, 0.05, 7),
        (0.10, 0.08, 7),
        (0.10, 0.10, 7),
        (0.05, 0.05, 14),
        (0.05, 0.08, 14),
        (0.10, 0.08, 14),
        (0.05, 0.05, 21),
        (0.10, 0.10, 21),
        (0.05, 0.08, 30),
        (0.10, 0.08, 30),
    ]
    
    results = []
    print("\n" + "="*80)
    print("多参数回测结果")
    print("="*80)
    
    for otm, wing, dte in params:
        result = simulate_iron_condor(df, otm, wing, dte, 
                                       initial_capital=10000,
                                       min_premium=200,
                                       cooldown_days=5,
                                       early_close=1)
        
        results.append({
            'OTM%': int(otm*100),
            'Wing%': int(wing*100),
            'DTE': dte,
            'Trades': result['trades'],
            'Wins': result['wins'],
            'Win%': f"{result['win_rate']:.1f}%",
            'Profit': f"${result['total_profit']:,.0f}",
            'Annual%': f"{result['annual_return']:.1f}%",
            'MaxDD%': f"{result['max_drawdown']:.1f}%",
            'Final': f"${result['final_capital']:,.0f}"
        })
        
        print(f"OTM={int(otm*100):2d}% Wing={int(wing*100):2d}% DTE={dte:2d} | "
              f"交易:{result['trades']:3d} 胜率:{result['win_rate']:.1f}% | "
              f"年化:{result['annual_return']:6.1f}% 回撤:{result['max_drawdown']:5.1f}% | "
              f"利润:${result['total_profit']:,.0f}")
    
    # 显示最优结果
    print("\n" + "="*80)
    print("最优参数组合")
    print("="*80)
    
    best = max(results, key=lambda x: float(x['Annual%'].replace('%','').replace('$','')))
    print(f"最优: OTM={best['OTM%']}%, Wing={best['Wing%']}%, DTE={best['DTE']}")
    print(f"  年化收益: {best['Annual%']}, 最大回撤: {best['MaxDD%']}")
    print(f"  总交易: {best['Trades']}次, 胜率: {best['Win%']}")
    print(f"  最终资金: {best['Final']}")
    
    # 完整结果表
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('Annual%', ascending=False)
    print("\n完整排名:")
    print(results_df.to_string(index=False))
    
    # 保存结果
    results_df.to_csv('backtest_results/spy_15yr_backtest_results.csv', index=False)
    print("\n结果已保存到 backtest_results/spy_15yr_backtest_results.csv")

if __name__ == '__main__':
    main()