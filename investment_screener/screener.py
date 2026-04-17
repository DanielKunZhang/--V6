#!/usr/bin/env python3
"""
投资标的筛选系统 v2.0 — 指数成分股版
架构：三层筛选
  Layer 1 (自动) : 动态拉取指数成分股 → 量化代理指标过滤 → 候选标的
  Layer 2 (人工) : Claude /初筛 + /估值 → 写入 watchlist.json
  Layer 3 (自动) : 每周价格监控，MoS≥40% 触发邮件预警

机会成本逻辑：
  候选标的需在 PE_TTM + 质量 + 增长 + 行业可比 四维复合口径上
  显著优于现有持仓，才值得进入替换研究池

用法：
  python3 screener.py --watchlist          # 持仓价格监控（每周）
  python3 screener.py --universe           # 全指数成分股扫描（每季度）
  python3 screener.py --all                # 两者都运行
  python3 screener.py --test-email         # 测试邮件
  python3 screener.py --no-email           # 不发邮件（调试）
  python3 screener.py --list-index US      # 预览指数成分股列表
"""

import json
import logging
import argparse
import smtplib
import time
import os
import sys
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from math import ceil, inf, isfinite
from pathlib import Path
from statistics import median

from env_utils import load_local_env

load_local_env()

try:
    import urllib.request
    import html.parser
    URLLIB_AVAILABLE = True
except ImportError:
    URLLIB_AVAILABLE = False

# ─────────────────────────────────────────────
# SECTION 1: CONFIG
# ─────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.json"
FUTU_HOST = os.getenv("FUTU_HOST", "127.0.0.1")
FUTU_PORT = int(os.getenv("FUTU_PORT", "11111"))
USD_HKD = 7.8
USD_CNY = 7.2
FUTU_FILTER_MAX_CALLS = 9
FUTU_FILTER_WINDOW_SECONDS = 30
_FUTU_FILTER_CALL_TIMES = []

DEFAULT_CONFIG = {
    "email": {
        "enabled": False,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "use_tls": True,
        "sender": "",
        "password": "",
        "recipients": [],
        "subject_prefix": "[投资预警]"
    },
    "screener": {
        "watchlist_alert_mos_threshold": 0.40,
        "universe_min_score": 6,
        "request_delay_seconds": 3,
        "opportunity_cost_discount": 0.25,
        "opportunity_cost_ev_fcf_discount": 0.25
    },
    "paths": {
        "watchlist": str(SCRIPT_DIR / "watchlist.json"),
        "holdings": str(SCRIPT_DIR / "holdings.json"),
        "reports_dir": str(SCRIPT_DIR / "reports/"),
        "log_file": str(SCRIPT_DIR / "screener.log")
    },
    "notifications": {
        "send_on_no_alerts": False
    }
}


def load_config(path=DEFAULT_CONFIG_PATH):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if Path(path).exists():
        with open(path) as f:
            user_cfg = json.load(f)
        for section, values in user_cfg.items():
            if section.startswith("_"):
                continue
            if isinstance(values, dict) and section in cfg:
                for k, v in values.items():
                    if not k.startswith("_"):
                        cfg[section][k] = v
            else:
                cfg[section] = values
    return cfg


def setup_logging(log_file):
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


# ─────────────────────────────────────────────
# SECTION 2: INDEX CONSTITUENT FETCHING
# ─────────────────────────────────────────────

def _make_ssl_context():
    """Create SSL context that works on macOS (tries certifi, then system, then unverified)."""
    import ssl
    # Try certifi first
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    # Try macOS system cert bundle
    import platform
    if platform.system() == "Darwin":
        for path in [
            "/etc/ssl/cert.pem",
            "/usr/local/etc/openssl/cert.pem",
            "/opt/homebrew/etc/openssl@3/cert.pem",
        ]:
            if os.path.exists(path):
                try:
                    return ssl.create_default_context(cafile=path)
                except Exception:
                    continue
    # Last resort: unverified (acceptable for public index data)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def format_money(value, currency: str | None = None, decimals: int = 2) -> str:
    if value is None or value == "N/A":
        return "N/A"
    try:
        number = float(value)
    except Exception:
        return str(value)
    unit = currency or ""
    return f"{number:.{decimals}f} {unit}".strip()


def sanitize_numeric(value):
    try:
        number = float(value)
    except Exception:
        return None
    return number if isfinite(number) else None


def fetch_sp500() -> list[str]:
    """Fetch S&P 500 constituents. Tries pandas→GitHub CSV→hardcoded."""
    import urllib.request, ssl

    ssl_ctx = _make_ssl_context()

    # Method 1: pandas.read_html with SSL context
    try:
        import pandas as pd
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_ctx))
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        with opener.open(url, timeout=20) as resp:
            html_bytes = resp.read()
        import io
        tables = pd.read_html(io.BytesIO(html_bytes), attrs={"id": "constituents"})
        if tables:
            symbols = tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()
            if len(symbols) > 400:
                logging.info(f"S&P 500 (pandas/Wikipedia): {len(symbols)} 只成分股")
                return symbols
    except Exception as e:
        logging.warning(f"pandas read_html S&P 500 失败: {e}")

    # Method 2: GitHub CSV
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
            content = resp.read().decode("utf-8")
        lines = content.strip().split("\n")[1:]
        symbols = [l.split(",")[0].strip().replace(".", "-") for l in lines if l.strip()]
        if len(symbols) > 400:
            logging.info(f"S&P 500 (GitHub CSV): {len(symbols)} 只")
            return symbols
    except Exception as e2:
        logging.warning(f"GitHub S&P 500 CSV 失败: {e2}")

    logging.info("使用 S&P 500 硬编码列表（top 141）")
    return _sp500_hardcoded()


def _sp500_hardcoded() -> list[str]:
    """Hardcoded top ~300 S&P 500 by market cap as last resort (network unavailable)."""
    return [
        # Mega cap
        "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","BRK-B","LLY","AVGO",
        "TSLA","WMT","JPM","V","UNH","XOM","MA","ORCL","COST","HD",
        # Large cap tech & growth
        "PG","JNJ","ABBV","BAC","MRK","NFLX","CVX","KO","AMD","CRM",
        "PEP","ADBE","ACN","TMO","MCD","CSCO","ABT","GE","DHR","WFC",
        "AXP","QCOM","TXN","MS","IBM","INTU","CAT","NOW","AMGN","SPGI",
        # Healthcare & pharma
        "RTX","ISRG","BKNG","UBER","GS","LOW","T","VRTX","LMT","PFE",
        "SYK","UNP","ELV","MMC","DE","MDT","REGN","SCHW","C","ADI",
        "BLK","CB","AMAT","GILD","TJX","PLD","MO","SBUX","ZTS","ETN",
        # Industrial & financial
        "BSX","NKE","DUK","SO","ICE","CME","PNC","KLAC","HCA","APH",
        "SHW","USB","MCO","ITW","CL","FI","TT","MSI","MDLZ","EW",
        "NOC","MMM","PANW","SNPS","AON","HUM","PSA","NSC","FCX","ROP",
        "AIG","LRCX","EMR","GD","MET","AJG","CARR","CDNS","TDG","AFL",
        "WM","ECL","CSX","OKE","ORLY","PCAR","CTAS","PSX","AEP","WELL",
        "NXPI","D","PAYX","CCI","SRE","ODFL","CMG","PDD","BABA","JD",
        # Mid-large cap additions
        "TCOM","TROW","RF","FITB","KEY","CFG","HBAN","MTB","ZION","CMA",
        "STT","BK","NTRS","FRC","SIVB","ALLY","SYF","COF","DFS","AMP",
        "LNC","GL","PRU","MFC","SFM","EXC","ED","XEL","PPL","CMS",
        "FE","EIX","WEC","AWK","ES","CNP","NI","OGE","POR","SR",
        "WAT","IDXX","BIO","MTD","PKI","HOLX","TECH","ALGN","ABMD","PODD",
        "DXCM","NTRA","VEEV","DOCS","HLTH","ACAD","PCVX","MRNA","BNTX","REGN",
        "HUM","MOH","CNC","WCG","CVS","RAD","WBA","CAH","MCK","ABC",
        "HSIC","PDCO","OMI","PRGO","CTLT","IQV","CRL","LH","DGX","SCPG",
        "GPN","FISV","FIS","JKHY","EPAM","CTSH","INFY","WIT","GLOB","EXLS",
        "CACI","SAIC","LDOS","BAH","CSGP","ANSS","CDNS","NUAN","NLOK","GEN",
        "NTAP","HPQ","HPE","DELL","SMCI","WDC","STX","ANET","JNPR","ZBRA",
        "TER","MKSI","ENTG","ONTO","FORM","ICHR","ACLS","MTSI","AEHR","AMBA",
    ]


def fetch_csi300() -> list[str]:
    """Fetch 沪深300 constituents. Returns .SS/.SZ suffixed symbols."""
    # Try akshare if available
    try:
        import akshare as ak
        df = ak.index_stock_cons(symbol="000300")
        symbols = []
        for code in df["品种代码"].tolist():
            if code.startswith("6"):
                symbols.append(code + ".SS")
            else:
                symbols.append(code + ".SZ")
        logging.info(f"沪深300 (akshare): {len(symbols)} 只")
        return symbols
    except Exception:
        pass

    # Fallback: hardcoded 沪深300 top constituents
    logging.info("akshare 不可用，使用沪深300硬编码列表")
    return _csi300_hardcoded()




