#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_promotion_gate"
DEFAULT_BACKTEST = ROOT / "backtest_results" / "v6ab_daily_evolution" / "latest_pit_classifier_bridge_backtest.json"
DEFAULT_ATTRIBUTION = ROOT / "backtest_results" / "v6ab_daily_evolution" / "latest_pit_vs_v2_attribution.json"
DEFAULT_HINDSIGHT = ROOT / "backtest_results" / "v6ab_v2_hindsight_audit" / "latest.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def row_by_candidate(backtest: dict[str, Any], candidate: str) -> dict[str, Any]:
    for row in backtest.get("rows", []):
        if row.get("candidate") == candidate:
            return row
    return {}


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def safe_get(row: dict[str, Any], path: list[str], default: float = 0.0) -> float:
    cur: Any = row
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    try:
        return float(cur)
    except Exception:
        return default


def metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    return {
        "ann_delta": safe_get(candidate, ["stats", "ann_ret"]) - safe_get(baseline, ["stats", "ann_ret"]),
        "max_dd_delta": safe_get(candidate, ["stats", "max_dd"]) - safe_get(baseline, ["stats", "max_dd"]),
        "sharpe_delta": safe_get(candidate, ["stats", "sharpe"]) - safe_get(baseline, ["stats", "sharpe"]),
        "ann_2020_delta": safe_get(candidate, ["periods", "2020", "ann_ret"]) - safe_get(baseline, ["periods", "2020", "ann_ret"]),
        "ann_2022_delta": safe_get(candidate, ["periods", "2022", "ann_ret"]) - safe_get(baseline, ["periods", "2022", "ann_ret"]),
        "ann_2024_2026_delta": safe_get(candidate, ["periods", "2024_2026", "ann_ret"]) - safe_get(baseline, ["periods", "2024_2026", "ann_ret"]),
        "cost_delta": safe_get(candidate, ["turnover_cost", "est_cost_drag"]) - safe_get(baseline, ["turnover_cost", "est_cost_drag"]),
        "pit_active_rebalances": safe_get(candidate, ["turnover_cost", "pit_active_rebalances"]),
    }


def hindsight_rows(hindsight: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row.get("scenario", ""): row for row in hindsight.get("scenario_deltas", [])}


