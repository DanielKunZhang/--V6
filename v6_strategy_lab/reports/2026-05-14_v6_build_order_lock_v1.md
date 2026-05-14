# V6 Build Order Lock v1

- Date: `2026-05-14`
- Scope: lock the practical build order for the next V6 phase so execution, overlay, and research do not compete for the same decision slot

## One-Line Decision

接下来 V6 的正式构建顺序锁定为：

1. `V6-A balanced challenger cutover evidence + 2026-05-26 decision day`
2. `Radar-Sourced Overlay` 真实小样本实验
3. `V6-B dynamic universe engine` 的 synthetic historical / point-in-time research

## Why This Order

### 1. V6-A first

- 这是最近端、最接近生产的收益增强路径。
- 它已经有：
  - standalone challenger evidence
  - turnover / cost re-audit
  - replay bridge
  - live preview / release gate wiring
- 它缺的不是研究逻辑，而是 `2026-05-26` 的正式治理决策。

### 2. Overlay second

- 它是争取右尾收益最快的实验仓。
- 但它不应污染 V6，也不应在样本不足时承担“生活费系统”的职责。
- 正确定位是：
  - `Radar` 提供候选
  - `Overlay` 负责小额、可全亏的高弹性表达
  - 先积累 `20-30` 笔真实样本，再讨论是否扩大权重

### 3. V6-B third

- V6-B 战略上重要，但当前仍是研究引擎，不是 production sleeve。
- 它要解决的是：
  - point-in-time universe 生成
  - synthetic historical 验证
  - live-forward 对照
  - 与 V6-A / Allocator 的治理边界
- 在这些没有完成前，V6-B 不能抢占 V6-A 的生产优先级。

## What Can Run In Parallel

- `V6-A` 主线继续跑到 `2026-05-26`，不动当前 live ATTACK pilot。
- `Overlay` 可以继续做小额手动真实样本，不等待 V6-A cutover。
- `V6-B` 可以继续做研究和工件建设，但不得申请实盘权重。

## Hard Rules

- 不允许因为 `Overlay` 某次大赚，就跳过样本门槛。
- 不允许因为 `V6-B` 概念更大，就提前绕过 point-in-time / OOS / gate。
- 不允许把 `V6-A live pilot review` 和 `balanced challenger cutover decision` 混成同一步自动替换。

## Current Practical Read

今天最该做的不是再开新研究坑，而是把三条线的边界维持清楚：

- `V6-A` 负责更稳地抬升资本池年化
- `Overlay` 负责追求小额右尾
- `V6-B` 负责保证未来 V6 不只吃老资源池