def _csi300_hardcoded() -> list[str]:
    """Top ~80 沪深300 constituents by weight."""
    return [
        "600036.SS","601318.SS","600519.SS","601166.SS","600016.SS",
        "601288.SS","601398.SS","601939.SS","600030.SS","000858.SZ",
        "603288.SS","002304.SZ","600276.SS","000333.SZ","300750.SZ",
        "601601.SS","600887.SS","000651.SZ","600900.SS","002594.SZ",
        "601088.SS","600028.SS","601628.SS","600019.SS","601857.SS",
        "601766.SS","600585.SS","601800.SS","601668.SS","601186.SS",
        "600104.SS","600309.SS","000002.SZ","601688.SS","002230.SZ",
        "600703.SS","000063.SZ","300015.SZ","002714.SZ","600763.SS",
        "603259.SS","000538.SZ","002475.SZ","300059.SZ","688981.SS",
        "600050.SS","601728.SS","002466.SZ","601899.SS","002049.SZ",
        "000776.SZ","600886.SS","000568.SZ","002238.SZ","000895.SZ",
        "601985.SS","600111.SS","603501.SS","688036.SS","002007.SZ",
    ]


def fetch_hk_constituents() -> list[str]:
    """HSI + HSCEI + 恒生科技指数 主要成分股。"""
    # Try Wikipedia HSI
    hsi_hardcoded = [
        # 恒生指数 HSI 82只（2024年）
        "0700.HK","9988.HK","0005.HK","0939.HK","1299.HK",
        "2318.HK","0941.HK","3690.HK","1810.HK","9618.HK",
        "0388.HK","2628.HK","0003.HK","0006.HK","0012.HK",
        "0016.HK","0017.HK","0027.HK","0066.HK","0083.HK",
        "0101.HK","0151.HK","0175.HK","0267.HK","0288.HK",
        "0291.HK","0316.HK","0322.HK","0386.HK","0390.HK",
        "0669.HK","0688.HK","0762.HK","0823.HK","0857.HK",
        "0868.HK","0881.HK","0883.HK","0960.HK","0968.HK",
        "0992.HK","1044.HK","1093.HK","1109.HK","1113.HK",
        "1177.HK","1211.HK","1378.HK","1398.HK","1876.HK",
        "1928.HK","2007.HK","2020.HK","2269.HK","2313.HK",
        "2382.HK","2388.HK","2899.HK","3968.HK","3988.HK",
        "6098.HK","6690.HK","6862.HK","9888.HK","9999.HK",
        # 恒生科技 额外
        "1024.HK","2015.HK","0241.HK","3067.HK","6060.HK",
        "9961.HK","2331.HK","0268.HK","1347.HK","2518.HK",
        # 中资金融/保险
        "0998.HK","2601.HK","1339.HK","1336.HK","6030.HK",
    ]
    logging.info(f"港股: 使用硬编码 {len(hsi_hardcoded)} 只（HSI+HSCEI+恒生科技）")
    return hsi_hardcoded


def fetch_plate_constituents(ctx, ft, plate_code: str, label: str) -> list[str]:
    try:
        ret, data = ctx.get_plate_stock(plate_code)
        if ret != ft.RET_OK or data is None or data.empty:
            logging.warning(f"{label} Futu 板块拉取失败: {data}")
            return []
        codes = data["code"].astype(str).tolist()
        symbols = [futu_to_external_symbol(code) for code in codes]
        symbols = [symbol for symbol in symbols if symbol]
        logging.info(f"{label} (Futu {plate_code}): {len(symbols)} 只")
        return symbols
    except Exception as e:
        logging.warning(f"{label} Futu 板块异常: {e}")
        return []


def fetch_us_constituents_futu(ctx, ft) -> list[str]:
    return fetch_plate_constituents(ctx, ft, "US..SPX", "S&P 500")


def fetch_csi300_futu(ctx, ft) -> list[str]:
    return fetch_plate_constituents(ctx, ft, "SH.000300", "沪深300")


def fetch_hk_constituents_futu(ctx, ft) -> list[str]:
    labels = [
        ("HK.800000", "恒生指数"),
        ("HK.800100", "恒生国企指数"),
        ("HK.800700", "恒生科技指数"),
    ]
    merged = []
    for plate_code, label in labels:
        merged.extend(fetch_plate_constituents(ctx, ft, plate_code, label))
    deduped = list(dict.fromkeys(merged))
    if deduped:
        logging.info(f"港股 (Futu HSI+HSCEI+HSTECH 去重): {len(deduped)} 只")
    return deduped


def get_index_universe(markets: list[str], ft=None, ctx=None) -> dict[str, list[str]]:
    """
    返回各市场的指数成分股列表。
    markets: ['US', 'HK', 'A'] 的子集
    """
    universe = {}
    if "US" in markets:
        logging.info("拉取 S&P 500 成分股...")
        universe["US"] = fetch_us_constituents_futu(ctx, ft) if ft and ctx else []
        if not universe["US"]:
            universe["US"] = fetch_sp500()
    if "HK" in markets:
        logging.info("拉取港股成分股（HSI+HSCEI+恒生科技）...")
        universe["HK"] = fetch_hk_constituents_futu(ctx, ft) if ft and ctx else []
        if not universe["HK"]:
            universe["HK"] = fetch_hk_constituents()
    if "A" in markets:
        logging.info("拉取沪深300成分股...")
        universe["A"] = fetch_csi300_futu(ctx, ft) if ft and ctx else []
        if not universe["A"]:
            universe["A"] = fetch_csi300()
    return universe


# ─────────────────────────────────────────────
# SECTION 3: DATA FETCHING
# ─────────────────────────────────────────────

def fetch_stock_data(symbol: str, delay: int = 3) -> dict:
    return {
        "symbol": symbol,
        "name": symbol,
        "currency": "USD",
        "price": None,
        "market_cap": None,
        "error": "deprecated_fetch_stock_data_use_futu_scan",
    }


def is_network_or_source_error(error: str | None) -> bool:
    text = (error or "").lower()
    if not text:
        return False
    markers = [
        "rate_limited_or_no_data",
        "could not resolve host",
        "guce.yahoo.com",
        "timed out",
        "timeout",
        "ssl",
        "certificate verify failed",
        "too many requests",
        "429",
        "curl:",
        "connection",
    ]
    return any(marker in text for marker in markers)


def get_futu_module():
    try:
        import futu as ft
        return ft
    except Exception as e:
        logging.error(f"导入 futu 失败: {e}")
        return None


def open_futu_quote_context():
    ft = get_futu_module()
    if ft is None:
        return None, None
    try:
        return ft, ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    except Exception as e:
        logging.error(f"连接 Futu OpenD 失败: {e}")
        return ft, None


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def market_to_futu_enums(ft, market: str) -> list:
    mapping = {
        "US": [ft.Market.US],
        "HK": [ft.Market.HK],
        "A": [ft.Market.SH, ft.Market.SZ],
    }
    return mapping.get(market, [])


def get_futu_stock_field(ft, *names):
    for name in names:
        field = getattr(ft.StockField, name, None)
        if field is not None:
            return field
    raise AttributeError(f"futu.StockField missing all candidates: {', '.join(names)}")


def market_from_futu_code(ft, futu_code: str):
    prefix = (futu_code or "").split(".", 1)[0].upper()
    mapping = {
        "US": ft.Market.US,
        "HK": ft.Market.HK,
        "SH": ft.Market.SH,
        "SZ": ft.Market.SZ,
    }
    return mapping.get(prefix)


def market_currency(market: str) -> str:
    return {"US": "USD", "HK": "HKD", "A": "CNY"}.get(market, "USD")


def usd_threshold_in_local(market: str, usd_value: float) -> float:
    if market == "HK":
        return usd_value * USD_HKD
    if market == "A":
        return usd_value * USD_CNY
    return usd_value


def futu_to_external_symbol(futu_code: str) -> str:
    if not futu_code:
        return futu_code
    futu_code = futu_code.upper()
    if futu_code.startswith("US."):
        return futu_code.split(".", 1)[1]
    if futu_code.startswith("HK."):
        raw_code = futu_code.split(".", 1)[1]
        trimmed = raw_code.lstrip("0") or "0"
        return f"{trimmed.zfill(4)}.HK"
    if futu_code.startswith("SH."):
        return f"{futu_code.split('.', 1)[1]}.SS"
    if futu_code.startswith("SZ."):
        return f"{futu_code.split('.', 1)[1]}.SZ"
    return futu_code


def build_symbol_maps(symbols: list[str], market: str) -> tuple[dict[str, str], dict[str, str]]:
    symbol_to_futu, futu_to_symbol = {}, {}
    exchange = "US" if market == "US" else ("HK" if market == "HK" else None)
    for symbol in symbols:
        futu_code = normalize_symbol_for_futu(symbol, exchange=exchange)
        if futu_code:
            symbol_to_futu[symbol] = futu_code
            futu_to_symbol[futu_code] = symbol
    return symbol_to_futu, futu_to_symbol


def preflight_universe_data_source(ctx) -> tuple[bool, str | None, list[dict]]:
    ft = get_futu_module()
    if ctx is None or ft is None:
        return False, "futu_context_unavailable", []
    sample_codes = ["US.AAPL", "US.MSFT", "HK.00700"]
    attempts = []
    try:
        ret, data = ctx.get_market_snapshot(sample_codes)
        if ret != ft.RET_OK or data is None or data.empty:
            detail = str(data) if data is not None else "empty response"
            for code in sample_codes:
                attempts.append({"symbol": code, "ok": False, "error": detail})
            return False, f"futu_precheck_failed | {detail}"[:180], attempts
        returned = set(data["code"].astype(str)) if "code" in data.columns else set()
        for code in sample_codes:
            attempts.append({"symbol": code, "ok": (not returned) or (code in returned), "error": None if ((not returned) or (code in returned)) else "missing_from_snapshot"})
        success_count = sum(1 for item in attempts if item["ok"])
        return success_count >= 1, None if success_count >= 1 else "futu_precheck_failed", attempts
    except Exception as e:
        detail = str(e)[:180]
        for code in sample_codes:
            attempts.append({"symbol": code, "ok": False, "error": detail})
        return False, f"futu_precheck_failed | {detail}"[:180], attempts


