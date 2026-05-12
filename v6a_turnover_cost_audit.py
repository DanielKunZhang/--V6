#!/usr/bin/env python3
"""
V6-A Turnover / Cost Audit
按规格 2026-05-12_v6a_turnover_cost_audit_spec.md 实现。

ATTACK_EQUAL_REPLAY 是 6 个子候选等权组合；
turnover / daily_return 从子候选均值推导，composite 文件提供汇总参考。

用法：
  python3 v6a_turnover_cost_audit.py --tag 20260512_initial
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT       = Path(__file__).resolve().parent
REPLAY_DIR = ROOT / "backtest_results" / "attack_engine_replay"
OUT_DIR    = ROOT / "backtest_results" / "v6a_turnover_cost_audit"

REBALANCES_FILE = REPLAY_DIR / "attack_replay_rebalances_20260506_live_refreshed.csv"
DAILY_FILE      = REPLAY_DIR / "attack_replay_daily_20260506_live_refreshed.csv"
COMPOSITE_FILE  = REPLAY_DIR / "attack_replay_composite_20260506_live_refreshed.csv"

COST_BPS_LEVELS = [0, 5, 10, 25, 50, 100]
NOTIONALS       = [5_000, 25_000, 50_000, 100_000]

# OOS split: composite reports full_years=13.6, train_years=7.6 → OOS starts ~7.6 yr after data start
OOS_YEAR_OFFSET = 7.6
RECENT_YEAR_OFFSET = 2.0


# ── data loading ─────────────────────────────────────────────────────────────

def load_data() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    reb = pd.read_csv(REBALANCES_FILE, parse_dates=["date"])
    daily = pd.read_csv(DAILY_FILE, parse_dates=["date"])
    comp_row = pd.read_csv(COMPOSITE_FILE).iloc[0].to_dict()

    sub_candidates = sorted(reb["candidate_id"].unique().tolist())
    return reb, daily, comp_row, sub_candidates


def build_equal_replay(reb: pd.DataFrame, daily: pd.DataFrame, sub_candidates: list[str]
                       ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build ATTACK_EQUAL_REPLAY daily and rebalance series from sub-candidates.

    Convention:
    - Daily return: simple mean of all 6 sub-candidates (daily file always has all 6) ✓
    - Portfolio turnover: sum of sub-candidate turnovers on a given day / 6
      This is correct because each sub-candidate represents 1/6 of the portfolio.
      On days where only 1 sub-candidate rebalances (most days), portfolio turnover
      = that candidate's turnover / 6. Using naive mean would overstate by up to 6x.
    - Turnover source: rebalances file (not daily file, which uses a different convention).
    """
    n_candidates = len(sub_candidates)

    # --- daily returns: mean across all 6 (daily file has all 6 every day) ---
    d = daily[daily["candidate_id"].isin(sub_candidates)].copy()
    daily_eq = (
        d.groupby("date")
        .agg(
            daily_return=("daily_return", "mean"),
            rebalanced=("rebalanced", "any"),
            risk_on_frac=("gross_exposure", lambda x: (x > 0).mean()),
        )
        .reset_index()
        .sort_values("date")
    )

    # --- portfolio turnover: sum over candidates with rows / n_candidates ---
    # (candidates not in rebalances on a given day have 0 turnover)
    reb_sub = reb[reb["candidate_id"].isin(sub_candidates)].copy()
    reb_agg = (
        reb_sub.groupby("date")
        .agg(
            turnover_sum=("turnover", "sum"),
            transaction_cost=("transaction_cost", "sum"),
            risk_on=("risk_on", "any"),
            n_candidates_with_rows=("candidate_id", "count"),
        )
        .reset_index()
    )
    reb_agg["turnover"] = reb_agg["turnover_sum"] / n_candidates
    reb_agg["transaction_cost"] = reb_agg["transaction_cost"] / n_candidates
    reb_agg = reb_agg.rename(columns={"n_candidates_with_rows": "n_candidates"})
    reb_eq = reb_agg[["date", "turnover", "transaction_cost", "risk_on", "n_candidates"]].sort_values("date")

    # join portfolio turnover onto daily for cost sensitivity
    daily_eq = daily_eq.merge(
        reb_eq[["date", "turnover"]].rename(columns={"turnover": "reb_turnover"}),
        on="date", how="left"
    )
    daily_eq["reb_turnover"] = daily_eq["reb_turnover"].fillna(0.0)

    # reconstruct equity from daily returns (base 15_000)
    daily_eq["equity"] = 15_000.0
    for i in range(1, len(daily_eq)):
        daily_eq.iloc[i, daily_eq.columns.get_loc("equity")] = (
            daily_eq.iloc[i - 1]["equity"] * (1 + daily_eq.iloc[i]["daily_return"])
        )

    daily_eq["peak"]     = daily_eq["equity"].cummax()
    daily_eq["drawdown"] = daily_eq["equity"] / daily_eq["peak"] - 1

    return daily_eq, reb_eq


