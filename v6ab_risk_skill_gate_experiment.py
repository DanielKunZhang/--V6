#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

import v6ab_classifier_bridge_backtest as bridge
import v6ab_pit_classifier_bridge_backtest as pit
import v6b_theme_rotation_backtest as bt
from v6ab_sleeve_blend_backtest import benchmark_equity, dynamic_b_sizing_equity, load_v6a_composite


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_risk_skill_gate_experiment"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
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


def build_base_curves(prices: pd.DataFrame, baseline_eq: pd.Series, args: argparse.Namespace) -> dict[str, pd.Series]:
    return {
        "V6A": load_v6a_composite(args.v6a_daily),
        "baseline_v2": baseline_eq,
        "GLD": benchmark_equity(prices, "US.GLD"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
    }


def active_cap_from_snapshots(snapshots: list[dict[str, Any]]) -> float:
    caps = [
        float(snap.get("b_sleeve_cap_hint", 0.05))
        for snap in snapshots
        if snap.get("theme_allowlist") and not snap.get("fallback_to_v2", True)
    ]
    return max(caps) if caps else 0.45


def run_dynamic_candidate(curves: dict[str, pd.Series], b_key: str, pit_cap: float, args: argparse.Namespace) -> pd.Series:
    return dynamic_b_sizing_equity(
        curves,
        b_key=b_key,
        b_low=0.05,
        b_mid=min(0.30, pit_cap),
        b_high=max(0.05, min(0.45, pit_cap)),
        b_strong_126d=0.08,
        b_weak_63d=-0.08,
        hedge_max=0.30,
        vol_threshold=0.28,
        corr_threshold=0.60,
        dd_threshold=-0.12,
        start=args.start,
        end=args.end,
    )[0]


def theme_by_id(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("theme")): row for row in snap.get("themes", []) if row.get("theme")}


def risky_theme_ids(snap: dict[str, Any], rule: Callable[[dict[str, Any]], bool]) -> set[str]:
    return {theme_id for theme_id, row in theme_by_id(snap).items() if rule(row)}


