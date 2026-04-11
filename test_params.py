#!/usr/bin/env python3
"""
Iron Condor 参数测试脚本
按照指定参数进行多时期历史回测

港股（腾讯）: 本金5万HKD, OTM=5%, Wing=8%, DTE=25
美股（SPY）: 本金1万USD, OTM=10%, Wing=8%, DTE=26
"""

import sys
import math
import logging
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest_real import fetch_futu_kline, bs_option_price, historical_volatility

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# ============================================
#  港股 Iron Condor 回测
# ============================================

def hk_option_expiry_for_month(year: int, month: int) -> date:
    """港股期权月度到期日"""
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    workdays_found = 0
    while True:
        if d.weekday() < 5:
            workdays_found += 1
            if workdays_found == 2:
                return d
        d -= timedelta(days=1)


def get_hk_option_expiries(start: date, end: date) -> List[date]:
    """获取区间内所有月度到期日"""
    expiries = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        exp = hk_option_expiry_for_month(y, m)
        if start <= exp <= end:
            expiries.append(exp)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return expiries


@dataclass
class ICPOS:
    sell_put_k: float
    buy_put_k: float
    sell_call_k: float
    buy_call_k: float
    net_credit: float
    open_date: date
    expiration: date


class HKBacktester:
    """港股 Iron Condor 回测"""
    LOT_SIZE = 100
    COMMISSION = 40  # HKD
    SLIPPAGE = 0.005

    def __init__(self, initial_capital=50000, otm=0.05, wing=0.08, dte=25):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.otm = otm
        self.wing = wing
        self.dte = dte
        self.trades = []
        self.daily = []

    def run(self, df: pd.DataFrame, label: str = "") -> Dict:
        """运行回测"""
        df = df.copy()
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values('date').reset_index(drop=True)

        # 生成月度到期日
        start_date = df['date'].min()
        end_date = df['date'].max()
        expiries = get_hk_option_expiries(start_date, end_date)

        # 按月开仓
        last_expiry = None

        for i, row in df.iterrows():
            current_date = row['date']
            price = row['Close']

            # 计算历史波动率
            if i >= 20:
                hist_vol = historical_volatility(df.iloc[:i+1]['Close'], iv_premium=1.15)
            else:
                hist_vol = 0.30

            # 找到最近的到期日
            exp = None
            for e in expiries:
                if e > current_date and (last_expiry is None or e != last_expiry):
                    exp = e
                    break

            if exp is None:
                continue

            days_to_exp = (exp - current_date).days

            # 入场逻辑：到期前DTE天开仓
            if days_to_exp == self.dte:
                # 检查是否已有持仓
                if last_expiry == exp:
                    continue

                # 计算行权价 - 正确的卖方价差结构
                # 保护腿（买）：更虚值 | 收取腿（卖）：更接近价内
                # 这样收到净权利金，最大亏损有限
                buy_put_k = int(price * (1 - self.otm))       # 虚值 PUT（保护腿）
                sell_put_k = int(buy_put_k * (1 + self.wing))  # 更价内 PUT（收取腿）
                buy_call_k = int(price * (1 + self.otm))      # 虚值 CALL（保护腿）
                sell_call_k = int(buy_call_k * (1 - self.wing))  # 更价内 CALL（收取腿）

                # 计算权利金
                T = self.dte / 365
                r = 0.04

                put_sell_p = bs_option_price(price, sell_put_k, T, hist_vol, r, "PUT")
                put_buy_p = bs_option_price(price, buy_put_k, T, hist_vol, r, "PUT")
                call_sell_p = bs_option_price(price, sell_call_k, T, hist_vol, r, "CALL")
                call_buy_p = bs_option_price(price, buy_call_k, T, hist_vol, r, "CALL")

                net_credit = (put_sell_p - put_buy_p + call_sell_p - call_buy_p) * self.LOT_SIZE

                # 记录开仓
                pos = ICPOS(sell_put_k, buy_put_k, sell_call_k, buy_call_k,
                           net_credit, current_date, exp)
                last_expiry = exp

                self.trades.append({
                    'date': current_date,
                    'expiry': exp,
                    'price': price,
                    'sell_put': sell_put_k,
                    'buy_put': buy_put_k,
                    'sell_call': sell_call_k,
                    'buy_call': buy_call_k,
                    'credit': net_credit,
                })

            # 检查是否到期 - 修正平仓逻辑
            if last_expiry and current_date >= last_expiry:
                # 计算到期盈亏
                exp_row = df[df['date'] <= last_expiry].iloc[-1]
                exp_price = exp_row['Close']

                # 查找对应交易
                for tr in reversed(self.trades):
                    if tr['expiry'] == last_expiry and 'pnl' not in tr:
                        # 修正后的行权价结构：
                        # 卖出的sell是更价内（sell_put > buy_put, sell_call < buy_call）
                        # 买的是更虚值作为保护
                        
                        # PUT边：如果价格跌破sell_put（更价内那腿），亏损
                        put_loss = 0
                        if exp_price <= tr['sell_put']:
                            # 亏损 = 价差 - 收到的权利金
                            put_loss = (tr['sell_put'] - tr['buy_put']) * self.LOT_SIZE
                        
                        # CALL边：如果价格涨过sell_call（更价内那腿），亏损
                        call_loss = 0
                        if exp_price >= tr['sell_call']:
                            # 亏损 = 价差 - 收到的权利金
                            call_loss = (tr['buy_call'] - tr['sell_call']) * self.LOT_SIZE
                        
                        # 净盈亏 = 权利金 - 亏损 - 佣金
                        pnl = tr['credit'] - put_loss - call_loss - self.COMMISSION * 4

                        tr['exp_price'] = exp_price
                        tr['pnl'] = pnl
                        tr['win'] = pnl > 0

                        self.cash += pnl
                        break

                last_expiry = None

            # 记录每日市值
            self.daily.append({
                'date': current_date,
                'cash': self.cash,
                'value': self.cash,
            })

        return self._stats(label)

    def _stats(self, label: str) -> Dict:
        if not self.trades:
            return {}

        df = pd.DataFrame(self.trades)
        wins = df[df.get('win', pd.Series([False]*len(df))) == True]
        losses = df[df.get('win', pd.Series([False]*len(df))) == False]

        # 计算最大回撤
        cum = [self.initial_capital]
        for d in self.daily:
            cum.append(d['value'])
        max_dd = 0
        peak = cum[0]
        for v in cum:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            max_dd = max(max_dd, dd)

        years = (self.daily[-1]['date'] - self.daily[0]['date']).days / 365 if self.daily else 1
        total_ret = (self.cash - self.initial_capital) / self.initial_capital
        ann_ret = (1 + total_ret) ** (1 / max(years, 0.1)) - 1 if years > 0 else 0

        return {
            'label': label,
            'initial': self.initial_capital,
            'final': self.cash,
            'total_return': total_ret * 100,
            'ann_return': ann_ret * 100,
            'max_drawdown': max_dd * 100,
            'trades': len(df),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(df) * 100 if len(df) > 0 else 0,
            'avg_credit': df['credit'].mean() if 'credit' in df.columns else 0,
            'avg_pnl': df.get('pnl', pd.Series([0]*len(df))).mean(),
        }


