#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


ROOT = Path(__file__).parent
OUT_DIR = ROOT / "backtest_results" / "attack_engine_release_gate"
DEFAULT_REPLAY_COMPOSITE = ROOT / "backtest_results" / "attack_engine_replay" / "attack_replay_composite_20260506_v1.csv"
DEFAULT_REPLAY_SUMMARY = ROOT / "backtest_results" / "attack_engine_replay" / "attack_replay_summary_20260506_v1.csv"
DEFAULT_LIVE_PREVIEW_ORDERS = ROOT / "backtest_results" / "attack_engine_live_preview" / "attack_live_order_preview_orders_20260506_v1.csv"
DEFAULT_LIVE_PREVIEW_QUOTES = ROOT / "backtest_results" / "attack_engine_live_preview" / "attack_live_order_preview_quotes_20260506_v1.json"
DEFAULT_LIVE_PREVIEW_ACCOUNT = ROOT / "backtest_results" / "attack_engine_live_preview" / "attack_live_order_preview_account_20260506_v1.json"


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def fmt_pct(value: Any) -> str:
    number = as_float(value)
    if math.isnan(number):
        return ""
    return f"{number:.2f}%"


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": False, "warnings": [f"missing_file:{path}"]}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "warnings": [f"json_load_error:{path}:{exc}"]}


def check(name: str, passed: bool, detail: str, severity: str = "blocker") -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "severity": severity, "detail": detail}


def latest_signal_date(summary_path: Path) -> str:
    if not summary_path.exists():
        return ""
    df = pd.read_csv(summary_path)
    if df.empty or "latest_date" not in df.columns:
        return ""
    return str(pd.to_datetime(df["latest_date"]).max().date())


def build_gate(args: argparse.Namespace) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    composite_path = Path(args.replay_composite)
    summary_path = Path(args.replay_summary)
    orders_path = Path(args.live_preview_orders)
    quotes_path = Path(args.live_preview_quotes)
    account_path = Path(args.live_preview_account)

    if composite_path.exists():
        composite = pd.read_csv(composite_path)
    else:
        composite = pd.DataFrame()
    if composite.empty:
        checks.append(check("replay_composite_exists", False, f"missing_or_empty:{composite_path}"))
        row: Dict[str, Any] = {}
    else:
        row = composite.iloc[0].to_dict()
        checks.append(check("replay_composite_exists", True, str(composite_path), "info"))

    full_ann = as_float(row.get("full_ann_ret"))
    oos_ann = as_float(row.get("oos_ann_ret"))
    full_dd = as_float(row.get("full_max_dd"))
    oos_sharpe = as_float(row.get("oos_sharpe"))
    min_equity = as_float(row.get("min_equity_pct"))
    r3 = as_float(row.get("rolling_3y_worst_ann"))

    checks.extend(
        [
            check("full_ann_gate", full_ann >= args.min_full_ann, f"{fmt_pct(full_ann)} >= {args.min_full_ann:.2f}%"),
            check("oos_ann_gate", oos_ann >= args.min_oos_ann, f"{fmt_pct(oos_ann)} >= {args.min_oos_ann:.2f}%"),
            check("drawdown_gate", full_dd >= args.max_full_dd, f"{fmt_pct(full_dd)} >= {args.max_full_dd:.2f}%"),
            check("oos_sharpe_gate", oos_sharpe >= args.min_oos_sharpe, f"{oos_sharpe:.2f} >= {args.min_oos_sharpe:.2f}"),
            check("min_equity_gate", min_equity >= args.min_equity_pct, f"{fmt_pct(min_equity)} >= {args.min_equity_pct:.2f}%"),
            check("rolling_3y_gate", r3 >= args.min_rolling_3y_ann, f"{fmt_pct(r3)} >= {args.min_rolling_3y_ann:.2f}%"),
        ]
    )

    signal_date = latest_signal_date(summary_path)
    if signal_date:
        age_days = max((pd.Timestamp(args.asof_date).normalize() - pd.Timestamp(signal_date).normalize()).days, 0)
        checks.append(
            check(
                "signal_freshness_gate",
                age_days <= args.max_signal_age_days,
                f"signal_date={signal_date}, asof={args.asof_date}, age_days={age_days}, max={args.max_signal_age_days}",
            )
        )
    else:
        checks.append(check("signal_freshness_gate", False, f"missing latest_date in {summary_path}"))

    if orders_path.exists():
        orders = pd.read_csv(orders_path)
    else:
        orders = pd.DataFrame()
    checks.append(check("live_preview_orders_exist", not orders.empty, str(orders_path)))
    if not orders.empty and "preview_order_value" in orders.columns:
        buy_notional = float(orders.loc[orders.get("side", "") == "BUY", "preview_order_value"].sum())
        executable_notional = float(orders.loc[orders.get("side", "").isin(["BUY", "SELL"]), "preview_order_value"].abs().sum())
        checks.append(
            check(
                "live_preview_has_executable_orders",
                executable_notional > 0,
                f"buy_notional={buy_notional:.2f}, executable_notional={executable_notional:.2f}",
            )
        )
        bad_order_values = int((orders.get("order_value_ok", True) == False).sum())
        checks.append(check("order_value_gate", bad_order_values == 0, f"bad_order_value_lines={bad_order_values}"))

    quotes = load_json(quotes_path)
    checks.append(check("live_quotes_gate", bool(quotes.get("ok")), f"warnings={quotes.get('warnings', [])}"))
    quote_count = len(quotes.get("quotes", {}) or {})
    checks.append(check("live_quotes_complete_gate", quote_count >= args.min_quote_count, f"quote_count={quote_count}", "blocker"))

    account = load_json(account_path)
    account_ok = bool(account.get("ok", True)) and not any(str(w).startswith("account_timeout") for w in account.get("warnings", []) or [])
    checks.append(check("live_account_gate", account_ok, f"warnings={account.get('warnings', [])}"))

    blocker_failed = [item for item in checks if item["severity"] == "blocker" and not item["passed"]]
    gate_result = "PASS" if not blocker_failed else "FAIL"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "gate_result": gate_result,
        "asof_date": args.asof_date,
        "strategy": "V6-A ATTACK_EQUAL_REPLAY",
        "checks": checks,
        "failed_blockers": blocker_failed,
        "summary": {
            "full_ann_ret": full_ann,
            "oos_ann_ret": oos_ann,
            "full_max_dd": full_dd,
            "oos_sharpe": oos_sharpe,
            "min_equity_pct": min_equity,
            "rolling_3y_worst_ann": r3,
            "latest_signal_date": signal_date,
        },
    }


