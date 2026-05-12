#!/usr/bin/env python3
"""
Smoke tests for v6_automation_preflight_gate.py
Six deterministic scenarios using local fixture JSON files.

Usage:
  python3 tests/test_v6_automation_preflight_gate.py

No external dependencies. All Futu/OpenD calls are bypassed via fixture injection.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Import the check functions directly (no network calls needed for unit tests)
from v6_automation_preflight_gate import (
    check_kill_switch,
    check_managed_state,
    check_pending_orders,
    check_account_cash,
    check_order_size,
    check_spread,
    make_check,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

POLICY_BASE = {
    "kill_switch": {"enabled": False, "reason": "test", "updated_at": "2026-05-12", "updated_by": "test"},
    "futu": {"host": "127.0.0.1", "port": 11111, "real_acc_id": "281756481449956811",
             "target_symbols": ["US.AMZN", "US.GLD"]},
    "managed_state": {
        "file": "",  # overridden per test via temp file
        "expected_strategy": "V6-A ATTACK_EQUAL_REPLAY",
        "allowed_ticker_prefix": "US.",
    },
    "cash": {"min_cash_buffer_usd": 100, "block_all_if_buys_unfunded": True},
    "order_size": {
        "max_total_notional_usd": 5000,
        "max_order_value_usd": 5000,
        "min_order_value_usd": 25,
        "allow_full_exit_below_min": True,
    },
    "slippage": {
        "max_spread_pct_core": 0.30,
        "max_spread_pct_defensive_etf": 0.10,
        "defensive_etf_tickers": ["US.BIL", "US.GLD"],
        "warning_slippage_pct": 0.50,
        "critical_slippage_pct": 1.00,
    },
}

VALID_STATE = {
    "strategy": "V6-A ATTACK_EQUAL_REPLAY",
    "positions": {"US.AMZN": 4.0, "US.GLD": 1.0},
    "pending_orders": [],
    "created_at": "2026-05-11T22:21:02",
    "updated_at": "2026-05-12T12:24:18",
}

CLEAN_FUTU_DATA = {
    "quotes": {
        "US.AMZN": {"bid": 268.99, "ask": 269.02, "last": 269.00},
        "US.GLD":  {"bid": 434.60, "ask": 434.65, "last": 434.63},
    },
    "acct_info": {"usd_net_cash_power": 5000.0, "us_cash": 2000.0},
}

BUY_ORDERS = [
    {"ticker": "US.AMZN", "side": "BUY", "preview_qty": 1, "order_price": 269.0,
     "preview_order_value": 269.0},
]


def _write_state(state: dict) -> Path:
    """Write a state dict to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump(state, f)
    f.close()
    return Path(f.name)


def _policy_with_state(state_path: Path) -> dict:
    import copy
    p = copy.deepcopy(POLICY_BASE)
    p["managed_state"]["file"] = str(state_path)
    return p


# ── test 1: kill switch ON blocks automation ──────────────────────────────────

def test_kill_switch_on_blocks():
    """Kill switch enabled → FAIL BLOCKER."""
    policy_ks_on = dict(POLICY_BASE, kill_switch={
        "enabled": True, "reason": "test_block", "updated_at": "2026-05-12", "updated_by": "test"
    })
    c = check_kill_switch(policy_ks_on)
    assert c["status"] == "FAIL", f"Expected FAIL, got {c['status']}: {c['detail']}"
    assert c["severity"] == "BLOCKER"
    assert "ON" in c["detail"]
    print(f"  ✅ test_kill_switch_on_blocks: PASS (detail='{c['detail'][:60]}...')")


# ── test 2: malformed managed state blocks ────────────────────────────────────

def test_malformed_state_blocks():
    """Managed state with wrong strategy → FAIL BLOCKER."""
    bad_state = dict(VALID_STATE, strategy="WRONG_STRATEGY")
    state_path = _write_state(bad_state)
    policy = _policy_with_state(state_path)
    c, _ = check_managed_state(policy)
    assert c["status"] == "FAIL", f"Expected FAIL, got {c['status']}: {c['detail']}"
    assert c["severity"] == "BLOCKER"
    assert "strategy mismatch" in c["detail"]
    state_path.unlink()
    print(f"  ✅ test_malformed_state_blocks: PASS (detail='{c['detail'][:60]}...')")


