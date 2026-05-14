#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "backtest_results" / "price_cache"
OUT_DIR = ROOT / "backtest_results" / "free_data_seed_cache"


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def stooq_symbol(ticker: str) -> str:
    plain = normalize_ticker(ticker).replace("US.", "")
    return f"{plain.lower()}.us"


def cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{normalize_ticker(ticker).replace('.', '_')}_daily.csv"


def fetch_stooq(ticker: str, allow_insecure_ssl: bool = False) -> pd.DataFrame:
    symbol = stooq_symbol(ticker)
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    context = ssl._create_unverified_context() if allow_insecure_ssl else None
    with urllib.request.urlopen(url, timeout=20, context=context) as resp:
        content = resp.read().decode("utf-8")
    if not content.strip() or content.strip().lower() == "no data":
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(content))
    if df.empty or "Date" not in df.columns or "Close" not in df.columns:
        return pd.DataFrame()
    df = df.rename(columns={"Date": "date"})
    keep = ["date", "Open", "High", "Low", "Close", "Volume"]
    for col in keep:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[keep].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "Close"]).sort_values("date")
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df


def fetch_akshare(ticker: str) -> pd.DataFrame:
    import akshare as ak

    plain = normalize_ticker(ticker).replace("US.", "")
    df = ak.stock_us_daily(symbol=plain, adjust="")
    if df.empty or "date" not in df.columns or "close" not in df.columns:
        return pd.DataFrame()
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    keep = ["date", "Open", "High", "Low", "Close", "Volume"]
    for col in keep:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[keep].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "Close"]).sort_values("date")
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df


def write_cache(ticker: str, df: pd.DataFrame, start: str, end: str, force: bool, source: str) -> dict:
    if df.empty:
        return {"ticker": ticker, "status": "empty"}
    filtered = df[(pd.to_datetime(df["date"]) >= pd.Timestamp(start)) & (pd.to_datetime(df["date"]) <= pd.Timestamp(end))].copy()
    if filtered.empty:
        return {"ticker": ticker, "status": "empty_after_filter"}
    path = cache_path(ticker)
    if path.exists() and not force:
        existing = pd.read_csv(path, parse_dates=["date"])
        merged = pd.concat([existing, filtered], ignore_index=True)
        merged = merged.dropna(subset=["date", "Close"]).sort_values("date").drop_duplicates(subset="date", keep="last")
        merged["date"] = pd.to_datetime(merged["date"]).dt.strftime("%Y-%m-%d")
    else:
        merged = filtered
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    return {
        "ticker": ticker,
        "status": "ok",
        "source": source,
        "cache_path": str(path.relative_to(ROOT)),
        "rows": int(len(merged)),
        "start": str(pd.to_datetime(merged["date"]).min().date()),
        "end": str(pd.to_datetime(merged["date"]).max().date()),
        "research_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local price cache from free data sources for research-only rough tests.")
    parser.add_argument("--tickers", required=True, help="Comma-separated tickers, e.g. US.AAOI,US.MRVL")
    parser.add_argument("--source", choices=["akshare", "stooq"], default="akshare")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-insecure-ssl", action="store_true", help="Research-only fallback for local certificate-chain issues.")
    args = parser.parse_args()

    tickers = [normalize_ticker(item) for item in args.tickers.split(",") if item.strip()]
    rows = []
    for ticker in tickers:
        try:
            if args.source == "akshare":
                df = fetch_akshare(ticker)
                source_name = "akshare_sina_us_daily"
            else:
                df = fetch_stooq(ticker, allow_insecure_ssl=args.allow_insecure_ssl)
                source_name = "stooq_free_csv"
            row = write_cache(ticker, df, args.start, args.end, args.force, source_name)
        except Exception as exc:
            row = {"ticker": ticker, "status": "error", "error": repr(exc), "research_only": True}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tag": args.tag,
        "source": args.source,
        "research_only": True,
        "allow_insecure_ssl": bool(args.allow_insecure_ssl),
        "warning": "Free-data cache is for rough research only. Revalidate with Futu before V6-B promotion or live/overlay decisions.",
        "rows": rows,
    }
    path = OUT_DIR / f"free_data_seed_cache_{args.tag}.json"
    latest = OUT_DIR / "latest.json"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    print(f"manifest={path}")


if __name__ == "__main__":
    main()
