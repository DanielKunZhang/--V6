#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from v6ab_evidence_ledger import TICKER_THEME_OVERRIDES, expiry_from_source, freshness, infer_theme


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_historical_evidence"
CACHE_DIR = ROOT / "backtest_results" / "sec_cache"
COMPANY_TICKERS_CACHE = CACHE_DIR / "company_tickers.json"

DEFAULT_TICKERS = [
    "US.TSM",
    "US.AMD",
    "US.NVDA",
    "US.AVGO",
    "US.ANET",
    "US.MU",
    "US.WDC",
    "US.MRVL",
    "US.LITE",
    "US.AAOI",
    "US.COHR",
    "US.CRDO",
    "US.ALAB",
    "US.SNDK",
    "US.CSCO",
    "US.BE",
    "US.IREN",
    "US.APLD",
    "US.CORZ",
    "US.GOOGL",
    "US.MSFT",
    "US.AMZN",
    "US.META",
    "US.CEG",
    "US.NEE",
    "US.VST",
    "US.ETN",
]

FORM_ALLOWLIST = {"8-K", "10-Q", "10-K", "20-F", "6-K", "40-F"}
FORM_GROUP = {
    "8-K": ("sec_8k", "neutral", 0.62, 0.76, 365),
    "6-K": ("sec_6k", "neutral", 0.58, 0.70, 365),
    "10-Q": ("sec_10q", "positive", 0.66, 0.84, 540),
    "10-K": ("sec_10k", "positive", 0.70, 0.90, 730),
    "20-F": ("sec_20f", "positive", 0.66, 0.84, 730),
    "40-F": ("sec_40f", "positive", 0.66, 0.84, 730),
}

ITEM_TYPE_RULES = [
    ("1.01", "material_agreement", "positive", 0.72, 0.86, 365),
    ("2.02", "earnings_release", "positive", 0.74, 0.88, 210),
    ("7.01", "investor_presentation", "positive", 0.68, 0.82, 270),
    ("8.01", "business_update", "positive", 0.66, 0.80, 270),
]


def normalize_ticker(raw: str) -> str:
    return raw.strip().upper()


def sec_lookup_key(ticker: str) -> str:
    return normalize_ticker(ticker).replace("US.", "")


def theme_for_ticker(ticker: str) -> str:
    return TICKER_THEME_OVERRIDES.get(ticker, infer_theme(ticker))


