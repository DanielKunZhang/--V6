#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
OUT_DIR = ROOT / "backtest_results" / "v6ab_legacy_winner_preservation_experiment"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"
DEFAULT_V6A_DAILY = bridge.DEFAULT_V6A_DAILY

AI_THEMES = {
    "semis_ai",
    "ai_platform",
    "ai_optical",
    "ai_networking",
    "ai_infra",
    "ai_memory",
    "ai_power_datacenter",
}
PROTECTED_LEGACY_THEMES = {
    "technology",
    "liquidity_growth",
    "broad_beta",
    "precious_metals",
    "energy_resources",
    "consumer_discretionary",
    "financials",
}


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


def selected_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("theme_id")) for row in rows if row.get("selected")}


def should_preserve_baseline(
    snap: dict[str, Any],
    baseline_rows: list[dict[str, Any]],
    pit_rows: list[dict[str, Any]],
    *,
    policy: str = "v1_preserve_any_legacy",
) -> tuple[bool, list[str]]:
    if snap.get("override_allowlist"):
        return False, []
    boosted = set(snap.get("boost_allowlist", [])) | set(snap.get("theme_allowlist", []))
    if not (boosted & AI_THEMES):
        return False, []
    baseline_selected = selected_ids(baseline_rows)
    pit_selected = selected_ids(pit_rows)
    missed = sorted((baseline_selected & PROTECTED_LEGACY_THEMES) - pit_selected)
    if policy == "v2_memory_requires_broad_legacy_confirmation" and "ai_memory" in boosted and len(missed) < 2:
        return False, missed
    return bool(missed), missed