def normalize_symbol_for_futu(symbol: str, exchange: str | None = None) -> str | None:
    symbol = (symbol or "").strip().upper()
    exchange = (exchange or "").strip().upper()
    if not symbol:
        return None
    if "." in symbol:
        left, right = symbol.split(".", 1)
        if left in {"US", "HK", "SH", "SZ"}:
            return symbol
        if right == "HK":
            return f"HK.{left.zfill(5)}"
        if right == "SS":
            return f"SH.{left}"
        if right == "SZ":
            return f"SZ.{left}"
    if exchange in {"NASDAQ", "NYSE", "AMEX", "US"}:
        symbol = symbol.replace("-", ".")
        return f"US.{symbol}"
    if exchange in {"HK", "SEHK"}:
        return f"HK.{symbol.zfill(5)}"
    if exchange in {"SH", "SSE", "SS"}:
        return f"SH.{symbol}"
    if exchange in {"SZ", "SZSE"}:
        return f"SZ.{symbol}"
    if symbol.isalpha():
        return f"US.{symbol}"
    return None


def get_current_price_futu(symbol: str, exchange: str | None = None) -> float | None:
    futu_code = normalize_symbol_for_futu(symbol, exchange)
    if not futu_code:
        return None
    try:
        from futu import OpenQuoteContext, RET_OK, SubType
    except Exception:
        return None
    ctx = None
    try:
        ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
        ret, _ = ctx.subscribe([futu_code], [SubType.QUOTE], subscribe_push=False)
        if ret != RET_OK:
            return None
        ret, data = ctx.get_stock_quote([futu_code])
        if ret != RET_OK or data is None or data.empty:
            return None
        price = data.iloc[0].get("last_price")
        if price is None:
            return None
        return float(price)
    except Exception:
        return None
    finally:
        if ctx:
            try:
                ctx.close()
            except Exception:
                pass


def get_current_price(symbol: str, delay: int = 2, exchange: str | None = None) -> float | None:
    return get_current_price_futu(symbol, exchange=exchange)


# ─────────────────────────────────────────────
# SECTION 4: QUANTITATIVE FILTER
# ─────────────────────────────────────────────

def buffett_quant_score(data: dict) -> tuple[int, list[tuple]]:
    """9-point Futu-compatible Buffett quantitative proxy filter."""
    checks = []

    def chk(name, value, cond, threshold):
        if isinstance(value, float):
            vs = f"{value:.2f}"
        elif value is None:
            vs = "N/A"
        else:
            vs = str(value)
        icon = "✅" if cond else "❌"
        checks.append((icon, name, vs, threshold))
        return int(cond)

    mc = data.get("market_cap")
    roe = data.get("roe")
    gm = data.get("gross_margin")
    debt_assets = data.get("debt_assets_rate")
    ocf_ttm = data.get("operating_cash_flow_ttm")
    pe_ttm = data.get("pe_ttm")
    rev_g = data.get("revenue_growth")
    nm = data.get("net_margin")
    roic = data.get("roic")

    score = 0
    score += chk("市值≥$20亿",  mc,    mc    is not None and mc    >= 2e9,    "≥$2B")
    score += chk("ROE≥15%",     roe,   roe   is not None and roe   >= 0.15,   "≥15%")
    score += chk("毛利率≥30%",  gm,    gm    is not None and gm    >= 0.30,   "≥30%")
    score += chk("资产负债率≤60%", debt_assets, debt_assets is not None and debt_assets <= 0.60, "≤60%")
    score += chk("经营现金流TTM>0", ocf_ttm, ocf_ttm is not None and ocf_ttm > 0, ">0")
    score += chk("PE_TTM≤25x", pe_ttm, pe_ttm is not None and pe_ttm <= 25, "≤25x")
    score += chk("营收增速≥5%", rev_g, rev_g is not None and rev_g >= 0.05,   "≥5%")
    score += chk("净利率≥10%",  nm,    nm    is not None and nm    >= 0.10,   "≥10%")
    score += chk("ROIC≥8%",     roic,  roic  is not None and roic  >= 0.08,   "≥8%")
    return score, checks


# ─────────────────────────────────────────────
# SECTION 5: OPPORTUNITY COST COMPARISON
# ─────────────────────────────────────────────

def load_holdings_metrics(cfg: dict) -> dict:
    """
    Load current holdings and compute reference valuation hurdle for comparison.
    """
    holdings_path = cfg["paths"].get("holdings", str(SCRIPT_DIR / "holdings.json"))
    if not Path(holdings_path).exists():
        return {}
    with open(holdings_path) as f:
        data = json.load(f)
    return data.get("positions", {})


def infer_market_from_symbol(symbol: str, exchange: str | None = None) -> str | None:
    exchange = (exchange or "").upper()
    symbol = (symbol or "").upper()
    if exchange in {"US", "NASDAQ", "NYSE", "AMEX"}:
        return "US"
    if exchange in {"HK", "SEHK"}:
        return "HK"
    if exchange in {"A", "SH", "SZ", "SS", "SSE", "SZSE"}:
        return "A"
    if symbol.endswith(".HK"):
        return "HK"
    if symbol.endswith(".SS") or symbol.endswith(".SZ"):
        return "A"
    if symbol.isalpha():
        return "US"
    return None


def get_holding_underlying_symbol(position_key: str, meta: dict) -> str | None:
    if meta.get("_type") in {"cash", "option"}:
        return None
    symbol = meta.get("underlying") or position_key.split("_", 1)[0]
    market = infer_market_from_symbol(symbol, meta.get("exchange"))
    futu_code = normalize_symbol_for_futu(symbol, exchange=meta.get("exchange") or market)
    return futu_to_external_symbol(futu_code) if futu_code else symbol


def load_unique_equity_holdings(cfg: dict) -> dict[str, dict]:
    positions = load_holdings_metrics(cfg)
    merged = {}
    for position_key, meta in positions.items():
        symbol = get_holding_underlying_symbol(position_key, meta)
        if not symbol:
            continue
        market = infer_market_from_symbol(symbol, meta.get("exchange"))
        if not market:
            continue
        entry = merged.setdefault(symbol, {
            "symbol": symbol,
            "company": meta.get("company", symbol),
            "exchange": meta.get("exchange", market),
            "market": market,
            "currency": meta.get("currency", market_currency(market)),
            "sector": meta.get("sector"),
            "shares": 0,
            "accounts": [],
        })
        entry["shares"] += meta.get("shares", 0) or 0
        if meta.get("account"):
            entry["accounts"].append(meta.get("account"))
    return merged


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def average(values: list[float]) -> float | None:
    cleaned = [float(v) for v in values if isinstance(v, (int, float))]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def scale_up_score(value, floor: float, ceiling: float) -> float:
    if value is None:
        return 0.0
    if ceiling <= floor:
        return 0.0
    return clamp((float(value) - floor) / (ceiling - floor))


def scale_down_score(value, floor: float, ceiling: float) -> float:
    if value is None:
        return 0.0
    if ceiling <= floor:
        return 0.0
    return clamp((ceiling - float(value)) / (ceiling - floor))


def fetch_owner_plate_industry_map(ctx, ft, futu_codes: list[str]) -> dict[str, dict]:
    result = {}
    for batch in chunked(futu_codes, 200):
        ret, data = ctx.get_owner_plate(batch)
        if ret != ft.RET_OK or data is None or data.empty:
            continue
        for code, group in data.groupby("code"):
            industry_rows = group[group["plate_type"].astype(str).str.upper() == "INDUSTRY"]
            chosen = industry_rows.iloc[0] if not industry_rows.empty else None
            result[str(code)] = {
                "industry": None if chosen is None else chosen.get("plate_name"),
                "industry_plate_code": None if chosen is None else chosen.get("plate_code"),
                "industry_plate_type": None if chosen is None else chosen.get("plate_type"),
            }
    return result


def compute_quality_score(row: dict) -> float:
    score = 0.0
    score += 0.25 * scale_up_score(row.get("roe"), 0.12, 0.30)
    score += 0.20 * scale_up_score(row.get("gross_margin"), 0.25, 0.60)
    score += 0.15 * scale_up_score(row.get("net_margin"), 0.08, 0.25)
    score += 0.20 * scale_up_score(row.get("roic"), 0.08, 0.20)
    score += 0.10 * scale_down_score(row.get("debt_assets_rate"), 0.20, 0.70)
    score += 0.10 * (1.0 if (row.get("operating_cash_flow_ttm") or 0) > 0 else 0.0)
    return round(score * 100, 1)


def compute_growth_score(row: dict) -> float:
    return round(scale_up_score(row.get("revenue_growth"), 0.03, 0.20) * 100, 1)


def compute_absolute_value_score(row: dict) -> float:
    return round(scale_down_score(row.get("pe_ttm"), 12.0, 35.0) * 100, 1)


