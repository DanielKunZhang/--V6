# V6-A Balanced Challenger Cutover SOP v1

- Date: `2026-05-13`
- Earliest decision date: `2026-05-26`
- Scope: decide whether to promote `balanced challenger` into the active `V6-A core baseline` lane after the current live `ATTACK_EQUAL_REPLAY` manual pilot review
- Boundary: this SOP governs `evaluation`, `go/no-go`, and `cutover planning`; any real order placement still requires explicit manual confirmation

## One-Line Rule

`2026-05-26` 不是“默认切换日”，而是 `cutover decision day`。

只有当：

1. 当前 live `ATTACK_EQUAL_REPLAY` pilot 通过；
2. `balanced challenger` 的 fresh replay 和 single-candidate preview 也通过；
3. 迁移 diff 清楚且不会误伤非 V6 仓位；

才允许输出 `GO_CUTOVER`。

否则默认输出 `HOLD_OLD_BASELINE`。

## Why This SOP Exists

当前有两条不同的线：

- 当前 live 执行线：`V6-A ATTACK_EQUAL_REPLAY`
- 下一代 core upgrade 线：`balanced challenger = mom60 top3 trend150 mkt200 dd10 rebal10`

旧 pilot 的执行稳定，不自动等于新 challenger 已可切换。

所以必须把：

1. `旧 live pilot 是否稳定`
2. `新 challenger 是否 ready`
3. `切换会不会误伤账户`

分开检查，再统一决策。

## Allowed Outputs

### `GO_CUTOVER`

可以进入受控切换流程。

### `HOLD_OLD_BASELINE`

旧 live 线继续跑；新 challenger 继续补证据，但不切换。

### `PAUSE_V6`

出现执行层异常或账户边界风险，先暂停任何策略升级讨论，优先处理基础设施。

## Required Evidence Pack

到 `2026-05-26` 当天，必须先收齐以下工件。

### A. 当前 live pilot 证据

- 最新 `V6-A execution quality board`
- 最新 `pilot review dashboard`
- 最新 `reconciliation`
- 最新 `automation preflight / release gate`
- 最新 `managed state` 快照

### B. Balanced challenger 证据

- 最新 `v6a_core_replay` summary / report
- 最新 `balanced challenger` 单候选 `daily / summary / composite` 工件
- 最新 `turnover / cost re-audit`
- 最新 `replay bridge board`

### C. 切换预演证据

- `balanced challenger` 单候选 preview orders
- preview quotes
- preview account snapshot
- preview report
- migration diff：
  - `keep`
  - `sell`
  - `buy`
  - `ownership_transfer_only`

如果缺任何一类关键工件，默认输出 `HOLD_OLD_BASELINE`。

## Phase 1: Validate Current Live Pilot

这一阶段只回答：

`旧 live 执行线是否稳定到足以作为切换基础设施`

### Must Pass

- 没有 unresolved reconciliation failure
- 没有 unmanaged sell attempt
- managed state 可读且 strategy 名称正确
- pending orders 为 `0`，或剩余原因完全可解释
- drift 可解释且受控
- kill switch / gate 的阻断与放行行为符合预期

### If Fail

- 若失败属于“轻度、可恢复、非账户边界风险”：
  - 输出 `HOLD_OLD_BASELINE`
- 若失败属于“账户边界、误卖、state 损坏、reconciliation 持续失败”：
  - 输出 `PAUSE_V6`

## Phase 2: Validate Balanced Challenger Quality

这一阶段只回答：

`新 challenger 是否在 production-path 证据下仍然成立`

### Must Pass

- latest replay bridge 仍显示 challenger 优于 baseline
- cost re-audit 仍为 `PASS`
- replay / summary 满足当前 release-style 数值口径
- `rolling_3y_worst_ann >= 0`
- latest replay row 满足 freshness 要求

### Freshness Rule

以当前 release-gate 规则为下限。

实际执行口径：

- 最优：同日或前一交易日
- 可接受：满足现行 `max_signal_age_days`
- 超过 freshness 规则：直接 `HOLD_OLD_BASELINE`

### If Fail

- 若 challenger 指标退化，但旧 live 正常：
  - 输出 `HOLD_OLD_BASELINE`
