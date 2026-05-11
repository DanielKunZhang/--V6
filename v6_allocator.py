#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


def as_float(value: Any, default: float = float("nan")) -> float:
    try:
        return float(value)
    except Exception:
        return default


def load_metrics(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return pd.DataFrame(raw if isinstance(raw, list) else raw.get("sleeves", []))
    return pd.read_csv(path)


def find_sleeve(df: pd.DataFrame, name: str) -> dict[str, Any] | None:
    if "sleeve" not in df.columns:
        return None
    rows = df[df["sleeve"] == name]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def hard_block(row: dict[str, Any], policy: dict[str, Any]) -> str | None:
    for key in policy.get("hard_blocks", []):
        value = row.get(key)
        if value is True or str(value).lower() in {"true", "1", "yes", "failed"}:
            return key
    return None


def allocate(policy: dict[str, Any], metrics: pd.DataFrame) -> dict[str, Any]:
    weights = policy["default_weights"].copy()
    notes: list[str] = []

    v6a = find_sleeve(metrics, "V6-A")
    v6b = find_sleeve(metrics, "V6-B")
    if not v6a or not v6b:
        return {
            "allocation_case": "weak_or_unproven",
            "weights": weights,
            "notes": ["missing V6-A or V6-B metrics; default to V6-A"],
        }

    block = hard_block(v6b, policy)
    if block:
        return {
            "allocation_case": "weak_or_unproven",
            "weights": weights,
            "notes": [f"V6-B hard blocked: {block}"],
        }

    th = policy["thresholds"]
    v6a_oos = as_float(v6a.get("oos_ann_ret"))
    v6b_oos = as_float(v6b.get("oos_ann_ret"))
    v6a_sharpe = as_float(v6a.get("oos_sharpe"))
    v6b_sharpe = as_float(v6b.get("oos_sharpe"))
    v6a_dd = as_float(v6a.get("full_max_dd"))
    v6b_dd = as_float(v6b.get("full_max_dd"))
    corr = as_float(v6b.get("correlation_to_v6a"), 1.0)
    stable_windows = int(as_float(v6b.get("stable_windows_passed"), 0))

    if v6b_dd < v6a_dd - th["max_drawdown_worse_pct"]:
        return {
            "allocation_case": "weak_or_unproven",
            "weights": weights,
            "notes": [f"V6-B drawdown too weak: {v6b_dd:.2f}% vs V6-A {v6a_dd:.2f}%"],
        }

    sharpe_ok = v6b_sharpe >= v6a_sharpe + th["min_oos_sharpe_delta"]
    ann_delta = v6b_oos - v6a_oos

    if stable_windows >= th["stable_upgrade_min_windows"] and sharpe_ok and ann_delta >= 0:
        case = "stable_upgrade"
        notes.append("V6-B passed enough stable windows; allow 50/50 research allocation.")
    elif corr <= th["low_correlation_threshold"] and sharpe_ok and ann_delta >= 0:
        case = "low_corr_complement"
        notes.append("V6-B is low-correlation complement with acceptable OOS Sharpe.")
    elif corr >= th["high_correlation_threshold"] and sharpe_ok and ann_delta >= th["min_oos_ann_delta_for_high_corr"]:
        case = "high_corr_watchlist"
        notes.append("V6-B is high-correlation but materially stronger; allow small sleeve.")
    else:
        case = "weak_or_unproven"
        notes.append("V6-B has not earned capital weight; keep default V6-A.")

    weights = policy["candidate_weights"][case].copy()
    return {
        "allocation_case": case,
        "weights": weights,
        "inputs": {
            "v6a_oos_ann_ret": v6a_oos,
            "v6b_oos_ann_ret": v6b_oos,
            "v6a_oos_sharpe": v6a_sharpe,
            "v6b_oos_sharpe": v6b_sharpe,
            "v6a_full_max_dd": v6a_dd,
            "v6b_full_max_dd": v6b_dd,
            "correlation_to_v6a": corr,
            "stable_windows_passed": stable_windows,
        },
        "notes": notes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule-based allocator for V6 sleeves.")
    parser.add_argument("--policy", default="v6_strategy_lab/configs/v6_allocator_policy_v1.json")
    parser.add_argument("--metrics", required=True, help="CSV or JSON with sleeve-level metrics.")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    metrics = load_metrics(Path(args.metrics))
    result = allocate(policy, metrics)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
