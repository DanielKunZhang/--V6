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
- 当前阶段：`SIMULATE_TESTING`
- 当前目标：先完成模拟盘执行闭环，再进入小额真实 pilot 讨论

## 推荐流程

1. 每月在 `hypotheses/` 新增假设。
2. 将可回测假设转成 challenger 配置或脚本。
3. 输出到 `reports/`。
4. 关键指标进入 `scorecards/`。
5. 季度做一次主策略 revalidation。
