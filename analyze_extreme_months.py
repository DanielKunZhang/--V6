#!/usr/bin/env python3
"""
分析QQQ极端月份涨跌幅
"""

import json
import sys

# 从命令行读取JSON数据
if len(sys.argv) < 2:
    print("Usage: python analyze_extreme_months.py <kline_json_file>")
    sys.exit(1)

filename = sys.argv[1]
# 文件可能包含日志行，提取JSON部分
json_lines = []
with open(filename, 'r') as f:
    for line in f:
        line = line.strip()
        if line.startswith('{'):
            json_lines.append(line)
        elif line.startswith('['):
            json_lines.append(line)
if not json_lines:
    print("未找到JSON数据")
    sys.exit(1)
# 合并所有JSON行（通常只有一行）
json_str = ''.join(json_lines)
data = json.loads(json_str)

kline_data = data['data']

# 查找特定极端月份
extreme_months = [
    ("2000-04", -41.8, "互联网泡沫破裂"),
    ("2008-10", -28.3, "金融危机"),
    ("2020-03", -14.9, "新冠熔断"),
    ("2000-11", None, "互联网泡沫延续"),
    ("2001-03", None, "互联网泡沫底部"),
    ("2002-09", None, "科技股二次探底"),
    ("2008-11", None, "金融危机延续"),
    ("2011-08", None, "欧债危机"),
    ("2018-12", None, "加息周期"),
    ("2022-06", None, "通胀飙升")
]

print("📊 QQQ极端月份涨跌幅分析 (2000-2025)")
print("=" * 60)

# 先计算所有月份的涨跌幅
monthly_returns = []
for i in range(1, len(kline_data)):
    prev_close = float(kline_data[i-1]['close'])
    curr_close = float(kline_data[i]['close'])
    month_return = (curr_close - prev_close) / prev_close * 100
    time_str = kline_data[i]['time'][:7]  # YYYY-MM
    
    monthly_returns.append((time_str, month_return, prev_close, curr_close))

# 找出跌幅最大的月份
monthly_returns_sorted = sorted(monthly_returns, key=lambda x: x[1])
print("\n🔻 跌幅最大的10个月份:")
for i in range(min(10, len(monthly_returns_sorted))):
    month_str, ret, prev, curr = monthly_returns_sorted[i]
    print(f"  {month_str}: {ret:.1f}% ({prev:.1f} → {curr:.1f})")

# 找出涨幅最大的月份
monthly_returns_sorted_desc = sorted(monthly_returns, key=lambda x: x[1], reverse=True)
print("\n🔺 涨幅最大的10个月份:")
for i in range(min(10, len(monthly_returns_sorted_desc))):
    month_str, ret, prev, curr = monthly_returns_sorted_desc[i]
    print(f"  {month_str}: {ret:.1f}% ({prev:.1f} → {curr:.1f})")

# 检查特定极端月份
print("\n🎯 用户关注的极端月份:")
for target_month, expected_return, desc in extreme_months:
    found = False
    for month_str, ret, prev, curr in monthly_returns:
        if month_str == target_month:
            found = True
            diff = ""
            if expected_return is not None:
                diff = f" (预期: {expected_return}%, 差异: {ret - expected_return:.1f}%)"
            print(f"  {target_month} ({desc}): {ret:.1f}%{diff}")
            break
    if not found:
        print(f"  {target_month} ({desc}): 未找到数据")

# 计算铁鹰策略在极端月份的可能表现
print("\n⚡ 铁鹰策略在极端月份的影响分析 (基于真实月K线数据)")
print("假设: DTE=30天, OTM=5%, Wing=8%, G2 (2组), 本金 $15,000")
print("=" * 80)

# 策略参数
OTM_PCT = 0.05
WING_PCT = 0.08
CREDIT_RATE = 0.015  # 权利金率 = 1.5% 股价
GROUPS = 2
STOP_LOSS_MULTIPLIER = 2.0  # 2倍权利金止损
HV20_THRESHOLD = 0.20  # 20% 波动率过滤
SLOW_BEAR_THRESHOLD = -0.07  # -7% 20日累计跌幅

# 计算每个月的铁鹰策略表现
print("\n📉 最差10个月份的铁鹰策略模拟表现:")
print("月份 | QQQ月回报% | 股价 | 权利金 | 是否突破OTM | 估算亏损 | 止损触发 | 防御机制评估")
print("-" * 100)

# 按回报排序取最差10个月
worst_months = sorted(monthly_returns, key=lambda x: x[1])[:10]

total_loss = 0
loss_months = 0

