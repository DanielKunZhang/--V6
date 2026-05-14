#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import attack_engine_live_order_preview as preview


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "backtest_results" / "v6a_cutover"
DEFAULT_DAILY = ROOT / "backtest_results" / "v6a_core_replay" / "v6a_core_replay_daily_20260514_bridge_refresh_v3_v6a_core_balanced.csv"
DEFAULT_MANAGED_STATE = ROOT / "backtest_results" / "v6a_state" / "v6a_managed_positions_real_281756481449956811.json"
DEFAULT_ACCOUNT_FALLBACK = ROOT / "backtest_results" / "attack_engine_live_preview" / "attack_live_order_preview_account_20260514_balanced_cutover_preview_v3.json"


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def fmt_usd(value: Any) -> str:
    number = as_float(value, math.nan)
    if math.isnan(number):
        return ""
    return f"${number:,.2f}"


def fmt_pct(value: Any) -> str:
    number = as_float(value, math.nan)
    if math.isnan(number):
        return ""
    return f"{number:.2f}%"


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def load_managed_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"strategy": "", "positions": {}, "pending_orders": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("positions", {})
    payload.setdefault("pending_orders", [])
    return payload


def latest_target_weights(daily_path: Path) -> tuple[str, str, dict[str, float]]:
    daily = pd.read_csv(daily_path)
    if daily.empty:
        raise RuntimeError(f"empty daily replay file: {daily_path}")
    daily["date"] = pd.to_datetime(daily["date"])
    row = daily.sort_values("date").iloc[-1]
    weights = preview.parse_weights(str(row["weights_json"]))
    signal_date = pd.Timestamp(row["date"]).date().isoformat()
    candidate_label = str(row.get("candidate_label") or row.get("candidate_id") or "")
    return signal_date, candidate_label, preview.scale_weights(weights, 1.0)


def visible_account_qty(account_snapshot: dict[str, Any], tickers: set[str]) -> dict[str, float]:
    out = {ticker: 0.0 for ticker in tickers}
    for row in account_snapshot.get("positions", []) or []:
        code = normalize_code(row.get("code"))
        if code in out:
            out[code] += as_float(row.get("qty"), 0.0)
    return out


