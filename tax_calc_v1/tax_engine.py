from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

try:
    from .models import DividendRecord, Lot, RealizedGainRecord, TaxSummary, TradeRecord
    from .tax_rules import DEFAULT_FX_RATES_TO_CNY, RuleProfile
except ImportError:
    from models import DividendRecord, Lot, RealizedGainRecord, TaxSummary, TradeRecord
    from tax_rules import DEFAULT_FX_RATES_TO_CNY, RuleProfile


MONEY_QUANT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def safe_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).strip().replace(",", "")
    if text == "":
        return Decimal("0")
    return Decimal(text)


def load_fx_rates(path: Path | None) -> dict[str, Decimal]:
    rates = dict(DEFAULT_FX_RATES_TO_CNY)
    if not path or not path.exists():
        return rates
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            currency = (row.get("currency") or "").strip().upper()
            rate_text = (row.get("cny_rate") or "").strip()
            if currency and rate_text:
                rates[currency] = safe_decimal(rate_text)
    return rates


def to_cny(amount: Decimal, currency: str, fx_rates: dict[str, Decimal]) -> Decimal:
    if currency not in fx_rates:
        raise ValueError(f"缺少 {currency} → CNY 汇率，请在 fx_rates_2025.csv 中补充。")
    return money(amount * fx_rates[currency])


def load_opening_lots(path: Path | None) -> list[Lot]:
    if not path or not path.exists():
        return []
    lots: list[Lot] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = (row.get("symbol") or "").strip()
            currency = (row.get("currency") or "").strip().upper()
            quantity = safe_decimal(row.get("quantity"))
            unit_cost = safe_decimal(row.get("unit_cost"))
            if not symbol or not currency or quantity <= 0 or unit_cost <= 0:
                continue
            acquisition_text = (row.get("acquisition_date") or "").strip()
            acquisition_date = date.fromisoformat(acquisition_text) if acquisition_text else None
            lots.append(
                Lot(
                    symbol=symbol,
                    region=(row.get("region") or "待确认").strip(),
                    currency=currency,
                    quantity_remaining=quantity,
                    unit_cost=unit_cost,
                    acquisition_date=acquisition_date,
                    source=(row.get("source") or "opening_lot").strip(),
                )
            )
    return lots


def _lot_sort_key(lot: Lot) -> tuple[date, str]:
    return (lot.acquisition_date or date.min, lot.source)


def build_remaining_lots(
    trades: list[TradeRecord],
    seed_opening_lots: list[Lot],
    profile: RuleProfile,
) -> tuple[list[Lot], list[str]]:
    lots_by_key: dict[tuple[str, str, str], list[Lot]] = defaultdict(list)
    for seed_lot in seed_opening_lots:
        lots_by_key[(seed_lot.symbol, seed_lot.region, seed_lot.currency)].append(
            Lot(
                symbol=seed_lot.symbol,
                region=seed_lot.region,
                currency=seed_lot.currency,
                quantity_remaining=seed_lot.quantity_remaining,
                unit_cost=seed_lot.unit_cost,
                acquisition_date=seed_lot.acquisition_date,
                source=seed_lot.source,
            )
        )
    for key in lots_by_key:
        lots_by_key[key].sort(key=_lot_sort_key)

    warnings: list[str] = []
    taxable_trades = [trade for trade in trades if is_taxable_trade(trade, profile)]
    taxable_trades.sort(key=lambda trade: (trade.trade_date or date.max, trade.statement_file, trade.symbol, trade.side))

    for trade in taxable_trades:
        key = (trade.symbol, trade.region, trade.currency)
        if trade.side == "BUY" and trade.quantity > 0:
            total_cost = abs(trade.gross_amount) + trade.fees_total
            unit_cost = total_cost / trade.quantity
            lots_by_key[key].append(
                Lot(
                    symbol=trade.symbol,
                    region=trade.region,
                    currency=trade.currency,
                    quantity_remaining=trade.quantity,
                    unit_cost=unit_cost,
                    acquisition_date=trade.trade_date,
                    source=f"{trade.statement_file}:{trade.trade_date or ''}:BUY",
                )
            )
            lots_by_key[key].sort(key=_lot_sort_key)
            continue

        if trade.side != "SELL" or trade.quantity <= 0:
            continue

        remaining_quantity = trade.quantity
        while remaining_quantity > 0 and lots_by_key[key]:
            current_lot = lots_by_key[key][0]
            matched_quantity = min(remaining_quantity, current_lot.quantity_remaining)
            current_lot.quantity_remaining -= matched_quantity
            if current_lot.quantity_remaining < Decimal("0.0000001"):
                current_lot.quantity_remaining = Decimal("0")
            remaining_quantity -= matched_quantity
            if current_lot.quantity_remaining <= 0:
                lots_by_key[key].pop(0)

        if remaining_quantity > 0:
            warnings.append(
                f"历史推导缺少 {trade.symbol} 在 {trade.trade_date} 卖出的前序成本 {remaining_quantity} 股；"
                "说明还需要更早年度月结单或手工补录历史 lot。"
            )

    remaining_lots: list[Lot] = []
    for key_lots in lots_by_key.values():
        for lot in key_lots:
            if lot.quantity_remaining > Decimal("0.0000001"):
                remaining_lots.append(lot)
    remaining_lots.sort(key=lambda lot: (lot.symbol, lot.region, lot.currency, lot.acquisition_date or date.min, lot.source))
    return remaining_lots, warnings


