#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
SHARED_CACHE_DIR = ROOT / "backtest_results" / "price_cache"
ROUGH_CACHE_DIR = ROOT / "backtest_results" / "v6b_rough_test" / "price_cache"
OUT_DIR = ROOT / "backtest_results" / "v6b_missing_opportunity_review"
DEFAULT_THEME_MAP = ROOT / "v6_strategy_lab" / "configs" / "v6b_missing_opportunity_review_theme_map_v1.json"
DEFAULT_UNIVERSE = ROOT / "v6_strategy_lab" / "configs" / "v6b_point_in_time_universe_seed_20260510.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def plain_ticker(ticker: str) -> str:
    return ticker.replace("US.", "")


def cache_paths_for(ticker: str) -> list[Path]:
    plain = plain_ticker(ticker)
    shared_name = ticker.replace(".", "_")
    return [
        SHARED_CACHE_DIR / f"{shared_name}_daily.csv",
        ROUGH_CACHE_DIR / f"{plain}_daily.csv",
    ]


def read_close_series(ticker: str, start: str, end: str) -> tuple[pd.Series | None, str | None]:
    frames: list[pd.DataFrame] = []
    source: str | None = None
    for path in cache_paths_for(ticker):
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        if "Close" not in df.columns:
            continue
        frames.append(df[["date", "Close"]].copy())
        if source is None:
            source = str(path.relative_to(ROOT))
    if not frames:
        return None, None
    merged = pd.concat(frames, ignore_index=True)
    merged = merged.dropna(subset=["date", "Close"]).sort_values("date")
    merged = merged.drop_duplicates(subset="date", keep="last")
    series = merged.set_index("date")["Close"].sort_index().loc[start:end].dropna()
    if series.empty:
        return None, source
    series.name = ticker
    return series, source


def build_price_matrix(tickers: list[str], start: str, end: str) -> tuple[pd.DataFrame, dict[str, str]]:
    data: dict[str, pd.Series] = {}
    sources: dict[str, str] = {}
    for ticker in tickers:
        series, source = read_close_series(ticker, start, end)
        if series is not None:
            data[ticker] = series
        if source:
            sources[ticker] = source
    prices = pd.DataFrame(data).sort_index()
    prices.index = pd.to_datetime(prices.index)
    return prices.ffill(limit=3), sources


def pct_change(series: pd.Series, window: int) -> float | None:
    if len(series) <= window:
        return None
    base = float(series.iloc[-window - 1])
    if base == 0:
        return None
    return float(series.iloc[-1] / base - 1.0)