def test_missing_state_file_blocks():
    """State file not found → FAIL BLOCKER."""
    policy = _policy_with_state(Path("/nonexistent/state.json"))
    c, _ = check_managed_state(policy)
    assert c["status"] == "FAIL"
    assert "not found" in c["detail"]
    print(f"  ✅ test_missing_state_file_blocks: PASS")


def test_negative_position_blocks():
    """Negative quantity in managed state → FAIL BLOCKER."""
    bad_state = dict(VALID_STATE, positions={"US.AMZN": -1.0})
    state_path = _write_state(bad_state)
    policy = _policy_with_state(state_path)
    c, _ = check_managed_state(policy)
    assert c["status"] == "FAIL"
    assert "negative position qty" in c["detail"]
    state_path.unlink()
    print(f"  ✅ test_negative_position_blocks: PASS")


# ── test 3: pending order blocks ──────────────────────────────────────────────

def test_pending_order_blocks():
    """Managed state with pending orders → FAIL BLOCKER."""
    state_with_pending = dict(VALID_STATE, pending_orders=[
        {"order_id": "TEST123", "ticker": "US.AMZN", "side": "BUY"}
    ])
    c = check_pending_orders(state_with_pending)
    assert c["status"] == "FAIL", f"Expected FAIL, got {c['status']}: {c['detail']}"
    assert c["severity"] == "BLOCKER"
    assert "pending order" in c["detail"].lower()
    print(f"  ✅ test_pending_order_blocks: PASS (detail='{c['detail'][:60]}...')")


# ── test 4: insufficient cash blocks ─────────────────────────────────────────

def test_insufficient_cash_blocks():
    """Buy notional + buffer exceeds available cash → FAIL BLOCKER."""
    tight_futu = {
        "quotes": CLEAN_FUTU_DATA["quotes"],
        "acct_info": {"usd_net_cash_power": 50.0},  # only $50 available
    }
    large_buy_orders = [
        {"ticker": "US.AMZN", "side": "BUY", "preview_qty": 10, "order_price": 269.0,
         "preview_order_value": 2690.0},
    ]
    c = check_account_cash(POLICY_BASE, tight_futu, large_buy_orders)
    assert c["status"] == "FAIL", f"Expected FAIL, got {c['status']}: {c['detail']}"
    assert c["severity"] == "BLOCKER"
    assert "Insufficient" in c["detail"]
    print(f"  ✅ test_insufficient_cash_blocks: PASS (detail='{c['detail'][:70]}...')")


def test_no_buys_cash_pass():
    """No BUY orders → cash check trivially passes."""
    c = check_account_cash(POLICY_BASE, CLEAN_FUTU_DATA, [])
    assert c["status"] == "PASS", f"Expected PASS, got {c['status']}: {c['detail']}"
    print(f"  ✅ test_no_buys_cash_pass: PASS")


# ── test 5: high spread blocks ────────────────────────────────────────────────

def test_high_spread_blocks():
    """Wide spread on core stock exceeds 0.30% → FAIL BLOCKER."""
    wide_spread_futu = {
        "quotes": {
            "US.AMZN": {"bid": 265.0, "ask": 272.0, "last": 268.5},  # ~2.6% spread
            "US.GLD":  {"bid": 434.60, "ask": 434.65, "last": 434.63},
        },
        "acct_info": {},
    }
    c = check_spread(POLICY_BASE, wide_spread_futu, BUY_ORDERS)
    assert c["status"] == "FAIL", f"Expected FAIL, got {c['status']}: {c['detail']}"
    assert c["severity"] == "BLOCKER"
    assert "spread" in c["detail"].lower()
    print(f"  ✅ test_high_spread_blocks: PASS (detail='{c['detail'][:70]}...')")


