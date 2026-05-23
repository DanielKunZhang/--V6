#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
INBOX_DIR = DESKTOP_ROOT / "信息源扫描" / "Theme_Evidence_Inbox"
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUTPUT_DIR = ROOT / "backtest_results" / "manual_theme_evidence_ledger"

A_SHARE_INBOX = INBOX_DIR / "A股Radar_人工信息搜集_INBOX.md"
V6AB_INBOX = INBOX_DIR / "V6AB_人工信息搜集_INBOX.md"
OFFICIAL_POLICY_SCAN_JSON = REPORT_ROOT / "A股官方政策白名单扫描_LATEST.json"

LOCAL_JSON = OUTPUT_DIR / "latest_theme_evidence_ledger.json"
LOCAL_CSV = OUTPUT_DIR / "latest_theme_evidence_ledger.csv"
DESKTOP_JSON = REPORT_ROOT / "Theme_Evidence_人工搜集_LATEST.json"
DESKTOP_CSV = REPORT_ROOT / "Theme_Evidence_人工搜集_LATEST.csv"
DESKTOP_MD = REPORT_ROOT / "Theme_Evidence_人工搜集_LATEST.md"

REVIEW_HORIZONS = (5, 10, 14)
SA_RATINGS = {"Buy", "Strong Buy", "Hold", "Sell", "Strong Sell"}

TEMPLATE = """# {title}

用途：这里是收件箱，不是表格作业。你可以直接把 Seeking Alpha、公告、政策、新闻标题、截图文字、自己的几句话判断粘贴到下面。

使用规则：
- 直接粘贴原文或摘要即可，不需要填表。
- 多条信息之间空一行，或者用 `---` 分隔。
- 如果你愿意，可以在开头写一句：主题=半导体设备 / NVDA / AI power；不写也可以。
- INBOX 只放待处理新信息；系统处理写入 ledger 后，可以删除已处理内容。
- 历史档案看 `Theme_Evidence_人工搜集_LATEST.md/json/csv`。

## 待处理粘贴区

<!-- 在下面直接粘贴新信息。处理后可以删除。 -->

"""


HEADER_MAP = {
    "日期": "date",
    "市场": "market",
    "主题": "theme",
    "来源类型": "source_type",
    "摘要": "summary",
    "方向": "evidence_direction",
    "置信度": "confidence",
    "阶段": "stage",
    "来源": "link_or_source",
    "结论": "user_verdict",
    "备注": "notes",
}

FIELDNAMES = [
    "evidence_id",
    "date",
    "market",
    "theme",
    "source_type",
    "summary",
    "evidence_direction",
    "confidence",
    "stage",
    "link_or_source",
    "user_verdict",
    "notes",
    "source_inbox",
    "review_status",
    "review_5d_due",
    "review_10d_due",
    "review_14d_due",
    "review_5d_result",
    "review_10d_result",
    "review_14d_result",
    "actual_impact",
    "classification_correct",
    "error_type",
    "review_notes",
    "created_at",
    "updated_at",
]


def ensure_inboxes() -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if not A_SHARE_INBOX.exists():
        A_SHARE_INBOX.write_text(TEMPLATE.format(title="A股 Radar 人工主题证据搜集 INBOX", market="A股"), encoding="utf-8")
    if not V6AB_INBOX.exists():
        V6AB_INBOX.write_text(TEMPLATE.format(title="V6AB / 美股 Radar 人工主题证据搜集 INBOX", market="US"), encoding="utf-8")


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue
    return None


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def split_md_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def normalize_header(value: str) -> str:
    value = value.strip()
    return HEADER_MAP.get(value, value)


