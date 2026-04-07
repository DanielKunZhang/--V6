#!/usr/bin/env python3
"""
计算QQQ HV20历史分布
"""
import pandas as pd
import numpy as np
import json
import sys
from datetime import datetime

# 解析JSON数据
data_str = """{"code": "US.QQQ", "ktype": "1d", "source": "history", "data": [{"time": "2023-01-03 00:00:00", "open": 263.189956594, "high": 264.664368969, "low": 256.802469093, "close": 259.104707686, "volume": 42335325, "turnover": 11214096052.0}, {"time": "2023-01-04 00:00:00", "open": 261.22080784, "high": 262.014345397, "low": 257.194339492, "close": 260.339099442, "volume": 47754861, "turnover": 12669330029.0}, {"time": "2023-01-05 00:00:00", "open": 258.673650247, "high": 258.840195167, "low": 255.950150976, "close": 256.263647295, "volume": 45396744, "turnover": 11923253547.0}, {"time": "2023-01-06 00:00:00", "open": 257.997673809, "high": 264.45373863, "low": 255.048849058, "close": 263.336907993, "volume": 54659739, "turnover": 14528203466.0}, {"time": "2023-01-09 00:00:00", "open": 265.325650267, "high": 269.695005214, "low": 264.43414511, "close": 265.041544228, "volume": 45568676, "turnover": 12425635323.0}, {"time": "2023-01-10 00:00:00", "open": 264.012884431, "high": 267.392766621, "low": 263.503452913, "close": 267.285002261, "volume": 35247763, "turnover": 9559275821.0}, {"time": "2023-01-11 00:00:00", "open": 268.352849098, "high": 272.016837327, "low": 267.5691083, "close": 271.909072967, "volume": 44077036, "turnover": 12143678320.0}, {"time": "2023-01-12 00:00:00", "open": 272.467488285, "high": 274.407246759, "low": 268.176507418, "close": 273.378586962, "volume": 60599953, "turnover": 16833170437.0}, {"time": "2023-01-13 00:00:00", "open": 270.88041317, "high": 275.5035042, "low": 270.547323331, "close": 275.259564877, "volume": 44802936, "turnover": 12501031121.0}, {"time": "2023-01-17 00:00:00", "open": 275.063629677, "high": 277.101355751, "low": 273.898794917, "close": 275.817980195, "volume": 36269738, "turnover": 10201942472.0}, {"time": "2023-01-18 00:00:00", "open": 277.35607151, "high": 278.903959585, "low": 272.026634086, "close": 272.232366046, "volume": 47754549, "turnover": 13395375698.0}, {"time": "2023-01-19 00:00:00", "open": 270.606103891, "high": 271.737629667, "low": 268.323458818, "close": 269.557850574, "volume": 44150436, "turnover": 12170389944.0}, {"time": "2023-01-20 00:00:00", "open": 271.164519209, "high": 277.26790067, "low": 270.106469132, "close": 276.934810831, "volume": 60613606, "turnover": 16949393097.0}, {"time": "2023-01-23 00:00:00", "open": 277.777332189, "high": 284.311771089, "low": 276.983794631, "close": 283.087176093, "volume": 52799905, "turnover": 15144800996.0}, {"time": "2023-01-24 00:00:00", "open": 282.226991824, "high": 283.168142829, "low": 278.833273557, "close": 279.8887789, "volume": 38552156, "turnover": 10984328584.0}, {"time": "2023-01-25 00:00:00", "open": 278.12018648, "high": 279.899806092, "low": 276.821603723, "close": 277.941484034, "volume": 39549455, "turnover": 11101301719.0}, {"time": "2023-01-26 00:00:00", "open": 280.388810371, "high": 282.556010973, "low": 279.325561318, "close": 279.970906616, "volume": 38755376, "turnover": 11085703704.0}, {"time": "2023-01-27 00:00:00", "open": 279.868534179, "high": 284.575238822, "low": 279.75270026, "close": 284.075169876, "volume": 43048275, "turnover": 12417266121.0}, {"time": "2023-01-30 00:00:00", "open": 283.274340587, "high": 284.432765275, "low": 277.335632264, "close": 278.312268791, "volume": 49282072, "turnover": 14073555310.0}, {"time": "2023-01-31 00:00:00", "open": 278.163355179, "high": 283.192734743, "low": 275.764055051, "close": 282.387645566, "volume": 66951725, "turnover": 19183620442.0}]}"""