def merge_opening_lots(derived_lots: list[Lot], manual_lots: list[Lot]) -> list[Lot]:
    if not manual_lots:
        return derived_lots
    manual_keys = {(lot.symbol, lot.region, lot.currency) for lot in manual_lots}
    merged = [lot for lot in derived_lots if (lot.symbol, lot.region, lot.currency) not in manual_keys]
    merged.extend(manual_lots)
    merged.sort(key=lambda lot: (lot.symbol, lot.region, lot.currency, lot.acquisition_date or date.min, lot.source))
    return merged


def derive_year_end_lots_with_min_opening(
    trades: list[TradeRecord],
    ending_positions: dict[tuple[str, str, str], Decimal],
    profile: RuleProfile,
) -> tuple[list[Lot], list[str]]:
    warnings: list[str] = []
    lots_out: list[Lot] = []
    grouped: dict[tuple[str, str, str], list[TradeRecord]] = defaultdict(list)

    for trade in trades:
        if not is_taxable_trade(trade, profile):
            continue
        grouped[(trade.symbol, trade.region, trade.currency)].append(trade)

    for key, expected_qty in ending_positions.items():
        symbol, region, currency = key
        symbol_trades = grouped.get(key, [])
        if not symbol_trades and expected_qty > 0:
            warnings.append(f"{symbol} 在年度税表期末有 {expected_qty} {currency} 持仓，但交易流水里未找到对应买卖记录。")
            continue

        symbol_trades.sort(key=lambda trade: (trade.trade_date or date.min, trade.statement_file, trade.side))
        inventory = Decimal("0")
        min_inventory = Decimal("0")
        for trade in symbol_trades:
            inventory += trade.quantity if trade.side == "BUY" else -trade.quantity
            if inventory < min_inventory:
                min_inventory = inventory

        opening_unknown = -min_inventory
        fifo_lots: list[Lot] = []
        if opening_unknown > 0:
            fifo_lots.append(
                Lot(
                    symbol=symbol,
                    region=region,
                    currency=currency,
                    quantity_remaining=opening_unknown,
                    unit_cost=Decimal("0"),
                    acquisition_date=None,
                    source="UNKNOWN_OPENING_LOT",
                )
            )

        for trade in symbol_trades:
            if trade.side == "BUY":
                total_cost = abs(trade.gross_amount) + trade.fees_total
                unit_cost = total_cost / trade.quantity
                fifo_lots.append(
                    Lot(
                        symbol=symbol,
                        region=region,
                        currency=currency,
                        quantity_remaining=trade.quantity,
                        unit_cost=unit_cost,
                        acquisition_date=trade.trade_date,
                        source=f"{trade.statement_file}:{trade.trade_date or ''}:BUY",
                    )
                )
                continue

            remain = trade.quantity
            while remain > 0 and fifo_lots:
                current_lot = fifo_lots[0]
                matched = min(remain, current_lot.quantity_remaining)
                current_lot.quantity_remaining -= matched
                if current_lot.quantity_remaining < Decimal("0.0000001"):
                    current_lot.quantity_remaining = Decimal("0")
                remain -= matched
                if current_lot.quantity_remaining <= 0:
                    fifo_lots.pop(0)
            if remain > 0:
                warnings.append(f"{symbol} 年度税表交易流水在 {trade.trade_date} 仍出现 {remain} 股无法匹配的卖出。")

        unknown_remaining = Decimal("0")
        known_remaining = Decimal("0")
        surviving_known_lots: list[Lot] = []
        for lot in fifo_lots:
            if lot.quantity_remaining <= Decimal("0.0000001"):
                continue
            if lot.source == "UNKNOWN_OPENING_LOT":
                unknown_remaining += lot.quantity_remaining
            else:
                known_remaining += lot.quantity_remaining
                surviving_known_lots.append(lot)

        total_remaining = unknown_remaining + known_remaining
        if total_remaining != expected_qty:
            warnings.append(
                f"{symbol} 年度税表推导后的期末持仓 {total_remaining} {currency} 与持仓总览 {expected_qty} {currency} 不一致。"
            )
            continue
        if unknown_remaining > 0:
            warnings.append(
                f"{symbol} 期末仍有 {unknown_remaining} 股来自更早历史未知 lot，需要更早年度成交或手工成本。"
            )
            continue

        lots_out.extend(surviving_known_lots)

    lots_out.sort(key=lambda lot: (lot.symbol, lot.region, lot.currency, lot.acquisition_date or date.min, lot.source))
    return lots_out, warnings


