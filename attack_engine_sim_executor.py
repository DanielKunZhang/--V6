#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

from attack_engine_live_order_preview import (
    DEFAULT_FUTU_HOME_DIR,
    V3_REPO,
    _account_worker,
    _quote_worker,
    latest_weights_by_candidate,
    composite_equal_weights,
    normalize_code,
    positive_first,
    run_worker_with_timeout,
    scale_weights,
)


ROOT = Path(__file__).parent
OUT_DIR = ROOT / "backtest_results" / "attack_engine_sim_executor"
DEFAULT_DAILY = ROOT / "backtest_results" / "attack_engine_replay" / "attack_replay_daily_20260506_live_refreshed.csv"
DEFAULT_STRATEGY_NAME = "V6-A ATTACK_EQUAL_REPLAY"


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def current_us_positions(account_snapshot: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in account_snapshot.get("positions", []) or []:
        code = normalize_code(row.get("code"))
        if not code.startswith("US."):
            continue
        qty = as_float(row.get("qty"), 0.0)
        if abs(qty - round(qty)) < 1e-9 and qty > 0:
            out[code] = out.get(code, 0) + int(round(qty))
    return out


def load_managed_state(path: Path, *, strategy_name: str) -> Dict[str, Any]:
    if not path.exists():
        return {
            "strategy": strategy_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": "",
            "positions": {},
            "pending_orders": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if str(payload.get("strategy", "")) != strategy_name:
        raise SystemExit(f"managed state strategy mismatch: {payload.get('strategy')} != {strategy_name}")
    payload.setdefault("positions", {})
    payload.setdefault("pending_orders", [])
    return payload


def write_managed_state(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def current_managed_positions(path: Path, *, strategy_name: str) -> Dict[str, int]:
    state = load_managed_state(path, strategy_name=strategy_name)
    positions: Dict[str, int] = {}
    for code, qty in dict(state.get("positions", {}) or {}).items():
        norm = normalize_code(code)
        value = as_float(qty, 0.0)
        if value > 0:
            positions[norm] = int(math.floor(value))
    return positions


def build_target_qty(
    weights: Dict[str, float],
    quotes: Dict[str, Any],
    strategy_capital: float,
    max_gross: float,
) -> Dict[str, int]:
    scaled = scale_weights(weights, max_gross)
    targets: Dict[str, int] = {}
    for code, weight in sorted(scaled.items()):
        if code == "CASH" or weight <= 0:
            continue
        quote = quotes.get(code, {})
        price = positive_first(quote.get("ask"), quote.get("last"), quote.get("mid"))
        if price <= 0:
            targets[code] = 0
        else:
            targets[code] = int(math.floor(strategy_capital * float(weight) / price))
    return targets


def build_transition_orders(
    *,
    account_snapshot: Dict[str, Any],
    weights: Dict[str, float],
    quotes: Dict[str, Any],
    strategy_capital: float,
    max_gross: float,
    max_order_value: float,
    liquidate_non_target_us_positions: bool,
    current_positions_override: Dict[str, int] | None = None,
) -> pd.DataFrame:
    current = dict(current_positions_override) if current_positions_override is not None else current_us_positions(account_snapshot)
    target = build_target_qty(weights, quotes, strategy_capital, max_gross)
    codes = set(target)
    if liquidate_non_target_us_positions:
        codes.update(current)

    rows = []
    for code in sorted(codes):
        current_qty = int(current.get(code, 0))
        target_qty = int(target.get(code, 0))
        delta = target_qty - current_qty
        if delta == 0:
            side = "HOLD"
        else:
            side = "BUY" if delta > 0 else "SELL"
        quote = quotes.get(code, {})
        order_price = positive_first(quote.get("ask") if side == "BUY" else quote.get("bid"), quote.get("last"), quote.get("mid"))
        preview_qty = abs(delta)
        preview_value = preview_qty * order_price
        if max_order_value > 0 and preview_value > max_order_value and order_price > 0:
            preview_qty = int(math.floor(max_order_value / order_price))
            preview_value = preview_qty * order_price
        rows.append(
            {
                "code": code,
                "side": "HOLD" if preview_qty == 0 else side,
                "current_qty": current_qty,
                "target_qty": target_qty,
                "delta_qty": delta,
                "preview_qty": preview_qty,
                "order_price": round(float(order_price), 4),
                "preview_order_value": round(float(preview_value), 2),
                "bid": round(as_float(quote.get("bid"), 0.0), 4),
                "ask": round(as_float(quote.get("ask"), 0.0), 4),
                "last": round(as_float(quote.get("last"), 0.0), 4),
                "update_time": quote.get("update_time", ""),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        side_rank = {"SELL": 0, "BUY": 1, "HOLD": 2}
        out["_side_rank"] = out["side"].map(side_rank).fillna(9)
        out = out.sort_values(["_side_rank", "code"]).drop(columns=["_side_rank"]).reset_index(drop=True)
    return out


def place_sim_orders(orders: pd.DataFrame, *, host: str, port: int, acc_id: str, home_dir: Path) -> List[Dict[str, Any]]:
    account_mod = load_module("v6_sim_futu_account_snapshot", V3_REPO / "futu_account_snapshot.py")
    account_mod.ensure_futu_home(home_dir)
    from futu import OpenSecTradeContext, OrderType, RET_OK, TrdEnv, TrdSide

    ctx = OpenSecTradeContext(
        host=host,
        port=port,
        filter_trdmarket="US",
        security_firm="FUTUSECURITIES",
    )
    results: List[Dict[str, Any]] = []
    try:
        for _, row in orders.iterrows():
            if row["side"] not in {"BUY", "SELL"} or int(row["preview_qty"]) <= 0:
                continue
            trd_side = TrdSide.BUY if row["side"] == "BUY" else TrdSide.SELL
            ret, data = ctx.place_order(
                code=str(row["code"]),
                price=float(row["order_price"]),
                qty=int(row["preview_qty"]),
                trd_side=trd_side,
                order_type=OrderType.NORMAL,
                adjust_limit=0,
                trd_env=TrdEnv.SIMULATE,
                acc_id=int(acc_id),
            )
            results.append(
                {
                    "code": str(row["code"]),
                    "side": str(row["side"]),
                    "qty": int(row["preview_qty"]),
                    "price": float(row["order_price"]),
                    "ok": bool(ret == RET_OK),
                    "detail": data.to_dict("records") if ret == RET_OK and hasattr(data, "to_dict") else str(data),
                }
            )
    finally:
        ctx.close()
    return results


def order_id_from_detail(result: Dict[str, Any]) -> str:
    detail = result.get("detail", [])
    if isinstance(detail, list) and detail:
        return str(detail[0].get("order_id", ""))
    return ""


def validate_sells_against_managed_state(orders: pd.DataFrame, state: Dict[str, Any]) -> None:
    positions = state.get("positions", {}) if isinstance(state.get("positions"), dict) else {}
    for _, row in orders.iterrows():
        if str(row["side"]).upper() != "SELL":
            continue
        code = normalize_code(row["code"])
        sell_qty = float(row["preview_qty"])
        managed_qty = float(positions.get(code, 0.0))
        if sell_qty > managed_qty + 1e-9:
            raise SystemExit(f"refuse to sell unmanaged V6 SIM shares: {code} sell={sell_qty} managed={managed_qty}")


def update_managed_state_with_results(
    path: Path,
    *,
    strategy_name: str,
    orders: pd.DataFrame,
    results: List[Dict[str, Any]],
    execute: bool,
) -> Dict[str, Any]:
    state = load_managed_state(path, strategy_name=strategy_name)
    validate_sells_against_managed_state(orders, state)
    if not execute:
        return state

    pending = list(state.get("pending_orders", []) or [])
    for result in results:
        if not result.get("ok"):
            continue
        pending.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "code": normalize_code(result.get("code")),
                "side": str(result.get("side", "")).upper(),
                "qty": int(float(result.get("qty", 0))),
                "limit_price": float(result.get("price", 0.0)),
                "ok": bool(result.get("ok", False)),
                "order_id": order_id_from_detail(result),
                "status": "SUBMITTED_NEEDS_RECONCILIATION" if result.get("ok") else "SUBMIT_FAILED",
            }
        )
    state["pending_orders"] = pending
    write_managed_state(path, state)
    return state


def write_report(path: Path, orders: pd.DataFrame, results: List[Dict[str, Any]], execute: bool) -> None:
    lines = [
        "# V6 Sim Executor",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Mode: `{'EXECUTE_SIMULATE' if execute else 'PLAN_ONLY'}`",
        "- Trade env: `SIMULATE`",
        "",
        "## Orders",
        "",
        "| code | side | current | target | qty | price | value | bid/ask |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in orders.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["code"]),
                    str(row["side"]),
                    str(int(row["current_qty"])),
                    str(int(row["target_qty"])),
                    str(int(row["preview_qty"])),
                    f"${as_float(row['order_price']):,.2f}",
                    f"${as_float(row['preview_order_value']):,.2f}",
                    f"${as_float(row['bid']):,.2f}/${as_float(row['ask']):,.2f}",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Results", "", "```json", json.dumps(results, ensure_ascii=False, indent=2, default=str), "```"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="V6 simulator transition/execution helper.")
    parser.add_argument("--daily", default=str(DEFAULT_DAILY))
    parser.add_argument("--strategy-capital", type=float, default=5000.0)
    parser.add_argument("--max-gross", type=float, default=1.0)
    parser.add_argument("--max-order-value", type=float, default=5000.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--sim-acc-id", default="19005590")
    parser.add_argument("--home-dir", default=str(DEFAULT_FUTU_HOME_DIR))
    parser.add_argument("--quote-timeout-sec", type=float, default=12.0)
    parser.add_argument("--account-timeout-sec", type=float, default=12.0)
    parser.add_argument("--liquidate-non-target-us-positions", action="store_true")
    parser.add_argument("--net-managed-positions", action="store_true")
    parser.add_argument("--managed-positions-state", default="")
    parser.add_argument("--strategy-name", default=DEFAULT_STRATEGY_NAME)
    parser.add_argument("--update-managed-state", action="store_true")
    parser.add_argument("--execute-sim", action="store_true")
    parser.add_argument("--tag", default="latest")
    args = parser.parse_args()

    managed_state_path = Path(args.managed_positions_state) if args.managed_positions_state else None
    managed_state = None
    current_override = None
    if args.net_managed_positions:
        if managed_state_path is None:
            raise SystemExit("--net-managed-positions requires --managed-positions-state")
        managed_state = load_managed_state(managed_state_path, strategy_name=args.strategy_name)
        current_override = current_managed_positions(managed_state_path, strategy_name=args.strategy_name)

    latest = latest_weights_by_candidate(Path(args.daily))
    weights = composite_equal_weights(latest)
    quote_codes = sorted({code for code in weights if code != "CASH"} | {"US.AMZN", "US.AVGO", "US.SOXX"})
    quotes = run_worker_with_timeout(
        _quote_worker,
        {"tickers": quote_codes, "host": args.host, "port": args.port, "home_dir": args.home_dir},
        args.quote_timeout_sec,
        {
            "ok": False,
            "quotes": {},
            "warnings": [f"quote_timeout:{args.quote_timeout_sec:.0f}s"],
            "snapshot_time": "",
        },
    )
    if not quotes.get("ok"):
        raise SystemExit(f"quote fetch failed: {quotes.get('warnings')}")
    account = run_worker_with_timeout(
        _account_worker,
        {
            "host": args.host,
            "port": args.port,
            "acc_id": args.sim_acc_id,
            "trd_env": "SIMULATE",
            "home_dir": args.home_dir,
        },
        args.account_timeout_sec,
        {
            "ok": False,
            "warnings": [f"account_timeout:{args.account_timeout_sec:.0f}s"],
            "positions": [],
            "capital": {},
            "account": {},
        },
    )
    if account.get("warnings"):
        raise SystemExit(f"account warnings: {account.get('warnings')}")

    orders = build_transition_orders(
        account_snapshot=account,
        weights=weights,
        quotes=quotes.get("quotes", {}),
        strategy_capital=args.strategy_capital,
        max_gross=args.max_gross,
        max_order_value=args.max_order_value,
        liquidate_non_target_us_positions=args.liquidate_non_target_us_positions,
        current_positions_override=current_override,
    )
    if managed_state is not None:
        validate_sells_against_managed_state(orders, managed_state)
    results = (
        place_sim_orders(orders, host=args.host, port=args.port, acc_id=args.sim_acc_id, home_dir=Path(args.home_dir))
        if args.execute_sim
        else []
    )
    if managed_state_path is not None and args.update_managed_state:
        update_managed_state_with_results(
            managed_state_path,
            strategy_name=args.strategy_name,
            orders=orders,
            results=results,
            execute=bool(args.execute_sim),
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    orders_path = OUT_DIR / f"v6_sim_orders_{args.tag}.csv"
    results_path = OUT_DIR / f"v6_sim_results_{args.tag}.json"
    report_path = OUT_DIR / f"v6_sim_report_{args.tag}.md"
    orders.to_csv(orders_path, index=False)
    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_report(report_path, orders, results, args.execute_sim)
    print("== V6 Sim Executor ==")
    print(f"Mode:    {'EXECUTE_SIMULATE' if args.execute_sim else 'PLAN_ONLY'}")
    print(f"Orders:  {orders_path}")
    print(f"Results: {results_path}")
    print(f"Report:  {report_path}")


if __name__ == "__main__":
    main()
