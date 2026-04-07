# 港股 vs 美股 Iron Condor 脚本对比与改进

## 2026-04-05 改进完成

### 1. refresh_cache=True 改进（futuapi 最佳实践）

已在两个脚本的所有持仓查询位置添加 `refresh_cache=True`：

| 脚本 | 位置 |
|------|------|
| main_ic.py (港股) | `_check_existing_positions()`, `_get_positions_with_expiry()` |
| main_ic_us.py (美股) | `check_existing_positions()`, `_get_positions_with_expiry()` |

### 2. 非交易日跳过机制对比

| 功能 | 港股 (main_ic.py) | 美股 (main_ic_us.py) |
|------|-------------------|---------------------|
| 交易日判断 | ✅ `_is_today_trading_day()` 使用 `data.is_hk_trading_day()` | ✅ `_is_today_trading_day()` 使用 `quote_ctx.request_trading_days(market=Market.US)` |
| check_and_manage 入口 | ✅ 先检查交易日再执行 | ✅ 改进后新增（之前缺失） |

### 3. 平仓机制对比

| 功能 | 港股 (main_ic.py) | 美股 (main_ic_us.py) |
|------|-------------------|---------------------|
| 平仓触发逻辑 | ✅ `_should_close_today()` 使用 `prev_n_trading_day()` 确保在正确的交易日平仓 | ✅ 改进后新增类似逻辑 |
| 长假预警 | ✅ 港股有完整的长假预警机制 | ✅ 改进后添加 |
| 平仓核心逻辑 | `today >= close_trigger_day` | `today >= close_trigger_day`（对齐） |

### 4. 主要差异点（正常差异）

| 项目 | 港股 | 美股 |
|------|------|------|
| 标的 | HK.00700 (腾讯) | US.QQQ (纳指100) |
| DTE | 25-30天（月度） | 26天（月度） |
| OTM | 5% | 10% |
| Wing | 8% | 8% |
| 最大组数 | 2组 | 2组 |

### 5. 港股特有功能（暂不需要移植）

- 止损通知（`notifier.notify_alert`）- 美股脚本已预留结构但未接入
- 平仓前7天预警机制（港股专属：pre_expiry 7天模式）

---

## 待办

- [ ] 美股脚本接入 notifier 通知（与港股对齐）
- [ ] 美股添加 daemon 模式支持（当前只支持 --once）