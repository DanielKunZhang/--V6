from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class TradeRecord:
    statement_file: str
    statement_month: str
    trade_date: date | None
    settlement_date: date | None
    side: str
    symbol: str
    raw_code: str
    market: str
    region: str
    currency: str
    quantity: Decimal
    unit_price: Decimal
    gross_amount: Decimal
    net_cash_change: Decimal
    fees_total: Decimal
    fees_breakdown: dict[str, Decimal] = field(default_factory=dict)
    instrument_type: str = "UNKNOWN"
    raw_header: str = ""


@dataclass
class CashActivityRecord:
    statement_file: str
    statement_month: str
    date: date
    direction: str
    activity_type: str
    currency: str
    amount: Decimal
    note: str


@dataclass
class DividendRecord:
    date: date
    symbol: str
    region: str
    currency: str
    gross_dividend: Decimal
    foreign_tax_withheld: Decimal
    source_statement_files: list[str] = field(default_factory=list)
    raw_notes: list[str] = field(default_factory=list)


@dataclass
class Lot:
    symbol: str
    region: str
    currency: str
    quantity_remaining: Decimal
    unit_cost: Decimal
    acquisition_date: date | None
    source: str


@dataclass
class RealizedGainRecord:
    sell_date: date | None
    symbol: str
    region: str
    currency: str
    quantity: Decimal
    gross_proceeds: Decimal
    allocated_sell_fees: Decimal
    cost_basis: Decimal
    realized_gain: Decimal
    acquisition_sources: str
    unresolved_quantity: Decimal = Decimal("0")


@dataclass
class TaxSummary:
    year: int
    capital_gross_proceeds: Decimal
    capital_cost_basis: Decimal
    capital_sell_fees: Decimal
    capital_net_gain: Decimal
    capital_taxable_income: Decimal
    capital_tax_before_credit: Decimal
    dividend_gross_income: Decimal
    dividend_foreign_tax_paid: Decimal
    dividend_tax_before_credit: Decimal
    dividend_credit_used: Decimal
    dividend_credit_carryforward: Decimal
    total_tax_due_cny: Decimal
    incomplete: bool
    warnings: list[str] = field(default_factory=list)