def build_market_opportunity_stats(rows_by_market: dict[str, list[dict]]) -> dict[str, dict]:
    stats = {}
    for market, rows in (rows_by_market or {}).items():
        market_pes = [row.get("pe_ttm") for row in rows if row.get("pe_ttm") is not None]
        market_median_pe = median(market_pes) if market_pes else None
        sector_pe = {}
        for row in rows:
            industry = row.get("industry")
            pe_ttm = row.get("pe_ttm")
            if not industry or pe_ttm is None:
                continue
            sector_pe.setdefault(industry, []).append(pe_ttm)
        stats[market] = {
            "market_median_pe": market_median_pe,
            "industry_median_pe": {industry: median(values) for industry, values in sector_pe.items() if values},
        }
    return stats


def compute_sector_value_score(row: dict, market_stats: dict[str, dict]) -> tuple[float, float | None]:
    market = row.get("market")
    industry = row.get("industry")
    pe_ttm = row.get("pe_ttm")
    if pe_ttm is None:
        return 0.0, None
    benchmark = None
    if market in market_stats:
        benchmark = market_stats[market]["industry_median_pe"].get(industry) if industry else None
        if benchmark is None:
            benchmark = market_stats[market].get("market_median_pe")
    if benchmark is None or benchmark <= 0:
        return 50.0, None
    ratio = benchmark / pe_ttm
    score = clamp(0.5 + 0.625 * (ratio - 1.0)) * 100
    return round(score, 1), round(benchmark, 1)


def compute_opportunity_score_components(row: dict, market_stats: dict[str, dict]) -> dict:
    quality_score = compute_quality_score(row)
    growth_score = compute_growth_score(row)
    absolute_value_score = compute_absolute_value_score(row)
    sector_value_score, sector_pe_median = compute_sector_value_score(row, market_stats)
    opportunity_score = round(
        0.45 * quality_score +
        0.20 * growth_score +
        0.20 * absolute_value_score +
        0.15 * sector_value_score,
        1,
    )
    return {
        "quality_score": quality_score,
        "growth_score": growth_score,
        "absolute_value_score": absolute_value_score,
        "sector_value_score": sector_value_score,
        "sector_pe_median": sector_pe_median,
        "opportunity_score": opportunity_score,
    }


def build_opportunity_hurdle(holdings_meta: dict[str, dict], reference_rows: dict[str, dict], market_stats: dict[str, dict]) -> dict:
    holdings_metrics = {}
    for symbol, meta in holdings_meta.items():
        base_row = dict(reference_rows.get(symbol, {}))
        base_row.setdefault("symbol", symbol)
        base_row.setdefault("name", meta.get("company", symbol))
        base_row.setdefault("market", meta.get("market"))
        base_row.setdefault("currency", meta.get("currency"))
        if not base_row.get("industry"):
            base_row["industry"] = meta.get("sector")
        components = compute_opportunity_score_components(base_row, market_stats)
        base_row.update(components)
        holdings_metrics[symbol] = {
            "symbol": symbol,
            "company": meta.get("company", symbol),
            "market": base_row.get("market"),
            "industry": base_row.get("industry"),
            "pe_ttm": base_row.get("pe_ttm"),
            "quality_score": base_row.get("quality_score"),
            "growth_score": base_row.get("growth_score"),
            "absolute_value_score": base_row.get("absolute_value_score"),
            "sector_value_score": base_row.get("sector_value_score"),
            "opportunity_score": base_row.get("opportunity_score"),
        }

    holdings_sorted = sorted(
        holdings_metrics.values(),
        key=lambda item: item.get("opportunity_score", inf),
    )
    valid_scores = [item["opportunity_score"] for item in holdings_sorted if item.get("opportunity_score") is not None]
    median_score = median(valid_scores) if valid_scores else 0.0
    weakest = holdings_sorted[0] if holdings_sorted else None

    market_baselines = {}
    for market in sorted({item.get("market") for item in holdings_sorted if item.get("market")}):
        market_items = [item for item in holdings_sorted if item.get("market") == market and item.get("opportunity_score") is not None]
        if not market_items:
            continue
        cohort_size = max(1, ceil(len(market_items) * 0.30))
        bottom_cohort = market_items[:cohort_size]
        market_baselines[market] = {
            "count": len(market_items),
            "median_score": median([item["opportunity_score"] for item in market_items]),
            "bottom_cohort_score": round(average([item.get("opportunity_score") for item in bottom_cohort]) or 0.0, 1),
            "bottom_cohort_quality": round(average([item.get("quality_score") for item in bottom_cohort]) or 0.0, 1),
            "bottom_cohort_growth": round(average([item.get("growth_score") for item in bottom_cohort]) or 0.0, 1),
            "bottom_cohort_pe": round(average([item.get("pe_ttm") for item in bottom_cohort if item.get("pe_ttm") and item.get("pe_ttm") > 0]) or 0.0, 1),
            "symbols": [item["symbol"] for item in bottom_cohort],
        }

    return {
        "metric_name": "Composite Opportunity Score",
        "min_value": min(valid_scores) if valid_scores else 0.0,
        "median_value": median_score,
        "holdings_metrics": holdings_metrics,
        "holdings_metrics_sorted": holdings_sorted,
        "market_baselines": market_baselines,
        "weakest_holding": weakest,
    }


def build_comparison_baseline(candidate: dict, hurdle: dict) -> dict | None:
    holdings_metrics = hurdle.get("holdings_metrics") or {}
    if not holdings_metrics:
        return None

    candidate_market = candidate.get("market")
    candidate_industry = candidate.get("industry")
    same_industry_pool = [
        item for item in holdings_metrics.values()
        if item.get("market") == candidate_market
        and candidate_industry
        and item.get("industry")
        and item.get("industry") == candidate_industry
    ]
    if same_industry_pool:
        target = min(same_industry_pool, key=lambda item: item.get("opportunity_score", inf))
        return {
            "basis": "same_industry",
            "label": f"同业持仓 {target['symbol']}",
            "symbol": target["symbol"],
            "opportunity_score": target.get("opportunity_score"),
            "quality_score": target.get("quality_score"),
            "growth_score": target.get("growth_score"),
            "pe_ttm": target.get("pe_ttm"),
            "sector_value_score": target.get("sector_value_score"),
        }

    market_baseline = (hurdle.get("market_baselines") or {}).get(candidate_market)
    if market_baseline and market_baseline.get("bottom_cohort_score") is not None:
        return {
            "basis": "market_bottom_cohort",
            "label": f"{candidate_market} 持仓底部30%均值",
            "symbol": "/".join(market_baseline.get("symbols") or []),
            "opportunity_score": market_baseline.get("bottom_cohort_score"),
            "quality_score": market_baseline.get("bottom_cohort_quality"),
            "growth_score": market_baseline.get("bottom_cohort_growth"),
            "pe_ttm": market_baseline.get("bottom_cohort_pe"),
            "sector_value_score": None,
        }

    target = hurdle.get("weakest_holding")
    if not target:
        return None
    return {
        "basis": "global_weakest",
        "label": f"全组合最弱持仓 {target['symbol']}",
        "symbol": target["symbol"],
        "opportunity_score": target.get("opportunity_score"),
        "quality_score": target.get("quality_score"),
        "growth_score": target.get("growth_score"),
        "pe_ttm": target.get("pe_ttm"),
        "sector_value_score": target.get("sector_value_score"),
    }


def flag_opportunity(candidate: dict, hurdle: dict, discount: float = 0.25) -> str | None:
    if candidate.get("symbol") in (hurdle.get("holdings_metrics") or {}):
        return None

    baseline = build_comparison_baseline(candidate, hurdle)
    if not baseline:
        return None

    candidate_score = candidate.get("opportunity_score")
    candidate_quality = candidate.get("quality_score")
    candidate_pe = candidate.get("pe_ttm")
    candidate_abs_value = candidate.get("absolute_value_score", 0)
    candidate_sector_value = candidate.get("sector_value_score", 0)
    if candidate_score is None or candidate_quality is None or candidate_pe is None:
        return None
    if candidate_pe <= 0:
        return None
    if not (candidate_abs_value >= 35 or (candidate_sector_value >= 70 and candidate_pe <= 35)):
        return None

    target_score = baseline.get("opportunity_score")
    target_quality = baseline.get("quality_score")
    target_pe = baseline.get("pe_ttm")
    if target_score is None or target_quality is None:
        return None

    score_gap = candidate_score - target_score
    median_hurdle = hurdle.get("median_value", 0.0)
    quality_ok = candidate_quality >= (target_quality - 5)
    growth_ok = candidate.get("growth_score", 0) >= (baseline.get("growth_score", 0) - 10)
    if baseline.get("basis") == "same_industry":
        valuation_ok = (
            target_pe is not None and target_pe > 0 and candidate_pe <= target_pe * (1 + min(discount, 0.10))
        ) or (
            candidate_sector_value >= (baseline.get("sector_value_score") or 0) + 12
        )
    else:
        valuation_ok = candidate_abs_value >= 45 or candidate_sector_value >= 65
    score_ok = score_gap >= 8 and candidate_score >= (median_hurdle + 5)

    if score_ok and quality_ok and growth_ok and valuation_ok:
        if baseline.get("basis") == "same_industry":
            target_pe_text = f"{target_pe:.1f}x" if isinstance(target_pe, (int, float)) else "N/A"
            value_text = f"PE {candidate_pe:.1f}x vs {target_pe_text}"
        else:
            value_text = f"PE {candidate_pe:.1f}x；行业估值分 {candidate_sector_value:.1f}"
        return f"综合机会分 {candidate_score:.1f} vs {baseline['label']} {target_score:.1f}；{value_text}"
    return None


