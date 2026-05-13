# H007: V6-A 参数 challenger，能否在不破坏治理纪律的前提下提升基线？

- Status: active
- Created: 2026-05-13
- Cadence: monthly / quarterly

## 假设

在不改变 `V6-A core pool`、不引入 V6-B 动态票池的前提下，`V6-A` 现有参数未必已经是最优基线。

更具体地说：

- 通过有限、受约束的参数搜索，
- 可能找到比当前 `mom60 / top3 / trend100 / market150 / dd10 / rebal5`
- 更适合作为“相对安全年化增强器”的 `V6-A parameter challenger`。

## 背景

在 `V6-B profile attribution` 研究中，发现部分看似来自动态轨道的提升，其实有一部分来自 `same-parameter V6-A base-only` 本身的参数改善。

这意味着：

- `V6-B` 研究不能替代 `V6-A` 自身的参数 challenger；
- `V6-A baseline` 也不应被当成永恒最优，只能被当成当前 anchor。

## 研究边界

- 不允许做无边界参数扩张。
- 不允许因为近 1-2 个月行情而追着调参。
- 只允许围绕现有治理认可的范围做 bounded search。
- 结果必须同时看 `full / OOS / MaxDD / Sharpe`，不能只看年化。

## 通过标准

- Full `ann_ret` 不低于当前 baseline。
- Full `sharpe` 不低于当前 baseline。
- `max_dd` 不明显恶化。
- `oos_sharpe` 不低于当前 baseline，或有明确风险收益补偿。
- 参数邻域结果不能过于脆弱。

## 预期用途

- 若通过，可升级为 `formal V6-A parameter challenger`。
- 若不通过，维持当前 `V6-A baseline` 不动。
