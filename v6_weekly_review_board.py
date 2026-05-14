#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
REPORTING_DIR = ROOT / "backtest_results" / "v6_reporting"
PILOT_REVIEW_DIR = ROOT / "backtest_results" / "v6a_pilot_review"
PREFLIGHT_LATEST = ROOT / "backtest_results" / "v6_automation_preflight" / "latest.json"
V6A_PARAM_DIR = ROOT / "backtest_results" / "v6a_parameter_challenger"
V6A_ROBUSTNESS_DIR = ROOT / "backtest_results" / "v6a_parameter_robustness"
V6A_REAUDIT_DIR = ROOT / "backtest_results" / "v6a_challenger_turnover_cost_reaudit"
V6B_PROFILE_DIR = ROOT / "backtest_results" / "v6b_profile_search"
MISSING_REVIEW_LATEST = ROOT / "backtest_results" / "v6b_missing_opportunity_review" / "latest.json"
OUT_DIR = ROOT / "backtest_results" / "v6_weekly_review"
BACKLOG_DIR = ROOT / "backtest_results" / "v6_research_backlog"


def read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime)
    return files[-1] if files else None


def rel(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def summarize_v6a_positions(pilot_review: dict[str, Any]) -> dict[str, Any]:
    perf = pilot_review.get("performance", {}) if isinstance(pilot_review, dict) else {}
    rows = perf.get("by_ticker", []) if isinstance(perf.get("by_ticker"), list) else []
    total = float(perf.get("market_val_total") or 0.0)
    cleaned = []
    for row in rows:
        mv = float(row.get("market_val") or 0.0)
        weight = mv / total if total > 0 else 0.0
        cleaned.append(
            {
                "code": str(row.get("code") or ""),
                "market_val": mv,
                "weight": weight,
                "unrealized_pl_pct": float(row.get("unrealized_pl_pct") or 0.0),
            }
        )
    cleaned = sorted(cleaned, key=lambda item: item["market_val"], reverse=True)
    top3 = cleaned[:3]
    top3_weight = sum(item["weight"] for item in top3)
    return {
        "rows": cleaned,
        "top3": top3,
        "top3_weight": top3_weight,
        "market_val_total": total,
        "unrealized_pl_pct_points": float(perf.get("unrealized_pl_pct") or 0.0),
    }


def load_latest_v6a_parameter_candidate() -> dict[str, Any]:
    csv_path = latest_file(V6A_PARAM_DIR, "*.csv")
    if csv_path is None:
        return {}
    df = pd.read_csv(csv_path)
    if df.empty:
        return {}
    df["dd_pref_distance"] = (df["dd_stop"] - 0.10).abs()
    ranked = df.sort_values(
        ["gate_rank", "ann_delta", "sharpe_delta", "dd_worse", "dd_pref_distance"],
        ascending=[True, False, False, True, True],
    )
    top = ranked.iloc[0].to_dict()
    balanced_df = df[
        (df["gate"] == "promising_core_upgrade") &
        (df["top_n"] >= 3)
    ].sort_values(["sharpe_delta", "dd_worse", "ann_delta", "dd_pref_distance"], ascending=[False, True, False, True])
    balanced = balanced_df.iloc[0].to_dict() if not balanced_df.empty else top

    def pack(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": rel(csv_path),
            "label": str(row.get("label") or ""),
            "gate": str(row.get("gate") or ""),
            "top_n": int(row.get("top_n") or 0),
            "ann_ret": float(row.get("ann_ret") or 0.0),
            "max_dd": float(row.get("max_dd") or 0.0),
            "sharpe": float(row.get("sharpe") or 0.0),
            "ann_delta": float(row.get("ann_delta") or 0.0),
            "sharpe_delta": float(row.get("sharpe_delta") or 0.0),
            "dd_worse": float(row.get("dd_worse") or 0.0),
            "oos_sharpe": float(row.get("oos_sharpe") or 0.0),
            "oos_sharpe_delta": float(row.get("oos_sharpe_delta") or 0.0),
        }

    return {
        "path": rel(csv_path),
        "raw_top": pack(top),
        "balanced_top": pack(balanced),
    }


def load_latest_v6a_robustness() -> dict[str, Any]:
    json_path = latest_file(V6A_ROBUSTNESS_DIR, "*.json")
    payload = read_json(json_path) if json_path else {}
    if not payload:
        return {}
    return {
        "path": rel(json_path),
        "target_label": str(payload.get("target_label") or ""),
        "verdict": str(payload.get("verdict") or ""),
        "neighbor_count": int(payload.get("neighbor_count") or 0),
        "good_neighbor_count": int(payload.get("good_neighbor_count") or 0),
    }


def load_latest_v6a_reaudit() -> dict[str, Any]:
    json_path = latest_file(V6A_REAUDIT_DIR, "*.json")
    payload = read_json(json_path) if json_path else {}
    if not payload:
        return {}
    candidate = payload.get("candidate_params", {}) if isinstance(payload.get("candidate_params"), dict) else {}
    return {
        "path": rel(json_path),
        "candidate_label": str(candidate.get("label") or ""),
        "verdict": str(payload.get("preliminary_verdict") or ""),
        "baseline_summary": payload.get("baseline_summary", {}),
        "candidate_summary": payload.get("candidate_summary", {}),
    }


def load_latest_v6b_track_signal(profile_prefix: str) -> dict[str, Any]:
    csv_path = latest_file(V6B_PROFILE_DIR, f"{profile_prefix}_*.csv")
    if csv_path is None:
        return {}
    df = pd.read_csv(csv_path)
    if df.empty:
        return {}
    ranked = df.sort_values(
        ["track_gate_rank", "baseline_gate_rank", "track_ann_inc", "track_sharpe_inc", "vs_baseline_ann_delta"],
        ascending=[True, True, False, False, False],
    )
    top = ranked.iloc[0].to_dict()
    return {
        "path": rel(csv_path),
        "label": str(top.get("label") or ""),
        "baseline_gate": str(top.get("baseline_gate") or ""),
        "track_gate": str(top.get("track_gate") or ""),
        "ann_ret": float(top.get("ann_ret") or 0.0),
        "max_dd": float(top.get("max_dd") or 0.0),
        "sharpe": float(top.get("sharpe") or 0.0),
        "track_ann_inc": float(top.get("track_ann_inc") or 0.0),
        "track_sharpe_inc": float(top.get("track_sharpe_inc") or 0.0),
        "track_dd_inc": float(top.get("track_dd_inc") or 0.0),
    }


def load_latest_missing_review() -> dict[str, Any]:
    payload = read_json(MISSING_REVIEW_LATEST)
    if not payload:
        return {}
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    return {
        "path": rel(MISSING_REVIEW_LATEST),
        "as_of": str(payload.get("as_of") or ""),
        "critical_miss_count": int(summary.get("critical_miss_count") or 0),
        "watch_miss_count": int(summary.get("watch_miss_count") or 0),
        "active_weak_count": int(summary.get("active_weak_count") or 0),
        "coverage_gap_count": int(summary.get("coverage_gap_count") or 0),
        "theme_wakeup_count": int(summary.get("theme_wakeup_count") or 0),
        "critical_miss_tickers": [str(item) for item in summary.get("critical_miss_tickers", [])],
        "theme_wakeups": [str(item) for item in summary.get("theme_wakeups", [])],
    }


def build_backlog(
    daily_report: dict[str, Any],
    pilot_review: dict[str, Any],
    preflight: dict[str, Any],
    v6a_candidate: dict[str, Any],
    v6a_robustness: dict[str, Any],
    v6a_reaudit: dict[str, Any],
    core_signal: dict[str, Any],
    turnaround_signal: dict[str, Any],
    bottleneck_signal: dict[str, Any],
    missing_review: dict[str, Any],
    position_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    review_decision = str(pilot_review.get("review_decision") or "")
    if review_decision and review_decision != "GO":
        items.append(
            {
                "priority": "P0",
                "lane": "execution_quality",
                "title": "Keep V6-A in manual pilot and collect more execution evidence",
                "reason": f"Pilot review remains {review_decision}. System still in execution-validation phase.",
                "next_step": "Continue manual pilot and reuse the same review board at the next weekly checkpoint.",
            }
        )
    blockers = [str(item) for item in preflight.get("blockers", [])]
    actionable_blockers = [item for item in blockers if "kill switch is ON".lower() not in item.lower() and "Not in regular market hours".lower() not in item.lower()]
    if actionable_blockers:
        items.append(
            {
                "priority": "P0",
                "lane": "ops_guardrails",
                "title": "Investigate unexpected preflight blockers",
                "reason": "; ".join(actionable_blockers),
                "next_step": "Review preflight checks and remove only genuine operational blockers, not governance blockers.",
            }
        )
    if position_summary.get("top3_weight", 0.0) >= 0.80:
        items.append(
            {
                "priority": "P1",
                "lane": "risk_governance",
                "title": "Review current V6-A concentration and whether it still matches sleep-quality limits",
                "reason": f"Top 3 managed positions are {position_summary['top3_weight'] * 100:.1f}% of V6-A sleeve market value.",
                "next_step": "Keep this under weekly review; do not change production engine only because concentration feels uncomfortable.",
            }
        )
    preferred_v6a = (v6a_candidate or {}).get("balanced_top") or (v6a_candidate or {}).get("raw_top") or {}
    if preferred_v6a and preferred_v6a.get("gate") == "promising_core_upgrade":
        robustness_ok = (
            v6a_robustness
            and v6a_robustness.get("target_label") == preferred_v6a["label"]
            and v6a_robustness.get("verdict") == "stable_neighbor_cluster"
        )
        reaudit_ok = (
            v6a_reaudit
            and v6a_reaudit.get("candidate_label") == preferred_v6a["label"]
            and v6a_reaudit.get("verdict") == "candidate_survives_costs"
        )
        items.append(
            {
                "priority": "P1",
                "lane": "v6a_parameter_challenger",
                "title": (
                    "Build formal side-by-side board for the balanced V6-A challenger"
                    if robustness_ok and reaudit_ok
                    else "Run formal follow-up on the leading balanced V6-A challenger"
                ),
                "reason": (
                    f"Preferred candidate {preferred_v6a['label']} shows "
                    f"Ann +{preferred_v6a['ann_delta'] * 100:.1f}%, "
                    f"Sharpe +{preferred_v6a['sharpe_delta']:.2f}, "
                    f"dd change {preferred_v6a['dd_worse'] * 100:+.1f}% vs baseline."
                    + (
                        f" Robustness={v6a_robustness.get('verdict')}, cost_reaudit={v6a_reaudit.get('verdict')}."
                        if robustness_ok and reaudit_ok
                        else ""
                    )
                ),
                "next_step": (
                    "Prepare baseline vs balanced challenger review board and implementation/replay plan."
                    if robustness_ok and reaudit_ok
                    else "Do parameter-neighbor robustness and turnover/cost re-audit before any baseline promotion discussion."
                ),
            }
        )
    if core_signal and core_signal.get("track_gate") == "real_track_alpha":
        items.append(
            {
                "priority": "P1",
                "lane": "v6b_core_reaccel",
                "title": "Promote core_reaccel to formal V6-B challenger lane",
                "reason": (
                    f"Best core_reaccel overlay {core_signal['label']} still adds "
                    f"Ann +{core_signal['track_ann_inc'] * 100:.1f}% and "
                    f"Sharpe +{core_signal['track_sharpe_inc']:.2f} vs same-parameter V6-A base-only."
                ),
                "next_step": "Keep core_reaccel ahead of other V6-B tracks and build the next validation board around it.",
            }
        )
    if turnaround_signal and turnaround_signal.get("track_gate") == "real_track_alpha":
        items.append(
            {
                "priority": "P2",
                "lane": "v6b_turnaround",
                "title": "Keep turnaround as secondary research only",
                "reason": (
                    f"Turnaround still shows positive track increment, but only modestly "
                    f"(Ann +{turnaround_signal['track_ann_inc'] * 100:.1f}%, Sharpe +{turnaround_signal['track_sharpe_inc']:.2f})."
                ),
                "next_step": "Do not give allocator weight; only continue if new sparse-track evidence improves quality.",
            }
        )
    if bottleneck_signal and bottleneck_signal.get("track_gate") != "real_track_alpha":
        items.append(
            {
                "priority": "P2",
                "lane": "v6b_bottleneck",
                "title": "Freeze bottleneck as a live promotion candidate",
                "reason": (
                    f"Bottleneck top row {bottleneck_signal['label']} does not pass true track-alpha test "
                    f"(track gate = {bottleneck_signal['track_gate']})."
                ),
                "next_step": "Do not spend allocator attention here until universe quality or exits materially improve.",
            }
        )
    if missing_review and (missing_review.get("critical_miss_count", 0) > 0 or missing_review.get("theme_wakeup_count", 0) > 0):
        missing_names = ", ".join(missing_review.get("critical_miss_tickers", [])[:5]) or "none"
        theme_wakeups = ", ".join(missing_review.get("theme_wakeups", [])[:4]) or "none"
        items.append(
            {
                "priority": "P1",
                "lane": "radar_missing_opportunity",
                "title": "Review new missing-opportunity names before the next Radar universe refresh",
                "reason": (
                    f"Latest missing-opportunity review ({missing_review.get('as_of')}) shows "
                    f"{missing_review.get('critical_miss_count', 0)} critical misses "
                    f"and {missing_review.get('theme_wakeup_count', 0)} theme wakeups. "
                    f"Names={missing_names}; themes={theme_wakeups}."
                ),
                "next_step": "Decide whether to upgrade these names/themes into point-in-time research seed or explicitly document why they remain excluded.",
            }
        )
    if missing_review and missing_review.get("coverage_gap_count", 0) > 0:
        items.append(
            {
                "priority": "P2",
                "lane": "radar_coverage_gaps",
                "title": "Close Radar data and theme coverage gaps",
                "reason": (
                    f"Latest missing-opportunity review still has {missing_review.get('coverage_gap_count', 0)} coverage gaps "
                    f"and {missing_review.get('active_weak_count', 0)} active-but-weak names."
                ),
                "next_step": "Fetch or validate missing candidate data, then prune stale names or move them to explicit observe-only status.",
            }
        )
    report_status = daily_report.get("weekly_action") or ""
    if report_status:
        items.append(
            {
                "priority": "P3",
                "lane": "review_cadence",
                "title": "Keep weekly review cadence active",
                "reason": f"Latest report action is '{report_status}'. Weekly review is now a formal governance step, not optional reflection.",
                "next_step": "Run the weekly board again after the next full week of pilot data.",
            }
        )
    return items


def render_board_md(board: dict[str, Any]) -> str:
    lines = [
        "# Weekly V6 Review Board",
        "",
        f"- Generated: `{board['generated_at']}`",
        f"- Week Ending: `{board['week_ending']}`",
        f"- Review Decision: `{board['decision']}`",
        "",
        "## 1. Outcome Snapshot",
        "",
        f"- V6-A pilot review: `{board['pilot_review_decision']}`",
        f"- Managed unrealized P/L: `{board['managed_unrealized_pl_pct_points']:+.2f}%`",
        f"- Current top 3 concentration: `{board['top3_weight'] * 100:.1f}%`",
        f"- Latest report action: `{board['latest_weekly_action']}`",
        "",
        "## 2. Process Integrity",
        "",
        f"- Managed state strategy: `{board['managed_state_strategy']}`",
        f"- Reconciliation unresolved issues: `{board['recon_issue_count']}`",
        f"- Pending orders: `{board['pending_order_count']}`",
        f"- Preflight decision: `{board['preflight_decision']}`",
        f"- Preflight blockers: `{'; '.join(board['preflight_blockers']) if board['preflight_blockers'] else 'expected governance-only blockers'}`",
        "",
        "## 3. Exposure",
        "",
    ]
    for row in board["top_positions"]:
        lines.append(f"- `{row['code']}`: weight `{row['weight'] * 100:.1f}%`, P/L `{row['unrealized_pl_pct']:+.2f}%`")
    lines.extend(
        [
            "",
            "## 4. Research Signals",
            "",
            (
                f"- V6-A raw top candidate: `{board['v6a_candidate']['raw_top']['label']}` "
                f"({board['v6a_candidate']['raw_top']['gate']}, AnnΔ `{board['v6a_candidate']['raw_top']['ann_delta'] * 100:+.1f}%`, "
                f"SharpeΔ `{board['v6a_candidate']['raw_top']['sharpe_delta']:+.2f}`)"
                if board["v6a_candidate"] else "- V6-A raw top candidate: `n/a`"
            ),
            (
                f"- V6-A balanced candidate: `{board['v6a_candidate']['balanced_top']['label']}` "
                f"({board['v6a_candidate']['balanced_top']['gate']}, AnnΔ `{board['v6a_candidate']['balanced_top']['ann_delta'] * 100:+.1f}%`, "
                f"SharpeΔ `{board['v6a_candidate']['balanced_top']['sharpe_delta']:+.2f}`)"
                if board["v6a_candidate"] else "- V6-A balanced candidate: `n/a`"
            ),
            (
                f"- V6-A robustness: `{board['v6a_robustness']['verdict']}` on `{board['v6a_robustness']['target_label']}`"
                if board["v6a_robustness"] else "- V6-A robustness: `n/a`"
            ),
            (
                f"- V6-A cost re-audit: `{board['v6a_reaudit']['verdict']}` on `{board['v6a_reaudit']['candidate_label']}`"
                if board["v6a_reaudit"] else "- V6-A cost re-audit: `n/a`"
            ),
            (
                f"- V6-B core_reaccel: `{board['v6b_core']['track_gate']}` on `{board['v6b_core']['label']}`"
                if board["v6b_core"] else "- V6-B core_reaccel: `n/a`"
            ),
            (
                f"- V6-B turnaround: `{board['v6b_turnaround']['track_gate']}` on `{board['v6b_turnaround']['label']}`"
                if board["v6b_turnaround"] else "- V6-B turnaround: `n/a`"
            ),
            (
                f"- V6-B bottleneck: `{board['v6b_bottleneck']['track_gate']}` on `{board['v6b_bottleneck']['label']}`"
                if board["v6b_bottleneck"] else "- V6-B bottleneck: `n/a`"
            ),
            (
                f"- Missing opportunity review: `{board['missing_review']['critical_miss_count']} critical / "
                f"{board['missing_review']['theme_wakeup_count']} theme wakeups / "
                f"{board['missing_review']['coverage_gap_count']} coverage gaps` as of `{board['missing_review']['as_of']}`"
                if board["missing_review"] else "- Missing opportunity review: `n/a`"
            ),
            (
                f"- Missing opportunity names: `{', '.join(board['missing_review']['critical_miss_tickers'])}`"
                if board["missing_review"] and board["missing_review"].get("critical_miss_tickers") else "- Missing opportunity names: `none`"
            ),
            (
                f"- Theme wakeups: `{', '.join(board['missing_review']['theme_wakeups'])}`"
                if board["missing_review"] and board["missing_review"].get("theme_wakeups") else "- Theme wakeups: `none`"
            ),
            "",
            "## 5. Research Backlog",
            "",
        ]
    )
    for idx, item in enumerate(board["backlog_items"], start=1):
        lines.append(f"{idx}. [{item['priority']}] `{item['lane']}` {item['title']}")
        lines.append(f"   - Reason: {item['reason']}")
        lines.append(f"   - Next: {item['next_step']}")
    return "\n".join(lines) + "\n"


def render_backlog_md(backlog: list[dict[str, Any]], tag: str) -> str:
    lines = [
        "# V6 Research Backlog",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Source Weekly Tag: `{tag}`",
        "",
        "| priority | lane | title | next step |",
        "| --- | --- | --- | --- |",
    ]
    for item in backlog:
        lines.append(
            f"| `{item['priority']}` | `{item['lane']}` | {item['title']} | {item['next_step']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Weekly V6 Review Board and research backlog.")
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    latest_daily_path = REPORTING_DIR / "latest_daily.json"
    latest_weekly_path = REPORTING_DIR / "latest_weekly.json"
    pilot_review_path = latest_file(PILOT_REVIEW_DIR, "*.json")

    daily_report = read_json(latest_daily_path)
    weekly_report = read_json(latest_weekly_path)
    pilot_review = read_json(pilot_review_path) if pilot_review_path else {}
    preflight = read_json(PREFLIGHT_LATEST)

    position_summary = summarize_v6a_positions(pilot_review)
    v6a_candidate = load_latest_v6a_parameter_candidate()
    v6a_robustness = load_latest_v6a_robustness()
    v6a_reaudit = load_latest_v6a_reaudit()
    core_signal = load_latest_v6b_track_signal("core_reaccel_profile")
    bottleneck_signal = load_latest_v6b_track_signal("bottleneck_diffusion_profile")
    turnaround_signal = load_latest_v6b_track_signal("turnaround_momentum_profile")
    missing_review = load_latest_missing_review()

    backlog_items = build_backlog(
        daily_report=weekly_report or daily_report,
        pilot_review=pilot_review,
        preflight=preflight,
        v6a_candidate=v6a_candidate,
        v6a_robustness=v6a_robustness,
        v6a_reaudit=v6a_reaudit,
        core_signal=core_signal,
        turnaround_signal=turnaround_signal,
        bottleneck_signal=bottleneck_signal,
        missing_review=missing_review,
        position_summary=position_summary,
    )

    decision = "No change"
    if any(item["priority"] == "P0" for item in backlog_items):
        decision = "Investigate / Continue manual pilot"
    elif any(item["priority"] == "P1" for item in backlog_items):
        decision = "Research follow-up"

    board = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "week_ending": datetime.now().date().isoformat(),
        "decision": decision,
        "pilot_review_decision": str(pilot_review.get("review_decision") or ""),
        "managed_unrealized_pl_pct_points": position_summary.get("unrealized_pl_pct_points", 0.0),
        "top3_weight": position_summary.get("top3_weight", 0.0),
        "latest_weekly_action": str((weekly_report or daily_report).get("weekly_action") or ""),
        "managed_state_strategy": str((pilot_review.get("managed_state") or {}).get("strategy") or ""),
        "recon_issue_count": len(pilot_review.get("issues", []) or []),
        "pending_order_count": len((pilot_review.get("managed_state") or {}).get("pending_orders", []) or []),
        "preflight_decision": str(preflight.get("decision") or ""),
        "preflight_blockers": [str(item) for item in preflight.get("blockers", [])],
        "top_positions": position_summary.get("top3", []),
        "v6a_candidate": v6a_candidate,
        "v6a_robustness": v6a_robustness,
        "v6a_reaudit": v6a_reaudit,
        "v6b_core": core_signal,
        "v6b_turnaround": turnaround_signal,
        "v6b_bottleneck": bottleneck_signal,
        "missing_review": missing_review,
        "backlog_items": backlog_items,
        "artifacts": {
            "latest_daily": rel(latest_daily_path),
            "latest_weekly": rel(latest_weekly_path),
            "pilot_review": rel(pilot_review_path),
            "preflight": rel(PREFLIGHT_LATEST),
            "missing_review": rel(MISSING_REVIEW_LATEST),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BACKLOG_DIR.mkdir(parents=True, exist_ok=True)
    board_json = OUT_DIR / f"v6_weekly_review_{args.tag}.json"
    board_md = OUT_DIR / f"v6_weekly_review_{args.tag}.md"
    backlog_json = BACKLOG_DIR / f"v6_research_backlog_{args.tag}.json"
    backlog_md = BACKLOG_DIR / f"v6_research_backlog_{args.tag}.md"

    board_json.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
    board_md.write_text(render_board_md(board), encoding="utf-8")
    backlog_json.write_text(json.dumps(backlog_items, ensure_ascii=False, indent=2), encoding="utf-8")
    backlog_md.write_text(render_backlog_md(backlog_items, args.tag), encoding="utf-8")

    print(f"Board JSON:   {board_json}")
    print(f"Board MD:     {board_md}")
    print(f"Backlog JSON: {backlog_json}")
    print(f"Backlog MD:   {backlog_md}")
    print(f"Items:        {len(backlog_items)}")


if __name__ == "__main__":
    main()
