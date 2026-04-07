#!/usr/bin/env python3
"""
测试交易日校验逻辑（需要 OpenD 运行）

测试场景：
  1. 今天是否交易日
  2. 获取 2026 年 4 月港股交易日历
  3. 验证节假日识别（清明节 4-5 = 非交易日）
  4. 模拟到期日为 2026-04-29，计算平仓触发日（应为 4-28）
  5. 模拟到期日为 2026-01-29（农历年假期附近），验证平仓触发日跳过假期
"""

import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from data import FutuDataProvider


def section(title):
    print("\n" + "=" * 55)
    print(f"  {title}")
    print("=" * 55)


def main():
    data = FutuDataProvider()
    if not data.connect():
        print("❌ 无法连接 OpenD，请先启动富途 OpenD")
        return 1

    # ── 场景1：今天是否交易日 ─────────────────────────────
    section("场景1：今天是否港股交易日")
    today = date.today()
    is_td = data.is_hk_trading_day(today)
    print(f"今天 {today}（{today.strftime('%A')}）: {'✅ 交易日' if is_td else '🔴 非交易日'}")

    # ── 场景2：2026年4月全月交易日 ────────────────────────
    section("场景2：2026年4月港股交易日历")
    apr_days = data.get_hk_trading_days(date(2026, 4, 1), date(2026, 4, 30))
    print(f"共 {len(apr_days)} 个交易日：")
    for d in apr_days:
        print(f"  {d}  {d.strftime('%A')}")

    # ── 场景3：节假日识别（清明节） ───────────────────────
    section("场景3：清明节（2026-04-05 周日 + 2026-04-06 周一 调休）")
    for d in [date(2026, 4, 3), date(2026, 4, 4), date(2026, 4, 5),
              date(2026, 4, 6), date(2026, 4, 7)]:
        is_t = data.is_hk_trading_day(d)
        mark = "✅ 交易日" if is_t else "🔴 非交易日"
        print(f"  {d} ({d.strftime('%A'):9s}): {mark}")

    # ── 场景4：到期日 2026-04-29，平仓触发日 ─────────────
    section("场景4：到期日=2026-04-29，early_close=1天")
    expiry = date(2026, 4, 29)
    trigger = data.prev_n_trading_day(expiry, n=1)
    print(f"到期日: {expiry} ({expiry.strftime('%A')})")
    print(f"平仓触发日 (前1个交易日): {trigger} ({trigger.strftime('%A')})")
    expected = expiry - timedelta(days=1)
    print(f"自然日前1天: {expected} ({expected.strftime('%A')})")
    if trigger == expected:
        print("✅ 结果与自然日相同（无节假日干扰）")
    else:
        print(f"⚠️  结果不同（{expected} 是节假日，正确提前到 {trigger}）")

    # ── 场景5：early_close=2，前2个交易日 ────────────────
    section("场景5：到期日=2026-04-29，early_close=2天")
    trigger2 = data.prev_n_trading_day(expiry, n=2)
    print(f"平仓触发日 (前2个交易日): {trigger2} ({trigger2.strftime('%A')})")

    # ── 场景6：模拟"今天到了平仓触发日" ─────────────────
    section("场景6：模拟平仓触发逻辑")
    test_cases = [
        (date(2026, 4, 29), "到期当天"),
        (date(2026, 4, 28), "到期前1天（正常交易日）"),
        (date(2026, 4, 27), "到期前2天"),
        (date(2026, 4, 3),  "普通日，距到期还早"),
    ]
    for sim_today, desc in test_cases:
        trigger_d = data.prev_n_trading_day(expiry, n=1)
        should = sim_today >= trigger_d
        print(f"  模拟today={sim_today} ({desc}): {'🔴 需要平仓' if should else '⏳ 无需平仓'}")

    data.disconnect()
    print("\n✅ 测试完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
