#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

import v6ab_classifier_bridge_backtest as bridge
import v6ab_pit_classifier_bridge_backtest as pit
import v6b_theme_rotation_backtest as bt
from v6ab_sleeve_blend_backtest import benchmark_equity, load_v6a_composite


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_signal_sizing_experiment"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"
DEFAULT_V6A_DAILY = bridge.DEFAULT_V6A_DAILY


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


def theme_by_id(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("theme")): row for row in snap.get("themes", []) if row.get("theme")}


def active_theme_rows(snap: dict[str, Any]) -> list[dict[str, Any]]:
    by_theme = theme_by_id(snap)
    active_ids = list(snap.get("override_allowlist") or snap.get("boost_allowlist") or [])
    return [by_theme.get(theme_id, {"theme": theme_id}) for theme_id in active_ids]


def quality_features(snap: dict[str, Any]) -> dict[str, Any]:
    rows = active_theme_rows(snap)
    if not rows:
        return {
            "active_theme_count": 0,
            "min_entry_quality": 100.0,
            "min_fact_precision": 100.0,
            "max_crowding": 0.0,
            "actions": [],
            "active_themes": [],
        }
    return {
        "active_theme_count": len(rows),
        "min_entry_quality": min(float(row.get("entry_quality_score", 0.0) or 0.0) for row in rows),
        "min_fact_precision": min(float(row.get("fact_precision_score", 0.0) or 0.0) for row in rows),
        "max_crowding": max(float(row.get("crowding_score", 0.0) or 0.0) for row in rows),
        "actions": [str(row.get("entry_quality_action", "")) for row in rows],
        "active_themes": [str(row.get("theme", "")) for row in rows],
    }


def scale_no_entry_to_low(features: dict[str, Any]) -> float:
    return 0.0 if "NO_ENTRY_EDGE" in features.get("actions", []) else 1.0


def scale_low_fact_entry_half(features: dict[str, Any]) -> float:
    if float(features.get("min_entry_quality", 100.0)) < 50 or float(features.get("min_fact_precision", 100.0)) < 20:
        return 0.5
    return 1.0


def scale_quality_risk_ladder(features: dict[str, Any]) -> float:
    scale = 1.0
    if float(features.get("min_entry_quality", 100.0)) < 50 or float(features.get("min_fact_precision", 100.0)) < 20:
        scale = min(scale, 0.5)
    if "NO_ENTRY_EDGE" in features.get("actions", []):
        scale = min(scale, 0.33)
    if float(features.get("max_crowding", 0.0)) >= 90:
        scale = min(scale, 0.67)
    return scale


def build_scale_schedule(
    snapshots: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    rule: Callable[[dict[str, Any]], float],
) -> tuple[dict[pd.Timestamp, float], list[dict[str, Any]]]:
    by_asof = {str(snap.get("asof")): snap for snap in snapshots}
    schedule: dict[pd.Timestamp, float] = {}
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        dt = pd.Timestamp(decision["date"])
        snap = by_asof.get(str(decision.get("pit_asof")), {})
        if not snap or decision.get("fallback_to_v2", True):
            scale = 1.0
            features = quality_features({})
        else:
            features = quality_features(snap)
            scale = max(0.0, min(1.0, float(rule(features))))
        schedule[dt] = scale
        rows.append(
            {
                "date": str(dt.date()),
                "pit_asof": decision.get("pit_asof"),
                "fallback_to_v2": bool(decision.get("fallback_to_v2", True)),
                "scale": scale,
                **features,
            }
        )
    return schedule, rows


def schedule_scale_for_date(schedule: dict[pd.Timestamp, float], dates: list[pd.Timestamp], dt: pd.Timestamp) -> float:
    pos = np.searchsorted(dates, dt, side="right") - 1
    if pos < 0:
        return 1.0
    return float(schedule.get(dates[pos], 1.0))


