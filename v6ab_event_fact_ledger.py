#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from v6ab_evidence_ledger import expiry_from_source, freshness


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_event_facts"
DOC_CACHE = ROOT / "backtest_results" / "sec_doc_cache"
DEFAULT_HISTORICAL_EVIDENCE = ROOT / "backtest_results" / "v6ab_historical_evidence" / "latest.json"

FACT_RULES = [
    ("revenue_acceleration", "positive", 0.70, 0.82, ["revenue increased", "revenues increased", "net sales increased", "sales increased"]),
    ("guidance_raise", "positive", 0.72, 0.84, ["raise guidance", "raised guidance", "increased guidance", "above our prior outlook", "exceed our guidance"]),
    ("margin_expansion", "positive", 0.66, 0.78, ["gross margin increased", "operating margin increased", "margin expansion", "expanded margins"]),
    ("orders_backlog", "positive", 0.68, 0.80, ["backlog increased", "bookings increased", "order growth", "strong order", "strong demand", "increased demand"]),
    ("capex_capacity", "positive", 0.64, 0.76, ["capital expenditures increased", "increase in capital expenditures", "capacity expansion", "new capacity", "manufacturing capacity", "foundry capacity"]),
    ("cloud_data_center", "positive", 0.68, 0.82, ["cloud revenue", "aws revenue", "data center demand", "datacenter demand", "hyperscale demand", "server demand"]),
    ("ai_accelerator", "positive", 0.72, 0.86, ["ai accelerator", "gpu demand", "hbm demand", "high bandwidth memory", "optical interconnect"]),
    ("inventory_correction", "negative", 0.70, 0.84, ["inventory correction", "elevated inventory", "inventory digestion", "channel inventory", "customer inventory"]),
    ("demand_slowdown", "negative", 0.72, 0.84, ["weak demand", "demand weakness", "lower demand", "soft demand", "slowdown in demand", "macroeconomic weakness"]),
    ("guidance_cut", "negative", 0.74, 0.86, ["lower guidance", "reduced guidance", "below our prior outlook", "cut guidance", "withdraw guidance"]),
    ("margin_pressure", "negative", 0.66, 0.80, ["gross margin decreased", "operating margin decreased", "margin pressure", "pricing pressure", "lower margins"]),
    ("supply_constraint", "mixed", 0.62, 0.74, ["supply constraint", "supply shortage", "component shortage", "logistics constraint"]),
]

SOURCE_TYPES = {
    "earnings_release",
    "quarterly_report",
    "annual_report",
    "business_update",
    "investor_presentation",
    "material_agreement",
}
POSITIVE_REJECT_CONTEXT = [
    "risk factor",
    "could harm",
    "could adversely",
    "may not",
    "may be materially affected",
    "unfavorable",
    "legal and regulatory risks",
    "we face risks",
    "risks related",
    "failure to",
    "fail to",
    "if too many",
    "system interruption",
    "system interruptions",
    "continued efforts to reduce prices",
    "we depend on",
    "depend on our",
    "suppliers may",
    "capacity constraints",
    "limit supplies",
    "lead times",
    "shortages in",
    "other contingencies",
    "purchase obligations",
    "open purchase orders",
    "processed and delivered orders",
    "not be sustainable",
    "decrease",
]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        data = data.strip()
        if data:
            self.parts.append(data)


def sec_headers() -> dict[str, str]:
    return {
        "User-Agent": "CodexResearch/1.0 (research; contact: codex@example.com)",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "text/html,text/plain,*/*",
    }


def cache_path_for_url(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    suffix = ".txt"
    if "." in url.rsplit("/", 1)[-1]:
        suffix = "." + url.rsplit(".", 1)[-1].lower()[:8]
    return DOC_CACHE / f"{digest}{suffix}"


def fetch_text(url: str, refresh: bool = False, sleep_sec: float = 0.12) -> str:
    DOC_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = cache_path_for_url(url)
    if cache_path.exists() and not refresh:
        raw = cache_path.read_text(encoding="utf-8", errors="ignore")
    else:
        time.sleep(sleep_sec)
        resp = requests.get(url, headers=sec_headers(), timeout=45)
        resp.raise_for_status()
        raw = resp.text
        cache_path.write_text(raw, encoding="utf-8", errors="ignore")
    parser = TextExtractor()
    try:
        parser.feed(raw)
        text = " ".join(parser.parts)
    except Exception:
        text = raw
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text


def sentence_windows(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?。；;])\s+", text)
    out: list[str] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if 80 <= len(chunk) <= 900:
            out.append(chunk)
    return out


