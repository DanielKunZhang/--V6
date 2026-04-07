from futu import *
import pandas as pd

ctx = OpenQuoteContext('127.0.0.1', 11111)

print("=== 调试 VXN/VIX 数据获取 ===\n")

# 尝试获取VXN
vxn_codes = ['US.VXN', 'VXN', 'NDX.VXN', 'US.VIXN', '.VXN']
for code in vxn_codes:
    ret, data = ctx.get_market_snapshot([code])
    print(f"尝试代码: {code}")
    print(f"  返回码: {ret}")
    if ret == RET_OK:
        if not data.empty:
            print(f"  成功! 数据形状: {data.shape}")
            print(f"  字段: {list(data.columns)}")
            print(f"  首行数据:")
            for col in ['code', 'last_price', 'change_rate', 'update_time']:
                if col in data.columns:
                    print(f"    {col}: {data.iloc[0][col]}")
        else:
            print(f"  数据为空")
    else:
        print(f"  错误信息: {data}")
    print()

print("---\n")

# 获取VIX
vix_codes = ['US.VIX', 'VIX', '.VIX']
for code in vix_codes:
    ret, data = ctx.get_market_snapshot([code])
    print(f"尝试代码: {code}")
    print(f"  返回码: {ret}")
    if ret == RET_OK and not data.empty:
        print(f"  成功! 最新价: {data.iloc[0]['last_price']:.2f}, 涨跌幅: {data.iloc[0]['change_rate']*100:.2f}%")
    print()

print("---\n")

# 获取QQQ（作为对照）
ret, data = ctx.get_market_snapshot(['US.QQQ'])
print(f"尝试代码: US.QQQ")
print(f"  返回码: {ret}")
if ret == RET_OK and not data.empty:
    print(f"  成功! 最新价: ${data.iloc[0]['last_price']:.2f}, 涨跌幅: {data.iloc[0]['change_rate']*100:.2f}%")
else:
    print(f"  错误或数据为空: {data}")

print("\n=== 搜索所有指数代码 ===")
# 获取US市场的所有指数
ret, idx_data = ctx.get_stock_basicinfo(Market.US, SecurityType.IDX)
if ret == RET_OK and not idx_data.empty:
    print(f"找到 {len(idx_data)} 个指数")
    
    # 搜索包含"VOLATILITY"或"VIX"的指数
    volatility_indices = idx_data[idx_data['name'].str.contains('VOLATILITY|VIX|VXN', case=False, na=False)]
    if not volatility_indices.empty:
        print("\n找到波动率相关指数:")
        for idx, row in volatility_indices.iterrows():
            print(f"  {row['code']}: {row['name']}")
    else:
        print("\n未找到波动率指数，显示前10个指数:")
        for idx, row in idx_data.head(10).iterrows():
            print(f"  {row['code']}: {row['name']}")
else:
    print(f"无法获取指数列表: {idx_data if ret != RET_OK else '数据为空'}")

ctx.close()