from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber
import pandas as pd

try:
    from .models import CashActivityRecord, DividendRecord, TradeRecord
    from .tax_rules import REGION_BY_MARKET
except ImportError:
    from models import CashActivityRecord, DividendRecord, TradeRecord
    from tax_rules import REGION_BY_MARKET


CURRENCY_CODES = {"HKD", "USD", "CNH", "JPY", "SGD", "CNY"}
TRADE_DIRECTION_MAP = {
    "買買入入開開倉倉": "BUY",
    "买买入入开开仓仓": "BUY",
    "買入開倉": "BUY",
    "买入开仓": "BUY",
    "賣賣出出平平倉倉": "SELL",
    "卖卖出出平平仓仓": "SELL",
    "賣出平倉": "SELL",
    "卖出平仓": "SELL",
    "賣賣出出開開倉倉": "SHORT_OPEN",
    "卖卖出出开开仓仓": "SHORT_OPEN",
    "買買入入平平倉倉": "BUY_TO_CLOSE",
    "买买入入平平仓仓": "BUY_TO_CLOSE",
}


def parse_decimal(value: str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    cleaned = value.strip().replace(",", "").replace("+", "")
    if cleaned in {"", "-"}:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    year, month, day = value.split("/")
    return date(int(year), int(month), int(day))


def extract_pdf_lines(pdf_path: Path) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(line.strip() for line in text.splitlines() if line.strip())
    return lines


def parse_statement_month(lines: list[str], pdf_path: Path) -> str:
    for line in lines[:8]:
        match = re.search(r"(20\d{2})/(\d{2})", line)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
    match = re.search(r"(20\d{2})-(\d{2})", pdf_path.name)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return ""


def normalize_symbol(raw_code: str) -> str:
    symbol = raw_code.split("(")[0].strip()
    symbol = symbol.replace("）", "").replace(")", "")
    return symbol


def classify_instrument(symbol: str, raw_header: str) -> str:
    if re.search(r"\d{6}[CP]\d+", symbol) or re.search(r"[A-Z]{1,6}\d{6}[CP]\d+", symbol):
        return "OPTION"
    if re.search(r"\b\d{6}\s+\d+(\.\d+)?[CP]\b", raw_header):
        return "OPTION"
    if symbol.startswith("HK0000"):
        return "FUND"
    if symbol.isdigit() and len(symbol) == 5:
        return "STOCK"
    if symbol in {"VOO", "QQQ", "IWM", "GLD", "SPY"}:
        return "ETF"
    if re.fullmatch(r"[A-Z.]{1,8}", symbol):
        return "ADR" if symbol in {"PDD", "BABA", "JD", "BIDU", "TCOM"} else "STOCK"
    return "UNKNOWN"


def infer_region(market: str, symbol: str, currency: str) -> str:
    if market in REGION_BY_MARKET:
        return REGION_BY_MARKET[market]
    if symbol.isdigit() and len(symbol) == 5:
        return "中国香港"
    if currency == "USD":
        return "美国"
    if currency == "HKD":
        return "中国香港"
    return "待确认"


def is_trade_start(line: str) -> bool:
    return any(line.startswith(direction) for direction in TRADE_DIRECTION_MAP)


def parse_trade_block(block: list[str], statement_file: str, statement_month: str) -> TradeRecord | None:
    if not block:
        return None
    header = block[0]
    direction_raw = next((direction for direction in TRADE_DIRECTION_MAP if header.startswith(direction)), "")
    if not direction_raw:
        return None
    side = TRADE_DIRECTION_MAP[direction_raw]
    tokens = header.split()
    currency_index = next((idx for idx, token in enumerate(tokens) if token in CURRENCY_CODES), None)
    if currency_index is None or currency_index < 2 or len(tokens) < currency_index + 5:
        return None

    raw_code = tokens[1]
    symbol = normalize_symbol(raw_code)
    currency = tokens[currency_index]
    quantity = parse_decimal(tokens[currency_index + 1])
    unit_price = parse_decimal(tokens[currency_index + 2])
    gross_amount = parse_decimal(tokens[currency_index + 3])
    net_cash_change = parse_decimal(tokens[currency_index + 4])

    market = ""
    trade_date = None
    settlement_date = None
    fill_pattern = re.compile(
        r"^(?P<market>[A-Z]{3,5})\s+(?P<currency>[A-Z]{3})\s+"
        r"(?P<trade_date>20\d{2}/\d{2}/\d{2})\s+"
        r"(?P<settlement_date>20\d{2}/\d{2}/\d{2})\s+"
    )
    for line in block[1:]:
        match = fill_pattern.match(line)
        if match:
            market = match.group("market")
            trade_date = parse_date(match.group("trade_date"))
            settlement_date = parse_date(match.group("settlement_date"))
            break

    fee_line = next((line for line in block if "小計:" in line), "")
    fees_total = Decimal("0")
    fees_breakdown: dict[str, Decimal] = {}
    if fee_line:
        pairs = re.findall(r"([^:\s]+):\s*([+-]?\d[\d,]*(?:\.\d+)?)", fee_line)
        for name, amount in pairs:
            parsed_amount = parse_decimal(amount)
            if name == "小計":
                fees_total = parsed_amount
            else:
                fees_breakdown[name] = parsed_amount

    if not market:
        market = "SEHK" if symbol.isdigit() and len(symbol) == 5 else "US"
    region = infer_region(market, symbol, currency)
    instrument_type = classify_instrument(symbol, " ".join(block))
    return TradeRecord(
        statement_file=statement_file,
        statement_month=statement_month,
        trade_date=trade_date,
        settlement_date=settlement_date,
        side=side,
        symbol=symbol,
        raw_code=raw_code,
        market=market,
        region=region,
        currency=currency,
        quantity=quantity,
        unit_price=unit_price,
        gross_amount=gross_amount,
        net_cash_change=net_cash_change,
        fees_total=fees_total,
        fees_breakdown=fees_breakdown,
        instrument_type=instrument_type,
        raw_header=header,
    )


def parse_trades(lines: list[str], statement_file: str, statement_month: str) -> list[TradeRecord]:
    trades: list[TradeRecord] = []
    current_block: list[str] = []
    in_trade_pages = False

    for line in lines:
        if "交交易易--股股票票和和股股票票期期權權" in line or is_trade_start(line):
            in_trade_pages = True
        if "成交金額合計" in line or "資資金金進進出出" in line or "期期末末概概覽覽" in line:
            if current_block:
                parsed_trade = parse_trade_block(current_block, statement_file, statement_month)
                if parsed_trade:
                    trades.append(parsed_trade)
                current_block = []
            if "資資金金進進出出" in line or "期期末末概概覽覽" in line:
                in_trade_pages = False

        if not in_trade_pages:
            continue

        if is_trade_start(line):
            if current_block:
                parsed_trade = parse_trade_block(current_block, statement_file, statement_month)
                if parsed_trade:
                    trades.append(parsed_trade)
            current_block = [line]
        elif current_block:
            current_block.append(line)

    if current_block:
        parsed_trade = parse_trade_block(current_block, statement_file, statement_month)
        if parsed_trade:
            trades.append(parsed_trade)

    return trades


def parse_cash_activities(lines: list[str], statement_file: str, statement_month: str) -> list[CashActivityRecord]:
    records: list[CashActivityRecord] = []
    in_cash_section = False
    current_line = ""

    for line in lines:
        if "資資金金進進出出" in line:
            in_cash_section = True
            continue
        if in_cash_section and ("融融資資總總覽覽" in line or "期期末末概概覽覽" in line):
            if current_line:
                parsed_record = parse_cash_activity_line(current_line, statement_file, statement_month)
                if parsed_record:
                    records.append(parsed_record)
                current_line = ""
            in_cash_section = False
        if not in_cash_section:
            continue
        if re.match(r"^20\d{2}/\d{2}/\d{2}\s+", line):
            if current_line:
                parsed_record = parse_cash_activity_line(current_line, statement_file, statement_month)
                if parsed_record:
                    records.append(parsed_record)
            current_line = line
        elif current_line:
            current_line += " " + line

    if current_line:
        parsed_record = parse_cash_activity_line(current_line, statement_file, statement_month)
        if parsed_record:
            records.append(parsed_record)
    return records


def parse_cash_activity_line(line: str, statement_file: str, statement_month: str) -> CashActivityRecord | None:
    pattern = re.compile(
        r"^(?P<date>20\d{2}/\d{2}/\d{2})\s+"
        r"(?P<direction>\S+)\s+"
        r"(?P<type>\S+)\s+"
        r"(?P<currency>[A-Z]{3})\s+"
        r"(?P<amount>[+-]?\d[\d,]*(?:\.\d+)?)\s*"
        r"(?P<note>.*)$"
    )
    match = pattern.match(line)
    if not match:
        return None
    parsed_date = parse_date(match.group("date"))
    if parsed_date is None:
        return None
    return CashActivityRecord(
        statement_file=statement_file,
        statement_month=statement_month,
        date=parsed_date,
        direction=match.group("direction"),
        activity_type=match.group("type"),
        currency=match.group("currency"),
        amount=parse_decimal(match.group("amount")),
        note=match.group("note").strip(),
    )


def extract_symbol_from_dividend_note(note: str) -> str:
    cleaned = note.strip()
    match = re.match(r"([A-Z.]{1,10}|\d{5})\b", cleaned)
    if match:
        return match.group(1)
    return "待确认"


def parse_dividends(cash_records: list[CashActivityRecord]) -> list[DividendRecord]:
    grouped: dict[tuple[date, str, str], dict[str, object]] = defaultdict(
        lambda: {
            "gross": Decimal("0"),
            "withheld": Decimal("0"),
            "files": set(),
            "notes": [],
        }
    )
    for record in cash_records:
        note_upper = record.note.upper()
        is_dividend = "DIVIDEND" in note_upper or "DIVIDENDS" in note_upper or "股息" in record.note
        is_withholding = "WITHHOLDING TAX" in note_upper or "预扣" in record.note or "預扣" in record.note
        if not is_dividend and not is_withholding:
            continue
        symbol = extract_symbol_from_dividend_note(record.note)
        key = (record.date, symbol, record.currency)
        if is_dividend and record.amount > 0:
            grouped[key]["gross"] = grouped[key]["gross"] + record.amount
        if is_withholding and record.amount < 0:
            grouped[key]["withheld"] = grouped[key]["withheld"] + abs(record.amount)
        grouped[key]["files"].add(record.statement_file)
        grouped[key]["notes"].append(record.note)

    dividends: list[DividendRecord] = []
    for (record_date, symbol, currency), data in sorted(grouped.items()):
        gross = data["gross"]
        withheld = data["withheld"]
        if gross <= 0 and withheld <= 0:
            continue
        region = infer_region("US" if currency == "USD" else "SEHK", symbol, currency)
        dividends.append(
            DividendRecord(
                date=record_date,
                symbol=symbol,
                region=region,
                currency=currency,
                gross_dividend=gross,
                foreign_tax_withheld=withheld,
                source_statement_files=sorted(data["files"]),
                raw_notes=list(data["notes"]),
            )
        )
    return dividends


def parse_opening_positions(lines: list[str], statement_file: str, statement_month: str) -> list[dict[str, object]]:
    positions: list[dict[str, object]] = []
    in_section = False
    for line in lines:
        if "期期初初概概覽覽--股股票票和和股股票票期期權權" in line:
            in_section = True
            continue
        if in_section and (line == "交交易易" or line.startswith("製備日期")):
            break
        if not in_section:
            continue
        tokens = line.split()
        currency_index = next((idx for idx, token in enumerate(tokens) if token in CURRENCY_CODES), None)
        if currency_index is None or currency_index < 2 or len(tokens) < currency_index + 4:
            continue
        raw_code = tokens[0]
        symbol = normalize_symbol(raw_code)
        currency = tokens[currency_index]
        quantity = parse_decimal(tokens[currency_index + 1])
        price = parse_decimal(tokens[currency_index + 2])
        market = tokens[currency_index - 1] if currency_index >= 2 else ""
        if quantity == 0:
            continue
        positions.append(
            {
                "statement_file": statement_file,
                "statement_month": statement_month,
                "symbol": symbol,
                "raw_code": raw_code,
                "market": market,
                "region": infer_region(market, symbol, currency),
                "currency": currency,
                "quantity": quantity,
                "statement_price": price,
                "instrument_type": classify_instrument(symbol, line),
            }
        )
    return positions


def parse_statement(pdf_path: Path) -> tuple[list[TradeRecord], list[CashActivityRecord], list[DividendRecord], list[dict[str, object]]]:
    lines = extract_pdf_lines(pdf_path)
    statement_month = parse_statement_month(lines, pdf_path)
    trades = parse_trades(lines, pdf_path.name, statement_month)
    cash_records = parse_cash_activities(lines, pdf_path.name, statement_month)
    dividends = parse_dividends(cash_records)
    opening_positions = parse_opening_positions(lines, pdf_path.name, statement_month)
    return trades, cash_records, dividends, opening_positions


def infer_csv_market_currency(path: Path) -> tuple[str, str, str]:
    name = path.name
    if "港股" in name:
        return "SEHK", "HKD", "中国香港"
    return "US", "USD", "美国"


def parse_datetime_date(value: str | None) -> date | None:
    if not value:
        return None
    match = re.match(r"^(20\d{2}/\d{2}/\d{2})", value.strip())
    if not match:
        return None
    return parse_date(match.group(1))


def parse_csv_statement(path: Path) -> tuple[list[TradeRecord], list[CashActivityRecord], list[DividendRecord], list[dict[str, object]]]:
    market, currency, region = infer_csv_market_currency(path)
    trades: list[TradeRecord] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = (row.get("代码") or "").strip()
            direction = (row.get("方向") or "").strip()
            if not code or direction not in {"买入", "卖出"}:
                continue
            filled_quantity = parse_decimal(row.get("成交数量"))
            gross_amount = parse_decimal(row.get("成交金额"))
            unit_price = parse_decimal(row.get("成交价格") or row.get("订单价格"))
            fees_total = parse_decimal(row.get("合计费用"))
            trade_date = parse_datetime_date(row.get("成交时间") or row.get("下单时间"))
            if filled_quantity <= 0 or gross_amount <= 0 or unit_price <= 0 or trade_date is None:
                continue

            side = "BUY" if direction == "买入" else "SELL"
            symbol = normalize_symbol(code)
            instrument_type = classify_instrument(symbol, code)
            if instrument_type == "UNKNOWN":
                instrument_type = classify_instrument(symbol, row.get("名称") or "")

            net_cash_change = gross_amount + fees_total if side == "SELL" else -(gross_amount + fees_total)
            trades.append(
                TradeRecord(
                    statement_file=path.name,
                    statement_month=trade_date.strftime("%Y-%m"),
                    trade_date=trade_date,
                    settlement_date=trade_date,
                    side=side,
                    symbol=symbol,
                    raw_code=code,
                    market=market,
                    region=region,
                    currency=currency,
                    quantity=filled_quantity,
                    unit_price=unit_price,
                    gross_amount=gross_amount,
                    net_cash_change=net_cash_change,
                    fees_total=fees_total,
                    fees_breakdown={
                        "佣金": parse_decimal(row.get("佣金")),
                        "平台使用费": parse_decimal(row.get("平台使用费")),
                        "证监会规费": parse_decimal(row.get("证监会规费") or row.get("证监会征费")),
                        "交易活动费": parse_decimal(row.get("交易活动费") or row.get("交易费")),
                        "期权监管费": parse_decimal(row.get("期权监管费")),
                        "期权清算费": parse_decimal(row.get("期权清算费")),
                        "期权交收费": parse_decimal(row.get("期权交收费")),
                        "交收费": parse_decimal(row.get("交收费")),
                        "印花税": parse_decimal(row.get("印花税")),
                        "财汇局征费": parse_decimal(row.get("财汇局征费")),
                    },
                    instrument_type=instrument_type,
                    raw_header=f"{direction} {code} {row.get('名称') or ''}",
                )
            )
    return trades, [], [], []


def parse_any_statement(path: Path) -> tuple[list[TradeRecord], list[CashActivityRecord], list[DividendRecord], list[dict[str, object]]]:
    if path.suffix.lower() == ".csv":
        return parse_csv_statement(path)
    return parse_statement(path)


def parse_annual_tax_workbook(path: Path) -> tuple[list[TradeRecord], dict[tuple[str, str, str], Decimal]]:
    trades: list[TradeRecord] = []
    holdings: dict[tuple[str, str, str], Decimal] = {}

    trade_df = pd.read_excel(path, sheet_name="证券-交易流水")
    holding_df = pd.read_excel(path, sheet_name="证券-持仓总览")

    for _, row in trade_df.iterrows():
        symbol = str(row.get("代码名称") or "").strip()
        direction = str(row.get("方向") or "").strip()
        market = str(row.get("交易所/市场") or "").strip()
        currency = str(row.get("币种") or "").strip().upper()
        if not symbol or not direction or not market or not currency:
            continue
        if "买入" not in direction and "卖出" not in direction:
            continue

        quantity_raw = Decimal(str(row.get("数量/面值") or "0"))
        quantity = abs(quantity_raw)
        if quantity <= 0:
            continue

        gross_amount = abs(Decimal(str(row.get("成交金额") or "0")))
        fees_total = abs(Decimal(str(row.get("总费用") or "0")))
        trade_time = str(row.get("成交时间") or "").strip()
        trade_date = None
        if trade_time:
            trade_date = pd.to_datetime(trade_time).date()
        if trade_date is None:
            continue

        side = "BUY" if "买入" in direction else "SELL"
        region = infer_region(market, symbol, currency)
        instrument_type = classify_instrument(symbol, symbol)
        net_cash_change = gross_amount + fees_total if side == "SELL" else -(gross_amount + fees_total)
        trades.append(
            TradeRecord(
                statement_file=path.name,
                statement_month=trade_date.strftime("%Y-%m"),
                trade_date=trade_date,
                settlement_date=None,
                side=side,
                symbol=symbol,
                raw_code=symbol,
                market=market,
                region=region,
                currency=currency,
                quantity=quantity,
                unit_price=abs(Decimal(str(row.get("价格") or "0"))),
                gross_amount=gross_amount,
                net_cash_change=net_cash_change,
                fees_total=fees_total,
                fees_breakdown={},
                instrument_type=instrument_type,
                raw_header=f"{direction} {symbol}",
            )
        )

    for _, row in holding_df.iterrows():
        symbol = str(row.get("代码名称") or "").strip()
        market = str(row.get("交易所/市场") or "").strip()
        currency = str(row.get("币种") or "").strip().upper()
        if not symbol or not market or not currency:
            continue
        qty = Decimal(str(row.get("数量/面值") or "0"))
        if qty <= 0:
            continue
        region = infer_region(market, symbol, currency)
        holdings[(symbol, region, currency)] = qty

    return trades, holdings