def score_checks(candidate: dict[str, Any], baseline: dict[str, Any], attribution: dict[str, Any], hindsight: dict[str, Any]) -> list[dict[str, Any]]:
    delta = metric_delta(candidate, baseline)
    hrows = hindsight_rows(hindsight)
    semis_drop = abs(float(hrows.get("remove_semis_ai_theme", {}).get("v6ab_ann_delta", 0.0)))
    top5_drop = abs(float(hrows.get("remove_top5_contributor_tickers", {}).get("v6ab_ann_delta", 0.0)))
    proxy_drop = abs(float(hrows.get("proxy_only_no_stocks", {}).get("v6ab_ann_delta", 0.0)))
    tier_summary = attribution.get("tier_summary", {}) if isinstance(attribution.get("tier_summary"), dict) else {}
    boost = tier_summary.get("BOOST", {})
    override = tier_summary.get("OVERRIDE", {})
    periods = attribution.get("periods", {}) if isinstance(attribution.get("periods"), dict) else {}

    return [
        {
            "check": "full_ann_close_to_v2",
            "passed": delta["ann_delta"] >= -0.01,
            "value": delta["ann_delta"],
            "threshold": ">= -1.00pp",
            "reason": "候选不能明显牺牲全区间年化。",
        },
        {
            "check": "full_sharpe_close_to_v2",
            "passed": delta["sharpe_delta"] >= -0.05,
            "value": delta["sharpe_delta"],
            "threshold": ">= -0.05",
            "reason": "不能用更差收益质量换取叙事正确。",
        },
        {
            "check": "max_drawdown_not_materially_worse",
            "passed": delta["max_dd_delta"] >= -0.02,
            "value": delta["max_dd_delta"],
            "threshold": ">= -2.00pp",
            "reason": "全区间最大回撤不能明显恶化。",
        },
        {
            "check": "oos_2024_2026_not_worse",
            "passed": delta["ann_2024_2026_delta"] >= -0.01,
            "value": delta["ann_2024_2026_delta"],
            "threshold": ">= -1.00pp",
            "reason": "近年 OOS 不能明显落后 V2。",
        },
        {
            "check": "stress_2020_not_missed",
            "passed": delta["ann_2020_delta"] >= -0.03,
            "value": delta["ann_2020_delta"],
            "threshold": ">= -3.00pp",
            "reason": "不能明显错过 2020 这种强主线年份。",
        },
        {
            "check": "stress_2022_not_worse",
            "passed": delta["ann_2022_delta"] >= -0.02,
            "value": delta["ann_2022_delta"],
            "threshold": ">= -2.00pp",
            "reason": "熊市/加息年不能显著更差。",
        },
        {
            "check": "turnover_cost_control",
            "passed": delta["cost_delta"] <= 0.12,
            "value": delta["cost_delta"],
            "threshold": "<= +12.00pp est cost drag",
            "reason": "研究阶段可容忍额外换手，但不能无限制加成本。",
        },
        {
            "check": "pit_active_enough_to_evaluate",
            "passed": delta["pit_active_rebalances"] >= 30,
            "value": delta["pit_active_rebalances"],
            "threshold": ">= 30 active rebals",
            "reason": "活跃样本不足时不能解释成策略有效。",
        },
        {
            "check": "boost_month_quality_positive",
            "passed": float(boost.get("sum_delta", 0.0) or 0.0) >= -0.05,
            "value": float(boost.get("sum_delta", 0.0) or 0.0),
            "threshold": ">= -5.00pp sum delta",
            "reason": "BOOST 作为增强层，不能长期拖累 V2。",
        },
        {
            "check": "override_evidence_exists",
            "passed": int(override.get("count", 0) or 0) > 0,
            "value": int(override.get("count", 0) or 0),
            "threshold": "> 0 OVERRIDE months",
            "reason": "没有 OVERRIDE，说明系统尚未证明可排他替换 V2。",
        },
        {
            "check": "beats_degraded_v2_hindsight_baselines",
            "passed": (
                safe_get(candidate, ["stats", "ann_ret"]) > float(hrows.get("remove_top5_contributor_tickers", {}).get("v6ab_ann", 0.0))
                and safe_get(candidate, ["stats", "ann_ret"]) > float(hrows.get("remove_semis_ai_theme", {}).get("v6ab_ann", 0.0))
            ),
            "value": safe_get(candidate, ["stats", "ann_ret"]),
            "threshold": "ann > V2 without semis_ai and without top5 contributors",
            "reason": "候选至少要证明比去后视镜暴露后的 V2 更有价值。",
        },
        {
            "check": "hindsight_dependency_material_and_disclosed",
            "passed": semis_drop >= 0.05 and top5_drop >= 0.04 and proxy_drop >= 0.08,
            "value": {"semis_drop": semis_drop, "top5_drop": top5_drop, "proxy_drop": proxy_drop},
            "threshold": "V2 fragility disclosed",
            "reason": "晋级报告必须显式披露 V2 的静态赢家依赖。",
        },
        {
            "check": "period_attribution_no_hidden_failure",
            "passed": float(periods.get("2024_2026", {}).get("tier_sum_delta", 0.0) or 0.0) >= -0.02,
            "value": float(periods.get("2024_2026", {}).get("tier_sum_delta", 0.0) or 0.0),
            "threshold": "2024-2026 tier sum delta >= -2.00pp",
            "reason": "近年主线识别不能在归因层隐藏显著拖累。",
        },
    ]