def parse_inbox(path: Path, asof: date) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, Any]] = []
    headers: list[str] | None = None
    consumed_table_lines: set[int] = set()
    for line_no, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        consumed_table_lines.add(line_no)
        cells = split_md_row(stripped)
        if not cells:
            continue
        if all(set(cell.replace(":", "").strip()) <= {"-"} for cell in cells):
            continue
        normalized = [normalize_header(cell) for cell in cells]
        if "date" in normalized and "theme" in normalized and "summary" in normalized:
            headers = normalized
            continue
        if headers is None or len(cells) < 3:
            continue
        row = {headers[i]: cells[i] if i < len(cells) else "" for i in range(len(headers))}
        evidence_date = parse_date(row.get("date"))
        theme = str(row.get("theme", "")).strip()
        summary = str(row.get("summary", "")).strip()
        if not evidence_date or not theme or not summary or theme.startswith("示例"):
            continue
        market = str(row.get("market", "")).strip() or ("A股" if "A股" in path.name else "US")
        raw_id = "|".join([evidence_date.isoformat(), market, theme, summary, str(row.get("source_type", ""))])
        evidence_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16]
        rows.append(
            {
                "evidence_id": evidence_id,
                "date": evidence_date.isoformat(),
                "market": market,
                "theme": theme,
                "source_type": str(row.get("source_type", "")).strip(),
                "summary": summary,
                "evidence_direction": str(row.get("evidence_direction", "")).strip() or "mixed",
                "confidence": str(row.get("confidence", "")).strip(),
                "stage": str(row.get("stage", "")).strip(),
                "link_or_source": str(row.get("link_or_source", "")).strip(),
                "user_verdict": str(row.get("user_verdict", "")).strip() or "WATCH",
                "notes": str(row.get("notes", "")).strip(),
                "source_inbox": str(path),
                "review_status": "PENDING",
                "review_5d_due": (evidence_date + timedelta(days=5)).isoformat(),
                "review_10d_due": (evidence_date + timedelta(days=10)).isoformat(),
                "review_14d_due": (evidence_date + timedelta(days=14)).isoformat(),
                "review_5d_result": "",
                "review_10d_result": "",
                "review_14d_result": "",
                "actual_impact": "",
                "classification_correct": "",
                "error_type": "",
                "review_notes": "",
                "created_at": asof.isoformat(),
                "updated_at": asof.isoformat(),
            }
        )
    rows.extend(parse_free_text_blocks(path, lines, consumed_table_lines, asof))
    return rows


def infer_theme(text: str, market: str) -> str:
    lowered = text.lower()
    pairs = [
        ("vera rubin", "AI rack-scale systems / Rubin supply chain"),
        ("rubin", "AI rack-scale systems / Rubin supply chain"),
        ("vr200", "AI rack-scale systems / Rubin supply chain"),
        ("nvl72", "AI rack-scale systems / Rubin supply chain"),
        ("rack-scale", "AI rack-scale systems / Rubin supply chain"),
        ("rack scale", "AI rack-scale systems / Rubin supply chain"),
        ("机柜", "AI rack-scale systems / Rubin supply chain"),
        ("ai工厂", "AI rack-scale systems / Rubin supply chain"),
        ("整机柜", "AI rack-scale systems / Rubin supply chain"),
        ("整系统", "AI rack-scale systems / Rubin supply chain"),
        ("液冷", "AI rack-scale systems / cooling"),
        ("cpo", "AI optical / photonics"),
        ("pcb", "AI PCB / high-end materials"),
        ("abf", "AI PCB / high-end materials"),
        ("高端材料", "AI PCB / high-end materials"),
        ("电源", "AI power / data center"),
        ("hvdc", "AI power / data center"),
        ("人形机器人", "人形机器人"),
        ("机器人", "人形机器人"),
        ("半导体设备", "半导体设备"),
        ("国产替代", "国产替代"),
        ("低空经济", "低空经济"),
        ("电力设备", "电力设备"),
        ("算力", "算力"),
        ("mlcc", "AI服务器供应链 / MLCC被动元件"),
        ("多层陶瓷电容", "AI服务器供应链 / MLCC被动元件"),
        ("片式多层陶瓷电容", "AI服务器供应链 / MLCC被动元件"),
        ("被动元件", "AI服务器供应链 / MLCC被动元件"),
        ("电子元件", "AI服务器供应链 / MLCC被动元件"),
        ("电子元器件", "AI服务器供应链 / MLCC被动元件"),
        ("ai服务器", "AI服务器供应链 / MLCC被动元件"),
        ("nvda", "NVDA / AI GPU"),
        ("nvidia", "NVDA / AI GPU"),
        ("hbm", "AI memory / HBM"),
        ("mu", "AI memory / HBM"),
        ("chip stocks", "AI semis / accelerators"),
        ("qualcomm", "AI semis / accelerators"),
        ("amd", "AI semis / accelerators"),
        ("broadcom", "AI networking / ASIC"),
        ("avgo", "AI networking / ASIC"),
        ("anet", "AI networking / fabric"),
        ("lumentum", "AI optical / photonics"),
        ("coherent", "AI optical / photonics"),
        ("lite", "AI optical / photonics"),
        ("vertiv", "AI power / data center"),
        ("vrt", "AI power / data center"),
        ("generac", "AI power / data center"),
        ("gnrc", "AI power / data center"),
        ("rocket lab", "Space / launch"),
        ("rklb", "Space / launch"),
        ("spacex", "Space / launch"),
        ("microsoft", "AI cloud / software"),
        ("msft", "AI cloud / software"),
        ("alphabet", "AI cloud / software"),
        ("googl", "AI cloud / software"),
        ("amazon", "AI cloud / software"),
        ("amzn", "AI cloud / software"),
        ("meta", "AI cloud / software"),
        ("servicenow", "AI software / agentic"),
        ("quantum computing", "Quantum computing"),
        ("ai tech", "AI tech"),
        ("ai hardware", "AI hardware"),
        ("data center", "AI data center"),
        ("datacenter", "AI data center"),
        ("capex", "AI capex"),
        ("seeking alpha", "US manual source"),
    ]
    for needle, theme in pairs:
        if len(needle) <= 5 and needle.isascii():
            if re.search(rf"\b{re.escape(needle)}\b", lowered, flags=re.IGNORECASE):
                return theme
            continue
        if needle in lowered or needle in text:
            return theme
    return "A股待分类主题" if market == "A股" else "US待分类主题"


