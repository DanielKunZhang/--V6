# V6-A Balanced Cutover Gate Status v1

- Date: `2026-05-14`
- Scope: summarize the refreshed `balanced challenger` cutover evidence after the stale-cache blocker was removed
- Boundary: this is a `technical readiness` update, not the final `2026-05-26` cutover verdict

## One-Line Read

`Balanced challenger` 已经通过当前技术性 cutover gate。

这意味着：

- 工程接线基本完成
- fresh replay / preview / migration diff 三件套都已可用
- 但正式替换当前 live `ATTACK_EQUAL_REPLAY` 仍要等 `2026-05-26` 的治理决策

## What Changed Today

### 1. Freshness blocker was resolved

- 问题本质不是 challenger 回测逻辑坏了，而是本地 `price_cache` 旧到 `2026-05-05`
- 刷新核心缓存后，replay 现在能稳定走到 `2026-05-12`
- 这已经足够通过当前 `max_signal_age_days=5` 的 fresh gate

### 2. Preview path was re-run successfully

- 新 preview 工件：
  - `attack_live_order_preview_report_20260514_balanced_cutover_preview_v3.md`
- 结果：
  - `quotes/account/orders` 全部成功
  - 无 warnings
  - 当前目标持仓为 `AMZN / AVGO / GOOGL`

当前增量 buy 为：

- `US.AMZN +2`
- `US.AVGO +1`
- `US.GOOGL +2`

### 3. Release gate passed

- 工件：`backtest_results/attack_engine_release_gate/attack_engine_release_gate_20260514_balanced_cutover_gate_v1.md`
- 关键读数：
  - `full_ann_ret +33.97%`
  - `oos_ann_ret +44.18%`
  - `full_max_dd -22.34%`
  - `oos_sharpe 1.30`
  - `rolling_3y_worst_ann +0.78%`
  - `signal_date 2026-05-12`
  - `asof 2026-05-14`
  - `signal age 2 days`

## Migration Diff Read

当前 cutover 不是“大换仓”，而是“以旧 sleeve 为底做受控迁移”：

- `AMZN 4 -> 6`
- `AVGO 2 -> 3`
- `GOOGL 2 -> 4`
- `BIL 6 -> 0`
- `GLD 1 -> 0`

这说明当前迁移更像：

- transfer 旧 V6 已持有的重叠部分
- 对保留标的补足目标仓位
- 卖出旧策略已不再需要的防守仓位

## Practical Decision

今天可以下的结论不是 `GO_CUTOVER`，而是：

`TECHNICALLY_READY_FOR_2026_05_26_DECISION`

也就是：

- 技术证据够了
- 工程路径通了
- 当前不需要再怀疑“是不是 balanced challenger 还接不进生产链路”
- 现在该做的是继续把 live ATTACK pilot 跑到 `2026-05-26`

## Next Step

到 `2026-05-26` 当天，按既定 SOP 汇总：

1. 当前 live `ATTACK_EQUAL_REPLAY` 两周 pilot 证据
2. `balanced challenger` 的 fresh replay / preview / migration diff
3. 最终输出 `GO_CUTOVER / HOLD_OLD_BASELINE / PAUSE_V6`
