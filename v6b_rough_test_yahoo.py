"""
V6-B Rough Test — Yahoo Finance Data
======================================
WARNING: ROUGH_TEST_NO_POINT_IN_TIME
  - Universe chosen with hindsight (tickers added to seed in 2026-05-10)
  - Full 2018–2026 history used for ALL tickers
  - Results are directional signals only, NOT evidence for Allocator decisions
  - Point-in-time validated test must wait for Futu K-line quota (~2026-06-01)

Purpose:
  - Do V6-B candidates have momentum alpha at all?
  - Does V6-B pool outperform / underperform V6-A pool?
  - Which individual tickers fit the engine best?
  - Are there sub-pools (bottleneck / core_reaccel) that work differently?

Engine: simplified V6-A logic (momentum ranking + risk-on/off + defensive switch)
Data:   Yahoo Finance via yfinance, cached locally on first run
"""

from __future__ import annotations
import argparse
import json
import os, sys, time, warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

try:
    import akshare as ak
    _HAS_AKSHARE = True
except ImportError:
    _HAS_AKSHARE = False

warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent
CACHE_DIR = ROOT / "backtest_results" / "v6b_rough_test" / "price_cache"
OUT_DIR   = ROOT / "backtest_results" / "v6b_rough_test"
V3_CACHE  = ROOT / "cash_alpha_v3_repo" / "backtest_results" / "price_cache"
SEED_PATH = ROOT / "v6_strategy_lab" / "configs" / "v6b_point_in_time_universe_seed_20260510.json"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Date range ─────────────────────────────────────────────────────────────────
START = "2018-01-01"
END   = "2026-05-12"

# ── Engine constants ──────────────────────────────────────────────────────────
INITIAL_CAPITAL = 10_000.0
TRADING_DAYS    = 252
RISK_FREE       = 0.05

# ── Universe definitions ──────────────────────────────────────────────────────
# V6-B seed (from v6b_point_in_time_universe_seed_20260510.json)
V6B_CORE_REACCEL    = ["AMD", "ANET", "TSM"]
V6B_BOTTLENECK      = ["MU", "WDC", "AMKR"]
V6B_TURNAROUND      = ["INTC"]
V6B_WATCH_EXTRA     = ["AAOI", "COHR"]   # from diffusion map v1 Layer 3

# V6-A current pool (ai_mega) — for comparison
V6A_POOL = ["NVDA", "AVGO", "MSFT", "AMZN", "META", "GOOGL"]

# Defensive assets
DEFENSIVE = {"GLD": 0.45, "BIL": 0.35, "CASH": 0.20}

# Market regime filters
REGIME_TICKERS = ["QQQ", "SPY"]

# All tickers to download
ALL_TICKERS = sorted(set(
    V6B_CORE_REACCEL + V6B_BOTTLENECK + V6B_TURNAROUND +
    V6B_WATCH_EXTRA + V6A_POOL +
    list(k for k in DEFENSIVE if k != "CASH") +
    REGIME_TICKERS
))

# Pool configurations to compare
POOLS = {
    "V6-A  (ai_mega)         ": V6A_POOL,
    "V6-B  (core_reaccel)    ": V6B_CORE_REACCEL,
    "V6-B  (bottleneck)      ": V6B_BOTTLENECK,
    "V6-B  (full seed)       ": V6B_CORE_REACCEL + V6B_BOTTLENECK,
    "V6-B  (full+watch)      ": V6B_CORE_REACCEL + V6B_BOTTLENECK + V6B_WATCH_EXTRA,
    "V6-AB (blended)         ": V6A_POOL + V6B_CORE_REACCEL + V6B_BOTTLENECK,
    "V6-B  (turnaround ctrl) ": V6B_TURNAROUND,
}

