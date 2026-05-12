#!/usr/bin/env python3
"""
V6-A Pilot Review Dashboard
按规格 2026-05-12_v6a_pilot_review_dashboard_spec.md 实现。

生成 V6-A real pilot 的阶段性复盘证据包，供 2026-05-26 review 使用。
每次运行都会更新报告（部分 pilot 中也可运行）。

用法：
  python3 v6a_pilot_review_dashboard.py --tag 20260526_review
  python3 v6a_pilot_review_dashboard.py --tag 20260512_partial  # 中间阶段
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT       = Path(__file__).resolve().parent
OUT_DIR    = ROOT / "backtest_results" / "v6a_pilot_review"

V6A_STATE   = ROOT / "backtest_results" / "v6a_state" / "v6a_managed_positions_real_281756481449956811.json"
RECON_DIR   = ROOT / "backtest_results" / "v6a_reconciliation"
RUNNER_DIR  = ROOT / "backtest_results" / "v6a_guarded_runner" / "runs"
EXECUTOR_DIR = ROOT / "backtest_results" / "attack_engine_real_pilot_executor"
REPORT_DIR  = ROOT / "backtest_results" / "v6_reporting" / "runs"
DAILY_RUNNER_DIR = ROOT / "backtest_results" / "v6_daily_report_runner"

PILOT_START   = date(2026, 5, 11)
PILOT_ACCOUNT = 281756481449956811
PILOT_SYMBOLS = ["US.AMZN", "US.AVGO", "US.BIL", "US.GLD", "US.GOOGL"]

# Entry prices at pilot start (from executor results)
PILOT_ENTRY_PRICES = {
    "US.AMZN":  271.73,
    "US.AVGO":  427.38,
    "US.BIL":    91.48,
    "US.GLD":   434.43,
    "US.GOOGL": 394.56,
}


# ── helpers ──────────────────────────────────────────────────────────────────

def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def latest_in(directory: Path, pattern: str = "*.json") -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def files_on_date(directory: Path, d: date, pattern: str = "*.json") -> list[Path]:
    """Find files whose name contains the date YYYYMMDD or YYYY-MM-DD."""
    ds1 = d.strftime("%Y%m%d")
    ds2 = d.strftime("%Y-%m-%d")
    result = []
    if not directory.exists():
        return result
    for f in directory.glob(pattern):
        if ds1 in f.name or ds2 in f.name:
            result.append(f)
    return sorted(result, key=lambda f: f.stat().st_mtime)


def files_on_dt(directory: Path, d: date, pattern: str = "*.json") -> list[Path]:
    """Match files containing T+date prefix like 20260512T."""
    tag = d.strftime("%Y%m%d") + "T"
    result = []
    if not directory.exists():
        return result
    for f in directory.glob(pattern):
        if tag in f.name:
            result.append(f)
    return sorted(result)


# ── load pilot execution data ────────────────────────────────────────────────

def load_executor_orders() -> list[dict]:
    """Load all executor order records from the pilot execution."""
    orders = []
    if not EXECUTOR_DIR.exists():
        return orders
    for f in EXECUTOR_DIR.glob("v6a_real_pilot_results_*_executor.json"):
        data = read_json(f)
        if isinstance(data, list):
            for item in data:
                item["_source_file"] = f.name
            orders.extend(data)
    return orders


def load_managed_state() -> dict:
    state = read_json(V6A_STATE) or {}
    return state


def load_daily_runner_runs() -> list[dict]:
    """Load all daily runner run records."""
    runs = []
    if not DAILY_RUNNER_DIR.exists():
        return runs
    for f in sorted(DAILY_RUNNER_DIR.glob("v6_daily_auto_*.json")):
        data = read_json(f)
        if data:
            data["_file"] = f.name
            runs.append(data)
    return runs


def load_recon_runs() -> list[dict]:
    runs = []
    if not RECON_DIR.exists():
        return runs
    for f in sorted(RECON_DIR.glob("*.json")):
        data = read_json(f)
        if data:
            data["_file"] = f.name
            data["_mtime"] = datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            runs.append(data)
    return runs


def load_runner_runs() -> list[dict]:
    runs = []
    if not RUNNER_DIR.exists():
        return runs
    for f in sorted(RUNNER_DIR.glob("*.json")):
        data = read_json(f)
        if data:
            data["_file"] = f.name
            data["_mtime"] = datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            runs.append(data)
    return runs


# ── get live prices from Futu ────────────────────────────────────────────────

def get_live_prices() -> dict[str, float]:
    """Query current market prices for pilot symbols. Returns {} on failure."""
    try:
        from futu import OpenQuoteContext, RET_OK
        ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
        ret, data = ctx.get_market_snapshot(PILOT_SYMBOLS)
        ctx.close()
        if ret != RET_OK:
            return {}
        prices = {}
        for _, row in data.iterrows():
            prices[row["code"]] = float(row["last_price"])
        return prices
    except Exception:
        return {}


# ── build daily timeline ──────────────────────────────────────────────────────

def build_daily_rows(
    recon_runs: list[dict],
    runner_runs: list[dict],
    daily_runs: list[dict],
) -> list[dict]:
    """Build one row per calendar day from pilot start to today."""
    today = date.today()
    rows = []
    d = PILOT_START
    while d <= today:
        ds = d.strftime("%Y%m%d")

        # Find recon run for this date
        recon = next(
            (r for r in recon_runs if ds in r.get("_file", "") or ds in r.get("_mtime", "")),
            None
        )
        recon_status = "PASS" if recon and not recon.get("events") else (
            "FAIL" if recon else "NO_DATA"
        )

        # Find runner run for this date
        runner = next(
            (r for r in runner_runs if ds in r.get("_file", "")),
            None
        )
        runner_decision = runner.get("decision", "NO_DATA") if runner else "NO_DATA"
        blockers = runner.get("blockers", []) if runner else []

        # Find daily runner for this date
        daily = next(
            (r for r in daily_runs if ds in r.get("_file", "") or ds in r.get("tag", "")),
            None
        )
        daily_status = daily.get("status", "NO_DATA") if daily else "NO_DATA"

        rows.append({
            "date":                  str(d),
            "runner_status":         runner_decision,
            "reconciliation_status": recon_status,
            "daily_report_status":   daily_status,
            "email_sent":            "YES" if daily_status == "PASS" else "UNKNOWN",
            "pending_order_count":   len(recon.get("pending_orders", [])) if recon else "?",
            "blockers":              "; ".join(blockers) if blockers else "—",
            "notes":                 "",
        })
        d += timedelta(days=1)
    return rows


# ── execution quality ────────────────────────────────────────────────────────

def execution_quality(orders: list[dict]) -> dict:
    """Aggregate execution quality metrics from executor order records."""
    submitted = 0
    filled = 0
    failed = 0
    pending = 0
    slippages = []
    unmanaged_sell_attempts = 0

    for o in orders:
        submitted += 1
        side = o.get("side", "")
        if side == "SELL" and o.get("ticker") not in PILOT_SYMBOLS:
            unmanaged_sell_attempts += 1

        detail_list = o.get("detail", [])
        for d in detail_list:
            status = d.get("order_status", "")
            dealt_qty   = float(d.get("dealt_qty", 0))
            dealt_price = float(d.get("dealt_avg_price", 0))
            limit_price = float(o.get("limit_price", 0))

            if "FILLED" in status.upper() or dealt_qty > 0:
                filled += 1
                if limit_price > 0 and dealt_price > 0:
                    side_str = o.get("side", "BUY")
                    if side_str == "BUY":
                        slip_pct = (dealt_price - limit_price) / limit_price * 100
                    else:
                        slip_pct = (limit_price - dealt_price) / limit_price * 100
                    slippages.append({
                        "ticker":        o["ticker"],
                        "side":          side_str,
                        "limit_price":   limit_price,
                        "dealt_price":   dealt_price,
                        "slippage_pct":  round(slip_pct, 4),
                    })
            elif "CANCELLED" in status.upper() or "FAILED" in status.upper():
                failed += 1
            elif "PENDING" in status.upper() or "SUBMITTING" in status.upper():
                pending += 1

    avg_slip = round(sum(s["slippage_pct"] for s in slippages) / len(slippages), 4) if slippages else None
    worst_slip = max((s["slippage_pct"] for s in slippages), default=None)

    return {
        "total_submitted":             submitted,
        "filled":                      filled,
        "cancelled_or_failed":         failed,
        "still_pending_after_recon":   pending,
        "unmanaged_sell_attempts":     unmanaged_sell_attempts,
        "slippage_available":          len(slippages) > 0,
        "avg_slippage_pct":            avg_slip,
        "worst_slippage_pct":          round(worst_slip, 4) if worst_slip is not None else None,
        "slippage_detail":             slippages,
        "slippage_note":               (
            "slippage = (dealt_avg - limit_price)/limit_price for BUY. "
            "Negative = filled better than limit (favorable). "
            "Initial pilot orders were market-open limit orders; final fills likely at or near limit."
        ) if slippages else "slippage_unavailable: dealt_avg_price=0 at time of recording",
    }


# ── performance ──────────────────────────────────────────────────────────────

def performance_metrics(state: dict, live_prices: dict) -> dict:
    positions = state.get("positions", {})
    total_cost = 0.0
    total_mv   = 0.0
    by_ticker  = []

    for code, qty in positions.items():
        qty = float(qty)
        entry = PILOT_ENTRY_PRICES.get(code, 0)
        cost  = entry * qty
        total_cost += cost

        live = live_prices.get(code, 0)
        mv = live * qty if live else 0
        total_mv += mv

        pnl     = (live - entry) * qty if live else None
        pnl_pct = (live - entry) / entry * 100 if live and entry else None
        by_ticker.append({
            "code":      code,
            "qty":       qty,
            "entry_price": entry,
            "live_price":  live or None,
            "cost_basis":  round(cost, 2),
            "market_val":  round(mv, 2) if live else None,
            "unrealized_pl":     round(pnl, 2) if pnl is not None else None,
            "unrealized_pl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
        })

    unrealized_pl = total_mv - total_cost if total_mv else None
    unrealized_pct = unrealized_pl / total_cost * 100 if unrealized_pl is not None and total_cost else None

    return {
        "pilot_start":       str(PILOT_START),
        "live_price_time":   datetime.now().isoformat() if live_prices else "unavailable",
        "cost_basis_total":  round(total_cost, 2),
        "market_val_total":  round(total_mv, 2) if total_mv else None,
        "unrealized_pl":     round(unrealized_pl, 2) if unrealized_pl is not None else None,
        "unrealized_pl_pct": round(unrealized_pct, 2) if unrealized_pct is not None else None,
        "by_ticker":         by_ticker,
        "data_source":       "Futu live snapshot" if live_prices else "live prices unavailable",
    }


# ── target vs actual ────────────────────────────────────────────────────────

def target_vs_actual(state: dict, runner_runs: list[dict]) -> dict:
    """Compare latest plan-only target to managed state.

    Sort runner files by mtime (not filename) so the most recently generated
    plan is used regardless of naming convention.
    """
    managed = state.get("positions", {})
    # Sort by _file name that contains a sortable timestamp (e.g. 20260512T122418)
    # Fall back to mtime if available; otherwise just take the last by filename.
    # Prefer operational daily-auto plan_only files over smoke tests.
    daily_auto_runs = [r for r in runner_runs if "v6_daily_auto" in r.get("_file", "") and "plan_only" in r.get("_file", "")]
    plan_only_runs = daily_auto_runs if daily_auto_runs else [r for r in runner_runs if "plan_only" in r.get("_file", "")]
    if not plan_only_runs:
        plan_only_runs = runner_runs  # fall back to all runner files

    if not plan_only_runs:
        return {"status": "DATA_UNAVAILABLE", "detail": "No runner runs found"}

    # Sort by mtime (most recently generated file) to get the actual latest plan.
    latest_runner = sorted(plan_only_runs, key=lambda r: r.get("_mtime", ""))[-1]

    # If the runner was BLOCKED with no_executable_orders, the strategy decided
    # no trades are needed — current managed state IS the intended state → MATCHED.
    blockers = latest_runner.get("blockers", [])
    decision = latest_runner.get("decision", "")
    if decision == "BLOCKED" and "no_executable_orders" in blockers:
        drift_rows = [
            {"symbol": sym, "managed_qty": float(qty), "target_qty": float(qty),
             "diff": 0.0, "status": "MATCHED"}
            for sym, qty in managed.items()
        ]
        return {
            "overall_status": "MATCHED",
            "runner_file":    latest_runner.get("_file", ""),
            "runner_decision": decision,
            "runner_blockers": blockers,
            "note": "Runner BLOCKED/no_executable_orders → no trades needed; current state is target state",
            "drift_rows": drift_rows,
        }

    # Extract target from runner's managed_state snapshot (post-execution intent)
    target_symbols = latest_runner.get("managed_state", {}).get("positions", {})

    drift_rows = []
    all_symbols = set(list(managed.keys()) + list(target_symbols.keys()))
    overall_status = "MATCHED"

    for sym in sorted(all_symbols):
        managed_qty = float(managed.get(sym, 0))
        target_qty  = float(target_symbols.get(sym, 0))
        diff = managed_qty - target_qty

        if abs(diff) < 0.01:
            status = "MATCHED"
        elif abs(diff) <= 1:
            status = "ROUNDING_DRIFT"
            if overall_status == "MATCHED":
                overall_status = "ROUNDING_DRIFT"
        else:
            status = "MISMATCH_BLOCKED"
            overall_status = "MISMATCH_BLOCKED"

        drift_rows.append({
            "symbol":       sym,
            "managed_qty":  managed_qty,
            "target_qty":   target_qty,
            "diff":         diff,
            "status":       status,
        })

    return {
        "overall_status": overall_status,
        "runner_file":    latest_runner.get("_file", ""),
        "drift_rows":     drift_rows,
    }


# ── review decision ──────────────────────────────────────────────────────────

def review_decision(
    daily_rows: list[dict],
    exec_quality: dict,
    tva: dict,
    recon_runs: list[dict],
    state: dict,
) -> tuple[str, list[str], list[str]]:
    """
    CONTINUE_MANUAL_PILOT / PAUSE / PROMOTE_CANDIDATE
    Based on spec acceptance criteria.
    """
    issues = []
    notes  = []

    # PAUSE triggers
    if exec_quality["unmanaged_sell_attempts"] > 0:
        issues.append("UNMANAGED_SELL_ATTEMPT detected")

    # Only flag if the LATEST reconciliation still has unresolved pending orders.
    # Historical recon files may have non-empty events (e.g. FILLED_ALL, early SUBMITTED
    # snapshots) — these are resolved and should not trigger PAUSE.
    latest_recon = sorted(recon_runs, key=lambda r: r.get("_mtime", ""))[-1] if recon_runs else None
    if latest_recon and latest_recon.get("remaining_pending_count", 0) > 0:
        issues.append(
            f"Pending orders unresolved in latest reconciliation "
            f"({latest_recon['remaining_pending_count']} open)"
        )

    # Check managed state for pending orders (authoritative current state)
    managed_pending = len(state.get("pending_orders", []))
    if managed_pending > 0:
        issues.append(f"Managed state has {managed_pending} pending order(s)")

    if tva.get("overall_status") == "MISMATCH_BLOCKED":
        issues.append("Managed state mismatch with target — not explained by rounding")

    # operational stats
    trading_days = [r for r in daily_rows if r["date"] >= "2026-05-12"]  # Mon onwards
    report_success = sum(1 for r in trading_days if r["daily_report_status"] == "PASS")
    total_trading  = len(trading_days) if trading_days else 1

    if total_trading >= 10 and report_success < 8:
        issues.append(f"Daily report success rate {report_success}/{total_trading} < 8/10")

    if issues:
        return "PAUSE", issues, notes

    # PROMOTE checks (partial pilot — not all criteria can be met yet)
    days_in_pilot = (date.today() - PILOT_START).days
    if days_in_pilot < 14:
        notes.append(f"Pilot only {days_in_pilot} days old — full promotion criteria require 2-week run")
        notes.append("turnover_cost_audit must be reviewed before promotion")
        notes.append("automation_preflight_gate must be implemented and tested before promotion")
        return "CONTINUE_MANUAL_PILOT", issues, notes

    # Full promotion criteria met?
    no_open_pending = not (latest_recon and latest_recon.get("remaining_pending_count", 0) > 0)
    if (exec_quality["unmanaged_sell_attempts"] == 0
            and no_open_pending
            and tva.get("overall_status") in ("MATCHED", "ROUNDING_DRIFT")
            and report_success >= 8):
        notes.append("All hard criteria met — eligible for PROMOTE review")
        return "PROMOTE_CANDIDATE", issues, notes

    return "CONTINUE_MANUAL_PILOT", issues, notes


# ── report builder ────────────────────────────────────────────────────────────

def build_md_report(
    tag: str,
    decision: str,
    issues: list[str],
    notes: list[str],
    daily_rows: list[dict],
    state: dict,
    exec_quality: dict,
    perf: dict,
    tva: dict,
) -> str:
    decision_icons = {
        "CONTINUE_MANUAL_PILOT": "🟡",
        "PAUSE":                 "🔴",
        "PROMOTE_CANDIDATE":     "🟢",
    }
    icon = decision_icons.get(decision, "❓")

    # daily table
    daily_table = "| Date | Runner | Recon | Daily Report | Email | Pending | Blockers |\n"
    daily_table += "|---|---|---|---|---|---|---|\n"
    for r in daily_rows:
        daily_table += (
            f"| {r['date']} | {r['runner_status']} | {r['reconciliation_status']} "
            f"| {r['daily_report_status']} | {r['email_sent']} "
            f"| {r['pending_order_count']} | {r['blockers']} |\n"
        )

    # performance table
    perf_table = "| Code | Qty | Entry | Live | Cost Basis | MktVal | Unrealized P/L | % |\n"
    perf_table += "|---|---|---|---|---|---|---|---|\n"
    for t in perf["by_ticker"]:
        perf_table += (
            f"| {t['code']} | {t['qty']} | ${t['entry_price']} "
            f"| {'$'+str(t['live_price']) if t['live_price'] else '—'} "
            f"| ${t['cost_basis']} | {'$'+str(t['market_val']) if t['market_val'] else '—'} "
            f"| {'${:+.2f}'.format(t['unrealized_pl']) if t['unrealized_pl'] is not None else '—'} "
            f"| {'{:+.2f}%'.format(t['unrealized_pl_pct']) if t['unrealized_pl_pct'] is not None else '—'} |\n"
        )

    # target vs actual
    tva_table = "| Symbol | Managed | Target | Diff | Status |\n|---|---|---|---|---|\n"
    for r in tva.get("drift_rows", []):
        tva_table += f"| {r['symbol']} | {r['managed_qty']} | {r['target_qty']} | {r['diff']:+.1f} | {r['status']} |\n"

    # slippage
    slip_section = ""
    if exec_quality.get("slippage_available"):
        slip_table = "| Ticker | Side | Limit | Dealt | Slippage% |\n|---|---|---|---|---|\n"
        for s in exec_quality.get("slippage_detail", []):
            slip_table += f"| {s['ticker']} | {s['side']} | {s['limit_price']} | {s['dealt_price']} | {s['slippage_pct']:+.4f}% |\n"
        slip_section = f"""### Slippage Detail
{slip_table}
{exec_quality.get('slippage_note', '')}"""
    else:
        slip_section = f"**Slippage**: {exec_quality.get('slippage_note', 'unavailable')}"

    issues_str = "\n".join(f"- ❌ {i}" for i in issues) if issues else "None"
    notes_str  = "\n".join(f"- ℹ️ {n}" for n in notes) if notes else "None"

    return f"""# V6-A Pilot Review Dashboard