def apply_region_overrides(trades: list[TradeRecord], dividends: list[DividendRecord], path: Path | None) -> None:
    if not path or not path.exists():
        return
    overrides: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = (row.get("symbol") or "").strip()
            region = (row.get("region") or "").strip()
            if symbol and region:
                overrides[symbol] = region
    for trade in trades:
        if trade.symbol in overrides:
            trade.region = overrides[trade.symbol]
    for dividend in dividends:
        if dividend.symbol in overrides:
            dividend.region = overrides[dividend.symbol]


def is_taxable_trade(trade: TradeRecord, profile: RuleProfile) -> bool:
    return trade.instrument_type in profile.taxable_instrument_types and trade.side in {"BUY", "SELL"}


def calculate_realized_gains(
    trades: list[TradeRecord],
    opening_lots: list[Lot],
    profile: RuleProfile,
) -> tuple[list[RealizedGainRecord], list[str]]:
    lots_by_key: dict[tuple[str, str, str], list[Lot]] = defaultdict(list)
    for opening_lot in opening_lots:
        lots_by_key[(opening_lot.symbol, opening_lot.region, opening_lot.currency)].append(opening_lot)

    realized: list[RealizedGainRecord] = []
    warnings: list[str] = []

    taxable_trades = [trade for trade in trades if is_taxable_trade(trade, profile)]
    taxable_trades.sort(key=lambda trade: (trade.trade_date or date.max, trade.statement_file, trade.symbol, trade.side))

    for trade in taxable_trades:
        key = (trade.symbol, trade.region, trade.currency)
        if trade.side == "BUY":
            if trade.quantity <= 0:
                continue
            total_cost = abs(trade.gross_amount) + trade.fees_total
            unit_cost = total_cost / trade.quantity
            lots_by_key[key].append(
                Lot(
                    symbol=trade.symbol,
                    region=trade.region,
                    currency=trade.currency,
                    quantity_remaining=trade.quantity,
                    unit_cost=unit_cost,
                    acquisition_date=trade.trade_date,
                    source=f"{trade.statement_file}:{trade.trade_date or ''}:BUY",
                )
            )
            continue

        if trade.side != "SELL" or trade.quantity <= 0:
            continue

        remaining_quantity = trade.quantity
        acquisition_sources: list[str] = []
        lots = lots_by_key[key]
        while remaining_quantity > 0 and lots:
            current_lot = lots[0]
            matched_quantity = min(remaining_quantity, current_lot.quantity_remaining)
            ratio = matched_quantity / trade.quantity
            gross_proceeds = trade.gross_amount * ratio
            sell_fees = trade.fees_total * ratio
            cost_basis = current_lot.unit_cost * matched_quantity
            realized_gain = gross_proceeds - sell_fees - cost_basis
            acquisition_sources.append(current_lot.source)
            realized.append(
                RealizedGainRecord(
                    sell_date=trade.trade_date,
                    symbol=trade.symbol,
                    region=trade.region,
                    currency=trade.currency,
                    quantity=matched_quantity,
                    gross_proceeds=money(gross_proceeds),
                    allocated_sell_fees=money(sell_fees),
                    cost_basis=money(cost_basis),
                    realized_gain=money(realized_gain),
                    acquisition_sources="; ".join(acquisition_sources),
                )
            )
            current_lot.quantity_remaining -= matched_quantity
            remaining_quantity -= matched_quantity
            if current_lot.quantity_remaining <= 0:
                lots.pop(0)

        if remaining_quantity > 0:
            unresolved_ratio = remaining_quantity / trade.quantity
            unresolved_gross = money(trade.gross_amount * unresolved_ratio)
            unresolved_fee = money(trade.fees_total * unresolved_ratio)
            realized.append(
                RealizedGainRecord(
                    sell_date=trade.trade_date,
                    symbol=trade.symbol,
                    region=trade.region,
                    currency=trade.currency,
                    quantity=Decimal("0"),
                    gross_proceeds=Decimal("0"),
                    allocated_sell_fees=Decimal("0"),
                    cost_basis=Decimal("0"),
                    realized_gain=Decimal("0"),
                    acquisition_sources="MISSING_OPENING_LOT_COST",
                    unresolved_quantity=remaining_quantity,
                )
            )
            warnings.append(
                f"{trade.symbol} 在 {trade.trade_date} 卖出 {trade.quantity} 股，其中 {remaining_quantity} 股缺少期初/历史买入成本；"
                f"未计入毛收入 {unresolved_gross} {trade.currency}、卖出费用 {unresolved_fee} {trade.currency}。"
            )

    return realized, warnings