def find_facts(text: str) -> list[dict[str, Any]]:
    lower_text = f" {text.lower()} "
    windows = sentence_windows(text)
    facts: list[dict[str, Any]] = []
    for fact_type, direction, confidence, weight, phrases in FACT_RULES:
        matched_phrase = ""
        matched_snippet = ""
        for phrase in phrases:
            if phrase in lower_text:
                matched_phrase = phrase
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                for window in windows:
                    if pattern.search(window):
                        matched_snippet = window[:500]
                        break
                if not matched_snippet:
                    idx = lower_text.find(phrase)
                    matched_snippet = text[max(0, idx - 180) : idx + 320]
                break
        if matched_phrase:
            snippet_lower = matched_snippet.lower()
            if direction == "positive" and any(token in snippet_lower for token in POSITIVE_REJECT_CONTEXT):
                continue
            facts.append(
                {
                    "fact_type": fact_type,
                    "direction": direction,
                    "confidence": confidence,
                    "weight": weight,
                    "matched_phrase": matched_phrase,
                    "snippet": matched_snippet.strip(),
                }
            )
    return facts


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_rows(args: argparse.Namespace) -> dict[str, Any]:
    source = load_json(args.historical_evidence_json)
    source_rows = [
        row
        for row in source.get("rows", [])
        if row.get("source_path")
        and row.get("evidence_type") in SOURCE_TYPES
        and args.start <= str(row.get("source_date", "")) <= args.end
    ]
    if args.limit > 0:
        source_rows = source_rows[: args.limit]

    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for row in source_rows:
        url = str(row.get("source_path", ""))
        try:
            text = fetch_text(url, refresh=args.refresh_docs, sleep_sec=args.sleep_sec)
            facts = find_facts(text)
        except Exception as exc:
            failures.append(f"{row.get('ticker')}:{row.get('source_date')}:{exc!r}")
            continue
        for fact in facts:
            source_date = str(row.get("source_date"))
            rows.append(
                {
                    "asof": source_date,
                    "theme": row.get("theme", "unclassified"),
                    "ticker": row.get("ticker", ""),
                    "source": "event_fact_ledger",
                    "source_path": url,
                    "source_date": source_date,
                    "evidence_type": f"event_fact_{fact['fact_type']}",
                    "confidence": round(float(fact["confidence"]), 4),
                    "direction": fact["direction"],
                    "freshness": freshness(args.asof, source_date),
                    "expiry_date": expiry_from_source(source_date, args.ttl_days),
                    "summary": f"{fact['fact_type']}: {fact['matched_phrase']}; {fact['snippet']}",
                    "weight": round(float(fact["weight"]), 4),
                }
            )

    dedup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["ticker"]), str(row["source_date"]), str(row["evidence_type"]), str(row["source_path"]))
        dedup[key] = row
    rows = sorted(dedup.values(), key=lambda item: (item["source_date"], item["ticker"], item["evidence_type"]))
    return {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "source_evidence_json": str(args.historical_evidence_json),
        "source_rows_scanned": len(source_rows),
        "row_count": len(rows),
        "failure_count": len(failures),
        "failures": failures[:80],
        "rows": rows,
        "boundary": "rule_based_event_fact_extraction_from_pit_visible_sec_docs",
    }


def render_md(payload: dict[str, Any]) -> str:
    rows = payload["rows"]
    by_type: dict[str, int] = {}
    by_theme: dict[str, int] = {}
    for row in rows:
        by_type[row["evidence_type"]] = by_type.get(row["evidence_type"], 0) + 1
        by_theme[row["theme"]] = by_theme.get(row["theme"], 0) + 1
    lines = [
        "# V6AB Event Fact Ledger v1",
        "",
        f"- asof：`{payload['asof']}`",
        f"- 区间：`{payload['start']} -> {payload['end']}`",
        f"- scanned docs：`{payload['source_rows_scanned']}`",
        f"- fact rows：`{payload['row_count']}`",
        f"- failures：`{payload['failure_count']}`",
        "- 边界：规则化文本事实抽取，只进入 PIT evidence，不直接影响模拟盘。",
        "",
        "## Fact Counts",
        "",
    ]
    for key, count in sorted(by_type.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"- `{key}`：{count}")
    lines += ["", "## Theme Counts", ""]
    for key, count in sorted(by_theme.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"- `{key}`：{count}")
    lines += [
        "",
        "## Sample Rows",
        "",
        "| date | ticker | theme | fact | direction | summary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows[:20]:
        summary = str(row.get("summary", "")).replace("|", "/")[:160]
        lines.append(f"| {row['source_date']} | `{row['ticker']}` | {row['theme']} | {row['evidence_type']} | {row['direction']} | {summary} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract rule-based historical event facts from SEC/IR documents.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--historical-evidence-json", type=Path, default=DEFAULT_HISTORICAL_EVIDENCE)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--limit", type=int, default=0, help="0 means no limit")
    parser.add_argument("--ttl-days", type=int, default=365)
    parser.add_argument("--sleep-sec", type=float, default=0.12)
    parser.add_argument("--refresh-docs", action="store_true")
    parser.add_argument("--sync-desktop", action="store_true")
    args = parser.parse_args()

    payload = build_rows(args)
    md = render_md(payload)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    (OUT_DIR / "latest.json").write_text(json_text, encoding="utf-8")
    (OUT_DIR / "latest.md").write_text(md, encoding="utf-8")
    pd.DataFrame(payload["rows"]).to_csv(OUT_DIR / "latest.csv", index=False)
    if args.sync_desktop:
        (REPORT_ROOT / "V6AB_Event_Fact_Ledger_LATEST.json").write_text(json_text, encoding="utf-8")
        (REPORT_ROOT / "V6AB_Event_Fact_Ledger_LATEST.md").write_text(md, encoding="utf-8")
        pd.DataFrame(payload["rows"]).to_csv(REPORT_ROOT / "V6AB_Event_Fact_Ledger_LATEST.csv", index=False)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
