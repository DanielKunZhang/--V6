#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from attack_engine_live_order_preview import (
    DEFAULT_FUTU_HOME_DIR,
    _account_worker,
    _quote_worker,
    composite_equal_weights,
    latest_weights_by_candidate,
    normalize_code,
    run_worker_with_timeout,
)
from attack_engine_sim_executor import (
    build_transition_orders,
    check_sim_trade_ready,
    load_managed_state,
    place_sim_orders,
    resolve_sim_acc_id,
    update_managed_state_with_results,
    validate_sells_against_managed_state,
    write_report,
)
from v6ab_sleeve_blend_backtest import V6B_CONFIGS, benchmark_equity, dynamic_b_sizing_equity
from v6b_theme_rotation_backtest import build_price_matrix, run_strategy


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "v6ab_sim_executor"
DEFAULT_CONFIG = ROOT / "v6_strategy_lab" / "configs" / "v6ab_sim_candidate_v2.json"
DEFAULT_V6A_DAILY = ROOT / "backtest_results" / "attack_engine_replay" / "attack_replay_daily_20260520_live_refreshed.csv"
DEFAULT_STATE_DIR = ROOT / "backtest_results" / "v6a_state"


PRICE_TICKERS = [
    "US.SPY",
    "US.QQQ",
    "US.BIL",
    "US.IEF",
    "US.GLD",
    "US.VTV",
    "US.BRK.B",
    "US.IWM",
    "US.XLK",
    "US.IGV",
    "US.FDN",
    "US.ARKK",
    "US.SMH",
    "US.SOXX",
    "US.XLV",
    "US.XBI",
    "US.XLE",
    "US.XOP",
    "US.DBC",
    "US.SLV",
    "US.GDX",
    "US.XLF",
    "US.KRE",
    "US.XLI",
    "US.XLU",
    "US.XLY",
    "US.AMZN",
    "US.MSFT",
    "US.GOOGL",
    "US.META",
    "US.TSLA",
    "US.NFLX",
    "US.NVDA",
    "US.AVGO",
    "US.AMD",
    "US.ANET",
    "US.TSM",
    "US.MU",
    "US.WDC",
    "US.AMKR",
    "US.COHR",
    "US.AAOI",
    "US.LITE",
    "US.MRVL",
    "US.NOK",
    "US.LLY",
    "US.JPM",
    "US.ROK",
    "US.ETN",
    "US.HON",
    "US.IR",
    "US.TER",
]


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def clean_weights(weights: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value), 8) for key, value in sorted(weights.items()) if abs(float(value)) > 1e-10}


def normalize_weight_sum(weights: dict[str, float]) -> dict[str, float]:
    total = sum(float(value) for value in weights.values())
    if total <= 0:
        return {"CASH": 1.0}
    return {key: float(value) / total for key, value in weights.items()}


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_v6a_weights(path: Path) -> tuple[str, dict[str, float]]:
    latest = latest_weights_by_candidate(path)
    signal_date = str(latest["signal_date"].max())
    return signal_date, composite_equal_weights(latest)


def latest_v6b_and_overlay_weights(config: dict[str, Any], start: str, end: str) -> tuple[str, dict[str, float], dict[str, Any]]:
    prices = build_price_matrix(PRICE_TICKERS, start, end).ffill(limit=3)
    b_name = "v6b_guarded_top3_90"
    b_eq, b_decisions = run_strategy(prices, **V6B_CONFIGS[b_name])
    curves = {
        "V6A": benchmark_equity(prices, "US.QQQ"),
        "GLD": benchmark_equity(prices, "US.GLD"),
        "BIL": benchmark_equity(prices, "US.BIL"),
        "SPY": benchmark_equity(prices, "US.SPY"),
        "QQQ": benchmark_equity(prices, "US.QQQ"),
        b_name: b_eq,
    }
    sizing = config["v6b_dynamic_sizing"]
    overlay = config["dynamic_overlay"]
    _, log = dynamic_b_sizing_equity(
        curves,
        b_key=b_name,
        b_low=float(sizing["low_weight"]),
        b_mid=float(sizing["default_weight"]),
        b_high=float(sizing["high_weight"]),
        b_strong_126d=0.08,
        b_weak_63d=-0.08,
        hedge_max=float(overlay["max_overlay_weight"]),
        vol_threshold=float(overlay["vol_trigger"]),
        corr_threshold=float(overlay["corr_trigger"]),
        dd_threshold=float(overlay["drawdown_trigger"]),
        start=start,
        end=end,
    )
    latest_overlay_weights = json.loads(str(log.iloc[-1]["weights"]))
    latest_b_decision = b_decisions[-1] if b_decisions else {}
    meta = {
        "date": str(log.iloc[-1]["date"]),
        "v6b_wrapper_weights": latest_overlay_weights,
        "v6b_latest_decision": latest_b_decision,
    }
    return str(log.iloc[-1]["date"]), latest_overlay_weights, meta