def snapshot_price_by_code(account_snapshot: dict[str, Any]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for row in account_snapshot.get("positions", []) or []:
        code = normalize_code(row.get("code"))
        price = preview.positive_first(row.get("current_price"), row.get("last_price"), row.get("nominal_price"))
        if code and price > 0:
            prices[code] = float(price)
    return prices


def build_rows(
    *,
    weights: dict[str, float],
    managed_positions: dict[str, Any],
    visible_positions: dict[str, float],
    quotes: dict[str, Any],
    snapshot_prices: dict[str, float],
    strategy_capital: float,
) -> list[dict[str, Any]]:
    managed = {normalize_code(key): as_float(value, 0.0) for key, value in managed_positions.items()}
    target_tickers = {ticker for ticker in weights if ticker != "CASH"}
    managed_tickers = {ticker for ticker, qty in managed.items() if qty > 0}
    universe = sorted(target_tickers | managed_tickers)
    rows: list[dict[str, Any]] = []
    for ticker in universe:
        quote = dict(quotes.get(ticker, {}) or {})
        price = preview.positive_first(quote.get("ask"), quote.get("last"), quote.get("mid"), snapshot_prices.get(ticker))
        target_weight = as_float(weights.get(ticker), 0.0)
        target_value = strategy_capital * target_weight
        target_qty = int(math.floor(target_value / price)) if price > 0 and target_value > 0 else 0
        managed_qty = int(round(managed.get(ticker, 0.0)))
        visible_qty = int(round(visible_positions.get(ticker, 0.0)))
        transfer_qty = min(managed_qty, target_qty) if managed_qty > 0 and target_qty > 0 else 0
        buy_qty = max(target_qty - managed_qty, 0)
        sell_qty = max(managed_qty - target_qty, 0)
        status = "FLAT"
        if managed_qty > 0 and target_qty > 0:
            status = "OVERLAP"
        elif managed_qty > 0:
            status = "EXIT_ONLY"
        elif target_qty > 0:
            status = "ENTRY_ONLY"
        rows.append(
            {
                "ticker": ticker,
                "status": status,
                "target_weight_pct": round(target_weight * 100.0, 4),
                "reference_price": round(price, 4),
                "managed_qty": managed_qty,
                "visible_account_qty": visible_qty,
                "target_qty": target_qty,
                "ownership_transfer_qty": transfer_qty,
                "buy_qty": buy_qty,
                "sell_qty": sell_qty,
                "target_value_usd": round(target_value, 2),
                "quote_time": str(quote.get("update_time", "")),
            }
        )
    return rows


def write_markdown(
    path: Path,
    *,
    signal_date: str,
    candidate_label: str,
    managed_state_path: Path,
    account_snapshot: dict[str, Any],
    quote_snapshot: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    transfer_only = [row for row in rows if row["ownership_transfer_qty"] > 0 and row["buy_qty"] == 0 and row["sell_qty"] == 0]
    transfer_plus_buy = [row for row in rows if row["ownership_transfer_qty"] > 0 and row["buy_qty"] > 0]
    transfer_plus_sell = [row for row in rows if row["ownership_transfer_qty"] > 0 and row["sell_qty"] > 0]
    buy_only = [row for row in rows if row["ownership_transfer_qty"] == 0 and row["buy_qty"] > 0]
    sell_only = [row for row in rows if row["ownership_transfer_qty"] == 0 and row["sell_qty"] > 0]

    def section(title: str, section_rows: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {title}", "", "| ticker | managed | target | transfer | buy | sell | price | target value |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        if not section_rows:
            lines.append("| — | 0 | 0 | 0 | 0 | 0 | — | — |")
        else:
            for row in section_rows:
                lines.append(
                    f"| {row['ticker']} | {row['managed_qty']} | {row['target_qty']} | {row['ownership_transfer_qty']} | "
                    f"{row['buy_qty']} | {row['sell_qty']} | {fmt_usd(row['reference_price'])} | {fmt_usd(row['target_value_usd'])} |"
                )
        lines.extend([""])
        return lines

    lines = [
        "# V6-A Balanced Challenger Migration Diff",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Candidate: `{candidate_label}`",
        f"- Signal date: `{signal_date}`",
        f"- Managed state: `{rel(managed_state_path)}`",
        f"- Account snapshot time: `{account_snapshot.get('timestamp', '')}`",
        f"- Quote snapshot time: `{quote_snapshot.get('snapshot_time', '')}`",
        f"- Managed strategy label: `{load_managed_state(managed_state_path).get('strategy', '')}`",
        "",
        "## Interpretation",
        "",
        "- `ownership_transfer_only` means the old V6-A sleeve already holds the name and the balanced challenger also wants it.",
        "- `buy` means incremental shares needed after transfer.",
        "- `sell` means old managed shares that the balanced challenger would no longer keep.",
        "- This report is preview evidence only; it does not place orders.",
        "",
    ]
    lines.extend(section("Ownership Transfer Only", transfer_only))
    lines.extend(section("Ownership Transfer + Incremental Buy", transfer_plus_buy))
    lines.extend(section("Ownership Transfer + Trim Sell", transfer_plus_sell))
    lines.extend(section("Buy Only", buy_only))
    lines.extend(section("Sell Only", sell_only))
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build migration diff evidence for V6-A balanced challenger cutover.")
    parser.add_argument("--daily", default=str(DEFAULT_DAILY))
    parser.add_argument("--managed-positions-state", default=str(DEFAULT_MANAGED_STATE))
    parser.add_argument("--strategy-capital", type=float, default=5000.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--acc-id", default="281756481449956811")
    parser.add_argument("--trd-env", default="REAL")
    parser.add_argument("--home-dir", default=str(ROOT / ".tmp_futu_home"))
    parser.add_argument("--account-snapshot-fallback", default=str(DEFAULT_ACCOUNT_FALLBACK))
    parser.add_argument("--quote-timeout-sec", type=float, default=12.0)
    parser.add_argument("--account-timeout-sec", type=float, default=12.0)
    parser.add_argument("--tag", default="latest")
    args = parser.parse_args()

    daily_path = Path(args.daily)
    managed_state_path = Path(args.managed_positions_state)
    managed_state = load_managed_state(managed_state_path)
    signal_date, candidate_label, weights = latest_target_weights(daily_path)
    managed_positions = managed_state.get("positions", {}) if isinstance(managed_state.get("positions"), dict) else {}

    target_tickers = {ticker for ticker in weights if ticker != "CASH"}
    managed_tickers = {normalize_code(key) for key, value in managed_positions.items() if as_float(value, 0.0) > 0}
    tickers = sorted(target_tickers | managed_tickers)

    quote_snapshot = preview.run_worker_with_timeout(
        preview._quote_worker,
        {"tickers": tickers, "host": args.host, "port": args.port, "home_dir": args.home_dir},
        args.quote_timeout_sec,
        {"ok": False, "quotes": {}, "warnings": [f"quote_timeout:{args.quote_timeout_sec:.0f}s"], "snapshot_time": ""},
    )
    account_snapshot = preview.run_worker_with_timeout(
        preview._account_worker,
        {"host": args.host, "port": args.port, "acc_id": args.acc_id, "trd_env": args.trd_env, "home_dir": args.home_dir},
        args.account_timeout_sec,
        {"ok": False, "warnings": [f"account_timeout:{args.account_timeout_sec:.0f}s"], "positions": [], "capital": {}, "account": {}},
    )
    fallback_path = Path(args.account_snapshot_fallback)
    if (not account_snapshot.get("positions")) and fallback_path.exists():
        fallback_snapshot = json.loads(fallback_path.read_text(encoding="utf-8"))
        fallback_snapshot.setdefault("warnings", [])
        fallback_snapshot["warnings"] = list(account_snapshot.get("warnings", [])) + ["using_account_snapshot_fallback"]
        account_snapshot = fallback_snapshot

    visible_positions = visible_account_qty(account_snapshot, set(tickers))
    snapshot_prices = snapshot_price_by_code(account_snapshot)
    rows = build_rows(
        weights=weights,
        managed_positions=managed_positions,
        visible_positions=visible_positions,
        quotes=quote_snapshot.get("quotes", {}) or {},
        snapshot_prices=snapshot_prices,
        strategy_capital=args.strategy_capital,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"v6a_cutover_migration_diff_{args.tag}.json"
    md_path = OUT_DIR / f"v6a_cutover_migration_diff_{args.tag}.md"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_label": candidate_label,
        "signal_date": signal_date,
        "managed_state_path": rel(managed_state_path),
        "account_snapshot_time": account_snapshot.get("timestamp", ""),
        "quote_snapshot_time": quote_snapshot.get("snapshot_time", ""),
        "rows": rows,
        "account_warnings": account_snapshot.get("warnings", []),
        "quote_warnings": quote_snapshot.get("warnings", []),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(
        md_path,
        signal_date=signal_date,
        candidate_label=candidate_label,
        managed_state_path=managed_state_path,
        account_snapshot=account_snapshot,
        quote_snapshot=quote_snapshot,
        rows=rows,
    )
    print("== V6-A Cutover Migration Diff ==")
    print(f"JSON:   {json_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