def infer_source_type(text: str) -> str:
    lowered = text.lower()
    if "seeking alpha" in lowered:
        return "seeking_alpha"
    if "sec" in lowered or "10-q" in lowered or "10-k" in lowered or "8-k" in lowered:
        return "filing"
    if "earnings" in lowered or "财报" in text or "业绩" in text:
        return "earnings"
    if "公告" in text or "巨潮" in text:
        return "announcement"
    if "政策" in text or "发改委" in text or "工信部" in text or "证监会" in text:
        return "policy"
    if "订单" in text or "产能" in text or "客户" in text or "capex" in lowered:
        return "industry"
    return "manual_paste"


def summarize_block(block: str, limit: int = 220) -> str:
    one_line = " ".join(line.strip() for line in block.splitlines() if line.strip())
    return one_line[:limit]


def parse_free_text_blocks(path: Path, lines: list[str], consumed_table_lines: set[int], asof: date) -> list[dict[str, Any]]:
    market = "A股" if "A股" in path.name else "US"
    paste_lines = collect_paste_lines(lines, consumed_table_lines)
    has_sa_lines = market == "US" and any("seeking" in line.lower() or "hot themes" in line.lower() for line in paste_lines)
    sa_rows = parse_seeking_alpha_lines(path, paste_lines, asof) if has_sa_lines else []

    blocks: list[str] = []
    current: list[str] = []
    in_paste_area = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "## 待处理粘贴区":
            in_paste_area = True
            continue
        if not in_paste_area:
            continue
        if idx in consumed_table_lines:
            continue
        if not stripped or stripped == "---":
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        if stripped.startswith("<!--") or stripped.startswith("#"):
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())

    rows: list[dict[str, Any]] = []
    for block in blocks:
        if not block or "示例：" in block:
            continue
        if has_sa_lines and not any(marker in block for marker in ["来源：", "待验证", "动作：", "主题：", "摘要：", "短线群", "主源"]):
            continue
        summary = summarize_block(block)
        raw_id = "|".join([asof.isoformat(), market, summary])
        evidence_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16]
        rows.append(
            {
                "evidence_id": evidence_id,
                "date": asof.isoformat(),
                "market": market,
                "theme": infer_theme(block, market),
                "source_type": infer_source_type(block),
                "summary": summary,
                "evidence_direction": "mixed",
                "confidence": "3",
                "stage": "NEEDS_TRIAGE",
                "link_or_source": str(path),
                "user_verdict": "WATCH",
                "notes": "raw_manual_paste; needs AI triage",
                "source_inbox": str(path),
                "review_status": "PENDING",
                "review_5d_due": (asof + timedelta(days=5)).isoformat(),
                "review_10d_due": (asof + timedelta(days=10)).isoformat(),
                "review_14d_due": (asof + timedelta(days=14)).isoformat(),
                "review_5d_result": "",
                "review_10d_result": "",
                "review_14d_result": "",
                "actual_impact": "",
                "classification_correct": "",
                "error_type": "",
                "review_notes": "",
                "created_at": asof.isoformat(),
                "updated_at": asof.isoformat(),
            }
        )
    return sa_rows + rows