def quality_scaled_dynamic_b_sizing_equity(
    curves: dict[str, pd.Series],
    *,
    b_key: str,
    quality_schedule: dict[pd.Timestamp, float],
    b_low: float,
    b_mid: float,
    b_high: float,
    b_strong_126d: float,
    b_weak_63d: float,
    hedge_max: float,
    vol_threshold: float,
    corr_threshold: float,
    dd_threshold: float,
    start: str,
    end: str,
) -> tuple[pd.Series, pd.DataFrame]:
    frame = pd.DataFrame(curves).sort_index().ffill().dropna()
    frame = frame[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
    rets = frame.pct_change().fillna(0.0)
    spy_ma = frame["SPY"].rolling(200).mean()
    qqq_ma = frame["QQQ"].rolling(200).mean()
    gld_ma = frame["GLD"].rolling(126).mean()
    b_mom_63 = frame[b_key].pct_change(63)
    b_mom_126 = frame[b_key].pct_change(126)
    ab_corr = rets["V6A"].rolling(63).corr(rets[b_key])
    schedule_dates = sorted(quality_schedule)

    equity = bt.INITIAL_CAPITAL
    base_equity = 1.0
    base_peak = 1.0
    records: list[tuple[pd.Timestamp, float]] = []
    rows: list[dict[str, Any]] = []
    for i, dt in enumerate(frame.index):
        if i == 0:
            scale = schedule_scale_for_date(quality_schedule, schedule_dates, dt)
            cap = b_low + (b_mid - b_low) * scale
            b_weight = min(b_mid, cap)
            weights = {"V6A": 1.0 - b_weight, b_key: b_weight, "GLD": 0.0, "BIL": 0.0}
        else:
            prev = frame.index[i - 1]
            market_ok = (
                pd.notna(spy_ma.loc[prev])
                and pd.notna(qqq_ma.loc[prev])
                and frame.loc[prev, "SPY"] > spy_ma.loc[prev]
                and frame.loc[prev, "QQQ"] > qqq_ma.loc[prev]
            )
            market_bad = (
                pd.notna(spy_ma.loc[prev])
                and pd.notna(qqq_ma.loc[prev])
                and (frame.loc[prev, "SPY"] < spy_ma.loc[prev] or frame.loc[prev, "QQQ"] < qqq_ma.loc[prev])
            )
            b_weight = b_mid
            if pd.notna(b_mom_126.loc[prev]) and b_mom_126.loc[prev] >= b_strong_126d and market_ok:
                b_weight = b_high
            if pd.notna(b_mom_63.loc[prev]) and b_mom_63.loc[prev] <= b_weak_63d:
                b_weight = b_low
            if market_bad and pd.notna(ab_corr.loc[prev]) and ab_corr.loc[prev] >= corr_threshold:
                b_weight = min(b_weight, b_low)

            scale = schedule_scale_for_date(quality_schedule, schedule_dates, prev)
            cap = b_low + (b_high - b_low) * scale
            b_weight = min(b_weight, cap)

            a_weight = 1.0 - b_weight
            base_ret = a_weight * float(rets.loc[dt, "V6A"]) + b_weight * float(rets.loc[dt, b_key])
            base_equity *= 1.0 + base_ret
            base_peak = max(base_peak, base_equity)
            base_dd = base_equity / base_peak - 1.0
            blend_ret = a_weight * rets["V6A"] + b_weight * rets[b_key]
            base_vol = float(blend_ret.iloc[max(0, i - 63) : i].std() * np.sqrt(252)) if i > 20 else np.nan
            trigger_count = 0
            if market_bad:
                trigger_count += 1
            if np.isfinite(base_vol) and base_vol >= vol_threshold:
                trigger_count += 1
            if base_dd <= dd_threshold:
                trigger_count += 1
            if market_bad and pd.notna(ab_corr.loc[prev]) and ab_corr.loc[prev] >= corr_threshold:
                trigger_count += 1
            hedge_weight = hedge_max if trigger_count >= 2 else (hedge_max * 0.5 if trigger_count == 1 else 0.0)
            hedge_asset = "GLD" if pd.notna(gld_ma.loc[prev]) and frame.loc[prev, "GLD"] >= gld_ma.loc[prev] else "BIL"
            weights = {"V6A": a_weight * (1.0 - hedge_weight), b_key: b_weight * (1.0 - hedge_weight), "GLD": 0.0, "BIL": 0.0}
            weights[hedge_asset] = hedge_weight

        day_ret = sum(float(rets.loc[dt, key]) * weight for key, weight in weights.items() if key in rets.columns)
        equity *= 1.0 + day_ret
        records.append((dt, equity))
        rows.append(
            {
                "date": str(dt.date()),
                "equity": round(float(equity), 2),
                "quality_scale": round(float(scale), 6),
                "weights": json.dumps({key: round(float(value), 6) for key, value in weights.items() if value > 1e-9}, sort_keys=True),
            }
        )
    return pd.Series([value for _, value in records], index=[dt for dt, _ in records]), pd.DataFrame(rows)


def summarize_candidate(
    name: str,
    eq: pd.Series,
    baseline_v6ab: pd.Series,
    guarded_v6ab: pd.Series,
    schedule_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    stats = bt.stats(eq)
    baseline_stats = bt.stats(baseline_v6ab)
    guarded_stats = bt.stats(guarded_v6ab)
    periods = {
        "2020": period_stats(eq, "2020-01-01", "2020-12-31"),
        "2022": period_stats(eq, "2022-01-01", "2022-12-31"),
        "2024_2026": period_stats(eq, "2024-01-01", args.end),
    }
    baseline_periods = {
        "2020": period_stats(baseline_v6ab, "2020-01-01", "2020-12-31"),
        "2022": period_stats(baseline_v6ab, "2022-01-01", "2022-12-31"),
        "2024_2026": period_stats(baseline_v6ab, "2024-01-01", args.end),
    }
    guarded_periods = {
        "2020": period_stats(guarded_v6ab, "2020-01-01", "2020-12-31"),
        "2022": period_stats(guarded_v6ab, "2022-01-01", "2022-12-31"),
        "2024_2026": period_stats(guarded_v6ab, "2024-01-01", args.end),
    }
    changed = [row for row in schedule_rows if float(row.get("scale", 1.0)) < 1.0 and not row.get("fallback_to_v2", True)]
    return {
        "candidate": name,
        "stats": stats,
        "periods": periods,
        "delta_vs_v2": {
            "ann_delta": stats.get("ann_ret", 0.0) - baseline_stats.get("ann_ret", 0.0),
            "sharpe_delta": stats.get("sharpe", 0.0) - baseline_stats.get("sharpe", 0.0),
            "max_dd_delta": stats.get("max_dd", 0.0) - baseline_stats.get("max_dd", 0.0),
            "ann_2020_delta": periods["2020"].get("ann_ret", 0.0) - baseline_periods["2020"].get("ann_ret", 0.0),
            "ann_2022_delta": periods["2022"].get("ann_ret", 0.0) - baseline_periods["2022"].get("ann_ret", 0.0),
            "ann_2024_2026_delta": periods["2024_2026"].get("ann_ret", 0.0) - baseline_periods["2024_2026"].get("ann_ret", 0.0),
        },
        "delta_vs_guarded": {
            "ann_delta": stats.get("ann_ret", 0.0) - guarded_stats.get("ann_ret", 0.0),
            "sharpe_delta": stats.get("sharpe", 0.0) - guarded_stats.get("sharpe", 0.0),
            "max_dd_delta": stats.get("max_dd", 0.0) - guarded_stats.get("max_dd", 0.0),
            "ann_2020_delta": periods["2020"].get("ann_ret", 0.0) - guarded_periods["2020"].get("ann_ret", 0.0),
            "ann_2022_delta": periods["2022"].get("ann_ret", 0.0) - guarded_periods["2022"].get("ann_ret", 0.0),
            "ann_2024_2026_delta": periods["2024_2026"].get("ann_ret", 0.0) - guarded_periods["2024_2026"].get("ann_ret", 0.0),
        },
        "scaled_active_months": len(changed),
        "avg_active_scale": float(np.mean([float(row.get("scale", 1.0)) for row in changed])) if changed else 1.0,
        "scaled_rows": changed[:30],
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    if not snapshots:
        raise SystemExit(f"empty replay snapshots: {args.replay_json}")

    prices = bt.build_price_matrix(pit.required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    baseline_eq, _ = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    guarded_eq, guarded_decisions = pit.run_pit_v6b(
        prices,
        snapshots,
        bridge.BASELINE_CONFIG,
        mode="tier_turnover_guarded",
        turnover_guard_threshold=args.turnover_guard,
    )
    curves = build_base_curves(prices, baseline_eq, args)
    curves["pit_tier_turnover_guarded"] = guarded_eq
    baseline_v6ab = bridge.run_v6ab(curves, "baseline_v2", 0.45, args.start, args.end)[0]
    guarded_v6ab = quality_scaled_dynamic_b_sizing_equity(
        curves,
        b_key="pit_tier_turnover_guarded",
        quality_schedule={},
        b_low=0.05,
        b_mid=min(0.30, args.cap),
        b_high=args.cap,
        b_strong_126d=0.08,
        b_weak_63d=-0.08,
        hedge_max=0.30,
        vol_threshold=0.28,
        corr_threshold=0.60,
        dd_threshold=-0.12,
        start=args.start,
        end=args.end,
    )[0]

    rules: list[tuple[str, Callable[[dict[str, Any]], float]]] = [
        ("baseline_guarded_no_signal_sizing", lambda features: 1.0),
        ("cap_no_entry_edge_to_low", scale_no_entry_to_low),
        ("cap_low_fact_or_entry_half", scale_low_fact_entry_half),
        ("cap_quality_risk_ladder", scale_quality_risk_ladder),
    ]
    rows: list[dict[str, Any]] = []
    for name, rule in rules:
        schedule, schedule_rows = build_scale_schedule(snapshots, guarded_decisions, rule)
        eq, _ = quality_scaled_dynamic_b_sizing_equity(
            curves,
            b_key="pit_tier_turnover_guarded",
            quality_schedule=schedule,
            b_low=0.05,
            b_mid=min(0.30, args.cap),
            b_high=args.cap,
            b_strong_126d=0.08,
            b_weak_63d=-0.08,
            hedge_max=0.30,
            vol_threshold=0.28,
            corr_threshold=0.60,
            dd_threshold=-0.12,
            start=args.start,
            end=args.end,
        )
        rows.append(summarize_candidate(name, eq, baseline_v6ab, guarded_v6ab, schedule_rows, args))

    baseline_row = rows[0]
    promoted = [
        row
        for row in rows[1:]
        if row["delta_vs_guarded"]["ann_delta"] > 0.001
        and row["delta_vs_guarded"]["sharpe_delta"] >= 0.0
        and row["delta_vs_v2"]["ann_delta"] > baseline_row["delta_vs_v2"]["ann_delta"]
        and row["delta_vs_v2"]["ann_2020_delta"] >= baseline_row["delta_vs_v2"]["ann_2020_delta"] - 0.01
        and row["scaled_active_months"] >= 3
    ]
    ranked = sorted(
        rows,
        key=lambda row: (
            row["delta_vs_guarded"]["ann_delta"],
            row["delta_vs_guarded"]["sharpe_delta"],
            row["delta_vs_v2"]["ann_2024_2026_delta"],
        ),
        reverse=True,
    )
    return {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "turnover_guard": args.turnover_guard,
        "cap": args.cap,
        "baseline_v2": {
            "candidate": "baseline_v2_v6ab_dynamic_b",
            "stats": bt.stats(baseline_v6ab),
            "periods": {
                "2020": period_stats(baseline_v6ab, "2020-01-01", "2020-12-31"),
                "2022": period_stats(baseline_v6ab, "2022-01-01", "2022-12-31"),
                "2024_2026": period_stats(baseline_v6ab, "2024-01-01", args.end),
            },
        },
        "guarded": {
            "candidate": "pit_tier_turnover_guarded_v6ab_dynamic_b",
            "stats": bt.stats(guarded_v6ab),
            "periods": {
                "2020": period_stats(guarded_v6ab, "2020-01-01", "2020-12-31"),
                "2022": period_stats(guarded_v6ab, "2022-01-01", "2022-12-31"),
                "2024_2026": period_stats(guarded_v6ab, "2024-01-01", args.end),
            },
        },
        "rows": rows,
        "ranked": ranked,
        "decision": "REVIEW_SIGNAL_SIZING_CANDIDATE" if promoted else "NO_SIGNAL_SIZING_PROMOTION",
        "promoted_candidates": [row["candidate"] for row in promoted],
        "interpretation": [
            "该实验只改变 V6AB 对 PIT B sleeve 的表达强度，不改变 PIT 主题识别、allowlist 或模拟盘。",
            "低 fact precision / 低 entry quality 先降仓，而不是直接删除主题；这是为了验证方向正确但证据不足时是否应该少押。",
            "若提升小于门槛或只靠压低 active 表达获得，应保持 WATCH/诊断层。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB Signal Sizing Experiment",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- turnover guard：`{payload['turnover_guard']:.2f}`",
        f"- B cap：`{payload['cap']:.0%}`",
        f"- decision：`{payload['decision']}`",
        f"- promoted candidates：`{', '.join(payload.get('promoted_candidates', [])) or 'none'}`",
        "- 模拟盘动作：`NO_CHANGE`。",
        "",
        "## Ranked Candidates",
        "",
        "| candidate | ann | maxDD | Sharpe | ann vs V2 | ann vs guarded | 2020 vs guarded | 2024-2026 vs guarded | scaled months | avg scale |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["ranked"]:
        stats = row["stats"]
        dv2 = row["delta_vs_v2"]
        dg = row["delta_vs_guarded"]
        lines.append(
            f"| `{row['candidate']}` | {fmt_pct(stats.get('ann_ret'))} | {fmt_pct(stats.get('max_dd'))} | "
            f"{stats.get('sharpe', 0.0):.2f} | {fmt_pct(dv2.get('ann_delta'))} | "
            f"{fmt_pct(dg.get('ann_delta'))} | {fmt_pct(dg.get('ann_2020_delta'))} | "
            f"{fmt_pct(dg.get('ann_2024_2026_delta'))} | {row.get('scaled_active_months', 0)} | "
            f"{row.get('avg_active_scale', 1.0):.2f} |"
        )
    lines += [
        "",
        "## Baselines",
        "",
        "| baseline | ann | maxDD | Sharpe | 2020 ann | 2022 ann | 2024-2026 ann |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ["baseline_v2", "guarded"]:
        row = payload[key]
        stats = row["stats"]
        periods = row["periods"]
        lines.append(
            f"| `{row['candidate']}` | {fmt_pct(stats.get('ann_ret'))} | {fmt_pct(stats.get('max_dd'))} | "
            f"{stats.get('sharpe', 0.0):.2f} | {fmt_pct(periods['2020'].get('ann_ret'))} | "
            f"{fmt_pct(periods['2022'].get('ann_ret'))} | {fmt_pct(periods['2024_2026'].get('ann_ret'))} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
    ]
    lines.extend(f"- {item}" for item in payload.get("interpretation", []))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test V6AB signal quality sizing without changing paper sim.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--v6a-daily", type=Path, default=DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--turnover-guard", type=float, default=1.40)
    parser.add_argument("--cap", type=float, default=0.45)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Signal_Sizing_Experiment_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Signal_Sizing_Experiment_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