def sec_headers() -> dict[str, str]:
    return {
        "User-Agent": "CodexResearch/1.0 (research; contact: codex@example.com)",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json,text/plain,*/*",
    }


def sec_get_json(url: str, sleep_sec: float = 0.2) -> dict[str, Any]:
    time.sleep(sleep_sec)
    resp = requests.get(url, headers=sec_headers(), timeout=45)
    resp.raise_for_status()
    return resp.json()


def load_company_ticker_map(refresh: bool = False) -> dict[str, dict[str, Any]]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if COMPANY_TICKERS_CACHE.exists() and not refresh:
        payload = json.loads(COMPANY_TICKERS_CACHE.read_text(encoding="utf-8"))
    else:
        urls = [
            "https://www.sec.gov/files/company_tickers.json",
            "https://www.sec.gov/files/company_tickers_exchange.json",
        ]
        last_exc: Exception | None = None
        payload = {}
        for url in urls:
            try:
                payload = sec_get_json(url, sleep_sec=0.0)
                break
            except Exception as exc:
                last_exc = exc
        if not payload:
            raise RuntimeError(f"unable to load SEC ticker map: {last_exc!r}")
        COMPANY_TICKERS_CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out: dict[str, dict[str, Any]] = {}
    for row in payload.values():
        ticker = str(row.get("ticker", "")).upper()
        if not ticker:
            continue
        out[ticker] = {
            "cik": int(row.get("cik_str", 0) or 0),
            "title": str(row.get("title", "")),
        }
    return out


def base_form(form: str) -> str:
    return str(form).upper().replace("/A", "")


def cik_url(cik: int) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik:010d}.json"


def extra_file_url(name: str) -> str:
    return f"https://data.sec.gov/submissions/{name}"


def load_submission_files(cik: int, refresh: bool = False) -> list[dict[str, Any]]:
    cache_root = CACHE_DIR / f"{cik:010d}"
    cache_root.mkdir(parents=True, exist_ok=True)
    main_cache = cache_root / "submissions_main.json"
    if main_cache.exists() and not refresh:
        main = json.loads(main_cache.read_text(encoding="utf-8"))
    else:
        main = sec_get_json(cik_url(cik), sleep_sec=0.0)
        main_cache.write_text(json.dumps(main, ensure_ascii=False, indent=2), encoding="utf-8")

    files = [main]
    for extra in main.get("filings", {}).get("files", []):
        name = str(extra.get("name", "")).strip()
        if not name:
            continue
        cache_path = cache_root / name
        if cache_path.exists() and not refresh:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            payload = sec_get_json(extra_file_url(name), sleep_sec=0.0)
            cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append(payload)
    return files


def rows_from_submission(ticker: str, title: str, cik: int, payload: dict[str, Any], start: str, end: str) -> list[dict[str, Any]]:
    filings = payload.get("filings", {})
    recent = filings.get("recent", {})
    if not recent:
        return []

    columns = list(recent.keys())
    count = len(recent.get("accessionNumber", []))
    rows: list[dict[str, Any]] = []
    for idx in range(count):
        form = str(recent.get("form", [""])[idx]).strip()
        bform = base_form(form)
        if bform not in FORM_ALLOWLIST:
            continue
        filing_date = str(recent.get("filingDate", [""])[idx]).strip()
        if not filing_date or filing_date < start or filing_date > end:
            continue
        accession = str(recent.get("accessionNumber", [""])[idx]).strip()
        primary_doc = str(recent.get("primaryDocument", [""])[idx]).strip()
        desc_list = recent.get("primaryDocDescription", [""] * count)
        desc = str(desc_list[idx]) if idx < len(desc_list) else ""
        items_list = recent.get("items", [""] * count)
        items = str(items_list[idx]) if idx < len(items_list) else ""
        form_type, direction, confidence, weight, ttl_days = FORM_GROUP.get(
            bform,
            ("sec_filing", "neutral", 0.55, 0.70, 365),
        )
        if bform in {"8-K", "6-K"}:
            haystack = f"{items} {desc} {primary_doc}".lower()
            for item_code, item_type, item_direction, item_conf, item_weight, item_ttl in ITEM_TYPE_RULES:
                if item_code in items or item_type.replace("_", " ") in haystack:
                    form_type = item_type
                    direction = item_direction
                    confidence = item_conf
                    weight = item_weight
                    ttl_days = item_ttl
                    break
            if any(word in haystack for word in ["earnings", "results", "quarter", "q1", "q2", "q3", "q4"]):
                form_type = "earnings_release"
                direction = "positive"
                confidence = max(float(confidence), 0.74)
                weight = max(float(weight), 0.88)
                ttl_days = max(int(ttl_days), 210)
            elif any(word in haystack for word in ["presentation", "investor", "analyst"]):
                form_type = "investor_presentation"
                direction = "positive"
                confidence = max(float(confidence), 0.68)
                weight = max(float(weight), 0.82)
                ttl_days = max(int(ttl_days), 270)
        elif bform in {"10-Q", "10-K", "20-F", "40-F"}:
            form_type = {
                "10-Q": "quarterly_report",
                "10-K": "annual_report",
                "20-F": "annual_report",
                "40-F": "annual_report",
            }.get(bform, form_type)
        source_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{primary_doc}" if primary_doc else cik_url(cik)
        summary = f"{bform} filed {filing_date}; items={items or 'n/a'}; doc={primary_doc or 'n/a'}; desc={desc or 'n/a'}"
        rows.append(
            {
                "asof": filing_date,
                "theme": theme_for_ticker(ticker),
                "ticker": ticker,
                "source": "sec_submission",
                "source_path": source_url,
                "source_date": filing_date,
                "evidence_type": form_type,
                "confidence": round(float(confidence), 4),
                "direction": direction,
                "freshness": 1.0,
                "expiry_date": expiry_from_source(filing_date, ttl_days),
                "summary": summary,
                "weight": round(float(weight), 4),
            }
        )
    return rows


def build_rows(tickers: list[str], start: str, end: str, refresh: bool = False) -> dict[str, Any]:
    ticker_map = load_company_ticker_map(refresh=refresh)
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for ticker in tickers:
        info = ticker_map.get(sec_lookup_key(ticker))
        if not info:
            missing.append(ticker)
            continue
        cik = int(info["cik"])
        title = str(info["title"])
        try:
            files = load_submission_files(cik, refresh=refresh)
            for payload in files:
                rows.extend(rows_from_submission(ticker, title, cik, payload, start, end))
        except Exception as exc:
            missing.append(f"{ticker}:{exc!r}")

    dedup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["ticker"], row["source_path"])
        dedup[key] = row
    rows = sorted(dedup.values(), key=lambda row: (row["ticker"], row["source_date"], row["source_path"]))
    return {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "start": start,
        "end": end,
        "tickers": tickers,
        "row_count": len(rows),
        "missing_tickers": missing,
        "rows": rows,
        "source": "sec_submissions_api",
        "forms": sorted(FORM_ALLOWLIST),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_md(payload: dict[str, Any]) -> str:
    rows = payload["rows"]
    by_theme: dict[str, int] = {}
    by_form: dict[str, int] = {}
    for row in rows:
        by_theme[row["theme"]] = by_theme.get(row["theme"], 0) + 1
        by_form[row["evidence_type"]] = by_form.get(row["evidence_type"], 0) + 1
    lines = [
        "# V6AB SEC Historical Evidence Harvest",
        "",
        f"- 区间：`{payload['start']} -> {payload['end']}`",
        f"- ticker 数：`{len(payload['tickers'])}`",
        f"- 证据数：`{payload['row_count']}`",
        f"- missing tickers：`{len(payload['missing_tickers'])}`",
        "- 来源：SEC company submissions API（官方）",
        "- 说明：这是历史证据补足层，只用于 PIT replay / 对比，不直接改当前模拟盘。",
        "",
        "## Form Counts",
        "",
    ]
    for form, count in sorted(by_form.items()):
        lines.append(f"- `{form}`：{count}")
    lines += ["", "## Theme Counts", ""]
    for theme, count in sorted(by_theme.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"- `{theme}`：{count}")
    lines += [
        "",
        "## Sample Rows",
        "",
        "| ticker | theme | source_date | form | summary |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows[:20]:
        lines.append(
            f"| `{row['ticker']}` | {row['theme']} | {row['source_date']} | {row['evidence_type']} | "
            f"{row['summary'][:120].replace('|', '/')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvest historical SEC filings as PIT evidence rows.")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=str(date.today()))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--sync-desktop", action="store_true")
    parser.add_argument("--tag", default=pd.Timestamp.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    tickers = [normalize_ticker(t) for t in args.tickers.split(",") if t.strip()]
    payload = build_rows(tickers, args.start, args.end, refresh=args.refresh)
    md = render_md(payload)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"sec_historical_evidence_{args.tag}.json"
    csv_path = OUT_DIR / f"sec_historical_evidence_{args.tag}.csv"
    md_path = OUT_DIR / f"sec_historical_evidence_{args.tag}.md"
    latest_json = OUT_DIR / "latest.json"
    latest_csv = OUT_DIR / "latest.csv"
    latest_md = OUT_DIR / "latest.md"
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(json_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    write_csv(csv_path, payload["rows"])
    write_csv(latest_csv, payload["rows"])
    md_path.write_text(md, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")

    if args.sync_desktop:
        out_dir = DESKTOP_ROOT / "报表输出" / "LATEST"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "V6AB_SEC_Historical_Evidence_LATEST.md").write_text(md, encoding="utf-8")
        (out_dir / "V6AB_SEC_Historical_Evidence_LATEST.json").write_text(json_text, encoding="utf-8")
        write_csv(out_dir / "V6AB_SEC_Historical_Evidence_LATEST.csv", payload["rows"])

    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
