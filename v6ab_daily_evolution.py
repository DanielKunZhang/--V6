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


def render_daily_report(
    asof: str,
    classifier: dict[str, Any],
    steps: list[dict[str, Any]],
    promotion: dict[str, Any],
    boost_review: dict[str, Any],
    gate_experiment: dict[str, Any],
    pit_bridge: dict[str, Any],
) -> str:
    themes = classifier.get("themes", [])
    confirmed = [row for row in themes if row.get("state") == "CONFIRMED"]
    starter = [row for row in themes if row.get("state") == "STARTER"]
    candidates = [row for row in themes if row.get("state") == "CANDIDATE"]
    risk = [row for row in themes if row.get("state") == "RISK_REVIEW"]
    tickers = classifier.get("ticker_priority", [])
    promotion_decision = promotion.get("decision", {}) if isinstance(promotion.get("decision"), dict) else {}
    failed_checks = [
        row.get("check")
        for row in promotion.get("checks", [])
        if isinstance(row, dict) and not row.get("passed", False)
    ]
    boost_labels = boost_review.get("label_summary", []) if isinstance(boost_review.get("label_summary"), list) else []
    gate_ranked = gate_experiment.get("ranked", []) if isinstance(gate_experiment.get("ranked"), list) else []
    bridge_rows = pit_bridge.get("rows", []) if isinstance(pit_bridge.get("rows"), list) else []

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
        f"- PIT promotion gate：`{promotion_decision.get('tier', 'UNKNOWN')}` — {promotion_decision.get('action', '未生成')}",
        f"- 未通过 gate：{', '.join(failed_checks[:8]) if failed_checks else '无'}",
        f"- BOOST failure review：active={boost_review.get('active_boost_months', 0)}，negative={boost_review.get('negative_boost_months', 0)}，sum delta={float(boost_review.get('sum_tier_delta', 0.0)):+.2%}",
        "- 本报告只作为 V6-V3 研究输入，下一步接入回测比较。",
        "- 人工 triage 重点看高分 ticker 是否有真实订单/财报/估值支撑，以及是否只是拥挤交易。",
        "",
        "## BOOST 失败归因",
        "",
        "| label | count | sum tier delta |",
        "| --- | ---: | ---: |",
    ]
    for row in boost_labels[:8]:
        lines.append(f"| `{row.get('label')}` | {row.get('count', 0)} | {float(row.get('sum_tier_delta', 0.0)):+.2%} |")
    lines += [
        "",
        "## BOOST Gate 实验",
        "",
        "| candidate | kept | dropped | kept sum | improvement | positive damage | negative removed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in gate_ranked[:5]:
        lines.append(
            f"| `{row.get('candidate')}` | {row.get('kept_months', 0)} | {row.get('dropped_months', 0)} | "
            f"{float(row.get('kept_sum_delta', 0.0)):+.2%} | {float(row.get('improvement_vs_baseline', 0.0)):+.2%} | "
            f"{float(row.get('positive_damage', 0.0)):+.2%} | {float(row.get('negative_removed', 0.0)):+.2%} |"
        )
    lines += [
        "",
        "## PIT 候选对比",
        "",
        "| candidate | ann | maxDD | Sharpe | 2024-2026 ann | 2020 ann | active rebals |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in bridge_rows:
        if row.get("candidate") not in {
            "baseline_v2_v6ab_dynamic_b",
            "pit_tier_v6ab_dynamic_b",
            "pit_tier_turnover_guarded_v6ab_dynamic_b",
        }:
            continue
        stats = row.get("stats", {})
        periods = row.get("periods", {})
        turnover = row.get("turnover_cost", {})
        lines.append(
            f"| `{row.get('candidate')}` | {float(stats.get('ann_ret', 0.0)):+.2%} | "
            f"{float(stats.get('max_dd', 0.0)):+.2%} | {float(stats.get('sharpe', 0.0)):.2f} | "
            f"{float(periods.get('2024_2026', {}).get('ann_ret', 0.0)):+.2%} | "
            f"{float(periods.get('2020', {}).get('ann_ret', 0.0)):+.2%} | "
            f"{int(turnover.get('pit_active_rebalances', 0) or 0)} |"
        )
    lines += [
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
        run_step("pit_evidence_classifier_replay", [py, "v6ab_pit_evidence_replay.py", "--asof", args.asof]),
        run_step("pit_classifier_bridge_backtest", [py, "v6ab_pit_classifier_bridge_backtest.py", "--asof", args.asof]),
        run_step("pit_vs_v2_attribution", [py, "v6ab_pit_vs_v2_attribution.py", "--asof", args.asof]),
        run_step("promotion_gate", [py, "v6ab_promotion_gate.py", "--asof", args.asof]),
        run_step("pit_boost_failure_review", [py, "v6ab_pit_boost_failure_review.py", "--asof", args.asof]),
        run_step("boost_gate_experiment", [py, "v6ab_boost_gate_experiment.py", "--asof", args.asof]),
    ]
    classifier = load_json(OUT_DIR / "latest_mainline_classifier.json")
    promotion = load_json(ROOT / "backtest_results" / "v6ab_promotion_gate" / "latest.json")
    boost_review = load_json(ROOT / "backtest_results" / "v6ab_pit_boost_failure_review" / "latest.json")
    gate_experiment = load_json(ROOT / "backtest_results" / "v6ab_boost_gate_experiment" / "latest.json")
    pit_bridge = load_json(OUT_DIR / "latest_pit_classifier_bridge_backtest.json")
    report = render_daily_report(args.asof, classifier, steps, promotion, boost_review, gate_experiment, pit_bridge)
    payload = {
        "asof": args.asof,
        "steps": steps,
        "classifier": classifier,
        "promotion_gate": promotion,
        "boost_failure_review": boost_review,
        "boost_gate_experiment": gate_experiment,
        "pit_classifier_bridge_backtest": pit_bridge,
    }
    (OUT_DIR / "latest_daily_mainline_report.md").write_text(report, encoding="utf-8")
    (OUT_DIR / "latest_daily_evolution.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_ROOT / "V6AB_Daily_Mainline_Report_LATEST.md").write_text(report, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Daily_Evolution_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report)
    return 1 if any(step["status"] == "failed" for step in steps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