def futu_financial_filter(ft, stock_field, filter_min=None, filter_max=None, quarter=None):
    item = ft.FinancialFilter()
    item.stock_field = stock_field
    item.is_no_filter = False
    item.filter_min = filter_min
    item.filter_max = filter_max
    item.quarter = quarter or ft.FinancialQuarter.ANNUAL
    return item


def futu_simple_filter(ft, stock_field, filter_min=None, filter_max=None):
    item = ft.SimpleFilter()
    item.stock_field = stock_field
    item.is_no_filter = False
    item.filter_min = filter_min
    item.filter_max = filter_max
    return item


def fetch_futu_filter_results(ctx, ft, market_enum, filter_obj, page_size: int = 200):
    global _FUTU_FILTER_CALL_TIMES
    begin = 0
    items = []
    while True:
        now = time.time()
        _FUTU_FILTER_CALL_TIMES = [ts for ts in _FUTU_FILTER_CALL_TIMES if now - ts < FUTU_FILTER_WINDOW_SECONDS]
        if len(_FUTU_FILTER_CALL_TIMES) >= FUTU_FILTER_MAX_CALLS:
            sleep_for = FUTU_FILTER_WINDOW_SECONDS - (now - _FUTU_FILTER_CALL_TIMES[0]) + 0.5
            if sleep_for > 0:
                logging.info(f"  条件选股触发限频保护，等待 {sleep_for:.1f}s...")
                time.sleep(sleep_for)
            now = time.time()
            _FUTU_FILTER_CALL_TIMES = [ts for ts in _FUTU_FILTER_CALL_TIMES if now - ts < FUTU_FILTER_WINDOW_SECONDS]
        _FUTU_FILTER_CALL_TIMES.append(time.time())
        ret, payload = ctx.get_stock_filter(market=market_enum, filter_list=[filter_obj], begin=begin, num=page_size)
        if ret != ft.RET_OK:
            return ret, str(payload), items
        last_page, _, ret_list = payload
        items.extend(ret_list)
        if last_page or not ret_list:
            break
        begin += len(ret_list)
    return ft.RET_OK, None, items


def fetch_futu_basic_info_map(ctx, ft, futu_codes: list[str]) -> dict[str, dict]:
    result = {}
    grouped_codes = {}
    for code in futu_codes:
        market_enum = market_from_futu_code(ft, code)
        if market_enum is None:
            continue
        grouped_codes.setdefault(market_enum, []).append(code)

    for market_enum, codes in grouped_codes.items():
        for batch in chunked(codes, 200):
            ret, data = ctx.get_stock_basicinfo(market_enum, ft.SecurityType.STOCK, batch)
            if ret != ft.RET_OK or data is None or data.empty:
                continue
            for _, row in data.iterrows():
                result[str(row.get("code"))] = {
                    "name": row.get("name"),
                    "lot_size": row.get("lot_size"),
                    "stock_type": row.get("stock_type"),
                }
    return result


def fetch_futu_snapshot_map(ctx, ft, futu_codes: list[str]) -> tuple[dict[str, dict], str | None]:
    snapshots = {}
    errors = []
    for batch in chunked(futu_codes, 200):
        ret, data = ctx.get_market_snapshot(batch)
        if ret != ft.RET_OK:
            for code in batch:
                single_ret, single_data = ctx.get_market_snapshot([code])
                if single_ret != ft.RET_OK or single_data is None or single_data.empty:
                    errors.append(f"{code}: {single_data}")
                    continue
                for _, row in single_data.iterrows():
                    code = str(row.get("code"))
                    snapshots[code] = {
                        "price": sanitize_numeric(row.get("last_price")),
                        "market_cap": sanitize_numeric(row.get("total_market_val")),
                        "pe_ttm": sanitize_numeric(row.get("pe_ttm_ratio") if row.get("pe_ttm_ratio") is not None else row.get("pe_ratio")),
                        "pb_ratio": sanitize_numeric(row.get("pb_ratio")),
                    }
            continue
        if data is None or data.empty:
            continue
        for _, row in data.iterrows():
            code = str(row.get("code"))
            snapshots[code] = {
                "price": sanitize_numeric(row.get("last_price")),
                "market_cap": sanitize_numeric(row.get("total_market_val")),
                "pe_ttm": sanitize_numeric(row.get("pe_ttm_ratio") if row.get("pe_ttm_ratio") is not None else row.get("pe_ratio")),
                "pb_ratio": sanitize_numeric(row.get("pb_ratio")),
            }
    if errors and not snapshots:
        return snapshots, " | ".join(errors)[:180]
    if errors:
        logging.warning(f"快照阶段跳过 {len(errors)} 只异常代码")
    return snapshots, None


def get_futu_universe_criteria(ft, market: str):
    return [
        {
            "field": "market_cap",
            "label": "市值≥$20亿",
            "filter": futu_simple_filter(ft, ft.StockField.MARKET_VAL, filter_min=usd_threshold_in_local(market, 2e9)),
        },
        {
            "field": "roe",
            "label": "ROE≥15%",
            "filter": futu_financial_filter(ft, ft.StockField.RETURN_ON_EQUITY_RATE, filter_min=15),
            "scale": 0.01,
        },
        {
            "field": "gross_margin",
            "label": "毛利率≥30%",
            "filter": futu_financial_filter(ft, ft.StockField.GROSS_PROFIT_RATE, filter_min=30),
            "scale": 0.01,
        },
        {
            "field": "debt_assets_rate",
            "label": "资产负债率≤60%",
            "filter": futu_financial_filter(ft, get_futu_stock_field(ft, "DEBT_ASSETS_RATE", "DEBT_ASSET_RATE"), filter_max=60),
            "scale": 0.01,
        },
        {
            "field": "operating_cash_flow_ttm",
            "label": "经营现金流TTM>0",
            "filter": futu_financial_filter(ft, ft.StockField.OPERATING_CASH_FLOW_TTM, filter_min=0.0001),
        },
        {
            "field": "pe_ttm",
            "label": "PE_TTM≤25x",
            "filter": futu_simple_filter(ft, ft.StockField.PE_TTM, filter_min=0.0001, filter_max=25),
        },
        {
            "field": "revenue_growth",
            "label": "营收增速≥5%",
            "filter": futu_financial_filter(ft, ft.StockField.SUM_OF_BUSINESS_GROWTH, filter_min=5),
            "scale": 0.01,
        },
        {
            "field": "net_margin",
            "label": "净利率≥10%",
            "filter": futu_financial_filter(ft, ft.StockField.NET_PROFIT_RATE, filter_min=10),
            "scale": 0.01,
        },
        {
            "field": "roic",
            "label": "ROIC≥8%",
            "filter": futu_financial_filter(ft, ft.StockField.ROIC, filter_min=8),
            "scale": 0.01,
        },
    ]


# ─────────────────────────────────────────────
# SECTION 6: WATCHLIST PRICE MONITORING
# ─────────────────────────────────────────────

def check_watchlist(cfg: dict) -> tuple[list, list]:
    wl_path = cfg["paths"]["watchlist"]
    threshold = cfg["screener"]["watchlist_alert_mos_threshold"]
    delay = cfg["screener"]["request_delay_seconds"]

    if not Path(wl_path).exists():
        logging.warning(f"Watchlist not found: {wl_path}")
        return [], []

    with open(wl_path) as f:
        watchlist = json.load(f)

    stocks = watchlist.get("stocks", {})
    alerts, results = [], []
    logging.info(f"监控 {len(stocks)} 只持仓标的...")

    for symbol, meta in stocks.items():
        v_adj = meta.get("v_base_geo_adjusted") or meta.get("v_base")
        if not v_adj:
            continue
        alert_price = round(v_adj * (1 - threshold), 2)
        price = get_current_price(symbol, delay=delay, exchange=meta.get("exchange"))

        entry = {
            "symbol": symbol,
            "company": meta.get("company", symbol),
            "currency": meta.get("currency", "USD"),
            "v_base": meta.get("v_base"),
            "v_base_geo_adjusted": v_adj,
            "floor": meta.get("floor"),
            "ceiling": meta.get("ceiling"),
            "alert_threshold_pct": threshold * 100,
            "alert_price": alert_price,
            "current_price": price,
            "mos_pct": None,
            "last_analysis_date": meta.get("last_analysis_date"),
            "next_earnings": meta.get("next_earnings"),
            "notes": meta.get("notes", ""),
            "triggered": False
        }
        if price is None:
            entry["current_price"] = "N/A"
            logging.warning(f"  {symbol}: 无法获取价格")
        else:
            mos = (v_adj - price) / v_adj
            entry["mos_pct"] = round(mos * 100, 1)
            entry["triggered"] = price <= alert_price
            status = "🔔 触发预警" if entry["triggered"] else "  正常"
            logging.info(f"  {symbol}: ${price:.2f} | 预警价${alert_price} | MoS={mos*100:.1f}% {status}")
        results.append(entry)
        if entry["triggered"]:
            alerts.append(entry)

    return alerts, results


# ─────────────────────────────────────────────
# SECTION 7: UNIVERSE SCAN (INDEX-BASED)
# ─────────────────────────────────────────────

