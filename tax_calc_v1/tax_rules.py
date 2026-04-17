from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


CN_CAPITAL_GAIN_TAX_RATE = Decimal("0.20")
CN_DIVIDEND_TAX_RATE = Decimal("0.20")
CAPITAL_LOSS_CARRY_FORWARD_ALLOWED = False
FOREIGN_TAX_CREDIT_CARRY_FORWARD_YEARS = 5
SUPPORTED_YEAR = 2025

TAXABLE_INSTRUMENT_TYPES = {"STOCK", "ETF", "ADR"}
EXCLUDED_INSTRUMENT_TYPES = {"OPTION", "FUND", "CASH", "UNKNOWN"}

DEFAULT_FX_RATES_TO_CNY = {
    "CNY": Decimal("1"),
    "CNH": Decimal("1"),
    "USD": Decimal("7.1884"),
    "HKD": Decimal("0.9231"),
}

REGION_BY_MARKET = {
    "SEHK": "中国香港",
    "HK": "中国香港",
    "US": "美国",
    "OCEA": "美国",
    "JNST": "美国",
    "EDGX": "美国",
    "ARCX": "美国",
    "XNAS": "美国",
    "CDED": "美国",
    "BATO": "美国",
    "KNEM": "美国",
    "MEMX": "美国",
    "EMLD": "美国",
    "EPRL": "美国",
    "MXOP": "美国",
    "ARCO": "美国",
}


@dataclass(frozen=True)
class RuleProfile:
    name: str = "CN_OVERSEAS_INVESTMENT_TAX_V1"
    capital_gain_tax_rate: Decimal = CN_CAPITAL_GAIN_TAX_RATE
    dividend_tax_rate: Decimal = CN_DIVIDEND_TAX_RATE
    capital_loss_carry_forward_allowed: bool = CAPITAL_LOSS_CARRY_FORWARD_ALLOWED
    foreign_tax_credit_carry_forward_years: int = FOREIGN_TAX_CREDIT_CARRY_FORWARD_YEARS
    cost_basis_method: str = "FIFO"
    taxable_instrument_types: frozenset[str] = frozenset(TAXABLE_INSTRUMENT_TYPES)

