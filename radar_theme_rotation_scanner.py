#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
DESKTOP_DIR = Path("/Users/zhangkun/Desktop/AI个人投资公司")
PRICE_CACHE_DIR = ROOT / "backtest_results" / "price_cache"
ROUGH_CACHE_DIR = ROOT / "backtest_results" / "v6b_rough_test" / "price_cache"
OUT_DIR = ROOT / "backtest_results" / "radar_theme_rotation_scanner"
DEFAULT_CONFIG = ROOT / "v6_strategy_lab" / "configs" / "radar_theme_rotation_universe_v1.json"
JOURNAL_PATH = OUT_DIR / "scan_journal.json"
EXTERNAL_REGISTRY = ROOT / "v6_strategy_lab" / "configs" / "v6b_candidate_registry_v1.json"


LAYER_ORDER = [
    "leader_layer",
    "first_order_beneficiaries",
    "second_order_infrastructure",
    "third_order_high_beta",
]

LAYER_LABELS = {
    "leader_layer": "龙头层",
    "first_order_beneficiaries": "一阶受益",
    "second_order_infrastructure": "二阶扩散",
    "third_order_high_beta": "三阶高弹性",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_or_empty(path: Path) -> Any:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def normalize_ticker(ticker: str) -> str:
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        return ""
    if "." not in ticker:
        return f"US.{ticker}"
    return ticker


def load_external_sample_tickers(path: Path = EXTERNAL_REGISTRY) -> set[str]:
    payload = read_json_or_empty(path)
    if not isinstance(payload, dict):
        return set()
    markers = ["external", "short-term network", "friend", "trader", "外部", "朋友", "短线"]
    out: set[str] = set()
    for entry in payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        if bool(entry.get("external_sample")):
            ticker = normalize_ticker(str(entry.get("ticker") or ""))
            if ticker:
                out.add(ticker)
            continue
        source = str(entry.get("source") or "").lower()
        reason = str(entry.get("reason") or "").lower()
        if any(marker in source or marker in reason for marker in markers):
            ticker = normalize_ticker(str(entry.get("ticker") or ""))
            if ticker:
                out.add(ticker)
    return out


def cache_candidates(ticker: str) -> list[Path]:
    normalized = ticker.replace(".", "_")
    plain = ticker.replace("US.", "").replace(".", "_")
    return [
        PRICE_CACHE_DIR / f"{normalized}_daily.csv",
        ROUGH_CACHE_DIR / f"{plain}_daily.csv",
    ]


def read_price(ticker: str, start: str, end: str) -> tuple[pd.Series | None, pd.Series | None, str]:
    frames = []
    source = ""
    for path in cache_candidates(ticker):
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        if "Close" not in df.columns:
            continue
        cols = ["date", "Close"]
        if "Volume" in df.columns:
            cols.append("Volume")
        frame = df[cols].copy()
        frames.append(frame)
        if not source:
            source = str(path.relative_to(ROOT))
    if not frames:
        return None, None, ""
    merged = pd.concat(frames, ignore_index=True).dropna(subset=["date", "Close"])
    merged = merged.sort_values("date").drop_duplicates(subset="date", keep="last")
    merged = merged[(merged["date"] >= pd.Timestamp(start)) & (merged["date"] <= pd.Timestamp(end))]
    if merged.empty:
        return None, None, source
    close = merged.set_index("date")["Close"].astype(float).sort_index()
    volume = None
    if "Volume" in merged.columns:
        volume = merged.set_index("date")["Volume"].astype(float).sort_index().dropna()
    return close, volume, source


def pct_change(series: pd.Series, window: int) -> float | None:
    if len(series) <= window:
        return None
    base = float(series.iloc[-window - 1])
    if base <= 0:
        return None
    return float(series.iloc[-1] / base - 1.0)


def safe_mean(values: list[float]) -> float | None:
    values = [float(v) for v in values if v is not None]
    if not values:
        return None
    return float(sum(values) / len(values))


def scale(value: float | None, low: float, high: float) -> float:
    if value is None:
        return 0.0
    clipped = max(low, min(high, value))
    return (clipped - low) / (high - low) * 100.0


def compute_ticker_metrics(
    ticker: str,
    close: pd.Series,
    volume: pd.Series | None,
    benchmark: pd.Series,
    as_of: pd.Timestamp,
) -> dict[str, Any]:
    history = close.loc[:as_of].dropna()
    bench = benchmark.loc[:as_of].dropna()
    if len(history) < 80 or len(bench) < 80:
        return {"ticker": ticker, "eligible": False, "reason": "insufficient_history", "history_days": int(len(history))}

    last_date = pd.Timestamp(history.index.max())
    close_px = float(history.iloc[-1])
    ma50 = float(history.tail(50).mean())
    ma200 = float(history.tail(200).mean()) if len(history) >= 200 else float(history.mean())
    high63 = float(history.tail(63).max())
    high252 = float(history.tail(252).max()) if len(history) >= 252 else float(history.max())

    mom20 = pct_change(history, 20)
    mom60 = pct_change(history, 60)
    mom120 = pct_change(history, 120)
    bench20 = pct_change(bench, 20)
    bench60 = pct_change(bench, 60)
    bench120 = pct_change(bench, 120)
    rel20 = mom20 - bench20 if mom20 is not None and bench20 is not None else None
    rel60 = mom60 - bench60 if mom60 is not None and bench60 is not None else None
    rel120 = mom120 - bench120 if mom120 is not None and bench120 is not None else None

    vol_ratio = None
    if volume is not None and len(volume.loc[:as_of].dropna()) >= 40:
        vol_hist = volume.loc[:as_of].dropna()
        recent = float(vol_hist.tail(20).mean())
        base = float(vol_hist.tail(60).head(40).mean())
        if base > 0:
            vol_ratio = recent / base

    trend_gap = close_px / ma200 - 1.0 if ma200 > 0 else None
    drawdown63 = close_px / high63 - 1.0 if high63 > 0 else None
    drawdown252 = close_px / high252 - 1.0 if high252 > 0 else None

    score = (
        scale(mom20, -0.10, 0.25) * 0.18
        + scale(mom60, -0.20, 0.55) * 0.24
        + scale(mom120, -0.25, 0.80) * 0.14
        + scale(rel60, -0.15, 0.35) * 0.20
        + scale(trend_gap, -0.20, 0.45) * 0.12
        + scale(drawdown63, -0.30, 0.00) * 0.07
        + scale((vol_ratio or 1.0) - 1.0, -0.30, 0.80) * 0.05
    )
    if close_px < ma200:
        score = min(score, 55.0)
    if (as_of.normalize() - last_date.normalize()).days > 7:
        score = max(0.0, score - 10.0)

    return {
        "ticker": ticker,
        "eligible": True,
        "last_price_date": last_date.strftime("%Y-%m-%d"),
        "history_days": int(len(history)),
        "close": round(close_px, 4),
        "mom20": mom20,
        "mom60": mom60,
        "mom120": mom120,
        "rel20_vs_spy": rel20,
        "rel60_vs_spy": rel60,
        "rel120_vs_spy": rel120,
        "above_ma50": close_px > ma50,
        "above_ma200": close_px > ma200,
        "trend_gap": trend_gap,
        "drawdown63": drawdown63,
        "drawdown252": drawdown252,
        "volume_ratio_20v40": vol_ratio,
        "score": round(score, 2),
    }


def classify_trade_posture(row: dict[str, Any]) -> dict[str, str]:
    """把动量候选转成交易可处理口径，避免把追高当成买点。"""
    mom20 = row.get("mom20")
    mom60 = row.get("mom60")
    drawdown63 = row.get("drawdown63")
    above_ma50 = bool(row.get("above_ma50"))
    above_ma200 = bool(row.get("above_ma200"))
    score = float(row.get("score") or 0.0)

    if not above_ma50 or not above_ma200:
        return {
            "trade_posture": "观察，不追",
            "chase_risk": "中",
            "entry_note": "趋势未完全确认，只能等重新站稳或系统信号。",
        }
    if mom20 is not None and mom60 is not None and drawdown63 is not None:
        if mom20 >= 0.25 and mom60 >= 0.45 and drawdown63 >= -0.05:
            return {
                "trade_posture": "禁止直接追高",
                "chase_risk": "高",
                "entry_note": "短中期已经大幅兑现且接近阶段高位，只能等回撤、盘整或小额期权彩票规则。",
            }
        if mom20 >= 0.15 and mom60 >= 0.30 and drawdown63 >= -0.08:
            return {
                "trade_posture": "只允许小仓试错",
                "chase_risk": "中高",
                "entry_note": "趋势强但已不便宜，正股/期权都要用预设亏损上限。",
            }
    if score >= 70:
        return {
            "trade_posture": "可进入正式复核",
            "chase_risk": "中",
            "entry_note": "先做主线、催化、估值和仓位约束复核，再决定是否表达。",
        }
    return {
        "trade_posture": "观察",
        "chase_risk": "低到中",
        "entry_note": "强度未到直接表达阈值，继续等待确认。",
    }


def attach_trade_posture(row: dict[str, Any], source_channel: str) -> dict[str, Any]:
    enriched = dict(row)
    enriched["source_channel"] = source_channel
    enriched.update(classify_trade_posture(enriched))
    return enriched


def external_samples_from_metrics(
    ticker_metrics: dict[str, dict[str, Any]],
    themes: list[dict[str, Any]],
    external_tickers: set[str],
) -> list[dict[str, Any]]:
    samples = []
    for theme in themes:
        for layer in LAYER_ORDER:
            for ticker in theme.get(layer, []):
                if ticker not in external_tickers:
                    continue
                metric = dict(ticker_metrics.get(ticker, {"ticker": ticker, "eligible": False, "reason": "missing_cache"}))
                metric["theme_id"] = theme["theme_id"]
                metric["theme_label"] = theme["label"]
                metric["layer"] = layer
                metric["layer_label"] = LAYER_LABELS[layer]
                samples.append(attach_trade_posture(metric, "external_sample_review"))
    return sorted(samples, key=lambda row: (row.get("eligible", False), row.get("score", 0.0)), reverse=True)


def layer_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row.get("eligible")]
    if not eligible:
        return {"count": 0, "avg_score": 0.0, "avg_mom60": None, "avg_rel60": None, "strong_count": 0}
    return {
        "count": len(eligible),
        "avg_score": round(safe_mean([row["score"] for row in eligible]) or 0.0, 2),
        "avg_mom60": safe_mean([row.get("mom60") for row in eligible]),
        "avg_rel60": safe_mean([row.get("rel60_vs_spy") for row in eligible]),
        "strong_count": sum(1 for row in eligible if row.get("score", 0.0) >= 70),
    }


