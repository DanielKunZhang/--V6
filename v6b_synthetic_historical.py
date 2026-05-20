#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).parent
DEFAULT_POLICY_PATH = ROOT / "v6_strategy_lab" / "configs" / "v6b_synthetic_historical_generator_policy_v1.json"
DEFAULT_SEED_PATH = ROOT / "v6_strategy_lab" / "configs" / "v6b_point_in_time_universe_seed_20260510.json"
ROUGH_CACHE_DIR = ROOT / "backtest_results" / "v6b_rough_test" / "price_cache"
SHARED_CACHE_DIR = ROOT / "backtest_results" / "price_cache"

V6A_POOL = ["US.NVDA", "US.AVGO", "US.MSFT", "US.AMZN", "US.META", "US.GOOGL"]
DEFENSIVE = {"US.GLD": 0.45, "US.BIL": 0.35, "CASH": 0.20}
REGIME_TICKERS = ["US.QQQ", "US.SPY"]

SCORE_RANGES = {
    "mom20": (-0.15, 0.30),
    "mom60": (-0.20, 0.60),
    "mom120": (-0.30, 1.00),
    "rel60_vs_qqq": (-0.20, 0.40),
    "rel60_vs_smh": (-0.20, 0.40),
    "rel120_vs_qqq": (-0.30, 0.60),
}


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


def read_close_series(ticker: str, start: str, end: str) -> pd.Series | None:
    frames: list[pd.DataFrame] = []
    for path in cache_paths_for(ticker):
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        if "Close" not in df.columns:
            continue
        frames.append(df[["date", "Close"]].copy())
    if not frames:
        return None
    merged = pd.concat(frames, ignore_index=True)
    merged = merged.dropna(subset=["date", "Close"]).sort_values("date")
    merged = merged.drop_duplicates(subset="date", keep="last")
    series = merged.set_index("date")["Close"].sort_index().loc[start:end].dropna()
    if series.empty:
        return None
    series.name = ticker
    return series


