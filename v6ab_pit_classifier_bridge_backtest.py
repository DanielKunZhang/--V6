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
from v6ab_sleeve_blend_backtest import benchmark_equity, dynamic_b_sizing_equity, load_v6a_composite


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_daily_evolution"
DEFAULT_REPLAY = OUT_DIR / "pit_replay" / "latest_pit_classifier_replay.json"
DEFAULT_V6A_DAILY = bridge.DEFAULT_V6A_DAILY


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_for_date(snapshots: list[dict[str, Any]], dt: pd.Timestamp) -> dict[str, Any]:
    chosen: dict[str, Any] = {}
    for snap in snapshots:
        if pd.Timestamp(snap["asof"]) <= dt:
            chosen = snap
        else:
            break
    return chosen


def bridge_themes_from_snapshot(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return bridge.build_bridge_themes(
        {
            "theme_allowlist": snap.get("theme_allowlist", []),
            "ticker_priority": snap.get("ticker_priority", []),
        }
    )


def required_tickers_for_replay(snapshots: list[dict[str, Any]]) -> list[str]:
    tickers = {"US.SPY", "US.QQQ", "US.GLD", "US.BIL", "US.IEF"}
    for snap in snapshots:
        themes = bridge_themes_from_snapshot(snap)
        tickers.update(bridge.required_tickers(themes))
    tickers.update(bridge.required_tickers({"semis_ai": dict(bt.THEMES["semis_ai"])}))
    return sorted(tickers)


def has_confirmed_theme(snap: dict[str, Any]) -> bool:
    return any(row.get("state") == "CONFIRMED" for row in snap.get("themes", []))


def overlay_themes_from_snapshot(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    themes = dict(bt.THEMES)
    themes.update(bridge_themes_from_snapshot(snap))
    return themes


def tier_themes_from_snapshot(snap: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], str]:
    if snap.get("override_allowlist"):
        tier_snap = dict(snap)
        tier_snap["theme_allowlist"] = list(snap.get("override_allowlist", []))
        return bridge_themes_from_snapshot(tier_snap), "OVERRIDE"
    if snap.get("boost_allowlist"):
        tier_snap = dict(snap)
        tier_snap["theme_allowlist"] = list(snap.get("boost_allowlist", []))
        themes = dict(bt.THEMES)
        themes.update(bridge_themes_from_snapshot(tier_snap))
        return themes, "BOOST"
    return dict(bt.THEMES), "WATCH"


def run_pit_v6b(
    prices: pd.DataFrame,
    snapshots: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    mode: str = "hard_replace",
) -> tuple[pd.Series, list[dict[str, Any]]]:
    monthly_dates = [dt for dt in bt.month_end_dates(prices.index) if dt in prices.index]
    monthly = prices.loc[monthly_dates].dropna(how="all")
    returns = prices.pct_change().fillna(0.0)
    equity = bt.INITIAL_CAPITAL
    peak = equity
    current_weights = {"CASH": 1.0}
    preview: dict[pd.Timestamp, tuple[dict[str, float], list[dict[str, Any]], dict[str, Any]]] = {}
    decisions: list[dict[str, Any]] = []
    pick_config = {key: value for key, value in config.items() if key != "dd_brake"}
    use_dd_brake = bool(config.get("dd_brake"))

    old_themes = bt.THEMES
    try:
        for dt in monthly.index:
            dt = pd.Timestamp(dt)
            bt.THEMES = old_themes
            snap = snapshot_for_date(snapshots, dt)
            if monthly.index.get_loc(dt) < 12:
                weights, rows = {"CASH": 1.0}, []
            elif not snap or not snap.get("theme_allowlist"):
                weights, rows = bt.pick_weights(monthly, dt, **pick_config)
            else:
                pit_tier = "BOOST" if snap.get("theme_allowlist") else "WATCH"
                if mode == "tier":
                    themes, pit_tier = tier_themes_from_snapshot(snap)
                elif mode == "overlay" and not has_confirmed_theme(snap):
                    themes = overlay_themes_from_snapshot(snap)
                else:
                    pit_tier = "OVERRIDE" if mode == "hard_replace" else pit_tier
                    themes = bridge_themes_from_snapshot(snap)
                bt.THEMES = themes
                pit_config = dict(pick_config)
                pit_config["top_n"] = max(1, min(3, len(themes)))
                pit_config["stock_top_n"] = 3
                weights, rows = bt.pick_weights(monthly, dt, **pit_config)
            preview[dt] = (weights, rows, snap)

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
                weights, rows, snap = preview[pd.Timestamp(dt)]
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
                        "pit_mode": mode,
                        "pit_signal_tier": pit_tier if snap and snap.get("theme_allowlist") else "WATCH",
                        "pit_confirmed": has_confirmed_theme(snap),
                        "classifier_fallback_to_v2": bool(not snap or snap.get("fallback_to_v2", True)),
                        "fallback_to_v2": bool(not snap or not snap.get("theme_allowlist")),
                        "turnover": round(float(turnover), 6),
                        "top_themes": [
                            {
                                "theme_id": row["theme_id"],
                                "label": row["label"],
                                "selected_proxy": row["selected_proxy"],
                                "theme_score": round(float(row["theme_score"]), 6),
                                "breadth": round(float(row["breadth"]), 6),
                            }
                            for row in rows[:5]
                        ],
                    }
                )
            records.append((pd.Timestamp(dt), equity))
    finally:
        bt.THEMES = old_themes
    return pd.Series([value for _, value in records], index=[dt for dt, _ in records]), decisions