def get_oos_splits(daily_eq: pd.DataFrame) -> tuple[date, date, date]:
    start = daily_eq["date"].min().date()
    end   = daily_eq["date"].max().date()
    total_days = (end - start).days
    oos_start_days = int(OOS_YEAR_OFFSET * 365.25)
    recent_start_days = int((OOS_YEAR_OFFSET + (total_days / 365.25 - OOS_YEAR_OFFSET - RECENT_YEAR_OFFSET)) * 365.25)
    oos_start  = pd.Timestamp(start) + pd.Timedelta(days=oos_start_days)
    recent_start = daily_eq["date"].max() - pd.DateOffset(years=int(RECENT_YEAR_OFFSET))
    return oos_start.date(), recent_start.date(), end


# ── metric computations ───────────────────────────────────────────────────────

def rebalance_frequency(reb_eq: pd.DataFrame) -> dict:
    non_zero = reb_eq[reb_eq["turnover"] > 0.0001].copy()
    non_zero = non_zero.sort_values("date")
    intervals = non_zero["date"].diff().dt.days.dropna()
    total_days = (reb_eq["date"].max() - reb_eq["date"].min()).days
    years = total_days / 365.25

    return {
        "total_rebalance_rows":   len(reb_eq),
        "nonzero_rebalance_rows": len(non_zero),
        "rebalances_per_year":    round(len(non_zero) / years, 1) if years else 0,
        "avg_interval_days":      round(intervals.mean(), 1) if len(intervals) else None,
        "median_interval_days":   round(intervals.median(), 1) if len(intervals) else None,
        "max_interval_days":      int(intervals.max()) if len(intervals) else None,
        "data_years":             round(years, 2),
    }


