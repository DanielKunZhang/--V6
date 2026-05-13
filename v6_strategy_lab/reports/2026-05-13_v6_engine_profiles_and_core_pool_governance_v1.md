# V6 Engine Profiles And Core Pool Governance v1

- Date: 2026-05-13
- Status: active governance draft
- Purpose: clarify whether `V6-A` is immutable and whether `V6-B` should become a separate strategy.

## 一句话结论

`V6-A` 不是永远冻结的池子，但必须是 `低频、慢变、治理化更新` 的核心池。  
`V6-B` 也不应变成“一主题一策略”的集合，而应是 `动态资源池生成器`；执行层使用统一 V6 skeleton 下的少数 `track-aware profiles`。

## 先回答核心问题

### 1. V6-A 的池子永远不变吗

不是。

但正确理解不是“随市场每月换”，而是：

- `V6-A = 低频维护的核心资源池`
- 它的职责是给 V6 提供一个稳定、可解释、可长期复用的 baseline
- 所以它必须 `慢变`，而不是 `不变`

### 2. 什么情况下 V6-A 可以改

只允许三类原因：

1. `结构性失效`
   - 原核心票不再代表主线核心利润池

2. `长期领导权转移`
   - 出现更高质量、更稳定、更有代表性的核心龙头，且旧龙头的重要性明显下降

3. `治理 / 可交易性 / 风险约束变化`
   - 例如监管、流动性、地缘、会计质量、上市结构等问题让该票不再适合当核心底盘

不允许的理由：

- 最近涨得慢
- 最近没别人弹性大
- 聊天群最近不聊它了
- 某一两个月回测被 challenger 超过

## V6-A 的正确定位

`V6-A` 的意义不是“永远抓住所有最强票”。

它的意义是：

- 提供长期稳定 baseline
- 提供对大市值核心主线的持续暴露
- 成为所有 challenger 的比较基准

所以 `V6-A` 应该像“核心指数委员会”一样维护，而不是像 Radar 一样滚动刷新。

## 建议维护节奏

- `月度`：只复核，不换池
- `季度`：允许提出候选替换名单，但默认不动
- `半年`：才允许正式讨论核心池升级 / 降级
- `特殊事件触发`：重大监管、治理、业务断层或明确领导权转移时可提前处理

## V6-B 的正确定位

`V6-B` 不是第二套平行策略。

它的职责是：

- 发现新的资源池
- 验证这些资源池是否值得进入 V6 体系
- 为未来可能的核心迁移提供候选来源

所以更准确的结构是：

1. `V6-A`
   - 固定核心池
   - 慢变 baseline

2. `V6-B`
   - 动态资源池生成器
   - 快变 research layer

3. `V6 Engine`
   - 统一骨架

4. `Profile Selector`
   - 按 track 选择少数标准化 execution profiles

## 为什么不是“一池一策”

如果每个主题都发明一套策略，V6 会退化成：

- AI-capex 策略
- 电力策略
- 工业自动化策略
- 资源瓶颈策略

这不是系统，是故事堆叠。

正确做法是：

- 资源池可以变
- 但执行层只允许少数标准化 profile

## Track-Aware Profiles 的正式含义

这不等于“V6-B 独立成另一套系统”。

它的含义只是：

- 同一个 V6 engine skeleton
- 对不同 track 使用有限的参数档位

当前建议的四个 profile：

1. `v6a_core_baseline`
2. `core_reaccel_profile`
3. `bottleneck_diffusion_profile`
4. `turnaround_momentum_profile`

它们共享：

- risk-on / risk-off
- top-N 选择
- drawdown brake
- defensive switch
- allocator 审核

它们只在这些地方允许有差异：

- 动量窗口
- rebal 节奏
- drawdown 容忍度
- 暴露上限
- 是否需要额外 regime filter

## 当前执行结论

1. `V6-A` 不冻结，但保持低频维护
2. `V6-B` 继续做，而且值得做
3. `V6-B` 不是为了替换 V6-A，而是为了让 V6 不被单一核心池绑死
4. `V6-B` 不应变成“一主题一策略”，而应变成 `动态池 + 有边界的 profile selector`
5. 当前最重要的下一步，不是继续混池，而是：
   - 先做 `core_reaccel_profile`
   - 再做 `bottleneck_diffusion_profile`
   - 暂不优先继续研究 `blended_tracks`
