from futu import *
import numpy as np
from datetime import date, datetime, timedelta

quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)

print("=== 波动率指数对比 ===\n")

# 尝试获取VXN（纳斯达克100波动率指数）
vxn_codes = ['US.VXN', 'VXN', 'NDX.VXN', 'US.VIXN', '.VXN']
vxn_data = None
vxn_code_used = None

for code in vxn_codes:
    ret, data = quote_ctx.get_market_snapshot([code])
    if ret == RET_OK and not data.empty and data.iloc[0]['last_price'] > 0:
        vxn_data = data.iloc[0]
        vxn_code_used = code
        break

if vxn_data is not None:
    print(f"✅ VXN ({vxn_code_used}) 数据:")
    print(f"   最新价: {vxn_data['last_price']:.2f}")
    print(f"   涨跌幅: {vxn_data['change_rate']*100:.2f}%")
    print(f"   更新时间: {vxn_data['update_time']}")
else:
    print("❌ 无法获取VXN数据")

print()

# 获取VIX（标普500波动率指数）
vix_codes = ['US.VIX', 'VIX', '.VIX']
vix_data = None
vix_code_used = None

for code in vix_codes:
    ret, data = quote_ctx.get_market_snapshot([code])
    if ret == RET_OK and not data.empty and data.iloc[0]['last_price'] > 0:
        vix_data = data.iloc[0]
        vix_code_used = code
        break

if vix_data is not None:
    print(f"✅ VIX ({vix_code_used}) 数据:")
    print(f"   最新价: {vix_data['last_price']:.2f}")
    print(f"   涨跌幅: {vix_data['change_rate']*100:.2f}%")
    print(f"   更新时间: {vix_data['update_time']}")
else:
    print("❌ 无法获取VIX数据")

print()

# 获取QQQ数据
ret, qqq_data = quote_ctx.get_market_snapshot(['US.QQQ'])
if ret == RET_OK and not qqq_data.empty:
    qqq = qqq_data.iloc[0]
    print(f"✅ QQQ 数据:")
    print(f"   最新价: ${qqq['last_price']:.2f}")
    print(f"   涨跌幅: {qqq['change_rate']*100:.2f}%")
    print(f"   更新时间: {qqq['update_time']}")
else:
    print("❌ 无法获取QQQ数据")

print("\n=== 策略参数对比 ===")
print(f"我们的 HV20 阈值: 25%")
print(f"我们的 HV20 计算值: 26.1% (来自之前日志)")

if vxn_data is not None:
    vxn_value = vxn_data['last_price']
    print(f"\nVXN 当前值: {vxn_value:.1f}%")
    if vxn_value <= 25:
        print(f"✅ VXN ({vxn_value:.1f}%) ≤ 25% 阈值")
    else:
        print(f"⚠️  VXN ({vxn_value:.1f}%) > 25% 阈值")
    
    # 比较HV20和VXN
    hv20_calc = 26.1  # 我们的计算值
    diff = hv20_calc - vxn_value
    print(f"差异: HV20 ({hv20_calc:.1f}%) - VXN ({vxn_value:.1f}%) = {diff:.1f}个百分点")

if vix_data is not None:
    vix_value = vix_data['last_price']
    print(f"\nVIX 当前值: {vix_value:.1f}% (参考)")
    print(f"VXN-VIX 差值: {vxn_data['last_price'] - vix_value:.1f}个百分点 (如果VXN数据可用)")

# 检查是否有纳斯达克100指数代码
print("\n=== 搜索纳斯达克相关指数 ===")
ret, idx_data = quote_ctx.get_stock_basicinfo(Market.US, SecurityType.IDX)
if ret == RET_OK and not idx_data.empty:
    nasdaq_indices = idx_data[idx_data['name'].str.contains('NASDAQ', case=False, na=False) | 
                              idx_data['code'].str.contains('NDX', case=False, na=False)]
    if not nasdaq_indices.empty:
        print("找到纳斯达克相关指数:")
        for idx, row in nasdaq_indices.head(10).iterrows():
            print(f"  {row['code']}: {row['name']}")
    else:
        print("未找到纳斯达克指数")
else:
    print("无法获取指数列表")

quote_ctx.close()