def turnover_summary(reb_eq: pd.DataFrame, daily_eq: pd.DataFrame,
                     oos_start: date, recent_start: date) -> dict:
    non_zero = reb_eq[reb_eq["turnover"] > 0.0001]

    def ann_to(mask_reb, mask_daily):
        sub  = reb_eq[mask_reb]
        days = daily_eq[mask_daily]
        if len(days) < 2:
            return None
        yrs = (days["date"].max() - days["date"].min()).days / 365.25
        return round(sub["turnover"].sum() / yrs, 2) if yrs else None

    full_mask_reb    = pd.Series([True] * len(reb_eq), index=reb_eq.index)
    full_mask_daily  = pd.Series([True] * len(daily_eq), index=daily_eq.index)
    oos_mask_reb     = reb_eq["date"] >= pd.Timestamp(oos_start)
    oos_mask_daily   = daily_eq["date"] >= pd.Timestamp(oos_start)
    rec_mask_reb     = reb_eq["date"] >= pd.Timestamp(recent_start)
    rec_mask_daily   = daily_eq["date"] >= pd.Timestamp(recent_start)

    # annual turnover by calendar year
    reb_eq_nz = reb_eq.copy()
    reb_eq_nz["year"] = reb_eq_nz["date"].dt.year
    yearly = reb_eq_nz.groupby("year")["turnover"].sum()
    # approximate trading days per year ≈ 252
    daily_eq_c = daily_eq.copy()
    daily_eq_c["year"] = daily_eq_c["date"].dt.year
    tdays_per_year = daily_eq_c.groupby("year").size()
    yearly_ann = (yearly / (tdays_per_year / 252)).round(2)

    top10 = (
        reb_eq_nz[reb_eq_nz["turnover"] > 0.0001]
        .nlargest(10, "turnover")[["date", "turnover", "n_candidates"]]
        .assign(date=lambda x: x["date"].dt.strftime("%Y-%m-%d"))
        .to_dict("records")
    )

    return {
        "full_annual_turnover":    ann_to(full_mask_reb, full_mask_daily),
        "oos_annual_turnover":     ann_to(oos_mask_reb, oos_mask_daily),
        "recent_2y_annual_turnover": ann_to(rec_mask_reb, rec_mask_daily),
        "worst_year_turnover":     float(yearly_ann.max()) if len(yearly_ann) else None,
        "worst_year":              int(yearly_ann.idxmax()) if len(yearly_ann) else None,
        "median_year_turnover":    float(yearly_ann.median()) if len(yearly_ann) else None,
        "by_year":                 {str(k): round(float(v), 2) for k, v in yearly_ann.items()},
        "top10_largest_rebalances": top10,
        "convention_note": (
            "turnover is one-way fractional portfolio change per rebalance event, "
            "computed as mean across 6 equal-weight sub-candidates. "
            "turnover=1.0 means 100% one-way turnover."
        ),
    }


def cost_sensitivity(daily_eq: pd.DataFrame, reb_eq: pd.DataFrame,
                     oos_start: date, comp_row: dict) -> list[dict]:
    """
    Stress-test multiple cost levels.
    adjusted_daily_return = original_return - portfolio_turnover_on_day * cost_bps / 10000
    Portfolio turnover already joined onto daily_eq as 'reb_turnover'.
    """
    daily_c = daily_eq.copy().sort_values("date")

    results = []
    for bps in COST_BPS_LEVELS:
        cost_per_day = daily_c["reb_turnover"] * bps / 10_000
        adj_ret      = daily_c["daily_return"] - cost_per_day

        # full period
        n_years_full = (daily_c["date"].max() - daily_c["date"].min()).days / 365.25
        cumret_full  = (1 + adj_ret).prod() - 1
        ann_ret_full = (1 + cumret_full) ** (1 / n_years_full) - 1 if n_years_full > 0 else 0

        # max drawdown full
        eq_full = (1 + adj_ret).cumprod()
        peak_full = eq_full.cummax()
        dd_full = (eq_full / peak_full - 1).min()

        # OOS
        oos_mask  = daily_c["date"] >= pd.Timestamp(oos_start)
        oos_ret   = adj_ret[oos_mask]
        n_yrs_oos = oos_mask.sum() / 252
        cumret_oos = (1 + oos_ret).prod() - 1
        ann_ret_oos = (1 + cumret_oos) ** (1 / n_yrs_oos) - 1 if n_yrs_oos > 0 else 0

        # OOS Sharpe
        oos_sharpe = (oos_ret.mean() / oos_ret.std() * math.sqrt(252)
                      if oos_ret.std() > 0 else None)

        # OOS drawdown
        eq_oos  = (1 + oos_ret).cumprod()
        peak_oos = eq_oos.cummax()
        dd_oos  = (eq_oos / peak_oos - 1).min()

        # terminal equity ratio vs 0-cost baseline (using baseline from composite)
        baseline_final = comp_row.get("full_final", 523871)
        terminal_adj   = 15_000 * (1 + cumret_full)
        terminal_ratio = terminal_adj / baseline_final

        results.append({
            "cost_bps":         bps,
            "full_ann_ret_pct": round(ann_ret_full * 100, 2),
            "full_max_dd_pct":  round(dd_full * 100, 2),
            "oos_ann_ret_pct":  round(ann_ret_oos * 100, 2),
            "oos_max_dd_pct":   round(dd_oos * 100, 2),
            "oos_sharpe":       round(float(oos_sharpe), 2) if oos_sharpe else None,
            "terminal_ratio_vs_0bps": round(terminal_ratio, 3),
        })
    return results


