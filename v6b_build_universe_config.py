#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_POOL = [
    "US.AMZN",
    "US.AVGO",
    "US.GOOGL",
    "US.META",
    "US.MSFT",
    "US.NVDA",
]

SEMI_ETFS = ["US.SOXX", "US.SMH"]

DEFENSIVE_POOL = {
    "US.BIL": 0.35,
    "US.GLD": 0.45,
    "CASH": 0.20,
}


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_scores(path: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(path)
    return {row["ticker"]: row for row in payload.get("rows", [])}


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def active_entries(universe: dict[str, Any], as_of: str) -> list[dict[str, Any]]:
    as_of_dt = parse_date(as_of)
    rows = []
    for entry in universe.get("entries", []):
        if entry.get("status") != "active_research":
            continue
        entry_dt = parse_date(entry["entry_date"])
        exit_raw = entry.get("exit_date")
        exit_dt = parse_date(exit_raw) if exit_raw else None
        if entry_dt <= as_of_dt and (exit_dt is None or as_of_dt <= exit_dt):
            rows.append(entry)
    return rows


def build_config(
    universe: dict[str, Any],
    scores: dict[str, dict[str, Any]],
    as_of: str,
    min_score: float,
) -> dict[str, Any]:
    entries = active_entries(universe, as_of)
    eligible = []
    watch = []
    full = []
    by_track: dict[str, list[str]] = {}

    for entry in entries:
        ticker = entry["ticker"]
        score_row = scores.get(ticker, {})
        score = float(score_row.get("score", 0.0))
        status = score_row.get("status", "research_only")
        full.append(ticker)
        by_track.setdefault(entry["track"], []).append(ticker)
        if status == "eligible_research" and score >= min_score:
            eligible.append(ticker)
        if status in {"eligible_research", "watch"} and score >= 60:
            watch.append(ticker)

    eligible = dedupe(eligible)
    watch = dedupe(watch)
    full = dedupe(full)

    return {
        "version": as_of,
        "strategy_id": "V6-B_RADAR_MOMENTUM_CHALLENGER_POINT_IN_TIME",
        "status": "research_only",
        "description": "Generated from point-in-time Radar universe and scorecard. Not approved for live trading.",
        "as_of": as_of,
        "source_universe": universe.get("universe_id"),
        "source_scorecard": "v6b_scorecard",
        "base_pool": BASE_POOL,
        "semi_etf_pool": SEMI_ETFS,
        "radar_tracks": {track: dedupe(tickers) for track, tickers in sorted(by_track.items())},
        "defensive_pool": DEFENSIVE_POOL,
        "candidate_pool_variants": {
            "v6a_base_only": BASE_POOL,
            "v6b_eligible_only": dedupe(BASE_POOL + eligible + SEMI_ETFS),
            "v6b_watch_plus": dedupe(BASE_POOL + watch + SEMI_ETFS),
            "v6b_full_active": dedupe(BASE_POOL + full + SEMI_ETFS),
        },
        "release_gate": {
            "must_beat_or_complement_v6a": True,
            "min_oos_sharpe_delta_vs_v6a": 0.0,
            "min_combo_ann_return_improvement_pct": 3.0,
            "max_drawdown_worse_than_v6a_pct": 5.0,
            "requires_deterministic_replay": True,
            "requires_no_lookahead_audit": True,
            "requires_live_tradability_check": True,
        },
        "operating_rule": "Generated config is for research backtest only. Universe membership must be re-generated for each as_of date; do not manually backfill winners.",
    }


def write_summary(config: dict[str, Any], path: Path) -> None:
    lines = [
        "# V6-B Generated Universe Config Summary",
        "",
        f"- As Of: `{config['as_of']}`",
        f"- Status: `{config['status']}`",
        f"- Source Universe: `{config.get('source_universe')}`",
        "",
        "| variant | tickers | count |",
        "| --- | --- | ---: |",
    ]
    for variant, tickers in config["candidate_pool_variants"].items():
        lines.append(f"| `{variant}` | `{', '.join(tickers)}` | {len(tickers)} |")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This file is a point-in-time research input.",
            "- It is not a buy list and not a live trading approval.",
            "- Backtest still requires historical price coverage and release-gate review.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build V6-B backtest config from point-in-time universe and scorecard.")
    parser.add_argument("--universe", default="v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json")
    parser.add_argument("--scorecard", default="v6_strategy_lab/scorecards/v6b_scorecard_20260510_seed.json")
    parser.add_argument("--as-of", default="2026-05-10")
    parser.add_argument("--min-score", type=float, default=75.0)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    universe = load_json(Path(args.universe))
    scores = load_scores(Path(args.scorecard))
    config = build_config(universe, scores, args.as_of, args.min_score)

    out_dir = Path("v6_strategy_lab/configs/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = args.tag or args.as_of.replace("-", "")
    json_path = out_dir / f"v6b_generated_universe_{tag}.json"
    md_path = out_dir / f"v6b_generated_universe_{tag}.md"
    json_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_summary(config, md_path)
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")


if __name__ == "__main__":
    main()