def run_guarded_v6b(
    prices: pd.DataFrame,
    snapshots: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    turnover_guard_threshold: float = 1.4,
    policy: str = "v1_preserve_any_legacy",
) -> tuple[pd.Series, list[dict[str, Any]]]:
    monthly_dates = [dt for dt in bt.month_end_dates(prices.index) if dt in prices.index]
    monthly = prices.loc[monthly_dates].dropna(how="all")
    returns = prices.pct_change().fillna(0.0)
    equity = bt.INITIAL_CAPITAL
    peak = equity
    current_weights = {"CASH": 1.0}
    preview: dict[pd.Timestamp, tuple[dict[str, float], list[dict[str, Any]], dict[str, Any], str, bool, str, list[str]]] = {}
    decisions: list[dict[str, Any]] = []
    pick_config = {key: value for key, value in config.items() if key != "dd_brake"}
    use_dd_brake = bool(config.get("dd_brake"))

    old_themes = bt.THEMES
    try:
        for dt in monthly.index:
            dt = pd.Timestamp(dt)
            bt.THEMES = old_themes
            snap = pit_bridge.snapshot_for_date(snapshots, dt)
            pit_active = pit_bridge.snapshot_active_for_mode(snap, "tier_turnover_guarded")
            pit_tier = "WATCH"
            guard_reason = ""
            preserved: list[str] = []
            if monthly.index.get_loc(dt) < 12 or not pit_active:
                weights, rows = bt.pick_weights(monthly, dt, **pick_config) if monthly.index.get_loc(dt) >= 12 else ({"CASH": 1.0}, [])
            else:
                baseline_weights, baseline_rows = bt.pick_weights(monthly, dt, **pick_config)
                themes, pit_tier = pit_bridge.tier_themes_from_snapshot(snap)
                bt.THEMES = themes
                pit_config = dict(pick_config)
                pit_config["top_n"] = max(1, min(3, len(themes)))
                pit_config["stock_top_n"] = 3
                weights, rows = bt.pick_weights(monthly, dt, **pit_config)
                preserve, preserved = should_preserve_baseline(snap, baseline_rows, rows, policy=policy)
                proposed_turnover = sum(
                    abs(weights.get(k, 0.0) - current_weights.get(k, 0.0))
                    for k in set(weights) | set(current_weights)
                    if k != "CASH"
                )
                if preserve:
                    weights, rows = baseline_weights, baseline_rows
                    pit_active = False
                    pit_tier = "WATCH"
                    guard_reason = "legacy_winner_preserved:" + ",".join(preserved)
                elif not snap.get("override_allowlist") and proposed_turnover > turnover_guard_threshold:
                    weights, rows = baseline_weights, baseline_rows
                    pit_active = False
                    pit_tier = "WATCH"
                    guard_reason = f"turnover_guard>{turnover_guard_threshold:.2f}"
            preview[dt] = (weights, rows, snap, pit_tier, pit_active, guard_reason, preserved)

        records: list[tuple[pd.Timestamp, float]] = []
        for dt in prices.index:
            day_ret = current_weights.get("CASH", 0.0) * (bt.RISK_FREE / bt.TRADING_DAYS)
            for ticker, weight in current_weights.items():
                if ticker == "CASH":
                    continue
                if ticker in returns.columns and pd.notna(returns.loc[dt, ticker]):
                    day_ret += weight * float(returns.loc[dt, ticker])
            equity = max(equity * (1.0 + day_ret), 0.0)
            peak = max(peak, equity)
            dd = equity / peak - 1.0
            if dt in preview:
                weights, rows, snap, pit_tier, pit_active, guard_reason, preserved = preview[pd.Timestamp(dt)]
                if use_dd_brake:
                    if dd <= -0.25:
                        weights = bt.defensive_weights(monthly, pd.Timestamp(dt))
                    elif dd <= -0.15:
                        risky = sum(weight for ticker, weight in weights.items() if ticker != "CASH")
                        if risky > 0:
                            scale = 0.50
                            weights = {ticker: weight * scale for ticker, weight in weights.items() if ticker != "CASH"}
                            weights["US.BIL"] = weights.get("US.BIL", 0.0) + (1.0 - sum(weights.values()))
                turnover = sum(abs(weights.get(k, 0.0) - current_weights.get(k, 0.0)) for k in set(weights) | set(current_weights) if k != "CASH")
                equity -= equity * turnover * bt.TX_COST_BPS / 10_000.0
                current_weights = dict(weights)
                decisions.append(
                    {
                        "date": str(pd.Timestamp(dt).date()),
                        "weights": current_weights,
                        "drawdown": round(float(dd), 6),
                        "pit_asof": snap.get("asof"),
                        "pit_allowlist": snap.get("theme_allowlist", []),
                        "pit_boost_allowlist": snap.get("boost_allowlist", []),
                        "pit_override_allowlist": snap.get("override_allowlist", []),
                        "pit_mode": "tier_turnover_guarded_legacy_preserve",
                        "pit_signal_tier": pit_tier,
                        "pit_active_for_mode": pit_active,
                        "pit_confirmed": pit_bridge.has_confirmed_theme(snap),
                        "pit_guard_reason": guard_reason,
                        "legacy_preserved_themes": preserved,
                        "legacy_preservation_policy": policy,
                        "classifier_fallback_to_v2": bool(not snap or snap.get("fallback_to_v2", True)),
                        "fallback_to_v2": bool(not pit_active),
                        "turnover": round(float(turnover), 6),
                        "top_themes": [
                            {
                                "theme_id": row["theme_id"],
                                "label": row["label"],
                                "selected_proxy": row["selected_proxy"],
                                "theme_score": round(float(row["theme_score"]), 6),
                                "breadth": round(float(row["breadth"]), 6),
                                "selected": bool(row.get("selected", False)),
                            }
                            for row in rows[:5]
                        ],
                        "selected_themes": [
                            {
                                "theme_id": row["theme_id"],
                                "label": row["label"],
                                "selected_proxy": row["selected_proxy"],
                                "theme_score": round(float(row["theme_score"]), 6),
                                "breadth": round(float(row["breadth"]), 6),
                            }
                            for row in rows
                            if row.get("selected", False)
                        ],
                    }
                )
            records.append((pd.Timestamp(dt), equity))
    finally:
        bt.THEMES = old_themes
    return pd.Series([value for _, value in records], index=[dt for dt, _ in records]), decisions


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
    guarded_eq: pd.Series,
    baseline_decisions: list[dict[str, Any]],
    original_decisions: list[dict[str, Any]],
    guarded_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    dates = [row["date"] for row in baseline_decisions]
    baseline_rets = monthly_return(baseline_eq, dates)
    original_rets = monthly_return(original_eq, dates)
    guarded_rets = monthly_return(guarded_eq, dates)
    baseline_by_date = {row["date"]: row for row in baseline_decisions}
    original_by_date = {row["date"]: row for row in original_decisions}
    guarded_by_date = {row["date"]: row for row in guarded_decisions}
    rows: list[dict[str, Any]] = []
    for row in guarded_decisions:
        if not row.get("legacy_preserved_themes"):
            continue
        raw_date = str(row.get("date"))
        if raw_date not in baseline_rets:
            continue
        b = float(baseline_rets.get(raw_date, 0.0))
        o = float(original_rets.get(raw_date, 0.0))
        g = float(guarded_rets.get(raw_date, 0.0))
        rows.append(
            {
                "date": raw_date,
                "pit_asof": row.get("pit_asof"),
                "preserved_themes": row.get("legacy_preserved_themes", []),
                "v2_next_ret": b,
                "original_guarded_next_ret": o,
                "legacy_guarded_next_ret": g,
                "legacy_guarded_minus_v2": g - b,
                "legacy_guarded_minus_original": g - o,
                "v2_selected": selected_theme_labels(baseline_by_date.get(raw_date, {})),
                "original_guarded_selected": selected_theme_labels(original_by_date.get(raw_date, {})),
                "legacy_guarded_selected": selected_theme_labels(guarded_by_date.get(raw_date, {})),
                "guard_reason": row.get("pit_guard_reason", ""),
            }
        )
    return rows