def classify_stage(layer_summaries: dict[str, dict[str, Any]], theme_score: float) -> str:
    leader = layer_summaries.get("leader_layer", {})
    first = layer_summaries.get("first_order_beneficiaries", {})
    second = layer_summaries.get("second_order_infrastructure", {})
    third = layer_summaries.get("third_order_high_beta", {})

    if theme_score < 45:
        return "退潮或冷却"
    if leader.get("avg_score", 0) >= 70 and max(first.get("avg_score", 0), second.get("avg_score", 0)) < 60:
        return "龙头重估"
    if max(first.get("avg_score", 0), second.get("avg_score", 0)) >= 65:
        return "二阶扩散"
    if third.get("avg_score", 0) >= 65:
        return "三阶补涨/高弹性阶段"
    if theme_score >= 60:
        return "主线确认"
    return "观察"


def build_scan(config: dict[str, Any], start: str, end: str, as_of_arg: str, exclude_tickers: set[str] | None = None) -> dict[str, Any]:
    exclude_tickers = exclude_tickers or set()
    tickers = set(config.get("market_benchmarks", []))
    for theme in config.get("themes", []):
        for key in ["benchmarks", *LAYER_ORDER]:
            tickers.update(str(ticker) for ticker in theme.get(key, []))

    close_map: dict[str, pd.Series] = {}
    volume_map: dict[str, pd.Series | None] = {}
    sources: dict[str, str] = {}
    missing: list[str] = []
    for ticker in sorted(tickers):
        close, volume, source = read_price(ticker, start, end)
        if close is None:
            missing.append(ticker)
            continue
        close_map[ticker] = close
        volume_map[ticker] = volume
        sources[ticker] = source

    if "US.SPY" not in close_map:
        raise SystemExit("US.SPY is required as market benchmark in local price cache.")
    as_of = pd.Timestamp(as_of_arg) if as_of_arg else pd.Timestamp(close_map["US.SPY"].index.max())
    benchmark = close_map["US.SPY"]

    ticker_metrics: dict[str, dict[str, Any]] = {}
    for ticker, close in close_map.items():
        ticker_metrics[ticker] = compute_ticker_metrics(ticker, close, volume_map.get(ticker), benchmark, as_of)

    theme_rows = []
    candidate_rows = []
    for theme in config.get("themes", []):
        layer_rows: dict[str, list[dict[str, Any]]] = {}
        layer_summaries: dict[str, dict[str, Any]] = {}
        all_theme_metrics = []

        for layer in LAYER_ORDER:
            rows = []
            for ticker in theme.get(layer, []):
                if ticker in exclude_tickers:
                    continue
                metric = dict(ticker_metrics.get(ticker, {"ticker": ticker, "eligible": False, "reason": "missing_cache"}))
                metric["layer"] = layer
                metric["layer_label"] = LAYER_LABELS[layer]
                rows.append(metric)
                if metric.get("eligible"):
                    all_theme_metrics.append(metric)
                    if metric.get("score", 0.0) >= 60:
                        candidate_rows.append(
                            attach_trade_posture(
                                {
                                "theme_id": theme["theme_id"],
                                "theme_label": theme["label"],
                                "layer": layer,
                                "layer_label": LAYER_LABELS[layer],
                                **metric,
                                },
                                "independent_discovery",
                            )
                        )
            layer_rows[layer] = rows
            layer_summaries[layer] = layer_summary(rows)

        benchmark_rows = [ticker_metrics[ticker] for ticker in theme.get("benchmarks", []) if ticker in ticker_metrics and ticker_metrics[ticker].get("eligible")]
        benchmark_score = safe_mean([row["score"] for row in benchmark_rows]) or 0.0
        member_score = safe_mean([row["score"] for row in all_theme_metrics]) or 0.0
        leader_score = layer_summaries.get("leader_layer", {}).get("avg_score", 0.0)
        diffusion_score = max(
            layer_summaries.get("first_order_beneficiaries", {}).get("avg_score", 0.0),
            layer_summaries.get("second_order_infrastructure", {}).get("avg_score", 0.0),
            layer_summaries.get("third_order_high_beta", {}).get("avg_score", 0.0),
        )
        theme_score = round(benchmark_score * 0.35 + member_score * 0.35 + leader_score * 0.15 + diffusion_score * 0.15, 2)
        stage = classify_stage(layer_summaries, theme_score)
        top_candidates = sorted(
            [row for row in candidate_rows if row["theme_id"] == theme["theme_id"]],
            key=lambda row: (row.get("score", 0.0), row.get("rel60_vs_spy") or -9),
            reverse=True,
        )[:8]

        theme_rows.append(
            {
                "theme_id": theme["theme_id"],
                "theme_label": theme["label"],
                "theme_score": theme_score,
                "stage": stage,
                "benchmark_score": round(benchmark_score, 2),
                "member_score": round(member_score, 2),
                "leader_score": round(leader_score, 2),
                "diffusion_score": round(diffusion_score, 2),
                "layer_summaries": layer_summaries,
                "top_candidates": [
                    {
                        "ticker": row["ticker"],
                        "layer": row["layer_label"],
                        "score": row["score"],
                        "mom20": row.get("mom20"),
                        "mom60": row.get("mom60"),
                        "rel60_vs_spy": row.get("rel60_vs_spy"),
                    }
                    for row in top_candidates
                ],
            }
        )

    theme_rows = sorted(theme_rows, key=lambda row: row["theme_score"], reverse=True)
    candidate_rows = sorted(candidate_rows, key=lambda row: (row.get("score", 0.0), row.get("rel60_vs_spy") or -9), reverse=True)
    external_sample_rows = external_samples_from_metrics(ticker_metrics, config.get("themes", []), exclude_tickers)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.strftime("%Y-%m-%d"),
        "config_id": config.get("universe_id"),
        "summary": {
            "theme_count": len(theme_rows),
            "candidate_count": len(candidate_rows),
            "missing_cache_count": len(missing),
            "missing_cache": sorted(missing),
            "top_theme": theme_rows[0]["theme_label"] if theme_rows else "n/a",
            "top_theme_stage": theme_rows[0]["stage"] if theme_rows else "n/a",
            "excluded_tickers": sorted(exclude_tickers),
            "excluded_count": len(exclude_tickers),
            "external_sample_review_count": len(external_sample_rows),
        },
        "themes": theme_rows,
        "candidates": candidate_rows[:30],
        "external_sample_review": external_sample_rows,
        "sources": sources,
    }