def scan_universe(cfg: dict, markets: list[str] = None) -> tuple[dict, dict, dict]:
    """
    Fetch index constituents and run quantitative filter.
    Returns (candidates_by_market, all_results_by_market).
    """
    if markets is None:
        markets = ["US", "HK", "A"]
    min_score = cfg["screener"]["universe_min_score"]
    oc_discount = cfg["screener"].get(
        "opportunity_cost_discount",
        cfg["screener"].get("opportunity_cost_ev_fcf_discount", 0.25),
    )

    ft, ctx = open_futu_quote_context()
    if ctx is None or ft is None:
        logging.error("Universe 无法连接 Futu OpenD，跳过扫描。")
        universe = get_index_universe(markets)
        candidates = {market: [] for market in universe}
        all_results = {
            market: [{"symbol": symbol, "error": "futu_context_unavailable", "score": 0} for symbol in symbols]
            for market, symbols in universe.items()
        }
        return candidates, all_results, {"metric_name": "Composite Opportunity Score", "holdings_metrics": {}, "min_value": 0.0}

    # Get index constituents
    universe = get_index_universe(markets, ft=ft, ctx=ctx)

    data_source_ok, precheck_error, precheck_attempts = preflight_universe_data_source(ctx)
    if not data_source_ok:
        logging.error("Universe 数据源预检失败，跳过全量扫描。")
        for item in precheck_attempts:
            logging.error(f"  预检 {item['symbol']}: {item.get('error') or 'OK'}")
        candidates = {market: [] for market in universe}
        all_results = {
            market: [{"symbol": symbol, "error": precheck_error, "score": 0} for symbol in symbols]
            for market, symbols in universe.items()
        }
        try:
            ctx.close()
        except Exception:
            pass
        return candidates, all_results, {"metric_name": "Composite Opportunity Score", "holdings_metrics": {}, "min_value": 0.0}

    holdings_meta = load_unique_equity_holdings(cfg)
    holdings_by_market = {}
    for symbol, meta in holdings_meta.items():
        holdings_by_market.setdefault(meta["market"], []).append(symbol)

    total = sum(len(v) for v in universe.values())
    logging.info(f"\n扫描 {total} 只指数成分股（Futu API 条件选股 + 快照）")

    candidates, all_results = {}, {}
    reference_rows = {}
    tracked_rows_by_market = {}
    try:
        for market, symbols in universe.items():
            logging.info(f"\n── {market} ({len(symbols)} 只) ──")
            market_enums = market_to_futu_enums(ft, market)
            extra_symbols = [symbol for symbol in holdings_by_market.get(market, []) if symbol not in symbols]
            tracked_symbols = list(dict.fromkeys(symbols + extra_symbols))
            _, futu_to_symbol = build_symbol_maps(tracked_symbols, market)
            futu_codes = list(futu_to_symbol.keys())
            criteria = get_futu_universe_criteria(ft, market)

            rows = {
                symbol: {
                    "symbol": symbol,
                    "name": symbol,
                    "market": market,
                    "currency": market_currency(market),
                    "price": None,
                    "market_cap": None,
                    "pe_ttm": None,
                    "roe": None,
                    "gross_margin": None,
                    "net_margin": None,
                    "revenue_growth": None,
                    "debt_assets_rate": None,
                    "operating_cash_flow_ttm": None,
                    "roic": None,
                    "score": 0,
                    "score_max": 9,
                    "checks": [],
                    "passed": False,
                    "industry": None,
                    "opportunity_flag": None,
                }
                for symbol in tracked_symbols
            }

            basic_info_map = fetch_futu_basic_info_map(ctx, ft, futu_codes)
            for code, info in basic_info_map.items():
                symbol = futu_to_symbol.get(code)
                if symbol:
                    rows[symbol]["name"] = (info.get("name") or symbol)[:40]

            snapshot_map, snapshot_error = fetch_futu_snapshot_map(ctx, ft, futu_codes)
            if snapshot_error:
                logging.error(f"  {market}: 快照拉取失败 {snapshot_error}")
                candidates[market] = []
                all_results[market] = [{"symbol": symbol, "error": snapshot_error[:120], "score": 0} for symbol in symbols]
                continue
            for code, snap in snapshot_map.items():
                symbol = futu_to_symbol.get(code)
                if symbol:
                    rows[symbol]["price"] = snap.get("price")
                    rows[symbol]["market_cap"] = snap.get("market_cap")
                    if snap.get("pe_ttm") is not None:
                        rows[symbol]["pe_ttm"] = float(snap.get("pe_ttm"))

            industry_map = fetch_owner_plate_industry_map(ctx, ft, futu_codes)
            for code, info in industry_map.items():
                symbol = futu_to_symbol.get(code)
                if symbol:
                    rows[symbol]["industry"] = info.get("industry")
            for symbol in tracked_symbols:
                if not rows[symbol].get("industry") and symbol in holdings_meta:
                    rows[symbol]["industry"] = holdings_meta[symbol].get("sector")

            for criterion in criteria:
                matched_values = {}
                errors = []
                for market_enum in market_enums:
                    ret, err, items = fetch_futu_filter_results(ctx, ft, market_enum, criterion["filter"])
                    if ret != ft.RET_OK:
                        errors.append(str(err))
                        continue
                    for item in items:
                        matched_values[item.stock_code] = item[criterion["filter"]]
                if errors and not matched_values:
                    logging.error(f"  {market}: 条件 {criterion['label']} 拉取失败: {' | '.join(errors)[:180]}")
                    continue
                matched = 0
                for stock_code, value in matched_values.items():
                    symbol = futu_to_symbol.get(stock_code)
                    if symbol is None:
                        continue
                    if value is not None:
                        scale = criterion.get("scale", 1.0)
                        cleaned = sanitize_numeric(value)
                        rows[symbol][criterion["field"]] = None if cleaned is None else cleaned * scale
                    matched += 1
                logging.info(f"  {market}: {criterion['label']} 命中 {matched} 只")

            mkt_candidates, mkt_results = [], []
            for symbol in tracked_symbols:
                row = rows[symbol]
                score, checks = buffett_quant_score(row)
                row["score"] = score
                row["checks"] = checks
                row["passed"] = score >= min_score
                row["market_cap_b"] = round(row["market_cap"] / 1e9, 1) if row.get("market_cap") else None
                if symbol in holdings_meta:
                    reference_rows[symbol] = dict(row)
            tracked_rows_by_market[market] = [dict(rows[symbol]) for symbol in tracked_symbols]

            for i, symbol in enumerate(symbols, 1):
                if i % 50 == 0:
                    logging.info(f"  进度: {i}/{len(symbols)}...")
                row = rows[symbol]
                mkt_results.append(row)
                if row["passed"]:
                    mkt_candidates.append(row)
                    logging.info(f"  ✅ {symbol}: {row['score']}/9")
                else:
                    logging.debug(f"  ❌ {symbol}: {row['score']}/9")

            candidates[market] = mkt_candidates
            all_results[market] = mkt_results
    finally:
        try:
            ctx.close()
        except Exception:
            pass

    market_stats = build_market_opportunity_stats(tracked_rows_by_market)
    hurdle = build_opportunity_hurdle(holdings_meta, reference_rows, market_stats)
    if hurdle.get("holdings_metrics"):
        weakest = hurdle.get("weakest_holding") or {}
        weakest_score = weakest.get("opportunity_score", 0.0)
        weakest_symbol = weakest.get("symbol", "N/A")
        logging.info(f"持仓复合机会成本基准已建立：最弱持仓 {weakest_symbol} = {weakest_score:.1f}")

    for market, mkt_rows in all_results.items():
        for row in mkt_rows:
            row.update(compute_opportunity_score_components(row, market_stats))
        for row in candidates.get(market, []):
            row.update(compute_opportunity_score_components(row, market_stats))
            row["opportunity_flag"] = flag_opportunity(row, hurdle, oc_discount)
        n_opp = sum(1 for c in candidates.get(market, []) if c.get("opportunity_flag"))
        logging.info(f"  {market}: {len(candidates.get(market, []))}/{len(universe.get(market, []))} 通过 | {n_opp} 只触发机会成本标记")

    return candidates, all_results, hurdle


def summarize_error_results(all_results: dict | None) -> dict:
    summary = {"total_errors": 0, "by_type": {}, "by_market": {}}
    if not all_results:
        return summary
    for market, rows in all_results.items():
        market_errors = {}
        for row in rows:
            err = row.get("error")
            if not err:
                continue
            summary["total_errors"] += 1
            summary["by_type"][err] = summary["by_type"].get(err, 0) + 1
            market_errors[err] = market_errors.get(err, 0) + 1
        if market_errors:
            summary["by_market"][market] = market_errors
    return summary


# ─────────────────────────────────────────────
# SECTION 8: HTML REPORT
# ─────────────────────────────────────────────

