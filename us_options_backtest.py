"""
美股期权回测 - 使用 Yahoo Finance 免费数据
测试标的: SPY, QQQ, TSLA, NVDA, AAPL
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class USOptionsBacktester:
    """美股期权回测器 (使用 Yahoo 数据模拟)"""
    
    def __init__(self, ticker: str, capital: float = 100000):
        self.ticker = ticker
        self.capital = capital
        self.initial_capital = capital
        self.trades: List[Dict] = []
        self.daily_pnl: List[Dict] = []
        
        # 美股费用 (Iron Condor 4条腿)
        self.commission_per_leg = 0.45  # $0.15佣金 + $0.30平台费
        self.commission_per_trade = self.commission_per_leg * 4  # 开仓4条腿
        
    def fetch_data(self, start: str, end: str) -> pd.DataFrame:
        """获取 Yahoo 历史数据"""
        logger.info(f"获取 {self.ticker} 数据 {start} ~ {end}")
        df = yf.download(self.ticker, start=start, end=end, progress=False)
        df = df.reset_index()
        df.columns = ['date', 'open', 'high', 'low', 'close', 'adj_close', 'volume']
        return df
    
    def estimate_option_price(self, 
                            stock_price: float, 
                            strike: float, 
                            days_to_expiry: int,
                            is_call: bool = True) -> float:
        """
        简化期权定价 (使用近似公式)
        实际权利金 ≈ 内在价值 + 时间价值
        """
        # 假设 IV = 30% (美股大盘股典型值)
        iv = 0.30
        
        # 时间价值近似
        time_value = stock_price * iv * np.sqrt(days_to_expiry / 365)
        
        # 内在价值
        if is_call:
            intrinsic = max(0, stock_price - strike)
        else:
            intrinsic = max(0, strike - stock_price)
        
        # 虚值期权只有时间价值
        if intrinsic == 0:
            return time_value * 0.5  # 虚值约50%时间价值
        else:
            return intrinsic + time_value * 0.3
    
    def backtest_iron_condor(self,
                            df: pd.DataFrame,
                            otm_pct: float = 0.05,
                            wing_pct: float = 0.08,
                            dte: int = 7,
                            early_close_days: int = 1) -> Dict:
        """
        Iron Condor 回测
        
        Args:
            df: 股价数据
            otm_pct: OTM距离 (如 0.05 = 5%)
            wing_pct: 翼宽 (如 0.08 = 8%)
            dte: 到期天数
            early_close_days: 提前平仓天数
        """
        current_date = df['date'].min()
        end_date = df['date'].max()
        
        # 找到每周的交易日
        df['week'] = df['date'].dt.isocalendar().week
        df['year'] = df['date'].dt.isocalendar().year
        weekly_dates = df.groupby(['year', 'week'])['date'].first().reset_index()['date']
        
        position = None
        
        for open_date in weekly_dates:
            if open_date > end_date - timedelta(days=dte):
                break
                
            # 获取开仓日价格
            open_row = df[df['date'] <= open_date].iloc[-1]
            stock_price = float(open_row['close'])
            
            # 计算行权价
            put_sell_strike = stock_price * (1 - otm_pct)
            put_buy_strike = put_sell_strike * (1 - wing_pct)
            call_sell_strike = stock_price * (1 + otm_pct)
            call_buy_strike = call_sell_strike * (1 + wing_pct)
            
            # 估算权利金 (每手100股)
            put_sell_premium = self.estimate_option_price(stock_price, put_sell_strike, dte, False) * 100
            put_buy_premium = self.estimate_option_price(stock_price, put_buy_strike, dte, False) * 100
            call_sell_premium = self.estimate_option_price(stock_price, call_sell_strike, dte, True) * 100
            call_buy_premium = self.estimate_option_price(stock_price, call_buy_strike, dte, True) * 100
            
            # 净权利金收入
            net_credit = (put_sell_premium - put_buy_premium + 
                        call_sell_premium - call_buy_premium)
            
            # 找到到期日
            expiry_date = open_date + timedelta(days=dte)
            expiry_row = df[df['date'] <= expiry_date].iloc[-1] if len(df[df['date'] <= expiry_date]) > 0 else None
            
            if expiry_row is None:
                continue
                
            expiry_price = float(expiry_row['close'])
            
            # 计算盈亏
            # Put 侧
            if expiry_price < put_sell_strike:
                put_loss = (put_sell_strike - max(expiry_price, put_buy_strike)) * 100
            else:
                put_loss = 0
                
            # Call 侧
            if expiry_price > call_sell_strike:
                call_loss = (min(expiry_price, call_buy_strike) - call_sell_strike) * 100
            else:
                call_loss = 0
                
            total_loss = put_loss + call_loss
            pnl = net_credit - total_loss - self.commission_per_trade * 2  # 开平仓
            
            self.trades.append({
                'open_date': open_date.strftime('%Y-%m-%d'),
                'expiry_date': expiry_date.strftime('%Y-%m-%d'),
                'stock_price': stock_price,
                'expiry_price': expiry_price,
                'put_sell': put_sell_strike,
                'put_buy': put_buy_strike,
                'call_sell': call_sell_strike,
                'call_buy': call_buy_strike,
                'net_credit': net_credit,
                'pnl': pnl,
                'win': pnl > 0
            })
            
            self.capital += pnl
            
        return self._calculate_stats()
    
    def _calculate_stats(self) -> Dict:
        """计算回测统计"""
        if not self.trades:
            return {}
            
        df_trades = pd.DataFrame(self.trades)
        total_pnl = df_trades['pnl'].sum()
        wins = df_trades[df_trades['win'] == True]
        losses = df_trades[df_trades['win'] == False]
        
        # 计算最大回撤
        cumulative = [self.initial_capital]
        for t in self.trades:
            cumulative.append(cumulative[-1] + t['pnl'])
        
        max_drawdown = 0
        peak = cumulative[0]
        for val in cumulative:
            if val > peak:
                peak = val
            drawdown = (peak - val) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        # 年化收益
        years = len(self.trades) / 52  # 假设每周一次
        total_return = total_pnl / self.initial_capital
        ann_return = (1 + total_return) ** (1 / max(years, 0.1)) - 1 if years > 0 else 0
        
        return {
            'ticker': self.ticker,
            'initial_capital': self.initial_capital,
            'final_capital': self.capital,
            'total_pnl': total_pnl,
            'total_return_pct': total_return * 100,
            'ann_return_pct': ann_return * 100,
            'max_drawdown_pct': max_drawdown * 100,
            'total_trades': len(self.trades),
            'win_count': len(wins),
            'loss_count': len(losses),
            'win_rate': len(wins) / len(self.trades) * 100 if len(self.trades) > 0 else 0,
            'avg_credit': df_trades['net_credit'].mean(),
            'avg_pnl': df_trades['pnl'].mean(),
            'commission_per_trade': self.commission_per_trade,
            'trades': self.trades
        }


def run_multi_ticker_backtest():
    """多标的回测对比"""
    tickers = ['SPY', 'QQQ', 'TSLA', 'NVDA', 'AAPL']
    results = []
    
    for ticker in tickers:
        logger.info(f"\n{'='*50}")
        logger.info(f"回测 {ticker}")
        logger.info(f"{'='*50}")
        
        try:
            bt = USOptionsBacktester(ticker, capital=100000)
            df = bt.fetch_data('2015-01-01', '2025-12-31')
            
            if len(df) < 100:
                logger.warning(f"{ticker} 数据不足，跳过")
                continue
                
            result = bt.backtest_iron_condor(df, otm_pct=0.10, wing_pct=0.08, dte=26)  # 与实盘一致
            results.append(result)
            
            logger.info(f"年化收益: {result['ann_return_pct']:.2f}%")
            logger.info(f"最大回撤: {result['max_drawdown_pct']:.2f}%")
            logger.info(f"开仓次数: {result['total_trades']}")
            logger.info(f"胜率: {result['win_rate']:.1f}%")
            logger.info(f"均次权利金: ${result['avg_credit']:.2f}")
            
        except Exception as e:
            logger.error(f"{ticker} 回测失败: {e}")
    
    # 生成对比报告
    generate_comparison_report(results)
    return results


def generate_comparison_report(results: List[Dict]):
    """生成对比报告"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>美股 Iron Condor 回测对比</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; background: #0f172a; color: #e2e8f0; }
            h1 { color: #60a5fa; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 30px; }
            .card { background: #1e293b; border-radius: 12px; padding: 24px; border: 1px solid #334155; }
            .card h3 { margin-top: 0; color: #94a3b8; font-size: 14px; text-transform: uppercase; }
            .metric { font-size: 36px; font-weight: bold; margin: 10px 0; }
            .positive { color: #4ade80; }
            .negative { color: #f87171; }
            .row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #334155; }
            .row:last-child { border-bottom: none; }
            .label { color: #94a3b8; }
            .value { font-weight: 500; }
            .fee-note { background: #1e293b; padding: 16px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f59e0b; }
        </style>
    </head>
    <body>
        <h1>🦅 美股 Iron Condor 回测对比 (Yahoo数据)</h1>
        <p>参数: 10% OTM, 8% 翼宽, DTE=26 (与实盘一致)</p>
        
        <div class="fee-note">
            <strong>💰 费用说明:</strong> 美股期权 $0.45/张 (佣金$0.15 + 平台费$0.30), Iron Condor 4条腿 = $1.80/次开平仓
        </div>
        
        <div class="grid">
    """
    
    colors = ['#60a5fa', '#4ade80', '#fbbf24', '#f87171', '#a78bfa']
    
    for i, r in enumerate(results):
        color = colors[i % len(colors)]
        return_class = 'positive' if r['ann_return_pct'] > 0 else 'negative'
        
        html += f"""
            <div class="card">
                <h3>{r['ticker']}</h3>
                <div class="metric {return_class}" style="color: {color}">{r['ann_return_pct']:+.2f}%</div>
                <div style="color: #94a3b8; margin-bottom: 16px;">年化收益</div>
                
                <div class="row">
                    <span class="label">总收益</span>
                    <span class="value">{r['total_return_pct']:+.2f}%</span>
                </div>
                <div class="row">
                    <span class="label">最大回撤</span>
                    <span class="value" style="color: #f87171">{r['max_drawdown_pct']:.2f}%</span>
                </div>
                <div class="row">
                    <span class="label">开仓次数</span>
                    <span class="value">{r['total_trades']} 次</span>
                </div>
                <div class="row">
                    <span class="label">胜率</span>
                    <span class="value">{r['win_rate']:.1f}%</span>
                </div>
                <div class="row">
                    <span class="label">均次权利金</span>
                    <span class="value">${r['avg_credit']:.2f}</span>
                </div>
                <div class="row">
                    <span class="label">均次盈亏</span>
                    <span class="value" style="color: {'#4ade80' if r['avg_pnl'] > 0 else '#f87171'}">${r['avg_pnl']:.2f}</span>
                </div>
                <div class="row">
                    <span class="label">费用/次</span>
                    <span class="value">${r['commission_per_trade']:.2f}</span>
                </div>
            </div>
        """
    
    html += """
        </div>
        <p style="margin-top: 40px; color: #64748b; font-size: 12px;">
            * 注: 使用 Yahoo Finance 历史股价模拟期权定价，实际权利金可能有所不同
        </p>
    </body>
    </html>
    """
    
    output_path = '/Users/zhangkun/WorkBuddy/20260402141752/wheel_tencent/backtest_results/us_options_comparison.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    logger.info(f"\n✅ 报告已生成: {output_path}")


if __name__ == '__main__':
    run_multi_ticker_backtest()