# ============================================
#  美股 Iron Condor 回测
# ============================================

def get_us_weekly_expiries(start: date, end: date) -> List[date]:
    """美股周度到期日（每周五）"""
    expiries = []
    d = start
    while d.weekday() != 4:
        d += timedelta(days=1)
    while d <= end:
        expiries.append(d)
        d += timedelta(days=7)
    return expiries


class USBacktester:
    """美股 Iron Condor 回测"""
    LOT_SIZE = 100
    COMMISSION = 1.8  # USD (4腿)
    SLIPPAGE = 0.01

    def __init__(self, initial_capital=10000, otm=0.10, wing=0.08, dte=26):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.otm = otm
        self.wing = wing
        self.dte = dte
        self.trades = []
        self.daily = []

    def run(self, df: pd.DataFrame, label: str = "") -> Dict:
        """运行回测"""
        df = df.copy()
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values('date').reset_index(drop=True)

        start_date = df['date'].min()
        end_date = df['date'].max()
        expiries = get_us_weekly_expiries(start_date, end_date)

        last_expiry = None

        for i, row in df.iterrows():
            current_date = row['date']
            price = row['Close']

            if i >= 20:
                hist_vol = historical_volatility(df.iloc[:i]['Close'].values, iv_premium=1.15)
            else:
                hist_vol = 0.30

            exp = None
            for e in expiries:
                if e > current_date and (last_expiry is None or e != last_expiry):
                    exp = e
                    break

            if exp is None:
                continue

            days_to_exp = (exp - current_date).days

            if days_to_exp == self.dte:
                if last_expiry == exp:
                    continue

                # 计算行权价
                sell_put_k = int(price * (1 - self.otm))
                buy_put_k = int(sell_put_k * (1 - self.wing))
                sell_call_k = int(price * (1 + self.otm))
                buy_call_k = int(sell_call_k * (1 + self.wing))

                # 权利金
                T = self.dte / 365
                r = 0.04

                put_sell_p = bs_option_price(price, sell_put_k, T, hist_vol, r, "PUT")
                put_buy_p = bs_option_price(price, buy_put_k, T, hist_vol, r, "PUT")
                call_sell_p = bs_option_price(price, sell_call_k, T, hist_vol, r, "CALL")
                call_buy_p = bs_option_price(price, buy_call_k, T, hist_vol, r, "CALL")

                net_credit = (put_sell_p - put_buy_p + call_sell_p - call_buy_p) * self.LOT_SIZE

                pos = ICPOS(sell_put_k, buy_put_k, sell_call_k, buy_call_k,
                           net_credit, current_date, exp)
                last_expiry = exp

                self.trades.append({
                    'date': current_date,
                    'expiry': exp,
                    'price': price,
                    'sell_put': sell_put_k,
                    'buy_put': buy_put_k,
                    'sell_call': sell_call_k,
                    'buy_call': buy_call_k,
                    'credit': net_credit,
                })

            if last_expiry and current_date >= last_expiry:
                exp_row = df[df['date'] <= last_expiry].iloc[-1]
                exp_price = exp_row['Close']

                for tr in reversed(self.trades):
                    if tr['expiry'] == last_expiry and 'pnl' not in tr:
                        put_loss = max(0, tr['sell_put'] - exp_price) * self.LOT_SIZE if exp_price < tr['sell_put'] else 0
                        call_loss = max(0, exp_price - tr['sell_call']) * self.LOT_SIZE if exp_price > tr['sell_call'] else 0

                        put_protection = max(0, exp_price - tr['buy_put']) * self.LOT_SIZE if exp_price < tr['buy_put'] else 0
                        call_protection = max(0, tr['buy_call'] - exp_price) * self.LOT_SIZE if exp_price > tr['buy_call'] else 0

                        total_loss = max(0, put_loss - put_protection) + max(0, call_loss - call_protection)
                        pnl = tr['credit'] - total_loss - self.COMMISSION

                        tr['exp_price'] = exp_price
                        tr['pnl'] = pnl
                        tr['win'] = pnl > 0

                        self.cash += pnl
                        break

                last_expiry = None

            self.daily.append({
                'date': current_date,
                'cash': self.cash,
                'value': self.cash,
            })

        return self._stats(label)

    def _stats(self, label: str) -> Dict:
        if not self.trades:
            return {}

        df = pd.DataFrame(self.trades)
        wins = df[df.get('win', pd.Series([False]*len(df))) == True]
        losses = df[df.get('win', pd.Series([False]*len(df))) == False]

        cum = [self.initial_capital]
        for d in self.daily:
            cum.append(d['value'])
        max_dd = 0
        peak = cum[0]
        for v in cum:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            max_dd = max(max_dd, dd)

        years = (self.daily[-1]['date'] - self.daily[0]['date']).days / 365 if self.daily else 1
        total_ret = (self.cash - self.initial_capital) / self.initial_capital
        ann_ret = (1 + total_ret) ** (1 / max(years, 0.1)) - 1 if years > 0 else 0

        return {
            'label': label,
            'initial': self.initial_capital,
            'final': self.cash,
            'total_return': total_ret * 100,
            'ann_return': ann_ret * 100,
            'max_drawdown': max_dd * 100,
            'trades': len(df),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(df) * 100 if len(df) > 0 else 0,
            'avg_credit': df['credit'].mean() if 'credit' in df.columns else 0,
            'avg_pnl': df.get('pnl', pd.Series([0]*len(df))).mean(),
        }


