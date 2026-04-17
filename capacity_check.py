#!/usr/bin/env python3
"""
只读流动性容量检查（Futu/OpenD）
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta

import pandas as pd
import pytz
from futu import OpenQuoteContext, RET_OK, OptionType, SubType


HOST = "127.0.0.1"
PORT = 11111
ASSETS = [
    {"ticker": "US.QQQ", "name": "QQQ", "base_groups": 4},
    {"ticker": "US.IWM", "name": "IWM", "base_groups": 2},
    {"ticker": "US.GLD", "name": "GLD", "base_groups": 2},
]
PUT_OTM = 0.03
CALL_OTM = 0.06
WING = 0.09
TARGET_DTE = 45
REAL_CAPITAL = 15_000
LEVERAGE = 2.0


def nearest_expiry(ctx: OpenQuoteContext, ticker: str) -> tuple[str, int]:
    ret, data = ctx.get_option_expiration_date(ticker)
    if ret != RET_OK or data.empty:
        raise RuntimeError(f"{ticker} expiration failed: {data}")

    et_today = datetime.now(pytz.timezone("America/New_York")).date()
    candidates = []
    for _, row in data.iterrows():
        if "strike_time" in row and pd.notna(row["strike_time"]):
            exp = datetime.strptime(str(row["strike_time"])[:10], "%Y-%m-%d").date()
        else:
            exp = et_today + timedelta(days=int(row.get("option_expiry_date_distance", 999)))
        dte = (exp - et_today).days
        if dte >= 7:
            candidates.append((exp, dte))
    exp, dte = min(candidates, key=lambda item: abs(item[1] - TARGET_DTE))
    return exp.strftime("%Y-%m-%d"), dte


def stock_price(ctx: OpenQuoteContext, ticker: str) -> float:
    ctx.subscribe([ticker], [SubType.QUOTE], subscribe_push=False)
    time.sleep(0.2)
    ret, data = ctx.get_stock_quote([ticker])
    if ret != RET_OK or data.empty:
        raise RuntimeError(f"{ticker} quote failed: {data}")
    return float(data.iloc[0]["last_price"])


def option_chain(ctx: OpenQuoteContext, ticker: str, opt_type, expiry: str) -> pd.DataFrame:
    ret, data = ctx.get_option_chain(ticker, option_type=opt_type, start=expiry, end=expiry)
    if ret != RET_OK or data.empty:
        raise RuntimeError(f"{ticker} chain failed: {data}")
    data = data.copy()
    data["strike_price"] = data["strike_price"].astype(float)
    return data


def closest_leg(chain: pd.DataFrame, target_strike: float) -> dict:
    row = chain.loc[(chain["strike_price"] - target_strike).abs().idxmin()]
    return {"code": str(row["code"]), "strike": float(row["strike_price"])}


def snapshot(ctx: OpenQuoteContext, codes: list[str]) -> pd.DataFrame:
    ret, data = ctx.get_market_snapshot(codes)
    if ret != RET_OK:
        raise RuntimeError(f"snapshot failed: {data}")
    return data.copy()


def order_book_depth(ctx: OpenQuoteContext, code: str) -> dict:
    ctx.subscribe([code], [SubType.ORDER_BOOK], subscribe_push=False)
    time.sleep(0.1)
    ret, data = ctx.get_order_book(code, num=10)
    if ret != RET_OK or not data:
        return {"bid_px": 0.0, "ask_px": 0.0, "bid_qty_10": 0, "ask_qty_10": 0}

    def parse(levels):
        total = 0
        px = 0.0
        for i, level in enumerate(levels or []):
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                if i == 0:
                    px = float(level[0])
                try:
                    total += int(float(level[1]))
                except Exception:
                    pass
        return px, total

    bid_px, bid_qty = parse(data.get("Bid", []))
    ask_px, ask_qty = parse(data.get("Ask", []))
    return {"bid_px": bid_px, "ask_px": ask_px, "bid_qty_10": bid_qty, "ask_qty_10": ask_qty}


def build_legs(ctx: OpenQuoteContext, ticker: str, price: float, expiry: str) -> dict:
    calls = option_chain(ctx, ticker, OptionType.CALL, expiry)
    puts = option_chain(ctx, ticker, OptionType.PUT, expiry)
    targets = {
        "sell_put": price * (1 - PUT_OTM),
        "buy_put": price * (1 - PUT_OTM - WING),
        "sell_call": price * (1 + CALL_OTM),
        "buy_call": price * (1 + CALL_OTM + WING),
    }
    return {
        "sell_put": closest_leg(puts, targets["sell_put"]),
        "buy_put": closest_leg(puts, targets["buy_put"]),
        "sell_call": closest_leg(calls, targets["sell_call"]),
        "buy_call": closest_leg(calls, targets["buy_call"]),
    }


def groups_from_capital(actual_capital: float, asset_base_groups: int) -> float:
    nominal = actual_capital * LEVERAGE
    scale = nominal / 30_000
    return asset_base_groups * scale


def main():
    ctx = OpenQuoteContext(host=HOST, port=PORT)
    rows = []
    try:
        for asset in ASSETS:
            ticker = asset["ticker"]
            price = stock_price(ctx, ticker)
            expiry, dte = nearest_expiry(ctx, ticker)
            legs = build_legs(ctx, ticker, price, expiry)
            codes = [leg["code"] for leg in legs.values()]
            snap = snapshot(ctx, codes)
            snap_by_code = snap.set_index("code") if "code" in snap.columns else pd.DataFrame()
            for leg_name, leg in legs.items():
                code = leg["code"]
                row = snap_by_code.loc[code] if code in snap_by_code.index else {}
                book = order_book_depth(ctx, code)
                bid = float(row.get("bid_price", book["bid_px"]) or 0)
                ask = float(row.get("ask_price", book["ask_px"]) or 0)
                volume = int(float(row.get("volume", 0) or 0))
                oi = int(float(row.get("open_interest", row.get("option_open_interest", 0)) or 0))
                rows.append({
                    "asset": asset["name"],
                    "ticker": ticker,
                    "underlying": round(price, 2),
                    "expiry": expiry,
                    "dte": dte,
                    "leg": leg_name,
                    "code": code,
                    "strike": leg["strike"],
                    "bid": bid,
                    "ask": ask,
                    "spread": round(max(ask - bid, 0), 3),
                    "mid": round((bid + ask) / 2, 3) if bid and ask else 0,
                    "volume": volume,
                    "open_interest": oi,
                    "bid_qty_10": book["bid_qty_10"],
                    "ask_qty_10": book["ask_qty_10"],
                })
    finally:
        ctx.close()

    df = pd.DataFrame(rows)
    out = "backtest_results/capacity_check_snapshot.csv"
    df.to_csv(out, index=False)

    print(df.to_string(index=False))
    print(f"\nCSV: {out}")
    print("\nCurrent F=20x hard cap at actual capital $300,000 (nominal $600,000):")
    for asset in ASSETS:
        print(f"  {asset['name']}: {groups_from_capital(300_000, asset['base_groups']):.0f} groups")

    print("\nLiquidity bottleneck rough capacities by per-leg ADV%:")
    for asset in ASSETS:
        sub = df[df["asset"] == asset["name"]]
        nonzero_vol = sub["volume"][sub["volume"] > 0]
        nonzero_oi = sub["open_interest"][sub["open_interest"] > 0]
        min_volume = int(nonzero_vol.min()) if not nonzero_vol.empty else 0
        min_oi = int(nonzero_oi.min()) if not nonzero_oi.empty else 0
        min_book = int(sub[["bid_qty_10", "ask_qty_10"]].replace(0, math.inf).min().min()) if not sub.empty else 0
        if min_book == math.inf:
            min_book = 0
        for adv_pct in (0.01, 0.03, 0.05):
            groups_cap = min_volume * adv_pct if min_volume else 0
            actual_cap = groups_cap / asset["base_groups"] * 30_000 / LEVERAGE
            print(
                f"  {asset['name']} @ {adv_pct:.0%} min-leg volume: "
                f"{groups_cap:,.0f} groups ≈ actual ${actual_cap:,.0f} (nominal ${actual_cap*2:,.0f}); "
                f"min_leg_vol={min_volume:,}, min_leg_OI={min_oi:,}, min_10lvl_book={min_book:,}"
            )


if __name__ == "__main__":
    main()
