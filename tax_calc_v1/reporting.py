from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path

import pandas as pd

try:
    from .models import DividendRecord, Lot, RealizedGainRecord, TaxSummary, TradeRecord
    from .tax_engine import group_capital_by_region, group_dividends_by_region, money
except ImportError:
    from models import DividendRecord, Lot, RealizedGainRecord, TaxSummary, TradeRecord
    from tax_engine import group_capital_by_region, group_dividends_by_region, money


def decimal_to_string(value: object) -> object:
    if isinstance(value, Decimal):
        return str(money(value))
    return value


def dataclass_rows(records: list[object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in records:
        row = asdict(record) if is_dataclass(record) else dict(record)
        rows.append({key: decimal_to_string(value) for key, value in row.items()})
    return rows


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)


def build_opening_lot_template(opening_positions: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for position in opening_positions:
        key = (str(position["symbol"]), str(position["region"]), str(position["currency"]))
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "symbol": position["symbol"],
                "region": position["region"],
                "currency": position["currency"],
                "quantity": decimal_to_string(position["quantity"]),
                "unit_cost": "",
                "acquisition_date": "",
                "source": "2025-01期初持仓，请填入历史每股成本；如有多批成本，可拆成多行。",
                "statement_price_for_reference": decimal_to_string(position["statement_price"]),
                "instrument_type": position["instrument_type"],
            }
        )
    return rows