def decision_for_payload(
    rows: list[dict[str, Any]],
    month_review: list[dict[str, Any]],
    qualified_month_review: list[dict[str, Any]],
) -> dict[str, Any]:
    by_name = {row["candidate"]: row for row in rows}
    base = by_name.get("baseline_v2_v6ab_dynamic_b", {})
    original = by_name.get("original_pit_guarded_v6ab_dynamic_b", {})
    guarded = by_name.get("legacy_preserve_guarded_v6ab_dynamic_b", {})
    qualified = by_name.get("legacy_preserve_qualified_v6ab_dynamic_b", {})
    base_stats = base.get("stats", {})
    original_stats = original.get("stats", {})
    guarded_stats = guarded.get("stats", {})
    qualified_stats = qualified.get("stats", {})
    ann_delta_vs_v2 = float(guarded_stats.get("ann_ret", 0.0) or 0.0) - float(base_stats.get("ann_ret", 0.0) or 0.0)
    ann_delta_vs_original = float(guarded_stats.get("ann_ret", 0.0) or 0.0) - float(original_stats.get("ann_ret", 0.0) or 0.0)
    qualified_ann_delta_vs_v2 = float(qualified_stats.get("ann_ret", 0.0) or 0.0) - float(base_stats.get("ann_ret", 0.0) or 0.0)
    qualified_ann_delta_vs_original = float(qualified_stats.get("ann_ret", 0.0) or 0.0) - float(original_stats.get("ann_ret", 0.0) or 0.0)
    sharpe_delta_vs_v2 = float(guarded_stats.get("sharpe", 0.0) or 0.0) - float(base_stats.get("sharpe", 0.0) or 0.0)
    qualified_sharpe_delta_vs_v2 = float(qualified_stats.get("sharpe", 0.0) or 0.0) - float(base_stats.get("sharpe", 0.0) or 0.0)
    bad_months = [row for row in month_review if float(row.get("legacy_guarded_minus_original", 0.0) or 0.0) < -0.02]
    qualified_bad_months = [
        row for row in qualified_month_review if float(row.get("legacy_guarded_minus_original", 0.0) or 0.0) < -0.02
    ]
    tier = "REJECT_FOR_NOW"
    action = "legacy winner preservation 未证明优于当前 PIT guarded；保留为诊断。"
    if ann_delta_vs_v2 > 0.003 and ann_delta_vs_original >= -0.001 and sharpe_delta_vs_v2 >= 0 and not bad_months:
        tier = "WATCH"
        action = "legacy winner preservation 作为防错保护进入 WATCH；不改模拟盘。"
    if ann_delta_vs_original > 0.002 and sharpe_delta_vs_v2 > 0.02 and not bad_months:
        tier = "RESEARCH_OVERLAY"
        action = "legacy winner preservation 可作为研究 overlay 扩样本验证；不替换 V2。"
    qualified_tier = "REJECT_FOR_NOW"
    qualified_action = "qualified legacy preservation 仍需继续诊断。"
    if (
        qualified_ann_delta_vs_v2 > 0.003
        and qualified_ann_delta_vs_original >= -0.001
        and qualified_sharpe_delta_vs_v2 >= 0
        and not qualified_bad_months
    ):
        qualified_tier = "WATCH"
        qualified_action = "qualified legacy preservation 初步有效，进入 WATCH；不改模拟盘。"
    if (
        qualified_ann_delta_vs_original > 0.002
        and qualified_sharpe_delta_vs_v2 > 0.02
        and not qualified_bad_months
    ):
        qualified_tier = "RESEARCH_OVERLAY"
        qualified_action = "qualified legacy preservation 可作为研究 overlay 扩样本验证；不替换 V2。"
    return {
        "tier": tier,
        "action": action,
        "qualified_tier": qualified_tier,
        "qualified_action": qualified_action,
        "ann_delta_vs_v2": ann_delta_vs_v2,
        "ann_delta_vs_original_pit": ann_delta_vs_original,
        "qualified_ann_delta_vs_v2": qualified_ann_delta_vs_v2,
        "qualified_ann_delta_vs_original_pit": qualified_ann_delta_vs_original,
        "sharpe_delta_vs_v2": sharpe_delta_vs_v2,
        "qualified_sharpe_delta_vs_v2": qualified_sharpe_delta_vs_v2,
        "preserved_months": len(month_review),
        "bad_preserved_months": len(bad_months),
        "qualified_preserved_months": len(qualified_month_review),
        "qualified_bad_preserved_months": len(qualified_bad_months),
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB Legacy Winner Preservation Experiment",
        "",
        f"- 日期：`{payload['asof']}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "- 目的：验证 PIT AI boost 在无 OVERRIDE 时是否不应挤掉 V2 已识别的非 AI legacy winner。",
        f"- 决策：`{payload['decision']['tier']}` — {payload['decision']['action']}",
        f"- qualified v2：`{payload['decision'].get('qualified_tier')}` — {payload['decision'].get('qualified_action')}",
        f"- qualified v2 metrics：ann vs V2 `{fmt_pct(payload['decision'].get('qualified_ann_delta_vs_v2'))}`，ann vs original PIT `{fmt_pct(payload['decision'].get('qualified_ann_delta_vs_original_pit'))}`，bad months `{payload['decision'].get('qualified_bad_preserved_months')}`。",
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
        "## Preserved Month Review",
        "",
        "| date | preserved | V2 next | original PIT next | guarded next | guarded vs original | V2 selected | original selected | guarded selected |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in payload.get("month_review", [])[:20]:
        lines.append(
            f"| `{row['date']}` | `{', '.join(row.get('preserved_themes', []))}` | {fmt_pct(row.get('v2_next_ret'))} | "
            f"{fmt_pct(row.get('original_guarded_next_ret'))} | {fmt_pct(row.get('legacy_guarded_next_ret'))} | "
            f"{fmt_pct(row.get('legacy_guarded_minus_original'))} | {row.get('v2_selected', '')} | "
            f"{row.get('original_guarded_selected', '')} | {row.get('legacy_guarded_selected', '')} |"
        )
    qualified_rows = payload.get("qualified_month_review", [])
    if qualified_rows:
        lines += [
            "",
            "## Qualified V2 Preserved Month Review",
            "",
            "| date | preserved | V2 next | original PIT next | qualified next | qualified vs original | V2 selected | original selected | qualified selected |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
        ]
        for row in qualified_rows[:20]:
            lines.append(
                f"| `{row['date']}` | `{', '.join(row.get('preserved_themes', []))}` | {fmt_pct(row.get('v2_next_ret'))} | "
                f"{fmt_pct(row.get('original_guarded_next_ret'))} | {fmt_pct(row.get('legacy_guarded_next_ret'))} | "
                f"{fmt_pct(row.get('legacy_guarded_minus_original'))} | {row.get('v2_selected', '')} | "
                f"{row.get('original_guarded_selected', '')} | {row.get('legacy_guarded_selected', '')} |"
            )
    lines += [
        "",
        "## Interpretation",
        "",
        "- 本实验使用 V2 当期价格动量选出的 legacy winner 作为可见市场信号，不使用未来收益。",
        "- 若 guard 只是回到 V2，说明 PIT overlay 的问题是错误替换；若 guard 仍输，说明 V2 本身也不是该月最佳表达。",
        "- 该实验不是交易规则晋级；通过前仍只作为历史主线识别和表达保护研究。",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest V6AB legacy winner preservation guard offline.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--v6a-daily", type=Path, default=DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    if not snapshots:
        raise SystemExit(f"empty PIT replay: {args.replay_json}")

    prices = bt.build_price_matrix(pit_bridge.required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    baseline_eq, baseline_decisions = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    original_eq, original_decisions = pit_bridge.run_pit_v6b(
        prices,
        snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
    )
    guarded_eq, guarded_decisions = run_guarded_v6b(prices, snapshots, bridge.BASELINE_CONFIG)
    qualified_eq, qualified_decisions = run_guarded_v6b(
        prices,
        snapshots,
        bridge.BASELINE_CONFIG,
        policy="v2_memory_requires_broad_legacy_confirmation",
    )
    curves = {
        "V6A": load_v6a_composite(args.v6a_daily),
        "baseline_v2": baseline_eq,
        "original_pit_guarded": original_eq,
        "legacy_preserve_guarded": guarded_eq,
        "legacy_preserve_qualified": qualified_eq,
        "GLD": benchmark_equity(prices, "US.GLD"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
    }
    baseline_v6ab, _ = run_v6ab(curves, "baseline_v2", args.start, args.end)
    original_v6ab, _ = run_v6ab(curves, "original_pit_guarded", args.start, args.end)
    guarded_v6ab, _ = run_v6ab(curves, "legacy_preserve_guarded", args.start, args.end)
    qualified_v6ab, _ = run_v6ab(curves, "legacy_preserve_qualified", args.start, args.end)
    rows = [
        row_for("baseline_v2_standalone_v6b", baseline_eq, baseline_decisions, args),
        row_for("original_pit_guarded_standalone_v6b", original_eq, original_decisions, args),
        row_for("legacy_preserve_guarded_standalone_v6b", guarded_eq, guarded_decisions, args),
        row_for("legacy_preserve_qualified_standalone_v6b", qualified_eq, qualified_decisions, args),
        row_for("baseline_v2_v6ab_dynamic_b", baseline_v6ab, [], args),
        row_for("original_pit_guarded_v6ab_dynamic_b", original_v6ab, original_decisions, args),
        row_for("legacy_preserve_guarded_v6ab_dynamic_b", guarded_v6ab, guarded_decisions, args),
        row_for("legacy_preserve_qualified_v6ab_dynamic_b", qualified_v6ab, qualified_decisions, args),
    ]
    month_review = build_month_review(
        baseline_eq,
        original_eq,
        guarded_eq,
        baseline_decisions,
        original_decisions,
        guarded_decisions,
    )
    qualified_month_review = build_month_review(
        baseline_eq,
        original_eq,
        qualified_eq,
        baseline_decisions,
        original_decisions,
        qualified_decisions,
    )
    payload = {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "replay_json": str(args.replay_json),
        "rows": rows,
        "month_review": month_review,
        "qualified_month_review": qualified_month_review,
        "decision": decision_for_payload(rows, month_review, qualified_month_review),
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
    (REPORT_ROOT / "V6AB_Legacy_Winner_Preservation_Experiment_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Legacy_Winner_Preservation_Experiment_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