def generate_html_report(run_date, mode, alerts, watchlist_results,
                         candidates, all_results, hurdle=None) -> str:
    error_summary = summarize_error_results(all_results)

    # Watchlist rows
    wl_rows = ""
    for s in (watchlist_results or []):
        currency = s.get("currency", "")
        price = s.get("current_price")
        ps = format_money(price, currency) if isinstance(price, (int, float)) else str(price)
        mos = s.get("mos_pct")
        ms = f"{mos:.1f}%" if mos is not None else "N/A"
        triggered = s.get("triggered", False)
        rc = "alert-row" if triggered else ""
        badge = '<span class="badge-alert">🔔 预警</span>' if triggered else '<span class="badge-ok">正常</span>'
        wl_rows += f"""
        <tr class="{rc}">
          <td><strong>{s['symbol']}</strong></td>
          <td>{s.get('company','')[:28]}</td>
          <td>{ps}</td>
          <td>{format_money(s.get('v_base'), currency, 1)}</td>
          <td>{format_money(s.get('v_base_geo_adjusted'), currency, 1)}</td>
          <td>{format_money(s.get('alert_price'), currency, 1)}</td>
          <td>{ms}</td>
          <td>{format_money(s.get('floor'), currency, 1)}</td>
          <td>{badge}</td>
        </tr>"""

    # Holdings hurdle table
    hurdle_html = ""
    if hurdle and hurdle.get("holdings_metrics"):
        rows = ""
        for hdata in hurdle.get("holdings_metrics_sorted") or hurdle["holdings_metrics"].values():
            sym = hdata.get("symbol", "")
            pe_ttm = hdata.get("pe_ttm")
            pe_text = f"{pe_ttm:.1f}x" if isinstance(pe_ttm, (int, float)) else "N/A"
            rows += (
                f"<tr><td><strong>{sym}</strong></td>"
                f"<td>{hdata.get('company','')[:25]}</td>"
                f"<td>{(hdata.get('industry') or 'N/A')[:18]}</td>"
                f"<td>{pe_text}</td>"
                f"<td>{hdata.get('quality_score','N/A')}</td>"
                f"<td>{hdata.get('growth_score','N/A')}</td>"
                f"<td><strong>{hdata.get('opportunity_score','N/A')}</strong></td></tr>"
            )
        weakest = hurdle.get("weakest_holding") or {}
        weakest_basis = ""
        market = weakest.get("market")
        market_baseline = (hurdle.get("market_baselines") or {}).get(market)
        if market_baseline:
            weakest_basis = (
                f"；{market} 市场持仓底部30%均值 = <strong>{market_baseline.get('bottom_cohort_score','N/A')}</strong>"
            )
        hurdle_html = f"""
        <div class="card">
          <h2>⚖️ 机会成本基准（持仓复合评分）</h2>
          <p style="font-size:13px;color:#666;margin-bottom:12px">
            自动层按 <strong>PE_TTM + 质量(ROE/毛利率/净利率/ROIC/现金流) + 增长 + 行业相对估值</strong> 计算机会分。
            当前最弱持仓为 <strong>{weakest.get('symbol','N/A')}</strong>，机会分 <strong>{weakest.get('opportunity_score','N/A')}</strong>{weakest_basis}。
          </p>
          <table class="data-table">
            <thead><tr><th>持仓</th><th>公司</th><th>行业</th><th>PE_TTM</th><th>质量分</th><th>增长分</th><th>机会分</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    # Universe candidates
    cand_html = ""
    opp_candidates = []
    for market, cands in (candidates or {}).items():
        if not cands:
            continue
        cands = sorted(
            cands,
            key=lambda c: (
                c.get("opportunity_score", 0),
                c.get("score", 0),
                1 if c.get("opportunity_flag") else 0,
                -(c.get("pe_ttm") or 10**9),
            ),
            reverse=True,
        )
        rows = ""
        for c in cands:
            opp = c.get("opportunity_flag")
            opp_badge = f'<br><span class="badge-opp">⭐️ {opp}</span>' if opp else ""
            if opp:
                opp_candidates.append(c)
            evf = f"{c['pe_ttm']:.1f}x" if c.get("pe_ttm") is not None else "N/A"
            roe_s = f"{c['roe']*100:.1f}%" if c.get("roe") is not None else "N/A"
            rows += f"""
          <tr {'class="opp-row"' if opp else ""}>
            <td><strong>{c['symbol']}</strong>{opp_badge}</td>
            <td>{c.get('name','')[:30]}</td>
            <td>{format_money(c.get('price'), c.get('currency'))}</td>
            <td>{c.get('market_cap_b','N/A')}B</td>
            <td>{evf}</td>
            <td>{roe_s}</td>
            <td><strong>{c['score']}/{c['score_max']}</strong></td>
            <td><strong>{c.get('opportunity_score','N/A')}</strong></td>
            <td><code>/初筛 {c['symbol']}</code></td>
          </tr>"""
        cand_html += f"""
        <h3 style="color:#1565c0;margin-top:20px">{market} — {len(cands)} 只候选
          （其中 <span style="color:#e65100">{sum(1 for c in cands if c.get('opportunity_flag'))} 只触发机会成本标记</span>）
        </h3>
        <table class="data-table">
          <thead><tr>
            <th>代码</th><th>名称</th><th>价格</th><th>市值</th>
            <th>PE_TTM</th><th>ROE</th><th>评分</th><th>机会分</th><th>下一步</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>"""

    alert_count = len(alerts)
    total_scanned = sum(len(v) for v in (all_results or {}).values())
    total_cands = sum(len(v) for v in (candidates or {}).values())

    alert_banner = ""
    if alert_count > 0:
        syms = ", ".join(a["symbol"] for a in alerts)
        alert_banner = f"""
      <div class="alert-banner">
        🔔 {alert_count} 只持仓标的触发击球区预警：<strong>{syms}</strong> — MoS ≥ 40%
      </div>"""

    opp_banner = ""
    if opp_candidates:
        opp_syms = ", ".join(c["symbol"] for c in opp_candidates[:5])
        opp_banner = f"""
      <div class="opp-banner">
        ⭐️ {len(opp_candidates)} 只候选的复合机会成本优于现有持仓：<strong>{opp_syms}</strong>
        — 建议优先进行 /初筛 评估
      </div>"""

    diagnostic_banner = ""
    if error_summary["total_errors"] > 0:
        by_type = " / ".join(
            f"{err}: {count}"
            for err, count in sorted(error_summary["by_type"].items(), key=lambda item: item[1], reverse=True)
        )
        diagnostic_banner = f"""
      <div class="alert-banner" style="background:linear-gradient(135deg,#ffebee,#fff3e0);border-left-color:#c62828">
        ⚠️ 本次扫描有 <strong>{error_summary['total_errors']}</strong> 条数据抓取失败记录。
        失败摘要：<strong>{by_type}</strong>
      </div>"""

    mode_label = {"watchlist": "持仓监控", "universe": "指数成分股扫描", "full": "完整扫描"}.get(mode, mode)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>投资筛选报告 {run_date}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, 'PingFang SC', sans-serif; background: #f5f7fa; color: #333; }}
    .header {{
      background: linear-gradient(135deg, #1565c0 0%, #0d47a1 50%, #01579b 100%);
      color: white; padding: 32px 40px;
    }}
    .header h1 {{ font-size: 26px; font-weight: 700; }}
    .header .subtitle {{ margin-top: 8px; opacity: .85; font-size: 13px; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 20px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin:20px 0; }}
    .kpi-card {{ background:white; border-radius:10px; padding:18px 14px; box-shadow:0 2px 8px rgba(0,0,0,.07); text-align:center; }}
    .kpi-value {{ font-size:30px; font-weight:700; color:#1565c0; }}
    .kpi-value.red {{ color:#c62828; }} .kpi-value.orange {{ color:#e65100; }} .kpi-value.green {{ color:#2e7d32; }}
    .kpi-label {{ font-size:11px; color:#888; margin-top:4px; }}
    .card {{ background:white; border-radius:10px; padding:24px; box-shadow:0 2px 8px rgba(0,0,0,.07); margin-bottom:20px; }}
    .card h2 {{ font-size:17px; color:#1565c0; border-bottom:2px solid #e3f2fd; padding-bottom:8px; margin-bottom:14px; }}
    .alert-banner {{ background:linear-gradient(135deg,#fff8e1,#fff3cd); border-left:5px solid #f9a825;
                     border-radius:8px; padding:14px 18px; margin-bottom:16px; font-size:14px; }}
    .opp-banner {{ background:linear-gradient(135deg,#fff3e0,#ffe0b2); border-left:5px solid #e65100;
                   border-radius:8px; padding:14px 18px; margin-bottom:16px; font-size:14px; }}
    .data-table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
    .data-table th {{ background:#e3f2fd; color:#1565c0; padding:9px 10px; text-align:left; font-weight:600; }}
    .data-table td {{ padding:8px 10px; border-bottom:1px solid #f0f0f0; }}
    .data-table tr:hover td {{ background:#fafbff; }}
    .alert-row td {{ background:#fff8e1 !important; font-weight:600; }}
    .opp-row td {{ background:#fff3e0 !important; }}
    .badge-alert {{ background:#ff6f00; color:white; border-radius:10px; padding:2px 8px; font-size:11px; }}
    .badge-ok {{ background:#e8f5e9; color:#2e7d32; border-radius:10px; padding:2px 8px; font-size:11px; }}
    .badge-opp {{ background:#e65100; color:white; border-radius:10px; padding:2px 7px; font-size:11px; }}
    .next-steps {{ background:#e8f5e9; border-left:4px solid #43a047; border-radius:8px; padding:14px 18px; }}
    .next-steps h3 {{ color:#2e7d32; margin-bottom:8px; font-size:15px; }}
    .next-steps li {{ margin:5px 0; font-size:13px; }}
    .footer {{ text-align:center; padding:20px; color:#aaa; font-size:11px; margin-top:20px; }}
    code {{ background:#f0f4ff; padding:2px 5px; border-radius:3px; font-size:11px; color:#1565c0; }}
  </style>
</head>
<body>
  <div class="header">
  <h1>📡 投资标的筛选报告</h1>
  <div class="subtitle">
    {run_date} &nbsp;|&nbsp; {mode_label} &nbsp;|&nbsp;
    指数成分股：Futu SPX / CSI300 / HSI / HSCEI / HSTECH &nbsp;|&nbsp;
    机会成本比较：PE_TTM + 质量 + 增长 + 行业可比
  </div>
</div>
<div class="container">

  {alert_banner}
  {opp_banner}
  {diagnostic_banner}

  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-value {'red' if alert_count else 'green'}">{alert_count}</div>
      <div class="kpi-label">🔔 持仓价格预警（MoS≥40%）</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value orange">{len(opp_candidates)}</div>
      <div class="kpi-label">⭐️ 机会成本候选（复合口径优于持仓）</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">{total_cands}</div>
      <div class="kpi-label">🔍 量化候选（≥6/9）</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">{total_scanned}</div>
      <div class="kpi-label">🌏 扫描指数成分股总数</div>
    </div>
  </div>

  <!-- Watchlist -->
  <div class="card">
    <h2>📋 持仓 Watchlist 价格监控</h2>
    <p style="font-size:12px;color:#666;margin-bottom:10px">
      预警：价格 ≤ V_base_geo × 60%（安全边际 ≥ 40%）。V_base 为原始估值，V_base_geo 为地缘折价后估值。
    </p>
    <table class="data-table">
      <thead><tr>
        <th>代码</th><th>公司</th><th>当前价</th>
        <th>V_base</th><th>V_base(geo)</th><th>预警触发价</th><th>MoS</th><th>Floor</th><th>状态</th>
      </tr></thead>
      <tbody>
        {wl_rows or '<tr><td colspan="9" style="text-align:center;color:#aaa">暂无持仓或数据获取失败</td></tr>'}
      </tbody>
    </table>
  </div>

  <!-- Opportunity Cost -->
  {hurdle_html}

  <!-- Universe Candidates -->
  {"" if not cand_html else f'<div class="card"><h2>🔍 指数成分股量化候选</h2><p style="font-size:12px;color:#666;margin-bottom:10px">通过≥6/9量化指标 | ⭐️=复合机会成本优于现有持仓，建议优先初筛</p>{cand_html}</div>'}

  <!-- Next Steps -->
  <div class="next-steps">
    <h3>📌 建议下一步</h3>
    <ul>
      {"".join(f'<li>🔔 <strong>{a["symbol"]}</strong>（MoS={a.get("mos_pct","?")}%）：价格触发击球区 → <code>/估值 {a["symbol"]} {a.get("current_price","XXX")}</code></li>' for a in alerts)}
      {"".join(f'<li>⭐️ <strong>{c["symbol"]}</strong>（{c.get("name","")[:20]}，机会分={c.get("opportunity_score","?")}）：机会成本候选 → <code>/初筛 {c["symbol"]}</code></li>' for c in opp_candidates[:5])}
      {"".join(f'<li>🔍 <strong>{c["symbol"]}</strong>（{c.get("name","")[:20]}，{c["score"]}/9）→ <code>/初筛 {c["symbol"]}</code></li>' for market_cands in (candidates or {}).values() for c in market_cands[:2] if not c.get("opportunity_flag"))}
      {'<li style="color:#c62828">本次扫描 0 候选，且伴随大量数据抓取失败；优先检查 Futu OpenD 连接、权限和条件选股额度，而不是直接解读为“市场无机会”。</li>' if total_cands == 0 and error_summary["total_errors"] > 0 else ''}
      {'<li style="color:#aaa">本次扫描无预警、无机会成本候选</li>' if not alerts and not opp_candidates and total_cands == 0 and error_summary["total_errors"] == 0 else ""}
    </ul>
  </div>

</div>
<div class="footer">
  投资筛选系统 v2.0 · {run_date} · 数据来源：Futu OpenD 快照 + Futu 条件选股财务字段 · 仅供参考，不构成投资建议
</div>
</body>
</html>"""
    return html