def decide_tier(checks: list[dict[str, Any]], candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    failed = [row["check"] for row in checks if not row["passed"]]
    hard_required = {
        "full_ann_close_to_v2",
        "full_sharpe_close_to_v2",
        "max_drawdown_not_materially_worse",
        "oos_2024_2026_not_worse",
        "stress_2020_not_missed",
        "boost_month_quality_positive",
        "override_evidence_exists",
    }
    if not failed:
        return {"tier": "PRODUCTION_ELIGIBLE", "action": "可进入最终人工确认；仍不自动替换模拟盘。"}
    if not (hard_required & set(failed)):
        return {"tier": "PAPER_SIM_CANDIDATE", "action": "可考虑进入 paper sim 候选，但仍需人工 gate。"}
    if "beats_degraded_v2_hindsight_baselines" not in failed and "pit_active_enough_to_evaluate" not in failed:
        return {"tier": "RESEARCH_OVERLAY", "action": "只能作为 V2 overlay/研究层继续改进，不能替换 V2。"}
    if safe_get(candidate, ["stats", "ann_ret"]) > 0 and safe_get(candidate, ["stats", "sharpe"]) > 0:
        return {"tier": "WATCH", "action": "保留观察；需要补 evidence/fact precision 后再评估。"}
    return {"tier": "REJECTED", "action": "拒绝当前候选；不要继续围绕该版本优化。"}


def render_md(payload: dict[str, Any]) -> str:
    candidate = payload["candidate"]
    baseline = payload["baseline"]
    decision = payload["decision"]
    delta = payload["delta"]
    lines = [
        "# V6AB PIT Promotion Gate",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- candidate：`{candidate.get('candidate')}`",
        f"- baseline：`{baseline.get('candidate')}`",
        f"- promotion tier：`{decision['tier']}`",
        f"- action：{decision['action']}",
        "- 模拟盘动作：`NO_CHANGE`，继续保持 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`。",
        "",
        "## Core Comparison",
        "",
        "| metric | V2 | candidate | delta |",
        "| --- | ---: | ---: | ---: |",
        f"| ann | {fmt_pct(safe_get(baseline, ['stats', 'ann_ret']))} | {fmt_pct(safe_get(candidate, ['stats', 'ann_ret']))} | {fmt_pct(delta['ann_delta'])} |",
        f"| maxDD | {fmt_pct(safe_get(baseline, ['stats', 'max_dd']))} | {fmt_pct(safe_get(candidate, ['stats', 'max_dd']))} | {fmt_pct(delta['max_dd_delta'])} |",
        f"| Sharpe | {safe_get(baseline, ['stats', 'sharpe']):.2f} | {safe_get(candidate, ['stats', 'sharpe']):.2f} | {delta['sharpe_delta']:+.2f} |",
        f"| 2020 ann | {fmt_pct(safe_get(baseline, ['periods', '2020', 'ann_ret']))} | {fmt_pct(safe_get(candidate, ['periods', '2020', 'ann_ret']))} | {fmt_pct(delta['ann_2020_delta'])} |",
        f"| 2022 ann | {fmt_pct(safe_get(baseline, ['periods', '2022', 'ann_ret']))} | {fmt_pct(safe_get(candidate, ['periods', '2022', 'ann_ret']))} | {fmt_pct(delta['ann_2022_delta'])} |",
        f"| 2024-2026 ann | {fmt_pct(safe_get(baseline, ['periods', '2024_2026', 'ann_ret']))} | {fmt_pct(safe_get(candidate, ['periods', '2024_2026', 'ann_ret']))} | {fmt_pct(delta['ann_2024_2026_delta'])} |",
        f"| est cost drag | {fmt_pct(safe_get(baseline, ['turnover_cost', 'est_cost_drag']))} | {fmt_pct(safe_get(candidate, ['turnover_cost', 'est_cost_drag']))} | {fmt_pct(delta['cost_delta'])} |",
        "",
        "## Gate Checks",
        "",
        "| check | result | value | threshold | reason |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in payload["checks"]:
        value = row["value"]
        if isinstance(value, dict):
            value_text = ", ".join(f"{k}={fmt_pct(float(v))}" for k, v in value.items())
        elif row["check"] in {"full_sharpe_close_to_v2"}:
            value_text = f"{float(value):+.2f}"
        elif row["check"] in {"pit_active_enough_to_evaluate", "override_evidence_exists"}:
            value_text = f"{float(value):.0f}"
        elif isinstance(value, (int, float)):
            value_text = fmt_pct(float(value)) if abs(float(value)) <= 1.5 and "rebalances" not in row["check"] and "months" not in row["check"] else f"{value:.2f}"
        else:
            value_text = str(value)
        lines.append(f"| `{row['check']}` | {'PASS' if row['passed'] else 'FAIL'} | {value_text} | {row['threshold']} | {row['reason']} |")
    lines += [
        "",
        "## Interpretation",
        "",
        "- 当前 gate 把 V2 后视镜审计纳入晋级标准：候选不只要看起来接近 V2，还要解释 V2 对静态赢家池的依赖。",
        "- `RESEARCH_OVERLAY` 表示方向可继续，但只能作为 V2 增强/研究输入，不能排他替换 V2。",
        "- `PAPER_SIM_CANDIDATE` 以上才允许讨论是否进入模拟盘候选；`PRODUCTION_ELIGIBLE` 才允许最后人工确认是否动模拟盘/生产。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate V6AB PIT candidate promotion against V2 and hindsight audit.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--backtest-json", type=Path, default=DEFAULT_BACKTEST)
    parser.add_argument("--attribution-json", type=Path, default=DEFAULT_ATTRIBUTION)
    parser.add_argument("--hindsight-json", type=Path, default=DEFAULT_HINDSIGHT)
    parser.add_argument("--candidate", default="pit_tier_v6ab_dynamic_b")
    parser.add_argument("--baseline", default="baseline_v2_v6ab_dynamic_b")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    backtest = load_json(args.backtest_json)
    attribution = load_json(args.attribution_json)
    hindsight = load_json(args.hindsight_json)
    baseline = row_by_candidate(backtest, args.baseline)
    candidate = row_by_candidate(backtest, args.candidate)
    if not baseline or not candidate:
        raise SystemExit(f"missing baseline/candidate in {args.backtest_json}")

    checks = score_checks(candidate, baseline, attribution, hindsight)
    delta = metric_delta(candidate, baseline)
    decision = decide_tier(checks, candidate, baseline)
    payload = {
        "asof": args.asof,
        "backtest_json": str(args.backtest_json),
        "attribution_json": str(args.attribution_json),
        "hindsight_json": str(args.hindsight_json),
        "baseline": baseline,
        "candidate": candidate,
        "delta": delta,
        "checks": checks,
        "decision": decision,
    }
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md + "\n", encoding="utf-8")
    pd.DataFrame(checks).to_csv(args.output_dir / "latest_checks.csv", index=False)
    (REPORT_ROOT / "V6AB_Promotion_Gate_LATEST.md").write_text(md + "\n", encoding="utf-8")
    (REPORT_ROOT / "V6AB_Promotion_Gate_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
