#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import v6ab_classifier_bridge_backtest as bridge
import v6ab_legacy_winner_preservation_experiment as legacy
import v6ab_pit_classifier_bridge_backtest as pit
import v6b_theme_rotation_backtest as bt
from v6ab_sleeve_blend_backtest import benchmark_equity, dynamic_b_sizing_equity, load_v6a_composite


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_defense_layer_attribution"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"
DEFAULT_V6A_DAILY = bridge.DEFAULT_V6A_DAILY


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing json: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def max_drawdown_window(eq: pd.Series) -> dict[str, Any]:
    series = eq.dropna().sort_index()
    peak = series.cummax()
    dd = series / peak - 1.0
    trough = dd.idxmin()
    peak_date = series.loc[:trough].idxmax()
    recovery_candidates = series.loc[trough:][series.loc[trough:] >= peak.loc[trough]]
    recovery = recovery_candidates.index[0] if not recovery_candidates.empty else pd.NaT
    return {
        "peak": pd.Timestamp(peak_date),
        "trough": pd.Timestamp(trough),
        "recovery": None if pd.isna(recovery) else pd.Timestamp(recovery),
        "max_dd": float(dd.loc[trough]),
        "peak_equity": float(series.loc[peak_date]),
        "trough_equity": float(series.loc[trough]),
    }


def parse_weights(value: Any) -> dict[str, float]:
    if isinstance(value, dict):
        return {str(k): float(v) for k, v in value.items()}
    if not isinstance(value, str) or not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return {str(k): float(v) for k, v in data.items()}


def window_stats(eq: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, float]:
    part = eq[(eq.index >= start) & (eq.index <= end)].dropna()
    if part.empty:
        return {"return": np.nan, "max_dd": np.nan}
    ret = float(part.iloc[-1] / part.iloc[0] - 1.0)
    dd = float((part / part.cummax() - 1.0).min())
    return {"return": ret, "max_dd": dd}


def contribution_rows(
    log: pd.DataFrame,
    curves: dict[str, pd.Series],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict[str, Any]]:
    frame = pd.DataFrame(curves).sort_index().ffill().dropna()
    rets = frame.pct_change().fillna(0.0)
    log = log.copy()
    log["date_ts"] = pd.to_datetime(log["date"])
    rows: list[dict[str, Any]] = []
    mask = (log["date_ts"] >= start) & (log["date_ts"] <= end)
    for _, row in log.loc[mask].iterrows():
        dt = pd.Timestamp(row["date_ts"])
        weights = parse_weights(row.get("weights"))
        contrib = {key: float(rets.loc[dt, key]) * weight for key, weight in weights.items() if key in rets.columns}
        rows.append(
            {
                "date": str(dt.date()),
                "equity": float(row.get("equity", np.nan)),
                "weights": weights,
                "daily_contrib": contrib,
                "total_ret": float(sum(contrib.values())),
                "hedge_weight": float(weights.get("GLD", 0.0) + weights.get("BIL", 0.0)),
                "hedge_asset": "GLD" if weights.get("GLD", 0.0) > 0 else ("BIL" if weights.get("BIL", 0.0) > 0 else "-"),
            }
        )
    return rows


def summarize_contrib(rows: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        for key, value in row["daily_contrib"].items():
            totals[key] = totals.get(key, 0.0) + float(value)
    totals["hedge_weight_avg"] = float(np.mean([row["hedge_weight"] for row in rows])) if rows else np.nan
    totals["hedge_days"] = float(sum(1 for row in rows if row["hedge_weight"] > 0))
    totals["days"] = float(len(rows))
    return totals


def overhedge_audit(log: pd.DataFrame, curves: dict[str, pd.Series], peak: pd.Timestamp, trough: pd.Timestamp) -> dict[str, Any]:
    frame = pd.DataFrame(curves).sort_index().ffill().dropna()
    rets = frame.pct_change().fillna(0.0)
    log = log.copy()
    log["date_ts"] = pd.to_datetime(log["date"])
    hedge_days = 0
    overhedge_days = 0
    total_drag = 0.0
    false_drag = 0.0
    audited: list[dict[str, Any]] = []
    for _, row in log.iterrows():
        dt = pd.Timestamp(row["date_ts"])
        if peak <= dt <= trough:
            continue
        if dt not in rets.index:
            continue
        weights = parse_weights(row.get("weights"))
        hedge_weight = weights.get("GLD", 0.0) + weights.get("BIL", 0.0)
        if hedge_weight <= 0:
            continue
        b_keys = [key for key in weights if key not in {"V6A", "GLD", "BIL"}]
        b_key = b_keys[0] if b_keys else ""
        if b_key not in rets.columns:
            continue
        risky_weight = weights.get("V6A", 0.0) + weights.get(b_key, 0.0)
        risky_ret = 0.0
        if risky_weight > 0:
            risky_ret = (
                weights.get("V6A", 0.0) * float(rets.loc[dt, "V6A"])
                + weights.get(b_key, 0.0) * float(rets.loc[dt, b_key])
            ) / risky_weight
        hedge_ret = (
            weights.get("GLD", 0.0) * float(rets.loc[dt, "GLD"])
            + weights.get("BIL", 0.0) * float(rets.loc[dt, "BIL"])
        ) / hedge_weight
        drag = hedge_weight * (hedge_ret - risky_ret)
        is_overhedge = risky_ret > hedge_ret and risky_ret > 0
        hedge_days += 1
        total_drag += drag
        if is_overhedge:
            overhedge_days += 1
            false_drag += drag
        audited.append(
            {
                "date": str(dt.date()),
                "hedge_weight": float(hedge_weight),
                "risky_ret": float(risky_ret),
                "hedge_ret": float(hedge_ret),
                "drag": float(drag),
                "overhedge": bool(is_overhedge),
            }
        )
    worst = sorted(audited, key=lambda item: item["drag"])[:10]
    return {
        "hedge_days_ex_maxdd": hedge_days,
        "overhedge_days": overhedge_days,
        "overhedge_rate": float(overhedge_days / hedge_days) if hedge_days else 0.0,
        "total_drag": float(total_drag),
        "false_drag": float(false_drag),
        "top_drag_days": worst,
    }


def fmt_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value * 100:+.2f}%"