def small_account_check(reb_eq: pd.DataFrame, daily_eq: pd.DataFrame) -> dict:
    """Estimate rebalance notional and rounding feasibility at various account sizes."""
    non_zero = reb_eq[reb_eq["turnover"] > 0.0001]["turnover"]
    avg_to   = float(non_zero.mean()) if len(non_zero) else 0
    worst_to = float(non_zero.max()) if len(non_zero) else 0

    notional_rows = []
    for n in NOTIONALS:
        avg_reb  = round(avg_to * n, 0)
        worst_reb = round(worst_to * n, 0)
        notional_rows.append({
            "notional_usd":       n,
            "avg_rebalance_usd":  avg_reb,
            "worst_rebalance_usd": worst_reb,
        })

    # check for rounding at 5k: from last known weights
    last_reb = reb_eq.sort_values("date").iloc[-1]
    # get individual sub-candidate last weights to check per-ticker
    rounding_risks = []
    # High share price names in V6-A universe
    high_price_names = ["US.AVGO", "US.AMZN", "US.GOOGL", "US.GLD", "US.BIL", "US.GOOGL"]
    # Approximate share prices as of pilot start (conservative estimate)
    approx_prices = {
        "US.AVGO":  550,
        "US.AMZN":  195,
        "US.GOOGL": 165,
        "US.GLD":   315,
        "US.BIL":    91,
    }
    # V6-A at 5k uses ~39% per name (2 names + cash)
    typical_weight = 0.39
    for code, price in approx_prices.items():
        shares_5k = (5_000 * typical_weight) / price
        if shares_5k < 1.5:
            rounding_risks.append({
                "code":        code,
                "approx_price": price,
                "shares_at_5k": round(shares_5k, 2),
                "risk":         "rounds_to_0_or_1 — significant drift",
            })
        else:
            rounding_risks.append({
                "code":         code,
                "approx_price": price,
                "shares_at_5k": round(shares_5k, 2),
                "risk":         "ok",
            })

    return {
        "avg_turnover_per_rebalance": round(avg_to, 4),
        "worst_turnover_per_rebalance": round(worst_to, 4),
        "notional_by_account_size":  notional_rows,
        "rounding_risks_at_5k":      rounding_risks,
        "note": (
            "rounding_risks based on approximate pilot weights (~39% per name, 2 names active). "
            "GLD and BIL carry lower rounding risk due to lower share price. "
            "AVGO at $550 may show 1-share rounding drift at 5k."
        ),
    }


def verdict(cost_rows: list[dict], to_summary: dict) -> tuple[str, str]:
    """PASS / WATCH / FAIL based on spec acceptance criteria."""
    # find 25 bps row
    row_25 = next(r for r in cost_rows if r["cost_bps"] == 25)
    oos_ret_25  = row_25["oos_ann_ret_pct"]
    oos_dd_0    = next(r for r in cost_rows if r["cost_bps"] == 0)["oos_max_dd_pct"]
    oos_dd_25   = row_25["oos_max_dd_pct"]
    dd_worsening = oos_dd_25 - oos_dd_0   # negative = worse

    if oos_ret_25 >= 25 and abs(dd_worsening) <= 3:
        result = "PASS"
        reason = (
            f"OOS annual return after 25 bps = {oos_ret_25:.1f}% (≥25% threshold). "
            f"OOS max drawdown worsening = {abs(dd_worsening):.2f}pp (≤3pp threshold). "
            f"Strategy remains viable after realistic cost assumptions."
        )
    elif oos_ret_25 >= 18:
        result = "WATCH"
        reason = (
            f"OOS annual return after 25 bps = {oos_ret_25:.1f}% (18-25% band). "
            f"OOS max drawdown worsening = {abs(dd_worsening):.2f}pp. "
            f"Acceptable but monitor cost leakage at scale."
        )
    else:
        result = "FAIL"
        reason = (
            f"OOS annual return after 25 bps = {oos_ret_25:.1f}% (<18% threshold). "
            f"Strategy may not survive realistic execution costs."
        )
    return result, reason


