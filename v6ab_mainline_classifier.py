#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_daily_evolution"
DEFAULT_LEDGER = OUT_DIR / "latest_evidence_ledger.json"
PRICE_CACHE = ROOT / "backtest_results" / "price_cache"

THEMES: dict[str, dict[str, Any]] = {
    "semis_ai": {
        "label": "Semis / AI Compute",
        "proxies": ["US.SMH", "US.SOXX"],
        "stocks": ["US.NVDA", "US.AVGO", "US.AMD", "US.TSM", "US.MU", "US.ANET", "US.COHR", "US.MRVL", "US.LITE", "US.AAOI"],
        "offensive": True,
    },
    "ai_infra": {
        "label": "AI Infrastructure",
        "proxies": ["US.SMH", "US.XLK", "US.XLI"],
        "stocks": ["US.NVDA", "US.AVGO", "US.AMD", "US.ANET", "US.VRT", "US.ETN", "US.GEV", "US.CEG"],
        "offensive": True,
    },
    "ai_networking": {
        "label": "AI Networking / Fabric",
        "proxies": ["US.SMH", "US.XLK"],
        "stocks": ["US.ANET", "US.AVGO", "US.MRVL", "US.NOK", "US.CSCO"],
        "offensive": True,
    },
    "ai_optical": {
        "label": "AI Optical / Interconnect",
        "proxies": ["US.SMH", "US.XLK"],
        "stocks": ["US.COHR", "US.AAOI", "US.LITE", "US.CRDO", "US.ALAB"],
        "offensive": True,
    },
    "ai_memory": {
        "label": "AI Memory / Storage",
        "proxies": ["US.SMH", "US.SOXX"],
        "stocks": ["US.MU", "US.WDC", "US.SNDK"],
        "offensive": True,
    },
    "ai_power_datacenter": {
        "label": "AI Power / Data Center",
        "proxies": ["US.XLU", "US.XLI"],
        "stocks": ["US.NEE", "US.CEG", "US.VST", "US.GEV", "US.ETN", "US.BE", "US.IREN", "US.APLD", "US.CORZ"],
        "offensive": True,
    },
    "ai_platform": {
        "label": "AI Platform / Search / Cloud",
        "proxies": ["US.QQQ", "US.XLK", "US.FDN"],
        "stocks": ["US.GOOGL", "US.MSFT", "US.AMZN", "US.META", "US.NVDA"],
        "offensive": True,
    },
    "robotics_automation": {
        "label": "Robotics / Automation",
        "proxies": ["US.XLI", "US.XLK"],
        "stocks": ["US.TSLA", "US.ROK", "US.HON", "US.IR", "US.ETN"],
        "offensive": True,
    },
    "unclassified": {"label": "Unclassified", "proxies": ["US.SPY"], "stocks": [], "offensive": False},
}
HISTORICAL_THEMES: dict[str, dict[str, Any]] = {
    "liquidity_growth": {
        "label": "Liquidity Growth / High Beta Growth",
        "proxies": ["US.ARKK", "US.QQQ", "US.IWM"],
        "stocks": ["US.TSLA", "US.AMZN", "US.NFLX", "US.NVDA", "US.AMD", "US.META"],
        "offensive": True,
        "market_only": True,
    },
    "broad_beta": {
        "label": "Broad Beta",
        "proxies": ["US.SPY", "US.QQQ", "US.IWM"],
        "stocks": ["US.AMZN", "US.MSFT", "US.GOOGL", "US.META", "US.TSLA"],
        "offensive": True,
        "market_only": True,
    },
    "technology": {
        "label": "Technology / Software",
        "proxies": ["US.XLK", "US.IGV", "US.FDN", "US.ARKK"],
        "stocks": ["US.MSFT", "US.GOOGL", "US.META", "US.AMZN", "US.NFLX"],
        "offensive": True,
        "market_only": True,
    },
    "precious_metals": {
        "label": "Gold / Precious Metals",
        "proxies": ["US.GLD", "US.SLV", "US.GDX"],
        "stocks": [],
        "offensive": False,
        "market_only": True,
    },
    "energy_resources": {
        "label": "Energy / Resources",
        "proxies": ["US.XLE", "US.XOP", "US.DBC"],
        "stocks": [],
        "offensive": False,
        "market_only": True,
    },
    "financials": {
        "label": "Financials",
        "proxies": ["US.XLF", "US.KRE"],
        "stocks": ["US.JPM", "US.BRK.B"],
        "offensive": False,
        "market_only": True,
    },
    "industrials_infra": {
        "label": "Industrials / Infrastructure",
        "proxies": ["US.XLI"],
        "stocks": ["US.ROK", "US.ETN", "US.HON", "US.IR", "US.TER"],
        "offensive": False,
        "market_only": True,
    },
    "utilities_power": {
        "label": "Utilities / Power",
        "proxies": ["US.XLU"],
        "stocks": [],
        "offensive": False,
        "market_only": True,
    },
    "consumer_discretionary": {
        "label": "Consumer Discretionary",
        "proxies": ["US.XLY"],
        "stocks": ["US.AMZN", "US.TSLA", "US.NFLX"],
        "offensive": True,
        "market_only": True,
    },
}