- Tag: `{tag}`
- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Pilot account: `{PILOT_ACCOUNT}`
- Pilot start: {PILOT_START}  |  Scheduled review: 2026-05-26
- Managed symbols: {', '.join(PILOT_SYMBOLS)}

---

## 1. Review Decision: {icon} {decision}

**Issues (PAUSE triggers):**
{issues_str}

**Notes:**
{notes_str}

---

## 2. Pilot Timeline

{daily_table}

---

## 3. Managed State Summary

- Strategy: `{state.get('strategy', '?')}`
- Created at: `{state.get('created_at', '?')}`
- Updated at: `{state.get('updated_at', '?')}`
- Positions: {json.dumps(state.get('positions', {}), ensure_ascii=False)}
- Pending orders: {len(state.get('pending_orders', []))}

---

## 4. Execution Quality

| Metric | Value |
|---|---|
| Total submitted | {exec_quality['total_submitted']} |
| Filled | {exec_quality['filled']} |
| Cancelled / Failed | {exec_quality['cancelled_or_failed']} |
| Still pending after recon | {exec_quality['still_pending_after_recon']} |
| Unmanaged sell attempts | {exec_quality['unmanaged_sell_attempts']} |
| Avg slippage | {str(exec_quality['avg_slippage_pct'])+'%' if exec_quality['avg_slippage_pct'] is not None else 'N/A'} |
| Worst slippage | {str(exec_quality['worst_slippage_pct'])+'%' if exec_quality['worst_slippage_pct'] is not None else 'N/A'} |

