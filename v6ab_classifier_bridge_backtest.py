#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

import v6b_theme_rotation_backtest as bt
from v6ab_sleeve_blend_backtest import benchmark_equity, dynamic_b_sizing_equity, load_v6a_composite


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_daily_evolution"
DEFAULT_CLASSIFIER = OUT_DIR / "latest_mainline_classifier.json"
DEFAULT_V6A_DAILY = ROOT / "backtest_results" / "attack_engine_replay" / "attack_replay_daily_20260520_live_refreshed.csv"

BASELINE_CONFIG = {
    "top_n": 3,
    "min_theme_score": 0.08,
    "risk_weight": 0.90,
    "use_cooldown": True,
    "vol_target": 0.22,
    "dd_brake": True,
    "expression": "stocks",
    "stock_top_n": 2,
}


THEME_PROXY_FALLBACKS = {
    "liquidity_growth": ["US.ARKK", "US.QQQ", "US.IWM"],
    "semis_ai": ["US.SMH", "US.SOXX"],
    "ai_memory": ["US.SMH", "US.SOXX"],
    "ai_networking": ["US.SMH", "US.XLK"],
    "ai_optical": ["US.SMH", "US.XLK"],
    "ai_infra": ["US.SMH", "US.XLK", "US.XLI"],
    "ai_power_datacenter": ["US.XLU", "US.XLI"],
    "ai_platform": ["US.QQQ", "US.XLK", "US.FDN"],
    "robotics_automation": ["US.XLI", "US.XLK"],
}

