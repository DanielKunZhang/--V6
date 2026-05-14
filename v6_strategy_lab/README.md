# V6 Strategy Lab

V6 Strategy Lab 是 V6 的研究与治理层，不是执行层。

## 当前职责

- 记录每月策略假设
- 维护 challenger 策略
- 生成月度/季度复盘报告
- 维护 V6-A 的升级、降权、暂停规则

## 不负责

- 不直接提交订单
- 不直接修改 V6-A 当前模拟盘执行
- 不绕过 release gate

## 当前主线

- 主策略：`V6-A ATTACK_EQUAL_REPLAY`
- 当前阶段：`REAL_MANUAL_PILOT_ACTIVE`
- 当前目标：先把 `$5,000` real manual pilot 的执行质量证据做满，再进入自动化层级与资金扩容讨论；并同步完善 V6-B 动态 universe 与 Allocator 治理层
- 并行升级线：`V6-A core replay bridge` 已建立，用于 `v6a_core_baseline` 与 `balanced challenger` 的 runner-compatible parity 验证；该桥接层不改动当前 live ATTACK pilot

## 推荐流程

1. 每月在 `hypotheses/` 新增假设。
2. 将可回测假设转成 challenger 配置或脚本。
3. 输出到 `reports/`。
4. 关键指标进入 `scorecards/`。
5. 季度做一次主策略 revalidation。

## 周度运行补充

当前周度治理建议增加这一条顺序：

1. 先运行 `v6b_missing_opportunity_review.py`
2. 再运行 `v6_weekly_review_board.py`

原因：

- `Missing Opportunity Review` 负责找本周主题内强票是否漏出当前 Radar seed
- `Weekly V6 Review Board` 负责把这些漏网、覆盖缺口和现有 challenger 一起汇总成正式 backlog
- `v6b_candidate_registry_v1.json` 负责承接 `active_research` 之外的 `watch_add_candidate / observe_only / theme_watch`

当前边界：

- `Missing Opportunity Review` 是 review/watch 工件，不是自动入池
- 真正把名字写进 `point-in-time universe` 仍需人工确认
- 周度人工 triage 参考 `reports/2026-05-14_v6b_radar_weekly_triage_sop_v1.md`
