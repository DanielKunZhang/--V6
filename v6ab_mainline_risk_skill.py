#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
PRICE_CACHE = ROOT / "backtest_results" / "price_cache"


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def price_path(ticker: str) -> Path:
    return PRICE_CACHE / f"{ticker.replace('.', '_')}_daily.csv"


def load_price(ticker: str, asof: str | None = None) -> pd.DataFrame:
    path = price_path(ticker)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "date" not in df.columns or "Close" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"])
    if asof:
        df = df[df["date"] <= pd.Timestamp(asof)]
    return df.sort_values("date").reset_index(drop=True)


def trailing_return(df: pd.DataFrame, days: int) -> float | None:
    if df.empty or len(df) <= days:
        return None
    now = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-days])
    if now <= 0 or prev <= 0:
        return None
    return now / prev - 1.0


def max_drawup(df: pd.DataFrame, days: int) -> float | None:
    if df.empty or len(df) <= days:
        return None
    window = df["Close"].iloc[-days:]
    low = float(window.min())
    now = float(window.iloc[-1])
    if low <= 0 or now <= 0:
        return None
    return now / low - 1.0


def count_terms(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(1 for term in terms if term.lower() in lower)


def evidence_text(rows: list[dict[str, Any]], theme_id: str) -> str:
    parts = []
    for row in rows:
        if row.get("theme") != theme_id:
            continue
        parts.append(str(row.get("summary", "")))
        parts.append(str(row.get("evidence_type", "")))
        parts.append(str(row.get("direction", "")))
    return "\n".join(parts)


def theme_price_features(theme: dict[str, Any], asof: str) -> dict[str, Any]:
    ret_21: list[float] = []
    ret_63: list[float] = []
    ret_126: list[float] = []
    drawups_126: list[float] = []
    tickers = list(dict.fromkeys(list(theme.get("proxies", [])) + list(theme.get("stocks", []))))
    for ticker in tickers:
        df = load_price(ticker, asof=asof)
        if df.empty:
            continue
        for bucket, days in [(ret_21, 21), (ret_63, 63), (ret_126, 126)]:
            value = trailing_return(df, days)
            if value is not None:
                bucket.append(value)
        value = max_drawup(df, 126)
        if value is not None:
            drawups_126.append(value)

    def mean(values: list[float]) -> float:
        return float(np.mean(values)) if values else 0.0

    def max_value(values: list[float]) -> float:
        return float(max(values)) if values else 0.0

    return {
        "priced_count": len(ret_63),
        "avg_21d_return": mean(ret_21),
        "avg_63d_return": mean(ret_63),
        "avg_126d_return": mean(ret_126),
        "max_126d_return": max_value(ret_126),
        "max_126d_drawup": max_value(drawups_126),
        "extreme_126d_fraction": float(np.mean([value >= 1.0 for value in ret_126])) if ret_126 else 0.0,
    }


def crowding_score(price_features: dict[str, Any], text: str) -> float:
    avg_63 = float(price_features.get("avg_63d_return", 0.0) or 0.0)
    avg_126 = float(price_features.get("avg_126d_return", 0.0) or 0.0)
    max_126 = float(price_features.get("max_126d_return", 0.0) or 0.0)
    max_drawup = float(price_features.get("max_126d_drawup", 0.0) or 0.0)
    extreme_fraction = float(price_features.get("extreme_126d_fraction", 0.0) or 0.0)
    text_hits = count_terms(
        text,
        [
            "crowding",
            "fomo",
            "iv",
            "overvalued",
            "too_much_narrative",
            "seller追涨",
            "卖方追涨",
            "内部人减持",
            "insider",
            "减持",
            "已被发现",
            "叙事透支",
            "期望值为负",
        ],
    )
    score = (
        max(0.0, avg_63) * 85
        + max(0.0, avg_126) * 55
        + max(0.0, max_126) * 35
        + max(0.0, max_drawup) * 25
        + extreme_fraction * 30
        + text_hits * 8
    )
    return round(clamp(score), 4)


def valuation_payoff_risk_score(text: str, evidence_rows: list[dict[str, Any]], theme_id: str) -> float:
    theme_rows = [row for row in evidence_rows if row.get("theme") == theme_id]
    valuation_rows = [row for row in theme_rows if "valuation" in str(row.get("evidence_type", "")).lower()]
    negative_rows = [row for row in theme_rows if str(row.get("direction", "")) == "negative"]
    mixed_rows = [row for row in theme_rows if str(row.get("direction", "")) == "mixed"]
    text_hits = count_terms(
        text,
        [
            "valuation",
            "overvalued",
            "needs_pullback",
            "too_much_narrative",
            "no protection",
            "无保护",
            "赔率",
            "期权溢价",
            "目标价",
            "pe",
            "price target",
        ],
    )
    score = len(valuation_rows) * 8 + len(negative_rows) * 7 + len(mixed_rows) * 3 + text_hits * 4
    return round(clamp(score), 4)


def position_quality_score(text: str, evidence_rows: list[dict[str, Any]], theme_id: str) -> float:
    positive_terms = [
        "bottleneck",
        "duopoly",
        "pricing power",
        "platform",
        "upstream",
        "leader",
        "leading",
        "validated",
        "qualification",
        "order",
        "capacity",
        "关键瓶颈",
        "双寡头",
        "定价权",
        "上游",
        "平台",
        "龙头",
        "订单",
        "认证",
        "产能",
    ]
    negative_terms = [
        "supplier dependency",
        "external supply",
        "customer concentration",
        "cpo",
        "substitution",
        "module assembler",
        "capex",
        "cash burn",
        "warrant not triggered",
        "供应商",
        "外采",
        "卡脖子",
        "客户集中",
        "替代",
        "组装",
        "烧钱",
        "减持",
    ]
    positive = count_terms(text, positive_terms)
    negative = count_terms(text, negative_terms)
    theme_rows = [row for row in evidence_rows if row.get("theme") == theme_id]
    positive_rows = [row for row in theme_rows if str(row.get("direction", "")) == "positive"]
    negative_rows = [row for row in theme_rows if str(row.get("direction", "")) == "negative"]
    score = 55 + positive * 5 + len(positive_rows) * 2 - negative * 7 - len(negative_rows) * 4
    return round(clamp(score), 4)


def event_risk_score(text: str) -> float:
    terms = [
        "earnings",
        "guidance",
        "q2",
        "q3",
        "binary event",
        "utilization",
        "warrant",
        "customer cut",
        "order",
        "财报",
        "指引",
        "利用率",
        "砍单",
        "订单",
        "认证",
        "触发",
    ]
    return round(clamp(count_terms(text, terms) * 7), 4)


def fact_precision_score(theme_row: dict[str, Any]) -> float:
    narrative = float(theme_row.get("narrative_score", 0.0) or 0.0)
    fundamental = float(theme_row.get("fundamental_score", 0.0) or 0.0)
    institutional = float(theme_row.get("institutional_score", 0.0) or 0.0)
    history = float(theme_row.get("historical_depth_score", 0.0) or 0.0)
    evidence = int(theme_row.get("evidence_count", 0) or 0)
    fact = fundamental * 0.45 + history * 0.30 + institutional * 0.15 + min(evidence, 12) * 1.5
    narrative_drag = max(0.0, narrative - max(fundamental, history)) * 0.15
    return round(clamp(fact - narrative_drag), 4)


def payoff_risk_score(crowding: float, valuation: float, event: float) -> float:
    return round(clamp(crowding * 0.45 + valuation * 0.35 + event * 0.20), 4)


def entry_quality_action(entry_quality: float, payoff_risk: float, position_quality: float) -> str:
    if payoff_risk >= 70 and entry_quality < 55:
        return "RISK_REVIEW"
    if payoff_risk >= 55:
        return "CAPPED_BOOST_ONLY"
    if entry_quality >= 72 and position_quality >= 60:
        return "BOOST_ELIGIBLE"
    if entry_quality >= 58:
        return "WATCH"
    return "NO_ENTRY_EDGE"


def apply_risk_skill(
    theme_row: dict[str, Any],
    theme_def: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    asof: str,
) -> dict[str, Any]:
    text = evidence_text(evidence_rows, str(theme_row.get("theme", "")))
    price_features = theme_price_features(theme_def, asof)
    crowding = crowding_score(price_features, text)
    valuation = valuation_payoff_risk_score(text, evidence_rows, str(theme_row.get("theme", "")))
    position = position_quality_score(text, evidence_rows, str(theme_row.get("theme", "")))
    event = event_risk_score(text)
    fact = fact_precision_score(theme_row)
    payoff = payoff_risk_score(crowding, valuation, event)
    mainline = float(theme_row.get("mainline_score", 0.0) or 0.0)
    entry_quality = clamp(mainline * 0.40 + fact * 0.22 + position * 0.23 - payoff * 0.18 + 15)
    return {
        "fact_precision_score": fact,
        "position_quality_score": position,
        "crowding_score": crowding,
        "valuation_payoff_risk_score": valuation,
        "event_risk_score": event,
        "payoff_risk_score": payoff,
        "entry_quality_score": round(entry_quality, 4),
        "entry_quality_action": entry_quality_action(entry_quality, payoff, position),
        "risk_skill_price_features": price_features,
    }