try:
    data = json.loads(data_str)
    # 转换为DataFrame
    df = pd.DataFrame(data['data'])
    
    # 提取收盘价
    closes = pd.Series([float(d['close']) for d in data['data']])
    
    print(f"数据点数量: {len(closes)}")
    
    # 计算对数收益率
    log_returns = np.log(closes / closes.shift(1)).dropna()
    
    # 计算滚动20日年化波动率 (HV20)
    # 年化因子 sqrt(252)
    window = 20
    if len(log_returns) >= window:
        rolling_std = log_returns.rolling(window=window).std()
        hv20 = rolling_std * np.sqrt(252)
        
        # 移除NaN值
        hv20_clean = hv20.dropna()
        
        print(f"\nHV20分析 (基于{len(hv20_clean)}个有效数据点):")
        print(f"当前HV20: {0.261:.3f} (脚本计算值)")
        print(f"历史HV20统计:")
        print(f"  最小值: {hv20_clean.min():.3f}")
        print(f"  25%分位数: {hv20_clean.quantile(0.25):.3f}")
        print(f"  中位数: {hv20_clean.median():.3f}")
        print(f"  75%分位数: {hv20_clean.quantile(0.75):.3f}")
        print(f"  最大值: {hv20_clean.max():.3f}")
        print(f"  平均值: {hv20_clean.mean():.3f}")
        print(f"  标准差: {hv20_clean.std():.3f}")
        
        # 百分比分析
        thresholds = [0.15, 0.20, 0.25, 0.28, 0.30, 0.35]
        print(f"\nHV20阈值分布:")
        for th in thresholds:
            pct_below = (hv20_clean <= th).mean() * 100
            print(f"  ≤{th:.0%}: {pct_below:.1f}% 的时间")
        
        # 当前HV20所处百分位
        if 0.261 in hv20_clean.values:
            rank = (hv20_clean <= 0.261).mean() * 100
            print(f"\n当前HV20=0.261在历史分布中的位置: 高于{rank:.1f}%的历史值")
        else:
            # 近似计算
            sorted_hv = sorted(hv20_clean.values)
            lower_count = sum(1 for x in sorted_hv if x <= 0.261)
            rank = (lower_count / len(sorted_hv)) * 100
            print(f"\n当前HV20=0.261在历史分布中的位置: 约高于{rank:.1f}%的历史值")
            
    else:
        print(f"数据不足，需要至少{window+1}个数据点，当前只有{len(closes)}个")
        
except Exception as e:
    print(f"解析错误: {e}")
    print("使用完整数据...")
    
    # 尝试读取完整数据文件
    import subprocess
    result = subprocess.run(
        ["python3", "/Users/zhangkun/.workbuddy/skills/futuapi/scripts/quote/get_kline.py", 
         "US.QQQ", "--ktype", "1d", "--start", "2023-01-01", "--end", "2025-12-31", "--num", "1000", "--json"],
        capture_output=True, text=True, cwd="/Users/zhangkun/WorkBuddy/20260402141752/wheel_tencent"
    )
    
    if result.returncode == 0:
        output = result.stdout
        # 提取JSON部分
        lines = output.split('\n')
        json_lines = []
        in_json = False
        for line in lines:
            if line.strip().startswith('{'):
                in_json = True
            if in_json:
                json_lines.append(line)
            if line.strip().endswith('}'):
                break
        
        if json_lines:
            try:
                json_str = '\n'.join(json_lines)
                data = json.loads(json_str)
                
                # 提取收盘价序列
                closes_list = [float(item['close']) for item in data['data']]
                closes = pd.Series(closes_list)
                
                print(f"获取到 {len(closes)} 个数据点")
                
                # 计算对数收益率
                log_returns = np.log(closes / closes.shift(1)).dropna()
                
                # 计算滚动20日年化波动率 (HV20)
                window = 20
                if len(log_returns) >= window:
                    rolling_std = log_returns.rolling(window=window).std()
                    hv20 = rolling_std * np.sqrt(252)
                    
                    # 移除NaN值
                    hv20_clean = hv20.dropna()
                    
                    print(f"\nHV20分析 (基于{len(hv20_clean)}个有效数据点，2023-01-01至2025-12-31):")
                    print(f"当前HV20: {0.261:.3f} (脚本计算值)")
                    print(f"历史HV20统计:")
                    print(f"  最小值: {hv20_clean.min():.3f}")
                    print(f"  25%分位数: {hv20_clean.quantile(0.25):.3f}")
                    print(f"  中位数: {hv20_clean.median():.3f}")
                    print(f"  75%分位数: {hv20_clean.quantile(0.75):.3f}")
                    print(f"  最大值: {hv20_clean.max():.3f}")
                    print(f"  平均值: {hv20_clean.mean():.3f}")
                    print(f"  标准差: {hv20_clean.std():.3f}")
                    
                    # 百分比分析
                    thresholds = [0.15, 0.20, 0.25, 0.28, 0.30, 0.35]
                    print(f"\nHV20阈值分布:")
                    for th in thresholds:
                        pct_below = (hv20_clean <= th).mean() * 100
                        print(f"  ≤{th:.0%}: {pct_below:.1f}% 的时间")
                    
                    # 当前HV20所处百分位
                    sorted_hv = sorted(hv20_clean.values)
                    lower_count = sum(1 for x in sorted_hv if x <= 0.261)
                    rank = (lower_count / len(sorted_hv)) * 100
                    print(f"\n当前HV20=0.261在历史分布中的位置: 约高于{rank:.1f}%的历史值")
                    
                else:
                    print(f"数据不足，需要至少{window+1}个数据点，当前只有{len(closes)}个")
                    
            except Exception as e2:
                print(f"处理完整数据时出错: {e2}")
    else:
        print(f"获取数据失败: {result.stderr}")