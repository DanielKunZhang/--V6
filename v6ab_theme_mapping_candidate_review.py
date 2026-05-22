#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import v6ab_classifier_bridge_backtest as bridge
import v6ab_pit_classifier_bridge_backtest as pit
import v6b_theme_rotation_backtest as bt
from v6ab_pit_vs_v2_attribution import monthly_return
from v6ab_risk_skill_gate_experiment import active_cap_from_snapshots, build_base_curves, period_stats, run_dynamic_candidate
from v6ab_theme_mapping_experiment import apply_mapping, platform_parent_conflict_to_technology


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_theme_mapping_candidate_review"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def stats_row(eq: pd.Series, decisions: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "stats": bt.stats(eq),
        "periods": {
            "2020": period_stats(eq, "2020-01-01", "2020-12-31"),
            "2022": period_stats(eq, "2022-01-01", "2022-12-31"),
            "2024_2026": period_stats(eq, "2024-01-01", args.end),
        },
        "turnover_cost": pit.decision_metrics(decisions),
    }


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


def deltas(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    return {
        "ann_delta": safe_get(candidate, ["stats", "ann_ret"]) - safe_get(baseline, ["stats", "ann_ret"]),
        "max_dd_delta": safe_get(candidate, ["stats", "max_dd"]) - safe_get(baseline, ["stats", "max_dd"]),
        "sharpe_delta": safe_get(candidate, ["stats", "sharpe"]) - safe_get(baseline, ["stats", "sharpe"]),
        "ann_2020_delta": safe_get(candidate, ["periods", "2020", "ann_ret"]) - safe_get(baseline, ["periods", "2020", "ann_ret"]),
        "ann_2022_delta": safe_get(candidate, ["periods", "2022", "ann_ret"]) - safe_get(baseline, ["periods", "2022", "ann_ret"]),
        "ann_2024_2026_delta": safe_get(candidate, ["periods", "2024_2026", "ann_ret"])
        - safe_get(baseline, ["periods", "2024_2026", "ann_ret"]),
        "active_rebalances_delta": safe_get(candidate, ["turnover_cost", "pit_active_rebalances"])
        - safe_get(baseline, ["turnover_cost", "pit_active_rebalances"]),
        "cost_delta": safe_get(candidate, ["turnover_cost", "est_cost_drag"])
        - safe_get(baseline, ["turnover_cost", "est_cost_drag"]),
    }


def summarize_monthly(rows: list[dict[str, Any]], start: str, end: str) -> dict[str, Any]:
    seg = [row for row in rows if start <= row["date"] <= end]
    if not seg:
        return {"count": 0}
    values = [float(row["candidate_minus_v2"]) for row in seg]
    active = [row for row in seg if row.get("candidate_active")]
    return {
        "count": len(seg),
        "active": len(active),
        "sum_delta": float(np.sum(values)),
        "avg_delta": float(np.mean(values)),
        "win_rate": float(np.mean([value > 0 for value in values])),
        "negative_months": int(np.sum([value < 0 for value in values])),
    }


def build_monthly_rows(
    baseline_v6ab: pd.Series,
    candidate_v6ab: pd.Series,
    baseline_decisions: list[dict[str, Any]],
    candidate_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    decision_dates = [row["date"] for row in baseline_decisions]
    base_rets = monthly_return(baseline_v6ab, decision_dates)
    cand_rets = monthly_return(candidate_v6ab, decision_dates)
    candidate_by_date = {row["date"]: row for row in candidate_decisions}
    rows = []
    for raw_date in decision_dates[:-1]:
        if raw_date not in base_rets:
            continue
        cand = candidate_by_date.get(raw_date, {})
        base_ret = float(base_rets.get(raw_date, 0.0))
        cand_ret = float(cand_rets.get(raw_date, 0.0))
        rows.append(
            {
                "date": raw_date,
                "candidate_active": bool(cand and not cand.get("fallback_to_v2", True)),
                "pit_signal_tier": cand.get("pit_signal_tier", "WATCH"),
                "pit_boost_allowlist": cand.get("pit_boost_allowlist", []),
                "pit_override_allowlist": cand.get("pit_override_allowlist", []),
                "v2_next_ret": base_ret,
                "candidate_next_ret": cand_ret,
                "candidate_minus_v2": cand_ret - base_ret,
                "candidate_turnover": float(cand.get("turnover", 0.0) or 0.0),
                "candidate_selected": ", ".join(
                    f"{item.get('theme_id')}:{item.get('selected_proxy')}"
                    for item in cand.get("selected_themes", [])
                ),
            }
        )
    return rows


def build_checks(candidate: dict[str, Any], baseline: dict[str, Any], monthly_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    delta = deltas(candidate, baseline)
    active = safe_get(candidate, ["turnover_cost", "pit_active_rebalances"])
    full_monthly = summarize_monthly(monthly_rows, "1900-01-01", "2999-12-31")
    return [
        {
            "check": "beats_v2_full_ann",
            "passed": delta["ann_delta"] > 0.0,
            "value": delta["ann_delta"],
            "threshold": "> 0",
            "reason": "候选应至少超过 V2 全区间年化。",
        },
        {
            "check": "sharpe_not_worse",
            "passed": delta["sharpe_delta"] >= 0.0,
            "value": delta["sharpe_delta"],
            "threshold": ">= 0",
            "reason": "不能用更差收益质量换取主线解释。",
        },
        {
            "check": "maxdd_not_worse",
            "passed": delta["max_dd_delta"] >= -0.005,
            "value": delta["max_dd_delta"],
            "threshold": ">= -0.50pp",
            "reason": "最大回撤不能明显恶化。",
        },
        {
            "check": "beats_2020",
            "passed": delta["ann_2020_delta"] > 0.0,
            "value": delta["ann_2020_delta"],
            "threshold": "> 0",
            "reason": "父/子主题冲突修正应改善 2020 主线识别。",
        },
        {
            "check": "beats_2024_2026",
            "passed": delta["ann_2024_2026_delta"] >= 0.0,
            "value": delta["ann_2024_2026_delta"],
            "threshold": ">= 0",
            "reason": "不能为了修历史而牺牲近年 OOS。",
        },
        {
            "check": "active_sample_enough",
            "passed": active >= 30,
            "value": active,
            "threshold": ">= 30",
            "reason": "active 样本仍是晋级硬约束。",
        },
        {
            "check": "monthly_sum_positive",
            "passed": float(full_monthly.get("sum_delta", 0.0)) > 0.0,
            "value": float(full_monthly.get("sum_delta", 0.0)),
            "threshold": "> 0",
            "reason": "月度归因不应只靠少数曲线端点改善。",
        },
        {
            "check": "override_exists",
            "passed": safe_get(candidate, ["turnover_cost", "pit_active_rebalances"]) > 0
            and any(row.get("pit_override_allowlist") for row in monthly_rows),
            "value": sum(1 for row in monthly_rows if row.get("pit_override_allowlist")),
            "threshold": "> 0",
            "reason": "没有 OVERRIDE 仍不能排他替换 V2。",
        },
    ]


def decision_from_checks(checks: list[dict[str, Any]]) -> dict[str, str]:
    failed = {row["check"] for row in checks if not row["passed"]}
    if not failed:
        return {"tier": "PAPER_SIM_CANDIDATE", "action": "可进入 paper sim 候选审查；仍需人工确认，不自动替换 V2。"}
    if failed <= {"active_sample_enough", "override_exists"}:
        return {"tier": "RESEARCH_OVERLAY", "action": "方向通过收益/回撤/归因检查，但因 active<30 或 OVERRIDE=0，不能替换 V2。"}
    return {"tier": "WATCH", "action": "保留研究候选，继续补 evidence/归因，不进入模拟盘。"}


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    if not snapshots:
        raise SystemExit(f"empty replay snapshots: {args.replay_json}")
    mapped_snapshots, meta = apply_mapping(snapshots, args.candidate, platform_parent_conflict_to_technology)

    prices = bt.build_price_matrix(pit.required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    baseline_eq, baseline_decisions = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    base_curves = build_base_curves(prices, baseline_eq, args)
    baseline_v6ab = bridge.run_v6ab(base_curves, "baseline_v2", 0.45, args.start, args.end)[0]
    pit_cap = active_cap_from_snapshots(snapshots)

    candidate_standalone, candidate_decisions = pit.run_pit_v6b(
        prices,
        mapped_snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
        turnover_guard_threshold=args.turnover_guard,
    )
    candidate_curves = dict(base_curves)
    candidate_curves[args.candidate] = candidate_standalone
    candidate_v6ab = run_dynamic_candidate(candidate_curves, args.candidate, pit_cap, args)

    baseline = {"candidate": "baseline_v2_v6ab_dynamic_b", **stats_row(baseline_v6ab, [], args)}
    candidate = {"candidate": args.candidate, **stats_row(candidate_v6ab, candidate_decisions, args)}
    monthly_rows = build_monthly_rows(baseline_v6ab, candidate_v6ab, baseline_decisions, candidate_decisions)
    checks = build_checks(candidate, baseline, monthly_rows)
    return {
        "asof": args.asof,
        "candidate_name": args.candidate,
        "start": args.start,
        "end": args.end,
        "turnover_guard": args.turnover_guard,
        "mapping_meta": meta,
        "baseline": baseline,
        "candidate": candidate,
        "delta": deltas(candidate, baseline),
        "period_attribution": {
            "full": summarize_monthly(monthly_rows, args.start, args.end),
            "2020": summarize_monthly(monthly_rows, "2020-01-01", "2020-12-31"),
            "2022": summarize_monthly(monthly_rows, "2022-01-01", "2022-12-31"),
            "2024_2026": summarize_monthly(monthly_rows, "2024-01-01", args.end),
        },
        "checks": checks,
        "decision": decision_from_checks(checks),
        "worst_months": sorted(monthly_rows, key=lambda row: row["candidate_minus_v2"])[:12],
        "best_months": sorted(monthly_rows, key=lambda row: row["candidate_minus_v2"], reverse=True)[:12],
        "monthly_rows": monthly_rows,
        "interpretation": [
            "该报告是正式候选审查，不改变 classifier、PIT replay 或模拟盘。",
            "父/子主题冲突规则只在 ai_platform 与 technology 同时 BOOST 且无 OVERRIDE 时合并到 technology。",
            "若仍无 OVERRIDE 或 active<30，只能保持 RESEARCH_OVERLAY，不得替换 V2。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    baseline = payload["baseline"]
    candidate = payload["candidate"]
    delta = payload["delta"]
    decision = payload["decision"]
    lines = [
        "# V6AB Theme Mapping Candidate Review",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- candidate：`{payload['candidate_name']}`",
        f"- decision：`{decision['tier']}` — {decision['action']}",
        "- 模拟盘动作：`NO_CHANGE`。",
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
        f"| active rebalances | 0 | {safe_get(candidate, ['turnover_cost', 'pit_active_rebalances']):.0f} | {delta['active_rebalances_delta']:+.0f} |",
        "",
        "## Period Attribution",
        "",
        "| period | months | active | sum delta | avg | win rate | negative |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for period, row in payload["period_attribution"].items():
        lines.append(
            f"| `{period}` | {row.get('count', 0)} | {row.get('active', 0)} | {fmt_pct(row.get('sum_delta'))} | "
            f"{fmt_pct(row.get('avg_delta'))} | {fmt_pct(row.get('win_rate'))} | {row.get('negative_months', 0)} |"
        )
    lines += [
        "",
        "## Gate Checks",
        "",
        "| check | result | value | threshold |",
        "| --- | --- | ---: | --- |",
    ]
    for row in payload["checks"]:
        value = row["value"]
        if isinstance(value, bool):
            value_text = str(value)
        elif row["check"] in {"active_sample_enough", "override_exists"}:
            value_text = f"{float(value):.0f}"
        elif row["check"] == "sharpe_not_worse":
            value_text = f"{float(value):+.2f}"
        else:
            value_text = fmt_pct(float(value))
        lines.append(f"| `{row['check']}` | {'PASS' if row['passed'] else 'FAIL'} | {value_text} | {row['threshold']} |")
    lines += [
        "",
        "## Mapping Rows",
        "",
        "| asof | before | after |",
        "| --- | --- | --- |",
    ]
    for row in payload.get("mapping_meta", {}).get("mapped_rows", [])[:12]:
        lines.append(
            f"| `{row.get('asof')}` | `{', '.join(row.get('before_boost', []))}` | `{', '.join(row.get('after_boost', []))}` |"
        )
    lines += [
        "",
        "## Worst Months",
        "",
        "| date | delta | active | selected |",
        "| --- | ---: | --- | --- |",
    ]
    for row in payload["worst_months"][:8]:
        lines.append(
            f"| `{row['date']}` | {fmt_pct(row['candidate_minus_v2'])} | `{row['candidate_active']}` | `{row.get('candidate_selected', '')}` |"
        )
    lines += ["", "## Interpretation", ""]
    lines.extend(f"- {item}" for item in payload.get("interpretation", []))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Formal review for V6AB parent theme conflict mapping candidate.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--candidate", default="platform_parent_conflict_to_technology")
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--v6a-daily", type=Path, default=bridge.DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--turnover-guard", type=float, default=1.40)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    pd.DataFrame(payload["monthly_rows"]).to_csv(args.output_dir / "latest_monthly.csv", index=False)
    (REPORT_ROOT / "V6AB_Theme_Mapping_Candidate_Review_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (REPORT_ROOT / "V6AB_Theme_Mapping_Candidate_Review_LATEST.md").write_text(md, encoding="utf-8")
    pd.DataFrame(payload["monthly_rows"]).to_csv(REPORT_ROOT / "V6AB_Theme_Mapping_Candidate_Review_LATEST.csv", index=False)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
