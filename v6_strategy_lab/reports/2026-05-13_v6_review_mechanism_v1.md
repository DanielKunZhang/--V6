# V6 Review Mechanism v1

- Date: `2026-05-13`
- Status: active
- Scope: 定义 V6 的日常 / 周度 / 月度 / 季度复盘机制

## 一句话结论

是的，应该有复盘机制。

但 V6 不该照搬高频或超高频团队那种“每天复盘大量交易细节”的模式。  
V6 的正确节奏是：

- `每日轻检查`
- `每周正式复盘`
- `每月研究复盘`
- `每季度治理复盘`

## 复盘的真正意义

复盘不是为了：

- 给涨跌找借口
- 因为今天亏了就想改规则
- 用情绪替代证据

复盘真正的作用是四件事：

1. `分离结果和过程`
   - 赚钱不一定做对，亏钱也不一定做错。
   - 复盘的第一任务，是判断这次盈亏到底来自 `正确过程` 还是 `偶然结果`。

2. `尽早发现系统漂移`
   - 比如执行没对上、pending orders 堆积、风险暴露偏了、动态池质量下降。
   - 这些问题如果不看，很容易悄悄扩大。

3. `把交易经验沉淀成规则`
   - 不复盘，经验只会停留在感觉里。
   - 复盘之后，经验才可能变成：`保留 / 修正 / 淘汰 / 新假设`。

4. `降低情绪对系统的污染`
   - 当你焦虑时，最容易做的是临时改系统。
   - 固定节奏的复盘，能把“想改”变成“按周期、有证据地评估要不要改”。

## 为什么 V6 不需要高频式复盘

成功的短线团队之所以常做日复盘，是因为：

- 交易频率高
- 单日样本很多
- 执行误差和微观结构影响很大

而 V6 当前是中低频系统，交易没有那么密。

所以：

- `每日` 更像运维检查
- `每周` 才是主要的交易复盘单位
- `每月 / 每季度` 才是策略和治理层复盘单位

## 四层复盘板

## 1. Daily Ops Review

- 频率：每个交易日
- 用时：`5-10` 分钟
- 目的：抓执行和运维错误，不做策略结论

看什么：

- managed state 是否正常
- reconciliation 是否 PASS
- pending orders 是否异常
- 日报 / 早报是否正常生成
- 有无 unmanaged sell / drift / malformed state
- 是否出现超预期滑点、报价异常、OpenD 异常

产出：

- `OK`
- `Investigate`
- `Pause if needed`

一句话理解：

- `Daily review = 看系统有没有坏，不是看自己今天有没有赚。`

## 2. Weekly System Review

- 频率：每周一次
- 用时：`30-45` 分钟
- 目的：判断这一周的收益、回撤、暴露和执行，是否来自 V6 预期中的行为

看什么：

- 本周收益来自哪些持仓 / 因子 / 风险暴露
- 本周回撤是否在预期范围内
- 当前持仓是否仍符合 risk-on / risk-off 逻辑
- 是否出现过度集中、风格漂移、非预期暴露
- 本周有没有规则被破坏
- 有没有明显 missed names，但系统本来不该抓，还是本该抓却没抓到

产出：

- `No change`
- `Need investigation`
- `Need research follow-up`
- `Need risk discussion`

一句话理解：

- `Weekly review = 看这一周系统是不是在按它该有的方式赚钱或亏钱。`

## 3. Monthly Research Review

- 频率：每月一次
- 用时：`60-90` 分钟
- 目的：把复盘结果转成研究队列，而不是直接改生产参数

看什么：

- V6-A 相对 baseline / benchmark 的状态
- V6-B 当前动态池质量
- missed opportunity review
- 哪些 challenger 值得继续
- 哪些假设应终止
- 是否需要补新的 track / universe / filter / governance rule

产出：

- `Keep baseline`
- `Open new challenger`
- `Freeze weak research`
- `Promote candidate to formal review`

一句话理解：

- `Monthly review = 把现象变成研究问题，把研究问题变成候选实验。`

## 4. Quarterly Governance Review

- 频率：每季度一次
- 用时：`2-3` 小时
- 目的：决定主系统是否维持、降权、暂停、升级

看什么：

- Full / OOS / rolling / black swan / drawdown
- turnover / cost / tradability
- live-forward 与历史口径是否一致
- 是否有 challenger 真的优于生产基线
- 是否需要调整 `V6-A core pool`
- allocator 是否需要改变权重边界

产出：

- `Maintain`
- `Promote challenger`
- `De-risk`
- `Pause`

一句话理解：

- `Quarterly review = 决定系统本身是否该变。`

## 当前 V6 的推荐复盘结构

按你现在的系统阶段，最有价值的是：

1. `Daily Ops Review`
   - 继续用 `morning_brief + v6_reporting + reconciliation + preflight`

2. `Weekly V6 Review`
   - 这是接下来最该正式化的主复盘单位

3. `Monthly Research Review`
   - 连接 `V6-A parameter challenger`、`V6-B track research`、`Radar missed names`

4. `Quarterly Governance Review`
   - 现在先保留为治理边界，等样本再多一些再严肃执行

## 当前阶段最该复盘的内容

你现在最不该每天盯的是：

- 今天赚没赚
- 某个朋友又赚了多少
- 某个标的今天是不是比你持仓更强

你现在最该复盘的是：

- `V6 有没有按规则运行`
- `规则运行后的实际摩擦是否可接受`
- `当前持仓和风险暴露是否还是你能睡得着的结构`
- `哪些研究方向真的能提升系统，哪些只是让人兴奋`

## 直接落地建议

从今天开始，V6 复盘机制按下面执行：

1. 每日：只做 `ops check`
2. 每周：做一次 `Weekly V6 Review`
3. 每月：做一次 `Research Review`
4. 每季度：做一次 `Governance Review`

其中最先值得新增的，是：

- `Weekly V6 Review Board`

因为它正好卡在：

- 不会像日复盘那样噪音太大
- 也不会像月复盘那样太慢

它最适合你现在这个频率和阶段。
