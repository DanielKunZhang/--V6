#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import v6b_theme_rotation_backtest as bt
import v6ab_classifier_bridge_backtest as bridge
import v6ab_pit_classifier_bridge_backtest as pit_bridge
from v6ab_pit_vs_v2_attribution import monthly_return, selected_theme_labels
from v6ab_sleeve_blend_backtest import benchmark_equity, dynamic_b_sizing_equity, load_v6a_composite


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_override_candidate_backtest"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"
DEFAULT_REVIEW = ROOT / "backtest_results" / "v6ab_override_evidence_candidate_review" / "latest.json"
DEFAULT_V6A_DAILY = bridge.DEFAULT_V6A_DAILY

NOISE_TOKENS = {
    "fair use",
    "copyright",
    "lawsuit",
    "litigation",
    "case on",
    "motions for summary judgment",
    "legal",
    "regulatory",
    "risk factor",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def period_stats(eq: pd.Series, start: str, end: str) -> dict[str, Any]:
    seg = eq[(eq.index >= pd.Timestamp(start)) & (eq.index <= pd.Timestamp(end))]
    if len(seg) < 30:
        return {}
    return bt.stats(seg / float(seg.iloc[0]) * bt.INITIAL_CAPITAL)


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def candidate_rows(review: dict[str, Any], include_watch: bool = False) -> list[dict[str, Any]]:
    allowed = {"OVERRIDE_EVIDENCE_CANDIDATE"}
    if include_watch:
        allowed.add("WATCH_OVERRIDE_EVIDENCE")
    rows = [row for row in review.get("rows", []) if row.get("review_decision") in allowed]
    return sorted(rows, key=lambda row: (str(row.get("asof")), str(row.get("child_theme"))))


def quality_flags(row: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    samples = row.get("child", {}).get("sample_facts", []) if isinstance(row.get("child"), dict) else []
    for fact in samples:
        summary = str(fact.get("summary", "")).lower()
        if any(token in summary for token in NOISE_TOKENS):
            flags.append("legal_or_risk_context_noise")
            break
    child = row.get("child", {}) if isinstance(row.get("child"), dict) else {}
    if int(child.get("actionable_unique_tickers", 0) or 0) < 2:
        flags.append("single_ticker_fact_breadth")
    if float(row.get("quality_score_advantage", 0.0) or 0.0) < 0:
        flags.append("negative_quality_advantage")
    return flags


def effective_rebalance_date(asof: str, rebalance_dates: list[pd.Timestamp]) -> str:
    asof_ts = pd.Timestamp(asof).normalize()
    for dt in rebalance_dates:
        if pd.Timestamp(dt).normalize() >= asof_ts:
            return str(pd.Timestamp(dt).date())
    return str(pd.Timestamp(rebalance_dates[-1]).date())


def build_candidate_snapshots(
    snapshots: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    rebalance_dates: list[pd.Timestamp],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_effective: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        effective = effective_rebalance_date(str(row.get("asof")), rebalance_dates)
        by_effective.setdefault(effective, []).append(row)

    applied: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = copy.deepcopy(snapshots)
    existing_by_asof = {str(snap.get("asof")): snap for snap in out}
    for effective, rows in by_effective.items():
        base_snap = copy.deepcopy(pit_bridge.snapshot_for_date(snapshots, pd.Timestamp(effective)))
        if not base_snap:
            continue
        item = existing_by_asof.get(effective)
        if item is None:
            item = base_snap
            item["asof"] = effective
            out.append(item)
            existing_by_asof[effective] = item
        children = sorted({str(row.get("child_theme")) for row in rows if row.get("child_theme")})
        item["override_allowlist"] = children
        item["boost_allowlist"] = sorted(set(item.get("boost_allowlist", [])) | set(children))
        item["theme_allowlist"] = sorted(set(item.get("theme_allowlist", [])) | set(children))
        item["fallback_to_v2"] = False
        item["override_candidate_research_only"] = True
        for row in rows:
            applied.append(
                {
                    "asof": row.get("asof"),
                    "effective_trade_date": effective,
                    "child_theme": row.get("child_theme"),
                    "parent_theme": row.get("parent_theme"),
                    "market_advantage": row.get("market_advantage"),
                    "quality_score_advantage": row.get("quality_score_advantage"),
                    "actionable_rows": row.get("child", {}).get("actionable_rows", 0),
                    "actionable_unique_tickers": row.get("child", {}).get("actionable_unique_tickers", 0),
                    "quality_flags": quality_flags(row),
                }
            )
    return sorted(out, key=lambda row: str(row.get("asof"))), applied


def build_curves(
    prices: pd.DataFrame,
    v6a_path: Path,
    baseline_eq: pd.Series,
    original_guarded_eq: pd.Series,
    candidate_tier_eq: pd.Series,
    candidate_guarded_eq: pd.Series,
) -> dict[str, pd.Series]:
    return {
        "V6A": load_v6a_composite(v6a_path),
        "baseline_v2": baseline_eq,
        "original_pit_guarded": original_guarded_eq,
        "override_candidate_tier": candidate_tier_eq,
        "override_candidate_guarded": candidate_guarded_eq,
        "GLD": benchmark_equity(prices, "US.GLD"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
    }


def run_v6ab(curves: dict[str, pd.Series], b_key: str, start: str, end: str) -> tuple[pd.Series, pd.DataFrame]:
    return dynamic_b_sizing_equity(
        curves,
        b_key=b_key,
        b_low=0.05,
        b_mid=0.30,
        b_high=0.45,
        b_strong_126d=0.08,
        b_weak_63d=-0.08,
        hedge_max=0.30,
        vol_threshold=0.28,
        corr_threshold=0.60,
        dd_threshold=-0.12,
        start=start,
        end=end,
    )


def decision_metrics(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    return pit_bridge.decision_metrics(decisions)


def row_for(name: str, eq: pd.Series, decisions: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "candidate": name,
        "stats": bt.stats(eq),
        "periods": {
            "full": bt.stats(eq),
            "oos_2024_2026": period_stats(eq, "2024-01-01", args.end),
            "2024_2026": period_stats(eq, "2024-01-01", args.end),
            "2022": period_stats(eq, "2022-01-01", "2022-12-31"),
            "2021": period_stats(eq, "2021-01-01", "2021-12-31"),
            "2020": period_stats(eq, "2020-01-01", "2020-12-31"),
        },
        "turnover_cost": decision_metrics(decisions),
    }


def build_month_attribution(
    baseline_eq: pd.Series,
    original_eq: pd.Series,
    candidate_eq: pd.Series,
    baseline_decisions: list[dict[str, Any]],
    original_decisions: list[dict[str, Any]],
    candidate_decisions: list[dict[str, Any]],
    applied: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    dates = [row["date"] for row in baseline_decisions]
    baseline_rets = monthly_return(baseline_eq, dates)
    original_rets = monthly_return(original_eq, dates)
    candidate_rets = monthly_return(candidate_eq, dates)
    baseline_by_date = {row["date"]: row for row in baseline_decisions}
    original_by_date = {row["date"]: row for row in original_decisions}
    candidate_by_date = {row["date"]: row for row in candidate_decisions}
    applied_by_effective: dict[str, list[dict[str, Any]]] = {}
    for row in applied:
        applied_by_effective.setdefault(str(row.get("effective_trade_date")), []).append(row)

    rows: list[dict[str, Any]] = []
    effective_dates = [
        row["date"]
        for row in candidate_decisions
        if row.get("pit_override_allowlist") and str(row.get("date")) in applied_by_effective
    ]
    for raw_date in sorted(dict.fromkeys(effective_dates)):
        if raw_date not in baseline_rets:
            continue
        candidate_row = candidate_by_date.get(raw_date, {})
        pit_asof = str(candidate_row.get("pit_asof", raw_date))
        b = float(baseline_rets.get(raw_date, 0.0))
        o = float(original_rets.get(raw_date, 0.0))
        c = float(candidate_rets.get(raw_date, 0.0))
        rows.append(
            {
                "date": raw_date,
                "pit_asof": pit_asof,
                "applied_overrides": applied_by_effective.get(raw_date, []),
                "v2_next_ret": b,
                "original_guarded_next_ret": o,
                "candidate_next_ret": c,
                "candidate_minus_v2": c - b,
                "candidate_minus_original_guarded": c - o,
                "v2_selected": selected_theme_labels(baseline_by_date.get(raw_date, {})),
                "original_guarded_selected": selected_theme_labels(original_by_date.get(raw_date, {})),
                "candidate_selected": selected_theme_labels(candidate_by_date.get(raw_date, {})),
                "candidate_turnover": candidate_row.get("turnover", 0.0),
                "candidate_guard_reason": candidate_row.get("pit_guard_reason", ""),
            }
        )
    return rows


def decision_for_payload(rows: list[dict[str, Any]], month_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {row["candidate"]: row for row in rows}
    base = by_name.get("baseline_v2_v6ab_dynamic_b", {})
    cand = by_name.get("override_candidate_guarded_v6ab_dynamic_b", {})
    base_stats = base.get("stats", {})
    cand_stats = cand.get("stats", {})
    ann_delta = float(cand_stats.get("ann_ret", 0.0) or 0.0) - float(base_stats.get("ann_ret", 0.0) or 0.0)
    sharpe_delta = float(cand_stats.get("sharpe", 0.0) or 0.0) - float(base_stats.get("sharpe", 0.0) or 0.0)
    maxdd_delta = float(cand_stats.get("max_dd", 0.0) or 0.0) - float(base_stats.get("max_dd", 0.0) or 0.0)
    bad_months = [row for row in month_rows if float(row.get("candidate_minus_v2", 0.0) or 0.0) < -0.02]
    noisy = [
        applied
        for row in month_rows
        for applied in row.get("applied_overrides", [])
        if applied.get("quality_flags")
    ]
    if ann_delta > 0.005 and sharpe_delta >= 0.02 and maxdd_delta >= -0.01 and not bad_months and not noisy:
        tier = "RESEARCH_OVERLAY_READY"
        action = "可进入下一层研究评审，但仍不改模拟盘。"
    elif ann_delta > 0 and sharpe_delta >= 0:
        tier = "WATCH"
        action = "收益质量略有改善，但样本少或质量仍需审查。"
    else:
        tier = "REJECT_FOR_NOW"
        action = "离线 override 未证明有效，保留事实 ledger 改进，不制度化 override。"
    return {
        "tier": tier,
        "action": action,
        "ann_delta_vs_v2": ann_delta,
        "sharpe_delta_vs_v2": sharpe_delta,
        "maxdd_delta_vs_v2": maxdd_delta,
        "bad_override_months": len(bad_months),
        "quality_flagged_overrides": len(noisy),
        "paper_sim_action": "NO_CHANGE",
    }


def render_md(payload: dict[str, Any]) -> str:
    decision = payload.get("decision", {})
    lines = [
        "# V6AB Override Candidate Backtest",
        "",
        f"- 日期：`{payload['asof']}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "- 目的：只对 evidence review 已通过的 OVERRIDE 候选月份做离线回测，验证是否真有收益价值。",
        f"- 决策：`{decision.get('tier', 'UNKNOWN')}` — {decision.get('action', '')}",
        "",
        "## Results",
        "",
        "| candidate | ann | maxDD | Sharpe | 2024-2026 ann | 2022 ann | 2021 ann | 2020 ann | avg turnover | active rebals |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["rows"]:
        s = row["stats"]
        p = row["periods"]
        m = row["turnover_cost"]
        lines.append(
            f"| `{row['candidate']}` | {fmt_pct(s.get('ann_ret'))} | {fmt_pct(s.get('max_dd'))} | "
            f"{float(s.get('sharpe', 0.0) or 0.0):.2f} | {fmt_pct(p.get('2024_2026', {}).get('ann_ret'))} | "
            f"{fmt_pct(p.get('2022', {}).get('ann_ret'))} | {fmt_pct(p.get('2021', {}).get('ann_ret'))} | "
            f"{fmt_pct(p.get('2020', {}).get('ann_ret'))} | {float(m.get('avg_turnover', 0.0) or 0.0):.2f} | "
            f"{m.get('pit_active_rebalances', 0)} |"
        )
    lines += [
        "",
        "## Applied Override Months",
        "",
        "| trade date | pit asof | override | v2 next | original guarded next | candidate next | vs V2 | vs original | selected | flags |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in payload.get("month_attribution", []):
        overrides = ", ".join(
            f"{x.get('child_theme')}<-{x.get('parent_theme')}@{x.get('asof')}"
            for x in row.get("applied_overrides", [])
        )
        flags = ", ".join(sorted({flag for x in row.get("applied_overrides", []) for flag in x.get("quality_flags", [])})) or "-"
        lines.append(
            f"| `{row['date']}` | `{row.get('pit_asof')}` | `{overrides}` | {fmt_pct(row.get('v2_next_ret'))} | "
            f"{fmt_pct(row.get('original_guarded_next_ret'))} | {fmt_pct(row.get('candidate_next_ret'))} | "
            f"{fmt_pct(row.get('candidate_minus_v2'))} | {fmt_pct(row.get('candidate_minus_original_guarded'))} | "
            f"{row.get('candidate_selected', '')} | {flags} |"
        )
    lines += [
        "",
        "## Evidence Quality Flags",
        "",
    ]
    flagged = [row for row in payload.get("applied_overrides", []) if row.get("quality_flags")]
    if not flagged:
        lines.append("- 无自动质量警报。")
    for row in flagged:
        lines.append(
            f"- `{row.get('asof')}` `{row.get('child_theme')}`：{', '.join(row.get('quality_flags', []))}"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- 本实验只使用已通过 evidence review 的候选月份，不改变 PIT replay、classifier 或模拟盘。",
        "- 若收益改善但存在事实噪音，应先修 fact precision，再考虑制度化。",
        "- 若离线 override 无效，应保留事实 ledger 改进，但不新增复杂交易规则。",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest evidence-approved V6AB OVERRIDE candidates offline.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--override-review-json", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--v6a-daily", type=Path, default=DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--include-watch", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    replay = load_json(args.replay_json)
    review = load_json(args.override_review_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    candidates = candidate_rows(review, include_watch=args.include_watch)
    prices = bt.build_price_matrix(pit_bridge.required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    rebalance_dates = [dt for dt in bt.month_end_dates(prices.index) if dt in prices.index]
    candidate_snapshots, applied = build_candidate_snapshots(snapshots, candidates, rebalance_dates)
    if not applied:
        raise SystemExit("no override candidates to test")
    baseline_eq, baseline_decisions = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    original_guarded_eq, original_guarded_decisions = pit_bridge.run_pit_v6b(
        prices,
        snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
    )
    candidate_tier_eq, candidate_tier_decisions = pit_bridge.run_pit_v6b(
        prices,
        candidate_snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier",
    )
    candidate_guarded_eq, candidate_guarded_decisions = pit_bridge.run_pit_v6b(
        prices,
        candidate_snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
    )

    curves = build_curves(prices, args.v6a_daily, baseline_eq, original_guarded_eq, candidate_tier_eq, candidate_guarded_eq)
    baseline_v6ab, _ = run_v6ab(curves, "baseline_v2", args.start, args.end)
    original_guarded_v6ab, _ = run_v6ab(curves, "original_pit_guarded", args.start, args.end)
    candidate_tier_v6ab, _ = run_v6ab(curves, "override_candidate_tier", args.start, args.end)
    candidate_guarded_v6ab, _ = run_v6ab(curves, "override_candidate_guarded", args.start, args.end)

    rows = [
        row_for("baseline_v2_standalone_v6b", baseline_eq, baseline_decisions, args),
        row_for("original_pit_guarded_standalone_v6b", original_guarded_eq, original_guarded_decisions, args),
        row_for("override_candidate_tier_standalone_v6b", candidate_tier_eq, candidate_tier_decisions, args),
        row_for("override_candidate_guarded_standalone_v6b", candidate_guarded_eq, candidate_guarded_decisions, args),
        row_for("baseline_v2_v6ab_dynamic_b", baseline_v6ab, [], args),
        row_for("original_pit_guarded_v6ab_dynamic_b", original_guarded_v6ab, original_guarded_decisions, args),
        row_for("override_candidate_tier_v6ab_dynamic_b", candidate_tier_v6ab, candidate_tier_decisions, args),
        row_for("override_candidate_guarded_v6ab_dynamic_b", candidate_guarded_v6ab, candidate_guarded_decisions, args),
    ]
    month_attribution = build_month_attribution(
        baseline_eq,
        original_guarded_eq,
        candidate_guarded_eq,
        baseline_decisions,
        original_guarded_decisions,
        candidate_guarded_decisions,
        applied,
    )
    payload = {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "diagnostic_only": True,
        "paper_sim_action": "NO_CHANGE",
        "include_watch": bool(args.include_watch),
        "candidate_count": len(candidates),
        "applied_overrides": applied,
        "rows": rows,
        "month_attribution": month_attribution,
    }
    payload["decision"] = decision_for_payload(rows, month_attribution)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    (args.output_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md + "\n", encoding="utf-8")
    pd.DataFrame(
        [
            {
                "candidate": row["candidate"],
                **row["stats"],
                "ann_2024_2026": row["periods"]["2024_2026"].get("ann_ret"),
                "ann_2022": row["periods"]["2022"].get("ann_ret"),
                "ann_2021": row["periods"]["2021"].get("ann_ret"),
                "ann_2020": row["periods"]["2020"].get("ann_ret"),
                **{f"turnover_{k}": v for k, v in row["turnover_cost"].items()},
            }
            for row in rows
        ]
    ).to_csv(args.output_dir / "latest.csv", index=False)
    (REPORT_ROOT / "V6AB_Override_Candidate_Backtest_LATEST.md").write_text(md + "\n", encoding="utf-8")
    (REPORT_ROOT / "V6AB_Override_Candidate_Backtest_LATEST.json").write_text(json_text, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
