# V6-A Balanced Cutover Decision-Day Card v1

- Created: `2026-05-14`
- Use date: `2026-05-26`
- Scope: one-page operator card for the `balanced challenger` cutover decision
- Boundary: this card decides `whether to cut over`, not `auto-place orders`

## Trigger

到 `2026-05-26` 当天，你只需要发一句：

`执行 V6-A balanced challenger cutover SOP`

## Allowed Verdicts

- `GO_CUTOVER`
- `HOLD_OLD_BASELINE`
- `PAUSE_V6`

除这三种外，不允许输出第四种模糊结论。

## Day-Of Workflow

1. 先收 evidence pack。
2. 先判旧 live `ATTACK_EQUAL_REPLAY` pilot 是否稳定。
3. 再判 `balanced challenger` 是否仍然 fresh 且通过 gate。
4. 再判 preview / migration diff 是否清楚且无误卖风险。
5. 最后只输出一个 verdict。
6. 若 verdict=`GO_CUTOVER`，只继续生成 cutover 执行建议；真实下单前仍需你再次确认。

## Evidence Pack Must-Have

### A. 当前 live pilot

- 最新 `execution quality board`
- 最新 `pilot review dashboard`
- 最新 `reconciliation`
- 最新 `managed state` 快照
- 最新 `preflight / release gate`

### B. Balanced challenger

- 最新 `v6a_core_replay` `daily / summary / composite`
- 最新 `turnover / cost re-audit`
- 最新 `replay bridge board`
- 最新 `balanced cutover gate status`

### C. 切换预演

- 最新 preview `orders / quotes / account / report`
- 最新 `migration diff`

缺任何关键工件，默认 `HOLD_OLD_BASELINE`。

## Verdict Rules

### Output `PAUSE_V6` if

- `managed state` 损坏或 strategy mismatch
- unresolved reconciliation failure
- unmanaged sell risk
- preview / migration 显示可能误伤非 V6 仓位
- runner / report / gate 链路本身失真，已经无法信任

### Output `HOLD_OLD_BASELINE` if

- 旧 live pilot 仍能跑，但执行质量不够干净
- challenger 证据不 fresh
- challenger replay / gate / preview 任一缺失
- migration diff 还不够清楚

### Output `GO_CUTOVER` only if

- 旧 live pilot `PASS`
- challenger 最新 replay / gate `PASS`
- preview `quotes/account/orders` 干净
- migration diff 清楚、可解释、无误卖边界风险

## Output Format

当天执行后，结论必须按这个结构给出：

1. `Verdict`
2. `Why`
3. `Critical evidence`
4. `Today next step`

如果是 `GO_CUTOVER`，还必须额外给出：

1. `ownership transfer`
2. `sell list`
3. `buy list`
4. `final confirm phrase`

## Execution Boundary

- `GO_CUTOVER` 不等于当场自动交易
- 真实执行前，仍需单独确认：`GO_BALANCED_CUTOVER_EXECUTE`
- 若当天只适合完成 verdict，不适合交易时段内执行，允许先决策、后执行

## Practical Default

默认偏向不是“能切就切”，而是：

`先证明旧线稳定，再证明新线 ready，再做受控迁移。`
