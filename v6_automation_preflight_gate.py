#!/usr/bin/env python3
"""
V6 Automation Preflight Gate
按规格 2026-05-12_v6_automation_preflight_gate_spec.md 实现。

在任何自动实盘下单前运行此脚本。检查8项前置条件，输出
auto_execution_allowed 字段明确表明是否允许执行。

Kill switch 默认 enabled=true → 自动交易被阻断。
只有当 kill_switch.enabled = false 时才允许自动下单。

用法：
  python3 v6_automation_preflight_gate.py
  python3 v6_automation_preflight_gate.py --tag 20260526_morning
  python3 v6_automation_preflight_gate.py --config v6_strategy_lab/configs/v6_automation_preflight_policy_v1.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT       = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "v6_strategy_lab" / "configs" / "v6_automation_preflight_policy_v1.json"

# ── helpers ───────────────────────────────────────────────────────────────────

def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def make_check(name: str, status: str, severity: str, detail: str = "") -> dict:
    """status: PASS | FAIL | WARN | SKIP. severity: INFO | WARN | BLOCKER."""
    return {"name": name, "status": status, "severity": severity, "detail": detail}


# ── check 1: kill switch ──────────────────────────────────────────────────────

def check_kill_switch(policy: dict) -> dict:
    ks = policy.get("kill_switch", {})
    enabled = ks.get("enabled", True)
    reason  = ks.get("reason", "unset")
    updated = ks.get("updated_at", "unknown")
    if enabled:
        return make_check(
            "kill_switch",
            "FAIL", "BLOCKER",
            f"Kill switch is ON (reason={reason}, updated_at={updated}). "
            "Set kill_switch.enabled=false in policy config to allow automation."
        )
    return make_check(
        "kill_switch",
        "PASS", "BLOCKER",
        f"Kill switch is OFF (updated_at={updated})"
    )


# ── check 2: managed state validity ──────────────────────────────────────────

def check_managed_state(policy: dict) -> tuple[dict, dict | None]:
    ms_cfg    = policy.get("managed_state", {})
    state_path = ROOT / ms_cfg.get("file", "")
    expected_strategy = ms_cfg.get("expected_strategy", "V6-A ATTACK_EQUAL_REPLAY")
    allowed_prefix    = ms_cfg.get("allowed_ticker_prefix", "US.")

    if not state_path.exists():
        return make_check("managed_state_valid", "FAIL", "BLOCKER",
                          f"State file not found: {state_path}"), None

    state = read_json(state_path)
    if state is None:
        return make_check("managed_state_valid", "FAIL", "BLOCKER",
                          f"State file could not be parsed: {state_path}"), None

    errors = []
    if state.get("strategy") != expected_strategy:
        errors.append(f"strategy mismatch: expected '{expected_strategy}', got '{state.get('strategy')}'")
    if not isinstance(state.get("positions"), dict):
        errors.append("positions is not a dict")
    if not isinstance(state.get("pending_orders"), list):
        errors.append("pending_orders is not a list")
    for sym, qty in state.get("positions", {}).items():
        if not str(sym).startswith(allowed_prefix):
            errors.append(f"ticker not normalized: {sym}")
        if float(qty) < 0:
            errors.append(f"negative position qty: {sym}={qty}")

    if errors:
        return make_check("managed_state_valid", "FAIL", "BLOCKER",
                          "State file invalid: " + "; ".join(errors)), None

    return make_check("managed_state_valid", "PASS", "BLOCKER",
                      f"Strategy={state['strategy']}, positions={list(state.get('positions', {}).keys())}"
                      ), state


# ── check 3: pending orders ───────────────────────────────────────────────────

def check_pending_orders(state: dict) -> dict:
    if state is None:
        return make_check("no_pending_orders", "FAIL", "BLOCKER",
                          "Managed state unavailable — cannot check pending orders")
    pending = state.get("pending_orders", [])
    if pending:
        return make_check(
            "no_pending_orders", "FAIL", "BLOCKER",
            f"{len(pending)} pending order(s) exist before new automatic placement. "
            "Run reconciliation to clear first."
        )
    return make_check("no_pending_orders", "PASS", "BLOCKER", "No pending orders in managed state")


# ── check 4: OpenD / Futu connectivity ───────────────────────────────────────

def check_futu_connectivity(policy: dict) -> tuple[dict, dict | None]:
    futu_cfg = policy.get("futu", {})
    host     = futu_cfg.get("host", "127.0.0.1")
    port     = futu_cfg.get("port", 11111)
    acc_id   = futu_cfg.get("real_acc_id")
    symbols  = futu_cfg.get("target_symbols", [])

    try:
        from futu import OpenQuoteContext, OpenSecTradeContext, TrdEnv, TrdMarket, RET_OK

        # Quote context
        qctx = OpenQuoteContext(host=host, port=port)
        ret, snap = qctx.get_market_snapshot(symbols)
        qctx.close()
        if ret != RET_OK:
            return make_check("futu_connectivity", "FAIL", "BLOCKER",
                              f"Quote snapshot failed: {snap}"), None

        quotes = {}
        for _, row in snap.iterrows():
            bid  = float(row.get("bid_price", 0) or 0)
            ask  = float(row.get("ask_price", 0) or 0)
            last = float(row.get("last_price", 0) or 0)
            quotes[row["code"]] = {"bid": bid, "ask": ask, "last": last}

        # Trade context + account query
        tctx = OpenSecTradeContext(host=host, port=port)
        ret2, accs = tctx.get_acc_list()
        if ret2 != RET_OK:
            tctx.close()
            return make_check("futu_connectivity", "FAIL", "BLOCKER",
                              f"Account list query failed: {accs}"), None

        # Verify target account exists
        acc_ids = [str(a["acc_id"]) for a in accs.to_dict("records")]
        if acc_id and str(acc_id) not in acc_ids:
            tctx.close()
            return make_check("futu_connectivity", "FAIL", "BLOCKER",
                              f"Target account {acc_id} not found in account list: {acc_ids}"), None

        # Cash query
        ret3, info = tctx.accinfo_query(trd_env=TrdEnv.REAL, acc_id=int(acc_id), refresh_cache=True)
        tctx.close()
        if ret3 != RET_OK:
            return make_check("futu_connectivity", "FAIL", "BLOCKER",
                              f"Account info query failed: {info}"), None

        acct_info = info.to_dict("records")[0] if len(info) > 0 else {}

        return make_check(
            "futu_connectivity", "PASS", "BLOCKER",
            f"Quote + trade + account OK. {len(symbols)} symbols quoted."
        ), {"quotes": quotes, "acct_info": acct_info}

    except ImportError:
        return make_check("futu_connectivity", "FAIL", "BLOCKER",
                          "futu-api not installed"), None
    except Exception as e:
        return make_check("futu_connectivity", "FAIL", "BLOCKER",
                          f"Connectivity error: {type(e).__name__}: {e}"), None


# ── check 5: account cash / buying power ──────────────────────────────────────

def check_account_cash(
    policy: dict,
    futu_data: dict | None,
    preview_orders: list[dict],
) -> dict:
    cash_cfg = policy.get("cash", {})
    min_buffer = float(cash_cfg.get("min_cash_buffer_usd", 100))

    if futu_data is None:
        return make_check("account_cash", "FAIL", "BLOCKER",
                          "Futu data unavailable — cannot verify cash")

    acct = futu_data.get("acct_info", {})

    # For US stock buying power, prefer usd_net_cash_power (margin-aware USD buying capacity).
    # Fall back to us_cash if usd_net_cash_power is missing.
    def _to_float(v):
        try:
            return float(v) if v is not None and str(v).strip().upper() not in ("", "N/A", "NONE") else None
        except (TypeError, ValueError):
            return None

    available = _to_float(acct.get("usd_net_cash_power")) or _to_float(acct.get("us_cash"))

    # Only BUY orders consume cash (HOLD rows are no-ops)
    buy_orders = [o for o in preview_orders if str(o.get("side", "")).upper() == "BUY"]
    total_buy_notional = sum(
        float(o.get("preview_qty", o.get("qty", 0)) or 0)
        * float(o.get("order_price", o.get("price", 0)) or 0)
        for o in buy_orders
    )

    if total_buy_notional == 0:
        # No buys planned — cash check trivially passes regardless of balance
        return make_check(
            "account_cash", "PASS", "INFO",
            "No BUY orders in preview — cash check not applicable"
        )

    if available is None:
        return make_check("account_cash", "WARN", "WARN",
                          "USD buying power field unavailable in account info")

    required = total_buy_notional + min_buffer
    if available < required:
        return make_check(
            "account_cash", "FAIL", "BLOCKER",
            f"Insufficient USD buying power: available={available:.2f}, "
            f"buy_notional={total_buy_notional:.2f} + buffer={min_buffer:.2f} = {required:.2f} required. "
            "Block all automatic execution."
        )
    return make_check(
        "account_cash", "PASS", "BLOCKER",
        f"USD buying power {available:.2f} >= required {required:.2f} "
        f"(buy_notional={total_buy_notional:.2f} + buffer={min_buffer:.2f})"
    )


# ── check 6: order size limits ────────────────────────────────────────────────

def check_order_size(policy: dict, preview_orders: list[dict], state: dict | None) -> dict:
    size_cfg = policy.get("order_size", {})
    max_total = float(size_cfg.get("max_total_notional_usd", 5000))
    max_order = float(size_cfg.get("max_order_value_usd", 5000))
    min_order = float(size_cfg.get("min_order_value_usd", 25))
    allow_full_exit = size_cfg.get("allow_full_exit_below_min", True)
    managed_pos = (state or {}).get("positions", {})

    # Only validate executable orders (BUY or SELL), not HOLD rows
    exec_orders = [o for o in preview_orders if str(o.get("side", "")).upper() in ("BUY", "SELL")]

    if not exec_orders:
        return make_check("order_size_limits", "PASS", "BLOCKER",
                          "No executable orders (BUY/SELL) to validate")

    errors = []
    total_notional = 0.0
    for o in exec_orders:
        qty   = float(o.get("preview_qty", o.get("qty", 0)) or 0)
        price = float(o.get("order_price",  o.get("price", 0)) or 0)
        val   = abs(float(o.get("preview_order_value", qty * price) or 0)) if qty * price == 0 else qty * price
        total_notional += val
        sym   = o.get("ticker") or o.get("symbol", "")
        side  = str(o.get("side", "")).upper()

        if val > max_order:
            errors.append(f"{sym} {side}: order value {val:.2f} > max {max_order}")

        if val < min_order:
            # Full exit of managed position is allowed below min
            is_full_exit = (
                allow_full_exit
                and side == "SELL"
                and sym in managed_pos
                and abs(qty - float(managed_pos.get(sym, 0))) < 0.01
            )
            if not is_full_exit:
                errors.append(f"{sym} {side}: order value {val:.2f} < min {min_order} (not a full exit)")

    if total_notional > max_total:
        errors.append(f"Total notional {total_notional:.2f} > max_total {max_total}")

    if errors:
        return make_check("order_size_limits", "FAIL", "BLOCKER",
                          "Order size violation(s): " + "; ".join(errors))
    return make_check("order_size_limits", "PASS", "BLOCKER",
                      f"All {len(exec_orders)} executable order(s) within size limits "
                      f"(total_notional={total_notional:.2f})")


# ── check 7: slippage / spread guard ─────────────────────────────────────────

def check_spread(policy: dict, futu_data: dict | None, preview_orders: list[dict]) -> dict:
    slip_cfg  = policy.get("slippage", {})
    max_core  = float(slip_cfg.get("max_spread_pct_core", 0.30)) / 100
    max_etf   = float(slip_cfg.get("max_spread_pct_defensive_etf", 0.10)) / 100
    etf_list  = slip_cfg.get("defensive_etf_tickers", [])

    if futu_data is None:
        return make_check("spread_guard", "FAIL", "BLOCKER",
                          "Futu data unavailable — cannot check spreads")

    quotes = futu_data.get("quotes", {})
    if not quotes:
        return make_check("spread_guard", "WARN", "WARN",
                          "No quote data available for spread check")

    violations = []
    checked = []
    for sym, q in quotes.items():
        bid, ask = q.get("bid", 0), q.get("ask", 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else q.get("last", 0)
        if mid <= 0:
            checked.append(f"{sym}:no_mid")
            continue
        spread_pct = (ask - bid) / mid if bid > 0 and ask > 0 else None
        if spread_pct is None:
            checked.append(f"{sym}:spread_unavailable")
            continue
        limit = max_etf if sym in etf_list else max_core
        checked.append(f"{sym}:{spread_pct*100:.3f}%")
        if spread_pct > limit:
            violations.append(
                f"{sym}: spread {spread_pct*100:.3f}% > limit {limit*100:.3f}%"
            )

    if violations:
        return make_check(
            "spread_guard", "FAIL", "BLOCKER",
            "Spread exceeds threshold — block pre-trade: " + "; ".join(violations)
        )
    return make_check("spread_guard", "PASS", "BLOCKER",
                      "All spreads within threshold. Checked: " + ", ".join(checked))


# ── check 8: release gate freshness ──────────────────────────────────────────

def check_release_gate_freshness(policy: dict) -> tuple[dict, dict | None]:
    fresh_cfg  = policy.get("freshness", {})
    runs_dir   = ROOT / fresh_cfg.get("runner_runs_dir", "backtest_results/v6a_guarded_runner/runs")
    max_age    = int(fresh_cfg.get("max_signal_age_days", 7))

    if not runs_dir.exists():
        return make_check("release_gate_freshness", "FAIL", "BLOCKER",
                          f"Runner runs directory not found: {runs_dir}"), None

    # Find latest plan_only runner file (files may have a prefix like v6a_guarded_runner_)
    plan_files = [
        f for f in sorted(runs_dir.glob("*v6_daily_auto_*plan_only*.json"),
                          key=lambda f: f.stat().st_mtime, reverse=True)
    ]
    if not plan_files:
        return make_check("release_gate_freshness", "FAIL", "BLOCKER",
                          "No plan_only runner files found"), None

    latest = plan_files[0]
    runner = read_json(latest)
    if runner is None:
        return make_check("release_gate_freshness", "FAIL", "BLOCKER",
                          f"Could not parse latest runner file: {latest.name}"), None

    generated_at = runner.get("generated_at", "")
    try:
        gen_dt = datetime.fromisoformat(generated_at)
        age_days = (datetime.now() - gen_dt).days
    except Exception:
        age_days = 999

    if age_days > max_age:
        return make_check(
            "release_gate_freshness", "FAIL", "BLOCKER",
            f"Latest runner is {age_days} days old (max {max_age}). "
            f"Re-run guarded runner to get fresh signal. File: {latest.name}"
        ), runner

    # Check that the runner itself passed its release gate
    blockers = runner.get("blockers", [])
    # "no_executable_orders" is acceptable (no trades needed today)
    critical_blockers = [b for b in blockers if b not in ("no_executable_orders",)]
    if critical_blockers:
        return make_check(
            "release_gate_freshness", "FAIL", "BLOCKER",
            f"Latest runner has unresolved blocker(s): {critical_blockers}. "
            f"File: {latest.name}"
        ), runner

    return make_check(
        "release_gate_freshness", "PASS", "BLOCKER",
        f"Latest runner: {latest.name} (age={age_days}d, decision={runner.get('decision')}, "
        f"blockers={blockers})"
    ), runner


# ── check: trading session ────────────────────────────────────────────────────

def check_trading_session(policy: dict) -> dict:
    sess_cfg = policy.get("trading_session", {})
    if not sess_cfg.get("auto_execution_only_during_regular_hours", True):
        return make_check("trading_session", "PASS", "INFO",
                          "Session restriction disabled in policy")

    try:
        import zoneinfo
        tz    = zoneinfo.ZoneInfo(sess_cfg.get("timezone", "America/New_York"))
        now   = datetime.now(tz)
        start = sess_cfg.get("regular_hours_start", "09:30")
        end_s = sess_cfg.get("regular_hours_end", "16:00")
        sh, sm = [int(x) for x in start.split(":")]
        eh, em = [int(x) for x in end_s.split(":")]
        in_session = (now.weekday() < 5
                      and (now.hour, now.minute) >= (sh, sm)
                      and (now.hour, now.minute) < (eh, em))
        if not in_session:
            return make_check(
                "trading_session", "FAIL", "BLOCKER",
                f"Not in regular market hours: {now.strftime('%A %H:%M %Z')} "
                f"(session {start}–{end_s} ET weekdays only)"
            )
        return make_check("trading_session", "PASS", "INFO",
                          f"In regular market hours: {now.strftime('%A %H:%M %Z')}")
    except Exception as e:
        return make_check("trading_session", "WARN", "WARN",
                          f"Could not verify trading session: {e}")


# ── load preview orders ───────────────────────────────────────────────────────

def load_latest_preview_orders(policy: dict) -> list[dict]:
    """Load the most recent live order preview CSV."""
    try:
        import csv
        preview_dir = ROOT / "backtest_results" / "attack_engine_live_preview"
        if not preview_dir.exists():
            return []
        order_files = sorted(
            preview_dir.glob("attack_live_order_preview_orders_*.csv"),
            key=lambda f: f.stat().st_mtime, reverse=True
        )
        if not order_files:
            return []
        latest = order_files[0]
        orders = []
        with open(latest, encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                orders.append(dict(row))
        return orders
    except Exception:
        return []


# ── assemble result ───────────────────────────────────────────────────────────

def assemble_output(
    tag: str,
    checks: list[dict],
    artifacts: dict,
    kill_switch_on: bool,
) -> dict:
    blockers = [c for c in checks if c["status"] == "FAIL" and c["severity"] == "BLOCKER"]
    warnings = [c for c in checks if c["status"] in ("FAIL", "WARN") and c["severity"] == "WARN"]
    errors   = [c for c in checks if c["status"] == "FAIL" and c["severity"] not in ("BLOCKER",)]

    if blockers:
        decision = "BLOCK"
    elif warnings:
        decision = "WARN"
    else:
        decision = "PASS"

    auto_allowed = decision == "PASS" and not kill_switch_on

    return {
        "tag":                   tag,
        "generated_at":          datetime.now().isoformat(),
        "decision":              decision,
        "auto_execution_allowed": auto_allowed,
        "kill_switch_on":        kill_switch_on,
        "checks": checks,
        "blockers":  [f"{c['name']}: {c['detail']}" for c in blockers],
        "warnings":  [f"{c['name']}: {c['detail']}" for c in warnings],
        "errors":    [f"{c['name']}: {c['detail']}" for c in errors],
        "artifacts": artifacts,
    }


# ── markdown report ───────────────────────────────────────────────────────────

def build_md(result: dict) -> str:
    decision_icons = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "🔴", "ERROR": "❌"}
    icon = decision_icons.get(result["decision"], "❓")
    ks_icon = "🔴 ON (automation blocked)" if result["kill_switch_on"] else "🟢 OFF (automation allowed)"

    checks_table = "| Check | Status | Severity | Detail |\n|---|---|---|---|\n"
    for c in result["checks"]:
        status_icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "SKIP": "—"}.get(c["status"], c["status"])
        checks_table += f"| {c['name']} | {status_icon} {c['status']} | {c['severity']} | {c['detail'][:120]} |\n"

    blockers_str = "\n".join(f"- ❌ {b}" for b in result["blockers"]) if result["blockers"] else "None"
    warnings_str = "\n".join(f"- ⚠️ {w}" for w in result["warnings"]) if result["warnings"] else "None"

    return f"""# V6 Automation Preflight Gate

