#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_DIR = Path("/Users/zhangkun/Desktop/AI个人投资公司")
SEED = ROOT / "us_radar_13f_system_input_seed.csv"
OUT_DIR = ROOT / "backtest_results" / "us_radar_13f_system_input"

FIELDS = [
    "quarter",
    "as_of",
    "ticker",
    "theme",
    "source_managers",
    "institutional_validation",
    "institutional_hedge_signal",
    "crowding_penalty",
    "reflexivity_score",
    "macro_regime_fit",
    "system_score",
    "position_role",
    "next_system_action",
    "review_deadline",
    "priority",
    "status",
    "no_trade_reason",
    "system_effect",
]


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def compute_system_effect(row: dict[str, Any]) -> str:
    role = row.get("position_role", "")
    priority = row.get("priority", "")
    crowding = to_int(row.get("crowding_penalty"))
    validation = to_int(row.get("institutional_validation"))
    reflexivity = to_int(row.get("reflexivity_score"))
    if crowding >= 5:
        return "risk_control_first"
    if role == "V6B_candidate" and validation >= 4:
        return "candidate_quality_upgrade"
    if reflexivity >= 5:
        return "reflexivity_risk_watch"
    if priority in {"P0", "P1"}:
        return "research_priority"
    return "archive_only"


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    validation = to_int(row.get("institutional_validation"))
    hedge = 1 if row.get("institutional_hedge_signal", "").strip().lower() not in {"", "none", "no"} else 0
    crowding = to_int(row.get("crowding_penalty"))
    reflexivity = to_int(row.get("reflexivity_score"))
    macro = to_int(row.get("macro_regime_fit"))
    system_score = validation * 2 + hedge + macro + reflexivity - crowding
    out = dict(row)
    out["ticker"] = str(out.get("ticker", "")).strip().upper()
    out["system_score"] = system_score
    out["system_effect"] = compute_system_effect(out)
    return {field: out.get(field, "") for field in FIELDS}


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

    def key(row: dict[str, Any]) -> tuple[int, str, int]:
        return (
            order.get(str(row.get("priority", "")), 9),
            str(row.get("review_deadline", "9999-12-31")),
            -to_int(row.get("system_score")),
        )

    return sorted(rows, key=key)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_md(path: Path, rows: list[dict[str, Any]], tag: str) -> None:
    open_rows = [r for r in rows if str(r.get("status", "")).upper() == "OPEN"]
    p0 = [r for r in open_rows if r.get("priority") == "P0"]
    p1 = [r for r in open_rows if r.get("priority") == "P1"]
    lines = [
        "# US Radar 13F System Input",
        "",
        f"- Tag: `{tag}`",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Open P0: `{len(p0)}`",
        f"- Open P1: `{len(p1)}`",
        "",
        "## 使用规则",
        "",
        "- 这张表是系统输入，不是展示文档，也不是买入清单。",
        "- `system_effect` 决定它反哺候选质量、风险控制、反身性监控还是只归档。",
        "- `next_system_action` 必须进入 Daily Board / V6-B refresh / Radar 复盘之一；否则 13F 学习无效。",
        "- 任何 13F 信号都不能单独解锁仓位。",
        "",
        "## P0/P1 动作",
        "",
        "| 优先级 | 标的 | 主题 | 角色 | 系统效果 | 截止 | 下一步 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in [r for r in open_rows if r.get("priority") in {"P0", "P1"}]:
        lines.append(
            f"| {row['priority']} | `{row['ticker']}` | {row['theme']} | {row['position_role']} | "
            f"{row['system_effect']} | {row['review_deadline']} | {row['next_system_action']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_payload(tag: str) -> dict[str, Any]:
    rows = sort_rows([normalize_row(row) for row in read_rows(SEED)])
    open_rows = [row for row in rows if str(row.get("status", "")).upper() == "OPEN"]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "seed": str(SEED),
        "as_of": str(date.today()),
        "row_count": len(rows),
        "open_p0_count": sum(1 for row in open_rows if row.get("priority") == "P0"),
        "open_p1_count": sum(1 for row in open_rows if row.get("priority") == "P1"),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build machine-readable 13F system input for US Radar/V6-B.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--sync-desktop", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload(args.tag)
    rows = payload["rows"]

    json_path = OUT_DIR / f"us_radar_13f_system_input_{args.tag}.json"
    csv_path = OUT_DIR / f"us_radar_13f_system_input_{args.tag}.csv"
    md_path = OUT_DIR / f"us_radar_13f_system_input_{args.tag}.md"
    latest_json = OUT_DIR / "latest.json"
    latest_csv = OUT_DIR / "latest.csv"
    latest_md = OUT_DIR / "latest.md"

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(json_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    write_csv(csv_path, rows)
    write_csv(latest_csv, rows)
    write_md(md_path, rows, args.tag)
    write_md(latest_md, rows, args.tag)

    if args.sync_desktop:
        out_dir = DESKTOP_DIR / "报表输出" / "LATEST"
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest_md, out_dir / "US_Radar_13F系统输入_LATEST.md")
        shutil.copy2(latest_csv, out_dir / "US_Radar_13F系统输入_LATEST.csv")
        shutil.copy2(latest_json, out_dir / "US_Radar_13F系统输入_LATEST.json")

    print("== US Radar 13F System Input ==")
    print(f"Rows: {payload['row_count']}")
    print(f"Open P0: {payload['open_p0_count']}")
    print(f"Open P1: {payload['open_p1_count']}")
    print(f"Markdown: {md_path}")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Sync desktop: {args.sync_desktop}")


if __name__ == "__main__":
    main()
