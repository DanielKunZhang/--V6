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
import v6ab_override_candidate_backtest as override_bt
import v6ab_pit_classifier_bridge_backtest as pit_bridge
from v6ab_pit_vs_v2_attribution import monthly_return, selected_theme_labels


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_parent_child_tilt_backtest"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"
DEFAULT_REVIEW = ROOT / "backtest_results" / "v6ab_override_evidence_candidate_review" / "latest.json"
DEFAULT_V6A_DAILY = bridge.DEFAULT_V6A_DAILY


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def period_stats(eq: pd.Series, start: str, end: str) -> dict[str, Any]:
    seg = eq[(eq.index >= pd.Timestamp(start)) & (eq.index <= pd.Timestamp(end))]
    if len(seg) < 30:
        return {}
    return bt.stats(seg / float(seg.iloc[0]) * bt.INITIAL_CAPITAL)


def build_tilt_snapshots(
    snapshots: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    rebalance_dates: list[pd.Timestamp],
    *,
    overlap_policy: str = "allow_child",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_effective: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        effective = override_bt.effective_rebalance_date(str(row.get("asof")), rebalance_dates)
        by_effective.setdefault(effective, []).append(row)

    out = copy.deepcopy(snapshots)
    existing_by_asof = {str(snap.get("asof")): snap for snap in out}
    applied: list[dict[str, Any]] = []
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
        parents = sorted({str(row.get("parent_theme")) for row in rows if row.get("parent_theme")})
        suppressed_children: set[str] = set()
        if overlap_policy == "parent_only_on_proxy_overlap":
            for row in rows:
                child = str(row.get("child_theme", ""))
                parent = str(row.get("parent_theme", ""))
                if child and parent and set(theme_proxies(child)) & set(theme_proxies(parent)):
                    suppressed_children.add(child)
        active_children = [child for child in children if child not in suppressed_children]
        tilt_allowlist = sorted(set(active_children) | set(parents))
        item["override_allowlist"] = []
        item["boost_allowlist"] = sorted(set(item.get("boost_allowlist", [])) | set(tilt_allowlist))
        item["theme_allowlist"] = sorted(set(item.get("theme_allowlist", [])) | set(tilt_allowlist))
        item["fallback_to_v2"] = False
        item["parent_child_tilt_research_only"] = True
        item["parent_child_tilt_overlap_policy"] = overlap_policy

        for row in rows:
            child_theme = str(row.get("child_theme", ""))
            applied.append(
                {
                    "asof": row.get("asof"),
                    "effective_trade_date": effective,
                    "child_theme": child_theme,
                    "parent_theme": row.get("parent_theme"),
                    "tilt_allowlist": sorted(set(tilt_allowlist)),
                    "overlap_policy": overlap_policy,
                    "child_suppressed_by_overlap_guard": child_theme in suppressed_children,
                    "market_advantage": row.get("market_advantage"),
                    "quality_score_advantage": row.get("quality_score_advantage"),
                    "actionable_rows": row.get("child", {}).get("actionable_rows", 0),
                    "actionable_unique_tickers": row.get("child", {}).get("actionable_unique_tickers", 0),
                    "quality_flags": override_bt.quality_flags(row),
                }
            )
    return sorted(out, key=lambda row: str(row.get("asof"))), applied


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
        "turnover_cost": pit_bridge.decision_metrics(decisions),
    }


