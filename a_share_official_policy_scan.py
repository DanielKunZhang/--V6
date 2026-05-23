#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUTPUT_DIR = ROOT / "backtest_results" / "a_share_official_policy_scan"
DEFAULT_CONFIG = ROOT / "a_share_official_policy_sources.json"


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_date_text(text: str) -> str:
    text = html.unescape(text or "")
    patterns = [
        r"(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})日?",
        r"(20\d{2})(\d{2})(\d{2})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            continue
    return ""


def decode_response(resp: requests.Response) -> str:
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def fetch_url(url: str, timeout: float) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return decode_response(resp)


def extract_links(page_html: str, source: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    base_url = str(source.get("base_url") or source.get("list_url") or "")
    anchor_re = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    href_re = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
    for match in anchor_re.finditer(page_html):
        attrs = match.group(1)
        body = match.group(2)
        href_match = href_re.search(attrs)
        if not href_match:
            continue
        title = clean_text(body)
        if len(title) < 6 or title in {"更多", "首页", "下一页", "上一页"}:
            continue
        href = href_match.group(1).strip()
        if href.startswith(("javascript:", "mailto:")):
            continue
        start = max(0, match.start() - 180)
        end = min(len(page_html), match.end() + 180)
        context = clean_text(page_html[start:end])
        rows.append(
            {
                "title": title,
                "url": urljoin(base_url, href),
                "published_date": parse_date_text(context),
                "context": context[:260],
            }
        )
    return rows


def infer_theme(title: str, theme_specs: list[dict[str, Any]]) -> tuple[str, list[str]]:
    hits: list[tuple[str, str]] = []
    for spec in theme_specs:
        theme = str(spec.get("theme", ""))
        for keyword in spec.get("keywords", []):
            keyword = str(keyword).strip()
            if keyword and keyword.lower() in title.lower():
                hits.append((theme, keyword))
    if not hits:
        return "A股待分类官方线索", []
    theme_order: list[str] = []
    hit_keywords: list[str] = []
    for theme, keyword in hits:
        if theme not in theme_order:
            theme_order.append(theme)
        if keyword not in hit_keywords:
            hit_keywords.append(keyword)
    return " / ".join(theme_order[:2]), hit_keywords[:8]


def is_low_quality_title(title: str) -> bool:
    title = clean_text(title)
    if len(title) < 8:
        return True
    low_quality_exact = {
        "中国资本市场标准网",
        "网站地图",
        "联系我们",
        "信息公开",
        "政务服务",
        "互动交流",
        "新闻发布",
        "最新动态",
    }
    if title in low_quality_exact:
        return True
    if re.search(r"(首页|更多|列表|专题|频道|客户端|微信|微博)$", title):
        return True
    return False


def confidence_score(source: dict[str, Any], published_date: str, keyword_hits: list[str], asof: date) -> int:
    score = int(source.get("priority", 70))
    if published_date:
        try:
            days_old = (asof - datetime.strptime(published_date, "%Y-%m-%d").date()).days
            if days_old <= 2:
                score += 6
            elif days_old > 14:
                score -= 10
        except ValueError:
            pass
    else:
        score -= 8
    score += min(len(keyword_hits), 4) * 2
    return max(1, min(99, score))


def is_recent_enough(published_date: str, asof: date, lookback_days: int) -> bool:
    if not published_date:
        return True
    try:
        d = datetime.strptime(published_date, "%Y-%m-%d").date()
    except ValueError:
        return True
    return asof - timedelta(days=lookback_days) <= d <= asof + timedelta(days=1)


def row_id(source_id: str, title: str, url: str) -> str:
    raw = "|".join([source_id, title, url])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def scan_sources(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    asof = datetime.strptime(args.asof, "%Y-%m-%d").date()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    theme_specs = config.get("theme_keywords", [])
    seen: set[str] = set()

    for source in config.get("sources", [])[: args.max_sources]:
        source_id = str(source.get("id", ""))
        list_urls = source.get("list_urls") or [source.get("list_url", "")]
        list_urls = [str(url) for url in list_urls if str(url or "").strip()]
        if not source_id or not list_urls:
            continue
        if args.no_network:
            failures.append({"source_id": source_id, "source": source.get("name", ""), "status": "SKIPPED", "reason": "no_network"})
            continue
        candidates: list[dict[str, str]] = []
        source_errors: list[str] = []
        for list_url in list_urls:
            try:
                page = fetch_url(list_url, args.timeout_sec)
                candidates.extend(extract_links(page, {**source, "list_url": list_url}))
            except Exception as exc:
                source_errors.append(f"{list_url}: {str(exc)[:180]}")
            time.sleep(args.sleep_sec)
        if not candidates:
            status = "FAILED" if source_errors else "EMPTY"
            reason = " | ".join(source_errors)[:260] if source_errors else "no parseable links on source page"
            failures.append(
                {
                    "source_id": source_id,
                    "source": source.get("name", ""),
                    "status": status,
                    "reason": reason,
                }
            )
            continue
        kept = 0
        for item in candidates:
            title = item["title"]
            if is_low_quality_title(title):
                continue
            theme, keyword_hits = infer_theme(title, theme_specs)
            if not keyword_hits and not args.include_uncategorized:
                continue
            if not is_recent_enough(item.get("published_date", ""), asof, args.lookback_days):
                continue
            evidence_id = row_id(source_id, title, item["url"])
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            conf = confidence_score(source, item.get("published_date", ""), keyword_hits, asof)
            rows.append(
                {
                    "evidence_id": evidence_id,
                    "date": item.get("published_date") or args.asof,
                    "source": source.get("name", ""),
                    "source_id": source_id,
                    "source_type": source.get("source_type", "official_policy"),
                    "theme": theme,
                    "title": title,
                    "url": item["url"],
                    "keyword_hits": keyword_hits,
                    "confidence": conf,
                    "needs_manual_review": conf < 88 or not item.get("published_date"),
                    "notes": "official_whitelist_title_scan; no_trade_signal; Phase1A evidence only",
                }
            )
            kept += 1
            if kept >= args.max_items_per_source:
                break
        if kept == 0:
            status = "EMPTY_WITH_FETCH_ERRORS" if source_errors else "EMPTY"
            failures.append(
                {
                    "source_id": source_id,
                    "source": source.get("name", ""),
                    "status": status,
                    "reason": "no recent keyword-matched titles; manual review only if expected major policy"
                    + (f"; fetch_errors={' | '.join(source_errors)[:180]}" if source_errors else ""),
                }
            )

    rows.sort(key=lambda r: (int(r.get("confidence", 0)), str(r.get("date", ""))), reverse=True)
    return {
        "asof": args.asof,
        "status": "OK" if rows else "EMPTY",
        "source_count": min(len(config.get("sources", [])), args.max_sources),
        "row_count": len(rows),
        "lookback_days": args.lookback_days,
        "rows": rows,
        "failures": failures,
        "manual_review": [row for row in rows if row.get("needs_manual_review")][:30],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "evidence_id",
        "date",
        "source",
        "source_id",
        "source_type",
        "theme",
        "title",
        "url",
        "keyword_hits",
        "confidence",
        "needs_manual_review",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            item = dict(row)
            item["keyword_hits"] = " / ".join(item.get("keyword_hits", []))
            writer.writerow(item)


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# A股官方政策/公告白名单扫描",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 状态：`{payload['status']}`",
        f"- 白名单源数：`{payload['source_count']}`",
        f"- 命中条数：`{payload['row_count']}`",
        f"- 回看天数：`{payload['lookback_days']}`",
        "- 用途：A股 Radar Phase 1A 官方证据扫描 / 人工复核入口，不是自动交易信号。",
        "- 边界：只扫白名单公开页面；不绕登录、不绕验证码、不碰付费墙。",
        "",
    ]
    if payload.get("rows"):
        lines += [
            "## 命中线索",
            "",
            "| 日期 | 来源 | 主题 | 置信度 | 需复核 | 标题 |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
        for row in payload["rows"][:30]:
            title = str(row.get("title", ""))
            url = str(row.get("url", ""))
            link = f"[{title}]({url})" if url else title
            lines.append(
                f"| {row.get('date', '')} | {row.get('source', '')} | {row.get('theme', '')} | "
                f"{row.get('confidence', '')} | {'YES' if row.get('needs_manual_review') else 'NO'} | {link} |"
            )
        lines.append("")
    if payload.get("manual_review"):
        lines += ["## 今日需人工复核", ""]
        for row in payload["manual_review"][:12]:
            lines.append(f"- {row.get('theme', '')}｜{row.get('source', '')}｜{row.get('title', '')}｜{row.get('url', '')}")
        lines.append("")
    if payload.get("failures"):
        lines += ["## 爬取失败/空结果", ""]
        for item in payload["failures"][:20]:
            lines.append(f"- `{item.get('source_id')}` {item.get('source', '')}: {item.get('status', '')} - {item.get('reason', '')}")
        lines.append("")
    lines += [
        "## 使用口径",
        "",
        "- 官方标题命中只能证明“需要复核”，不能证明主题已形成可交易主线。",
        "- 若同一主题同时出现官方政策、交易所/公告、板块热度三类证据，再进入 A股 Radar 主线持续性复核。",
        "- 若关键源失败或疑似重要但未抓到正文，由人工检索补入 A股Radar INBOX。",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan whitelist official / exchange sources for A-share Radar evidence.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--max-sources", type=int, default=20)
    parser.add_argument("--max-items-per-source", type=int, default=20)
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--sleep-sec", type=float, default=1.5)
    parser.add_argument("--include-uncategorized", action="store_true")
    parser.add_argument("--no-network", action="store_true", help="Validate config and write an empty skipped report.")
    args = parser.parse_args()

    config = load_config(args.config)
    payload = scan_sources(args, config)
    md = render_md(payload)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "latest.json").write_text(json_text, encoding="utf-8")
    (OUTPUT_DIR / "latest.md").write_text(md, encoding="utf-8")
    write_csv(OUTPUT_DIR / "latest.csv", payload["rows"])
    (REPORT_ROOT / "A股官方政策白名单扫描_LATEST.json").write_text(json_text, encoding="utf-8")
    (REPORT_ROOT / "A股官方政策白名单扫描_LATEST.md").write_text(md, encoding="utf-8")
    write_csv(REPORT_ROOT / "A股官方政策白名单扫描_LATEST.csv", payload["rows"])
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
