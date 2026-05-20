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


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "v6b_selection_quality"
DEFAULT_MANIFEST = ROOT / "v6_strategy_lab" / "configs" / "synthetic_history" / "20260520_v5_real_stock_pit" / "manifest.json"


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def forward_return(prices: pd.DataFrame, ticker: str, date: pd.Timestamp, days: int) -> float | None:
    if ticker not in prices.columns:
        return None
    series = prices[ticker].dropna()
    future = series[series.index >= date]
    if len(future) <= days:
        return None
    base = float(future.iloc[0])
    target = float(future.iloc[days])
    if base <= 0:
        return None
    return target / base - 1.0


def collect_rows(manifest: dict[str, Any], prices: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snap in manifest.get("snapshots", []):
        as_of = pd.Timestamp(snap["as_of"])
        for theme, tickers in snap.get("selected", {}).items():
            for rank, ticker in enumerate(tickers, start=1):
                row: dict[str, Any] = {"as_of": str(as_of.date()), "theme": theme, "ticker": ticker, "rank": rank}
                for days in [21, 63, 126]:
                    ret = forward_return(prices, ticker, as_of, days)
                    row[f"fwd_{days}d"] = ret
                rows.append(row)
    return rows


def summarize(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    for key, sub in df.groupby(group_cols):
        item: dict[str, Any] = {}
        if not isinstance(key, tuple):
            key = (key,)
        for col, value in zip(group_cols, key):
            item[col] = value
        item["n"] = int(len(sub))
        for horizon in ["fwd_21d", "fwd_63d", "fwd_126d"]:
            valid = sub[horizon].dropna()
            item[f"{horizon}_avg"] = float(valid.mean()) if len(valid) else np.nan
            item[f"{horizon}_median"] = float(valid.median()) if len(valid) else np.nan
            item[f"{horizon}_hit_rate"] = float((valid > 0).mean()) if len(valid) else np.nan
            item[f"{horizon}_n"] = int(len(valid))
        rows.append(item)
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["fwd_63d_avg", "fwd_126d_avg", "n"], ascending=[False, False, False])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit point-in-time V6-B selections by forward returns.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)
    tickers = set()
    for snap in manifest.get("snapshots", []):
        for selected in snap.get("selected", {}).values():
            tickers.update(selected)
    prices = build_price_matrix(sorted(tickers), args.start, args.end).ffill(limit=3)
    rows = collect_rows(manifest, prices)
    df = pd.DataFrame(rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = OUT_DIR / f"v6b_selection_quality_raw_{args.tag}.csv"
    theme_path = OUT_DIR / f"v6b_selection_quality_by_theme_{args.tag}.csv"
    ticker_path = OUT_DIR / f"v6b_selection_quality_by_ticker_{args.tag}.csv"
    theme_ticker_path = OUT_DIR / f"v6b_selection_quality_by_theme_ticker_{args.tag}.csv"
    report_path = OUT_DIR / f"v6b_selection_quality_{args.tag}.md"

    df.to_csv(raw_path, index=False)
    by_theme = summarize(df, ["theme"])
    by_ticker = summarize(df, ["ticker"])
    by_theme_ticker = summarize(df, ["theme", "ticker"])
    by_theme.to_csv(theme_path, index=False)
    by_ticker.to_csv(ticker_path, index=False)
    by_theme_ticker.to_csv(theme_ticker_path, index=False)

    lines = [
        "# V6-B PIT Selection Quality Audit",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Manifest: `{manifest_path}`",
        "- Method: forward returns after each monthly PIT selection; this is diagnostic, not an executable strategy by itself.",
        "",
        "## Theme Quality",
        "",
        by_theme.to_markdown(index=False),
        "",
        "## Best Theme/Ticker Pairs",
        "",
        by_theme_ticker.sort_values(["fwd_63d_avg", "fwd_126d_avg"], ascending=[False, False]).head(30).to_markdown(index=False),
        "",
        "## Weak Theme/Ticker Pairs",
        "",
        by_theme_ticker[by_theme_ticker["n"] >= 3].sort_values(["fwd_63d_avg", "fwd_126d_avg"], ascending=[True, True]).head(30).to_markdown(index=False),
        "",
        f"- Raw: `{raw_path}`",
        f"- By theme: `{theme_path}`",
        f"- By ticker: `{ticker_path}`",
        f"- By theme/ticker: `{theme_ticker_path}`",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {report_path}")
    print(f"Raw: {raw_path}")


if __name__ == "__main__":
    main()