def collect_paste_lines(lines: list[str], consumed_table_lines: set[int]) -> list[str]:
    out: list[str] = []
    in_paste_area = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "## 待处理粘贴区":
            in_paste_area = True
            continue
        if not in_paste_area or idx in consumed_table_lines:
            continue
        if stripped.startswith("<!--") or stripped.startswith("#"):
            continue
        if stripped:
            out.append(stripped)
    return out


def is_symbol(value: str) -> bool:
    if not value or len(value) > 8:
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
    return value.upper() == value and all(ch in allowed for ch in value) and any(ch.isalpha() for ch in value)


def is_sa_noise(value: str) -> bool:
    return value in {
        "Save",
        "Share",
        "FREE",
        "Theme",
        "Article",
        "Symbol",
        "Chg",
        *SA_RATINGS,
    }


def is_sa_date_line(value: str) -> bool:
    lower = value.lower()
    return (
        lower.startswith("yesterday")
        or lower.startswith("today")
        or lower.startswith("mon,")
        or lower.startswith("tue,")
        or lower.startswith("wed,")
        or lower.startswith("thu,")
        or lower.startswith("fri,")
        or lower.startswith("sat,")
        or lower.startswith("sun,")
    )


def parse_symbol_change_line(value: str) -> str:
    parts = value.strip().split()
    if len(parts) < 2:
        return ""
    symbol = parts[0].strip()
    change = parts[1].strip()
    if is_symbol(symbol) and ("%" in change or change.startswith(("+", "-"))):
        return symbol
    return ""


def make_manual_row(
    *,
    path: Path,
    asof: date,
    market: str,
    theme: str,
    source_type: str,
    summary: str,
    link_or_source: str,
    notes: str,
) -> dict[str, Any]:
    raw_id = "|".join([asof.isoformat(), market, theme, source_type, summary])
    evidence_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16]
    return {
        "evidence_id": evidence_id,
        "date": asof.isoformat(),
        "market": market,
        "theme": theme,
        "source_type": source_type,
        "summary": summary,
        "evidence_direction": "mixed",
        "confidence": "2" if source_type == "seeking_alpha_premium_title" else "3",
        "stage": "NEEDS_TRIAGE",
        "link_or_source": link_or_source,
        "user_verdict": "WATCH",
        "notes": notes,
        "source_inbox": str(path),
        "review_status": "PENDING",
        "review_5d_due": (asof + timedelta(days=5)).isoformat(),
        "review_10d_due": (asof + timedelta(days=10)).isoformat(),
        "review_14d_due": (asof + timedelta(days=14)).isoformat(),
        "review_5d_result": "",
        "review_10d_result": "",
        "review_14d_result": "",
        "actual_impact": "",
        "classification_correct": "",
        "error_type": "",
        "review_notes": "",
        "created_at": asof.isoformat(),
        "updated_at": asof.isoformat(),
    }


def make_evidence_row(
    *,
    evidence_id: str,
    evidence_date: date,
    market: str,
    theme: str,
    source_type: str,
    summary: str,
    confidence: str,
    stage: str,
    link_or_source: str,
    user_verdict: str,
    notes: str,
    source_inbox: str,
    asof: date,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "date": evidence_date.isoformat(),
        "market": market,
        "theme": theme,
        "source_type": source_type,
        "summary": summary,
        "evidence_direction": "mixed",
        "confidence": confidence,
        "stage": stage,
        "link_or_source": link_or_source,
        "user_verdict": user_verdict,
        "notes": notes,
        "source_inbox": source_inbox,
        "review_status": "PENDING",
        "review_5d_due": (evidence_date + timedelta(days=5)).isoformat(),
        "review_10d_due": (evidence_date + timedelta(days=10)).isoformat(),
        "review_14d_due": (evidence_date + timedelta(days=14)).isoformat(),
        "review_5d_result": "",
        "review_10d_result": "",
        "review_14d_result": "",
        "actual_impact": "",
        "classification_correct": "",
        "error_type": "",
        "review_notes": "",
        "created_at": asof.isoformat(),
        "updated_at": asof.isoformat(),
    }