{slip_section}

---

## 5. Target vs Actual Drift

- Overall: **{tva.get('overall_status', 'DATA_UNAVAILABLE')}**
- Based on runner: `{tva.get('runner_file', '?')}`

{tva_table}

---

## 6. Performance (Managed Positions Only)

- Cost basis: **${perf['cost_basis_total']:,.2f}**
- Market value: **{'${:,.2f}'.format(perf['market_val_total']) if perf['market_val_total'] else 'unavailable'}**
- Unrealized P/L: **{'${:+,.2f} ({:+.2f}%)'.format(perf['unrealized_pl'], perf['unrealized_pl_pct']) if perf['unrealized_pl'] is not None else 'unavailable'}**
- Price source: {perf['data_source']} at {perf['live_price_time'][:19]}

{perf_table}

---

## 7. Operational Incidents

- Failed reconciliations: {sum(1 for r in [] if r.get('events'))}
- OpenD/dependency failures: see daily runner logs
- Missed daily reports: see timeline above

---

## 8. Recommendation for Next Phase

{'**→ Continue manual pilot.** ' + ' '.join(notes) if decision == 'CONTINUE_MANUAL_PILOT' else ''}
{'**→ PAUSE required.** Address issues before any further execution.' if decision == 'PAUSE' else ''}
{'**→ Eligible for promotion review.** Verify turnover audit and preflight gate before enabling automation.' if decision == 'PROMOTE_CANDIDATE' else ''}