def apply_gate(
    snapshots: list[dict[str, Any]],
    name: str,
    rule: Callable[[dict[str, Any]], bool],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out: list[dict[str, Any]] = []
    dropped_rows: list[dict[str, Any]] = []
    for snap in snapshots:
        item = copy.deepcopy(snap)
        risky = risky_theme_ids(item, rule)
        before_boost = list(item.get("boost_allowlist", []))
        before_override = list(item.get("override_allowlist", []))
        item["boost_allowlist"] = [theme for theme in before_boost if theme not in risky]
        item["override_allowlist"] = [theme for theme in before_override if theme not in risky]
        if before_boost != item["boost_allowlist"] or before_override != item["override_allowlist"]:
            dropped = sorted((set(before_boost) | set(before_override)) & risky)
            dropped_rows.append(
                {
                    "asof": item.get("asof"),
                    "dropped_themes": dropped,
                    "before_boost": before_boost,
                    "after_boost": item["boost_allowlist"],
                    "before_override": before_override,
                    "after_override": item["override_allowlist"],
                }
            )
        out.append(item)
    return out, {
        "candidate": name,
        "changed_snapshots": len(dropped_rows),
        "dropped_rows": dropped_rows,
    }


def summarize(
    name: str,
    standalone_eq: pd.Series,
    v6ab_eq: pd.Series,
    decisions: list[dict[str, Any]],
    baseline_v6ab: pd.Series,
    args: argparse.Namespace,
    gate_meta: dict[str, Any],
) -> dict[str, Any]:
    stats = bt.stats(v6ab_eq)
    baseline_stats = bt.stats(baseline_v6ab)
    periods = {
        "full": stats,
        "2020": period_stats(v6ab_eq, "2020-01-01", "2020-12-31"),
        "2022": period_stats(v6ab_eq, "2022-01-01", "2022-12-31"),
        "2024_2026": period_stats(v6ab_eq, "2024-01-01", args.end),
    }
    baseline_periods = {
        "2020": period_stats(baseline_v6ab, "2020-01-01", "2020-12-31"),
        "2022": period_stats(baseline_v6ab, "2022-01-01", "2022-12-31"),
        "2024_2026": period_stats(baseline_v6ab, "2024-01-01", args.end),
    }
    turnover = pit.decision_metrics(decisions)
    return {
        "candidate": name,
        "stats": stats,
        "standalone_stats": bt.stats(standalone_eq),
        "periods": periods,
        "turnover_cost": turnover,
        "delta": {
            "ann_delta": stats.get("ann_ret", 0.0) - baseline_stats.get("ann_ret", 0.0),
            "sharpe_delta": stats.get("sharpe", 0.0) - baseline_stats.get("sharpe", 0.0),
            "max_dd_delta": stats.get("max_dd", 0.0) - baseline_stats.get("max_dd", 0.0),
            "ann_2020_delta": periods["2020"].get("ann_ret", 0.0) - baseline_periods["2020"].get("ann_ret", 0.0),
            "ann_2022_delta": periods["2022"].get("ann_ret", 0.0) - baseline_periods["2022"].get("ann_ret", 0.0),
            "ann_2024_2026_delta": periods["2024_2026"].get("ann_ret", 0.0)
            - baseline_periods["2024_2026"].get("ann_ret", 0.0),
        },
        "active_rebalances": turnover.get("pit_active_rebalances", 0),
        "changed_snapshots": gate_meta.get("changed_snapshots", 0),
        "dropped_rows": gate_meta.get("dropped_rows", [])[:20],
    }


def rule_risk_review(row: dict[str, Any]) -> bool:
    return str(row.get("entry_quality_action", "")) == "RISK_REVIEW"


def rule_high_payoff_risk(row: dict[str, Any]) -> bool:
    return float(row.get("payoff_risk_score", 0.0) or 0.0) >= 70


def rule_low_entry_quality(row: dict[str, Any]) -> bool:
    return float(row.get("entry_quality_score", 0.0) or 0.0) < 50


def rule_capped_or_risk(row: dict[str, Any]) -> bool:
    return str(row.get("entry_quality_action", "")) in {"RISK_REVIEW", "CAPPED_BOOST_ONLY"}


def rule_balanced(row: dict[str, Any]) -> bool:
    return (
        str(row.get("entry_quality_action", "")) == "RISK_REVIEW"
        or (
            float(row.get("payoff_risk_score", 0.0) or 0.0) >= 65
            and float(row.get("entry_quality_score", 0.0) or 0.0) < 55
        )
    )


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    if not snapshots:
        raise SystemExit(f"empty replay snapshots: {args.replay_json}")

    prices = bt.build_price_matrix(pit.required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    baseline_eq, _ = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    base_curves = build_base_curves(prices, baseline_eq, args)
    baseline_v6ab = bridge.run_v6ab(base_curves, "baseline_v2", 0.45, args.start, args.end)[0]
    pit_cap = active_cap_from_snapshots(snapshots)

    rules: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        ("baseline_guarded_no_risk_gate", lambda row: False),
        ("drop_risk_review_boost", rule_risk_review),
        ("drop_high_payoff_risk_ge70", rule_high_payoff_risk),
        ("drop_low_entry_quality_lt50", rule_low_entry_quality),
        ("drop_capped_or_risk", rule_capped_or_risk),
        ("drop_balanced_risk_skill", rule_balanced),
    ]
    rows: list[dict[str, Any]] = []
    for name, rule in rules:
        gated_snapshots, gate_meta = apply_gate(snapshots, name, rule)
        standalone_eq, decisions = pit.run_pit_v6b(
            prices,
            gated_snapshots,
            bridge.BASELINE_CONFIG,
            mode="tier_turnover_guarded",
            turnover_guard_threshold=args.turnover_guard,
        )
        curves = dict(base_curves)
        curves[name] = standalone_eq
        v6ab_eq = run_dynamic_candidate(curves, name, pit_cap, args)
        rows.append(summarize(name, standalone_eq, v6ab_eq, decisions, baseline_v6ab, args, gate_meta))

    baseline_row = rows[0]
    for row in rows:
        row["ann_vs_baseline_guarded"] = row["stats"].get("ann_ret", 0.0) - baseline_row["stats"].get("ann_ret", 0.0)
        row["sharpe_vs_baseline_guarded"] = row["stats"].get("sharpe", 0.0) - baseline_row["stats"].get("sharpe", 0.0)
        row["active_vs_baseline_guarded"] = row["active_rebalances"] - baseline_row["active_rebalances"]

    ranked = sorted(
        rows,
        key=lambda row: (
            row["delta"]["ann_delta"],
            row["delta"]["sharpe_delta"],
            row["delta"]["ann_2024_2026_delta"],
            row["active_rebalances"],
        ),
        reverse=True,
    )
    promoted = [
        row
        for row in rows[1:]
        if row["ann_vs_baseline_guarded"] > 0.001
        and row["sharpe_vs_baseline_guarded"] >= 0.0
        and row["active_rebalances"] >= max(25, rows[0]["active_rebalances"] - 2)
        and row["delta"]["ann_2020_delta"] >= rows[0]["delta"]["ann_2020_delta"] - 0.01
    ]
    return {
        "asof": args.asof,
        "replay_json": str(args.replay_json),
        "start": args.start,
        "end": args.end,
        "turnover_guard": args.turnover_guard,
        "baseline": {
            "candidate": "baseline_v2_v6ab_dynamic_b",
            "stats": bt.stats(baseline_v6ab),
            "periods": {
                "2020": period_stats(baseline_v6ab, "2020-01-01", "2020-12-31"),
                "2022": period_stats(baseline_v6ab, "2022-01-01", "2022-12-31"),
                "2024_2026": period_stats(baseline_v6ab, "2024-01-01", args.end),
            },
        },
        "rows": rows,
        "ranked": ranked,
        "decision": "REVIEW_FOR_FORMAL_GATE" if promoted else "NO_RISK_GATE_PROMOTION",
        "promoted_candidates": [row["candidate"] for row in promoted],
        "interpretation": [
            "这是 risk skill gate 的离线候选实验，不改变正式 classifier、PIT replay 或模拟盘。",
            "只有同时改善全区间/Sharpe/2024-2026，且没有把 active 样本压到不可评估，才值得进入下一轮正式 attribution/promotion gate。",
            "若收益改善来自大幅减少 active 月份，应视为过严风控，不应晋级。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB Risk Skill Gate Experiment",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- turnover guard：`{payload['turnover_guard']:.2f}`",
        f"- decision：`{payload['decision']}`",
        f"- promoted candidates：`{', '.join(payload.get('promoted_candidates', [])) or 'none'}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "",
        "## Ranked Candidates",
        "",
        "| candidate | active | changed snaps | ann | ann vs V2 | ann vs guarded | maxDD | Sharpe | Sharpe vs guarded | 2020 delta | 2022 delta | 2024-2026 delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["ranked"]:
        stats = row["stats"]
        delta = row["delta"]
        lines.append(
            f"| `{row['candidate']}` | {row['active_rebalances']} | {row['changed_snapshots']} | "
            f"{fmt_pct(stats.get('ann_ret'))} | {fmt_pct(delta.get('ann_delta'))} | "
            f"{fmt_pct(row.get('ann_vs_baseline_guarded'))} | {fmt_pct(stats.get('max_dd'))} | "
            f"{float(stats.get('sharpe', 0.0) or 0.0):.2f} | {float(row.get('sharpe_vs_baseline_guarded', 0.0) or 0.0):+.2f} | "
            f"{fmt_pct(delta.get('ann_2020_delta'))} | {fmt_pct(delta.get('ann_2022_delta'))} | "
            f"{fmt_pct(delta.get('ann_2024_2026_delta'))} |"
        )

    lines += [
        "",
        "## Changed Snapshot Samples",
        "",
        "| candidate | asof | dropped | before boost | after boost |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        for item in row.get("dropped_rows", [])[:5]:
            lines.append(
                f"| `{row['candidate']}` | {item.get('asof')} | `{', '.join(item.get('dropped_themes', []))}` | "
                f"`{', '.join(item.get('before_boost', []))}` | `{', '.join(item.get('after_boost', []))}` |"
            )

    lines += [
        "",
        "## Interpretation",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["interpretation"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline test V6AB risk skill gating candidates.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--v6a-daily", type=Path, default=pit.DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--turnover-guard", type=float, default=1.4)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Risk_Skill_Gate_Experiment_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORT_ROOT / "V6AB_Risk_Skill_Gate_Experiment_LATEST.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