def summarize_tax(
    year: int,
    realized_records: list[RealizedGainRecord],
    dividends: list[DividendRecord],
    fx_rates: dict[str, Decimal],
    warnings: list[str],
    profile: RuleProfile,
) -> TaxSummary:
    capital_gross_cny = Decimal("0")
    capital_cost_cny = Decimal("0")
    capital_sell_fees_cny = Decimal("0")
    capital_gain_cny = Decimal("0")
    incomplete = bool(warnings)

    for record in realized_records:
        if record.unresolved_quantity > 0:
            incomplete = True
            continue
        capital_gross_cny += to_cny(record.gross_proceeds, record.currency, fx_rates)
        capital_cost_cny += to_cny(record.cost_basis, record.currency, fx_rates)
        capital_sell_fees_cny += to_cny(record.allocated_sell_fees, record.currency, fx_rates)
        capital_gain_cny += to_cny(record.realized_gain, record.currency, fx_rates)

    capital_taxable_income = max(capital_gain_cny, Decimal("0"))
    capital_tax_before_credit = money(capital_taxable_income * profile.capital_gain_tax_rate)

    dividend_gross_cny = Decimal("0")
    dividend_withheld_cny = Decimal("0")
    for dividend in dividends:
        dividend_gross_cny += to_cny(dividend.gross_dividend, dividend.currency, fx_rates)
        dividend_withheld_cny += to_cny(dividend.foreign_tax_withheld, dividend.currency, fx_rates)

    dividend_tax_before_credit = money(dividend_gross_cny * profile.dividend_tax_rate)
    dividend_credit_used = min(dividend_withheld_cny, dividend_tax_before_credit)
    dividend_credit_carryforward = max(dividend_withheld_cny - dividend_tax_before_credit, Decimal("0"))
    total_tax_due = money(capital_tax_before_credit + dividend_tax_before_credit - dividend_credit_used)

    if not profile.capital_loss_carry_forward_allowed and capital_gain_cny < 0:
        warnings.append("本年度财产转让净亏损按规则不产生应纳税额，也不结转以后年度抵扣。")
    if dividend_credit_carryforward > 0:
        warnings.append(
            f"股息境外已纳税额超过抵免限额 {dividend_credit_carryforward} CNY，需按境外税额抵免规则记录结转。"
        )

    return TaxSummary(
        year=year,
        capital_gross_proceeds=money(capital_gross_cny),
        capital_cost_basis=money(capital_cost_cny),
        capital_sell_fees=money(capital_sell_fees_cny),
        capital_net_gain=money(capital_gain_cny),
        capital_taxable_income=money(capital_taxable_income),
        capital_tax_before_credit=capital_tax_before_credit,
        dividend_gross_income=money(dividend_gross_cny),
        dividend_foreign_tax_paid=money(dividend_withheld_cny),
        dividend_tax_before_credit=dividend_tax_before_credit,
        dividend_credit_used=money(dividend_credit_used),
        dividend_credit_carryforward=money(dividend_credit_carryforward),
        total_tax_due_cny=total_tax_due,
        incomplete=incomplete,
        warnings=warnings,
    )