# ============================================
#  主测试
# ============================================

def test_hk_tencent():
    """测试港股腾讯"""
    print("\n" + "="*60)
    print("📊 港股 Iron Condor 回测 - 腾讯 00700.HK")
    print("参数: 本金=5万HKD, OTM=5%, Wing=8%, DTE=25")
    print("="*60)

    # 获取数据
    print("\n📥 获取腾讯历史数据...")
    df = fetch_futu_kline("HK.00700", "2019-01-01", "2025-12-31")
    if df is None:
        print("❌ 无法获取数据，请检查富途OpenD是否启动")
        return

    print(f"✅ 获取 {len(df)} 个交易日")

    # 多时期测试
    periods = [
        ("2019-2020", "2019-01-01", "2020-12-31"),
        ("2020-2021", "2020-01-01", "2021-12-31"),
        ("2022", "2022-01-01", "2022-12-31"),
        ("2023-2024", "2023-01-01", "2024-12-31"),
        ("2025", "2025-01-01", "2025-12-31"),
        ("2019-2025全周期", "2019-01-01", "2025-12-31"),
    ]

    results = []

    for label, start, end in periods:
        period_df = df[(df['date'] >= pd.to_datetime(start).date()) &
                      (df['date'] <= pd.to_datetime(end).date())]
        if len(period_df) < 50:
            continue

        bt = HKBacktester(initial_capital=50000, otm=0.05, wing=0.08, dte=25)
        r = bt.run(period_df, label)

        if r:
            results.append(r)
            print(f"\n--- {label} ---")
            print(f"  年化: {r['ann_return']:+.2f}%")
            print(f"  回撤: {r['max_drawdown']:.2f}%")
            print(f"  次数: {r['trades']} 次")
            print(f"  胜率: {r['win_rate']:.1f}%")
            print(f"  均次权利金: {r['avg_credit']:.0f} HKD")

    return results


