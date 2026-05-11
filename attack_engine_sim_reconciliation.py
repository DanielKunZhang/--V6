#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pandas as pd


OUT_DIR = Path("backtest_results") / "attack_engine_sim_reconciliation"
DEFAULT_ACC_ID = 19005590


def load_targets(orders_csv: Path) -> dict[str, int]:
    orders = pd.read_csv(orders_csv)
    required = {"code", "target_qty"}
    missing = required - set(orders.columns)
    if missing:
        raise ValueError(f"{orders_csv} missing columns: {sorted(missing)}")
    targets: dict[str, int] = {}
    for row in orders.to_dict("records"):
        targets[str(row["code"])] = int(float(row["target_qty"]))
    return targets


def load_expected_orders(orders_csv: Path) -> list[dict[str, Any]]:
    orders = pd.read_csv(orders_csv)
    required = {"code", "side", "preview_qty", "order_price"}
    missing = required - set(orders.columns)
    if missing:
        raise ValueError(f"{orders_csv} missing columns: {sorted(missing)}")
    expected = []
    for row in orders.to_dict("records"):
        qty = int(float(row.get("preview_qty", 0) or 0))
        if qty <= 0:
            continue
        expected.append(
            {
                "code": str(row["code"]),
                "side": str(row["side"]),
                "qty": qty,
                "price": round(float(row["order_price"]), 2),
            }
        )
    return expected


def query_orders(acc_id: int) -> pd.DataFrame:
    from futu import OpenSecTradeContext, RET_OK, SecurityFirm, TrdEnv, TrdMarket

    ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host="127.0.0.1",
        port=11111,
        security_firm=SecurityFirm.FUTUSECURITIES,
    )
    try:
        ret, data = ctx.order_list_query(trd_env=TrdEnv.SIMULATE, acc_id=acc_id, refresh_cache=True)
        if ret != RET_OK:
            raise RuntimeError(f"order_list_query failed: {data}")
        return data.copy()
    finally:
        ctx.close()


def query_positions(acc_id: int) -> pd.DataFrame:
    from futu import OpenSecTradeContext, RET_OK, SecurityFirm, TrdEnv, TrdMarket

    ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host="127.0.0.1",
        port=11111,
        security_firm=SecurityFirm.FUTUSECURITIES,
    )
    try:
        ret, data = ctx.position_list_query(trd_env=TrdEnv.SIMULATE, acc_id=acc_id, refresh_cache=True)
        if ret != RET_OK:
            raise RuntimeError(f"position_list_query failed: {data}")
        return data.copy()
    finally:
        ctx.close()


def normalize_positions(raw: pd.DataFrame) -> dict[str, int]:
    positions: dict[str, int] = {}
    if raw.empty or "code" not in raw.columns:
        return positions
    for row in raw.to_dict("records"):
        code = str(row.get("code", ""))
        qty = int(float(row.get("qty", 0) or 0))
        if qty:
            positions[code] = qty
    return positions


def normalize_orders(raw: pd.DataFrame, expected_orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if raw.empty:
        return []
    expected = {
        (row["code"], row["side"], int(row["qty"]), round(float(row["price"]), 2))
        for row in expected_orders
    }
    rows = []
    for row in raw.to_dict("records"):
        code = str(row.get("code", ""))
        side = str(row.get("trd_side", ""))
        qty = int(float(row.get("qty", 0) or 0))
        price = round(float(row.get("price", 0) or 0), 2)
        if (code, side, qty, price) not in expected:
            continue
        rows.append(
            {
                "code": code,
                "side": side,
                "status": str(row.get("order_status", "")),
                "order_id": str(row.get("order_id", "")),
                "qty": float(qty),
                "dealt_qty": float(row.get("dealt_qty", 0) or 0),
                "price": price,
                "create_time": str(row.get("create_time", "")),
                "updated_time": str(row.get("updated_time", "")),
            }
        )
    return rows


def reconcile(targets: dict[str, int], positions: dict[str, int], orders: list[dict[str, Any]]) -> dict[str, Any]:
    all_codes = sorted(set(targets) | set(positions))
    position_rows = []
    mismatches = []
    for code in all_codes:
        target = int(targets.get(code, 0))
        actual = int(positions.get(code, 0))
        ok = target == actual
        if not ok:
            mismatches.append(code)
        position_rows.append({"code": code, "target_qty": target, "actual_qty": actual, "matched": ok})

    active_statuses = {"SUBMITTED", "SUBMITTING", "WAITING_SUBMIT", "WAITING", "FILLED_PART"}
    active_orders = [row for row in orders if row["status"] in active_statuses]
    failed_orders = [row for row in orders if "FAILED" in row["status"] or "DISABLED" in row["status"]]
    filled_orders = [row for row in orders if row["status"] == "FILLED_ALL"]

    if not mismatches and not active_orders and not failed_orders:
        status = "PASS"
        reason = "positions match V6 targets and no active/failed transition orders remain"
    elif active_orders and not failed_orders:
        status = "PENDING"
        reason = "transition orders are submitted but not fully filled yet"
    elif failed_orders:
        status = "BLOCKED"
        reason = "one or more transition orders failed or were disabled"
    else:
        status = "MISMATCH"
        reason = "positions do not match V6 targets"

    return {
        "status": status,
        "reason": reason,
        "position_rows": position_rows,
        "orders": orders,
        "active_order_count": len(active_orders),
        "filled_order_count": len(filled_orders),
        "failed_order_count": len(failed_orders),
        "mismatches": mismatches,
    }


def write_report(path: Path, result: dict[str, Any], orders_csv: Path, acc_id: int) -> None:
    lines = [
        "# V6 Sim Reconciliation",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Trade env: `SIMULATE`",
        f"- Account: `{acc_id}`",
        f"- Orders CSV: `{orders_csv}`",
        f"- Status: `{result['status']}`",
        f"- Reason: {result['reason']}",
        "",
        "## Position Match",
        "",
        "| code | target | actual | matched |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in result["position_rows"]:
        lines.append(f"| {row['code']} | {row['target_qty']} | {row['actual_qty']} | {row['matched']} |")

    lines.extend(
        [
            "",
            "## Transition Orders",
            "",
            "| code | side | status | qty | dealt | price | order_id | updated |",
            "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in result["orders"]:
        lines.append(
            f"| {row['code']} | {row['side']} | {row['status']} | {row['qty']:.0f} | "
            f"{row['dealt_qty']:.0f} | {row['price']:.2f} | {row['order_id']} | {row['updated_time']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile V6 simulate transition orders against target positions.")
    parser.add_argument("--orders-csv", required=True)
    parser.add_argument("--tag", default="latest")
    parser.add_argument("--acc-id", type=int, default=DEFAULT_ACC_ID)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    orders_csv = Path(args.orders_csv)
    targets = load_targets(orders_csv)
    expected_orders = load_expected_orders(orders_csv)
    order_rows = normalize_orders(query_orders(args.acc_id), expected_orders)
    positions = normalize_positions(query_positions(args.acc_id))
    result = reconcile(targets, positions, order_rows)

    json_path = OUT_DIR / f"v6_sim_reconciliation_{args.tag}.json"
    md_path = OUT_DIR / f"v6_sim_reconciliation_{args.tag}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(md_path, result, orders_csv, args.acc_id)
    print("== V6 Sim Reconciliation ==")
    print(f"Status: {result['status']}")
    print(f"Reason: {result['reason']}")
    print(f"JSON:   {json_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
