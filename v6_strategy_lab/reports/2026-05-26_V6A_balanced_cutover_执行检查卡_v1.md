# 2026-05-26 V6-A Balanced Cutover 执行检查卡 v1

- 创建日期：`2026-05-14`
- 使用日期：`2026-05-26`
- 适用范围：判断是否把 V6-A 当前 live `ATTACK_EQUAL_REPLAY` 切换为 `balanced challenger`
- 核心边界：这张卡只做 `go / hold / pause` 决策；不自动下单
- 关联文件：
  - `v6_strategy_lab/reports/2026-05-13_v6a_balanced_challenger_cutover_sop_v1.md`
  - `v6_strategy_lab/reports/2026-05-14_v6a_balanced_cutover_decision_day_card_v1.md`
  - `v6_strategy_lab/reports/2026-05-14_v6a_balanced_cutover_gate_status_v1.md`

## 一句话规则

`2026-05-26` 是 `cutover decision day`，不是默认切换日。

默认结论是 `HOLD_OLD_BASELINE`。只有旧 live pilot、balanced challenger、preview / migration diff 三层证据同时通过，才允许输出 `GO_CUTOVER`。

## 当天用户只需要发这句话

```text
执行 V6-A balanced challenger cutover SOP
```

## 当天允许的唯一三种结论

| 结论 | 含义 | 后续动作 |
| --- | --- | --- |
| `GO_CUTOVER` | 可以进入受控切换流程 | 生成迁移建议；真实下单前仍需用户再次确认 |
| `HOLD_OLD_BASELINE` | 当前旧 V6-A 继续跑，新 challenger 继续补证据 | 不切换、不扩容、不改变真实账户 |
| `PAUSE_V6` | 发现账户边界、状态、reconciliation 或误卖风险 | 暂停 V6 升级讨论，先修基础设施 |

不允许输出“倾向切换”“可以考虑”“小切一下”这类模糊结论。

## 执行前检查

开始前先确认：

- Futu OpenD 已打开。
- 当前时间最好在美股 RTH 前后，至少能拉到行情 / 账户快照。
- `git status` 已确认没有影响 V6 执行链路的未解释改动。
- 当天只做 `$5,000` 级别 V6-A pilot / cutover 决策，不讨论扩容。
- `kill switch` 默认保持 ON；即使输出 `GO_CUTOVER`，真实执行前也需要单独确认。

## 固定命令顺序

以下命令按顺序执行。当天 tag 建议统一使用 `20260526_cutover_review`。

### 1. 生成旧 live pilot 复盘证据

```bash
cd /Users/zhangkun/WorkBuddy/程序化/量化程序
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6a_pilot_review_dashboard.py --tag 20260526_cutover_review
```

必须读取输出里的：

- `review_decision`
- `managed unrealized P/L`
- `pending orders`
- `target vs actual`
- `reconciliation` 状态

若出现 unresolved reconciliation failure、managed state 损坏、pending orders 无法解释，进入 `PAUSE_V6` 或 `HOLD_OLD_BASELINE`。

### 2. 跑自动化 preflight gate

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6_automation_preflight_gate.py --tag 20260526_cutover_review
```

这里的重点不是打开自动交易，而是确认：

- kill switch 是否按预期阻断。
- managed state 是否可读。
- pending orders 是否为 0 或可解释。
- OpenD / quote / trade / account 链路是否正常。
- release gate freshness 是否仍可用。

如果 preflight 链路本身失真，当天不能 cutover。

### 3. 刷新 balanced challenger replay

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6a_core_deterministic_replay.py \
  --config v6_strategy_lab/configs/v6a_core_replay_bridge_v1.json \
  --tag 20260526_cutover_review
```

必须确认：

- `balanced challenger` 仍优于 baseline。
- `rolling_3y_worst_ann >= 0`。
- `latest_date / signal_date` 满足 freshness 要求。
- 指标没有明显退化到低于当前 release gate 口径。

如果 replay 不 fresh，默认 `HOLD_OLD_BASELINE`。

### 4. 重新生成 migration diff

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6a_cutover_migration_diff.py \
  --tag 20260526_cutover_review
```

必须确认四类清楚：

- `ownership_transfer_only`
- `ownership_transfer + incremental buy`
- `buy only`
- `sell only`

禁止出现：

- 卖出非 V6 managed state 管理的仓位。
- 为切换策略而先卖后买同一只票。
- 无法解释的异常大单。
- target 与实际账户不可对齐。

### 5. 生成 weekly review / backlog 快照

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 v6_weekly_review_board.py --tag 20260526_cutover_review
```

作用：

- 把当天 pilot、preflight、challenger、backlog 证据拉到同一张 review board。
- 如果 weekly board 的结论仍是 `Investigate / Continue manual pilot`，默认不切。

### 6. 刷新中央风控和每日驾驶舱

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 central_risk_board.py --cadence weekly --tag 20260526_cutover_review
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 governance_reporting_runner.py --scope daily --tag 20260526_cutover_review
```

作用：

- 确认总账户集中度没有新增红线。
- 确认 V6 仍只是小额 pilot，不因为 cutover 变成扩容。
- 把最终状态同步到 `AI个人投资公司_每日驾驶舱.html`。

## 判定矩阵

| 条件 | 结论 |
| --- | --- |
| 旧 live pilot 有账户边界风险、managed state 损坏、reconciliation 持续失败 | `PAUSE_V6` |
| 旧 live pilot 有普通执行瑕疵，但不涉及账户边界 | `HOLD_OLD_BASELINE` |
| 旧 live pilot 通过，但 challenger replay 不 fresh 或指标退化 | `HOLD_OLD_BASELINE` |
| 旧 live pilot 通过，challenger replay 通过，但 preview / migration diff 不清楚 | `HOLD_OLD_BASELINE` |
| 旧 live pilot 通过，challenger replay 通过，preview / migration diff 清楚，且无误卖风险 | `GO_CUTOVER` |

## 如果输出 GO_CUTOVER

仍然不能自动下单。必须先给出：

- `ownership transfer` 清单
- `sell list`
- `buy list`
- 预计订单价值
- 是否存在非 V6 仓位重叠
- 最终确认短语

真实执行前，用户必须单独确认：

```text
GO_BALANCED_CUTOVER_EXECUTE
```

没有这句话，不能触发真实订单。

## 如果输出 HOLD_OLD_BASELINE

当天动作：

- 当前 `ATTACK_EQUAL_REPLAY` 继续保持。
- `balanced challenger` 继续作为 research winner / production candidate。
- 不做迁移，不扩容，不改参数。
- 把缺失证据写进 V6 Research Backlog。

## 如果输出 PAUSE_V6

当天动作：

- 暂停任何 cutover / 扩容讨论。
- 先修 managed state、reconciliation、OpenD、release gate 或账户边界问题。
- 修完后重新跑 pilot review 和 preflight。

## 当天最终输出格式

执行完后必须按这个格式给用户：

```text
Verdict:
Why:
Critical Evidence:
Blocked / Missing:
Today Next Step:
Need User Confirmation:
```

## 当前预设立场

我们希望 V6 是“相对安全地拉高年化收益”的系统，不是为了追求更高回测而牺牲执行安全。

所以 `balanced challenger` 即使更强，也必须先通过 `pilot 稳定性 -> fresh replay -> preview / migration diff -> 用户确认` 四层门。