def theme_defs_for_taxonomy(taxonomy: str) -> dict[str, dict[str, Any]]:
    if taxonomy == "historical":
        merged = dict(HISTORICAL_THEMES)
        merged.update(THEMES)
        return merged
    return THEMES


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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


def ret(df: pd.DataFrame, days: int) -> float | None:
    if df.empty or len(df) <= days:
        return None
    now = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-days])
    if now <= 0 or prev <= 0:
        return None
    return now / prev - 1.0


def above_ma(df: pd.DataFrame, days: int) -> bool:
    if df.empty or len(df) < days:
        return False
    ma = float(df["Close"].iloc[-days:].mean())
    return ma > 0 and float(df["Close"].iloc[-1]) > ma


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def market_score(theme_id: str, asof: str | None = None, theme_defs: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    theme_defs = theme_defs or THEMES
    theme = theme_defs.get(theme_id, THEMES["unclassified"])
    spy = load_price("US.SPY", asof=asof)
    spy_ret_63 = ret(spy, 63) or 0.0
    proxy_scores = []
    stock_scores = []
    for ticker in theme["proxies"]:
        df = load_price(ticker, asof=asof)
        if df.empty:
            continue
        r63 = ret(df, 63) or 0.0
        r126 = ret(df, 126) or 0.0
        rel = r63 - spy_ret_63
        trend = 1.0 if above_ma(df, 200) else 0.0
        proxy_scores.append(clamp(50 + r63 * 90 + r126 * 45 + rel * 70 + trend * 10))
    for ticker in theme["stocks"]:
        df = load_price(ticker, asof=asof)
        if df.empty:
            continue
        r63 = ret(df, 63) or 0.0
        r126 = ret(df, 126) or 0.0
        trend = 1.0 if above_ma(df, 100) else 0.0
        stock_scores.append(clamp(45 + r63 * 80 + r126 * 35 + trend * 10))
    proxy_score = float(np.mean(proxy_scores)) if proxy_scores else 45.0
    breadth = float(np.mean([score >= 60 for score in stock_scores])) if stock_scores else 0.0
    stock_score = float(np.mean(stock_scores)) if stock_scores else 45.0
    total = proxy_score * 0.55 + stock_score * 0.25 + breadth * 20
    return {
        "market_score": round(clamp(total), 4),
        "proxy_score": round(proxy_score, 4),
        "stock_score": round(stock_score, 4),
        "breadth": round(breadth, 4),
        "priced_tickers": len(stock_scores),
    }


def evidence_scores(rows: list[dict[str, Any]], theme_id: str) -> dict[str, float]:
    theme_rows = [row for row in rows if row.get("theme") == theme_id]
    buckets = {
        "narrative_score": [],
        "fundamental_score": [],
        "institutional_score": [],
        "historical_depth_score": [],
        "risk_penalty": [],
    }
    for row in theme_rows:
        conf = float(row.get("confidence", 0.5))
        fresh = float(row.get("freshness", 0.5))
        weight = float(row.get("weight", 0.5))
        raw = 100.0 * conf * fresh * weight
        direction = str(row.get("direction", "neutral"))
        if direction == "negative":
            buckets["risk_penalty"].append(raw)
            continue
        if direction == "mixed":
            buckets["risk_penalty"].append(raw * 0.45)
            raw *= 0.75
        etype = str(row.get("evidence_type", "")).lower()
        if "institutional" in etype:
            buckets["institutional_score"].append(raw)
        elif (
            "valuation" in etype
            or "earnings" in etype
            or "10q" in etype
            or "10-q" in etype
            or "10k" in etype
            or "10-k" in etype
            or "20f" in etype
            or "20-f" in etype
            or "40f" in etype
            or "40-f" in etype
            or "annual_report" in etype
            or "quarterly_report" in etype
        ):
            buckets["fundamental_score"].append(raw)
        else:
            buckets["narrative_score"].append(raw)
        if (
            etype.startswith("sec_")
            or etype
            in {
                "earnings_release",
                "investor_presentation",
                "business_update",
                "material_agreement",
                "quarterly_report",
                "annual_report",
            }
        ):
            buckets["historical_depth_score"].append(raw)

    def bucket_score(values: list[float]) -> float:
        if not values:
            return 0.0
        top = sorted(values, reverse=True)[:8]
        return float(np.mean(top))

    return {
        "narrative_score": round(bucket_score(buckets["narrative_score"]), 4),
        "fundamental_score": round(bucket_score(buckets["fundamental_score"]), 4),
        "institutional_score": round(bucket_score(buckets["institutional_score"]), 4),
        "historical_depth_score": round(bucket_score(buckets["historical_depth_score"]), 4),
        "risk_penalty": round(bucket_score(buckets["risk_penalty"]), 4),
        "evidence_count": len(theme_rows),
    }


def classify_state(
    mainline_score: float,
    market: float,
    evidence_count: int,
    risk_penalty: float,
    *,
    breadth: float = 0.0,
    market_only: bool = False,
) -> str:
    if mainline_score >= 68 and market >= 58 and evidence_count >= 6 and risk_penalty < 25:
        return "CONFIRMED"
    if mainline_score >= 58 and market >= 52 and evidence_count >= 3:
        return "STARTER"
    if market_only and market >= 82 and breadth >= 0.66 and risk_penalty < 25:
        return "STARTER"
    if mainline_score >= 48 or evidence_count >= 3:
        return "CANDIDATE"
    if risk_penalty >= 30:
        return "RISK_REVIEW"
    return "DORMANT"


def signal_tier(row: dict[str, Any]) -> str:
    state = str(row.get("state", "DORMANT"))
    market = float(row.get("market_score", 0.0))
    breadth = float(row.get("breadth", 0.0))
    evidence_count = int(row.get("evidence_count", 0))
    risk_penalty = float(row.get("risk_penalty", 0.0))
    mainline = float(row.get("mainline_score", 0.0))
    market_only = bool(row.get("market_only", False))
    if market_only and evidence_count < 2:
        if state in {"CONFIRMED", "STARTER"} and market >= 90 and breadth >= 0.75 and risk_penalty < 20:
            return "BOOST"
        if state in {"CONFIRMED", "STARTER", "CANDIDATE"} and (market >= 75 or breadth >= 0.50):
            return "WATCH"
        return "NONE"
    if state == "CONFIRMED" and mainline >= 72 and market >= 65 and breadth >= 0.66 and evidence_count >= 8 and risk_penalty < 20:
        return "OVERRIDE"
    if state in {"CONFIRMED", "STARTER"} and market >= 52 and risk_penalty < 30:
        return "BOOST"
    if state == "CANDIDATE" and (evidence_count >= 3 or market >= 75) and risk_penalty < 35:
        return "WATCH"
    return "NONE"


def ticker_priority(rows: list[dict[str, Any]], theme_allowlist: list[str]) -> list[dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    for row in rows:
        theme = str(row.get("theme", ""))
        ticker = str(row.get("ticker", ""))
        if theme not in theme_allowlist or not ticker.startswith("US."):
            continue
        direction = str(row.get("direction", "neutral"))
        sign = -1.0 if direction == "negative" else 0.55 if direction == "mixed" else 1.0
        points = sign * float(row.get("confidence", 0.5)) * float(row.get("freshness", 0.5)) * float(row.get("weight", 0.5)) * 100.0
        item = scores.setdefault(ticker, {"ticker": ticker, "theme": theme, "score": 0.0, "evidence_count": 0})
        item["score"] += points
        item["evidence_count"] += 1
    ranked = sorted(scores.values(), key=lambda item: (item["score"], item["evidence_count"]), reverse=True)
    for item in ranked:
        item["score"] = round(float(item["score"]), 4)
    return ranked[:30]


def build_classifier(ledger: dict[str, Any], asof: str, taxonomy: str = "ai") -> dict[str, Any]:
    rows = ledger.get("rows", [])
    theme_rows = []
    theme_defs = theme_defs_for_taxonomy(taxonomy)
    for theme_id, theme in theme_defs.items():
        m = market_score(theme_id, asof=asof, theme_defs=theme_defs)
        e = evidence_scores(rows, theme_id)
        offensive_bonus = 3.0 if theme.get("offensive") else -4.0
        mainline = (
            m["market_score"] * 0.45
            + e["narrative_score"] * 0.18
            + e["fundamental_score"] * 0.16
            + e["institutional_score"] * 0.16
            + e["historical_depth_score"] * 0.18
            - e["risk_penalty"] * 0.16
            + offensive_bonus
        )
        state = classify_state(
            mainline,
            m["market_score"],
            int(e["evidence_count"]),
            e["risk_penalty"],
            breadth=float(m.get("breadth", 0.0)),
            market_only=bool(theme.get("market_only")),
        )
        row = {
            "theme": theme_id,
            "label": theme["label"],
            "market_only": bool(theme.get("market_only", False)),
            **m,
            **e,
            "mainline_score": round(clamp(mainline), 4),
            "state": state,
        }
        row["signal_tier"] = signal_tier(row)
        theme_rows.append(row)
    theme_rows = sorted(theme_rows, key=lambda row: row["mainline_score"], reverse=True)
    allowlist = [row["theme"] for row in theme_rows if row["state"] in {"CONFIRMED", "STARTER"}]
    watchlist = [row["theme"] for row in theme_rows if row["signal_tier"] == "WATCH"]
    boost_allowlist = [row["theme"] for row in theme_rows if row["signal_tier"] in {"BOOST", "OVERRIDE"}]
    override_allowlist = [row["theme"] for row in theme_rows if row["signal_tier"] == "OVERRIDE"]
    confirmed = [row for row in theme_rows if row["state"] == "CONFIRMED"]
    starter = [row for row in theme_rows if row["state"] == "STARTER"]
    fallback = not confirmed
    b_cap = 0.45 if confirmed and confirmed[0]["mainline_score"] >= 72 else 0.30 if confirmed or starter else 0.05
    priorities = ticker_priority(rows, allowlist or ["semis_ai", "ai_infra"])
    return {
        "asof": asof,
        "taxonomy": taxonomy,
        "active_baseline": "V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING",
        "fallback_to_v2": fallback,
        "b_sleeve_cap_hint": b_cap,
        "theme_allowlist": allowlist,
        "watchlist": watchlist,
        "boost_allowlist": boost_allowlist,
        "override_allowlist": override_allowlist,
        "themes": theme_rows,
        "ticker_priority": priorities,
        "paper_sim_action": "NO_CHANGE_BACKTEST_ONLY",
        "notes": [
            "Classifier v1 is research-only and must not replace the active paper sim.",
            "Non-price evidence can affect allowlist/ranking/cap hints, not direct trades.",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB Mainline Classifier v1",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 当前生产基线：`{payload['active_baseline']}`",
        f"- 是否 fallback 到 V2：`{payload['fallback_to_v2']}`",
        f"- B sleeve cap hint：`{payload['b_sleeve_cap_hint']:.0%}`",
        f"- 交易动作：`{payload['paper_sim_action']}`",
        "",
        "## Theme State",
        "",
        "| theme | state | tier | mainline | market | narrative | fundamental | institutional | history | risk | evidence | breadth |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["themes"]:
        lines.append(
            f"| {row['label']} | `{row['state']}` | `{row['signal_tier']}` | {row['mainline_score']:.1f} | {row['market_score']:.1f} | "
            f"{row['narrative_score']:.1f} | {row['fundamental_score']:.1f} | {row['institutional_score']:.1f} | "
            f"{row['historical_depth_score']:.1f} | {row['risk_penalty']:.1f} | {row['evidence_count']} | {row['breadth']:.2f} |"
        )
    lines += ["", "## Ticker Priority", "", "| ticker | theme | score | evidence |", "| --- | --- | ---: | ---: |"]
    for row in payload["ticker_priority"][:20]:
        lines.append(f"| `{row['ticker']}` | {row['theme']} | {row['score']:.1f} | {row['evidence_count']} |")
    lines += [
        "",
        "## Decision Boundary",
        "",
        "- 当前只生成研究状态和回测输入，不改 V6AB 模拟盘。",
        "- 若无 `CONFIRMED` theme，继续 fallback 到 V2。",
        "- 下一步才把 `theme_allowlist` / `ticker_priority` / `b_sleeve_cap_hint` 接入回测对比。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build V6AB mainline classifier v1 from evidence ledger and local prices.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--ledger-json", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--taxonomy", choices=["ai", "historical"], default="ai")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    ledger = load_json(args.ledger_json)
    payload = build_classifier(ledger, args.asof, taxonomy=args.taxonomy)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest_mainline_classifier.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "latest_mainline_classifier.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Mainline_Classifier_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_ROOT / "V6AB_Mainline_Classifier_LATEST.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
