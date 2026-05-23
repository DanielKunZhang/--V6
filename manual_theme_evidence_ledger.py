#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
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

LOCAL_JSON = OUTPUT_DIR / "latest_theme_evidence_ledger.json"
LOCAL_CSV = OUTPUT_DIR / "latest_theme_evidence_ledger.csv"
DESKTOP_JSON = REPORT_ROOT / "Theme_Evidence_人工搜集_LATEST.json"
DESKTOP_CSV = REPORT_ROOT / "Theme_Evidence_人工搜集_LATEST.csv"
DESKTOP_MD = REPORT_ROOT / "Theme_Evidence_人工搜集_LATEST.md"

REVIEW_HORIZONS = (5, 10, 14)

TEMPLATE = """# {title}

用途：你把当天/本周看到的高质量政策、产业、公告、财报、资金或盘面线索放在下面表格里。系统只负责结构化记录和到期提醒，不自动交易。

填写规则：
- 一条线索一行。
- 不确定就写 `WATCH`，不要为了完整性硬凑。
- `confidence` 用 1-5，3=值得记录，4=较强，5=非常强。
- `user_verdict` 用 `KEEP / WATCH / REJECT`。
- INBOX 只放待处理新信息；系统处理写入 ledger 后，可以删除已处理行。
- 历史档案看 `Theme_Evidence_人工搜集_LATEST.md/json/csv`，不要把 INBOX 当档案库。

| date | market | theme | source_type | summary | evidence_direction | confidence | stage | link_or_source | user_verdict | notes |
| --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| 2026-05-23 | {market} | 示例主题 | policy/industry/earnings/flow/price_action/filing/13F | 示例：这里写一句话摘要 | positive/negative/mixed | 3 | 启动/主升/分歧/冷却/WATCH | 来源标题或链接 | WATCH | 可空 |
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
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
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
    return rows


def merge_rows(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], asof: date) -> list[dict[str, Any]]:
    by_id = {str(row.get("evidence_id", "")): dict(row) for row in existing if row.get("evidence_id")}
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
    incoming = parse_inbox(A_SHARE_INBOX, asof) + parse_inbox(V6AB_INBOX, asof)
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
