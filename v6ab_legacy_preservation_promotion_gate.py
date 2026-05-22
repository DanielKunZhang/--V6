#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_legacy_preservation_promotion_gate"
DEFAULT_EXPERIMENT = ROOT / "backtest_results" / "v6ab_legacy_winner_preservation_experiment" / "latest.json"
DEFAULT_FALSE_NEGATIVE = ROOT / "backtest_results" / "v6ab_legacy_preservation_false_negative_audit" / "latest.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def row_by_candidate(payload: dict[str, Any], name: str) -> dict[str, Any]:
    for row in payload.get("rows", []):
        if row.get("candidate") == name:
            return row
    return {}


def get(row: dict[str, Any], path: list[str], default: float = 0.0) -> float:
    cur: Any = row
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    try:
        return float(cur)
    except Exception:
        return default


def delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    return {
        "ann": get(candidate, ["stats", "ann_ret"]) - get(baseline, ["stats", "ann_ret"]),
        "sharpe": get(candidate, ["stats", "sharpe"]) - get(baseline, ["stats", "sharpe"]),
        "max_dd": get(candidate, ["stats", "max_dd"]) - get(baseline, ["stats", "max_dd"]),
        "ann_2020": get(candidate, ["periods", "2020", "ann_ret"]) - get(baseline, ["periods", "2020", "ann_ret"]),
        "ann_2022": get(candidate, ["periods", "2022", "ann_ret"]) - get(baseline, ["periods", "2022", "ann_ret"]),
        "ann_2024_2026": get(candidate, ["periods", "2024_2026", "ann_ret"]) - get(baseline, ["periods", "2024_2026", "ann_ret"]),
        "cost": get(candidate, ["turnover_cost", "est_cost_drag"]) - get(baseline, ["turnover_cost", "est_cost_drag"]),
        "active": get(candidate, ["turnover_cost", "pit_active_rebalances"]),
    }


