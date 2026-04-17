# 富途境外投资个税计算脚本 v1

这个目录用于把富途标准 PDF 月结单整理成中国税务居民境外投资个税申报参考数据，主要服务于个人所得税 APP 的“境外收入申报”。

## v1 范围

- 读取富途月结单 PDF：`2025-01对账单.pdf` 至 `2025-12对账单.pdf`
- 统计当年已实现股票/ETF/ADR 交易盈亏
- 剔除未平仓浮盈浮亏、入金出金、融资利息、基金申赎现金流
- 单独统计现金股息与境外预扣税
- 输出个税 APP 参考汇总、逐笔交易底稿、股息底稿、复核事项

## 核心规则

- 仅统计纳税年度 `1.1-12.31` 已实现盈亏
- 同年度已实现盈利和亏损互抵，年度净亏损应纳税额为 0
- 资本亏损不结转以后年度
- 交易成本和卖出税费进入税前抵扣口径
- 股息红利按 20% 单独计算，境外已预扣税按限额抵免

## 首次运行

在当前目录执行：

```bash
python3 main.py --pdf-dir .. --year 2025 --out-dir outputs/2025
```

如果你已经把更早年度月结单也放进同一目录，建议直接启用自动推导：

```bash
python3 main.py --pdf-dir .. --year 2025 --out-dir outputs/2025 --auto-derive-opening-lots
```

这样脚本会：

- 自动读取 `2025` 之前的 PDF 月结单
- 用历史买卖记录 FIFO 推导 `2025-01-01` 时点的剩余持仓 lot
- 把推导结果写到 `outputs/2025/derived_opening_lots.csv`
- 再把这些 lot 作为 `2025` 计税的期初成本

如果某些仓位在历史月结单里仍然找不到最初建仓，脚本会继续在 `warnings.csv` 提醒你补更早年度或手工填表。

如果输出提示“结果不完整”，先打开：

- `outputs/2025/opening_lots_template.csv`
- `outputs/2025/warnings.csv`

把 2025 年初已经持有、但在 2025 年卖出的股票历史成本填入：

- `config/opening_lots_2025.csv`

然后重跑。

## 输出文件

- `outputs/2025/cn_overseas_tax_report_2025.xlsx`：总表，最适合人工阅读和申报前复核
- `outputs/2025/tax_app_reference.csv`：按“所得类型 × 国家/地区”汇总，供个税 APP 填报参考
- `outputs/2025/realized_capital_gains.csv`：已实现交易底稿
- `outputs/2025/dividends.csv`：股息与预扣税底稿
- `outputs/2025/derived_opening_lots.csv`：由历史月结单自动推导出的 2025 期初持仓 lot
- `outputs/2025/opening_lots_used.csv`：本次计算实际使用的期初 lot（自动推导 + 手工覆盖合并后）
- `outputs/2025/warnings.csv`：必须复核的问题
- `outputs/2025/tax_report.md`：简明文字报告

## 重要边界

- 这是报税辅助引擎与审计底稿生成器，不替代税务机关或专业税务师意见。
- 部分卖出成本匹配默认使用 FIFO。若券商年度税表或税务师采用不同 lot 成本口径，应以可证明底稿调整。
- 美股 ADR、港股、跨市场证券的“所得来源地”可能存在口径差异，`config/issuer_region_overrides.csv` 可人工覆盖。
- v1 不自动计算期权、基金、债券、公司行动拆股/合股等复杂情形；这些会在复核事项中保留。
- 若只下载到 `2024` 月结单，而实际建仓早于 `2024`，自动推导仍会不完整。