def build_derived_opening_lot_rows(lots: list[Lot]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for lot in lots:
        if lot.quantity_remaining <= Decimal("0.0000001"):
            continue
        rows.append(
            {
                "symbol": lot.symbol,
                "region": lot.region,
                "currency": lot.currency,
                "quantity": decimal_to_string(lot.quantity_remaining),
                "unit_cost": decimal_to_string(lot.unit_cost),
                "acquisition_date": lot.acquisition_date.isoformat() if lot.acquisition_date else "",
                "source": lot.source,
            }
        )
    return rows


def build_app_reference_rows(
    realized_records: list[RealizedGainRecord],
    dividends: list[DividendRecord],
    fx_rates: dict[str, Decimal],
) -> list[dict[str, object]]:
    return group_capital_by_region(realized_records, fx_rates) + group_dividends_by_region(dividends, fx_rates)


def build_summary_rows(summary: TaxSummary) -> list[dict[str, object]]:
    return [
        {"item": "年度", "amount_cny": summary.year, "note": ""},
        {"item": "财产转让收入总额", "amount_cny": summary.capital_gross_proceeds, "note": "已平仓且成本完整部分"},
        {"item": "财产原值/买入成本", "amount_cny": summary.capital_cost_basis, "note": "含买入侧费用"},
        {"item": "转让合理税费", "amount_cny": summary.capital_sell_fees, "note": "卖出侧费用"},
        {"item": "财产转让年度净收益", "amount_cny": summary.capital_net_gain, "note": "同年度盈亏互抵"},
        {"item": "财产转让应纳税所得额", "amount_cny": summary.capital_taxable_income, "note": "年度净亏损按 0 计税，不结转"},
        {"item": "财产转让应纳税额", "amount_cny": summary.capital_tax_before_credit, "note": "20%"},
        {"item": "股息红利收入总额", "amount_cny": summary.dividend_gross_income, "note": "现金股息毛额"},
        {"item": "股息红利境外已纳税额", "amount_cny": summary.dividend_foreign_tax_paid, "note": "预扣税/withholding tax"},
        {"item": "股息红利应纳税额", "amount_cny": summary.dividend_tax_before_credit, "note": "20%"},
        {"item": "股息红利本年抵免额", "amount_cny": summary.dividend_credit_used, "note": "限额抵免"},
        {"item": "股息红利超限结转抵免额", "amount_cny": summary.dividend_credit_carryforward, "note": "预留 5 年结转接口"},
        {"item": "合计应补税额", "amount_cny": summary.total_tax_due_cny, "note": "用于个税 APP 申报参考"},
        {"item": "结果是否完整", "amount_cny": "否" if summary.incomplete else "是", "note": "若否，先处理 unresolved/warnings"},
    ]


def write_report(
    output_dir: Path,
    year: int,
    trades: list[TradeRecord],
    realized_records: list[RealizedGainRecord],
    dividends: list[DividendRecord],
    derived_opening_lots: list[Lot],
    opening_lots_used: list[Lot],
    opening_template_rows: list[dict[str, object]],
    app_reference_rows: list[dict[str, object]],
    summary: TaxSummary,
    fx_rates: dict[str, Decimal],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    write_csv(output_dir / "normalized_trades.csv", dataclass_rows(trades))
    write_csv(output_dir / "realized_capital_gains.csv", dataclass_rows(realized_records))
    write_csv(output_dir / "dividends.csv", dataclass_rows(dividends))
    write_csv(output_dir / "derived_opening_lots.csv", build_derived_opening_lot_rows(derived_opening_lots))
    write_csv(output_dir / "opening_lots_used.csv", build_derived_opening_lot_rows(opening_lots_used))
    write_csv(output_dir / "opening_lots_template.csv", opening_template_rows)
    write_csv(output_dir / "tax_app_reference.csv", [{key: decimal_to_string(value) for key, value in row.items()} for row in app_reference_rows])
    write_csv(output_dir / "summary.csv", [{key: decimal_to_string(value) for key, value in row.items()} for row in build_summary_rows(summary)])
    write_csv(output_dir / "warnings.csv", [{"warning": warning} for warning in summary.warnings])

    payload = {
        "summary": {key: decimal_to_string(value) for key, value in asdict(summary).items()},
        "fx_rates_to_cny": {currency: str(rate) for currency, rate in fx_rates.items()},
        "app_reference": [{key: decimal_to_string(value) for key, value in row.items()} for row in app_reference_rows],
        "warnings": summary.warnings,
    }
    write_json(output_dir / "tax_report.json", payload)

    with pd.ExcelWriter(output_dir / f"cn_overseas_tax_report_{year}.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(build_summary_rows(summary)).to_excel(writer, sheet_name="申报汇总", index=False)
        pd.DataFrame(app_reference_rows).to_excel(writer, sheet_name="个税APP参考", index=False)
        pd.DataFrame(dataclass_rows(realized_records)).to_excel(writer, sheet_name="已实现交易明细", index=False)
        pd.DataFrame(dataclass_rows(dividends)).to_excel(writer, sheet_name="股息红利明细", index=False)
        pd.DataFrame(build_derived_opening_lot_rows(derived_opening_lots)).to_excel(writer, sheet_name="自动推导期初lot", index=False)
        pd.DataFrame(build_derived_opening_lot_rows(opening_lots_used)).to_excel(writer, sheet_name="实际使用期初lot", index=False)
        pd.DataFrame(opening_template_rows).to_excel(writer, sheet_name="期初持仓成本模板", index=False)
        pd.DataFrame({"currency": list(fx_rates.keys()), "cny_rate": list(fx_rates.values())}).to_excel(writer, sheet_name="汇率", index=False)
        pd.DataFrame({"warning": summary.warnings}).to_excel(writer, sheet_name="复核事项", index=False)

    markdown = [
        f"# {year} 中国税务居民境外投资个税测算报告",
        "",
        "## 核心结论",
        f"- 合计应补税额：{summary.total_tax_due_cny} CNY",
        f"- 财产转让年度净收益：{summary.capital_net_gain} CNY",
        f"- 财产转让应纳税额：{summary.capital_tax_before_credit} CNY",
        f"- 股息红利应纳税额：{summary.dividend_tax_before_credit} CNY",
        f"- 股息红利本年抵免额：{summary.dividend_credit_used} CNY",
        f"- 结果完整性：{'不完整，需要补充期初成本/复核事项' if summary.incomplete else '完整'}",
        "",
        "## 个税 APP 填报参考",
        "- `tax_app_reference.csv` 按“所得类型 × 国家/地区”汇总，方便对应境外收入申报与境外所得抵免明细。",
        "- `cn_overseas_tax_report_*.xlsx` 里同名 sheet 已整理为可读格式。",
        "",
        "## 复核事项",
    ]
    if summary.warnings:
        markdown.extend(f"- {warning}" for warning in summary.warnings)
    else:
        markdown.append("- 暂无阻断性复核事项。")
    markdown.extend(
        [
            "",
            "## 重要边界",
            "- 本工具是报税辅助引擎与审计底稿生成器，不替代税务机关或专业税务师意见。",
            "- 部分卖出成本匹配默认使用 FIFO；若券商年度已实现盈亏明细采用不同 lot 规则，应以可证明口径调整期初成本表。",
            "- 未平仓浮盈浮亏、入金出金、融资利息、基金申赎现金流均不进入本版计税。",
        ]
    )
    (output_dir / "tax_report.md").write_text("\n".join(markdown), encoding="utf-8")