# Engine parameter grid
ENGINE_PARAMS = [
    dict(trend_ma=100, market_ma=150, mom_days=60,  top_n=3, dd_stop=0.10, rebal=5,  label="base    (mom60  top3 dd10%)"),
    dict(trend_ma=100, market_ma=150, mom_days=120, top_n=3, dd_stop=0.10, rebal=5,  label="slow    (mom120 top3 dd10%)"),
    dict(trend_ma=100, market_ma=150, mom_days=60,  top_n=2, dd_stop=0.10, rebal=5,  label="conc    (mom60  top2 dd10%)"),
    dict(trend_ma=100, market_ma=150, mom_days=60,  top_n=3, dd_stop=0.15, rebal=5,  label="loose   (mom60  top3 dd15%)"),
]

# ── Data loading ──────────────────────────────────────────────────────────────

def _v3_cache_path(ticker: str) -> Path | None:
    """Check V3 local cache (QQQ, SPY already there)."""
    p = V3_CACHE / f"US_{ticker}_daily.csv"
    return p if p.exists() else None


def _local_cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker}_daily.csv"


def _load_csv(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path, parse_dates=["date"])
        df = df.rename(columns={"date": "Date"}).set_index("Date")
        df = df[["Open", "High", "Low", "Close"]].dropna()
        df = df.loc[START:END]
        return df if len(df) > 200 else None
    except Exception:
        return None


def _download_yf(ticker: str, retries: int = 3) -> pd.DataFrame | None:
    for attempt in range(retries):
        try:
            df = yf.download(ticker, start=START, end=END, interval="1d",
                             progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[["Open", "High", "Low", "Close"]].dropna()
            df.index = pd.to_datetime(df.index)
            if len(df) > 200:
                return df
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3 + attempt * 2)
    return None


def _save_csv(df: pd.DataFrame, path: Path):
    df.reset_index().rename(columns={"Date": "date"}).to_csv(path, index=False)


def _download_akshare(ticker: str) -> pd.DataFrame | None:
    """Download via akshare as Yahoo fallback."""
    if not _HAS_AKSHARE:
        return None
    try:
        raw = ak.stock_us_daily(symbol=ticker, adjust="qfq")
        raw["date"] = pd.to_datetime(raw["date"])
        raw = raw.rename(columns={"open": "Open", "high": "High",
                                   "low": "Low", "close": "Close"})
        raw = raw.set_index("date")[["Open", "High", "Low", "Close"]].dropna()
        raw = raw.sort_index().loc[START:END]
        return raw if len(raw) > 200 else None
    except Exception:
        return None


def load_all_prices(cache_only: bool = False) -> dict[str, pd.DataFrame]:
    prices: dict[str, pd.DataFrame] = {}
    print("Loading price data...")
    for ticker in ALL_TICKERS:
        # 1. V3 local cache (QQQ, SPY, etc.)
        v3p = _v3_cache_path(ticker)
        if v3p:
            df = _load_csv(v3p)
            if df is not None:
                prices[ticker] = df
                print(f"  {ticker:<8} V3 cache  {len(df)} bars")
                continue

        # 2. Our local cache
        local_p = _local_cache_path(ticker)
        if local_p.exists():
            df = _load_csv(local_p)
            if df is not None:
                prices[ticker] = df
                print(f"  {ticker:<8} local     {len(df)} bars")
                continue

        if cache_only:
            print(f"  {ticker:<8} missing cache (cache-only)")
            continue

        # 3. Download from akshare (preferred when Yahoo is rate-limited)
        print(f"  {ticker:<8} downloading (akshare)...", end="", flush=True)
        df = _download_akshare(ticker)
        if df is not None:
            _save_csv(df, local_p)
            prices[ticker] = df
            print(f" {len(df)} bars  ✓")
            time.sleep(0.5)
            continue
        print(" akshare failed, trying Yahoo...", end="", flush=True)

        # 4. Fallback to Yahoo Finance
        df = _download_yf(ticker)
        if df is not None:
            _save_csv(df, local_p)
            prices[ticker] = df
            print(f" {len(df)} bars  ✓")
        else:
            print(f" FAILED — skipping")
        time.sleep(1.5)

    return prices


