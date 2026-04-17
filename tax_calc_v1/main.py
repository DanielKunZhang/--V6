from __future__ import annotations

import argparse
import re
from pathlib import Path

try:
    from .futu_statement_parser import parse_any_statement, parse_annual_tax_workbook
    from .reporting import build_app_reference_rows, build_opening_lot_template, write_report
    from .tax_engine import (
        apply_region_overrides,
        build_remaining_lots,
        calculate_realized_gains,
        derive_year_end_lots_with_min_opening,
        load_fx_rates,
        load_opening_lots,
        merge_opening_lots,
        summarize_tax,
    )
    from .tax_rules import RuleProfile, SUPPORTED_YEAR
except ImportError:
    from futu_statement_parser import parse_any_statement, parse_annual_tax_workbook
    from reporting import build_app_reference_rows, build_opening_lot_template, write_report
    from tax_engine import (
        apply_region_overrides,
        build_remaining_lots,
        calculate_realized_gains,
        derive_year_end_lots_with_min_opening,
        load_fx_rates,
        load_opening_lots,
        merge_opening_lots,
        summarize_tax,
    )
    from tax_rules import RuleProfile, SUPPORTED_YEAR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Futu PDF 对账单 → 中国税务居民境外投资个税测算 v1")
    parser.add_argument("--pdf-dir", type=Path, default=Path("."), help="富途月结单 PDF 所在目录")
    parser.add_argument("--year", type=int, default=SUPPORTED_YEAR, help="纳税年度")
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/2025"), help="输出目录")
    parser.add_argument("--opening-lots", type=Path, default=Path("config/opening_lots_2025.csv"), help="期初/历史持仓成本 CSV")
    parser.add_argument("--fx-rates", type=Path, default=Path("config/fx_rates_2025.csv"), help="年度外币兑人民币汇率 CSV")
    parser.add_argument("--region-overrides", type=Path, default=Path("config/issuer_region_overrides.csv"), help="证券来源地覆盖表")
    parser.add_argument("--auto-derive-opening-lots", action="store_true", help="自动用目标年度之前的月结单推导期初 lot")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    statement_files = sorted(
        [
            path
            for path in args.pdf_dir.iterdir()
            if path.is_file() and "对账单" in path.name and path.suffix.lower() in {".pdf", ".csv"}
        ]
    )
    if not statement_files:
        raise SystemExit(f"未在 {args.pdf_dir} 找到 PDF/CSV 对账单。")

    current_year_pdf_files = []
    history_pdf_files = []
    for statement_path in statement_files:
        name = statement_path.name
        if name.startswith(f"{args.year}-"):
            current_year_pdf_files.append(statement_path)
        else:
            prefix = name[:4]
            if prefix.isdigit() and int(prefix) < args.year:
                history_pdf_files.append(statement_path)

    pdf_files = current_year_pdf_files or all_pdf_files
    if not pdf_files:
        raise SystemExit(f"未找到 {args.year} 年 PDF 对账单。")

    all_trades = []
    all_dividends = []
    all_opening_positions = []
    history_trades = []

    for statement_path in history_pdf_files:
        trades, cash_records, dividends, opening_positions = parse_any_statement(statement_path)
        history_trades.extend(trades)

    for statement_path in pdf_files:
        trades, cash_records, dividends, opening_positions = parse_any_statement(statement_path)
        all_trades.extend(trades)
        all_dividends.extend(dividends)
        if statement_path == pdf_files[0]:
            all_opening_positions.extend(opening_positions)

    apply_region_overrides(all_trades, all_dividends, args.region_overrides)
    apply_region_overrides(history_trades, [], args.region_overrides)
    fx_rates = load_fx_rates(args.fx_rates)
    profile = RuleProfile()
    manual_opening_lots = load_opening_lots(args.opening_lots)

    derived_opening_lots = []
    history_warnings = []
    if args.auto_derive_opening_lots and history_trades:
        derived_opening_lots, history_warnings = build_remaining_lots(history_trades, [], profile)

    relevant_opening_symbols = {str(position["symbol"]) for position in all_opening_positions}
    if relevant_opening_symbols:
        history_warnings = [warning for warning in history_warnings if any(f" {symbol} " in warning for symbol in relevant_opening_symbols)]
    unresolved_history_symbols = set()
    for warning in history_warnings:
        match = re.match(r"历史推导缺少\s+([A-Z0-9.]+)\s+", warning)
        if match:
            unresolved_history_symbols.add(match.group(1))

    annual_derived_lots = []
    annual_warnings = []
    annual_tax_path = args.pdf_dir / f"{args.year - 1}_年度税表.xlsx"
    if args.auto_derive_opening_lots and annual_tax_path.exists() and all_opening_positions:
        annual_trades, annual_holdings = parse_annual_tax_workbook(annual_tax_path)
        apply_region_overrides(annual_trades, [], args.region_overrides)
        relevant_holdings = {
            key: qty
            for key, qty in annual_holdings.items()
            if key[0] in unresolved_history_symbols
        }
        annual_derived_lots, annual_warnings = derive_year_end_lots_with_min_opening(annual_trades, relevant_holdings, profile)
        resolved_symbols = {lot.symbol for lot in annual_derived_lots}
        if resolved_symbols:
            history_warnings = [
                warning
                for warning in history_warnings
                if not any(f" {symbol} " in warning for symbol in resolved_symbols)
            ]

    opening_lots = merge_opening_lots(derived_opening_lots, annual_derived_lots)
    opening_lots = merge_opening_lots(opening_lots, manual_opening_lots)
    opening_lots_snapshot = [
        type(lot)(
            symbol=lot.symbol,
            region=lot.region,
            currency=lot.currency,
            quantity_remaining=lot.quantity_remaining,
            unit_cost=lot.unit_cost,
            acquisition_date=lot.acquisition_date,
            source=lot.source,
        )
        for lot in opening_lots
    ]
    realized_records, warnings = calculate_realized_gains(all_trades, opening_lots, profile)
    warnings = history_warnings + annual_warnings + warnings
    summary = summarize_tax(args.year, realized_records, all_dividends, fx_rates, warnings, profile)
    opening_template_rows = build_opening_lot_template(all_opening_positions)
    app_reference_rows = build_app_reference_rows(realized_records, all_dividends, fx_rates)
    write_report(
        output_dir=args.out_dir,
        year=args.year,
        trades=all_trades,
        realized_records=realized_records,
        dividends=all_dividends,
        derived_opening_lots=derived_opening_lots,
        opening_lots_used=opening_lots_snapshot,
        opening_template_rows=opening_template_rows,
        app_reference_rows=app_reference_rows,
        summary=summary,
        fx_rates=fx_rates,
    )

    print(f"✅ 已完成 {args.year} 年税务测算")
    print(f"📄 输出目录: {args.out_dir}")
    print(f"💰 合计应补税额: {summary.total_tax_due_cny} CNY")
    if args.auto_derive_opening_lots:
        print(f"📦 自动推导期初 lot 数: {len(derived_opening_lots)}")
    if summary.incomplete:
        print("⚠️ 结果不完整：请先查看 warnings.csv 和 opening_lots_template.csv，补全期初/历史成本后重跑。")


if __name__ == "__main__":
    main()