def test_etf_spread_threshold():
    """Defensive ETF (GLD) uses tighter 0.10% threshold."""
    # GLD spread ~0.15% (over ETF limit but under core limit)
    etf_wide_futu = {
        "quotes": {
            "US.AMZN": {"bid": 268.99, "ask": 269.02, "last": 269.00},  # 0.011% — fine
            "US.GLD":  {"bid": 433.50, "ask": 434.65, "last": 434.07},  # ~0.27% — over ETF limit
        },
        "acct_info": {},
    }
    c = check_spread(POLICY_BASE, etf_wide_futu, [])
    assert c["status"] == "FAIL", f"Expected FAIL for wide GLD spread, got {c['status']}: {c['detail']}"
    assert "US.GLD" in c["detail"]
    print(f"  ✅ test_etf_spread_threshold: PASS (GLD wide spread correctly caught)")


# ── test 6: clean fixture passes ─────────────────────────────────────────────

def test_clean_fixture_passes():
    """All checks with valid inputs → PASS."""
    # Kill switch
    c1 = check_kill_switch(POLICY_BASE)
    assert c1["status"] == "PASS", f"kill_switch: {c1['detail']}"

    # Managed state
    state_path = _write_state(VALID_STATE)
    policy = _policy_with_state(state_path)
    c2, state = check_managed_state(policy)
    assert c2["status"] == "PASS", f"managed_state: {c2['detail']}"
    state_path.unlink()

    # Pending orders
    c3 = check_pending_orders(VALID_STATE)
    assert c3["status"] == "PASS", f"pending_orders: {c3['detail']}"

    # Cash (no buys)
    c5 = check_account_cash(POLICY_BASE, CLEAN_FUTU_DATA, [])
    assert c5["status"] == "PASS", f"account_cash: {c5['detail']}"

    # Order sizes (no executable orders)
    c6 = check_order_size(POLICY_BASE, [], VALID_STATE)
    assert c6["status"] == "PASS", f"order_size: {c6['detail']}"

    # Spread (all within limits)
    c7 = check_spread(POLICY_BASE, CLEAN_FUTU_DATA, [])
    assert c7["status"] == "PASS", f"spread: {c7['detail']}"

    print(f"  ✅ test_clean_fixture_passes: all 6 checks PASS")


# ── test: order size violations ───────────────────────────────────────────────

def test_order_too_large_blocks():
    """Single order exceeds max_order_value → FAIL BLOCKER."""
    huge_order = [{"ticker": "US.AMZN", "side": "BUY", "preview_qty": 100,
                   "order_price": 269.0, "preview_order_value": 26900.0}]
    c = check_order_size(POLICY_BASE, huge_order, VALID_STATE)
    assert c["status"] == "FAIL"
    assert "order value" in c["detail"]
    print(f"  ✅ test_order_too_large_blocks: PASS")


def test_hold_orders_ignored():
    """HOLD rows in preview don't trigger order size check."""
    hold_orders = [
        {"ticker": "US.AMZN", "side": "HOLD", "preview_qty": 0, "order_price": 269.0,
         "preview_order_value": 0.0},
        {"ticker": "US.GLD",  "side": "HOLD", "preview_qty": 0, "order_price": 434.0,
         "preview_order_value": 0.0},
    ]
    c = check_order_size(POLICY_BASE, hold_orders, VALID_STATE)
    assert c["status"] == "PASS", f"HOLD orders should be ignored: {c['detail']}"
    print(f"  ✅ test_hold_orders_ignored: PASS")


# ── runner ────────────────────────────────────────────────────────────────────

def run_all():
    tests = [
        test_kill_switch_on_blocks,
        test_malformed_state_blocks,
        test_missing_state_file_blocks,
        test_negative_position_blocks,
        test_pending_order_blocks,
        test_insufficient_cash_blocks,
        test_no_buys_cash_pass,
        test_high_spread_blocks,
        test_etf_spread_threshold,
        test_clean_fixture_passes,
        test_order_too_large_blocks,
        test_hold_orders_ignored,
    ]

    print(f"\n{'='*60}")
    print("V6 Automation Preflight Gate — Smoke Tests")
    print(f"{'='*60}")

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {t.__name__}: FAIL — {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: ERROR — {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{passed+failed} passed, {failed} failed")
    print(f"{'='*60}")
    return failed


if __name__ == "__main__":
    sys.exit(run_all())