def fmt_date(value: pd.Timestamp | None) -> str:
    if value is None or pd.isna(value):
        return "not recovered"
    return str(pd.Timestamp(value).date())


def run_v6ab_curve(curves: dict[str, pd.Series], b_key: str, start: str, end: str) -> tuple[pd.Series, pd.DataFrame]:
    return dynamic_b_sizing_equity(
        curves,
        b_key=b_key,
        b_low=0.05,
        b_mid=0.30,
        b_high=0.45,
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
        "# V6AB Defense Layer Attribution",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 回测区间：`{payload['start']} -> {payload['end']}`",
        "- 目的：验证 Deepseek 提出的“MaxDD 是否被防守层天花板锁死”假设。",
        "- 结论：本报告只做诊断，不改变 V6AB 模拟盘。",
        "",
        "## Verdict",
        "",
        f"- defense ceiling hypothesis：`{payload['verdict']['defense_ceiling_hypothesis']}`",
        f"- strategy recommendation：`{payload['verdict']['strategy_recommendation']}`",
        f"- reason：{payload['verdict']['reason']}",
        "",
        "## MaxDD Windows",
        "",
        "| candidate | maxDD | peak | trough | recovery | window return | avg hedge | hedge days | main negative contributor |",
        "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for item in payload["candidates"]:
        w = item["window"]
        c = item["contribution_summary"]
        contributors = {k: v for k, v in c.items() if k not in {"hedge_weight_avg", "hedge_days", "days"}}
        main_neg = min(contributors.items(), key=lambda kv: kv[1])[0] if contributors else "-"
        lines.append(
            f"| `{item['name']}` | {fmt_pct(w['max_dd'])} | {w['peak']} | {w['trough']} | {w['recovery']} | "
            f"{fmt_pct(item['window_stats']['return'])} | {fmt_pct(c.get('hedge_weight_avg'))} | {int(c.get('hedge_days', 0))}/{int(c.get('days', 0))} | `{main_neg}` |"
        )

    lines.extend(["", "## Contribution Summary During MaxDD Window", ""])
    for item in payload["candidates"]:
        lines.append(f"### {item['name']}")
        lines.append("")
        lines.append("| sleeve | arithmetic contribution |")
        lines.append("| --- | ---: |")
        c = item["contribution_summary"]
        for key, value in sorted(c.items()):
            if key in {"hedge_weight_avg", "hedge_days", "days"}:
                continue
            lines.append(f"| `{key}` | {fmt_pct(value)} |")
        lines.append("")

    lines.extend(
        [
            "",
            "## Overhedge Audit Outside MaxDD Window",
            "",
            "| candidate | hedge days | overhedge days | overhedge rate | total hedge drag | false hedge drag |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in payload["candidates"]:
        audit = item["overhedge_audit"]
        lines.append(
            f"| `{item['name']}` | {audit['hedge_days_ex_maxdd']} | {audit['overhedge_days']} | "
            f"{fmt_pct(audit['overhedge_rate'])} | {fmt_pct(audit['total_drag'])} | {fmt_pct(audit['false_drag'])} |"
        )
    lines.extend(["", "### Worst Hedge Drag Days", ""])
    for item in payload["candidates"]:
        lines.append(f"#### {item['name']}")
        lines.append("")
        lines.append("| date | hedge weight | risky ret | hedge ret | hedge drag |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for row in item["overhedge_audit"].get("top_drag_days", [])[:5]:
            lines.append(
                f"| {row['date']} | {fmt_pct(row['hedge_weight'])} | {fmt_pct(row['risky_ret'])} | "
                f"{fmt_pct(row['hedge_ret'])} | {fmt_pct(row['drag'])} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Interpretation",
            "",
            "- 如果三个版本的 MaxDD peak/trough 高度重合，说明 Deepseek 对“同一压力窗口”的观察成立。",
            "- 如果 MaxDD 窗口内 hedge days 很多但仍未明显降回撤，说明问题不只是防守未触发，可能是 hedge asset/weight 不够有效。",
            "- 如果主要负贡献来自 `V6A` 或 B sleeve，而 GLD/BIL 贡献为正或接近 0，则不能把回撤简单归因给三态防守层。",
            "- 如果 MaxDD 外 overhedge drag 很大，防守层优化的主要价值可能是提高年化，而不是继续压 MaxDD。",
            "- 下一步只允许做离线 defense experiment；不得直接改模拟盘 V2。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribute V6AB max drawdown to offensive sleeves and defensive overlay.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--v6a-daily", type=Path, default=DEFAULT_V6A_DAILY)
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    if not snapshots:
        raise SystemExit(f"empty PIT replay: {args.replay_json}")

    prices = bt.build_price_matrix(pit.required_tickers_for_replay(snapshots), args.start, args.end).ffill(limit=3)
    baseline_eq, _ = bridge.run_v6b(prices, bridge.BASELINE_CONFIG)
    guarded_eq, _ = pit.run_pit_v6b(prices, snapshots, bridge.BASELINE_CONFIG, mode="tier_turnover_guarded")
    qualified_eq, _ = legacy.run_guarded_v6b(
        prices,
        snapshots,
        bridge.BASELINE_CONFIG,
        policy="v2_memory_requires_broad_legacy_confirmation",
    )

    curves = {
        "V6A": load_v6a_composite(args.v6a_daily),
        "baseline_v2": baseline_eq,
        "pit_tier_turnover_guarded": guarded_eq,
        "legacy_preserve_qualified": qualified_eq,
        "GLD": benchmark_equity(prices, "US.GLD"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
    }
    candidates_raw = [
        ("baseline_v2_v6ab_dynamic_b", "baseline_v2"),
        ("pit_tier_turnover_guarded_v6ab_dynamic_b", "pit_tier_turnover_guarded"),
        ("legacy_preserve_qualified_v6ab_dynamic_b", "legacy_preserve_qualified"),
    ]
    candidates: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    for name, b_key in candidates_raw:
        eq, log = run_v6ab_curve(curves, b_key, args.start, args.end)
        window = max_drawdown_window(eq)
        rows = contribution_rows(log, curves, window["peak"], window["trough"])
        summary = summarize_contrib(rows)
        overhedge = overhedge_audit(log, curves, window["peak"], window["trough"])
        item = {
            "name": name,
            "window": {
                "max_dd": window["max_dd"],
                "peak": fmt_date(window["peak"]),
                "trough": fmt_date(window["trough"]),
                "recovery": fmt_date(window["recovery"]),
            },
            "window_stats": window_stats(eq, window["peak"], window["trough"]),
            "contribution_summary": summary,
            "overhedge_audit": overhedge,
            "sample_rows": rows[:5] + rows[-5:] if len(rows) > 10 else rows,
            "stats": bt.stats(eq),
        }
        candidates.append(item)
        windows.append(window)

    same_trough = len({fmt_date(row["trough"]) for row in windows}) == 1
    hedge_avgs = [item["contribution_summary"].get("hedge_weight_avg", 0.0) for item in candidates]
    hedge_active = all(np.isfinite(value) and value > 0.05 for value in hedge_avgs)
    if same_trough and hedge_active:
        verdict = {
            "defense_ceiling_hypothesis": "PARTIALLY_SUPPORTED",
            "strategy_recommendation": "RUN_OFFLINE_CONTINUOUS_DEFENSE_EXPERIMENT",
            "reason": "三个版本最大回撤窗口高度重合，且防守层在窗口内已触发；需要验证是 hedge asset/weight 粗糙，还是进攻 sleeve 同源暴露太强。",
        }
    elif same_trough:
        verdict = {
            "defense_ceiling_hypothesis": "WINDOW_SUPPORTED_BUT_DEFENSE_TRIGGER_NOT_PROVEN",
            "strategy_recommendation": "INSPECT_TRIGGER_RULES_BEFORE_ASSET_EXPANSION",
            "reason": "三个版本最大回撤窗口重合，但防守触发强度不足；优先检查 trigger，而不是直接加入更多防守资产。",
        }
    else:
        verdict = {
            "defense_ceiling_hypothesis": "NOT_PROVEN",
            "strategy_recommendation": "DO_NOT_CHANGE_DEFENSE_LAYER_YET",
            "reason": "三个版本最大回撤窗口不完全一致，不能把相同 MaxDD 简化为防守层天花板。",
        }

    payload = {
        "asof": args.asof,
        "start": args.start,
        "end": args.end,
        "verdict": verdict,
        "candidates": candidates,
    }
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md + "\n", encoding="utf-8")
    (REPORT_ROOT / "V6AB_Defense_Layer_Attribution_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (REPORT_ROOT / "V6AB_Defense_Layer_Attribution_LATEST.md").write_text(md + "\n", encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