for month_str, ret, prev_close, curr_close in worst_months:
    # 估算股价（使用前收盘价）
    price = prev_close
    # 估算权利金（每股）
    credit_per_share = price * OTM_PCT * CREDIT_RATE  # 每股权利金
    credit_per_group = credit_per_share * 100  # 每张合约100股
    credit_total = credit_per_group * GROUPS
    
    # 判断是否突破OTM
    broken = abs(ret) > OTM_PCT * 100  # ret是百分比
    if broken:
        # 计算亏损百分比（在翼宽内线性估算）
        excess_move = abs(ret) - OTM_PCT * 100
        loss_pct = min(100, excess_move / (WING_PCT * 100) * 100)
        # 最大理论亏损（每股）
        max_loss_per_share = price * WING_PCT - credit_per_share
        max_loss_per_group = max_loss_per_share * 100
        max_loss_total = max_loss_per_group * GROUPS
        # 估算实际亏损
        estimated_loss = max_loss_total * (loss_pct / 100)
        status = "突破"
    else:
        estimated_loss = 0
        loss_pct = 0
        status = "安全"
    
    # 止损触发检查
    stop_loss_triggered = estimated_loss > credit_per_group * STOP_LOSS_MULTIPLIER * GROUPS
    
    # 防御机制评估（简化）
    # HV20过滤：需要日数据，这里用月内波动率近似（(high-low)/open）
    # 慢熊检测：需要前20日数据，无法计算
    defense_note = "需日数据评估"
    
    total_loss += estimated_loss
    if estimated_loss > 0:
        loss_months += 1
    
    print(f"{month_str} | {ret:5.1f}% | ${price:7.1f} | ${credit_per_share:.3f} | {status:^8} | ${estimated_loss:8.0f} | {'是' if stop_loss_triggered else '否':^6} | {defense_note}")

# 计算总亏损占本金比例
initial_capital = 15000
loss_pct_of_capital = total_loss / initial_capital * 100

print("\n📊 极端月份策略表现总结:")
print(f"最差10个月份中，策略被突破的次数: {loss_months}/10")
print(f"累计估算亏损: ${total_loss:,.0f} (占本金 {loss_pct_of_capital:.1f}%)")
print(f"平均单次亏损: ${total_loss/loss_months if loss_months>0 else 0:,.0f}")

# 分析历史极端月份（用户关注的）
print("\n🎯 用户关注的极端月份策略表现分析:")
special_months = ["2000-04", "2008-10", "2020-03", "2022-06"]
for target_month in special_months:
    found = False
    for month_str, ret, prev_close, curr_close in monthly_returns:
        if month_str == target_month:
            found = True
            price = prev_close
            credit_per_share = price * OTM_PCT * CREDIT_RATE
            broken = abs(ret) > OTM_PCT * 100
            if broken:
                excess_move = abs(ret) - OTM_PCT * 100
                loss_pct = min(100, excess_move / (WING_PCT * 100) * 100)
                max_loss_per_share = price * WING_PCT - credit_per_share
                max_loss_per_group = max_loss_per_share * 100
                max_loss_total = max_loss_per_group * GROUPS
                estimated_loss = max_loss_total * (loss_pct / 100)
            else:
                estimated_loss = 0
            
            # 评估防御机制
            defense_notes = []
            # 1. HV20过滤：如果月波动率 > 20%，可能阻止开仓
            # 但需要日数据，这里用月内高低价差估算波动率
            # 2. 慢熊检测：前20日累计跌幅 >7% 会触发防御
            # 3. 止损：如果亏损 > 2倍权利金会触发
            stop_loss_triggered = estimated_loss > credit_per_share * 100 * STOP_LOSS_MULTIPLIER * GROUPS
            if stop_loss_triggered:
                defense_notes.append("止损会触发")
            else:
                defense_notes.append("止损可能不触发")
            
            print(f"\n{target_month} (QQQ月回报: {ret:.1f}%):")
            print(f"  铁鹰状态: {'被突破' if broken else '安全'}")
            print(f"  估算亏损: ${estimated_loss:,.0f}")
            print(f"  防御机制: {', '.join(defense_notes)}")
            break
    if not found:
        print(f"{target_month}: 数据未找到")

print("\n🔒 策略防御机制在极端月份中的有效性分析:")
print("1. HV20过滤 (波动率>20%时禁止开仓):")
print("   - 在2000-04、2008-10、2020-03等极端月份，波动率极高")
print("   - 如果HV20过滤器生效，策略不会在月初开仓，避免亏损")
print("   - 但若已有持仓，仍需面对市场冲击")
print("2. 慢熊检测 (20日累计跌幅>7%时增大OTM至25%):")
print("   - 在渐进式下跌中，会提前增大保护距离")
print("   - 在2008-10等暴跌月份，可能来不及反应")
print("3. 硬止损 (单组亏损>2倍权利金时强制平仓):")
print("   - 在突破OTM后，如果亏损达到阈值，会及时平仓")
print("   - 限制单次亏损规模，避免灾难性损失")
print("4. 全局止损 (总亏损>20%时全部平仓):")
print("   - 保护整体本金，防止连续亏损累积")
print("5. 冷却期 (止损后暂停开仓15-30天):")
print("   - 避免在连续下跌中反复开仓亏损")

print("\n💡 延长回测至2008年的建议:")
print("✅ 建议运行完整回测 (backtest_real.py) 覆盖2000-2025年")
print("✅ 重点验证策略在2000-2002年互联网泡沫和2008年金融危机的表现")
print("✅ 检查HV20过滤器和慢熊检测在危机期间的有效性")
print("✅ 评估最大回撤是否在可接受范围内 (<20%)")
print("✅ 如果回撤过大，考虑调整参数: 增大OTM距离、减少组数、加强止损")