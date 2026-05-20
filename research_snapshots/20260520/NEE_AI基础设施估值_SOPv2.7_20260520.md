# NEE AI Infrastructure Valuation SOP v2.7

日期：2026-05-20
对象：NextEra Energy, Inc.（NEE）
框架：AI Infrastructure SOP v2.7
结论：Research / AI power infrastructure anchor；当前不买正股，等待更好价格或监管/合同证据。

## 路由

```text
VALUATION_FRAMEWORK_SELECTED = AI_Infrastructure_SOP_v2.7
WHY_THIS_FRAMEWORK = regulated utility + AI data center load growth + Dominion/Virginia exposure
WHY_NOT_v2.5 = v2.5 无法充分处理 AI load growth / rate base / 大客户电力需求 option
WHY_NOT_v2.6 = NEE 不是 AI 平台、软件或半导体核心复利股，WACC、监管回报、利率敏感度不同
SYSTEM_FEEDBACK_TARGET = radar_order_valuation_seed.csv + watchlist.json + events_calendar.json
```

## 关键输入

- 价格参考：`$90.06`，2026-05-19 收盘；盘后 `$89.93`。
- 市值 / EV：约 `$187.8B / $290.2B`；股本约 `2.09B`。
- 2026E adjusted EPS：`$3.92-$4.02`，公司目标高端；2025 adjusted EPS base 为 `$3.71`。
- 公司目标：adjusted EPS `8%+` CAGR 至 2032，并目标 2032-2035 继续 `8%+`。
- 股息：年化约 `$2.49`，股息率约 `2.8%`；公司仍预计 2026 年前约 `10%` 增长，2026 年末至 2028 年约 `6%` 增长。
- 资本结构：总债务约 `$104.4B`，Debt/EBITDA 约 `7.37x`，利率敏感度高。
- Dominion 交易：全股票，D 股东每股获得 `0.8138` 股 NEE；交易预计 12-18 个月完成。
- 合并后公司：超过 `80%` regulated，约 `10M` utility customer accounts，`110GW` generation，combined rate base `$138B`，预期 regulatory capital employed 约 `11%` 年增，large-load pipeline 超过 `130GW`。

## v2.7 估值输出

| 项目 | 估计 |
|---|---:|
| V_floor | `$62-$70` |
| V_base | `$78-$88` |
| V_AI_infra_option | `$6-$12` |
| Risk-adjusted value | `$84-$96` |
| Bull case | `$105-$120` |
| Current price vs base | 约 `102%-115%` |
| Current price vs risk-adjusted | 约 `94%-107%` |
| Current price vs bull | 约 `75%-86%` |
| valuation_verdict | `FAIR_BUT_NEEDS_PULLBACK` |
| position_role | `Research / AI power infra anchor` |
| next_system_action | 加入 Radar P1；跟踪 Dominion 审批、Virginia 数据中心负荷、large-load tariff、rate base / capex recovery |
| no_trade_reason | 当前价格已接近风险调整价值，AI option 尚未由审批、合同和回报率完全确认 |

## 情景

### Bear Infra：`$62-$70`

假设：

- Dominion 交易审批延迟或附带苛刻条件。
- 长端利率上行，utility 估值回到高股息率折价。
- large-load pipeline 无法有效转化为 rate base、PPA 或可回收 capex。

估值锚：

- dividend yield `3.5%-4.0%`。
- 2026E EPS `16x-17.5x`。
- AI infra option 基本归零。

### Base Infra：`$78-$88`

假设：

- NEE 独立业务仍可按 2026E EPS `$3.92-$4.02` 与 8%+ EPS CAGR 跑。
- FPL 和 Energy Resources 的 backlog / data center hub strategy 兑现一部分。
- Dominion 交易尚未完全完成，因此不把 9%+ pro forma EPS growth 全额资本化。

估值锚：

- 2026E EPS `19x-22x`。
- dividend growth DDM 对应约 `$80-$90`。
- 资本结构和利率压制估值上限。

### Bull Infra：`$105-$120`

触发条件：

- Dominion 交易在 12-18 个月内顺利完成。
- Virginia / Carolinas 数据中心负荷明确进入 rate base、large-load tariff、PPA 或 capex recovery。
- 合并后 `9%+` adjusted EPS growth 和 `11%` regulatory capital employed growth 被市场相信。
- 利率环境不继续压制 long-duration utility。

这个情景不能作为当前买入依据，只能作为后续确认后的上修空间。

## NEE 特别问题回答

1. Dominion / Virginia 数据中心负荷是否已经进入 rate base、PPA、capex recovery 或 EPS？
   - 目前是 pipeline 和战略逻辑，尚不是充分兑现。公司给出 large-load pipeline、rate base growth 和 EPS accretion，但仍需监管审批、tariff、合同、资本开支回收细节。

2. 监管审批和全股票稀释是否抵消 AI 基础设施 option？
   - 短期会抵消相当一部分。交易虽预计 accretive，但审批期 12-18 个月，全股票交易、bill credits、监管条件和债务成本都要折价处理。

3. 6%-8% / 8%+ EPS growth 是 AI load growth 上修，还是传统 utility growth？
   - 当前独立 NEE 的 8%+ 仍主要来自 FPL capital investment、Energy Resources backlog、contracted renewables/storage、data center hub strategy。合并后 9%+ 才更明确体现 Dominion / large-load / regulated rate base expansion，但尚未完成。

4. 相对 CEG / VST / GEV / ETN / BE / XEL / SO / DUK 是否最优？
   - 目前不是最强弹性表达。NEE 更像低波动、监管化、规模化的 AI 电力行业锚；CEG/VST 可能弹性更强，GEV/ETN 更像设备卖铲人。NEE 需要横向比较后才可升级为候选仓。

5. 它是低波动行业锚、候选仓，还是主题验证器？
   - 当前是 `AI power infra anchor / theme validator`，仓位上限 `0%`。只有当价格回到 base 以下且审批/合同证据改善，才考虑 `Watch Position 1%-2%`。

## 操作规则

- 当前：不买，Radar P1 研究。
- 观察区：`$82-$88`，只适合继续研究，不构成买点。
- 初始击球区：`$72-$78`，需同时确认交易审批未恶化、利率未继续上行、large-load / capex recovery 证据增强。
- 优先买点：`<$72`，若基本面未恶化，可考虑 Watch Position 级别复核。
- 追高禁区：`>$95` 且没有新审批/合同/EPS 上修证据，不追。

## 系统反哺

- `radar_order_valuation_seed.csv`：新增 NEE，结论 `FAIR_BUT_NEEDS_PULLBACK`。
- `screener/watchlist.json`：新增 NEE 作为 watchlist，不是建仓信号。
- `events_calendar.json`：新增 Dominion / AI power infrastructure 跟踪动作。

## 资料来源

- NextEra Energy Q1 2026 earnings release: https://www.investor.nexteraenergy.com/~/media/Files/N/NEE-IR/reports-and-fillings/quarterly-earnings/2026/Q1%202026/2026-0423%20NEEQ12026News%20Release%20vF.pdf
- NextEra / Dominion transaction announcement: https://newsroom.nexteraenergy.com/2026-05-18-NextEra-Energy-and-Dominion-Energy-to-Combine%2C-Creating-the-Worlds-Largest-Regulated-Electric-Utility-Business-and-North-Americas-Premier-Energy-Infrastructure-Platform-Benefiting-Customers?l=12
- StockAnalysis NEE statistics, 2026-05-19 close: https://stockanalysis.com/stocks/nee/statistics/
