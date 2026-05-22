#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

import v6ab_pit_classifier_bridge_backtest as pit_bridge
import v6b_theme_rotation_backtest as bt


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUT_DIR = ROOT / "backtest_results" / "v6ab_legacy_preservation_trigger_review"
DEFAULT_WATCH = ROOT / "backtest_results" / "v6ab_legacy_preservation_forward_watch" / "latest.json"
DEFAULT_REPLAY = ROOT / "backtest_results" / "v6ab_daily_evolution" / "pit_replay" / "latest_pit_classifier_replay.json"

THEME_REVIEW_TICKERS = {
    "precious_metals": ["US.SLV", "US.GLD", "US.GDX"],
    "ai_optical": ["US.AAOI", "US.LITE", "US.COHR", "US.SMH", "US.SOXX"],
    "semis_ai": ["US.SMH", "US.SOXX"],
    "energy_resources": ["US.DBC"],
    "broad_beta": ["US.QQQ", "US.SPY"],
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2%}"


def returns_for(prices: pd.DataFrame, ticker: str, asof: pd.Timestamp) -> dict[str, Any]:
    if ticker not in prices.columns:
        return {"ticker": ticker, "missing": True}
    history = prices[ticker].dropna()
    if history.empty:
        return {"ticker": ticker, "missing": True}
    pos = history.index.searchsorted(asof)
    if pos >= len(history) or history.index[pos] != asof:
        return {"ticker": ticker, "missing": True}
    row: dict[str, Any] = {
        "ticker": ticker,
        "close": float(history.iloc[pos]),
        "missing": False,
    }
    for label, days in [("ret_1m", 21), ("ret_3m", 63), ("ret_6m", 126), ("ret_12m", 252)]:
        row[label] = None if pos < days else float(history.iloc[pos] / history.iloc[pos - days] - 1.0)
    row["near_3m_high"] = None
    if pos >= 63:
        high = float(history.iloc[pos - 63 : pos + 1].max())
        row["near_3m_high"] = high > 0 and float(history.iloc[pos]) / high >= 0.95
    return row


def summarize_theme(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if not row.get("missing")]
    out: dict[str, Any] = {"count": len(valid)}
    for key in ["ret_1m", "ret_3m", "ret_6m", "ret_12m"]:
        vals = [float(row[key]) for row in valid if row.get(key) is not None]
        out[f"median_{key}"] = None if not vals else float(pd.Series(vals).median())
    out["near_3m_high_count"] = int(sum(bool(row.get("near_3m_high")) for row in valid))
    return out


def verdict(protected: dict[str, Any], blocked: dict[str, Any], obs: dict[str, Any]) -> dict[str, Any]:
    protected_6m = protected.get("median_ret_6m")
    protected_3m = protected.get("median_ret_3m")
    blocked_3m = blocked.get("median_ret_3m")
    blocked_near_high = int(blocked.get("near_3m_high_count", 0) or 0)
    protected_ok = protected_6m is not None and protected_6m > 0.10
    protected_short_weak = protected_3m is not None and protected_3m < 0.0
    blocked_hot = blocked_3m is not None and blocked_3m > 0.25 and blocked_near_high >= 2
    if protected_ok and protected_short_weak and blocked_hot:
        tier = "REASONABLE_BUT_UNPROVEN"
        action = "本次保护有经济含义：legacy 主题仍有中期趋势，但短期转弱；被拦截的 AI optical 更像过热动量替换。继续 WATCH，不升级。"
    elif protected_ok:
        tier = "REASONABLE_WATCH"
        action = "保护对象仍有中期趋势，保留观察；需要后续收益验证。"
    else:
        tier = "WEAK_TRIGGER_REVIEW"
        action = "保护对象的市场证据不够强，后续若重复触发需检查 qualified 条件是否过度保护。"
    return {
        "tier": tier,
        "action": action,
        "paper_sim_action": "NO_CHANGE",
        "active_paper_sim_baseline": obs.get("active_paper_sim_baseline", "V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING"),
        "reason_codes": {
            "protected_6m_positive": protected_ok,
            "protected_3m_weak": protected_short_weak,
            "blocked_theme_hot": blocked_hot,
            "no_override": not bool(obs.get("pit_override_allowlist")),
        },
    }