- 不因此影响旧 live 线继续运行

## Phase 3: Validate Single-Candidate Preview Path

这一阶段只回答：

`balanced challenger 能不能被安全接进执行链路`

### Must Pass

- preview 命令成功生成
- quotes / account / orders 都可读
- order sizing 合理，无越权或异常大单
- 不尝试卖出非 V6 管理仓位
- 预览出来的目标仓位逻辑清楚，可被人工解释

### Preview Interpretation Rules

- 若无可执行订单，且当前仓位已接近 target：
  - 这是合法稳态，不算失败
- 若 preview 尝试 round-trip 同一只票：
  - 需要先解释和消除，再继续
- 若 preview 产生 unmanaged sell 风险：
  - 直接 `PAUSE_V6`

## Phase 4: Decision Matrix

```text
旧 live pilot FAIL，且涉及账户边界/状态损坏
-> PAUSE_V6

旧 live pilot FAIL，但只是普通执行瑕疵
-> HOLD_OLD_BASELINE

旧 live pilot PASS，但 challenger fresh replay / preview 不完整
-> HOLD_OLD_BASELINE

旧 live pilot PASS，challenger replay PASS，但 preview FAIL
-> HOLD_OLD_BASELINE

旧 live pilot PASS，challenger replay PASS，preview PASS
-> GO_CUTOVER
```

## Phase 5: Controlled Cutover Checklist

只有在输出 `GO_CUTOVER` 后，才允许进入这里。

### Step 1: Freeze

- 冻结旧 `ATTACK_EQUAL_REPLAY` 的临时人工调整
- 备份旧 managed state
- 保存切换前账户快照

### Step 2: Build Migration Diff

把旧 live 持仓和新 challenger target 分成四类：

- `keep`：旧有且新也要
- `sell`：旧有但新不要
- `buy`：新要但旧没有
- `ownership_transfer_only`：旧仓继续持有，但仅管理归属从旧策略切到新策略

### Step 3: Ownership Transfer Rule

如果某只票：

- 旧仓有
- 新仓也要

则优先做 `ownership_transfer_only`。

不允许为了切换策略而先卖出再买回同一只票，除非有明确原因。

### Step 4: Execute Migration

迁移顺序：

1. 先处理 `ownership_transfer_only`
2. 再处理必须卖出的 `sell`
3. 最后处理新增 `buy`

### Step 5: Post-Execution Reconciliation

执行后必须立刻检查：

- managed state 是否已切换到新策略名
- reconciliation 是否 PASS
- 实际仓位与新 target 是否匹配
- 有没有残留 pending orders

若这里失败，进入 `rollback / stabilize`，而不是继续扩动作。

## Phase 6: First-Week After Cutover

切换后第一周，只验证执行质量，不评价短期盈亏。

### Daily Checks

- managed state 是否只记录新策略应管理的仓位
- reconciliation 是否持续 PASS
- pending orders 是否清零
- drift 是否可解释
- 是否出现 unmanaged sell / malformed state / stale preview

### First-Week Restrictions

- 不加资金
- 不改参数
- 不同时引入 V6-B
- 不因 1-2 天涨跌回滚

## Rollback Triggers

切换后若出现以下任一情况，停止扩容讨论，优先稳定系统：

- reconciliation 持续失败
- managed state 损坏
- strategy mismatch
- unmanaged sell risk
- migration 后 target 与实际偏差无法解释

## Day-Of Invocation

到 `2026-05-26` 当天，用户只需要发一句：

`执行 V6-A balanced challenger cutover SOP`

一页执行卡：

- `v6_strategy_lab/reports/2026-05-14_v6a_balanced_cutover_decision_day_card_v1.md`

届时执行顺序固定为：

1. 收集 evidence pack
2. 输出三选一 verdict：
   - `GO_CUTOVER`
   - `HOLD_OLD_BASELINE`
   - `PAUSE_V6`
3. 若为 `GO_CUTOVER`，继续生成 migration diff 与执行建议
4. 在真实下单前，再单独要求最终人工确认

## Practical Default

默认立场不是“想切就切”，而是：

`先证明旧线稳定，再证明新线 ready，再做受控迁移。`

这比“2026-05-26 直接一把切过去”更慢半步，但风险显著更低。
