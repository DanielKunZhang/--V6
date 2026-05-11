#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "ticker",
    "entry_date",
    "exit_date",
    "track",
    "source",
    "reason",
    "anti_thesis",
    "status",
}


def parse_date(value: Any, field: str, row_no: int) -> datetime | None:
    if value is None and field == "exit_date":
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"row {row_no}: `{field}` must be YYYY-MM-DD or null for exit_date")
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"row {row_no}: `{field}` invalid date `{value}`") from exc


def audit(path: Path) -> tuple[list[str], dict[str, Any]]:
    config = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []
    entries = config.get("entries", [])
    if not isinstance(entries, list) or not entries:
        errors.append("config must contain non-empty `entries` list")
        return errors, {"warnings": warnings, "entries": 0}

    tickers: Counter[str] = Counter()
    active_tickers: Counter[str] = Counter()
    tracks: Counter[str] = Counter()

    for idx, row in enumerate(entries, start=1):
        missing = sorted(REQUIRED_FIELDS - set(row))
        if missing:
            errors.append(f"row {idx}: missing fields {missing}")
            continue
        ticker = row["ticker"]
        if not isinstance(ticker, str) or not ticker.startswith("US."):
            errors.append(f"row {idx}: ticker should look like `US.XYZ`, got `{ticker}`")
        tickers[ticker] += 1
        if row.get("status") == "active_research":
            active_tickers[ticker] += 1
        tracks[str(row.get("track"))] += 1

        try:
            entry_dt = parse_date(row.get("entry_date"), "entry_date", idx)
            exit_dt = parse_date(row.get("exit_date"), "exit_date", idx)
            if exit_dt is not None and entry_dt is not None and exit_dt < entry_dt:
                errors.append(f"row {idx}: exit_date before entry_date for {ticker}")
            if exit_dt is not None and not row.get("exit_reason"):
                errors.append(f"row {idx}: exit_date requires exit_reason for {ticker}")
        except ValueError as exc:
            errors.append(str(exc))

        for field in ["source", "reason", "anti_thesis"]:
            value = row.get(field)
            if not isinstance(value, str) or len(value.strip()) < 12:
                errors.append(f"row {idx}: `{field}` too short for {ticker}")

    duplicate_active = sorted([ticker for ticker, count in active_tickers.items() if count > 1])
    if duplicate_active:
        errors.append(f"duplicate active tickers: {duplicate_active}")

    duplicate_history = sorted([ticker for ticker, count in tickers.items() if count > 1])
    if duplicate_history:
        warnings.append(f"tickers with multiple history rows: {duplicate_history}")

    summary = {
        "warnings": warnings,
        "entries": len(entries),
        "unique_tickers": len(tickers),
        "active_tickers": len(active_tickers),
        "tracks": dict(sorted(tracks.items())),
    }
    return errors, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit V6-B point-in-time Radar universe config.")
    parser.add_argument("--config", default="v6_strategy_lab/configs/v6b_point_in_time_universe_seed_20260510.json")
    args = parser.parse_args()

    errors, summary = audit(Path(args.config))
    print(json.dumps({"ok": not errors, "errors": errors, **summary}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
