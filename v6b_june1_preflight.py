#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "v6b_june1_preflight"
DESKTOP_DIR = Path("/Users/zhangkun/Desktop/AI个人投资公司")
PYTHON = Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3")

REQUIRED_SCRIPTS = [
    "v6b_fetch_radar_price_cache.py",
    "v6b_missing_opportunity_review.py",
    "v6b_universe_audit.py",
    "v6b_score_universe.py",
    "v6b_build_universe_config.py",
    "v6b_radar_momentum_challenger.py",
    "v6b_synthetic_historical_radar_generator.py",
    "v6b_synthetic_historical_challenger.py",
    "v6_allocator.py",
]

REQUIRED_CONFIGS = [
    "v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json",
    "v6_strategy_lab/configs/v6b_candidate_registry_v1.json",
    "v6_strategy_lab/configs/v6b_missing_opportunity_review_theme_map_v1.json",
    "v6_strategy_lab/configs/v6_allocator_sample_metrics.csv",
]

OPTIONAL_LATEST = [
    "backtest_results/v6b_missing_opportunity_review/latest.json",
    "backtest_results/v6_weekly_review/latest.json",
    "backtest_results/v6_research_backlog/latest.json",
]


def file_row(path_text: str, required: bool = True) -> dict[str, Any]:
    path = ROOT / path_text
    exists = path.exists()
    return {
        "path": path_text,
        "required": required,
        "exists": exists,
        "size": path.stat().st_size if exists else 0,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if exists else "",
        "status": "PASS" if exists else ("FAIL" if required else "WARN"),
    }


def help_row(script: str) -> dict[str, Any]:
    path = ROOT / script
    if not path.exists():
        return {"script": script, "status": "FAIL", "note": "脚本不存在"}
    result = subprocess.run([str(PYTHON), str(path), "--help"], cwd=ROOT, capture_output=True, text=True, timeout=20)
    if result.returncode == 0 and "usage:" in result.stdout:
        return {"script": script, "status": "PASS", "note": "命令入口可用"}
    note = (result.stderr or result.stdout or "").strip().splitlines()
    return {"script": script, "status": "FAIL", "note": note[0] if note else "help 检查失败"}


def discover_manifest() -> dict[str, Any]:
    roots = [
        ROOT / "v6_strategy_lab" / "configs" / "synthetic_history",
        ROOT / "backtest_results" / "v6b_synthetic_historical_radar_generator",
    ]
    manifests: list[Path] = []
    for root in roots:
        if root.exists():
            manifests.extend(root.rglob("manifest.json"))
    manifests = sorted(manifests, key=lambda path: path.stat().st_mtime, reverse=True)
    latest = manifests[0] if manifests else None
    return {
        "exists": latest is not None,
        "latest_manifest": str(latest.relative_to(ROOT)) if latest else "",
        "status": "PASS" if latest else "WARN",
        "note": "已有历史 manifest，可作为 fallback；6月1日仍应生成新 manifest。" if latest else "暂无 synthetic history manifest，6月1日必须先跑 generator。",
    }


def build_payload() -> dict[str, Any]:
    script_rows = [file_row(path) for path in REQUIRED_SCRIPTS]
    config_rows = [file_row(path) for path in REQUIRED_CONFIGS]
    latest_rows = [file_row(path, required=False) for path in OPTIONAL_LATEST]
    help_rows = [help_row(script) for script in REQUIRED_SCRIPTS]
    manifest = discover_manifest()

    failures = [row for row in [*script_rows, *config_rows, *help_rows] if row["status"] == "FAIL"]
    warnings = [row for row in [*latest_rows, manifest] if row["status"] == "WARN"]
    status = "BLOCKED" if failures else "READY_WITH_MANUAL_DATA_REFRESH"

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "failures": failures,
        "warnings": warnings,
        "scripts": script_rows,
        "configs": config_rows,
        "latest_outputs": latest_rows,
        "help_checks": help_rows,
        "synthetic_manifest": manifest,
        "known_manual_blockers": [
            "无法在 6月1日前自动验证 Futu 历史 K 线额度是否已刷新。",
            "不能提前跑需要新增历史 K 线额度的 fetch / refresh 任务。",
            "registry / universe 的人工晋级仍需当天 review 后确认。",
        ],
        "day_of_card": "V6B_2026-06-01_EXECUTION_CARD.md",
    }


def table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[str]:
    if not rows:
        return ["_None_"]
    out = ["| " + " | ".join(label for _, label in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(key, "")) for key, _ in columns) + " |")
    return out


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# 2026-06-01 V6-B 执行预检报告",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 当前状态：`{payload['status']}`",
        f"- 当天执行卡：`{payload['day_of_card']}`",
        "",
        "## 一句话结论",
        "",
    ]
    if payload["status"] == "BLOCKED":
        lines.append("- 当前存在脚本或配置缺失，6月1日不能直接开跑。")
    else:
        lines.append("- 脚本、配置和命令入口已具备；6月1日真正的剩余 blocker 是历史 K 线额度刷新和当天人工 triage。")

    lines.extend(["", "## 脚本文件", ""])
    lines.extend(table(payload["scripts"], [("path", "路径"), ("exists", "存在"), ("mtime", "更新时间"), ("status", "状态")]))
    lines.extend(["", "## 配置文件", ""])
    lines.extend(table(payload["configs"], [("path", "路径"), ("exists", "存在"), ("mtime", "更新时间"), ("status", "状态")]))
    lines.extend(["", "## 命令入口检查", ""])
    lines.extend(table(payload["help_checks"], [("script", "脚本"), ("status", "状态"), ("note", "说明")]))
    lines.extend(["", "## 最新产物", ""])
    lines.extend(table(payload["latest_outputs"], [("path", "路径"), ("exists", "存在"), ("mtime", "更新时间"), ("status", "状态")]))
    lines.extend(["", "## Synthetic History Manifest", ""])
    lines.append(f"- 状态：`{payload['synthetic_manifest']['status']}`")
    lines.append(f"- 最新 manifest：`{payload['synthetic_manifest']['latest_manifest'] or 'none'}`")
    lines.append(f"- 说明：{payload['synthetic_manifest']['note']}")
    lines.extend(["", "## 手动 blocker", ""])
    for item in payload["known_manual_blockers"]:
        lines.append(f"- {item}")
    lines.extend(["", "## 6月1日当天动作", ""])
    lines.append("- 直接按 `V6B_2026-06-01_EXECUTION_CARD.md` 执行；若 fetch 成功，再继续 Missing Opportunity Review / Universe Audit / Scorecard / Challenger / Allocator。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight V6-B 2026-06-01 execution chain without consuming K-line quota.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--sync-desktop", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    json_path = OUT_DIR / f"v6b_june1_preflight_{args.tag}.json"
    md_path = OUT_DIR / f"v6b_june1_preflight_{args.tag}.md"
    latest_json = OUT_DIR / "latest.json"
    latest_md = OUT_DIR / "latest.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, payload)
    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    if args.sync_desktop:
        (DESKTOP_DIR / "2026-06-01_V6B_执行预检报告.md").write_text(latest_md.read_text(encoding="utf-8"), encoding="utf-8")
        (DESKTOP_DIR / "2026-06-01_V6B_执行预检报告.json").write_text(latest_json.read_text(encoding="utf-8"), encoding="utf-8")

    print("== V6-B June 1 Preflight ==")
    print(f"Status: {payload['status']}")
    print(f"Report: {md_path}")
    print(f"JSON:   {json_path}")
    print(f"Sync desktop: {args.sync_desktop}")


if __name__ == "__main__":
    main()