def build_checks(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    original: dict[str, Any],
    experiment: dict[str, Any],
    false_negative: dict[str, Any],
) -> list[dict[str, Any]]:
    vs_v2 = delta(candidate, baseline)
    vs_pit = delta(candidate, original)
    decision = experiment.get("decision", {}) if isinstance(experiment.get("decision"), dict) else {}
    fn_decision = false_negative.get("decision", {}) if isinstance(false_negative.get("decision"), dict) else {}
    return [
        {
            "check": "beats_v2_full_ann",
            "passed": vs_v2["ann"] >= 0.005,
            "value": vs_v2["ann"],
            "threshold": ">= +0.50pp",
            "reason": "保护层必须明显提高全区间收益，不能只是微小噪音。",
        },
        {
            "check": "beats_original_pit_full_ann",
            "passed": vs_pit["ann"] >= 0.003,
            "value": vs_pit["ann"],
            "threshold": ">= +0.30pp",
            "reason": "必须证明比当前 PIT guarded 更好，而不是只比 V2 好。",
        },
        {
            "check": "sharpe_improves_vs_v2",
            "passed": vs_v2["sharpe"] >= 0.02,
            "value": vs_v2["sharpe"],
            "threshold": ">= +0.02",
            "reason": "收益质量要改善。",
        },
        {
            "check": "drawdown_not_worse",
            "passed": vs_v2["max_dd"] >= -0.005,
            "value": vs_v2["max_dd"],
            "threshold": ">= -0.50pp",
            "reason": "防错保护不能增加重大回撤。",
        },
        {
            "check": "oos_2024_2026_not_worse_vs_pit",
            "passed": vs_pit["ann_2024_2026"] >= -0.002,
            "value": vs_pit["ann_2024_2026"],
            "threshold": ">= -0.20pp",
            "reason": "不能为了 2020 改善而牺牲近年 AI 主线。",
        },
        {
            "check": "stress_2020_materially_improves_vs_pit",
            "passed": vs_pit["ann_2020"] >= 0.03,
            "value": vs_pit["ann_2020"],
            "threshold": ">= +3.00pp",
            "reason": "本规则的核心价值是修复 2020 等非 AI 主线漏判。",
        },
        {
            "check": "stress_2022_not_worse_vs_pit",
            "passed": vs_pit["ann_2022"] >= -0.005,
            "value": vs_pit["ann_2022"],
            "threshold": ">= -0.50pp",
            "reason": "熊市年份不能因保护层恶化。",
        },
        {
            "check": "turnover_not_higher_than_original_pit",
            "passed": vs_pit["cost"] <= 0.002,
            "value": vs_pit["cost"],
            "threshold": "<= +0.20pp cost drag",
            "reason": "保护层不应通过更高换手实现收益。",
        },
        {
            "check": "enough_preserved_months_for_watch",
            "passed": int(decision.get("qualified_preserved_months", 0) or 0) >= 5,
            "value": int(decision.get("qualified_preserved_months", 0) or 0),
            "threshold": ">= 5 preserved months",
            "reason": "样本太少只能保留研究，不能升 WATCH。",
        },
        {
            "check": "no_bad_preserved_months",
            "passed": int(decision.get("qualified_bad_preserved_months", 0) or 0) == 0,
            "value": int(decision.get("qualified_bad_preserved_months", 0) or 0),
            "threshold": "== 0",
            "reason": "保护触发月不能出现明显坏样本。",
        },
        {
            "check": "false_negative_audit_passed",
            "passed": fn_decision.get("tier") == "PASS_FALSE_NEGATIVE_AUDIT",
            "value": fn_decision.get("tier", "UNKNOWN"),
            "threshold": "PASS_FALSE_NEGATIVE_AUDIT",
            "reason": "必须证明跳过保护没有漏掉真实 legacy 主线。",
        },
        {
            "check": "false_negative_risk_zero",
            "passed": int(fn_decision.get("false_negative_risk_count", 0) or 0) == 0,
            "value": int(fn_decision.get("false_negative_risk_count", 0) or 0),
            "threshold": "== 0",
            "reason": "不能存在明确漏保风险。",
        },
        {
            "check": "not_paper_sim_candidate_yet",
            "passed": False,
            "value": "RESEARCH_LAYER_ONLY",
            "threshold": "requires independent forward paper observation",
            "reason": "这是保护层，不是完整 PIT classifier 替代版本；即使指标通过，也只能升 WATCH/RESEARCH_OVERLAY。",
        },
    ]


