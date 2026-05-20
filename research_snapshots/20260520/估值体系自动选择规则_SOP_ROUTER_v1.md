# 估值体系自动选择规则 SOP Router v1

日期：2026-05-20
状态：active / routing rule

## 目的

后续所有 `/估值` 不能默认套同一套模板。必须先判断标的属性，再选择估值体系。选择错误会导致两个问题：

- 用传统 v2.5 低估 AI / 基础设施 option。
- 用 v2.6/v2.7 叙事化高价，破坏安全边际。

## 路由规则

| 标的属性 | 使用框架 | 例子 |
|---|---|---|
| 普通消费、平台、金融、传统制造、非 AI 主线 | SOP v2.5 | PDD、腾讯、泡泡玛特、招商银行、AAPL |
| AI 平台、AI 软件、AI 半导体、AI 核心复利候选 | AI-Core SOP v2.6 | MSFT、GOOGL、AMZN、NVDA、META、ADBE、AVGO、TSM、ASML |
| AI 电力、数据中心、电网、能源、设备、冷却、矿转算力、AI 基础设施扩散 | AI Infrastructure SOP v2.7 | NEE、CEG、VST、GEV、ETN、BE、VRT、IREN、APLD、CORZ、CRWV |
| 银行、保险、券商 | 金融专项框架 + v2.5纪律 | 招商银行、BRK金融部分 |
| 高波动右尾 / 主题票 / 无稳定现金流 | Radar 估值现实检查 + v2.7 风险约束 | AAOI、CRDO、ALAB、IREN、APLD |

## 强制步骤

每次估值前先输出：

```text
VALUATION_FRAMEWORK_SELECTED =
WHY_THIS_FRAMEWORK =
WHY_NOT_OTHER_FRAMEWORKS =
SYSTEM_FEEDBACK_TARGET =
```

`SYSTEM_FEEDBACK_TARGET` 必须是：

- `watchlist.json`
- `radar_order_valuation_seed.csv`
- `events_calendar.json`
- `US_Radar_13F系统输入`
- `交易决策日志`
- `Radar_样本闭环表`
- `Central Risk Board`

没有系统反馈目标的估值，只能算研究草稿，不能算完成。

## NEE 路由

NEE 当前自动选择：

```text
VALUATION_FRAMEWORK_SELECTED = AI Infrastructure SOP v2.7
WHY = AI 电力基础设施 / regulated utility + AI data center load growth / Dominion-Virginia 数据中心负荷
WHY_NOT_v2.5 = v2.5 无法充分建模 AI load growth option
WHY_NOT_v2.6 = NEE 不是 AI 平台或半导体核心复利候选，WACC、监管、rate base 与 utility 估值不同
SYSTEM_FEEDBACK_TARGET = radar_order_valuation_seed.csv + watchlist.json + events_calendar.json
```

## 禁止事项

- 不允许用 v2.6 或 v2.7 给高价买入找理由。
- 不允许把 AI option 当成 V_base。
- 不允许没有横向比较就把主题锚升级为候选仓。
- 不允许估值报告只停留在文档层。