def scale_metric(value: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    clipped = max(low, min(high, value))
    return round((clipped - low) / (high - low) * 100.0, 2)


def active_universe_map(universe: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for entry in universe.get("entries", []):
        ticker = str(entry.get("ticker") or "")
        if ticker and entry.get("status") == "active_research":
            rows[ticker] = entry
    return rows


def compute_metrics(
    prices: pd.DataFrame,
    ticker: str,
    as_of: pd.Timestamp,
    theme_benchmark: str,
    market_benchmark: str,
    *,
    min_history_days: int,
) -> dict[str, Any]:
    subset = prices.loc[:as_of]
    history = subset[ticker].dropna() if ticker in subset.columns else pd.Series(dtype=float)
    if len(history) < min_history_days:
        return {"eligible": False, "blocked_reason": "insufficient_history", "history_days": int(len(history))}

    last_date = pd.Timestamp(history.index.max())
    close = float(history.iloc[-1])
    ma50 = float(history.tail(50).mean()) if len(history) >= 50 else float(history.mean())
    ma200 = float(history.tail(200).mean()) if len(history) >= 200 else float(history.mean())
    high63 = float(history.tail(63).max()) if len(history) >= 63 else float(history.max())
    high252 = float(history.tail(252).max()) if len(history) >= 252 else float(history.max())

    market_hist = subset[market_benchmark].dropna()
    theme_hist = subset[theme_benchmark].dropna()

    mom20 = pct_change(history, 20)
    mom60 = pct_change(history, 60)
    mom120 = pct_change(history, 120)
    market60 = pct_change(market_hist, 60) if not market_hist.empty else None
    theme60 = pct_change(theme_hist, 60) if not theme_hist.empty else None

    if None in {mom20, mom60, mom120, market60, theme60}:
        return {"eligible": False, "blocked_reason": "insufficient_benchmark_window", "history_days": int(len(history))}

    metrics = {
        "eligible": True,
        "history_days": int(len(history)),
        "last_price_date": last_date.strftime("%Y-%m-%d"),
        "stale_days": int((as_of.normalize() - last_date.normalize()).days),
        "close": close,
        "ma50": ma50,
        "ma200": ma200,
        "above_ma50": close > ma50,
        "above_ma200": close > ma200,
        "trend_gap": close / ma200 - 1.0 if ma200 > 0 else 0.0,
        "drawdown_from_high63": close / high63 - 1.0 if high63 > 0 else 0.0,
        "drawdown_from_high252": close / high252 - 1.0 if high252 > 0 else 0.0,
        "mom20": mom20,
        "mom60": mom60,
        "mom120": mom120,
        "rel60_vs_market": mom60 - market60,
        "rel60_vs_theme_benchmark": mom60 - theme60,
    }
    return metrics


def score_metrics(metrics: dict[str, Any]) -> float:
    score = 0.0
    score += scale_metric(float(metrics["mom20"]), -0.15, 0.30) * 0.20
    score += scale_metric(float(metrics["mom60"]), -0.20, 0.60) * 0.30
    score += scale_metric(float(metrics["mom120"]), -0.30, 1.00) * 0.15
    score += scale_metric(float(metrics["rel60_vs_theme_benchmark"]), -0.20, 0.40) * 0.20
    score += scale_metric(float(metrics["trend_gap"]), -0.20, 0.50) * 0.10
    score += scale_metric(float(metrics["drawdown_from_high63"]), -0.35, 0.00) * 0.05
    final = round(score, 2)
    if not metrics.get("above_ma200", False):
        final = min(final, 55.0)
    if metrics.get("stale_days", 0) > 7:
        final = max(0.0, round(final - min(metrics["stale_days"], 30) * 0.8, 2))
    return final


def classify_action(*, active: bool, score: float) -> str:
    if active and score < 55:
        return "review_active_name"
    if active:
        return "already_covered"
    if score >= 80:
        return "urgent_seed_review"
    if score >= 70:
        return "seed_review"
    if score >= 60:
        return "watchlist_review"
    return "no_change"


def render_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.1f}%"


def render_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[str]:
    if not rows:
        return ["_None_"]
    header = "| " + " | ".join(label for _, label in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        values = [str(row.get(key, "")) for key, _ in columns]
        body.append("| " + " | ".join(values) + " |")
    return [header, sep, *body]


def build_review(
    theme_map: dict[str, Any],
    universe: dict[str, Any],
    prices: pd.DataFrame,
    sources: dict[str, str],
    as_of: pd.Timestamp,
    *,
    review_threshold: float,
    critical_threshold: float,
    theme_wakeup_threshold: float,
    min_history_days: int,
) -> dict[str, Any]:
    active_map = active_universe_map(universe)
    active_tickers = set(active_map)
    benchmark_map = theme_map.get("benchmarks", {})
    market_benchmark = str(benchmark_map.get("market") or "US.QQQ")

    theme_summaries: list[dict[str, Any]] = []
    critical_misses: list[dict[str, Any]] = []
    watch_misses: list[dict[str, Any]] = []
    active_weak: list[dict[str, Any]] = []
    coverage_gaps: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []

    for theme in theme_map.get("themes", []):
        theme_id = str(theme["theme_id"])
        label = str(theme["label"])
        theme_benchmark = benchmark_map.get("semi") if theme_id == "ai_supply_chain_diffusion" else benchmark_map.get("industrial")
        if not theme_benchmark:
            theme_benchmark = market_benchmark
        buckets: dict[str, list[str]] = {}
        for bucket in theme.get("buckets", []):
            for ticker in bucket.get("tickers", []):
                buckets.setdefault(str(ticker), []).append(str(bucket["bucket_id"]))
        sentinels = set(str(ticker) for ticker in theme.get("sentinels", []))
        theme_tickers = sorted(set(buckets) | sentinels)

        theme_rows: list[dict[str, Any]] = []
        theme_gaps: list[dict[str, Any]] = []
        for ticker in theme_tickers:
            bucket_ids = buckets.get(ticker, [])
            if ticker not in prices.columns:
                gap = {
                    "theme": label,
                    "theme_id": theme_id,
                    "ticker": ticker,
                    "buckets": ", ".join(bucket_ids) or "sentinel_only",
                    "gap_reason": "no_local_price_cache",
                    "active_in_universe": ticker in active_tickers,
                }
                theme_gaps.append(gap)
                coverage_gaps.append(gap)
                continue

            metrics = compute_metrics(
                prices,
                ticker,
                as_of,
                str(theme_benchmark),
                market_benchmark,
                min_history_days=min_history_days,
            )
            if not metrics.get("eligible"):
                gap = {
                    "theme": label,
                    "theme_id": theme_id,
                    "ticker": ticker,
                    "buckets": ", ".join(bucket_ids) or "sentinel_only",
                    "gap_reason": str(metrics.get("blocked_reason") or "unknown"),
                    "active_in_universe": ticker in active_tickers,
                }
                theme_gaps.append(gap)
                coverage_gaps.append(gap)
                continue

            score = score_metrics(metrics)
            row = {
                "theme": label,
                "theme_id": theme_id,
                "ticker": ticker,
                "buckets": ", ".join(bucket_ids) or "sentinel_only",
                "is_sentinel": ticker in sentinels,
                "active_in_universe": ticker in active_tickers,
                "score": score,
                "action": classify_action(active=ticker in active_tickers, score=score),
                "cache_source": sources.get(ticker, ""),
                **metrics,
            }
            theme_rows.append(row)
            all_rows.append(row)

        theme_rows.sort(key=lambda item: (item["score"], item["mom60"], item["mom20"]), reverse=True)
        sentinel_scores = [row["score"] for row in theme_rows if row["is_sentinel"]]
        sentinel_strength = round(sum(sentinel_scores) / len(sentinel_scores), 2) if sentinel_scores else 0.0
        theme_critical = [row for row in theme_rows if not row["active_in_universe"] and row["score"] >= critical_threshold]
        theme_watch = [row for row in theme_rows if not row["active_in_universe"] and row["score"] >= review_threshold]
        theme_active_weak = [row for row in theme_rows if row["active_in_universe"] and row["score"] < 55]
        active_count = sum(1 for row in theme_rows if row["active_in_universe"])

        if sentinel_strength >= theme_wakeup_threshold and active_count == 0:
            theme_status = "theme_awake_unseeded"
        elif theme_critical:
            theme_status = "missed_leaders_present"
        elif theme_active_weak:
            theme_status = "active_names_need_review"
        else:
            theme_status = "covered_or_cold"

        theme_summaries.append(
            {
                "theme": label,
                "theme_id": theme_id,
                "theme_status": theme_status,
                "sentinel_strength": sentinel_strength,
                "active_count": active_count,
                "critical_miss_count": len(theme_critical),
                "watch_miss_count": len(theme_watch),
                "coverage_gap_count": len(theme_gaps),
                "top_name": theme_rows[0]["ticker"] if theme_rows else "n/a",
                "top_score": theme_rows[0]["score"] if theme_rows else 0.0,
            }
        )
        critical_misses.extend(theme_critical)
        watch_misses.extend(theme_watch)
        active_weak.extend(theme_active_weak)

    critical_misses = sorted(critical_misses, key=lambda row: (row["score"], row["mom60"]), reverse=True)
    watch_misses = sorted(watch_misses, key=lambda row: (row["score"], row["mom60"]), reverse=True)
    active_weak = sorted(active_weak, key=lambda row: (row["score"], row["mom60"]))
    theme_summaries = sorted(theme_summaries, key=lambda row: (row["critical_miss_count"], row["sentinel_strength"]), reverse=True)
    theme_wakeups = [row for row in theme_summaries if row["theme_status"] == "theme_awake_unseeded"]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.strftime("%Y-%m-%d"),
        "review_threshold": review_threshold,
        "critical_threshold": critical_threshold,
        "theme_wakeup_threshold": theme_wakeup_threshold,
        "active_universe_id": universe.get("universe_id"),
        "theme_map_id": theme_map.get("review_id"),
        "summary": {
            "theme_count": len(theme_summaries),
            "active_universe_count": len(active_tickers),
            "review_row_count": len(all_rows),
            "critical_miss_count": len(critical_misses),
            "watch_miss_count": len(watch_misses),
            "active_weak_count": len(active_weak),
            "coverage_gap_count": len(coverage_gaps),
            "theme_wakeup_count": len(theme_wakeups),
            "critical_miss_tickers": [row["ticker"] for row in critical_misses[:8]],
            "theme_wakeups": [row["theme"] for row in theme_wakeups],
        },
        "themes": theme_summaries,
        "critical_misses": critical_misses,
        "watch_misses": watch_misses,
        "active_weak": active_weak,
        "coverage_gaps": coverage_gaps,
    }


def render_md(review: dict[str, Any]) -> str:
    lines = [
        "# V6-B Missing Opportunity Review",
        "",
        f"- Generated: `{review['generated_at']}`",
        f"- As Of: `{review['as_of']}`",
        f"- Active Universe: `{review['active_universe_id']}`",
        f"- Theme Map: `{review['theme_map_id']}`",
        "",
        "## Summary",
        "",
        f"- Themes reviewed: `{review['summary']['theme_count']}`",
        f"- Critical misses: `{review['summary']['critical_miss_count']}`",
        f"- Watch misses: `{review['summary']['watch_miss_count']}`",
        f"- Active-but-weak names: `{review['summary']['active_weak_count']}`",
        f"- Coverage gaps: `{review['summary']['coverage_gap_count']}`",
        f"- Theme wakeups: `{', '.join(review['summary']['theme_wakeups']) if review['summary']['theme_wakeups'] else 'none'}`",
        "",
        "## Theme Status",
        "",
    ]
    lines.extend(
        render_table(
            [
                {
                    "theme": row["theme"],
                    "status": row["theme_status"],
                    "sentinel_strength": f"{row['sentinel_strength']:.1f}",
                    "active_count": row["active_count"],
                    "critical_miss_count": row["critical_miss_count"],
                    "coverage_gap_count": row["coverage_gap_count"],
                    "top_name": f"{row['top_name']} ({row['top_score']:.1f})",
                }
                for row in review["themes"]
            ],
            [
                ("theme", "theme"),
                ("status", "status"),
                ("sentinel_strength", "sentinel_strength"),
                ("active_count", "active_count"),
                ("critical_miss_count", "critical_miss_count"),
                ("coverage_gap_count", "coverage_gap_count"),
                ("top_name", "top_name"),
            ],
        )
    )

    lines.extend(["", "## Critical Misses", ""])
    lines.extend(
        render_table(
            [
                {
                    "theme": row["theme"],
                    "ticker": row["ticker"],
                    "buckets": row["buckets"],
                    "score": f"{row['score']:.1f}",
                    "mom20": render_percent(row["mom20"]),
                    "mom60": render_percent(row["mom60"]),
                    "rel60": render_percent(row["rel60_vs_theme_benchmark"]),
                    "action": row["action"],
                }
                for row in review["critical_misses"][:12]
            ],
            [
                ("theme", "theme"),
                ("ticker", "ticker"),
                ("buckets", "buckets"),
                ("score", "score"),
                ("mom20", "mom20"),
                ("mom60", "mom60"),
                ("rel60", "rel60_vs_theme"),
                ("action", "action"),
            ],
        )
    )

    lines.extend(["", "## Active But Weak", ""])
    lines.extend(
        render_table(
            [
                {
                    "theme": row["theme"],
                    "ticker": row["ticker"],
                    "score": f"{row['score']:.1f}",
                    "mom20": render_percent(row["mom20"]),
                    "mom60": render_percent(row["mom60"]),
                    "stale_days": row["stale_days"],
                    "action": row["action"],
                }
                for row in review["active_weak"][:12]
            ],
            [
                ("theme", "theme"),
                ("ticker", "ticker"),
                ("score", "score"),
                ("mom20", "mom20"),
                ("mom60", "mom60"),
                ("stale_days", "stale_days"),
                ("action", "action"),
            ],
        )
    )

    lines.extend(["", "## Coverage Gaps", ""])
    lines.extend(
        render_table(
            [
                {
                    "theme": row["theme"],
                    "ticker": row["ticker"],
                    "buckets": row["buckets"],
                    "gap_reason": row["gap_reason"],
                    "active_in_universe": "yes" if row["active_in_universe"] else "no",
                }
                for row in review["coverage_gaps"][:20]
            ],
            [
                ("theme", "theme"),
                ("ticker", "ticker"),
                ("buckets", "buckets"),
                ("gap_reason", "gap_reason"),
                ("active_in_universe", "active_in_universe"),
            ],
        )
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Radar Missing Opportunity Review for V6-B.")
    parser.add_argument("--theme-map", default=str(DEFAULT_THEME_MAP))
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--as-of", default="")
    parser.add_argument("--review-threshold", type=float, default=70.0)
    parser.add_argument("--critical-threshold", type=float, default=80.0)
    parser.add_argument("--theme-wakeup-threshold", type=float, default=70.0)
    parser.add_argument("--min-history-days", type=int, default=252)
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    theme_map = load_json(Path(args.theme_map))
    universe = load_json(Path(args.universe))

    tickers: set[str] = set()
    for theme in theme_map.get("themes", []):
        tickers.update(str(ticker) for ticker in theme.get("sentinels", []))
        for bucket in theme.get("buckets", []):
            tickers.update(str(ticker) for ticker in bucket.get("tickers", []))
    benchmark_map = theme_map.get("benchmarks", {})
    tickers.update(str(value) for value in benchmark_map.values())

    prices, sources = build_price_matrix(sorted(tickers), args.start, args.end)
    if prices.empty:
        raise SystemExit("No local price data available for review.")

    market_benchmark = str(benchmark_map.get("market") or "US.QQQ")
    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
    elif market_benchmark in prices.columns:
        as_of = pd.Timestamp(prices[market_benchmark].dropna().index.max())
    else:
        as_of = pd.Timestamp(prices.index.max())

    review = build_review(
        theme_map,
        universe,
        prices,
        sources,
        as_of,
        review_threshold=args.review_threshold,
        critical_threshold=args.critical_threshold,
        theme_wakeup_threshold=args.theme_wakeup_threshold,
        min_history_days=args.min_history_days,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"v6b_missing_opportunity_review_{args.tag}.json"
    md_path = OUT_DIR / f"v6b_missing_opportunity_review_{args.tag}.md"
    latest_json = OUT_DIR / "latest.json"
    latest_md = OUT_DIR / "latest.md"

    payload = json.dumps(review, ensure_ascii=False, indent=2) + "\n"
    markdown = render_md(review)
    json_path.write_text(payload, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")

    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    print(f"As Of: {review['as_of']}")
    print(f"Critical misses: {review['summary']['critical_miss_count']}")
    print(f"Coverage gaps: {review['summary']['coverage_gap_count']}")


if __name__ == "__main__":
    main()