def decide(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [row["check"] for row in checks if not row["passed"]]
    hard_for_watch = {
        "beats_v2_full_ann",
        "beats_original_pit_full_ann",
        "sharpe_improves_vs_v2",
        "drawdown_not_worse",
        "oos_2024_2026_not_worse_vs_pit",
        "stress_2020_materially_improves_vs_pit",
        "stress_2022_not_worse_vs_pit",
        "no_bad_preserved_months",
        "false_negative_audit_passed",
        "false_negative_risk_zero",
    }
    if not (hard_for_watch & set(failed)):
        return {
            "tier": "WATCH",
            "action": "qualified legacy preservation 可进入 WATCH，继续做 forward paper 观察；不替换 V2 模拟盘。",
            "failed_checks": failed,
        }
    if "false_negative_audit_passed" in failed or "false_negative_risk_zero" in failed:
        return {
            "tier": "REJECT_FOR_NOW",
            "action": "漏保审计未通过，不能继续晋级。",
            "failed_checks": failed,
        }
    return {
        "tier": "RESEARCH_OVERLAY",
        "action": "方向有效但仍需继续研究；不替换 V2 模拟盘。",
        "failed_checks": failed,
    }


def render_md(payload: dict[str, Any]) -> str:
    decision = payload["decision"]
    candidate = payload["candidate"]
    baseline = payload["baseline"]
    original = payload["original_pit"]
    vs_v2 = payload["delta_vs_v2"]
    vs_pit = payload["delta_vs_original_pit"]
    lines = [
        "# V6AB Legacy Preservation Promotion Gate",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- candidate：`{candidate.get('candidate')}`",
        f"- baseline：`{baseline.get('candidate')}`",
        f"- original PIT：`{original.get('candidate')}`",
        f"- promotion tier：`{decision['tier']}`",
        f"- action：{decision['action']}",
        "- 模拟盘动作：`NO_CHANGE`。",
        "",
        "## Core Comparison",
        "",
        "| metric | vs V2 | vs original PIT |",
        "| --- | ---: | ---: |",
        f"| ann | {fmt_pct(vs_v2['ann'])} | {fmt_pct(vs_pit['ann'])} |",
        f"| Sharpe | {vs_v2['sharpe']:+.2f} | {vs_pit['sharpe']:+.2f} |",
        f"| maxDD | {fmt_pct(vs_v2['max_dd'])} | {fmt_pct(vs_pit['max_dd'])} |",
        f"| 2020 ann | {fmt_pct(vs_v2['ann_2020'])} | {fmt_pct(vs_pit['ann_2020'])} |",
        f"| 2022 ann | {fmt_pct(vs_v2['ann_2022'])} | {fmt_pct(vs_pit['ann_2022'])} |",
        f"| 2024-2026 ann | {fmt_pct(vs_v2['ann_2024_2026'])} | {fmt_pct(vs_pit['ann_2024_2026'])} |",
        f"| cost drag | {fmt_pct(vs_v2['cost'])} | {fmt_pct(vs_pit['cost'])} |",
        "",
        "## Gate Checks",
        "",
        "| check | result | value | threshold | reason |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in payload["checks"]:
        value = row["value"]
        if isinstance(value, float):
            value_text = f"{value:+.2f}" if "sharpe" in row["check"] else fmt_pct(value)
        else:
            value_text = str(value)
        lines.append(
            f"| `{row['check']}` | {'PASS' if row['passed'] else 'FAIL'} | {value_text} | {row['threshold']} | {row['reason']} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- 这个 gate 只评估 qualified legacy preservation 保护层，不代表完整 PIT classifier 可以替换 V2。",
        "- `WATCH` 表示可继续做 forward paper 观察和更严格 promotion 检查；仍不允许动当前 V2 模拟盘。",
        "- `not_paper_sim_candidate_yet` 固定失败，用来防止保护层被误解为完整模拟盘替代版本。",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Promotion gate for V6AB qualified legacy preservation guard.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--experiment-json", type=Path, default=DEFAULT_EXPERIMENT)
    parser.add_argument("--false-negative-json", type=Path, default=DEFAULT_FALSE_NEGATIVE)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    experiment = load_json(args.experiment_json)
    false_negative = load_json(args.false_negative_json)
    baseline = row_by_candidate(experiment, "baseline_v2_v6ab_dynamic_b")
    original = row_by_candidate(experiment, "original_pit_guarded_v6ab_dynamic_b")
    candidate = row_by_candidate(experiment, "legacy_preserve_qualified_v6ab_dynamic_b")
    if not baseline or not original or not candidate:
        raise SystemExit("missing baseline/original/candidate rows")
    checks = build_checks(candidate, baseline, original, experiment, false_negative)
    decision = decide(checks)
    payload = {
        "asof": args.asof,
        "experiment_json": str(args.experiment_json),
        "false_negative_json": str(args.false_negative_json),
        "baseline": baseline,
        "original_pit": original,
        "candidate": candidate,
        "delta_vs_v2": delta(candidate, baseline),
        "delta_vs_original_pit": delta(candidate, original),
        "checks": checks,
        "decision": decision,
    }
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Legacy_Preservation_Promotion_Gate_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Legacy_Preservation_Promotion_Gate_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
