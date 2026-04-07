#!/usr/bin/env python3
"""诊断脚本：安全获取期权链数据，不假设列名"""
from futu import *
import pandas as pd
import numpy as np
from datetime import date

ctx = OpenQuoteContext(host='127.0.0.1', port=11111)

# 1. 获取K线 - 先打印结构再取值
print("=== 1. 获取K线 ===")
result = ctx.request_history_kline('HK.00700', ktype=KLType.K_DAY, max_count=5)
print(f"返回类型: {type(result)}, 长度: {len(result)}")
for i, item in enumerate(result):
    print(f"  result[{i}]: type={type(item)}")
    if hasattr(item, 'shape'):
        print(f"    shape={item.shape}, columns={list(item.columns)}")
        print(item.head(2))
    elif isinstance(item, (int, float, str)):
        print(f"    value={item}")

# 安全提取
if len(result) >= 2:
    ret = result[0]
    kline = result[1]
elif isinstance(result, tuple) and len(result) == 3:
    ret, kline, _ = result
else:
    # 尝试旧格式
    try:
        ret, kline = result[:2]
    except:
        print("无法解析K线返回值!")
        ctx.close()
        exit(1)

print(f"\nret={ret}")
print(f"kline columns={list(kline.columns)}")
# 找close列
close_col = None
for c in kline.columns:
    if str(c).lower() in ('close', 'closing_price', 'close_price'):
        close_col = c
        break
if close_col is None:
    close_col = kline.columns[-1]  # 最后一个通常是收盘价
    print(f"  ⚠️ 未找到close列，使用最后一个: {close_col}")
else:
    print(f"  使用close列: {close_col}")

S = float(kline.iloc[-1][close_col])
time_col = 'time_key' if 'time_key' in kline.columns else kline.columns[0]
print(f"腾讯最近收盘价: {S:.2f} HKD")

# 2. 获取期权链
print("\n=== 2. 获取期权链 ===")
ret2, chain = ctx.get_option_chain('HK.00700')
print(f"期权链: {len(chain)} 条记录")
print(f"columns={list(chain.columns)}")
if ret2 != RET_OK:
    print(f"FAIL: {chain}")
    ctx.close()
    exit()

exp_dates = sorted(chain['expiry_date'].unique())
today = date(2026, 4, 5)
print(f"到期日列表(前10): {exp_dates[:10]}")

# 选30天附近的到期日
near_exp = None
dte_real = 0
for ed in exp_dates:
    ed_date = pd.to_datetime(ed).date()
    days = (ed_date - today).days
    if 20 <= days <= 45:
        near_exp = ed
        dte_real = days
        break
if not near_exp:
    for ed in exp_dates[:5]:
        ed_date = pd.to_datetime(ed).date()
        if ed_date > today:
            near_exp = ed
            dte_real = (ed_date - today).days
            break

print(f"\n选择到期日: {near_exp}, DTE={dte_real}天")

sub = chain[chain['expiry_date'] == near_exp]
puts = sub[sub['option_type']=='PUT'].copy()
calls = sub[sub['option_type']=='CALL'].copy()

otm, wing = 0.05, 0.08
targets = {
    'sell_put': S*(1-otm), 'buy_put': S*(1-otm-wing),
    'sell_call': S*(1+otm), 'buy_call': S*(1+otm+wing),
}

def find_best(df, target):
    if df.empty: return None, None, None
    d = df.copy()
    d['dist'] = abs(d['strike_price'] - target)
    d = d.sort_values('dist')
    b = d.iloc[0]
    iv = b.get('implied_volatility', None)
    lp = b.get('last_price', None)
    return b['strike_price'], iv, lp

print()
print('='*65)
print(f'  V5公式目标 vs 真实期权链 | S={S:.0f}, OTM={otm*100}%, Wing={wing*100}%')
print('='*65)

for name, tgt in targets.items():
    df = puts if 'put' in name else calls
    k, iv, lp = find_best(df, tgt)
    side = 'PUT' if 'put' in name else 'CALL'
    print(f'  {name:12s}: 目标={tgt:7.1f} -> 最近行权价={k:7.0f}  IV={iv}, last={lp}')

# 汇总IV
ivs = []
iv_data = []
for name, tgt in targets.items():
    df = puts if 'put' in name else calls
    _, iv, lp = find_best(df, tgt)
    if iv and pd.notna(iv):
        try:
            fiv = float(iv)
            ivs.append(fiv)
            iv_data.append((name, fiv))
        except: pass

if ivs:
    avg_iv = np.mean(ivs)
    print(f'\n  真实IV均值: {avg_iv:.1%}  范围: {min(ivs):.1%}-{max(ivs):.1%}')
    for n, v in iv_data:
        print(f'    {n}: IV={v:.1%}')

