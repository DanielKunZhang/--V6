#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import v6b_theme_rotation_backtest as bt
from v6ab_classifier_bridge_backtest import BASELINE_CONFIG, build_curves, run_v6ab


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_v2_hindsight_audit"
DEFAULT_V6A_DAILY = ROOT / "backtest_results" / "attack_engine_replay" / "attack_replay_daily_20260520_live_refreshed.csv"


def clone_themes() -> dict[str, dict[str, Any]]:
    return json.loads(json.dumps(bt.THEMES, ensure_ascii=False))


def required_tickers(themes: dict[str, dict[str, Any]]) -> list[str]:
    tickers = {"US.SPY", "US.QQQ", "US.GLD", "US.BIL", "US.IEF"}
    for theme in themes.values():
        tickers.update(theme.get("proxies", []))
        tickers.update(theme.get("stocks", []))
    return sorted(tickers)


def remove_tickers(themes: dict[str, dict[str, Any]], tickers: set[str]) -> dict[str, dict[str, Any]]:
    out = clone_theme_payload(themes)
    for theme in out.values():
        theme["proxies"] = [ticker for ticker in theme.get("proxies", []) if ticker not in tickers]
        theme["stocks"] = [ticker for ticker in theme.get("stocks", []) if ticker not in tickers]
    return {theme_id: theme for theme_id, theme in out.items() if theme.get("proxies") or theme.get("stocks")}


def remove_themes(themes: dict[str, dict[str, Any]], theme_ids: set[str]) -> dict[str, dict[str, Any]]:
    return {theme_id: theme for theme_id, theme in clone_theme_payload(themes).items() if theme_id not in theme_ids}


