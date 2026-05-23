#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUTPUT_DIR = ROOT / "backtest_results" / "a_share_radar_daily_loop"


def run_step(name: str, cmd: list[str], skip: bool = False) -> dict[str, Any]:
    if skip:
        return {"name": name, "status": "skipped", "cmd": cmd, "stdout": "", "stderr": ""}
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    status = "ok" if proc.returncode == 0 else "failed"
    return {
        "name": name,
        "status": status,
        "returncode": proc.returncode,
        "cmd": cmd,
        "stdout": proc.stdout[-6000:],
        "stderr": proc.stderr[-6000:],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# A股 Radar 每日闭环运行结果",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- dry_run：`{payload['dry_run']}`",
        "",
        "| 步骤 | 状态 | 命令 |",
        "| --- | --- | --- |",
    ]
    for step in payload["steps"]:
        cmd = " ".join(step["cmd"])
        lines.append(f"| {step['name']} | `{step['status']}` | `{cmd}` |")
    lines += [
        "",
        "## 关键输出",
        "",
        f"- 复盘：`{REPORT_ROOT / 'A股短线Radar复盘_LATEST.md'}`",
        f"- 反哺：`{REPORT_ROOT / 'A股短线Radar复盘反哺_LATEST.md'}`",
        f"- K线补齐：`{REPORT_ROOT / 'A股短线Radar_K线补齐_LATEST.md'}`",
        f"- 规则过严样本追踪：`{REPORT_ROOT / 'A股短线Radar规则过严样本追踪_LATEST.md'}`",
        f"- 主线分类准度Ledger：`{REPORT_ROOT / 'A股Radar主线分类准度Ledger_LATEST.md'}`",
        f"- 人工主题证据Ledger：`{REPORT_ROOT / 'Theme_Evidence_人工搜集_LATEST.md'}`",
        f"- V6AB共性迁移评估：`{REPORT_ROOT / 'A股Radar_V6AB共性迁移评估_LATEST.md'}`",
        f"- 跨市场研究同步：`{REPORT_ROOT / '跨市场研究同步_LATEST.md'}`",
        f"- 晚间指导：`{REPORT_ROOT / 'A股短线Radar晚间操作指导_LATEST.html'}`",
        "",
    ]
    failed = [step for step in payload["steps"] if step["status"] == "failed"]
    if failed:
        lines += ["## 失败详情", ""]
        for step in failed:
            lines.append(f"### {step['name']}")
            lines.append("")
            lines.append("```text")
            lines.append(step.get("stderr") or step.get("stdout") or "no output")
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the A-share Radar daily review-feedback-backfill-guide loop.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--dry-run", action="store_true", help="Do not fetch Futu K-line data.")
    parser.add_argument("--skip-review", action="store_true", help="Use existing latest review instead of refreshing snapshots.")
    parser.add_argument("--skip-backfill", action="store_true", help="Do not run targeted K-line backfill.")
    parser.add_argument("--send-email", action="store_true")
    args = parser.parse_args()

    py = sys.executable
    steps: list[dict[str, Any]] = []
    steps.append(
        run_step(
            "review",
            [py, "a_share_short_radar_review.py", "--asof", args.asof],
            skip=args.skip_review,
        )
    )
    steps.append(run_step("feedback", [py, "a_share_radar_feedback.py", "--asof", args.asof]))
    backfill_cmd = [py, "a_share_radar_backfill.py", "--asof", args.asof]
    if args.dry_run:
        backfill_cmd.append("--dry-run")
    steps.append(run_step("targeted_kline_backfill", backfill_cmd, skip=args.skip_backfill))
    steps.append(run_step("strict_rule_tracker", [py, "a_share_radar_strict_rule_tracker.py", "--asof", args.asof]))
    steps.append(run_step("classification_accuracy_ledger", [py, "a_share_radar_classification_ledger.py", "--asof", args.asof]))
    steps.append(run_step("manual_theme_evidence_ledger", [py, "manual_theme_evidence_ledger.py", "--asof", args.asof]))
    steps.append(run_step("v6ab_transfer_review", [py, "a_share_radar_v6ab_transfer_review.py", "--asof", args.asof]))
    steps.append(run_step("cross_market_research_sync", [py, "cross_market_research_sync.py", "--asof", args.asof]))
    guide_cmd = [py, "a_share_short_radar_evening_guide.py", "--asof", args.asof]
    if args.send_email:
        guide_cmd.append("--send-email")
    steps.append(run_step("evening_guide", guide_cmd))

    payload = {
        "asof": args.asof,
        "dry_run": args.dry_run,
        "steps": steps,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    md = render_md(payload)
    (OUTPUT_DIR / "latest_daily_loop.md").write_text(md, encoding="utf-8")
    (OUTPUT_DIR / "latest_daily_loop.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_ROOT / "A股短线Radar每日闭环_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "A股短线Radar每日闭环_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(md)
    return 1 if any(step["status"] == "failed" for step in steps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