def write_report(path: Path, payload: Dict[str, Any]) -> None:
    lines = [
        "# V6 Release Gate",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Strategy: `{payload['strategy']}`",
        f"- Gate result: `{payload['gate_result']}`",
        f"- As-of date: `{payload['asof_date']}`",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Checks", "", "| check | result | severity | detail |", "| --- | --- | --- | --- |"])
    for item in payload["checks"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["name"]),
                    "PASS" if item["passed"] else "FAIL",
                    str(item["severity"]),
                    str(item["detail"]).replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Decision", ""])
    if payload["gate_result"] == "PASS":
        lines.append("- V6-A is eligible for small-capital live launch preview. Manual approval is still required before placing orders.")
    else:
        lines.append("- V6-A is not ready for live launch. Failed blockers must be resolved before any real order execution.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Release gate for V6 attack engine before live launch.")
    parser.add_argument("--replay-composite", default=str(DEFAULT_REPLAY_COMPOSITE))
    parser.add_argument("--replay-summary", default=str(DEFAULT_REPLAY_SUMMARY))
    parser.add_argument("--live-preview-orders", default=str(DEFAULT_LIVE_PREVIEW_ORDERS))
    parser.add_argument("--live-preview-quotes", default=str(DEFAULT_LIVE_PREVIEW_QUOTES))
    parser.add_argument("--live-preview-account", default=str(DEFAULT_LIVE_PREVIEW_ACCOUNT))
    parser.add_argument("--asof-date", default=datetime.now().date().isoformat())
    parser.add_argument("--max-signal-age-days", type=int, default=5)
    parser.add_argument("--min-full-ann", type=float, default=25.0)
    parser.add_argument("--min-oos-ann", type=float, default=18.0)
    parser.add_argument("--max-full-dd", type=float, default=-30.0)
    parser.add_argument("--min-oos-sharpe", type=float, default=0.8)
    parser.add_argument("--min-equity-pct", type=float, default=70.0)
    parser.add_argument("--min-rolling-3y-ann", type=float, default=0.0)
    parser.add_argument("--min-quote-count", type=int, default=5)
    parser.add_argument("--tag", default="latest")
    args = parser.parse_args()

    payload = build_gate(args)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"attack_engine_release_gate_{args.tag}.json"
    md_path = OUT_DIR / f"attack_engine_release_gate_{args.tag}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(md_path, payload)
    print("== V6 Release Gate ==")
    print(f"Result: {payload['gate_result']}")
    print(f"JSON:   {json_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