def build_price_matrix(prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Align all tickers to common trading days using Close prices."""
    closes = {t: df["Close"] for t, df in prices.items()}
    px = pd.DataFrame(closes)
    px.index = pd.to_datetime(px.index)
    px = px.sort_index().loc[START:END]
    # Forward-fill up to 3 days for minor gaps
    px = px.ffill(limit=3)
    return px


def load_activation_dates(seed_path: Path) -> dict[str, pd.Timestamp]:
    if not seed_path.exists():
        return {}
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    dates: dict[str, pd.Timestamp] = {}
    for row in payload.get("entries", []):
        ticker = row.get("ticker")
        entry_date = row.get("entry_date")
        status = row.get("status")
        if not ticker or not entry_date or status != "active_research":
            continue
        ticker_plain = str(ticker).replace("US.", "")
        dates[ticker_plain] = pd.Timestamp(entry_date)
    return dates


# ── Engine ────────────────────────────────────────────────────────────────────

def run_engine(px: pd.DataFrame, risk_pool: list[str],
               params: dict,
               activation_dates: dict[str, pd.Timestamp] | None = None,
               always_active_tickers: set[str] | None = None) -> tuple[pd.Series, dict]:
    """
    Simplified V6-A engine on a given risk pool.
    Returns (equity_series, metrics_dict).
    """
    activation_dates = activation_dates or {}
    always_active_tickers = always_active_tickers or set()
    needed = risk_pool + [k for k in DEFENSIVE if k != "CASH"] + ["QQQ", "SPY"]
    available = [t for t in needed if t in px.columns]
    missing   = [t for t in needed if t not in px.columns]
    if missing:
        return pd.Series(dtype=float), {"error": f"missing: {missing}"}

    sub = px[available].dropna(how="all").copy()
    # Only keep rows where all regime + defensive assets are present
    regime_def = [t for t in ["QQQ", "SPY", "GLD", "BIL"] if t in available]
    sub = sub.dropna(subset=regime_def)
    # Fill gaps in risk assets (some stocks may not exist for full history)
    sub[risk_pool] = sub[risk_pool].ffill(limit=3)
    sub = sub.dropna(subset=risk_pool, how="all")

    if len(sub) < 200:
        return pd.Series(dtype=float), {"error": "insufficient data after alignment"}

    rets     = sub.pct_change().fillna(0.0)
    qqq      = sub["QQQ"]
    spy      = sub["SPY"]
    trend    = qqq.rolling(params["trend_ma"]).mean()
    slow_ma  = spy.rolling(params["market_ma"]).mean()
    risk_mom = {t: sub[t].pct_change(params["mom_days"]) for t in risk_pool if t in sub}

    equity       = INITIAL_CAPITAL
    peak         = equity
    stopped      = False
    cur_w        = {"CASH": 1.0}
    equity_curve = []

    for idx, dt in enumerate(sub.index):
        # Daily P&L
        day_ret = cur_w.get("CASH", 0.0) * (RISK_FREE / TRADING_DAYS)
        for t, w in cur_w.items():
            if t == "CASH":
                continue
            if t in rets.columns:
                day_ret += w * float(rets.loc[dt, t])
        equity = max(equity * (1 + day_ret), 0.0)
        peak   = max(peak, equity)
        dd     = equity / peak - 1.0

        # Drawdown stop
        if dd <= -params["dd_stop"]:
            stopped = True
        if stopped and qqq.loc[dt] > (trend.loc[dt] or 0):
            stopped = False
            peak = equity

        # Rebalance
        if idx % params["rebal"] == 0:
            qqq_ok    = pd.notna(trend.loc[dt]) and qqq.loc[dt] > trend.loc[dt]
            spy_ok    = pd.notna(slow_ma.loc[dt]) and spy.loc[dt] > slow_ma.loc[dt]
            risk_on   = (not stopped) and qqq_ok and spy_ok

            if risk_on:
                # Rank eligible tickers by momentum, pick top-N
                scores = {}
                for t in risk_pool:
                    activation_dt = activation_dates.get(t)
                    if activation_dates and activation_dt is None and t not in always_active_tickers:
                        continue
                    if activation_dt is not None and dt < activation_dt:
                        continue
                    if t in risk_mom and pd.notna(risk_mom[t].loc[dt]):
                        scores[t] = float(risk_mom[t].loc[dt])
                if scores:
                    ranked = sorted(scores, key=scores.get, reverse=True)
                    chosen = [t for t in ranked if scores[t] > 0][:params["top_n"]]
                    if chosen:
                        w_each = 1.0 / len(chosen)
                        cur_w  = {t: w_each for t in chosen}
                    else:
                        cur_w = {k: v for k, v in DEFENSIVE.items()}
                else:
                    cur_w = {k: v for k, v in DEFENSIVE.items()}
            else:
                cur_w = {k: v for k, v in DEFENSIVE.items()}

        equity_curve.append(equity)

    eq = pd.Series(equity_curve, index=sub.index)
    return eq, _calc_metrics(eq)


def _calc_metrics(eq: pd.Series) -> dict:
    if len(eq) < 50:
        return {}
    dr        = eq.pct_change().dropna()
    n_years   = (eq.index[-1] - eq.index[0]).days / 365.25
    total_ret = eq.iloc[-1] / eq.iloc[0] - 1
    ann_ret   = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1 if n_years > 0 else 0
    roll_max  = eq.cummax()
    max_dd    = ((eq - roll_max) / roll_max).min()
    rf_d      = RISK_FREE / TRADING_DAYS
    sharpe    = (dr - rf_d).mean() / dr.std() * np.sqrt(TRADING_DAYS) if dr.std() > 0 else 0
    calmar    = ann_ret / abs(max_dd) if max_dd < 0 else 0

    # OOS split (last 2 years)
    oos_start = eq.index[eq.index >= "2024-01-01"][0] if any(eq.index >= "2024-01-01") else eq.index[-1]
    eq_oos    = eq.loc[oos_start:]
    if len(eq_oos) > 50:
        dr_oos    = eq_oos.pct_change().dropna()
        n_oos     = (eq_oos.index[-1] - eq_oos.index[0]).days / 365.25
        oos_ann   = (eq_oos.iloc[-1] / eq_oos.iloc[0]) ** (1 / n_oos) - 1 if n_oos > 0 else 0
        oos_sh    = (dr_oos - rf_d).mean() / dr_oos.std() * np.sqrt(TRADING_DAYS) if dr_oos.std() > 0 else 0
        rm_oos    = eq_oos.cummax()
        oos_dd    = ((eq_oos - rm_oos) / rm_oos).min()
    else:
        oos_ann = oos_sh = oos_dd = float("nan")

    return dict(
        ann_ret=ann_ret, total_ret=total_ret, max_dd=max_dd,
        sharpe=sharpe, calmar=calmar,
        oos_ann=oos_ann, oos_sharpe=oos_sh, oos_dd=oos_dd,
        n_years=round(n_years, 1),
        final_equity=round(eq.iloc[-1], 0),
    )


def buy_hold(px: pd.DataFrame, tickers: list[str]) -> tuple[pd.Series, dict]:
    """Equal-weight buy-and-hold for a list of tickers."""
    avail = [t for t in tickers if t in px.columns]
    if not avail:
        return pd.Series(dtype=float), {}
    sub = px[avail].dropna(how="all").ffill(limit=3).dropna()
    rets = sub.pct_change().fillna(0.0)
    eq = INITIAL_CAPITAL * (1 + rets.mean(axis=1)).cumprod()
    return eq, _calc_metrics(eq)


# ── Reporting ─────────────────────────────────────────────────────────────────

GATE = dict(ann_ret=0.18, sharpe=0.80, oos_sharpe=0.60, max_dd=-0.35)


def _gate_flag(m: dict) -> str:
    if not m:
        return "ERR"
    if (m.get("ann_ret", 0) >= GATE["ann_ret"] and
            m.get("sharpe", 0) >= GATE["sharpe"] and
            m.get("oos_sharpe", 0) >= GATE["oos_sharpe"] and
            m.get("max_dd", -1) >= GATE["max_dd"]):
        return "✓"
    return " "


def print_section(title: str, rows: list[dict]):
    print(f"\n{'═'*120}")
    print(f"  {title}")
    print('═'*120)
    hdr = (f"  {'Config':<45} {'Pool / Tickers':<32} "
           f"{'AnnR':>6} {'OOS':>6} {'MaxDD':>7} {'Sh':>5} {'OOS-Sh':>6} "
           f"{'Final$':>7}  Gate")
    print(hdr)
    print('─'*120)
    for r in rows:
        m = r.get("m", {})
        if not m or "error" in m:
            print(f"  {r['label']:<45} {r['pool_str']:<32}  [no data / {m.get('error','')}]")
            continue
        gate = _gate_flag(m)
        print(f"  {r['label']:<45} {r['pool_str']:<32} "
              f"{m['ann_ret']*100:>+5.1f}% "
              f"{m['oos_ann']*100:>+5.1f}% "
              f"{m['max_dd']*100:>+6.1f}% "
              f"{m['sharpe']:>5.2f} "
              f"{m['oos_sharpe']:>6.2f} "
              f"${m['final_equity']:>6,.0f}  {gate}")
    print(f"\n  ✓ = AnnR≥18%  Sharpe≥0.8  OOS-Sharpe≥0.6  MaxDD≥-35%")


def write_markdown(all_sections: list[dict], path: Path, status_label: str, notes: list[str]):
    lines = [
        "# V6-B Rough Test — Yahoo Finance Data",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Status: **{status_label}**",
        "- Data: Yahoo Finance daily OHLCV (yfinance)",
        "- Scope: 2018-01-01 – 2026-05-12",
        "- OOS split: 2024-01-01 – 2026-05-12",
        "",
    ]
    for note in notes:
        lines.append(f"> {note}")
    lines.append("")
    for sec in all_sections:
        lines.append(f"## {sec['title']}")
        lines.append("")
        lines.append(f"| Config | Pool | AnnR | OOS | MaxDD | Sharpe | OOS-Sh | Final$ | Gate |")
        lines.append(f"|--------|------|-----:|----:|------:|-------:|-------:|-------:|:----:|")
        for r in sec["rows"]:
            m = r.get("m", {})
            if not m or "error" in m:
                lines.append(f"| {r['label']} | {r['pool_str']} | — | — | — | — | — | — | ERR |")
                continue
            gate = _gate_flag(m)
            lines.append(
                f"| {r['label']} | {r['pool_str']} "
                f"| {m['ann_ret']*100:+.1f}% "
                f"| {m['oos_ann']*100:+.1f}% "
                f"| {m['max_dd']*100:.1f}% "
                f"| {m['sharpe']:.2f} "
                f"| {m['oos_sharpe']:.2f} "
                f"| ${m['final_equity']:,.0f} "
                f"| {gate} |"
            )
        lines.append("")
    path.write_text("\n".join(lines))
    print(f"\n  Report → {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run V6-B rough probe using local caches / optional entry-date discipline.")
    parser.add_argument("--respect-entry-dates", action="store_true", help="Mask V6-B tickers before their seed entry_date.")
    parser.add_argument("--cache-only", action="store_true", help="Use only local caches; do not download data.")
    parser.add_argument("--tag", default="", help="Optional tag suffix for markdown report.")
    args = parser.parse_args()

    activation_dates = load_activation_dates(SEED_PATH) if args.respect_entry_dates else {}
    always_active_tickers = set(V6A_POOL) if args.respect_entry_dates else set()
    status_label = "ENTRY_DATE_RESPECTED_PROBE" if args.respect_entry_dates else "ROUGH_TEST_NO_POINT_IN_TIME"
    notes = []
    if args.respect_entry_dates:
        notes.extend(
            [
                "⚠️  This is NOT a formal point-in-time historical backtest.",
                "The probe respects `entry_date` from the 2026-05-10 V6-B seed, so V6-B names are inactive before that date.",
                "Interpretation: this can test whether earlier rough-test conclusions were inflated by premature activation, but it still cannot validate long-term V6-B edge.",
            ]
        )
    else:
        notes.extend(
            [
                "⚠️  This is a look-ahead biased rough test. Universe selected with 2026-05-10 knowledge.",
                "Results are directional signals only. NOT valid for Allocator weight decisions.",
                "Point-in-time validated test requires Futu K-line quota (~2026-06-01).",
            ]
        )

    print("=" * 70)
    print(f"  V6-B Rough Test  [{status_label}]")
    print("=" * 70)

    # 1. Load prices
    prices = load_all_prices(cache_only=args.cache_only)
    px = build_price_matrix(prices)
    print(f"\nPrice matrix: {len(px)} days × {len(px.columns)} tickers  "
          f"[{px.index[0].date()} – {px.index[-1].date()}]")
    print(f"Available: {sorted(px.columns.tolist())}")

    all_sections = []

    # ── Section 1: Engine comparison across pools (base params) ──────────────
    print(f"\n{'═'*70}")
    print("  Running engine across pools (base params)...")
    rows_s1 = []
    bparams = ENGINE_PARAMS[0]
    for pool_label, pool in POOLS.items():
        avail = [t for t in pool if t in px.columns]
        if not avail:
            continue
        eq, m = run_engine(px, avail, bparams, activation_dates=activation_dates, always_active_tickers=always_active_tickers)
        rows_s1.append({
            "label": f"{pool_label}  [{bparams['label']}]",
            "pool_str": "+".join(avail),
            "m": m,
        })
    # Benchmark: QQQ buy-hold
    eq_bh, m_bh = buy_hold(px, ["QQQ"])
    rows_s1.append({"label": "Benchmark: QQQ buy-hold", "pool_str": "QQQ", "m": m_bh})
    eq_spy, m_spy = buy_hold(px, ["SPY"])
    rows_s1.append({"label": "Benchmark: SPY buy-hold", "pool_str": "SPY", "m": m_spy})

    sec1 = {"title": "Section 1 — Pool Comparison (base engine params, mom60 top3 dd10%)", "rows": rows_s1}
    all_sections.append(sec1)
    print_section(sec1["title"], sec1["rows"])

    # ── Section 2: Parameter sensitivity (V6-B full seed) ────────────────────
    print(f"\n{'═'*70}")
    print("  Running parameter sensitivity (V6-B full seed pool)...")
    rows_s2 = []
    v6b_full = [t for t in V6B_CORE_REACCEL + V6B_BOTTLENECK if t in px.columns]
    for p in ENGINE_PARAMS:
        eq, m = run_engine(px, v6b_full, p, activation_dates=activation_dates, always_active_tickers=always_active_tickers)
        rows_s2.append({
            "label": f"V6-B full seed  [{p['label']}]",
            "pool_str": "+".join(v6b_full),
            "m": m,
        })

    sec2 = {"title": "Section 2 — V6-B Full Seed: Parameter Sensitivity", "rows": rows_s2}
    all_sections.append(sec2)
    print_section(sec2["title"], sec2["rows"])

    # ── Section 3: Individual ticker buy-hold (engine-less alpha signal) ──────
    print(f"\n{'═'*70}")
    print("  Individual ticker buy-hold (raw momentum signal)...")
    rows_s3 = []
    all_individual = (V6B_CORE_REACCEL + V6B_BOTTLENECK +
                      V6B_WATCH_EXTRA + ["INTC"] + ["NVDA", "AVGO"])
    for t in all_individual:
        if t not in px.columns:
            continue
        eq, m = buy_hold(px, [t])
        track = ("core_reaccel" if t in V6B_CORE_REACCEL
                 else "bottleneck" if t in V6B_BOTTLENECK
                 else "watch" if t in V6B_WATCH_EXTRA
                 else "turnaround" if t == "INTC"
                 else "V6-A ref")
        rows_s3.append({
            "label": f"{t:<8} buy-hold  [{track}]",
            "pool_str": t,
            "m": m,
        })

    sec3 = {"title": "Section 3 — Individual Ticker Buy-Hold (raw alpha signal, no engine)", "rows": rows_s3}
    all_sections.append(sec3)
    print_section(sec3["title"], sec3["rows"])

    # ── Section 4: V6-B vs V6-A engine head-to-head ───────────────────────────
    print(f"\n{'═'*70}")
    print("  V6-B vs V6-A head-to-head across all param sets...")
    rows_s4 = []
    v6a_avail = [t for t in V6A_POOL if t in px.columns]
    v6b_avail = [t for t in V6B_CORE_REACCEL + V6B_BOTTLENECK if t in px.columns]
    for p in ENGINE_PARAMS:
        eq_a, m_a = run_engine(px, v6a_avail, p, activation_dates=activation_dates, always_active_tickers=always_active_tickers)
        eq_b, m_b = run_engine(px, v6b_avail, p, activation_dates=activation_dates, always_active_tickers=always_active_tickers)
        rows_s4.append({"label": f"V6-A  [{p['label']}]", "pool_str": "+".join(v6a_avail), "m": m_a})
        rows_s4.append({"label": f"V6-B  [{p['label']}]", "pool_str": "+".join(v6b_avail), "m": m_b})

    sec4 = {"title": "Section 4 — V6-A vs V6-B Head-to-Head (same engine, different pools)", "rows": rows_s4}
    all_sections.append(sec4)
    print_section(sec4["title"], sec4["rows"])

    # ── Write markdown report ─────────────────────────────────────────────────
    default_tag = "entry_date_respected" if args.respect_entry_dates else "lookahead"
    tag = args.tag or f"{default_tag}_{datetime.now().strftime('%Y%m%d_%H%M')}"
    md_path = OUT_DIR / f"v6b_rough_test_{tag}.md"
    write_markdown(all_sections, md_path, status_label=status_label, notes=notes)

    # ── Summary verdict ────────────────────────────────────────────────────────
    print(f"\n{'═'*70}")
    print("  ROUGH TEST VERDICT")
    print('═'*70)

    # Find best V6-B config from sec1
    v6b_rows = [r for r in rows_s1 if "V6-B" in r["label"] and r.get("m") and "error" not in r["m"]]
    v6a_row  = next((r for r in rows_s1 if "V6-A" in r["label"] and r.get("m")), None)

    if v6a_row and v6b_rows:
        best_v6b = max(v6b_rows, key=lambda r: r["m"].get("sharpe", -99))
        ma = v6a_row["m"]
        mb = best_v6b["m"]
        print(f"\n  Best V6-B config: {best_v6b['label'].strip()}")
        print(f"  {'':30} {'V6-A':>10} {'V6-B best':>10} {'delta':>8}")
        for k, label in [("ann_ret","AnnR"), ("sharpe","Sharpe"),
                          ("oos_sharpe","OOS-Sharpe"), ("max_dd","MaxDD")]:
            va = ma.get(k, float("nan"))
            vb = mb.get(k, float("nan"))
            scale = 100 if k in ("ann_ret","max_dd") else 1
            delta = (vb - va) * scale
            sym = "↑" if delta > 0 else "↓"
            print(f"  {label:30} {va*scale:>+9.2f}  {vb*scale:>+9.2f}  {sym}{abs(delta):>6.2f}")

    print(f"\n  ⚠  REMINDER: {status_label}")
    if args.respect_entry_dates:
        print("     Entry dates are respected, but historical winner generation is still missing.")
        print("     Treat this as an anti-lookahead sanity check, not as V6-B validation.")
    else:
        print("     These results use hindsight-selected universe.")
        print("     Do NOT use to set Allocator weights.")
        print("     Validated test: after Futu K-line quota refreshes (~2026-06-01)")
    print()


if __name__ == "__main__":
    main()