def test_us_spy():
    """测试美股SPY"""
    print("\n" + "="*60)
    print("📊 美股 Iron Condor 回测 - SPY")
    print("参数: 本金=1万USD, OTM=10%, Wing=8%, DTE=26")
    print("="*60)

    # 使用Yahoo Finance获取数据
    import yfinance as yf

    print("\n📥 获取SPY历史数据...")
    data = yf.download("SPY", start="2019-01-01", end="2025-12-31", progress=False)
    df = data.reset_index()
    df.columns = ['date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']

    print(f"✅ 获取 {len(df)} 个交易日")

    periods = [
        ("2019-2020", "2019-01-01", "2020-12-31"),
        ("2020-2021", "2020-01-01", "2021-12-31"),
        ("2022", "2022-01-01", "2022-12-31"),
        ("2023-2024", "2023-01-01", "2024-12-31"),
        ("2025", "2025-01-01", "2025-12-31"),
        ("2019-2025全周期", "2019-01-01", "2025-12-31"),
    ]

    results = []

    for label, start, end in periods:
        period_df = df[(df['date'] >= pd.to_datetime(start)) &
                      (df['date'] <= pd.to_datetime(end))]
        if len(period_df) < 50:
            continue

        bt = USBacktester(initial_capital=10000, otm=0.10, wing=0.08, dte=26)
        r = bt.run(period_df, label)

        if r:
            results.append(r)
            print(f"\n--- {label} ---")
            print(f"  年化: {r['ann_return']:+.2f}%")
            print(f"  回撤: {r['max_drawdown']:.2f}%")
            print(f"  次数: {r['trades']} 次")
            print(f"  胜率: {r['win_rate']:.1f}%")
            print(f"  均次权利金: ${r['avg_credit']:.0f}")

    return results