# ─────────────────────────────────────────────
# SECTION 9: EMAIL
# ─────────────────────────────────────────────

def send_email(html_content: str, subject: str, cfg: dict) -> bool:
    ec = cfg["email"]
    if not ec.get("enabled"):
        logging.info("邮件已禁用")
        return False
    sender = ec.get("sender", "")
    password = os.environ.get("IC_EMAIL_PASSWORD") or ec.get("password", "")
    recipients = ec.get("recipients", [])
    if not all([sender, password, recipients]):
        logging.warning("邮件配置不完整，跳过")
        return False
    if "YOUR_" in password:
        logging.warning("邮件密码尚未配置（仍为占位符），跳过发送")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    host = ec["smtp_host"]
    port = ec["smtp_port"]
    try:
        if ec.get("use_ssl_direct", False):
            # Port 465: direct SSL (163, QQ mail, etc.)
            with smtplib.SMTP_SSL(host, port) as srv:
                srv.login(sender, password)
                srv.sendmail(sender, recipients, msg.as_string())
        else:
            # Port 587: STARTTLS (Gmail, etc.)
            with smtplib.SMTP(host, port) as srv:
                if ec.get("use_tls", True):
                    srv.starttls()
                srv.login(sender, password)
                srv.sendmail(sender, recipients, msg.as_string())
        logging.info(f"✅ 邮件已发送至 {recipients}")
        return True
    except Exception as e:
        logging.error(f"邮件发送失败: {e}")
        return False


# ─────────────────────────────────────────────
# SECTION 10: MAIN
# ─────────────────────────────────────────────

def save_report(html: str, cfg: dict, run_date: str, mode: str) -> str:
    reports_dir = Path(cfg["paths"]["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    fp = reports_dir / f"screener_{mode}_{run_date}.html"
    with open(fp, "w", encoding="utf-8") as f:
        f.write(html)
    logging.info(f"报告已保存: {fp}")
    return str(fp)


def main():
    parser = argparse.ArgumentParser(description="投资标的筛选系统 v2.0")
    parser.add_argument("--watchlist",  action="store_true", help="持仓价格监控")
    parser.add_argument("--universe",   action="store_true", help="全指数成分股扫描（季度）")
    parser.add_argument("--all",        action="store_true", help="两者都运行")
    parser.add_argument("--markets",    nargs="+", default=["US","HK","A"],
                        help="扫描市场子集，如 --markets US HK")
    parser.add_argument("--test-email", action="store_true", help="测试邮件配置")
    parser.add_argument("--no-email",   action="store_true", help="不发邮件")
    parser.add_argument("--list-index", metavar="MARKET",
                        help="预览指数成分股列表（US/HK/A），不执行扫描")
    parser.add_argument("--config",     default=str(DEFAULT_CONFIG_PATH))
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg["paths"]["log_file"])
    run_date = datetime.now().strftime("%Y%m%d_%H%M")

    # Preview mode
    if args.list_index:
        ft, ctx = open_futu_quote_context()
        universe = get_index_universe([args.list_index.upper()], ft=ft, ctx=ctx)
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass
        for market, syms in universe.items():
            print(f"\n{market} — {len(syms)} 只成分股:")
            for i, s in enumerate(syms, 1):
                print(f"  {i:3d}. {s}")
        return

    logging.info("=" * 60)
    logging.info(f"投资筛选系统 v2.0 启动 {run_date}")
    logging.info("=" * 60)

    if args.test_email:
        test_html = f"<h2>测试邮件</h2><p>时间：{run_date}，系统运行正常。</p>"
        send_email(test_html, f"{cfg['email']['subject_prefix']} 测试 {run_date}", cfg)
        return

    alerts, watchlist_results = [], []
    candidates, all_results = {}, {}
    hurdle = None

    do_watchlist = args.watchlist or args.all or (not args.universe)
    do_universe = args.universe or args.all

    if do_watchlist:
        logging.info("\n【Layer 3】持仓价格监控...")
        alerts, watchlist_results = check_watchlist(cfg)

    if do_universe:
        logging.info("\n【Layer 1+2】指数成分股扫描...")
        candidates, all_results, hurdle = scan_universe(cfg, args.markets)

    mode = "full" if (do_watchlist and do_universe) else ("universe" if do_universe else "watchlist")

    html = generate_html_report(run_date, mode, alerts, watchlist_results,
                                candidates, all_results, hurdle)
    report_path = save_report(html, cfg, run_date, mode)

    # Email decision
    opp_count = sum(1 for cands in candidates.values() for c in cands if c.get("opportunity_flag"))
    should_send = (not args.no_email) and (alerts or opp_count > 0 or cfg["notifications"].get("send_on_no_alerts"))
    if should_send:
        prefix = cfg["email"]["subject_prefix"]
        if alerts:
            syms = ", ".join(a["symbol"] for a in alerts)
            subject = f"{prefix} 🔔 {len(alerts)}只价格预警：{syms} · {run_date[:8]}"
        elif opp_count:
            subject = f"{prefix} ⭐️ {opp_count}只机会成本候选 · {run_date[:8]}"
        else:
            subject = f"{prefix} 全清，无预警 · {run_date[:8]}"
        send_email(html, subject, cfg)

    # Console summary
    total_cands = sum(len(v) for v in candidates.values())
    logging.info(f"\n扫描完成 | 价格预警:{len(alerts)} | 机会成本候选:{opp_count} | 量化候选:{total_cands}")
    logging.info(f"报告: {report_path}")

    if alerts or opp_count:
        print("\n" + "=" * 60)
        if alerts:
            print("🔔 价格预警 — 在Claude Code中运行：")
            for a in alerts:
                p = a.get("current_price")
                ps = f"{p:.2f}" if isinstance(p, float) else str(p)
                print(f"  /估值 {a['symbol']} {ps}   (MoS={a.get('mos_pct','?')}%)")
        if opp_count:
            print("⭐️ 机会成本候选 — 优先初筛：")
            for cands in candidates.values():
                for c in cands:
                    if c.get("opportunity_flag"):
                        pe_ttm = c.get("pe_ttm")
                        pe_text = f"{pe_ttm:.1f}x" if isinstance(pe_ttm, (int, float)) else "N/A"
                        print(f"  /初筛 {c['symbol']}   ({c.get('name','')[:25]}，PE_TTM={pe_text})")
        print("=" * 60)


if __name__ == "__main__":
    main()