def clone_theme_payload(themes: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return json.loads(json.dumps(themes, ensure_ascii=False))


def run_v6b_with_themes(
    prices: pd.DataFrame,
    themes: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> tuple[pd.Series, list[dict[str, Any]]]:
    old_themes = bt.THEMES
    try:
        bt.THEMES = themes
        return bt.run_strategy(prices, **config)
    finally:
        bt.THEMES = old_themes


def period_stats(eq: pd.Series, start: str, end: str) -> dict[str, Any]:
    seg = eq[(eq.index >= pd.Timestamp(start)) & (eq.index <= pd.Timestamp(end))]
    if len(seg) < 30:
        return {}
    return bt.stats(seg / float(seg.iloc[0]) * bt.INITIAL_CAPITAL)


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:+.2%}"


def theme_lookup(themes: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = defaultdict(list)
    for theme_id, theme in themes.items():
        for ticker in theme.get("proxies", []) + theme.get("stocks", []):
            lookup[ticker].append(theme_id)
    return dict(lookup)


def infer_theme_for_ticker(ticker: str, decision: dict[str, Any], lookup: dict[str, list[str]]) -> str:
    top_ids = [row.get("theme_id") for row in decision.get("top_themes", [])]
    candidates = lookup.get(ticker, [])
    for theme_id in top_ids:
        if theme_id in candidates:
            return str(theme_id)
    return candidates[0] if candidates else "unmapped"


def decision_periods(decisions: list[dict[str, Any]], price_index: pd.DatetimeIndex) -> list[tuple[pd.Timestamp, pd.Timestamp, dict[str, Any]]]:
    out = []
    for idx, decision in enumerate(decisions):
        start = pd.Timestamp(decision["date"])
        end = pd.Timestamp(decisions[idx + 1]["date"]) if idx + 1 < len(decisions) else price_index[-1]
        start_pos = price_index.searchsorted(start)
        end_pos = price_index.searchsorted(end)
        if start_pos >= len(price_index):
            continue
        if end_pos >= len(price_index):
            end_pos = len(price_index) - 1
        if end_pos <= start_pos:
            continue
        out.append((price_index[start_pos], price_index[end_pos], decision))
    return out


def contribution_summary(
    prices: pd.DataFrame,
    decisions: list[dict[str, Any]],
    themes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    returns = prices.pct_change().fillna(0.0)
    lookup = theme_lookup(themes)
    ticker_contrib: dict[str, float] = defaultdict(float)
    theme_contrib: dict[str, float] = defaultdict(float)
    ticker_exposure_days: dict[str, int] = defaultdict(int)
    theme_exposure_days: dict[str, int] = defaultdict(int)
    ticker_avg_weight: dict[str, float] = defaultdict(float)
    theme_avg_weight: dict[str, float] = defaultdict(float)
    periods = decision_periods(decisions, prices.index)

    for start, end, decision in periods:
        weights = {k: float(v) for k, v in decision.get("weights", {}).items() if k != "CASH" and float(v) > 0}
        days = returns.loc[(returns.index > start) & (returns.index <= end)].index
        if len(days) == 0:
            continue
        for ticker, weight in weights.items():
            theme_id = infer_theme_for_ticker(ticker, decision, lookup)
            ticker_exposure_days[ticker] += len(days)
            theme_exposure_days[theme_id] += len(days)
            ticker_avg_weight[ticker] += weight * len(days)
            theme_avg_weight[theme_id] += weight * len(days)
            if ticker in returns.columns:
                contrib = float((returns.loc[days, ticker] * weight).sum())
                ticker_contrib[ticker] += contrib
                theme_contrib[theme_id] += contrib

    total_days = max(len(prices.index), 1)

    def rows(contrib: dict[str, float], exposure_days: dict[str, int], avg_weight: dict[str, float]) -> list[dict[str, Any]]:
        return sorted(
            [
                {
                    "id": key,
                    "approx_simple_contribution": float(value),
                    "exposure_days": int(exposure_days.get(key, 0)),
                    "exposure_day_ratio": float(exposure_days.get(key, 0) / total_days),
                    "avg_weight_when_held": float(avg_weight.get(key, 0.0) / max(exposure_days.get(key, 0), 1)),
                }
                for key, value in contrib.items()
            ],
            key=lambda row: row["approx_simple_contribution"],
            reverse=True,
        )

    return {
        "ticker_contribution": rows(ticker_contrib, ticker_exposure_days, ticker_avg_weight),
        "theme_contribution": rows(theme_contrib, theme_exposure_days, theme_avg_weight),
    }


def summarize_decisions(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    top_counts: dict[str, int] = defaultdict(int)
    weight_counts: dict[str, int] = defaultdict(int)
    for decision in decisions:
        for row in decision.get("top_themes", [])[:3]:
            top_counts[str(row.get("theme_id"))] += 1
        for ticker, weight in decision.get("weights", {}).items():
            if ticker != "CASH" and float(weight) > 0:
                weight_counts[ticker] += 1
    return {
        "top_theme_counts": sorted(top_counts.items(), key=lambda row: row[1], reverse=True),
        "selected_ticker_counts": sorted(weight_counts.items(), key=lambda row: row[1], reverse=True),
    }


def scenario_payload(
    name: str,
    themes: dict[str, dict[str, Any]],
    prices: pd.DataFrame,
    args: argparse.Namespace,
) -> dict[str, Any]:
    standalone_eq, decisions = run_v6b_with_themes(prices, themes, BASELINE_CONFIG)
    curves = build_curves(prices, args.v6a_daily, standalone_eq, standalone_eq)
    v6ab_eq, v6ab_log = run_v6ab(curves, "baseline_v2", 0.45, args.start, args.end)
    return {
        "scenario": name,
        "theme_count": len(themes),
        "standalone_stats": bt.stats(standalone_eq),
        "v6ab_stats": bt.stats(v6ab_eq),
        "periods": {
            "standalone": {
                "2020": period_stats(standalone_eq, "2020-01-01", "2020-12-31"),
                "2022": period_stats(standalone_eq, "2022-01-01", "2022-12-31"),
                "2024_2026": period_stats(standalone_eq, "2024-01-01", args.end),
            },
            "v6ab": {
                "2020": period_stats(v6ab_eq, "2020-01-01", "2020-12-31"),
                "2022": period_stats(v6ab_eq, "2022-01-01", "2022-12-31"),
                "2024_2026": period_stats(v6ab_eq, "2024-01-01", args.end),
            },
        },
        "decision_summary": summarize_decisions(decisions),
        "avg_dynamic_b_weight": average_dynamic_weight(v6ab_log, "baseline_v2"),
        "contribution": contribution_summary(prices, decisions, themes),
    }


def average_dynamic_weight(log: pd.DataFrame, key: str) -> float:
    if log.empty or "weights" not in log.columns:
        return 0.0
    values = []
    for raw in log["weights"]:
        try:
            values.append(float(json.loads(raw).get(key, 0.0)))
        except (TypeError, json.JSONDecodeError):
            continue
    return float(np.mean(values)) if values else 0.0


def delta_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = next(row for row in rows if row["scenario"] == "baseline_v2")
    base_standalone = baseline["standalone_stats"]
    base_v6ab = baseline["v6ab_stats"]
    out = []
    for row in rows:
        out.append(
            {
                "scenario": row["scenario"],
                "standalone_ann": row["standalone_stats"].get("ann_ret"),
                "standalone_max_dd": row["standalone_stats"].get("max_dd"),
                "standalone_sharpe": row["standalone_stats"].get("sharpe"),
                "standalone_ann_delta": row["standalone_stats"].get("ann_ret", 0.0) - base_standalone.get("ann_ret", 0.0),
                "v6ab_ann": row["v6ab_stats"].get("ann_ret"),
                "v6ab_max_dd": row["v6ab_stats"].get("max_dd"),
                "v6ab_sharpe": row["v6ab_stats"].get("sharpe"),
                "v6ab_ann_delta": row["v6ab_stats"].get("ann_ret", 0.0) - base_v6ab.get("ann_ret", 0.0),
                "v6ab_sharpe_delta": row["v6ab_stats"].get("sharpe", 0.0) - base_v6ab.get("sharpe", 0.0),
                "v6ab_2024_2026_ann": row["periods"]["v6ab"]["2024_2026"].get("ann_ret"),
                "v6ab_2022_ann": row["periods"]["v6ab"]["2022"].get("ann_ret"),
                "v6ab_2020_ann": row["periods"]["v6ab"]["2020"].get("ann_ret"),
            }
        )
    return out


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# V6AB V2 Hindsight Exposure Audit",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 区间：`{payload['start']} -> {payload['end']}`",
        "- 用途：审计 V2 是否过度依赖静态后视镜赢家池；不改变模拟盘。",
        "- 模拟盘状态：`NO_CHANGE`，继续保持 `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`。",
        "",
        "## Scenario Stress Tests",
        "",
        "| scenario | V6B ann | V6B maxDD | V6B Sharpe | V6AB ann | V6AB maxDD | V6AB Sharpe | V6AB ann delta | 2020 | 2022 | 2024-2026 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["scenario_deltas"]:
        lines.append(
            f"| `{row['scenario']}` | {fmt_pct(row['standalone_ann'])} | {fmt_pct(row['standalone_max_dd'])} | {row.get('standalone_sharpe', 0):.2f} | "
            f"{fmt_pct(row['v6ab_ann'])} | {fmt_pct(row['v6ab_max_dd'])} | {row.get('v6ab_sharpe', 0):.2f} | "
            f"{fmt_pct(row['v6ab_ann_delta'])} | {fmt_pct(row['v6ab_2020_ann'])} | {fmt_pct(row['v6ab_2022_ann'])} | {fmt_pct(row['v6ab_2024_2026_ann'])} |"
        )
    baseline = payload["scenarios"][0]
    lines += [
        "",
        "## Baseline V2 Approx Contribution",
        "",
        "### Themes",
        "",
        "| theme | approx contribution | ticker-days | ticker-day ratio | avg weight when held |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in baseline["contribution"]["theme_contribution"][:12]:
        lines.append(
            f"| `{row['id']}` | {fmt_pct(row['approx_simple_contribution'])} | {row['exposure_days']} | "
            f"{fmt_pct(row['exposure_day_ratio'])} | {fmt_pct(row['avg_weight_when_held'])} |"
        )
    lines += [
        "",
        "### Tickers",
        "",
        "| ticker | approx contribution | exposure days | exposure ratio | avg weight when held |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in baseline["contribution"]["ticker_contribution"][:20]:
        lines.append(
            f"| `{row['id']}` | {fmt_pct(row['approx_simple_contribution'])} | {row['exposure_days']} | "
            f"{fmt_pct(row['exposure_day_ratio'])} | {fmt_pct(row['avg_weight_when_held'])} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- 这不是为了否定 V2；V2 仍是当前模拟盘版本。",
        "- 如果拿掉少数静态赢家后收益显著坍塌，说明 V2 的历史成绩包含明显后视镜暴露，需要 PIT 主线识别来替代静态答案。",
        "- 如果压力测试后仍保持较高 Sharpe，说明 V2 的动量/风控框架本身有价值，可以作为 PIT 版本的结构底座。",
        "- 下一步应把该审计结果接入候选晋级规则：PIT 版本不仅要接近 V2，还要解释并降低 V2 的后视镜依赖。",
        "",
    ]
    return "\n".join(lines)


def build_scenarios(base_themes: dict[str, dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "baseline_v2": base_themes,
        "remove_nvda": remove_tickers(base_themes, {"US.NVDA"}),
        "remove_semis_ai_theme": remove_themes(base_themes, {"semis_ai"}),
        "remove_semis_ai_stocks_keep_etf": {
            **clone_theme_payload(base_themes),
            "semis_ai": {
                **clone_theme_payload(base_themes)["semis_ai"],
                "stocks": [],
            },
        },
        "remove_smh_soxx": remove_tickers(base_themes, {"US.SMH", "US.SOXX"}),
        "remove_qqq_arkk": remove_tickers(base_themes, {"US.QQQ", "US.ARKK"}),
        "proxy_only_no_stocks": {
            theme_id: {**theme, "stocks": []}
            for theme_id, theme in clone_theme_payload(base_themes).items()
            if theme.get("proxies")
        },
        "etf_broad_no_ai_stocks": remove_tickers(
            {
                theme_id: {**theme, "stocks": []}
                for theme_id, theme in clone_theme_payload(base_themes).items()
                if theme.get("proxies")
            },
            {"US.SMH", "US.SOXX", "US.ARKK"},
        ),
    }


def top_contributor_scenarios(
    base_themes: dict[str, dict[str, Any]],
    baseline_row: dict[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    ranked = [
        row["id"]
        for row in baseline_row["contribution"]["ticker_contribution"]
        if row["id"] not in {"US.BIL", "US.GLD", "US.IEF"} and row["approx_simple_contribution"] > 0
    ]
    return {
        "remove_top3_contributor_tickers": remove_tickers(base_themes, set(ranked[:3])),
        "remove_top5_contributor_tickers": remove_tickers(base_themes, set(ranked[:5])),
        "remove_top8_contributor_tickers": remove_tickers(base_themes, set(ranked[:8])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit V6AB V2 hindsight exposure without touching paper sim.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--v6a-daily", type=Path, default=DEFAULT_V6A_DAILY)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    base_themes = clone_themes()
    scenarios = build_scenarios(base_themes)
    prices = bt.build_price_matrix(required_tickers(base_themes), args.start, args.end).ffill(limit=3)

    rows = [scenario_payload("baseline_v2", scenarios["baseline_v2"], prices, args)]
    scenarios.update(top_contributor_scenarios(base_themes, rows[0]))
    rows.extend(
        scenario_payload(name, themes, prices, args)
        for name, themes in scenarios.items()
        if name != "baseline_v2"
    )
    payload = {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "baseline_config": BASELINE_CONFIG,
        "scenarios": rows,
        "scenario_deltas": delta_rows(rows),
    }
    md = render_md(payload)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md + "\n", encoding="utf-8")
    pd.DataFrame(payload["scenario_deltas"]).to_csv(args.output_dir / "latest_scenarios.csv", index=False)
    pd.DataFrame(rows[0]["contribution"]["ticker_contribution"]).to_csv(args.output_dir / "latest_baseline_ticker_contribution.csv", index=False)
    pd.DataFrame(rows[0]["contribution"]["theme_contribution"]).to_csv(args.output_dir / "latest_baseline_theme_contribution.csv", index=False)
    (REPORT_ROOT / "V6AB_V2_Hindsight_Audit_LATEST.md").write_text(md + "\n", encoding="utf-8")
    (REPORT_ROOT / "V6AB_V2_Hindsight_Audit_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