def generate_report(hk_results: List[Dict], us_results: List[Dict]):
    """生成HTML报告"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Iron Condor 参数测试报告</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; background: #0f172a; color: #e2e8f0; }
        h1 { color: #60a5fa; }
        h2 { color: #94a3b8; margin-top: 40px; }
        .section { background: #1e293b; border-radius: 12px; padding: 24px; margin: 20px 0; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; }
        .positive { color: #4ade80; }
        .negative { color: #f87171; }
        .config { background: #334155; padding: 16px; border-radius: 8px; margin: 20px 0; }
    </style>
</head>
<body>
    <h1>🦅 Iron Condor 参数测试报告</h1>
    <div class="config">
        <h3>📋 测试参数</h3>
        <p><strong>港股（腾讯）:</strong> 本金=5万HKD, OTM=5%, Wing=8%, DTE=25</p>
        <p><strong>美股（SPY）:</strong> 本金=1万USD, OTM=10%, Wing=8%, DTE=26</p>
    </div>

    <h2>📈 港股测试结果（腾讯 00700.HK）</h2>
    <div class="section">
        <table>
            <tr>
                <th>时期</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>开仓次数</th>
                <th>胜率</th>
                <th>均次权利金</th>
            </tr>
    """

    for r in hk_results:
        color_class = 'positive' if r['ann_return'] > 0 else 'negative'
        html += f"""
            <tr>
                <td>{r['label']}</td>
                <td class="{color_class}">{r['ann_return']:+.2f}%</td>
                <td class="negative">{r['max_drawdown']:.2f}%</td>
                <td>{r['trades']} 次</td>
                <td>{r['win_rate']:.1f}%</td>
                <td>{r['avg_credit']:.0f} HKD</td>
            </tr>
        """

    html += """
        </table>
    </div>

    <h2>📈 美股测试结果（SPY）</h2>
    <div class="section">
        <table>
            <tr>
                <th>时期</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>开仓次数</th>
                <th>胜率</th>
                <th>均次权利金</th>
            </tr>
    """

    for r in us_results:
        color_class = 'positive' if r['ann_return'] > 0 else 'negative'
        html += f"""
            <tr>
                <td>{r['label']}</td>
                <td class="{color_class}">{r['ann_return']:+.2f}%</td>
                <td class="negative">{r['max_drawdown']:.2f}%</td>
                <td>{r['trades']} 次</td>
                <td>{r['win_rate']:.1f}%</td>
                <td>${r['avg_credit']:.0f}</td>
            </tr>
        """

    html += """
        </table>
    </div>

    <h2>💡 分析总结</h2>
    <div class="section">
        <ul>
            <li>港股腾讯：波动适中，权利金较高，适合 Iron Condor</li>
            <li>美股 SPY：流动性最好，波动相对稳定</li>
            <li>DTE=25（港股月度）和 DTE=26（美股周度）能覆盖大部分行情</li>
        </ul>
    </div>
</body>
</html>
    """

    output_path = "/Users/zhangkun/WorkBuddy/20260402141752/wheel_tencent/backtest_results/param_test_report.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ 报告已生成: {output_path}")
    return output_path


if __name__ == "__main__":
    print("="*60)
    print("🦅 Iron Condor 参数测试")
    print("="*60)

    # 测试港股
    hk_results = test_hk_tencent()

    # 测试美股
    us_results = test_us_spy()

    # 生成报告
    if hk_results or us_results:
        generate_report(hk_results, us_results)