def group_capital_by_region(realized_records: list[RealizedGainRecord], fx_rates: dict[str, Decimal]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {
            "gross_income_rmb": Decimal("0"),
            "property_cost_rmb": Decimal("0"),
            "reasonable_fee_rmb": Decimal("0"),
            "taxable_income_rmb": Decimal("0"),
        }
    )
    for record in realized_records:
        if record.unresolved_quantity > 0:
            continue
        region_data = grouped[record.region]
        region_data["gross_income_rmb"] += to_cny(record.gross_proceeds, record.currency, fx_rates)
        region_data["property_cost_rmb"] += to_cny(record.cost_basis, record.currency, fx_rates)
        region_data["reasonable_fee_rmb"] += to_cny(record.allocated_sell_fees, record.currency, fx_rates)
        region_data["taxable_income_rmb"] += to_cny(record.realized_gain, record.currency, fx_rates)

    rows: list[dict[str, object]] = []
    for region, values in sorted(grouped.items()):
        taxable = money(values["taxable_income_rmb"])
        rows.append(
            {
                "income_type": "财产转让所得",
                "country_or_region": region,
                "gross_income_rmb": money(values["gross_income_rmb"]),
                "property_original_value_rmb": money(values["property_cost_rmb"]),
                "reasonable_tax_fee_rmb": money(values["reasonable_fee_rmb"]),
                "taxable_income_rmb": taxable,
                "tax_rate": "20%",
                "tax_before_credit_rmb": money(max(taxable, Decimal("0")) * Decimal("0.20")),
                "foreign_tax_paid_rmb": Decimal("0.00"),
                "credit_used_rmb": Decimal("0.00"),
            }
        )
    return rows


def group_dividends_by_region(dividends: list[DividendRecord], fx_rates: dict[str, Decimal]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {
            "gross_income_rmb": Decimal("0"),
            "foreign_tax_paid_rmb": Decimal("0"),
        }
    )
    for dividend in dividends:
        region_data = grouped[dividend.region]
        region_data["gross_income_rmb"] += to_cny(dividend.gross_dividend, dividend.currency, fx_rates)
        region_data["foreign_tax_paid_rmb"] += to_cny(dividend.foreign_tax_withheld, dividend.currency, fx_rates)

    rows: list[dict[str, object]] = []
    for region, values in sorted(grouped.items()):
        gross = money(values["gross_income_rmb"])
        tax_before_credit = money(gross * Decimal("0.20"))
        foreign_tax = money(values["foreign_tax_paid_rmb"])
        rows.append(
            {
                "income_type": "利息股息红利所得",
                "country_or_region": region,
                "gross_income_rmb": gross,
                "property_original_value_rmb": Decimal("0.00"),
                "reasonable_tax_fee_rmb": Decimal("0.00"),
                "taxable_income_rmb": gross,
                "tax_rate": "20%",
                "tax_before_credit_rmb": tax_before_credit,
                "foreign_tax_paid_rmb": foreign_tax,
                "credit_used_rmb": min(foreign_tax, tax_before_credit),
            }
        )
    return rows
