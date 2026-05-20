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
OUT_DIR = ROOT / "backtest_results" / "v6ab_daily_evolution"


def run_step(name: str, cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return {
        "name": name,
        "cmd": cmd,
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout": proc.stdout[-6000:],
        "stderr": proc.stderr[-6000:],
    }


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def render_daily_report(asof: str, classifier: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    themes = classifier.get("themes", [])
    confirmed = [row for row in themes if row.get("state") == "CONFIRMED"]
    starter = [row for row in themes if row.get("state") == "STARTER"]
    candidates = [row for row in themes if row.get("state") == "CANDIDATE"]
    risk = [row for row in themes if row.get("state") == "RISK_REVIEW"]
    tickers = classifier.get("ticker_priority", [])

    lines = [
        "# V6AB Daily Mainline Report",
        "",
        f"- 日期：`{asof}`",
        f"- 当前模拟盘基线：`{classifier.get('active_baseline', 'V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING')}`",
        f"- 交易/模拟盘动作：`{classifier.get('paper_sim_action', 'NO_CHANGE_BACKTEST_ONLY')}`",
        f"- fallback 到 V2：`{classifier.get('fallback_to_v2', True)}`",
        f"- B sleeve cap hint：`{float(classifier.get('b_sleeve_cap_hint', 0.05)):.0%}`",
        "",
        "## 主线状态",
        "",
        f"- confirmed：{', '.join(row['label'] for row in confirmed) if confirmed else '无'}",
        f"- starter：{', '.join(row['label'] for row in starter) if starter else '无'}",
        f"- candidate：{', '.join(row['label'] for row in candidates[:5]) if candidates else '无'}",
        f"- risk review：{', '.join(row['label'] for row in risk) if risk else '无'}",
        "",
        "## Top Themes",
        "",
        "| theme | state | mainline | market | evidence | risk |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in themes[:8]:
        lines.append(
            f"| {row['label']} | `{row['state']}` | {row['mainline_score']:.1f} | "
            f"{row['market_score']:.1f} | {row['evidence_count']} | {row['risk_penalty']:.1f} |"
        )
    lines += [
        "",
        "## Ticker Triage",
        "",
        "| ticker | theme | score | evidence | 人工动作 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in tickers[:12]:
        manual = "P0复核" if row["score"] >= 80 else "观察" if row["score"] >= 35 else "低优先级"
        lines.append(f"| `{row['ticker']}` | {row['theme']} | {row['score']:.1f} | {row['evidence_count']} | {manual} |")
    lines += [
        "",
        "## 今日决策",
        "",
        "- 不替换 V6AB 模拟盘版本；继续使用 V2 作为 fallback/active paper sim。",
        "- 本报告只作为 V6-V3 研究输入，下一步接入回测比较。",
        "- 人工 triage 重点看高分 ticker 是否有真实订单/财报/估值支撑，以及是否只是拥挤交易。",
        "",
        "## 运行状态",
        "",
        "| step | status |",
        "| --- | --- |",
    ]
    for step in steps:
        lines.append(f"| {step['name']} | `{step['status']}` |")
    failed = [step for step in steps if step["status"] == "failed"]
    if failed:
        lines += ["", "## 失败详情", ""]
        for step in failed:
            lines.append(f"### {step['name']}")
            lines.append("```text")
            lines.append(step.get("stderr") or step.get("stdout") or "no output")
            lines.append("```")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run V6AB Daily Evolution v1.")
    parser.add_argument("--asof", default=str(date.today()))
    args = parser.parse_args()

    py = sys.executable
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    steps = [
        run_step("evidence_ledger", [py, "v6ab_evidence_ledger.py", "--asof", args.asof]),
        run_step("mainline_classifier", [py, "v6ab_mainline_classifier.py", "--asof", args.asof]),
        run_step("classifier_bridge_backtest", [py, "v6ab_classifier_bridge_backtest.py", "--asof", args.asof]),
    ]
    classifier = load_json(OUT_DIR / "latest_mainline_classifier.json")
    report = render_daily_report(args.asof, classifier, steps)
    payload = {"asof": args.asof, "steps": steps, "classifier": classifier}
    (OUT_DIR / "latest_daily_mainline_report.md").write_text(report, encoding="utf-8")
    (OUT_DIR / "latest_daily_evolution.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_ROOT / "V6AB_Daily_Mainline_Report_LATEST.md").write_text(report, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Daily_Evolution_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report)
    return 1 if any(step["status"] == "failed" for step in steps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
