#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from v6b_synthetic_historical import build_price_matrix
from v6b_theme_rotation_backtest import month_end_dates


ROOT = Path(__file__).resolve().parent
DEFAULT_UNIVERSE = ROOT / "v6_strategy_lab" / "configs" / "radar_theme_rotation_universe_v1.json"
DEFAULT_OUT_DIR = ROOT / "v6_strategy_lab" / "configs" / "synthetic_history" / "20260520_v4_cross_theme_pit"


RADAR_TO_V6B_THEME = {
    "ai_compute_and_data_center": "semis_ai",
    "software_and_internet": "technology",
    "robotics_and_embodied_ai": "industrials_infra",
    "financials_and_capital_markets": "financials",
    "healthcare_and_biotech": "healthcare_biotech",
    "energy_and_commodities": "energy_resources",
    "gold_and_precious_metals": "precious_metals",
    "utilities_power_and_infrastructure": "utilities_power",
    "consumer_discretionary": "consumer_discretionary",
}

QUALITY_PROFILES: dict[str, dict[str, Any]] = {
    "none": {"description": "Original price-only trend eligibility."},
    "v6b_quality_v1": {
        "description": "Stricter point-in-time gates for real-stock V6-B candidates; no forward returns used.",
        "default": {"min_mom60": 0.03, "min_mom120": 0.00, "min_score": 0.04, "max_drawdown": -0.50},
        "themes": {
            "ai_compute_and_data_center": {"min_mom60": 0.05, "min_mom120": 0.00, "min_score": 0.06, "max_drawdown": -0.55},
            "software_and_internet": {"min_mom60": 0.04, "min_mom120": 0.00, "min_score": 0.05, "max_drawdown": -0.50},
            "healthcare_and_biotech": {"min_mom60": 0.03, "min_mom120": 0.00, "min_rel60": -0.02, "min_score": 0.05, "max_drawdown": -0.45},
            "energy_and_commodities": {"min_mom60": 0.04, "min_mom120": 0.00, "min_score": 0.05, "max_drawdown": -0.45},
            "gold_and_precious_metals": {"min_mom60": 0.03, "min_mom120": 0.00, "min_score": 0.04, "max_drawdown": -0.50},
            "financials_and_capital_markets": {"min_mom60": 0.04, "min_mom120": 0.02, "min_rel60": -0.01, "min_score": 0.05, "max_drawdown": -0.40},
            "industrials_infra": {"min_mom60": 0.04, "min_mom120": 0.00, "min_score": 0.05, "max_drawdown": -0.45},
            "utilities_power_and_infrastructure": {"min_mom60": 0.03, "min_mom120": 0.02, "min_score": 0.05, "max_drawdown": -0.40},
            "consumer_discretionary": {"min_mom60": 0.05, "min_mom120": 0.02, "min_rel60": -0.01, "min_score": 0.06, "max_drawdown": -0.45},
        },
    },
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_theme_members(theme: dict[str, Any]) -> list[str]:
    members: list[str] = []
    for key in ["leader_layer", "first_order_beneficiaries", "second_order_infrastructure", "third_order_high_beta"]:
        members.extend(theme.get(key, []))
    return list(dict.fromkeys(members))


def pct_change(series: pd.Series, days: int) -> float | None:
    series = series.dropna()
    if len(series) <= days:
        return None
    base = float(series.iloc[-days - 1])
    if base <= 0:
        return None
    return float(series.iloc[-1] / base - 1.0)


def score_candidate(prices: pd.DataFrame, ticker: str, benchmark: str, as_of: pd.Timestamp) -> dict[str, Any]:
    hist = prices.loc[:as_of, ticker].dropna() if ticker in prices.columns else pd.Series(dtype=float)
    bench = prices.loc[:as_of, benchmark].dropna() if benchmark in prices.columns else pd.Series(dtype=float)
    if len(hist) < 160 or len(bench) < 160:
        return {"eligible": False, "reason": "insufficient_history"}
    mom20 = pct_change(hist, 20)
    mom60 = pct_change(hist, 60)
    mom120 = pct_change(hist, 120)
    bench60 = pct_change(bench, 60)
    bench120 = pct_change(bench, 120)
    if None in {mom20, mom60, mom120, bench60, bench120}:
        return {"eligible": False, "reason": "insufficient_momentum_window"}
    close = float(hist.iloc[-1])
    ma126 = float(hist.tail(126).mean())
    ma200 = float(hist.tail(200).mean()) if len(hist) >= 200 else ma126
    high252 = float(hist.tail(252).max())
    if ma126 <= 0 or ma200 <= 0 or high252 <= 0:
        return {"eligible": False, "reason": "invalid_reference"}
    above_ma126 = close > ma126
    above_ma200 = close > ma200
    drawdown = close / high252 - 1.0
    rel60 = float(mom60 - bench60)
    rel120 = float(mom120 - bench120)
    if not above_ma126 or mom60 <= 0:
        return {"eligible": False, "reason": "weak_trend"}
    score = (
        float(mom20) * 0.15
        + float(mom60) * 0.30
        + float(mom120) * 0.25
        + rel60 * 0.20
        + rel120 * 0.10
        + (0.08 if above_ma200 else -0.05)
        + max(drawdown, -0.35) * 0.10
    )
    return {
        "eligible": True,
        "score": score,
        "mom20": mom20,
        "mom60": mom60,
        "mom120": mom120,
        "rel60": rel60,
        "rel120": rel120,
        "above_ma126": above_ma126,
        "above_ma200": above_ma200,
        "drawdown_from_high": drawdown,
        "history_days": int(len(hist)),
    }


def quality_gate(theme_id: str, metrics: dict[str, Any], profile_name: str) -> tuple[bool, str | None]:
    if profile_name == "none":
        return True, None
    profile = QUALITY_PROFILES.get(profile_name)
    if profile is None:
        raise ValueError(f"unknown quality profile: {profile_name}")
    gates = dict(profile.get("default", {}))
    gates.update(profile.get("themes", {}).get(theme_id, {}))
    checks = [
        ("min_mom60", "mom60", lambda actual, threshold: actual >= threshold),
        ("min_mom120", "mom120", lambda actual, threshold: actual >= threshold),
        ("min_rel60", "rel60", lambda actual, threshold: actual >= threshold),
        ("min_rel120", "rel120", lambda actual, threshold: actual >= threshold),
        ("min_score", "score", lambda actual, threshold: actual >= threshold),
        ("max_drawdown", "drawdown_from_high", lambda actual, threshold: actual >= threshold),
    ]
    for gate_key, metric_key, predicate in checks:
        if gate_key not in gates:
            continue
        actual = metrics.get(metric_key)
        if actual is None or not np.isfinite(actual) or not predicate(float(actual), float(gates[gate_key])):
            return False, f"quality_{gate_key}"
    return True, None


def build_snapshots(universe: dict[str, Any], prices: pd.DataFrame, start: str, end: str, max_per_theme: int, quality_profile: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    monthly_dates = [dt for dt in month_end_dates(prices.index) if pd.Timestamp(start) <= dt <= pd.Timestamp(end)]
    theme_defs = []
    for theme in universe.get("themes", []):
        v6b_theme = RADAR_TO_V6B_THEME.get(theme["theme_id"])
        if not v6b_theme:
            continue
        members = flatten_theme_members(theme)
        benchmarks = list(theme.get("benchmarks", []))
        benchmark = benchmarks[0] if benchmarks else "US.SPY"
        theme_defs.append({**theme, "v6b_theme": v6b_theme, "members": members, "benchmark": benchmark})

    snapshots: list[dict[str, Any]] = []
    selection_counts: dict[str, dict[str, Any]] = {}
    for as_of in monthly_dates:
        selected: dict[str, list[str]] = {}
        detail: dict[str, Any] = {}
        entry_count = 0
        for theme in theme_defs:
            rows = []
            blocked = []
            for ticker in theme["members"]:
                if ticker not in prices.columns:
                    blocked.append({"ticker": ticker, "reason": "missing_price"})
                    continue
                metrics = score_candidate(prices, ticker, theme["benchmark"], as_of)
                if not metrics.get("eligible"):
                    blocked.append({"ticker": ticker, "reason": metrics.get("reason", "unknown")})
                    continue
                passes, reason = quality_gate(theme["theme_id"], metrics, quality_profile)
                if not passes:
                    blocked.append({"ticker": ticker, "reason": reason})
                    continue
                rows.append({"ticker": ticker, **metrics})
            rows.sort(key=lambda row: (row["score"], row["mom60"], row["mom120"]), reverse=True)
            winners = [row["ticker"] for row in rows[:max_per_theme]]
            selected[theme["v6b_theme"]] = winners
            detail[theme["v6b_theme"]] = {
                "label": theme.get("label", theme["v6b_theme"]),
                "source_theme_id": theme["theme_id"],
                "benchmark": theme["benchmark"],
                "selected": winners,
                "candidate_count": len(rows),
                "blocked": blocked[:12],
            }
            entry_count += len(winners)
            for ticker in winners:
                item = selection_counts.setdefault(ticker, {"ticker": ticker, "themes": set(), "selected_months": 0, "first_selected": None, "last_selected": None})
                item["themes"].add(theme["v6b_theme"])
                item["selected_months"] += 1
                item["first_selected"] = item["first_selected"] or str(as_of.date())
                item["last_selected"] = str(as_of.date())
        snapshots.append(
            {
                "as_of": str(as_of.date()),
                "entry_count": entry_count,
                "track_counts": {key: len(value) for key, value in selected.items()},
                "selected": selected,
                "detail": detail,
            }
        )
    serializable_counts = []
    for row in selection_counts.values():
        serializable_counts.append({**row, "themes": sorted(row["themes"])})
    summary = {"selection_counts": sorted(serializable_counts, key=lambda row: row["selected_months"], reverse=True)}
    return snapshots, summary


def write_outputs(out_dir: Path, payload: dict[str, Any], summary: dict[str, Any]) -> None:
    out_dir = out_dir.resolve()
    snapshot_dir = out_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    for row in payload["snapshots"]:
        path = snapshot_dir / f"{row['as_of']}_v6b_cross_theme_universe.json"
        path.write_text(json.dumps({**payload["snapshot_header"], **row}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        manifest_rows.append({key: value for key, value in row.items() if key != "detail"} | {"path": str(path.relative_to(ROOT))})

    manifest = {
        **payload["manifest_header"],
        "snapshot_count": len(manifest_rows),
        "snapshots": manifest_rows,
        "selection_counts": summary["selection_counts"],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# V6-B Cross-Theme Point-in-Time Universe",
        "",
        f"- Generated: `{payload['manifest_header']['generated_at']}`",
        f"- Universe: `{payload['manifest_header']['source_universe']}`",
        f"- Snapshots: `{len(manifest_rows)}`",
        "- Boundary: price-only monthly reconstruction from the current cross-theme watch universe; no Futu quota used.",
        "",
        "## Most Frequently Selected",
        "",
        "| ticker | themes | first | last | months |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in summary["selection_counts"][:30]:
        lines.append(f"| `{row['ticker']}` | `{', '.join(row['themes'])}` | `{row['first_selected']}` | `{row['last_selected']}` | {row['selected_months']} |")
    lines.extend(["", "## Recent Snapshots", "", "| as_of | entry_count | selected |", "| --- | ---: | --- |"])
    for row in manifest_rows[-12:]:
        selected = "; ".join(f"{theme}:{','.join(tickers)}" for theme, tickers in row["selected"].items() if tickers)
        lines.append(f"| `{row['as_of']}` | {row['entry_count']} | {selected} |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a cross-theme point-in-time V6-B universe from local cached prices.")
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--max-per-theme", type=int, default=3)
    parser.add_argument("--quality-profile", choices=sorted(QUALITY_PROFILES), default="none")
    args = parser.parse_args()

    universe_path = Path(args.universe)
    universe = load_json(universe_path)
    tickers = set(universe.get("market_benchmarks", []))
    for theme in universe.get("themes", []):
        tickers.update(theme.get("benchmarks", []))
        tickers.update(flatten_theme_members(theme))
    tickers.discard("CASH")
    prices = build_price_matrix(sorted(tickers), args.start, args.end).ffill(limit=3)
    snapshots, summary = build_snapshots(universe, prices, args.start, args.end, args.max_per_theme, args.quality_profile)
    generated_at = datetime.now().isoformat(timespec="seconds")
    payload = {
        "manifest_header": {
            "generated_at": generated_at,
            "policy_id": "V6B_CROSS_THEME_PIT_PRICE_ONLY_V0",
            "source_universe": str(universe_path.relative_to(ROOT) if universe_path.is_relative_to(ROOT) else universe_path),
            "start": args.start,
            "end": args.end,
            "max_per_theme": args.max_per_theme,
            "quality_profile": args.quality_profile,
            "quality_profile_description": QUALITY_PROFILES[args.quality_profile]["description"],
            "rules": {
                "no_lookahead_price_signals": True,
                "price_only_generator": True,
                "current_watch_universe_boundary": True,
                "not_for_live_trading": True,
            },
        },
        "snapshot_header": {
            "status": "research_synthetic_historical",
            "policy_id": "V6B_CROSS_THEME_PIT_PRICE_ONLY_V0",
            "rules": {
                "no_lookahead_price_signals": True,
                "price_only_generator": True,
                "not_for_live_trading": True,
            },
            "quality_profile": args.quality_profile,
        },
        "snapshots": snapshots,
    }
    out_dir = Path(args.out_dir)
    write_outputs(out_dir, payload, summary)
    print(f"Manifest: {out_dir / 'manifest.json'}")
    print(f"Summary:  {out_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