def parse_official_policy_scan(path: Path, asof: date) -> list[dict[str, Any]]:
    payload = read_json(path)
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", "")).strip()
        if not title:
            continue
        evidence_date = parse_date(row.get("date")) or asof
        theme = str(row.get("theme", "")).strip() or "A股待分类官方线索"
        source = str(row.get("source", "")).strip()
        source_type = str(row.get("source_type", "")).strip() or "official_policy"
        url = str(row.get("url", "")).strip()
        confidence = str(row.get("confidence", "")).strip() or "5"
        raw_id = str(row.get("evidence_id", "")).strip() or hashlib.sha1(
            "|".join([source, title, url]).encode("utf-8")
        ).hexdigest()[:16]
        notes = "auto_official_whitelist_scan; no_trade_signal; Phase1A evidence only"
        if row.get("needs_manual_review"):
            notes += "; needs_manual_review"
        out.append(
            make_evidence_row(
                evidence_id=f"cn_official_{raw_id}"[:32],
                evidence_date=evidence_date,
                market="A股",
                theme=theme,
                source_type=f"auto_{source_type}",
                summary=f"{title} [{source}]",
                confidence=confidence,
                stage="OFFICIAL_AUTO_SCAN",
                link_or_source=url or str(path),
                user_verdict="WATCH",
                notes=notes,
                source_inbox=str(path),
                asof=asof,
            )
        )
    return out


