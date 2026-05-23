#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
DEFAULT_PLAN_JSON = REPORT_ROOT / "A股短线Radar下周一计划_LATEST.json"
OUTPUT_DIR = ROOT / "backtest_results" / "a_share_radar_classification_ledger"
LEDGER_JSON = OUTPUT_DIR / "latest_ledger.json"
LEDGER_CSV = OUTPUT_DIR / "latest_ledger.csv"

DESKTOP_JSON = REPORT_ROOT / "A股Radar主线分类准度Ledger_LATEST.json"
DESKTOP_CSV = REPORT_ROOT / "A股Radar主线分类准度Ledger_LATEST.csv"
DESKTOP_MD = REPORT_ROOT / "A股Radar主线分类准度Ledger_LATEST.md"

REVIEW_HORIZONS = (5, 10, 14)


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


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def compact_theme_snapshot(theme: dict[str, Any]) -> dict[str, Any]:
    member_count = safe_float(theme.get("member_count"))
    hot_count = safe_float(theme.get("hot_count"))
    breadth = hot_count / member_count if member_count > 0 else 0.0
    return {
        "theme": str(theme.get("theme", "")),
        "score": safe_float(theme.get("score")),
        "phase": str(theme.get("phase", "")),
        "action": str(theme.get("action", "")),
        "reason": str(theme.get("reason", "")),
        "member_count": int(member_count),
        "hot_count": int(hot_count),
        "limit_proxy_count": int(safe_float(theme.get("limit_proxy_count"))),
        "breadth_proxy": round(breadth, 4),
        "median_ret5": safe_float(theme.get("median_ret5")),
        "median_ret20": safe_float(theme.get("median_ret20")),
        "median_vol_ratio": safe_float(theme.get("median_vol_ratio")),
        "score_breakdown_schema": "涨停家数/连板高度/板块成交额放大/政策产业业绩催化/龙头辨识度/板块扩散质量/次日承接可能性，各0-5",
        "score_breakdown_status": "TOTAL_ONLY_FROM_CURRENT_PLAN",
    }


def seed_rows_from_plan(plan: dict[str, Any], asof: date) -> list[dict[str, Any]]:
    plan_date = parse_date(plan.get("asof")) or parse_date(plan.get("data_latest")) or asof
    next_trade_date = parse_date(plan.get("next_trade_date"))
    rows: list[dict[str, Any]] = []
    for theme in plan.get("themes", []) if isinstance(plan.get("themes"), list) else []:
        snap = compact_theme_snapshot(theme)
        if not snap["theme"]:
            continue
        sample_id = f"{plan_date.isoformat()}::{snap['theme']}::{snap['phase']}"
        rows.append(
            {
                "sample_id": sample_id,
                "source": "A_SHARE_SHORT_PLAN",
                "discovery_date": plan_date.isoformat(),
                "next_trade_date": next_trade_date.isoformat() if next_trade_date else "",
                **snap,
                "review_status": "PENDING",
                "review_5d_due": (plan_date + timedelta(days=5)).isoformat(),
                "review_10d_due": (plan_date + timedelta(days=10)).isoformat(),
                "review_14d_due": (plan_date + timedelta(days=14)).isoformat(),
                "review_5d_result": "",
                "review_10d_result": "",
                "review_14d_result": "",
                "actual_path": "",
                "classification_correct": "",
                "error_type": "",
                "impact_on_plan": "",
                "review_notes": "",
                "created_at": asof.isoformat(),
                "updated_at": asof.isoformat(),
            }
        )
    return rows


def merge_rows(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], asof: date) -> list[dict[str, Any]]:
    by_id = {str(row.get("sample_id", "")): dict(row) for row in existing if row.get("sample_id")}
    for row in incoming:
        sample_id = str(row["sample_id"])
        if sample_id not in by_id:
            by_id[sample_id] = row
            continue
        old = by_id[sample_id]
        for key in [
            "score",
            "action",
            "reason",
            "member_count",
            "hot_count",
            "limit_proxy_count",
            "breadth_proxy",
            "median_ret5",
            "median_ret20",
            "median_vol_ratio",
            "next_trade_date",
        ]:
            old[key] = row.get(key, old.get(key, ""))
        old["updated_at"] = asof.isoformat()
        by_id[sample_id] = old
    return sorted(by_id.values(), key=lambda r: (str(r.get("discovery_date", "")), str(r.get("theme", ""))), reverse=True)


def due_horizons(row: dict[str, Any], asof: date) -> list[str]:
    if str(row.get("review_status", "PENDING")).upper() in {"DONE", "CLOSED"}:
        return []
    due = []
    for days in REVIEW_HORIZONS:
        key = f"review_{days}d"
        due_date = parse_date(row.get(f"{key}_due"))
        result = str(row.get(f"{key}_result", "")).strip()
        if due_date and due_date <= asof and not result:
            due.append(f"D{days}")
    return due