def build_month_review(
    baseline_eq: pd.Series,
    original_eq: pd.Series,
    tilt_eq: pd.Series,
    baseline_decisions: list[dict[str, Any]],
    original_decisions: list[dict[str, Any]],
    tilt_decisions: list[dict[str, Any]],
    applied: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    dates = [row["date"] for row in baseline_decisions]
    baseline_rets = monthly_return(baseline_eq, dates)
    original_rets = monthly_return(original_eq, dates)
    tilt_rets = monthly_return(tilt_eq, dates)
    baseline_by_date = {row["date"]: row for row in baseline_decisions}
    original_by_date = {row["date"]: row for row in original_decisions}
    tilt_by_date = {row["date"]: row for row in tilt_decisions}
    applied_by_effective: dict[str, list[dict[str, Any]]] = {}
    for row in applied:
        applied_by_effective.setdefault(str(row.get("effective_trade_date")), []).append(row)

    rows: list[dict[str, Any]] = []
    for raw_date in sorted(applied_by_effective):
        if raw_date not in baseline_rets:
            continue
        b = float(baseline_rets.get(raw_date, 0.0))
        o = float(original_rets.get(raw_date, 0.0))
        t = float(tilt_rets.get(raw_date, 0.0))
        baseline_row = baseline_by_date.get(raw_date, {})
        original_row = original_by_date.get(raw_date, {})
        tilt_row = tilt_by_date.get(raw_date, {})
        applied_tilts = applied_by_effective.get(raw_date, [])
        v2_weights = dict(baseline_row.get("weights", {}))
        original_weights = dict(original_row.get("weights", {}))
        tilt_weights = dict(tilt_row.get("weights", {}))
        v2_risky = risky_exposure(v2_weights)
        original_risky = risky_exposure(original_weights)
        tilt_risky = risky_exposure(tilt_weights)
        proxy_overlap = has_parent_child_proxy_overlap(applied_tilts)
        reason = "MAINLINE_AND_EXPRESSION_OK"
        if t - b < -0.02:
            reason = "TILT_HURT_V2"
        elif t - o < -0.02:
            reason = "TILT_HURT_ORIGINAL_PIT"
        elif t > max(b, o):
            reason = "TILT_HELPED"
        expression_flags = []
        if proxy_overlap:
            expression_flags.append("child_parent_proxy_overlap")
        if tilt_risky > original_risky + 0.05:
            expression_flags.append("tilt_increased_risky_exposure")
        if t - b < -0.02 and proxy_overlap:
            expression_flags.append("duplicate_proxy_tilt_hurt")
        rows.append(
            {
                "date": raw_date,
                "pit_asof": tilt_row.get("pit_asof", raw_date),
                "applied_tilts": applied_tilts,
                "v2_next_ret": b,
                "original_guarded_next_ret": o,
                "tilt_next_ret": t,
                "tilt_minus_v2": t - b,
                "tilt_minus_original_guarded": t - o,
                "review_reason": reason,
                "expression_flags": expression_flags,
                "v2_risky_exposure": v2_risky,
                "original_guarded_risky_exposure": original_risky,
                "tilt_risky_exposure": tilt_risky,
                "v2_weights": v2_weights,
                "original_guarded_weights": original_weights,
                "tilt_weights": tilt_weights,
                "v2_selected": selected_theme_labels(baseline_row),
                "original_guarded_selected": selected_theme_labels(original_row),
                "tilt_selected": selected_theme_labels(tilt_by_date.get(raw_date, {})),
                "tilt_turnover": tilt_row.get("turnover", 0.0),
                "tilt_guard_reason": tilt_row.get("pit_guard_reason", ""),
            }
        )
    return rows


def risky_exposure(weights: dict[str, float]) -> float:
    return float(sum(float(weight) for ticker, weight in weights.items() if ticker not in {"CASH", "US.BIL"}))


def theme_proxies(theme_id: str) -> list[str]:
    theme = bt.THEMES.get(theme_id, {})
    proxies = list(theme.get("proxies", []))
    if proxies:
        return proxies
    return list(bridge.THEME_PROXY_FALLBACKS.get(theme_id, []))


def has_parent_child_proxy_overlap(applied_tilts: list[dict[str, Any]]) -> bool:
    for item in applied_tilts:
        child = str(item.get("child_theme", ""))
        parent = str(item.get("parent_theme", ""))
        if child and parent and set(theme_proxies(child)) & set(theme_proxies(parent)):
            return True
    return False


def decision_for_payload(rows: list[dict[str, Any]], month_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {row["candidate"]: row for row in rows}
    base = by_name.get("baseline_v2_v6ab_dynamic_b", {})
    original = by_name.get("original_pit_guarded_v6ab_dynamic_b", {})
    tilt = by_name.get("parent_child_tilt_guarded_v6ab_dynamic_b", {})
    overlap_guarded = by_name.get("overlap_guarded_tilt_v6ab_dynamic_b", {})
    base_stats = base.get("stats", {})
    original_stats = original.get("stats", {})
    tilt_stats = tilt.get("stats", {})
    overlap_guarded_stats = overlap_guarded.get("stats", {})
    ann_delta_vs_v2 = float(tilt_stats.get("ann_ret", 0.0) or 0.0) - float(base_stats.get("ann_ret", 0.0) or 0.0)
    ann_delta_vs_original = float(tilt_stats.get("ann_ret", 0.0) or 0.0) - float(original_stats.get("ann_ret", 0.0) or 0.0)
    overlap_ann_delta_vs_v2 = float(overlap_guarded_stats.get("ann_ret", 0.0) or 0.0) - float(base_stats.get("ann_ret", 0.0) or 0.0)
    overlap_ann_delta_vs_original = float(overlap_guarded_stats.get("ann_ret", 0.0) or 0.0) - float(original_stats.get("ann_ret", 0.0) or 0.0)
    sharpe_delta_vs_v2 = float(tilt_stats.get("sharpe", 0.0) or 0.0) - float(base_stats.get("sharpe", 0.0) or 0.0)
    maxdd_delta_vs_v2 = float(tilt_stats.get("max_dd", 0.0) or 0.0) - float(base_stats.get("max_dd", 0.0) or 0.0)
    bad_months = [row for row in month_rows if float(row.get("tilt_minus_v2", 0.0) or 0.0) < -0.02]
    helped_months = [row for row in month_rows if row.get("review_reason") == "TILT_HELPED"]

    tier = "REJECT_FOR_NOW"
    action = "parent+child tilt 未证明可晋级；保留为研究复盘项。"
    if ann_delta_vs_v2 > 0.003 and sharpe_delta_vs_v2 >= 0 and maxdd_delta_vs_v2 >= -0.005 and not bad_months:
        tier = "WATCH"
        action = "parent+child tilt 初步有效，但样本太少，只能进入 WATCH，不改模拟盘。"
    if ann_delta_vs_v2 > 0.006 and ann_delta_vs_original >= 0 and sharpe_delta_vs_v2 > 0.02 and not bad_months:
        tier = "RESEARCH_OVERLAY"
        action = "parent+child tilt 可作为研究 overlay 继续扩样本验证；不替换 V2。"

    return {
        "tier": tier,
        "action": action,
        "ann_delta_vs_v2": ann_delta_vs_v2,
        "ann_delta_vs_original_pit": ann_delta_vs_original,
        "overlap_guarded_ann_delta_vs_v2": overlap_ann_delta_vs_v2,
        "overlap_guarded_ann_delta_vs_original_pit": overlap_ann_delta_vs_original,
        "sharpe_delta_vs_v2": sharpe_delta_vs_v2,
        "maxdd_delta_vs_v2": maxdd_delta_vs_v2,
        "active_tilt_months": len(month_rows),
        "helped_months": len(helped_months),
        "bad_months": len(bad_months),
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB Parent + Child Tilt Backtest",
        "",
        f"- 日期：`{payload['asof']}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "- 目的：验证 evidence-approved 子主题是否适合作为父主题旁边的倾斜，而不是 hard override。",
        f"- 决策：`{payload['decision']['tier']}` — {payload['decision']['action']}",
        f"- overlap guard：ann vs V2 `{fmt_pct(payload['decision'].get('overlap_guarded_ann_delta_vs_v2'))}`，ann vs original PIT `{fmt_pct(payload['decision'].get('overlap_guarded_ann_delta_vs_original_pit'))}`。",
        "",
        "## Results",
        "",
        "| candidate | ann | maxDD | Sharpe | 2024-2026 ann | 2022 ann | 2021 ann | 2020 ann | avg turnover | active rebals |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["rows"]:
        s = row["stats"]
        p = row.get("periods", {})
        m = row.get("turnover_cost", {})
        lines.append(
            f"| `{row['candidate']}` | {fmt_pct(s.get('ann_ret'))} | {fmt_pct(s.get('max_dd'))} | "
            f"{s.get('sharpe', 0):.2f} | {fmt_pct(p.get('2024_2026', {}).get('ann_ret'))} | "
            f"{fmt_pct(p.get('2022', {}).get('ann_ret'))} | {fmt_pct(p.get('2021', {}).get('ann_ret'))} | "
            f"{fmt_pct(p.get('2020', {}).get('ann_ret'))} | {m.get('avg_turnover', 0):.2f} | "
            f"{m.get('pit_active_rebalances', 0)} |"
        )

    lines += [
        "",
        "## Tilt Month Review",
        "",
        "| trade date | pit asof | tilt | v2 next | original PIT next | tilt next | vs V2 | vs original | review | flags | risky exp V2/PIT/tilt | selected |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |",
    ]
    for row in payload.get("month_review", []):
        tilts = ", ".join(
            f"{item.get('child_theme')}+{item.get('parent_theme')}"
            for item in row.get("applied_tilts", [])
        )
        flags = ", ".join(row.get("expression_flags", [])) or "-"
        risk = (
            f"{float(row.get('v2_risky_exposure', 0.0) or 0.0):.0%}/"
            f"{float(row.get('original_guarded_risky_exposure', 0.0) or 0.0):.0%}/"
            f"{float(row.get('tilt_risky_exposure', 0.0) or 0.0):.0%}"
        )
        lines.append(
            f"| `{row['date']}` | `{row.get('pit_asof')}` | `{tilts}` | {fmt_pct(row.get('v2_next_ret'))} | "
            f"{fmt_pct(row.get('original_guarded_next_ret'))} | {fmt_pct(row.get('tilt_next_ret'))} | "
            f"{fmt_pct(row.get('tilt_minus_v2'))} | {fmt_pct(row.get('tilt_minus_original_guarded'))} | "
            f"`{row.get('review_reason')}` | `{flags}` | {risk} | {row.get('tilt_selected', '')} |"
        )

    overlap_rows = payload.get("overlap_guarded_month_review", [])
    if overlap_rows:
        lines += [
            "",
            "## Overlap Guard Month Review",
            "",
            "| trade date | policy | v2 next | original PIT next | guarded next | vs V2 | flags | risky exp V2/PIT/guarded | selected |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |",
        ]
        for row in overlap_rows:
            policies = ", ".join(
                str(item.get("overlap_policy", ""))
                for item in row.get("applied_tilts", [])
            )
            suppressed = any(bool(item.get("child_suppressed_by_overlap_guard")) for item in row.get("applied_tilts", []))
            flags = ", ".join(row.get("expression_flags", [])) or "-"
            if suppressed:
                flags = f"{flags}, child_suppressed_by_overlap_guard" if flags != "-" else "child_suppressed_by_overlap_guard"
            risk = (
                f"{float(row.get('v2_risky_exposure', 0.0) or 0.0):.0%}/"
                f"{float(row.get('original_guarded_risky_exposure', 0.0) or 0.0):.0%}/"
                f"{float(row.get('tilt_risky_exposure', 0.0) or 0.0):.0%}"
            )
            lines.append(
                f"| `{row['date']}` | `{policies}` | {fmt_pct(row.get('v2_next_ret'))} | "
                f"{fmt_pct(row.get('original_guarded_next_ret'))} | {fmt_pct(row.get('tilt_next_ret'))} | "
                f"{fmt_pct(row.get('tilt_minus_v2'))} | `{flags}` | {risk} | {row.get('tilt_selected', '')} |"
            )

    lines += [
        "",
        "## Interpretation",
        "",
        "- 本实验只改变研究回测里的主题表达方式，不改变 classifier、PIT replay 或 V6AB 模拟盘。",
        "- 若 tilt 仍在少数月份大幅跑输 V2，说明子主题事实正确也不等于表达正确，应继续做入场质量和月度复盘。",
        "- 若 tilt 优于 hard override，后续方向应从“替换父主题”转向“父主题框架下的证据倾斜”。",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest V6AB parent+child tilt candidates offline.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--override-review-json", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--v6a-daily", type=Path, default=DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    if not snapshots:
        raise SystemExit(f"empty PIT replay: {args.replay_json}")
    review = load_json(args.override_review_json)
    candidates = override_bt.candidate_rows(review)
    if not candidates:
        raise SystemExit("no evidence-approved parent+child candidates to test")

    prices = bt.build_price_matrix(pit_bridge.required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    rebalance_dates = [dt for dt in bt.month_end_dates(prices.index) if dt in prices.index]
    tilt_snapshots, applied = build_tilt_snapshots(snapshots, candidates, rebalance_dates)
    overlap_guarded_snapshots, overlap_guarded_applied = build_tilt_snapshots(
        snapshots,
        candidates,
        rebalance_dates,
        overlap_policy="parent_only_on_proxy_overlap",
    )

    baseline_eq, baseline_decisions = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    original_guarded_eq, original_guarded_decisions = pit_bridge.run_pit_v6b(
        prices,
        snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
    )
    tilt_eq, tilt_decisions = pit_bridge.run_pit_v6b(
        prices,
        tilt_snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
    )
    overlap_guarded_eq, overlap_guarded_decisions = pit_bridge.run_pit_v6b(
        prices,
        overlap_guarded_snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
    )
    curves = {
        "V6A": override_bt.load_v6a_composite(args.v6a_daily),
        "baseline_v2": baseline_eq,
        "original_pit_guarded": original_guarded_eq,
        "parent_child_tilt_guarded": tilt_eq,
        "overlap_guarded_tilt": overlap_guarded_eq,
        "GLD": override_bt.benchmark_equity(prices, "US.GLD"),
        "BIL": override_bt.benchmark_equity(prices, "US.BIL"),
        "SPY": override_bt.benchmark_equity(prices, "US.SPY"),
        "QQQ": override_bt.benchmark_equity(prices, "US.QQQ"),
    }
    baseline_v6ab, _ = override_bt.run_v6ab(curves, "baseline_v2", args.start, args.end)
    original_v6ab, _ = override_bt.run_v6ab(curves, "original_pit_guarded", args.start, args.end)
    tilt_v6ab, _ = override_bt.run_v6ab(curves, "parent_child_tilt_guarded", args.start, args.end)
    overlap_guarded_v6ab, _ = override_bt.run_v6ab(curves, "overlap_guarded_tilt", args.start, args.end)

    rows = [
        row_for("baseline_v2_standalone_v6b", baseline_eq, baseline_decisions, args),
        row_for("original_pit_guarded_standalone_v6b", original_guarded_eq, original_guarded_decisions, args),
        row_for("parent_child_tilt_guarded_standalone_v6b", tilt_eq, tilt_decisions, args),
        row_for("overlap_guarded_tilt_standalone_v6b", overlap_guarded_eq, overlap_guarded_decisions, args),
        row_for("baseline_v2_v6ab_dynamic_b", baseline_v6ab, [], args),
        row_for("original_pit_guarded_v6ab_dynamic_b", original_v6ab, original_guarded_decisions, args),
        row_for("parent_child_tilt_guarded_v6ab_dynamic_b", tilt_v6ab, tilt_decisions, args),
        row_for("overlap_guarded_tilt_v6ab_dynamic_b", overlap_guarded_v6ab, overlap_guarded_decisions, args),
    ]
    month_review = build_month_review(
        baseline_eq,
        original_guarded_eq,
        tilt_eq,
        baseline_decisions,
        original_guarded_decisions,
        tilt_decisions,
        applied,
    )
    overlap_guarded_month_review = build_month_review(
        baseline_eq,
        original_guarded_eq,
        overlap_guarded_eq,
        baseline_decisions,
        original_guarded_decisions,
        overlap_guarded_decisions,
        overlap_guarded_applied,
    )
    payload = {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "replay_json": str(args.replay_json),
        "override_review_json": str(args.override_review_json),
        "candidate_count": len(candidates),
        "applied_tilts": applied,
        "overlap_guarded_applied_tilts": overlap_guarded_applied,
        "rows": rows,
        "month_review": month_review,
        "overlap_guarded_month_review": overlap_guarded_month_review,
        "decision": decision_for_payload(rows, month_review),
    }
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    pd.DataFrame(
        [
            {
                "candidate": row["candidate"],
                **row["stats"],
                "ann_2024_2026": row["periods"]["2024_2026"].get("ann_ret"),
                "ann_2022": row["periods"]["2022"].get("ann_ret"),
                "ann_2021": row["periods"]["2021"].get("ann_ret"),
                "ann_2020": row["periods"]["2020"].get("ann_ret"),
                **{f"turnover_{key}": value for key, value in row["turnover_cost"].items()},
            }
            for row in rows
        ]
    ).to_csv(args.output_dir / "latest.csv", index=False)
    (REPORT_ROOT / "V6AB_Parent_Child_Tilt_Backtest_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Parent_Child_Tilt_Backtest_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