THEME_STOCK_FALLBACKS = {
    "liquidity_growth": ["US.TSLA", "US.AMZN", "US.NFLX", "US.NVDA", "US.AMD", "US.META"],
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_bridge_themes(classifier: dict[str, Any]) -> dict[str, dict[str, Any]]:
    allowed = set(classifier.get("theme_allowlist", []))
    if not allowed:
        allowed = {"semis_ai"}
    ticker_priority = classifier.get("ticker_priority", [])
    ranked_by_theme: dict[str, list[str]] = {}
    for row in ticker_priority:
        theme = str(row.get("theme", ""))
        ticker = str(row.get("ticker", ""))
        if theme in allowed and ticker.startswith("US."):
            ranked_by_theme.setdefault(theme, []).append(ticker)

    original = dict(bt.THEMES)
    bridge: dict[str, dict[str, Any]] = {}
    for theme_id in allowed:
        original_theme = original.get(theme_id, {})
        proxies = list(original_theme.get("proxies", [])) or THEME_PROXY_FALLBACKS.get(theme_id, ["US.SPY"])
        stocks = list(
            dict.fromkeys(
                ranked_by_theme.get(theme_id, [])
                + list(original_theme.get("stocks", []))
                + THEME_STOCK_FALLBACKS.get(theme_id, [])
            )
        )
        if not stocks and not proxies:
            continue
        bridge[theme_id] = {
            "label": str(original_theme.get("label", theme_id)),
            "proxies": proxies,
            "stocks": stocks,
        }
    if not bridge:
        bridge = {"semis_ai": original["semis_ai"]}
    return bridge


def required_tickers(themes: dict[str, dict[str, Any]]) -> list[str]:
    tickers = {"US.SPY", "US.QQQ", "US.GLD", "US.BIL", "US.IEF"}
    for theme in themes.values():
        tickers.update(theme.get("proxies", []))
        tickers.update(theme.get("stocks", []))
    for theme in bt.THEMES.values():
        tickers.update(theme.get("proxies", []))
        tickers.update(theme.get("stocks", []))
    return sorted(tickers)


def run_v6b(prices: pd.DataFrame, config: dict[str, Any], themes: dict[str, dict[str, Any]] | None = None) -> tuple[pd.Series, list[dict[str, Any]]]:
    old_themes = bt.THEMES
    try:
        if themes is not None:
            bt.THEMES = themes
        return bt.run_strategy(prices, **config)
    finally:
        bt.THEMES = old_themes


def period_stats(eq: pd.Series, start: str, end: str) -> dict[str, Any]:
    seg = eq[(eq.index >= pd.Timestamp(start)) & (eq.index <= pd.Timestamp(end))]
    if len(seg) < 30:
        return {}
    return bt.stats(seg / float(seg.iloc[0]) * bt.INITIAL_CAPITAL)


def build_curves(prices: pd.DataFrame, v6a_path: Path, baseline_eq: pd.Series, bridge_eq: pd.Series) -> dict[str, pd.Series]:
    return {
        "V6A": load_v6a_composite(v6a_path),
        "baseline_v2": baseline_eq,
        "classifier_bridge": bridge_eq,
        "GLD": benchmark_equity(prices, "US.GLD"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
    }


def run_v6ab(curves: dict[str, pd.Series], b_key: str, cap_hint: float, start: str, end: str) -> tuple[pd.Series, pd.DataFrame]:
    cap = max(0.05, min(0.45, float(cap_hint)))
    return dynamic_b_sizing_equity(
        curves,
        b_key=b_key,
        b_low=0.05,
        b_mid=min(0.30, cap),
        b_high=cap,
        b_strong_126d=0.08,
        b_weak_63d=-0.08,
        hedge_max=0.30,
        vol_threshold=0.28,
        corr_threshold=0.60,
        dd_threshold=-0.12,
        start=start,
        end=end,
    )


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB Classifier Bridge Backtest v1",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 回测区间：`{payload['start']} -> {payload['end']}`",
        f"- classifier allowlist：`{', '.join(payload['theme_allowlist']) or 'none'}`",
        f"- classifier B cap hint：`{payload['b_sleeve_cap_hint']:.0%}`",
        "- 证据边界：这是 current-evidence bridge，不是 point-in-time 历史证据，不能替换 V2。",
        "",
        "## Results",
        "",
        "| candidate | ann | maxDD | Sharpe | 2024-2026 ann | 2022 ann |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["rows"]:
        s = row["stats"]
        p2024 = row.get("periods", {}).get("2024_2026", {})
        p2022 = row.get("periods", {}).get("2022", {})
        lines.append(
            f"| {row['candidate']} | {s.get('ann_ret', 0):+.2%} | {s.get('max_dd', 0):+.2%} | "
            f"{s.get('sharpe', 0):.2f} | {p2024.get('ann_ret', 0):+.2%} | {p2022.get('ann_ret', 0):+.2%} |"
        )
    lines += [
        "",
        "## Bridge Themes",
        "",
        "| theme | proxies | stocks |",
        "| --- | --- | --- |",
    ]
    for theme_id, theme in payload["bridge_themes"].items():
        lines.append(
            f"| {theme_id} | `{', '.join(theme.get('proxies', []))}` | `{', '.join(theme.get('stocks', [])[:12])}` |"
        )
    lines += [
        "",
        "## Decision",
        "",
        "- 若 bridge 明显优于 V2，只说明接口方向值得继续；下一步必须做 PIT ledger/history 后再比较。",
        "- 若 bridge 不优于 V2，也不推翻 classifier，因为当前证据只代表今天，不代表历史。",
        "- 模拟盘保持 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge classifier outputs into V6AB backtest without touching paper sim.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--classifier-json", type=Path, default=DEFAULT_CLASSIFIER)
    parser.add_argument("--v6a-daily", type=Path, default=DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    classifier = load_json(args.classifier_json)
    bridge_themes = build_bridge_themes(classifier)
    prices = bt.build_price_matrix(required_tickers(bridge_themes), args.start, args.end).ffill(limit=3)
    baseline_eq, baseline_decisions = run_v6b(prices, BASELINE_CONFIG)
    bridge_config = dict(BASELINE_CONFIG)
    bridge_config["top_n"] = max(1, min(3, len(bridge_themes)))
    bridge_config["stock_top_n"] = 3
    bridge_eq, bridge_decisions = run_v6b(prices, bridge_config, bridge_themes)

    curves = build_curves(prices, args.v6a_daily, baseline_eq, bridge_eq)
    baseline_v6ab, baseline_log = run_v6ab(curves, "baseline_v2", 0.45, args.start, args.end)
    bridge_v6ab, bridge_log = run_v6ab(curves, "classifier_bridge", float(classifier.get("b_sleeve_cap_hint", 0.30)), args.start, args.end)

    rows = []
    for name, eq, log in [
        ("baseline_v2_standalone_v6b", baseline_eq, pd.DataFrame()),
        ("classifier_bridge_standalone_v6b", bridge_eq, pd.DataFrame()),
        ("baseline_v2_v6ab_dynamic_b", baseline_v6ab, baseline_log),
        ("classifier_bridge_v6ab_dynamic_b", bridge_v6ab, bridge_log),
    ]:
        rows.append(
            {
                "candidate": name,
                "stats": bt.stats(eq),
                "overlay_days": int((log["weights"].str.contains("GLD|BIL")).sum()) if not log.empty else 0,
                "periods": {
                    "2024_2026": period_stats(eq, "2024-01-01", args.end),
                    "2022": period_stats(eq, "2022-01-01", "2022-12-31"),
                    "2020": period_stats(eq, "2020-01-01", "2020-12-31"),
                },
            }
        )

    payload = {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "classifier_json": str(args.classifier_json),
        "theme_allowlist": classifier.get("theme_allowlist", []),
        "b_sleeve_cap_hint": float(classifier.get("b_sleeve_cap_hint", 0.30)),
        "bridge_themes": bridge_themes,
        "rows": rows,
        "recent_decisions": {
            "baseline": baseline_decisions[-6:],
            "classifier_bridge": bridge_decisions[-6:],
        },
    }
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "latest_classifier_bridge_backtest.json"
    md_path = args.output_dir / "latest_classifier_bridge_backtest.md"
    csv_path = args.output_dir / "latest_classifier_bridge_backtest.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")
    pd.DataFrame(
        [
            {
                "candidate": row["candidate"],
                "overlay_days": row["overlay_days"],
                **row["stats"],
                "ann_2024_2026": row["periods"]["2024_2026"].get("ann_ret"),
                "ann_2022": row["periods"]["2022"].get("ann_ret"),
                "ann_2020": row["periods"]["2020"].get("ann_ret"),
            }
            for row in rows
        ]
    ).to_csv(csv_path, index=False)
    (REPORT_ROOT / "V6AB_Classifier_Bridge_Backtest_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Classifier_Bridge_Backtest_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