def build_v6ab_target_weights(config: dict[str, Any], v6a_weights: dict[str, float], wrapper_weights: dict[str, float], v6b_decision: dict[str, Any]) -> dict[str, float]:
    b_name = "v6b_guarded_top3_90"
    v6a_sleeve_weight = float(wrapper_weights.get("V6A", 0.0))
    v6b_sleeve_weight = float(wrapper_weights.get(b_name, 0.0))
    out: dict[str, float] = {}
    for ticker, weight in v6a_weights.items():
        out[ticker] = out.get(ticker, 0.0) + v6a_sleeve_weight * float(weight)
    for ticker, weight in dict(v6b_decision.get("weights", {}) or {}).items():
        if ticker == "CASH":
            out["CASH"] = out.get("CASH", 0.0) + v6b_sleeve_weight * float(weight)
        else:
            out[ticker] = out.get(ticker, 0.0) + v6b_sleeve_weight * float(weight)
    out["GLD"] = out.get("GLD", 0.0) + float(wrapper_weights.get("GLD", 0.0))
    out["BIL"] = out.get("BIL", 0.0) + float(wrapper_weights.get("BIL", 0.0))
    out["CASH"] = out.get("CASH", 0.0) + float(wrapper_weights.get("CASH", 0.0))
    return normalize_weight_sum(out)