def forward_return(ticker: str, as_of: str, horizon_days: int, end: str) -> float | None:
    close, _, _ = read_price(ticker, "2000-01-01", end)
    if close is None or close.empty:
        return None
    series = close.sort_index()
    base_candidates = series.loc[:pd.Timestamp(as_of)]
    if base_candidates.empty:
        return None
    base_date = base_candidates.index.max()
    future = series.loc[base_date:]
    if len(future) <= horizon_days:
        return None
    base = float(future.iloc[0])
    target = float(future.iloc[horizon_days])
    if base <= 0:
        return None
    return float(target / base - 1.0)


def update_journal(scan: dict[str, Any], end: str) -> dict[str, Any]:
    existing = read_json_or_empty(JOURNAL_PATH)
    journal = existing if isinstance(existing, list) else []
    as_of = str(scan["as_of"])
    mode = str(scan.get("mode") or "full_universe_scan")

    journal = [entry for entry in journal if not (entry.get("as_of") == as_of and entry.get("mode", "full_universe_scan") == mode)]
    entry = {
        "generated_at": scan["generated_at"],
        "as_of": as_of,
        "mode": mode,
        "excluded_tickers": scan.get("summary", {}).get("excluded_tickers", []),
        "top_themes": [
            {
                "theme_label": row["theme_label"],
                "theme_score": row["theme_score"],
                "stage": row["stage"],
            }
            for row in scan["themes"][:5]
        ],
        "candidates": [
            {
                "ticker": row["ticker"],
                "theme_label": row["theme_label"],
                "layer_label": row["layer_label"],
                "score": row["score"],
                "mom20": row.get("mom20"),
                "mom60": row.get("mom60"),
                "rel60_vs_spy": row.get("rel60_vs_spy"),
            }
            for row in scan["candidates"][:20]
        ],
    }
    journal.append(entry)
    journal = sorted(journal, key=lambda row: row.get("as_of", ""))[-120:]

    for saved in journal:
        saved_as_of = str(saved.get("as_of") or "")
        for row in saved.get("candidates", []):
            ticker = str(row.get("ticker") or "")
            row["fwd_5d"] = forward_return(ticker, saved_as_of, 5, end)
            row["fwd_10d"] = forward_return(ticker, saved_as_of, 10, end)
            row["fwd_20d"] = forward_return(ticker, saved_as_of, 20, end)

    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL_PATH.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    evaluated = []
    for saved in journal:
        for row in saved.get("candidates", []):
            if row.get("fwd_20d") is not None:
                evaluated.append(row)
    hit_rate_20d = None
    avg_20d = None
    if evaluated:
        avg_20d = sum(float(row["fwd_20d"]) for row in evaluated) / len(evaluated)
        hit_rate_20d = sum(1 for row in evaluated if float(row["fwd_20d"]) > 0) / len(evaluated)

    return {
        "journal_path": str(JOURNAL_PATH.relative_to(ROOT)),
        "snapshot_count": len(journal),
        "evaluated_20d_count": len(evaluated),
        "avg_fwd_20d": avg_20d,
        "hit_rate_20d": hit_rate_20d,
    }


def pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.1f}%"


def render_md(scan: dict[str, Any]) -> str:
    journal = scan.get("journal", {})
    lines = [
        "# Radar 主线扩散自动扫描",
        "",
        f"- 生成时间：`{scan['generated_at']}`",
        f"- As Of：`{scan['as_of']}`",
        f"- Config：`{scan['config_id']}`",
        f"- 扫描模式：`{scan.get('mode', 'full_universe_scan')}`",
        f"- 当前最高主线：`{scan['summary']['top_theme']}`",
        f"- 主线阶段：`{scan['summary']['top_theme_stage']}`",
        f"- 缺失价格缓存：`{scan['summary']['missing_cache_count']}`",
        f"- 排除外部样本：`{scan['summary'].get('excluded_count', 0)}`",
        f"- 历史扫描快照：`{journal.get('snapshot_count', 0)}`",
        f"- 已可评估20日样本：`{journal.get('evaluated_20d_count', 0)}`",
        "",
        "## 主线排名",
        "",
        "| 排名 | 主线 | 分数 | 阶段 | 龙头 | 扩散 | 候选 |",
        "| --- | --- | ---: | --- | ---: | ---: | --- |",
    ]
    for idx, row in enumerate(scan["themes"], start=1):
        candidates = ", ".join(f"{item['ticker']}({item['score']:.0f})" for item in row["top_candidates"][:4]) or "无"
        lines.append(
            f"| {idx} | {row['theme_label']} | {row['theme_score']:.1f} | {row['stage']} | "
            f"{row['leader_score']:.1f} | {row['diffusion_score']:.1f} | {candidates} |"
        )

    lines.extend(["", "## 高分候选", ""])
    lines.extend(
        [
            "| 标的 | 主线 | 层级 | 分数 | 20日 | 60日 | 相对SPY 60日 | 趋势 |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in scan["candidates"][:20]:
        trend = "MA50/200上方" if row.get("above_ma50") and row.get("above_ma200") else "趋势未完全确认"
        lines.append(
            f"| `{row['ticker']}` | {row['theme_label']} | {row['layer_label']} | {row['score']:.1f} | "
            f"{pct(row.get('mom20'))} | {pct(row.get('mom60'))} | {pct(row.get('rel60_vs_spy'))} | {trend} |"
        )

    lines.extend(
        [
            "",
            "## 追高处理口径",
            "",
            "| 标的 | 来源 | 追高风险 | 处理 | 说明 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    posture_rows = scan["candidates"][:12] + scan.get("external_sample_review", [])[:8]
    if not posture_rows:
        lines.append("| 无 | - | - | - | - |")
    for row in posture_rows:
        lines.append(
            f"| `{row['ticker']}` | {row.get('source_channel', 'independent_discovery')} | "
            f"{row.get('chase_risk', 'n/a')} | {row.get('trade_posture', 'n/a')} | {row.get('entry_note', '')} |"
        )

    if scan.get("external_sample_review"):
        lines.extend(
            [
                "",
                "## 外部样本只做归因",
                "",
                "- 下列标的来自朋友、交易群或外部短线网络，只能用于学习主线扩散和追高风险，不能被标记为 Radar 独立发现。",
                "- 若要成为正式买入候选，必须在后续独立扫描或 Missing Opportunity Review 中再次通过。",
                "",
                "| 标的 | 主线 | 层级 | 分数 | 20日 | 60日 | 追高风险 | 处理 |",
                "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for row in scan["external_sample_review"]:
            lines.append(
                f"| `{row['ticker']}` | {row['theme_label']} | {row['layer_label']} | {row.get('score', 0):.1f} | "
                f"{pct(row.get('mom20'))} | {pct(row.get('mom60'))} | {row.get('chase_risk', 'n/a')} | {row.get('trade_posture', 'n/a')} |"
            )

    lines.extend(["", "## 缺失数据", ""])
    if scan["summary"]["missing_cache"]:
        lines.append(", ".join(f"`{ticker}`" for ticker in scan["summary"]["missing_cache"]))
    else:
        lines.append("无")

    lines.extend(
        [
            "",
            "## 反事后诸葛亮机制",
            "",
            f"- 每次扫描都会写入 `{journal.get('journal_path', 'n/a')}`。",
            "- 后续复盘必须检查当时是否已进入候选，而不是用今天的强势股回填过去。",
            f"- 当前 20 日可评估样本平均收益：`{pct(journal.get('avg_fwd_20d'))}`",
            f"- 当前 20 日命中率：`{pct(journal.get('hit_rate_20d'))}`",
            "",
            "",
            "## 解释口径",
            "",
            "- 这是自动主线扫描，不是交易信号。",
            "- `independent_discovery` 才是正式候选来源；外部样本只做方向归因、漏网复盘和追高风险评估。",
            "- 有效输出必须同时包含：主线排名、扩散阶段、高分候选。",
            "- 下一步由 Missing Opportunity Review、V6-B 或 Overlay 决定是否值得表达。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Automated cross-theme Radar rotation scanner.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--as-of", default="")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--sync-desktop", action="store_true")
    parser.add_argument("--exclude-external-samples", action="store_true", help="Exclude friend/external short-network samples to test independent discovery alpha.")
    parser.add_argument("--exclude-ticker", action="append", default=[], help="Additional ticker to exclude from independent discovery, e.g. US.AAOI. Can be repeated.")
    args = parser.parse_args()

    config = read_json(Path(args.config))
    exclude_tickers = load_external_sample_tickers() if args.exclude_external_samples else set()
    exclude_tickers.update(normalize_ticker(ticker) for ticker in args.exclude_ticker if normalize_ticker(ticker))
    scan = build_scan(config, args.start, args.end, args.as_of, exclude_tickers=exclude_tickers)
    scan["mode"] = "independent_discovery" if args.exclude_external_samples else "full_universe_scan"
    scan["journal"] = update_journal(scan, args.end)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"radar_theme_rotation_scan_{args.tag}.json"
    md_path = OUT_DIR / f"radar_theme_rotation_scan_{args.tag}.md"
    latest_json = OUT_DIR / "latest.json"
    latest_md = OUT_DIR / "latest.md"
    payload = json.dumps(scan, ensure_ascii=False, indent=2) + "\n"
    markdown = render_md(scan)
    json_path.write_text(payload, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")

    if args.sync_desktop:
        DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest_md, DESKTOP_DIR / "Radar_主线扩散自动扫描_LATEST.md")
        shutil.copy2(latest_json, DESKTOP_DIR / "Radar_主线扩散自动扫描_LATEST.json")

    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    print(f"Top theme: {scan['summary']['top_theme']} / {scan['summary']['top_theme_stage']}")
    print(f"Candidates: {scan['summary']['candidate_count']}")
    print(f"Missing cache: {scan['summary']['missing_cache_count']}")


if __name__ == "__main__":
    main()