def build_summary(rows: list[dict[str, Any]], asof: date) -> dict[str, Any]:
    due = []
    pending = 0
    done = 0
    for row in rows:
        status = str(row.get("review_status", "PENDING")).upper()
        if status in {"DONE", "CLOSED"}:
            done += 1
        else:
            pending += 1
        horizons = due_horizons(row, asof)
        if horizons:
            item = dict(row)
            item["due_horizons"] = horizons
            due.append(item)
    due = sorted(due, key=lambda r: (str(r.get("discovery_date", "")), str(r.get("theme", ""))))
    return {
        "asof": asof.isoformat(),
        "sample_count": len(rows),
        "pending_count": pending,
        "done_count": done,
        "due_count": len(due),
        "due_reviews": due,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "sample_id",
        "source",
        "discovery_date",
        "next_trade_date",
        "theme",
        "score",
        "phase",
        "action",
        "reason",
        "member_count",
        "hot_count",
        "limit_proxy_count",
        "breadth_proxy",
        "median_ret5",
        "median_ret20",
        "median_vol_ratio",
        "score_breakdown_schema",
        "score_breakdown_status",
        "review_status",
        "review_5d_due",
        "review_10d_due",
        "review_14d_due",
        "review_5d_result",
        "review_10d_result",
        "review_14d_result",
        "actual_path",
        "classification_correct",
        "error_type",
        "impact_on_plan",
        "review_notes",
        "created_at",
        "updated_at",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_md(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# A股 Radar 主线分类准度 Ledger",
        "",
        f"- 日期：`{summary['asof']}`",
        f"- 样本数：`{summary['sample_count']}`",
        f"- 待复核：`{summary['pending_count']}`",
        f"- 到期复核：`{summary['due_count']}`",
        "",
        "## 到期复核",
        "",
    ]
    due = summary.get("due_reviews", [])
    if not due:
        lines.append("- 暂无到期复核项。")
    else:
        lines += [
            "| 发现日 | 主线 | 当时阶段 | 分数 | 到期 | 当时理由 | 需要填写 |",
            "| --- | --- | --- | ---: | --- | --- | --- |",
        ]
        for row in due[:20]:
            lines.append(
                f"| {row.get('discovery_date', '')} | {row.get('theme', '')} | {row.get('phase', '')} | "
                f"{row.get('score', '')} | {', '.join(row.get('due_horizons', []))} | "
                f"{str(row.get('reason', ''))[:80]} | actual_path / classification_correct / error_type / impact_on_plan |"
            )
    lines += [
        "",
        "## 最近样本",
        "",
        "| 发现日 | 主线 | 阶段 | 分数 | 广度代理 | 成员/强势/涨停代理 | 状态 |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in rows[:12]:
        lines.append(
            f"| {row.get('discovery_date', '')} | {row.get('theme', '')} | {row.get('phase', '')} | "
            f"{row.get('score', '')} | {row.get('breadth_proxy', '')} | "
            f"{row.get('member_count', '')}/{row.get('hot_count', '')}/{row.get('limit_proxy_count', '')} | "
            f"{row.get('review_status', '')} |"
        )
    lines += [
        "",
        "## 复核口径",
        "",
        "- `classification_correct`：YES / PARTIAL / NO。",
        "- `error_type`：too_early / too_late / climax_as_start / divergence_as_cooling / cooling_as_divergence / data_gap / other。",
        "- `impact_on_plan`：missed_entry / avoided_loss / false_watch / false_trade_candidate / no_impact。",
        "- 30 条完整样本前不改规则，只统计错误类型和触发环境。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain A-share Radar mainline classification accuracy ledger.")
    parser.add_argument("--plan-json", type=Path, default=DEFAULT_PLAN_JSON)
    parser.add_argument("--asof", default=str(date.today()))
    args = parser.parse_args()

    asof = parse_date(args.asof) or date.today()
    plan = read_json(args.plan_json, {})
    existing_payload = read_json(LEDGER_JSON, {})
    existing_rows = existing_payload.get("rows", []) if isinstance(existing_payload, dict) else []
    incoming = seed_rows_from_plan(plan, asof) if isinstance(plan, dict) else []
    rows = merge_rows(existing_rows, incoming, asof)
    summary = build_summary(rows, asof)
    payload = {**summary, "rows": rows}
    md = render_md(summary, rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    LEDGER_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(LEDGER_CSV, rows)
    DESKTOP_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(DESKTOP_CSV, rows)
    DESKTOP_MD.write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
