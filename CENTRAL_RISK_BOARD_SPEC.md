# Central Risk Board Spec v1

- Created: `2026-05-14`
- Status: active_spec
- Scope: 定义整个 AI 个人投资公司的中央风险看板，而不是只看 V6

## One-Line Rule

`Weekly V6 Review Board` 已经有风险检查，但它还不是 `Central Risk Board`。

原因很简单：

- 它偏 `V6` 视角
- 它偏 `研究/执行复盘`
- 它还没有统一覆盖 `主仓 + V6 + Radar Overlay + 独立实验线`

所以中央风控层必须单独存在。

## Why This Layer Exists

你的目标不是只把一个策略跑好，而是经营一个小型投资公司。

那就必须有一个独立问题始终被回答：

`今天整个资本池到底暴露在什么风险上？`

不是：

- V6 今天赚没赚
- 某个票今天涨没涨
- 某个研究方向最近热不热

而是：

- 总账户是否过度集中
- 是否无意中在多个 sleeve 里押了同一主题
- 当前回撤是否还在睡得着的范围内
- 哪条线在贡献收益，哪条线在偷偷放大尾部风险

## Scope

中央风险看板覆盖：

- `价值投资主仓`
- `V6`
- `Radar-Sourced Overlay`
- `独立实验线`
  - 当前包括 `Micro Futures Lab`
  - 未来新增实验线也必须纳入

## Cadence

### Daily Light Check

- 只看是否出现异常
- 不做策略结论

### Weekly Formal Board

- 这是主风险看板
- 固定回答“这周整个资本池的风险有没有失真”

### Monthly Risk Review

- 看主题拥挤、相关性变化、预算边界是否需要调整

### Quarterly Governance Review

- 正式调整风险预算、单主题上限、实验仓上限

## Board Structure

### 1. Firm-Level Snapshot

必须展示：

- 总资产净值
- 现金 / 可动用现金
- 本周 / 本月 / 年初至今收益
- 当前回撤
- 年内最大回撤
- 前 `5` 大持仓占比
- 前 `3` 大主题占比

一句话目标：

`先知道整个公司是不是在不知不觉里变成单主题基金。`

### 2. Sleeve-Level Risk

每条 sleeve 必须单独列：

- 当前市值
- 预算占比
- 实际占比
- 本周收益
- 年初至今收益
- 当前回撤
- 是否触发黄灯/红灯

当前最少四类：

- `Value Main Book`
- `V6`
- `Radar Overlay`
- `Research / Experimental Sleeves`

### 3. Concentration Risk

必须展示：

- 单标的最大暴露
- 单主题最大暴露
- 单国家/市场暴露
- 单风格暴露
  - 例如：AI 成长、Mega Tech、半导体、港股消费

重点不是数学上绝对精确，而是：

`你要一眼看到“我是不是以为自己分散了，其实只是换名字重仓同一个东西”。`

### 4. Overlap Risk

必须检查：

- 主仓与 V6 是否重叠
- V6 与 Overlay 是否重叠
- 不同 sleeve 是否因同一主题高度相关

这层特别关键，因为你当前的真实风险不是“持仓太多”，而是：

`多个系统可能在不同名义下押同一条主线。`

### 5. Event Risk

至少看未来 `14` 天：

- 财报集中度
- 重要政策/发布会/行业事件
- 是否有多个重仓同时暴露在同一事件窗口

### 6. Risk Guardrails

中央风险看板必须输出三色状态：

- `GREEN`
- `YELLOW`
- `RED`

#### GREEN

- 当前风险在预算内
- 不需要动作

#### YELLOW

- 集中度上升
- 回撤偏大
- 某条 sleeve 失效风险上升
- 需要讨论，但不自动减仓

#### RED

- 超出单标的/单主题边界
- 未解释的回撤或异常
- 实验线风险外溢到主系统
- 必须采取动作

## Minimum v1 Metrics

第一版先不要过度复杂。

最小可用指标：

- 总资产
- 现金占比
- 主仓 / V6 / Overlay / 实验线 市值和占比
- 前 `10` 大持仓
- 前 `5` 大主题
- 当前回撤
- 各 sleeve 当前回撤
- 主仓与 V6 的重叠名单
- `14` 天事件清单

## What Current Weekly Review Already Covers

现有周复盘已经部分覆盖：

- V6 concentration
- V6 execution drift
- Missing opportunity
- Challenger / research backlog

但还缺：

- 全账户视角
- 跨 sleeve overlap
- 主仓主题浓度
- 主仓 + V6 + Overlay 联合风险

所以结论是：

`现有周报是 Central Risk Board 的输入，不是替代品。`

## Implementation Order

### v1

- 先做手工/半自动版本
- 直接读取：
  - `26年阶段性组合策略计划.html`
  - `morning_brief`
  - `V6 managed state`
  - `events_calendar.json`

### v2

- 增加主题分类映射
- 自动生成 overlap / theme concentration

### v3

- 增加历史序列
- 生成风险时间轴
- 让风控从“快照”升级成“趋势”

## Hard Principle

中央风控层的目的不是让你永远不冒险。

它的目的，是让你：

- 明确知道自己在冒什么险
- 明确知道哪些风险是主动承担
- 明确知道哪些风险是系统失控造成的