def write_target_report(path: Path, payload: dict[str, Any]) -> None:
    weights = payload["target_weights"]
    lines = [
        "# V6AB Sim Target",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Candidate: `{payload['candidate_id']}`",
        f"- V6-A signal date: `{payload['v6a_signal_date']}`",
        f"- V6AB wrapper date: `{payload['v6ab_signal_date']}`",
        f"- Strategy capital: `${payload['strategy_capital']:,.2f}`",
        "",
        "## Target Weights",
        "",
        "| ticker | weight |",
        "| --- | ---: |",
    ]
    for ticker, weight in sorted(weights.items(), key=lambda row: row[1], reverse=True):
        lines.append(f"| `{ticker}` | {float(weight):.2%} |")
    lines.extend(["", "## Wrapper", "", "```json", json.dumps(payload["wrapper_meta"], ensure_ascii=False, indent=2, default=str), "```"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="V6AB V2 paper-sim target/order helper.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--v6a-daily", default=str(DEFAULT_V6A_DAILY))
    parser.add_argument("--start", default="2012-05-21")
    parser.add_argument("--end", default="2026-05-19")
    parser.add_argument("--strategy-capital", type=float, default=0.0)
    parser.add_argument("--max-gross", type=float, default=1.0)
    parser.add_argument("--max-order-value", type=float, default=5000.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--sim-acc-id", default="")
    parser.add_argument("--home-dir", default=str(DEFAULT_FUTU_HOME_DIR))
    parser.add_argument("--quote-timeout-sec", type=float, default=12.0)
    parser.add_argument("--account-timeout-sec", type=float, default=12.0)
    parser.add_argument("--managed-positions-state", default="")
    parser.add_argument("--liquidate-non-target-us-positions", action="store_true")
    parser.add_argument("--execute-sim", action="store_true")
    parser.add_argument("--update-managed-state", action="store_true")
    parser.add_argument("--tag", default="latest")
    args = parser.parse_args()

    if args.strategy_capital <= 0:
        raise SystemExit("--strategy-capital is required and must be > 0 for V6AB paper sim.")

    sim_acc_id = resolve_sim_acc_id(
        host=args.host,
        port=args.port,
        configured_acc_id=args.sim_acc_id,
        home_dir=Path(args.home_dir),
    )
    managed_state_path = (
        Path(args.managed_positions_state)
        if args.managed_positions_state
        else DEFAULT_STATE_DIR / f"v6ab_managed_positions_sim_{sim_acc_id}.json"
    )

    config = load_config(Path(args.config))
    v6a_signal_date, v6a_weights = latest_v6a_weights(Path(args.v6a_daily))
    v6ab_signal_date, wrapper_weights, wrapper_meta = latest_v6b_and_overlay_weights(config, args.start, args.end)
    target_weights = clean_weights(build_v6ab_target_weights(config, v6a_weights, wrapper_weights, wrapper_meta["v6b_latest_decision"]))
    tickers = sorted(ticker for ticker in target_weights if ticker != "CASH")

    quotes = run_worker_with_timeout(
        _quote_worker,
        {"tickers": tickers, "host": args.host, "port": args.port, "home_dir": args.home_dir},
        args.quote_timeout_sec,
        {"ok": False, "quotes": {}, "warnings": [f"quote_timeout:{args.quote_timeout_sec:.0f}s"], "snapshot_time": ""},
    )
    if not quotes.get("ok"):
        raise SystemExit(f"quote fetch failed: {quotes.get('warnings')}")

    account = run_worker_with_timeout(
        _account_worker,
        {"host": args.host, "port": args.port, "acc_id": sim_acc_id, "trd_env": "SIMULATE", "home_dir": args.home_dir},
        args.account_timeout_sec,
        {"ok": False, "warnings": [f"account_timeout:{args.account_timeout_sec:.0f}s"], "positions": [], "capital": {}, "account": {}},
    )
    if account.get("warnings"):
        raise SystemExit(f"account warnings: {account.get('warnings')}")

    managed_state = load_managed_state(managed_state_path, strategy_name=str(config["candidate_id"]))
    current_override = {
        normalize_code(code): int(math.floor(as_float(qty, 0.0)))
        for code, qty in dict(managed_state.get("positions", {}) or {}).items()
        if as_float(qty, 0.0) > 0
    }
    orders = build_transition_orders(
        account_snapshot=account,
        weights=target_weights,
        quotes=quotes.get("quotes", {}),
        strategy_capital=float(args.strategy_capital),
        max_gross=float(args.max_gross),
        max_order_value=float(args.max_order_value),
        liquidate_non_target_us_positions=bool(args.liquidate_non_target_us_positions),
        current_positions_override=current_override,
    )
    validate_sells_against_managed_state(orders, managed_state)
    if args.execute_sim:
        preflight = check_sim_trade_ready(host=args.host, port=args.port, acc_id=sim_acc_id, home_dir=Path(args.home_dir))
        if not preflight.get("ok"):
            raise SystemExit(f"sim trade preflight failed: {preflight.get('reason')}")
    results = (
        place_sim_orders(orders, host=args.host, port=args.port, acc_id=sim_acc_id, home_dir=Path(args.home_dir))
        if args.execute_sim
        else []
    )
    if args.update_managed_state:
        update_managed_state_with_results(
            managed_state_path,
            strategy_name=str(config["candidate_id"]),
            orders=orders,
            results=results,
            execute=bool(args.execute_sim),
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_id": config["candidate_id"],
        "strategy_capital": float(args.strategy_capital),
        "v6a_signal_date": v6a_signal_date,
        "v6ab_signal_date": v6ab_signal_date,
        "target_weights": target_weights,
        "wrapper_meta": wrapper_meta,
    }
    target_path = OUT_DIR / f"v6ab_target_{args.tag}.json"
    target_md_path = OUT_DIR / f"v6ab_target_{args.tag}.md"
    orders_path = OUT_DIR / f"v6ab_orders_{args.tag}.csv"
    results_path = OUT_DIR / f"v6ab_results_{args.tag}.json"
    report_path = OUT_DIR / f"v6ab_order_report_{args.tag}.md"
    target_path.write_text(json.dumps(target_payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    write_target_report(target_md_path, target_payload)
    orders.to_csv(orders_path, index=False)
    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_report(report_path, orders, results, bool(args.execute_sim))
    print("== V6AB Sim Executor ==")
    print(f"Mode:    {'EXECUTE_SIMULATE' if args.execute_sim else 'PLAN_ONLY'}")
    print(f"Account: {sim_acc_id}")
    print(f"Target:  {target_path}")
    print(f"Orders:  {orders_path}")
    print(f"Results: {results_path}")
    print(f"Report:  {report_path}")


if __name__ == "__main__":
    main()
