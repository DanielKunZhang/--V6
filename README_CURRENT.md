# README_CURRENT

当前生产系统是美股多标的 `Iron Condor` 自动交易框架。

## 生产目标

- 主交易标的：`US.QQQ` / `US.IWM` / `US.GLD`
- 策略结构：不对称铁鹰 `Put 3.0% / Call 6.0% / Wing 9% / DTE 45`
- 资金：`$15,000` 实际本金
- 杠杆：`2x`
- 名义资金：`$30,000`
- 动态组数：`Config F=20x`

## 当前实盘配置基准

| 项目 | 内容 |
|---|---|
| 当前实盘配置 | `P3.0%/C6.0% Wing9% DTE45 2x + 动态Config F=20x` |
| 长周期复核（2026-04-12） | `F=20x` 为收益/终值最高：`+38.45% / -9.04% / Sharpe 2.90 / ~$5.47M` |
| 长周期复核（2026-04-12） | `D=10x` 为风险调整后更优：`+33.22% / -6.72% / Sharpe 2.92 / ~$2.95M` |

备注：`当前生产仍使用 F=20x；是否继续维持为“最佳配置”，以 OOS + 黑天鹅抽测结果为准`

## 资金分配

- `QQQ`: `$18,000` 名义资金，基线 `4` 组
- `IWM`: `$6,000` 名义资金，基线 `2` 组
- `GLD`: `$6,000` 名义资金，基线 `2` 组

## DTE 规则

- `DTE 45` 的含义是：**以 45 天为目标，选择最接近 45 的实际到期日**
- 不是只能固定选恰好 `45` 天
- 例如可选只有 `39` 和 `50`，当前代码会优先选 `50`，因为它离 `45` 更近
- 若最接近 `45` 的链流动性不足，程序会继续尝试更长的目标层级：`45 → 52 → 59 → 66`

## 动态组数逻辑

```text
effective_groups = base × (IC_MANUAL_CAPITAL × LEVERAGE / $30K)
cap = base × 20
```

- 当你调整 `IC_MANUAL_CAPITAL` 时，组数会自动联动调整
- 不再依赖账户总资产 API，避免其他仓位污染
- 每日交易日报与 `ic_monitor.py` 会同步展示当前容量档位、预计组数、单批建议与是否触发 `200k/300k` 阈值

## 风控骨架

- HV20开仓阈值：`QQQ/IWM <= 25%`，`GLD <= 18%`（超过即禁止新开仓）
- HV20降杠杆阈值：`HV20 > 22%`（仅在允许开仓时，`max_groups` 减半）
- HV20硬止损阈值：`HV20 >= 39%`
- HV20恢复阈值：`HV20 < 28%`
- 价格止损：穿入翼宽 `50%`
- 资金止损：单标的策略权益相对峰值回撤 `5%`
- 止盈：盈利达到权利金 `50%`
- 冷却期：`5` 天
- 提前平仓：到期前 `2` 个交易日
- 节假日保护：长假前自动跳过新开仓

## 当前生产入口

- `main_ic_us.py`：主交易程序
- `scheduler.py`：自动调度器
- `start_scheduler.sh`：守护启动入口
- `ic_monitor.py`：盘后监控与日报
- `dynamic_composite_backtest.py`：动态组数长周期对比回测
- `oos_validation.py`：样本外、鲁棒性、手续费、GFC/extreme 验证

## 常用命令

```bash
cd /Users/zhangkun/WorkBuddy/程序化/量化程序

# 干跑测试
python3 main_ic_us.py --once --dry-run

# 盘后监控
python3 ic_monitor.py

# 启动调度
bash start_scheduler.sh

# 查看日志
tail -f logs/scheduler_daemon.log

# 长周期动态回测
python3 dynamic_composite_backtest.py

# 样本外/极端年份验证
python3 oos_validation.py
```

## 说明

- 旧港股 / 腾讯 / Wheel 入口均已降级为历史遗留，不再作为生产执行入口
- 生产系统一律以美股多标的 IC 为准
