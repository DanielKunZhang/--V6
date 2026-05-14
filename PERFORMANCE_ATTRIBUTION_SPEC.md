# Performance Attribution Spec v1

- Created: `2026-05-14`
- Status: active_spec
- Scope: 定义 AI 个人投资公司未来的绩效归因框架

## One-Line Rule

归因不是解释涨跌，而是回答：

`这次收益 / 回撤，到底来自哪条线、哪个主题、哪个决策、还是哪次执行误差？`

## Why This Matters

没有归因时，复盘会退化成三种坏习惯：

- 赚钱就以为系统正确
- 亏钱就怀疑整个系统
- 看到别人涨得更快就想临时改方向

归因层的意义，是把情绪拆成证据。

## Four Attribution Layers

### 1. Account-Level Attribution

回答：

- 总账户 YTD 收益来自主仓、V6、Overlay、实验线各多少
- 哪条线在拖累
- 哪条线在真实增厚

### 2. Sleeve-Level Attribution

回答：

- 在某条 sleeve 内，哪几个标的或哪种暴露在贡献收益
- 回撤主要由什么导致
- 是策略逻辑本身、还是仓位分配失衡

### 3. Theme-Level Attribution

回答：

- AI、港股消费、红利、半导体、软件等主题分别贡献多少
- 是否存在“看起来很多系统，实际上都押同一主题”的问题

### 4. Execution-Level Attribution

回答：

- 理论收益和实际收益差多少
- 是滑点、未成交、rounding、时段限制，还是账户边界导致

## Minimum v1 Output

第一版归因报告最少包含：

- 总账户收益拆分
- 主仓 / V6 / Overlay / 实验线 收益拆分
- 前 `5` 大贡献标的
- 前 `5` 大拖累标的
- 前 `3` 大主题净贡献
- V6 理论 vs 实际执行偏差

## Cadence

### Weekly

- 看 sleeve-level 和 execution-level
- 作为正式周复盘的一部分

### Monthly

- 增加 theme-level 和 account-level
- 作为 Monthly Research Review 输入

### Quarterly

- 看哪条线真正值得保留、扩容、降级、暂停

## Success Standard

归因系统成熟后，应该能稳定回答：

1. 为什么这段时间总账户原地踏步
2. 是市场没给钱，还是系统错过了窗口
3. 是主仓拖累，还是 V6 没贡献，还是 Overlay 纯亏权利金
4. 该修的是研究、仓位、执行，还是根本不该修

## Hard Boundary

归因不能直接自动触发改策略。

它只能做两件事：

- 暴露问题
- 推动研究和治理讨论

不能做：

- 因为一周归因不好就自动调参
- 因为某条线贡献大就立刻无上限加预算

## First Implementation Order

### v1

- 手工 / 半自动
- 先做账户层 + sleeve 层 + V6 执行偏差

### v2

- 加入主题映射
- 自动输出主题净贡献

### v3

- 做成历史序列
- 开始看 rolling attribution

## Final Goal

最终不是为了生成一份好看的报告。

而是为了让你以后看到账户停滞、回撤、或别人暴利时，第一反应不是情绪，而是：

`先看归因。`