def build_price_matrix(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    data: dict[str, pd.Series] = {}
    for ticker in tickers:
        series = read_close_series(ticker, start, end)
        if series is not None:
            data[ticker] = series
    prices = pd.DataFrame(data).sort_index()
    prices.index = pd.to_datetime(prices.index)
    return prices.ffill(limit=3)


def load_seed_templates(seed_path: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(seed_path)
    rows: dict[str, dict[str, Any]] = {}
    for entry in payload.get("entries", []):
        rows[entry["ticker"]] = entry
    return rows


def month_end_trading_days(index: pd.DatetimeIndex, start: str, end: str) -> list[pd.Timestamp]:
    filtered = pd.Series(index=index[(index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end))], dtype=float)
    if filtered.empty:
        return []
    month_ends = filtered.groupby(filtered.index.to_period("M")).apply(lambda _: _.index.max())
    return [pd.Timestamp(value) for value in month_ends.tolist()]


def scale_metric(name: str, value: float) -> float:
    low, high = SCORE_RANGES[name]
    if high <= low:
        return 50.0
    clipped = max(low, min(high, value))
    return round((clipped - low) / (high - low) * 100.0, 2)


def _pct_change(history: pd.Series, window: int) -> float | None:
    if len(history) <= window:
        return None
    base = float(history.iloc[-window - 1])
    if base == 0:
        return None
    return float(history.iloc[-1] / base - 1.0)


def compute_metrics(
    prices: pd.DataFrame,
    ticker: str,
    as_of: pd.Timestamp,
    policy: dict[str, Any],
    benchmarks: dict[str, str],
) -> dict[str, Any]:
    subset = prices.loc[:as_of]
    history = subset[ticker].dropna() if ticker in subset.columns else pd.Series(dtype=float)
    min_history = int(policy["common"]["min_history_days"])
    if len(history) < min_history:
        return {"eligible": False, "blocked_reason": "insufficient_history", "history_days": int(len(history))}

    close = float(history.iloc[-1])
    trend_ma = int(policy["common"]["trend_ma_days"])
    ma200 = float(history.tail(trend_ma).mean())
    high_lookback = int(policy["common"]["high_lookback_days"])
    high252 = float(history.tail(high_lookback).max())
    if ma200 <= 0 or high252 <= 0:
        return {"eligible": False, "blocked_reason": "invalid_reference_level", "history_days": int(len(history))}

    qqq_hist = subset[benchmarks["market"]].dropna()
    smh_hist = subset[benchmarks["semi"]].dropna()
    mom20 = _pct_change(history, 20)
    mom60 = _pct_change(history, 60)
    mom120 = _pct_change(history, 120)
    qqq60 = _pct_change(qqq_hist, 60) if not qqq_hist.empty else None
    qqq120 = _pct_change(qqq_hist, 120) if not qqq_hist.empty else None
    smh60 = _pct_change(smh_hist, 60) if not smh_hist.empty else None
    if None in {mom20, mom60, mom120, qqq60, qqq120, smh60}:
        return {"eligible": False, "blocked_reason": "insufficient_benchmark_window", "history_days": int(len(history))}

    metrics = {
        "close": close,
        "ma200": ma200,
        "above_ma200": close > ma200,
        "trend_gap": close / ma200 - 1.0,
        "drawdown_from_high": close / high252 - 1.0,
        "mom20": mom20,
        "mom60": mom60,
        "mom120": mom120,
        "rel60_vs_qqq": mom60 - qqq60,
        "rel60_vs_smh": mom60 - smh60,
        "rel120_vs_qqq": mom120 - qqq120,
        "history_days": int(len(history)),
    }
    return {"eligible": True, **metrics}


def passes_filters(metrics: dict[str, Any], filters: dict[str, Any]) -> tuple[bool, str]:
    if not metrics.get("above_ma200", False):
        return False, "below_ma200"
    for field, value in filters.items():
        if field == "min_mom20" and metrics["mom20"] < float(value):
            return False, "mom20_too_weak"
        if field == "min_mom60" and metrics["mom60"] < float(value):
            return False, "mom60_too_weak"
        if field == "min_mom120" and metrics["mom120"] < float(value):
            return False, "mom120_too_weak"
        if field == "min_rel60_vs_qqq" and metrics["rel60_vs_qqq"] < float(value):
            return False, "rel60_vs_qqq_too_weak"
        if field == "min_rel60_vs_smh" and metrics["rel60_vs_smh"] < float(value):
            return False, "rel60_vs_smh_too_weak"
        if field == "max_drawdown_from_high" and metrics["drawdown_from_high"] < float(value):
            return False, "too_far_from_high"
    return True, ""


def score_candidate(metrics: dict[str, Any], weights: dict[str, float]) -> float:
    total_weight = 0.0
    weighted = 0.0
    for name, weight in weights.items():
        if name not in metrics:
            continue
        weighted += scale_metric(name, float(metrics[name])) * float(weight)
        total_weight += float(weight)
    return round(weighted / total_weight, 2) if total_weight else 0.0


def build_reason(template: dict[str, Any], track: str, ticker: str, as_of: pd.Timestamp, score: float, metrics: dict[str, Any]) -> str:
    thesis = template.get("reason") if template else f"Synthetic {track} candidate."
    return (
        f"{thesis} Synthetic snapshot as of {as_of.date()}: "
        f"score {score:.2f}, 60d {metrics['mom60'] * 100:.1f}%, "
        f"120d {metrics['mom120'] * 100:.1f}%, "
        f"rel60 vs QQQ {metrics['rel60_vs_qqq'] * 100:.1f}%, "
        f"above MA200 {metrics['trend_gap'] * 100:.1f}%."
    )


def build_entry(
    template: dict[str, Any] | None,
    ticker: str,
    track: str,
    as_of: pd.Timestamp,
    score: float,
    rank: int,
    metrics: dict[str, Any],
    policy_id: str,
) -> dict[str, Any]:
    anti_thesis = ""
    source = f"{policy_id} as_of {as_of.date()}"
    if template:
        anti_thesis = template.get("anti_thesis", "")
        source = template.get("source", source)
    return {
        "ticker": ticker,
        "entry_date": as_of.strftime("%Y-%m-%d"),
        "exit_date": None,
        "track": track,
        "source": source,
        "reason": build_reason(template or {}, track, ticker, as_of, score, metrics),
        "anti_thesis": anti_thesis or "Price / momentum confirmation breaks and the track-level thesis stops validating.",
        "status": "active_research",
        "synthetic_meta": {
            "generator_policy": policy_id,
            "synthetic_rank": rank,
            "synthetic_score": score,
            "metrics": {key: round(float(value), 6) for key, value in metrics.items() if isinstance(value, (int, float))},
        },
    }


def build_snapshot(
    prices: pd.DataFrame,
    policy: dict[str, Any],
    templates: dict[str, dict[str, Any]],
    as_of: pd.Timestamp,
) -> dict[str, Any]:
    benchmarks = policy["benchmarks"]
    track_rows: dict[str, Any] = {}
    entries: list[dict[str, Any]] = []
    for track, track_policy in policy["tracks"].items():
        candidates = []
        blocked = []
        for ticker in track_policy["members"]:
            metrics = compute_metrics(prices, ticker, as_of, policy, benchmarks)
            if not metrics.get("eligible"):
                blocked.append({"ticker": ticker, "reason": metrics.get("blocked_reason", "unknown")})
                continue
            ok, blocked_reason = passes_filters(metrics, track_policy["filters"])
            if not ok:
                blocked.append({"ticker": ticker, "reason": blocked_reason})
                continue
            score = score_candidate(metrics, track_policy["score_weights"])
            candidates.append({"ticker": ticker, "score": score, "metrics": metrics})
        candidates.sort(key=lambda row: (row["score"], row["metrics"]["mom60"], row["metrics"]["mom120"]), reverse=True)
        selected = candidates[: int(track_policy["max_names"])]
        track_rows[track] = {
            "selected": [row["ticker"] for row in selected],
            "candidate_count": len(candidates),
            "blocked": blocked,
        }
        for rank, row in enumerate(selected, start=1):
            template = templates.get(row["ticker"])
            entries.append(
                build_entry(
                    template=template,
                    ticker=row["ticker"],
                    track=track,
                    as_of=as_of,
                    score=row["score"],
                    rank=rank,
                    metrics=row["metrics"],
                    policy_id=policy["policy_id"],
                )
            )

    qqq = prices.loc[as_of, policy["benchmarks"]["market"]]
    spy = prices.loc[as_of, policy["benchmarks"]["broad"]]
    qqq_ma = prices.loc[:as_of, policy["benchmarks"]["market"]].dropna().tail(int(policy["common"]["trend_ma_days"])).mean()
    spy_ma = prices.loc[:as_of, policy["benchmarks"]["broad"]].dropna().tail(int(policy["common"]["trend_ma_days"])).mean()
    return {
        "version": as_of.strftime("%Y-%m-%d"),
        "universe_id": f"V6B_SYNTHETIC_RADAR_{as_of.strftime('%Y%m%d')}",
        "status": "research_synthetic_historical",
        "description": "Synthetic historical Radar snapshot generated from contemporaneous price signals only. Research-only.",
        "rules": {
            "no_lookahead": True,
            "generator_policy": policy["policy_id"],
            "selection_frequency": policy["selection_frequency"],
            "price_only_generator": True,
            "not_for_live_trading": True,
        },
        "market_regime": {
            "qqq_above_ma200": bool(qqq > qqq_ma) if pd.notna(qqq) and pd.notna(qqq_ma) else False,
            "spy_above_ma200": bool(spy > spy_ma) if pd.notna(spy) and pd.notna(spy_ma) else False,
        },
        "track_summary": track_rows,
        "entries": entries,
    }


def write_snapshot_series(
    snapshots: list[dict[str, Any]],
    out_dir: Path,
    policy: dict[str, Any],
    coverage: list[dict[str, Any]],
) -> tuple[Path, Path]:
    snapshot_dir = out_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    selection_rows: dict[str, dict[str, Any]] = {}

    for snapshot in snapshots:
        as_of = snapshot["version"]
        path = snapshot_dir / f"{as_of}_v6b_universe.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        track_counts = {track: len(info["selected"]) for track, info in snapshot["track_summary"].items()}
        manifest_rows.append(
            {
                "as_of": as_of,
                "path": str(path.as_posix()),
                "entry_count": len(snapshot["entries"]),
                "track_counts": track_counts,
                "selected": {track: info["selected"] for track, info in snapshot["track_summary"].items()},
            }
        )
        for entry in snapshot["entries"]:
            row = selection_rows.setdefault(
                entry["ticker"],
                {"ticker": entry["ticker"], "track": entry["track"], "first_selected": as_of, "last_selected": as_of, "selected_months": 0},
            )
            row["selected_months"] += 1
            row["last_selected"] = as_of

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy_id": policy["policy_id"],
        "snapshot_count": len(snapshots),
        "coverage": coverage,
        "snapshots": manifest_rows,
        "selection_summary": sorted(selection_rows.values(), key=lambda row: (row["track"], row["ticker"])),
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# V6-B Synthetic Historical Radar Generator",
        "",
        f"- Generated: `{manifest['generated_at']}`",
        f"- Policy: `{policy['policy_id']}`",
        f"- Snapshots: `{len(snapshots)}` monthly point-in-time universes",
        "- Boundary: price-only synthetic reconstruction; useful for no-lookahead research, not a final live approval.",
        "",
        "## Data Coverage",
        "",
        "| ticker | first_date | last_date | bars |",
        "| --- | --- | --- | ---: |",
    ]
    for row in coverage:
        lines.append(f"| `{row['ticker']}` | `{row['first_date']}` | `{row['last_date']}` | {row['bars']} |")
    lines.extend(
        [
            "",
            "## Selection Summary",
            "",
            "| ticker | track | first_selected | last_selected | selected_months |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    for row in manifest["selection_summary"]:
        lines.append(
            f"| `{row['ticker']}` | `{row['track']}` | `{row['first_selected']}` | `{row['last_selected']}` | {row['selected_months']} |"
        )
    sample_tracks = list(policy.get("tracks", {}).keys())
    lines.extend(["", "## Sample Snapshots", ""])
    lines.append("| as_of | entries | " + " | ".join(sample_tracks) + " |")
    lines.append("| --- | ---: | " + " | ".join(["---"] * len(sample_tracks)) + " |")
    sample_rows = manifest_rows[:2] + manifest_rows[-3:] if len(manifest_rows) > 5 else manifest_rows
    seen = set()
    for row in sample_rows:
        if row["as_of"] in seen:
            continue
        seen.add(row["as_of"])
        selected_cells = [f"`{', '.join(row['selected'].get(track, []))}`" for track in sample_tracks]
        lines.append(f"| `{row['as_of']}` | {row['entry_count']} | " + " | ".join(selected_cells) + " |")
    report_path = out_dir / "summary.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest_path, report_path