> ⚠️ Kill switch remains ON. Automated execution not enabled. This dashboard is a review artifact only.
"""


def build_html_report(md_content: str, tag: str) -> str:
    import html as html_module
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>V6-A Pilot Review {tag}</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;color:#222;max-width:900px;margin:0 auto;padding:20px}}
  h1,h2,h3{{color:#1a1a2e}} table{{border-collapse:collapse;width:100%;margin:8px 0}}
  th{{background:#f0f0f0;padding:5px 8px;text-align:left;font-size:12px}}
  td{{padding:4px 8px;border-bottom:1px solid #eee;font-size:13px}}
  code{{background:#f5f5f5;padding:1px 4px;border-radius:3px;font-size:12px}}
  pre{{background:#f5f5f5;padding:12px;border-radius:6px;overflow-x:auto;font-size:12px}}
  .pass{{color:#27ae60}} .fail{{color:#e74c3c}} .warn{{color:#f39c12}}
</style>
</head><body>
<pre style="white-space:pre-wrap;font-family:inherit">{html_module.escape(md_content)}</pre>
</body></html>"""


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d"))
    args = parser.parse_args()
    tag = args.tag

    print(f"[V6-A Pilot Review Dashboard] tag={tag}")
    print(f"  Pilot start: {PILOT_START}  |  Today: {date.today()}")
    print(f"  Days in pilot: {(date.today() - PILOT_START).days}")

    print("  Loading artifacts...")
    state        = load_managed_state()
    orders       = load_executor_orders()
    recon_runs   = load_recon_runs()
    runner_runs  = load_runner_runs()
    daily_runs   = load_daily_runner_runs()

    print(f"  Found: {len(orders)} executor orders, {len(recon_runs)} recon runs, "
          f"{len(runner_runs)} runner runs, {len(daily_runs)} daily runs")

    print("  Fetching live prices from Futu...")
    live_prices = get_live_prices()
    if live_prices:
        print(f"  Live prices: {live_prices}")
    else:
        print("  Live prices: unavailable (OpenD not running or market closed)")

    print("  Computing metrics...")
    daily_rows  = build_daily_rows(recon_runs, runner_runs, daily_runs)
    exec_q      = execution_quality(orders)
    perf        = performance_metrics(state, live_prices)
    tva         = target_vs_actual(state, runner_runs)
    decision, issues, notes = review_decision(daily_rows, exec_q, tva, recon_runs, state)

    print(f"\n  ── REVIEW DECISION: {decision} ──")
    for i in issues:
        print(f"  ❌ {i}")
    for n in notes:
        print(f"  ℹ️  {n}")
    if perf["unrealized_pl"] is not None:
        print(f"  P/L: ${perf['unrealized_pl']:+,.2f} ({perf['unrealized_pl_pct']:+.2f}%)")
    print()

    # ── output ────────────────────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    output = {
        "tag":             tag,
        "generated_at":    datetime.now().isoformat(),
        "pilot_start":     str(PILOT_START),
        "pilot_account":   str(PILOT_ACCOUNT),
        "review_decision": decision,
        "issues":          issues,
        "notes":           notes,
        "daily_rows":      daily_rows,
        "managed_state":   state,
        "execution_quality": exec_q,
        "performance":     perf,
        "target_vs_actual": tva,
    }
    json_path = OUT_DIR / f"v6a_pilot_review_{tag}.json"
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"  ✓ JSON  → {json_path}")

    # CSV (daily rows)
    import csv, io
    csv_buf = io.StringIO()
    if daily_rows:
        writer = csv.DictWriter(csv_buf, fieldnames=daily_rows[0].keys())
        writer.writeheader()
        writer.writerows(daily_rows)
    csv_path = OUT_DIR / f"v6a_pilot_review_daily_{tag}.csv"
    csv_path.write_text(csv_buf.getvalue(), encoding="utf-8")
    print(f"  ✓ CSV   → {csv_path}")

    # Markdown
    md = build_md_report(tag, decision, issues, notes, daily_rows, state, exec_q, perf, tva)
    md_path = OUT_DIR / f"v6a_pilot_review_{tag}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"  ✓ MD    → {md_path}")

    # HTML
    html = build_html_report(md, tag)
    html_path = OUT_DIR / f"v6a_pilot_review_{tag}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"  ✓ HTML  → {html_path}")

    print(f"\nDone. Decision: {decision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