def parse_seeking_alpha_lines(path: Path, lines: list[str], asof: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    mode = "articles"
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        lower = line.lower()
        if line == "HOT THEMES - NEWS":
            mode = "hot_themes"
            idx += 1
            continue
        if line == "ON THE MOVE - NEWS":
            mode = "on_the_move"
            idx += 1
            continue
        if line.startswith("Trending News"):
            mode = "trending_news"
            idx += 1
            continue
        if is_sa_noise(line) or line.startswith("<!--"):
            idx += 1
            continue

        if mode == "articles":
            inline = parse_inline_rating_symbol(line)
            if inline:
                title, rating, symbol = inline
                rows.append(
                    make_manual_row(
                        path=path,
                        asof=asof,
                        market="US",
                        theme=infer_theme(f"{title} {symbol}", "US"),
                        source_type="seeking_alpha_premium_title",
                        summary=f"{title} [{rating}; {symbol}]",
                        link_or_source="Seeking Alpha premium title list",
                        notes="premium_title_only; body_not_read; weak narrative evidence",
                    )
                )
                idx += 1
                continue
            title = line
            if is_symbol(title) or is_sa_date_line(title) or len(title) < 12:
                idx += 1
                continue
            j = idx + 1
            rating = ""
            timestamp = ""
            if j < len(lines) and lines[j] in SA_RATINGS:
                rating = lines[j]
                j += 1
            if j < len(lines) and is_sa_date_line(lines[j]):
                timestamp = lines[j]
                j += 1
            if j < len(lines) and is_symbol(lines[j]):
                symbol = lines[j]
                details = "; ".join(part for part in [rating, timestamp, symbol] if part)
                summary = f"{line} [{details}]"
                rows.append(
                    make_manual_row(
                        path=path,
                        asof=asof,
                        market="US",
                        theme=infer_theme(f"{line} {symbol}", "US"),
                        source_type="seeking_alpha_premium_title",
                        summary=summary,
                        link_or_source="Seeking Alpha premium title list",
                        notes="premium_title_only; body_not_read; weak narrative evidence",
                    )
                )
                idx = j + 1
                continue

        if mode == "hot_themes":
            if idx + 2 < len(lines) and is_symbol(lines[idx + 2].strip()):
                theme_label = line
                article = lines[idx + 1].strip()
                symbol = lines[idx + 2].strip()
                rows.append(
                    make_manual_row(
                        path=path,
                        asof=asof,
                        market="US",
                        theme=infer_theme(f"{theme_label} {article} {symbol}", "US"),
                        source_type="seeking_alpha_news_title",
                        summary=f"{theme_label}: {article} [{symbol}]",
                        link_or_source="Seeking Alpha HOT THEMES - NEWS",
                        notes="free_clickable_news; title_summary_only; validate important items with primary sources",
                    )
                )
                idx += 3
                continue

        if mode == "trending_news":
            if is_symbol(line) or is_sa_date_line(line) or line.lower().endswith("comments") or line.lower().endswith("comment"):
                idx += 1
                continue
            if idx + 1 < len(lines):
                symbol = parse_symbol_change_line(lines[idx + 1].strip())
                if symbol:
                    rows.append(
                        make_manual_row(
                            path=path,
                            asof=asof,
                            market="US",
                            theme=infer_theme(f"{line} {symbol}", "US"),
                            source_type="seeking_alpha_news_title",
                            summary=f"{line} [{symbol}]",
                            link_or_source="Seeking Alpha Trending News",
                            notes="free_clickable_news; title_summary_only; validate important items with primary sources",
                        )
                    )
                    idx += 2
                    continue

        if mode == "on_the_move":
            if idx + 2 < len(lines) and is_symbol(lines[idx + 1].strip()):
                article = line
                symbol = lines[idx + 1].strip()
                chg = lines[idx + 2].strip()
                rows.append(
                    make_manual_row(
                        path=path,
                        asof=asof,
                        market="US",
                        theme=infer_theme(f"{article} {symbol}", "US"),
                        source_type="seeking_alpha_on_the_move",
                        summary=f"{article} [{symbol}] {chg}",
                        link_or_source="Seeking Alpha ON THE MOVE - NEWS",
                        notes="free_clickable_news; price-move context; validate important items with primary sources",
                    )
                )
                idx += 3
                continue

        idx += 1
    return rows


def parse_inline_rating_symbol(line: str) -> tuple[str, str, str] | None:
    ratings = ["Strong Buy", "Strong Sell", "Buy", "Hold", "Sell"]
    for rating in ratings:
        marker = f" {rating.upper()} "
        upper = line.upper()
        if marker not in upper:
            continue
        idx = upper.rfind(marker)
        title = line[:idx].strip()
        symbol = line[idx + len(marker) :].strip().split()[0] if line[idx + len(marker) :].strip() else ""
        if title and is_symbol(symbol):
            return title, rating, symbol
    return None


def merge_rows(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], asof: date) -> list[dict[str, Any]]:
    refresh_sources = {str(row.get("source_inbox", "")) for row in incoming if row.get("source_inbox")}
    by_id = {}
    for row in existing:
        evidence_id = str(row.get("evidence_id", ""))
        if not evidence_id:
            continue
        source = str(row.get("source_inbox", ""))
        source_type = str(row.get("source_type", ""))
        notes = str(row.get("notes", ""))
        replaceable_manual_row = source in refresh_sources and (
            source_type.startswith("seeking_alpha") or "raw_manual_paste" in notes
        )
        if replaceable_manual_row:
            continue
        by_id[evidence_id] = dict(row)
    for row in incoming:
        evidence_id = str(row["evidence_id"])
        old = by_id.get(evidence_id)
        if old is None:
            by_id[evidence_id] = row
            continue
        for key in [
            "market",
            "theme",
            "source_type",
            "summary",
            "evidence_direction",
            "confidence",
            "stage",
            "link_or_source",
            "user_verdict",
            "notes",
            "source_inbox",
        ]:
            old[key] = row.get(key, old.get(key, ""))
        old["updated_at"] = asof.isoformat()
        by_id[evidence_id] = old
    return sorted(by_id.values(), key=lambda r: (str(r.get("date", "")), str(r.get("market", "")), str(r.get("theme", ""))), reverse=True)


def due_horizons(row: dict[str, Any], asof: date) -> list[str]:
    if str(row.get("review_status", "PENDING")).upper() in {"DONE", "CLOSED"}:
        return []
    due = []
    for days in REVIEW_HORIZONS:
        result = str(row.get(f"review_{days}d_result", "")).strip()
        due_date = parse_date(row.get(f"review_{days}d_due"))
        if due_date and due_date <= asof and not result:
            due.append(f"D{days}")
    return due