# ── report ────────────────────────────────────────────────────────────────────

def build_report(
    tag: str,
    freq: dict,
    to_sum: dict,
    cost_rows: list[dict],
    acct: dict,
    result: str,
    reason: str,
    oos_start: date,
    recent_start: date,
    sub_candidates: list[str],
) -> str:
    cost_table = "| Cost (bps) | Full Ann% | Full MaxDD% | OOS Ann% | OOS MaxDD% | OOS Sharpe | Terminal Ratio |\n"
    cost_table += "|---|---|---|---|---|---|---|\n"
    for r in cost_rows:
        cost_table += (
            f"| {r['cost_bps']} | {r['full_ann_ret_pct']} | {r['full_max_dd_pct']} "
            f"| {r['oos_ann_ret_pct']} | {r['oos_max_dd_pct']} "
            f"| {r['oos_sharpe'] or '—'} | {r['terminal_ratio_vs_0bps']} |\n"
        )

    top10_table = "| Date | Turnover | N Candidates |\n|---|---|---|\n"
    for e in to_sum["top10_largest_rebalances"]:
        top10_table += f"| {e['date']} | {e['turnover']:.4f} | {e['n_candidates']} |\n"

    notional_table = "| Account USD | Avg Rebal USD | Worst Rebal USD |\n|---|---|---|\n"
    for n in acct["notional_by_account_size"]:
        notional_table += f"| {n['notional_usd']:,} | {n['avg_rebalance_usd']:,.0f} | {n['worst_rebalance_usd']:,.0f} |\n"

    rounding_table = "| Code | Approx Price | Shares@5k | Risk |\n|---|---|---|---|\n"
    for r in acct["rounding_risks_at_5k"]:
        rounding_table += f"| {r['code']} | ${r['approx_price']} | {r['shares_at_5k']} | {r['risk']} |\n"

    yearly_rows = "\n".join(f"| {yr} | {tv} |" for yr, tv in sorted(to_sum["by_year"].items()))

    verdict_icon = "✅" if result == "PASS" else ("⚠️" if result == "WATCH" else "❌")

    return f"""# V6-A Turnover / Cost Audit

- Tag: `{tag}`
- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Strategy: `ATTACK_EQUAL_REPLAY` (equal-weight of {len(sub_candidates)} sub-candidates: {', '.join(sub_candidates)})
- OOS start: {oos_start}  |  Recent start: {recent_start}

---

## 1. Executive Conclusion: {verdict_icon} {result}

{reason}

> **Automation implication**: V6-A is {'suitable for small-account manual pilot with cost-aware execution' if result in ('PASS','WATCH') else 'NOT recommended for automation until turnover/cost profile is addressed'}.
> Kill switch remains ON until pilot review passes preflight gate.

---

## 2. Rebalance Frequency

| Metric | Value |
|---|---|
| Data span (years) | {freq['data_years']} |
| Total rebalance rows | {freq['total_rebalance_rows']} |
| Non-zero rebalance rows | {freq['nonzero_rebalance_rows']} |
| Rebalances per year | {freq['rebalances_per_year']} |
| Avg interval (days) | {freq['avg_interval_days']} |
| Median interval (days) | {freq['median_interval_days']} |
| Max interval without rebalance | {freq['max_interval_days']} days |

---

## 3. Turnover Summary

| Period | Ann. Turnover |
|---|---|
| Full period | {to_sum['full_annual_turnover']} |
| OOS (from {oos_start}) | {to_sum['oos_annual_turnover']} |
| Recent 2 years | {to_sum['recent_2y_annual_turnover']} |
| Worst calendar year | {to_sum['worst_year_turnover']} ({to_sum['worst_year']}) |
| Median calendar year | {to_sum['median_year_turnover']} |

**Convention**: {to_sum['convention_note']}

### By Year
| Year | Ann. Turnover |
|---|---|
{yearly_rows}

---

## 4. Cost Sensitivity

{cost_table}

---

## 5. Top 10 Largest Single Rebalance Events

{top10_table}

---

## 6. Small-Account Feasibility

Avg turnover per rebalance: `{acct['avg_turnover_per_rebalance']}` | Worst: `{acct['worst_turnover_per_rebalance']}`

### Rebalance Notional by Account Size

{notional_table}

### Rounding Risks at $5,000 Pilot

{rounding_table}

{acct['note']}

---

## 7. Data Caveats

- `ATTACK_EQUAL_REPLAY` daily returns and turnover computed as **simple mean of 6 sub-candidates** ({', '.join(sub_candidates)}). This matches the equal-weight portfolio construction convention.
- Equity series reconstructed from daily returns; absolute dollar values are illustrative.
- OOS split inferred from composite file metadata (train_years=7.6 → OOS start ≈ {oos_start}).
- Cost sensitivity uses one-way cost applied on rebalance days only. Spread/market impact not separately modeled.
- Share prices for rounding check are approximate as of 2026-05-11 pilot date.
- Futu historical K-line quota **not consumed** by this audit.
"""


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d"))
    args = parser.parse_args()
    tag = args.tag

    print(f"[V6-A Turnover Cost Audit] tag={tag}")
    print("  Loading data...")

    reb, daily, comp_row, sub_candidates = load_data()
    print(f"  Sub-candidates: {sub_candidates}")

    daily_eq, reb_eq = build_equal_replay(reb, daily, sub_candidates)
    oos_start, recent_start, end_date = get_oos_splits(daily_eq)
    print(f"  Data: {daily_eq['date'].min().date()} → {end_date}  |  OOS start: {oos_start}")

    print("  Computing metrics...")
    freq     = rebalance_frequency(reb_eq)
    to_sum   = turnover_summary(reb_eq, daily_eq, oos_start, recent_start)
    cost_rows = cost_sensitivity(daily_eq, reb_eq, oos_start, comp_row)
    acct     = small_account_check(reb_eq, daily_eq)
    result, reason = verdict(cost_rows, to_sum)

    print(f"\n  ── VERDICT: {result} ──")
    print(f"  {reason}\n")

    # ── output ────────────────────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    output = {
        "tag":              tag,
        "generated_at":     datetime.now().isoformat(),
        "strategy":         "ATTACK_EQUAL_REPLAY",
        "sub_candidates":   sub_candidates,
        "oos_start":        str(oos_start),
        "recent_start":     str(recent_start),
        "verdict":          result,
        "verdict_reason":   reason,
        "rebalance_frequency": freq,
        "turnover_summary":    to_sum,
        "cost_sensitivity":    cost_rows,
        "small_account_check": acct,
    }
    json_path = OUT_DIR / f"v6a_turnover_cost_audit_{tag}.json"
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"  ✓ JSON  → {json_path}")

    # CSV (cost sensitivity)
    csv_path = OUT_DIR / f"v6a_turnover_cost_audit_{tag}.csv"
    pd.DataFrame(cost_rows).to_csv(csv_path, index=False)
    print(f"  ✓ CSV   → {csv_path}")

    # Markdown
    report = build_report(tag, freq, to_sum, cost_rows, acct, result, reason,
                          oos_start, recent_start, sub_candidates)
    md_path = OUT_DIR / f"v6a_turnover_cost_audit_{tag}.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"  ✓ MD    → {md_path}")

    print(f"\nDone. Verdict: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
