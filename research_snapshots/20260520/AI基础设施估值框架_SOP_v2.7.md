# AI Infrastructure 估值框架 SOP v2.7

日期：2026-05-20
状态：active / valuation framework
适用：AI 电力、数据中心、电网、能源、设备、连接、冷却、地产/REIT、矿转算力等 AI 基础设施链条候选。

## 定位

v2.7 是 v2.6 的基础设施扩展版。它不是为了给 AI 叙事更高估值，而是为了把 AI CapEx 从半导体和软件扩散到真实资产、订单、负荷、电网、融资和监管回报时，用更合适的框架评估。

适用例子：

| 类型 | 例子 | 估值重点 |
|---|---|---|
| AI 电力 / 公用事业 | `NEE / CEG / VST / XEL / SO / DUK` | rate base、负荷增长、监管回报、利率敏感度 |
| 电气设备 / 电网 | `ETN / GEV / VRT` | backlog、订单、利润率、交付周期 |
| 数据中心 / 新云 / 矿转算力 | `CRWV / IREN / APLD / CORZ` | 客户合同、融资、折旧、稀释、电力成本 |
| 连接 / 光通信 / 存储 | `ANET / COHR / LITE / MU / WDC` | 订单能见度、周期、客户集中度、估值透支 |

## 核心原则

```text
V_base = 传统现金流 / 资产回报 / 监管回报底座
V_AI_infra_option = AI 需求传导到订单、负荷、rate base、backlog、ARR 或合同后的概率加权增量价值
```

AI 基础设施 option 必须来自可验证指标，不能来自“AI 用电会很多”这类叙事。

## 必填输出

每份 v2.7 报告必须输出：

- `V_floor`
- `V_base`
- `V_AI_infra_option`
- `Bear / Base / Bull`
- `current_price_vs_base`
- `current_price_vs_bull`
- `valuation_verdict`
- `position_role`
- `next_system_action`
- `no_trade_reason`

## V_AI_infra_option 建模

必须使用三情景概率加权：

| 情景 | 概率 | 关键变量 | 估值处理 |
|---|---:|---|---|
| Bear Infra | 20%-30% | AI 负荷/订单低于预期，利率或监管压制 | 只给传统底座价值 |
| Base Infra | 40%-60% | AI 需求部分兑现，回报率正常 | 进入 V_base |
| Bull Infra | 15%-30% | 明确合同、负荷、backlog、rate base 或 EPS 增厚兑现 | 形成 V_AI_infra_option |

如果没有订单、客户、负荷、监管回报、backlog、PPA、interconnect queue、capex recovery 或 ARR 等可追踪证据，`V_AI_infra_option = 0`。

## 子行业估值锚

### Regulated Utility / AI Power

适用：`NEE / XEL / SO / DUK` 等。

必须使用：

- DDM / dividend growth。
- EPS growth + justified P/E。
- rate base growth / allowed ROE。
- net debt / EBITDA、利率敏感度。
- 监管审批和资本开支回收概率。

不能只用 FCFF DCF，因为 regulated utility 的价值核心是监管允许回报、资本结构和股息增长。

### Merchant Power / Nuclear / Capacity

适用：`CEG / VST` 等。

必须使用：

- forward power price / capacity market sensitivity。
- nuclear / generation fleet margin。
- PPA / hyperscaler contract visibility。
- commodity-like downside case。

### Equipment / Grid / Cooling

适用：`ETN / GEV / VRT` 等。

必须使用：

- backlog。
- book-to-bill。
- segment margin。
- delivery lead time。
- data center / utility / industrial order split。

### Data Center / Miner-to-Compute

适用：`IREN / APLD / CORZ / CRWV` 等。

必须使用：

- signed customer contracts。
- power cost and availability。
- capex funding source。
- depreciation and maintenance capex。
- dilution / debt maturity。
- customer concentration。

这些标的默认不能主仓化，只能研究、Radar、右尾或定义风险表达。

## NEE 特别规则

NEE 属于：

```text
AI_power_infra_anchor / regulated_utility_plus_AI_load_growth
```

NEE 估值必须回答：

1. Dominion / Virginia 数据中心负荷是否真实进入 rate base、PPA、capex recovery 或 EPS？
2. 监管审批和全股票稀释是否抵消 AI 基础设施 option？
3. 6%-8% EPS growth guidance 是否因 AI load growth 上修，还是只是传统 utility growth？
4. 相对 `CEG / VST / GEV / ETN / BE / XEL / SO / DUK`，NEE 是否是最优风险收益表达？
5. 它是低波动行业锚、候选仓，还是只做主题验证器？

默认结论约束：

- 未完成横向比较前：`Research / AI power infra anchor`。
- 当前价格高于 V_base：不买正股。
- 只有当 `V_base` 提供足够中期年化回报，且 AI infra option 有合同/监管/负荷证据支撑，才可进入 `Watch Position`。

## 仓位规则

| 角色 | 仓位上限 |
|---|---:|
| 行业锚 / 主题验证器 | 0% |
| Watch Position | 1%-2% |
| Defensive Growth Sleeve | 2%-4% |
| Core Infrastructure Holding | 5%-8%，需 Central Risk Board 通过 |

AI Infrastructure 标的不能因为主题正确自动进入主仓。它必须证明风险调整后收益优于现金、V6-A、现有主仓和其他更直接表达。

## 对系统的反哺

v2.7 估值完成后必须更新至少一个系统入口：

- `radar_order_valuation_seed.csv`
- `events_calendar.json`
- `US_Radar_13F系统输入`
- `Radar_样本闭环表`
- `watchlist.json`
- `交易决策日志`

如果没有形成系统输入，只归档，不算完成估值。