def build_summary(rows: list[dict[str, Any]], asof: date) -> dict[str, Any]:
    due_rows = []
    for row in rows:
        horizons = due_horizons(row, asof)
        if horizons:
            item = dict(row)
            item["due_horizons"] = horizons
            due_rows.append(item)
    a_count = sum(1 for row in rows if str(row.get("market", "")).upper() in {"A股", "CN", "CHINA"})
    us_count = len(rows) - a_count
    return {
        "asof": asof.isoformat(),
        "sample_count": len(rows),
        "a_share_count": a_count,
        "us_count": us_count,
        "due_count": len(due_rows),
        "due_reviews": sorted(due_rows, key=lambda r: (str(r.get("date", "")), str(r.get("theme", "")))),
        "inboxes": {
            "a_share": str(A_SHARE_INBOX),
            "v6ab": str(V6AB_INBOX),
            "a_share_official_auto": str(OFFICIAL_POLICY_SCAN_JSON),
        },
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_md(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Theme Evidence 人工搜集 Ledger",
        "",
        f"- 日期：`{summary['asof']}`",
        f"- 样本数：`{summary['sample_count']}`",
        f"- A股：`{summary['a_share_count']}`",
        f"- US/V6AB：`{summary['us_count']}`",
        f"- 到期复核：`{summary['due_count']}`",
        f"- A股 INBOX：`{summary['inboxes']['a_share']}`",
        f"- V6AB INBOX：`{summary['inboxes']['v6ab']}`",
        f"- A股官方自动扫描：`{summary['inboxes']['a_share_official_auto']}`",
        "",
        "## 到期复核",
        "",
    ]
    if not summary["due_reviews"]:
        lines.append("- 暂无到期复核。")
    else:
        lines += [
            "| 日期 | 市场 | 主题 | 类型 | 方向 | 置信度 | 到期 | 摘要 |",
            "| --- | --- | --- | --- | --- | ---: | --- | --- |",
        ]
        for row in summary["due_reviews"][:20]:
            lines.append(
                f"| {row.get('date', '')} | {row.get('market', '')} | {row.get('theme', '')} | "
                f"{row.get('source_type', '')} | {row.get('evidence_direction', '')} | {row.get('confidence', '')} | "
                f"{', '.join(row.get('due_horizons', []))} | {str(row.get('summary', ''))[:90]} |"
            )
    lines += [
        "",
        "## 最近记录",
        "",
        "| 日期 | 市场 | 主题 | 类型 | 方向 | 置信度 | 结论 | 摘要 |",
        "| --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in rows[:15]:
        lines.append(
            f"| {row.get('date', '')} | {row.get('market', '')} | {row.get('theme', '')} | "
            f"{row.get('source_type', '')} | {row.get('evidence_direction', '')} | {row.get('confidence', '')} | "
            f"{row.get('user_verdict', '')} | {str(row.get('summary', ''))[:90]} |"
        )
    lines += [
        "",
        "## 复核口径",
        "",
        "- 这里记录的是人工发现的高质量线索，不是自动交易信号。",
        "- `actual_impact`：supported_mainline / contradicted_mainline / no_impact / too_noisy。",
        "- `classification_correct`：YES / PARTIAL / NO。",
        "- `error_type`：too_early / too_late / false_catalyst / missed_catalyst / data_gap / other。",
        "- A股 Radar 和 V6AB 可共享 ledger 机制，但不共享具体阈值、买点或证据权重。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a lightweight manual theme evidence ledger from fixed inbox docs.")
    parser.add_argument("--asof", default=str(date.today()))
    args = parser.parse_args()

    asof = parse_date(args.asof) or date.today()
    ensure_inboxes()
    existing = read_json(LOCAL_JSON)
    existing_rows = existing.get("rows", []) if isinstance(existing, dict) else []
    incoming = (
        parse_inbox(A_SHARE_INBOX, asof)
        + parse_inbox(V6AB_INBOX, asof)
        + parse_official_policy_scan(OFFICIAL_POLICY_SCAN_JSON, asof)
    )
    rows = merge_rows(existing_rows, incoming, asof)
    summary = build_summary(rows, asof)
    payload = {**summary, "rows": rows}
    md = render_md(summary, rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    LOCAL_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(LOCAL_CSV, rows)
    DESKTOP_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(DESKTOP_CSV, rows)
    DESKTOP_MD.write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