def period_stats(eq: pd.Series, start: str, end: str) -> dict[str, Any]:
    seg = eq[(eq.index >= pd.Timestamp(start)) & (eq.index <= pd.Timestamp(end))]
    if len(seg) < 30:
        return {}
    return bt.stats(seg / float(seg.iloc[0]) * bt.INITIAL_CAPITAL)


def decision_metrics(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    if not decisions:
        return {"rebalance_count": 0, "avg_turnover": 0.0, "est_cost_drag": 0.0, "pit_active_rebalances": 0}
    turnovers = []
    prev_weights = {"CASH": 1.0}
    for row in decisions:
        if "turnover" in row:
            turnover = float(row.get("turnover", 0.0))
        else:
            weights = dict(row.get("weights", {}))
            turnover = sum(abs(weights.get(k, 0.0) - prev_weights.get(k, 0.0)) for k in set(weights) | set(prev_weights) if k != "CASH")
            prev_weights = weights
        turnovers.append(turnover)
    return {
        "rebalance_count": len(decisions),
        "avg_turnover": float(np.mean(turnovers)),
        "total_turnover": float(np.sum(turnovers)),
        "est_cost_drag": float(np.sum(turnovers) * bt.TX_COST_BPS / 10_000.0),
        "pit_active_rebalances": int(sum(not row.get("fallback_to_v2", True) for row in decisions)),
    }


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB PIT Classifier Bridge Backtest v1",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 回测区间：`{payload['start']} -> {payload['end']}`",
        "- 证据边界：PIT replay 只使用本地 seed evidence 的可见性过滤；不是完整历史新闻/财报证据库。",
        "- 模拟盘动作：`NO_CHANGE_BACKTEST_ONLY`，继续保持 V2。",
        "",
        "## Results",
        "",
        "| candidate | ann | maxDD | Sharpe | 2024-2026 ann | 2022 ann | 2020 ann | avg turnover | est rebalance cost | PIT active rebals |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["rows"]:
        s = row["stats"]
        p = row.get("periods", {})
        m = row.get("turnover_cost", {})
        lines.append(
            f"| {row['candidate']} | {fmt_pct(s.get('ann_ret'))} | {fmt_pct(s.get('max_dd'))} | {s.get('sharpe', 0):.2f} | "
            f"{fmt_pct(p.get('2024_2026', {}).get('ann_ret'))} | {fmt_pct(p.get('2022', {}).get('ann_ret'))} | "
            f"{fmt_pct(p.get('2020', {}).get('ann_ret'))} | {m.get('avg_turnover', 0):.2f} | "
            f"{fmt_pct(m.get('est_cost_drag'))} | {m.get('pit_active_rebalances', 0)} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        "- 该结果用于验证 PIT 接口和防泄漏管线，不构成 V2 替换依据。",
        "- 晋级前仍需更完整的历史 evidence ledger，尤其是 2020、2022、2024 前后的真实主线证据。",
        "- 若 PIT active rebals 很少，说明当前本地 evidence 覆盖不足，不应过度解释收益差异。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest PIT classifier replay through V6AB without touching paper sim.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--extra-evidence-json", default="")
    parser.add_argument("--v6a-daily", type=Path, default=DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    if not snapshots:
        raise SystemExit(f"empty PIT replay: {args.replay_json}")

    prices = bt.build_price_matrix(required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    baseline_eq, baseline_decisions = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    pit_eq, pit_decisions = run_pit_v6b(prices, snapshots, bridge.BASELINE_CONFIG, mode="hard_replace")
    pit_overlay_eq, pit_overlay_decisions = run_pit_v6b(prices, snapshots, bridge.BASELINE_CONFIG, mode="overlay")
    pit_tier_eq, pit_tier_decisions = run_pit_v6b(prices, snapshots, bridge.BASELINE_CONFIG, mode="tier")
    curves = {
        "V6A": load_v6a_composite(args.v6a_daily),
        "baseline_v2": baseline_eq,
        "pit_classifier": pit_eq,
        "pit_classifier_overlay": pit_overlay_eq,
        "pit_classifier_tier": pit_tier_eq,
        "GLD": benchmark_equity(prices, "US.GLD"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
    }
    baseline_v6ab, baseline_log = bridge.run_v6ab(curves, "baseline_v2", 0.45, args.start, args.end)
    active_caps = [
        float(snap.get("b_sleeve_cap_hint", 0.05))
        for snap in snapshots
        if snap.get("theme_allowlist") and not snap.get("fallback_to_v2", True)
    ]
    pit_cap = max(active_caps) if active_caps else 0.45
    pit_v6ab, pit_log = dynamic_b_sizing_equity(
        curves,
        b_key="pit_classifier",
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
    )
    pit_overlay_v6ab, pit_overlay_log = dynamic_b_sizing_equity(
        curves,
        b_key="pit_classifier_overlay",
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
    )
    pit_tier_v6ab, pit_tier_log = dynamic_b_sizing_equity(
        curves,
        b_key="pit_classifier_tier",
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
    )

    rows = []
    for name, eq, decisions in [
        ("baseline_v2_standalone_v6b", baseline_eq, baseline_decisions),
        ("pit_classifier_standalone_v6b", pit_eq, pit_decisions),
        ("pit_overlay_standalone_v6b", pit_overlay_eq, pit_overlay_decisions),
        ("pit_tier_standalone_v6b", pit_tier_eq, pit_tier_decisions),
        ("baseline_v2_v6ab_dynamic_b", baseline_v6ab, []),
        ("pit_classifier_v6ab_dynamic_b", pit_v6ab, pit_decisions),
        ("pit_overlay_v6ab_dynamic_b", pit_overlay_v6ab, pit_overlay_decisions),
        ("pit_tier_v6ab_dynamic_b", pit_tier_v6ab, pit_tier_decisions),
    ]:
        rows.append(
            {
                "candidate": name,
                "stats": bt.stats(eq),
                "periods": {
                    "full": bt.stats(eq),
                    "oos_2024_2026": period_stats(eq, "2024-01-01", args.end),
                    "2024_2026": period_stats(eq, "2024-01-01", args.end),
                    "2022": period_stats(eq, "2022-01-01", "2022-12-31"),
                    "2020": period_stats(eq, "2020-01-01", "2020-12-31"),
                },
                "turnover_cost": decision_metrics(decisions),
            }
        )

    payload = {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "replay_json": str(args.replay_json),
        "evidence_boundary": replay.get("source_boundary"),
        "rows": rows,
        "recent_pit_decisions": pit_decisions[-12:],
        "recent_pit_overlay_decisions": pit_overlay_decisions[-12:],
        "recent_pit_tier_decisions": pit_tier_decisions[-12:],
    }
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest_pit_classifier_bridge_backtest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest_pit_classifier_bridge_backtest.md").write_text(md, encoding="utf-8")
    pd.DataFrame(
        [
            {
                "candidate": row["candidate"],
                **row["stats"],
                "ann_2024_2026": row["periods"]["2024_2026"].get("ann_ret"),
                "ann_2022": row["periods"]["2022"].get("ann_ret"),
                "ann_2020": row["periods"]["2020"].get("ann_ret"),
                **{f"turnover_{k}": v for k, v in row["turnover_cost"].items()},
            }
            for row in rows
        ]
    ).to_csv(args.output_dir / "latest_pit_classifier_bridge_backtest.csv", index=False)
    (REPORT_ROOT / "V6AB_PIT_Classifier_Bridge_Backtest_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_PIT_Classifier_Bridge_Backtest_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
