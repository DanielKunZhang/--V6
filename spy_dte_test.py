# SPY DTE 参数优化回测
import re, json, pandas as pd
from datetime import date, timedelta

# 读取文件
with open('data/spy_kline.json') as f:
    lines = f.readlines()

# 找到 JSON 行（以 {"code" 开头）
json_lines = []
for line in lines:
    if line.startswith('{"code"'):
        json_lines.append(line)
        break
    elif json_lines:
        json_lines.append(line)

# 合并 JSON 行并解析
text = ''.join(json_lines)
data = json.loads(text)
df = pd.DataFrame(data['data'])
df['date'] = pd.to_datetime(df['time']).dt.date
df['close'] = df['close'].astype(float)
prices = df.set_index('date')['close']
print(f'SPY: {len(df)}天')

# 周度到期日
weekly = []
c = prices.index[0]
while c <= prices.index[-1]:
    if c.weekday() == 4:
        weekly.append(c)
    c += timedelta(days=1)
weekly = [e for e in weekly if date(2024,1,1) <= e <= date(2025,12,31)]
print(f'周度到期日: {len(weekly)}')

# 参数
otm, wing, init = 0.10, 0.08, 10000

def test(dte):
    trades, cap = [], init
    for exp in weekly:
        od = exp - timedelta(days=dte)
        if od not in prices.index:
            continue
        S = prices[od]
        cred = S * (0.012 + dte/800)  # 权利金估算
        if exp not in prices.index:
            continue
        cS = prices[exp]
        lo, hi = S*(1-otm), S*(1+otm)
        if cS < lo or cS > hi:
            pnl = cred*100 - wing*S*100
        else:
            pnl = cred*100
        pnl = max(pnl, -wing*S*100)
        trades.append(pnl)
        cap += pnl
    if not trades:
        return None
    return {'dte': dte, 'trades': len(trades), 'pnl': sum(trades), 
            'wins': len([t for t in trades if t > 0]),
            'annual': (cap/init - 1) / 2 * 100}

print('\nDTE    交易    盈亏      年化')
print('-' * 45)
rs = []
for dte in range(7, 31):
    r = test(dte)
    if r and r['trades'] > 0:
        rs.append(r)
        print(f'{dte:3d}    {r["trades"]:2d}    {r["pnl"]:7.0f}   {r["annual"]:6.1f}%')

if rs:
    dr = pd.DataFrame(rs)
    best = dr.loc[dr['annual'].idxmax()]
    print(f'\n✅ 最优: DTE={int(best["dte"])}, 年化={best["annual"]:.1f}%')