- Tag: `{result['tag']}`
- Generated: {result['generated_at'][:19]}
- Strategy: V6-A ATTACK_EQUAL_REPLAY

---

## Decision: {icon} {result['decision']}

**auto_execution_allowed**: `{result['auto_execution_allowed']}`
**Kill switch**: {ks_icon}

---

## Gate Check Results

{checks_table}

---

## Blockers

{blockers_str}

---

## Warnings

{warnings_str}

---

## Interpretation

{"✅ All checks passed and kill switch is OFF — automatic execution is allowed by this gate." if result['auto_execution_allowed'] else
 ("🔴 Kill switch is ON — automatic execution is NOT allowed even though checks pass." if result['decision'] == 'PASS' and result['kill_switch_on'] else
  "🔴 One or more BLOCKER checks failed — automatic execution is NOT allowed.")}

> ⚠️ This gate is a preflight check only. Real order placement requires a separate runner with explicit confirmation.
"""


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag",    default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    tag         = args.tag
    config_path = Path(args.config)

    print(f"[V6 Automation Preflight Gate] tag={tag}")
    print(f"  Config: {config_path}")

    policy = read_json(config_path)
    if policy is None:
        print(f"  ERROR: Cannot read policy config: {config_path}")
        return 1

    kill_switch_on = policy.get("kill_switch", {}).get("enabled", True)
    print(f"  Kill switch: {'ON' if kill_switch_on else 'OFF'}")

    checks   = []
    artifacts = {}

    # ── Check 1: Kill switch ──────────────────────────────────────────────────
    print("  [1/8] Kill switch...")
    c1 = check_kill_switch(policy)
    checks.append(c1)
    print(f"        {c1['status']} — {c1['detail'][:80]}")

    # ── Check 2: Managed state ────────────────────────────────────────────────
    print("  [2/8] Managed state validity...")
    c2, state = check_managed_state(policy)
    checks.append(c2)
    print(f"        {c2['status']} — {c2['detail'][:80]}")
    if state:
        artifacts["managed_state_summary"] = {
            "strategy":      state.get("strategy"),
            "positions":     state.get("positions"),
            "pending_count": len(state.get("pending_orders", [])),
        }

    # ── Check 3: Pending orders ───────────────────────────────────────────────
    print("  [3/8] Pending orders...")
    c3 = check_pending_orders(state)
    checks.append(c3)
    print(f"        {c3['status']} — {c3['detail'][:80]}")

    # ── Check 4: Futu connectivity ────────────────────────────────────────────
    print("  [4/8] Futu/OpenD connectivity...")
    c4, futu_data = check_futu_connectivity(policy)
    checks.append(c4)
    print(f"        {c4['status']} — {c4['detail'][:80]}")
    if futu_data:
        artifacts["futu_quotes"] = futu_data.get("quotes", {})

    # ── Load preview orders ───────────────────────────────────────────────────
    preview_orders = load_latest_preview_orders(policy)
    artifacts["preview_order_count"] = len(preview_orders)

    # ── Check 5: Account cash ─────────────────────────────────────────────────
    print("  [5/8] Account cash / buying power...")
    c5 = check_account_cash(policy, futu_data, preview_orders)
    checks.append(c5)
    print(f"        {c5['status']} — {c5['detail'][:80]}")

    # ── Check 6: Order size limits ────────────────────────────────────────────
    print("  [6/8] Order size limits...")
    c6 = check_order_size(policy, preview_orders, state)
    checks.append(c6)
    print(f"        {c6['status']} — {c6['detail'][:80]}")

    # ── Check 7: Spread guard ─────────────────────────────────────────────────
    print("  [7/8] Slippage / spread guard...")
    c7 = check_spread(policy, futu_data, preview_orders)
    checks.append(c7)
    print(f"        {c7['status']} — {c7['detail'][:80]}")

    # ── Check 8: Release gate freshness ──────────────────────────────────────
    print("  [8/8] Release gate freshness...")
    c8, latest_runner = check_release_gate_freshness(policy)
    checks.append(c8)
    print(f"        {c8['status']} — {c8['detail'][:80]}")
    if latest_runner:
        artifacts["latest_runner_file"] = latest_runner.get("_file", "")

    # Trading session (informational, also a BLOCKER)
    c_sess = check_trading_session(policy)
    checks.append(c_sess)
    print(f"  [session] {c_sess['status']} — {c_sess['detail'][:80]}")

    # ── Assemble output ───────────────────────────────────────────────────────
    result = assemble_output(tag, checks, artifacts, kill_switch_on)

    print(f"\n  ── GATE DECISION: {result['decision']} ──")
    print(f"  auto_execution_allowed = {result['auto_execution_allowed']}")
    for b in result["blockers"]:
        print(f"  ❌ {b[:120]}")
    for w in result["warnings"]:
        print(f"  ⚠️  {w[:120]}")

    # ── Write outputs ─────────────────────────────────────────────────────────
    out_cfg = policy.get("output", {})
    out_dir = ROOT / out_cfg.get("dir", "backtest_results/v6_automation_preflight")
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"v6_automation_preflight_{tag}.json"
    md_path   = out_dir / f"v6_automation_preflight_{tag}.md"
    latest    = out_dir / out_cfg.get("latest_json", "latest.json")

    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(build_md(result), encoding="utf-8")
    latest.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n  ✓ JSON   → {json_path}")
    print(f"  ✓ MD     → {md_path}")
    print(f"  ✓ latest → {latest}")

    print(f"\nDone. Decision: {result['decision']} | auto_execution_allowed: {result['auto_execution_allowed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