# BS定价对比 - 内联实现
from scipy.stats import norm
import math

def bs_price(S, K, T_years, sigma, option_type):
    """BS定价，返回每张（100股）价格"""
    if T_years <= 0.001 or sigma <= 0.001:
        intrinsic = max(S - K, 0) if option_type == 'CALL' else max(K - S, 0)
        return intrinsic / 100.0
    r = 0.03  # 港币利率约3%
    d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T_years) / (sigma*math.sqrt(T_years))
    d2 = d1 - sigma * math.sqrt(T_years)
    if option_type == 'CALL':
        price = S*norm.cdf(d1) - K*math.exp(-r*T_years)*norm.cdf(d2)
    else:
        price = K*math.exp(-r*T_years)*norm.cdf(-d2) - S*norm.cdf(-d1)
    return price / 100.0  # per lot (100 shares)

if ivs:
    avg_iv = np.mean(ivs)
    print(f'\n  BS定价对比 (DTE={dte_real}, S={S:.0f}):')
    total_hv = 0
    total_iv = 0
    for name, tgt in targets.items():
        side = 'PUT' if 'put' in name else 'CALL'
        price_hv = bs_price(S, tgt, dte_real/365, 0.35, side)
        price_iv = bs_price(S, tgt, dte_real/365, avg_iv, side)
        diff_pct = (price_iv/price_hv-1)*100 if price_hv > 0 else 0
        total_hv += price_hv
        total_iv += price_iv
        print(f'    {name:12s}: HV(35%)={price_hv:8.1f}HKD  IV({avg_iv:.0%})={price_iv:8.1f}HKD  差异={diff_pct:+.0f}%')

    # 净权利金对比
    sell_legs_hv = sum(bs_price(S, targets[n], dte_real/365, 0.35, 'PUT') if 'put' in n else bs_price(S, targets[n], dte_real/365, 0.35, 'CALL') for n in ['sell_put','sell_call'])
    buy_legs_hv = sum(bs_price(S, targets[n], dte_real/365, 0.35, 'PUT') if 'put' in n else bs_price(S, targets[n], dte_real/365, 0.35, 'CALL') for n in ['buy_put','buy_call'])
    sell_legs_iv = sum(bs_price(S, targets[n], dte_real/365, avg_iv, 'PUT') if 'put' in n else bs_price(S, targets[n], dte_real/365, avg_iv, 'CALL') for n in ['sell_put','sell_call'])
    buy_legs_iv = sum(bs_price(S, targets[n], dte_real/365, avg_iv, 'PUT') if 'put' in n else bs_price(S, targets[n], dte_real/365, avg_iv, 'CALL') for n in ['buy_put','buy_call'])
    
    print(f'\n  净权利金/组:')
    print(f'    HV=35%时: ({sell_legs_hv:.0f}+{sell_legs_hv:.0f})-({buy_legs_hv:.0f}+{buy_legs_hv:.0f}) = ... 等等分开算:')
    
    sp_hv = bs_price(S, targets['sell_put'], dte_real/365, 0.35, 'PUT')
    bp_hv = bs_price(S, targets['buy_put'], dte_real/365, 0.35, 'PUT')
    sc_hv = bs_price(S, targets['sell_call'], dte_real/365, 0.35, 'CALL')
    bc_hv = bs_price(S, targets['buy_call'], dte_real/365, 0.35, 'CALL')
    net_hv = sp_hv + sc_hv - bp_hv - bc_hv
    
    sp_iv = bs_price(S, targets['sell_put'], dte_real/365, avg_iv, 'PUT')
    bp_iv = bs_price(S, targets['buy_put'], dte_real/365, avg_iv, 'PUT')
    sc_iv = bs_price(S, targets['sell_call'], dte_real/365, avg_iv, 'CALL')
    bc_iv = bs_price(S, targets['buy_call'], dte_real/365, avg_iv, 'CALL')
    net_iv = sp_iv + sc_iv - bp_iv - bc_iv
    
    print(f'    HV=35%净权利金: ({sp_hv:.0f}+{sc_hv:.0f})-({bp_hv:.0f}+{bc_hv:.0f}) = {net_hv:.0f} HKD/组')
    print(f'    IV={avg_iv:.0%}净权利金: ({sp_iv:.0f}+{sc_iv:.0f})-({bp_iv:.0f}+{bc_iv:.0f}) = {net_iv:.0f} HKD/组')
    print(f'    差异: {(net_iv/net_hv-1)*100:+.0f}%')
    print(f'\n  ⚠️ 关键结论: 如果真实IV >> 历史HV, 则回测低估了实际权利金!')

ctx.close()
print("\n=== 完成 ===")
