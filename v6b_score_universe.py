#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ticker = row.get("ticker", "").strip()
            if ticker:
                rows[ticker] = row
    return rows


def as_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def status_for(score: float, thresholds: dict[str, Any]) -> str:
    if score >= float(thresholds["eligible"]):
        return "eligible_research"
    if score >= float(thresholds["watch"]):
        return "watch"
    if score < float(thresholds["blocked"]):
        return "blocked"
    return "research_only"


def score_entry(
    entry: dict[str, Any],
    weights: dict[str, float],
    defaults: dict[str, float],
    override: dict[str, Any],
) -> dict[str, Any]:
    total_weight = sum(float(v) for v in weights.values())
    weighted = 0.0
    factors: dict[str, float] = {}
    for factor, weight in weights.items():
        value = as_float(override.get(factor), float(defaults.get(factor, 50)))
        value = max(0.0, min(100.0, value))
        factors[factor] = value
        weighted += value * float(weight)
    score = weighted / total_weight if total_weight else 0.0
    return {
        "ticker": entry["ticker"],
        "track": entry["track"],
        "entry_date": entry["entry_date"],
        "score": round(score, 2),
        "factors": factors,
        "notes": override.get("notes", ""),
        "source": entry.get("source", ""),
        "reason": entry.get("reason", ""),
        "anti_thesis": entry.get("anti_thesis", ""),
    }


def write_markdown(rows: list[dict[str, Any]], output: Path, generated: str) -> None:
    lines = [
        "# V6-B Radar Universe Scorecard",
        "",
        f"- Generated: `{generated}`",
        "- Status: research only; not a buy list.",
        "- Interpretation: score ranks V6-B research candidates before market-data backtest. Final buying still requires V6-B standalone, V6-A comparison, allocator weight, risk-on regime, and live tradability.",
        "",
        "| rank | ticker | track | status | score | notes |",
        "| ---: | --- | --- | --- | ---: | --- |",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(
            f"| {idx} | `{row['ticker']}` | `{row['track']}` | `{row['status']}` | {row['score']:.2f} | {row.get('notes','')} |"
        )
    lines.extend(
        [
            "",
            "## Important Boundary",
            "",
            "- This scorecard does not consume Futu historical K-line quota.",
            "- `price_momentum` and `liquidity_tradability` are currently manual/placeholder factors until data refresh.",
            "- Any live/simulated buying requires a separate V6-B backtest and allocator review.",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score V6-B point-in-time Radar universe.")
    parser.add_argument("--universe", default="v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json")
    parser.add_argument("--policy", default="v6_strategy_lab/configs/v6b_entry_sizing_policy_v1.json")
    parser.add_argument("--overrides", default="v6_strategy_lab/scorecards/v6b_score_overrides_20260510.csv")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    universe = load_json(Path(args.universe))
    policy = load_json(Path(args.policy))
    overrides = load_overrides(Path(args.overrides))
    weights = {k: float(v) for k, v in policy["score_weights"].items()}
    defaults = {k: float(v) for k, v in policy["default_factor_scores"].items()}
    thresholds = policy["score_thresholds"]

    rows = []
    for entry in universe.get("entries", []):
        if entry.get("status") != "active_research":
            continue
        row = score_entry(entry, weights, defaults, overrides.get(entry["ticker"], {}))
        row["status"] = status_for(row["score"], thresholds)
        rows.append(row)

    rows.sort(key=lambda r: (r["score"], r["ticker"]), reverse=True)
    out_dir = Path("v6_strategy_lab/scorecards")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"v6b_scorecard_{args.tag}.json"
    md_path = out_dir / f"v6b_scorecard_{args.tag}.md"
    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "status": "research_only",
        "policy": policy["policy_id"],
        "universe": universe["universe_id"],
        "rows": rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(rows, md_path, payload["generated"])
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")


if __name__ == "__main__":
    main()