def build_review(args: argparse.Namespace) -> dict[str, Any]:
    watch = load_json(args.watch_json)
    obs = watch.get("latest_observation", {}) if isinstance(watch.get("latest_observation"), dict) else {}
    if not obs:
        raise SystemExit(f"missing latest_observation: {args.watch_json}")
    decision_date = pd.Timestamp(obs["decision_date"])
    replay = load_json(args.replay_json)
    snapshots = sorted(replay.get("snapshots", []), key=lambda row: row["asof"])
    tickers = set()
    for theme in set(obs.get("legacy_preserved_themes", []) + obs.get("blocked_theme_ids", [])):
        tickers.update(THEME_REVIEW_TICKERS.get(theme, []))
    for group in ["semis_ai", "energy_resources", "broad_beta"]:
        tickers.update(THEME_REVIEW_TICKERS[group])
    tickers.update(pit_bridge.required_tickers_for_replay(snapshots))
    prices = bt.build_price_matrix(sorted(tickers), args.start, args.end).ffill(limit=3)
    theme_rows = {}
    theme_summary = {}
    for theme in sorted(set(obs.get("legacy_preserved_themes", []) + obs.get("blocked_theme_ids", []))):
        rows = [returns_for(prices, ticker, decision_date) for ticker in THEME_REVIEW_TICKERS.get(theme, [])]
        theme_rows[theme] = rows
        theme_summary[theme] = summarize_theme(rows)
    preserved_theme = (obs.get("legacy_preserved_themes") or [""])[0]
    blocked_theme = (obs.get("blocked_theme_ids") or [""])[0]
    decision = verdict(theme_summary.get(preserved_theme, {}), theme_summary.get(blocked_theme, {}), obs)
    return {
        "asof": args.asof,
        "decision_date": str(decision_date.date()),
        "watch_json": str(args.watch_json),
        "review_scope": "single_forward_watch_trigger",
        "observation": obs,
        "theme_rows": theme_rows,
        "theme_summary": theme_summary,
        "decision": decision,
    }


def render_md(payload: dict[str, Any]) -> str:
    obs = payload["observation"]
    decision = payload["decision"]
    lines = [
        "# V6AB Legacy Preservation Trigger Review",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 决策截面：`{payload['decision_date']}`",
        f"- review tier：`{decision['tier']}`",
        f"- action：{decision['action']}",
        f"- 模拟盘动作：`{decision['paper_sim_action']}`，继续 `{decision['active_paper_sim_baseline']}`。",
        "",
        "## Trigger",
        "",
        f"- preserved：`{', '.join(obs.get('legacy_preserved_themes', [])) or '-'}`",
        f"- blocked replacement：`{', '.join(obs.get('blocked_replacements', [])) or '-'}`",
        f"- PIT boost allowlist：`{', '.join(obs.get('pit_boost_allowlist', [])) or '-'}`",
        f"- PIT override allowlist：`{', '.join(obs.get('pit_override_allowlist', [])) or '-'}`",
        "",
        "## Theme Price Evidence",
        "",
        "| theme | ticker | 1m | 3m | 6m | 12m | near 3m high |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for theme, rows in payload.get("theme_rows", {}).items():
        for row in rows:
            if row.get("missing"):
                lines.append(f"| `{theme}` | `{row.get('ticker')}` | n/a | n/a | n/a | n/a | n/a |")
                continue
            lines.append(
                f"| `{theme}` | `{row.get('ticker')}` | {fmt_pct(row.get('ret_1m'))} | "
                f"{fmt_pct(row.get('ret_3m'))} | {fmt_pct(row.get('ret_6m'))} | "
                f"{fmt_pct(row.get('ret_12m'))} | {row.get('near_3m_high')} |"
            )
    lines += [
        "",
        "## Interpretation",
        "",
        "- `precious_metals` 的中长期价格证据仍存在，尤其 `SLV` 6-12 个月表现强；但近 1-3 个月已回落，不能把它解读为短期确定赢家。",
        "- 被拦截的 `ai_optical` 表达由 `AAOI/LITE/COHR` 等高动量个股驱动，3-12 个月涨幅极端，且 PIT 没有 OVERRIDE 证据。",
        "- 因此本次保护合理但未被 forward 收益证明；继续 WATCH，不能替换 V2，也不能把 qualified preservation 升为 paper sim。",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review the latest V6AB legacy preservation forward WATCH trigger.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--watch-json", type=Path, default=DEFAULT_WATCH)
    parser.add_argument("--replay-json", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_review(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Legacy_Preservation_Trigger_Review_LATEST.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "V6AB_Legacy_Preservation_Trigger_Review_LATEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
