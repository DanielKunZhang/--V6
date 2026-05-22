#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
SYSTEM_DOC = DESKTOP_ROOT / "系统优化升级依据" / "V6AB_A股Radar_双线迁移防污染原则_20260522.md"
OUT_DIR = ROOT / "backtest_results" / "cross_market_research_sync"

DEFAULT_V6AB_DAILY_JSON = ROOT / "backtest_results" / "v6ab_daily_evolution" / "latest_daily_evolution.json"
DEFAULT_A_SHARE_TRANSFER_JSON = ROOT / "backtest_results" / "a_share_radar_v6ab_transfer_review" / "latest.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_text(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n\n...（后文略）"
    return text


def pct(value: Any) -> str:
    try:
        return f"{float(value):+.2%}"
    except Exception:
        return "n/a"


def v6ab_summary(v6ab: dict[str, Any]) -> dict[str, Any]:
    daily = v6ab or {}
    pit_rows = daily.get("pit_classifier_bridge_backtest", {}).get("rows", [])
    by_candidate = {row.get("candidate"): row for row in pit_rows if isinstance(row, dict)}
    base = by_candidate.get("baseline_v2_v6ab_dynamic_b", {})
    guarded = by_candidate.get("pit_tier_turnover_guarded_v6ab_dynamic_b", {})
    override_bt = daily.get("override_candidate_backtest", {})
    override_decision = override_bt.get("decision", {}) if isinstance(override_bt.get("decision"), dict) else {}
    evidence = daily.get("override_evidence_candidate_review", {})
    evidence_counts = evidence.get("decision_counts", {}) if isinstance(evidence.get("decision_counts"), dict) else {}
    return {
        "asof": daily.get("asof", ""),
        "baseline_ann": base.get("stats", {}).get("ann_ret"),
        "guarded_ann": guarded.get("stats", {}).get("ann_ret"),
        "guarded_sharpe": guarded.get("stats", {}).get("sharpe"),
        "guarded_maxdd": guarded.get("stats", {}).get("max_dd"),
        "override_candidate_tier": override_decision.get("tier", "UNKNOWN"),
        "override_candidate_ann_delta": override_decision.get("ann_delta_vs_v2", 0.0),
        "override_evidence_counts": evidence_counts,
    }


def a_share_summary(a_share: dict[str, Any]) -> dict[str, Any]:
    decision = a_share.get("decision", {}) if isinstance(a_share.get("decision"), dict) else {}
    sample = a_share.get("sample_summary", {}) if isinstance(a_share.get("sample_summary"), dict) else {}
    theme_rows = a_share.get("theme_rows", []) if isinstance(a_share.get("theme_rows"), list) else []
    candidate_rows = a_share.get("candidate_rows", []) if isinstance(a_share.get("candidate_rows"), list) else []
    return {
        "asof": a_share.get("asof", ""),
        "tier": decision.get("tier", "UNKNOWN"),
        "blockers": decision.get("blockers", []),
        "review_rows": sample.get("review_rows", 0),
        "strict_tracker_evaluated_rows": sample.get("strict_tracker_evaluated_rows", 0),
        "top_theme": theme_rows[0].get("theme") if theme_rows else "",
        "paper_ready_count": sum(row.get("tier") == "PAPER_TRADE_READY" for row in candidate_rows),
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    v6ab = load_json(args.v6ab_daily_json)
    a_share = load_json(args.a_share_transfer_json)
    v6 = v6ab_summary(v6ab)
    ash = a_share_summary(a_share)

    shareable = [
        {
            "source_market": "V6AB",
            "target_market": "A股Radar",
            "transfer_type": "methodology",
            "insight": "OVERRIDE 候选必须经过离线回测；证据变好不等于交易规则可制度化。",
            "allowed_scope": "A股可复用“候选先离线/模拟验证，再晋级”的流程。",
            "not_allowed_scope": "不得把 V6AB 的月频 OVERRIDE、Sharpe、maxDD 阈值直接套到 A股日频。",
            "validation_required": "A股本地 D1/D3/D5 规则过严追踪样本与模拟触发归因。",
            "promotion_tier": "RESEARCH_TRANSFER",
        },
        {
            "source_market": "A股Radar",
            "target_market": "V6AB",
            "transfer_type": "review_framework",
            "insight": "每日复盘应明确区分主线正确、表达错误、规则过严、不可参与买点。",
            "allowed_scope": "V6AB 可复用为月度/回测候选归因框架。",
            "not_allowed_scope": "不得把 A股高开、涨停、D1/D3/D5 阈值直接套到 V6AB。",
            "validation_required": "V6AB 本地 PIT/OOS/月度 attribution 验证。",
            "promotion_tier": "RESEARCH_TRANSFER",
        },
    ]

    quarantined = [
        {
            "market": "V6AB",
            "item": "ai_memory 2021 override 月份、收益差、月频 rebalance 表达。",
            "reason": "这是美股/ETF/月频历史样本，不能迁移为 A股短线买点规则。",
        },
        {
            "market": "A股Radar",
            "item": "涨停潮、高开不可参与、成交额门槛、D1/D3/D5 样本规则。",
            "reason": "这是 A股交易制度和短线结构信号，不能直接迁移到 V6AB。",
        },
    ]

    validation_queue = [
        {
            "candidate": "V6AB_daily_review_layer",
            "source_market": "A股Radar",
            "target_market": "V6AB",
            "goal": "把 A股每日复盘框架迁移为 V6AB 月度候选归因层。",
            "next_validation": "输出每次 V6AB 优化的主线/表达/证据/过拟合/晋级归因，不改模拟盘。",
        },
        {
            "candidate": "A股Radar_promotion_gate",
            "source_market": "V6AB",
            "target_market": "A股Radar",
            "goal": "把 V6AB promotion gate 固化为 A股观察->模拟->人工小额评审链路。",
            "next_validation": "累计 >=20 个 review rows 与 >=20 个 strict tracker evaluated rows。",
        },
    ]

    return {
        "asof": args.asof,
        "diagnostic_only": True,
        "paper_sim_action": "NO_CHANGE",
        "principle_doc": str(SYSTEM_DOC),
        "inputs": {
            "v6ab_daily_json": str(args.v6ab_daily_json),
            "a_share_transfer_json": str(args.a_share_transfer_json),
        },
        "v6ab_summary": v6,
        "a_share_summary": ash,
        "shareable_insights": shareable,
        "quarantined_items": quarantined,
        "validation_queue": validation_queue,
        "prompt": build_prompt(),
        "decision": {
            "tier": "SYNC_PACKET_READY",
            "action": "可供定期人工/AI 复盘使用；只同步方法论和验证结论，隔离市场具体规则。",
        },
    }


def build_prompt() -> str:
    return """# 跨市场研究同步提示词

你是 AI个人投资公司 的跨市场同步审查员。请只同步可迁移的方法论、工程框架和验证结论，不得直接迁移市场具体规则。

必须输出：
1. `SHARE`：可共享的抽象方法或工程机制。
2. `QUARANTINE`：必须隔离的市场特定阈值、买点、信号、样本。
3. `VALIDATION_QUEUE`：若要迁移，目标市场必须完成哪些本地验证。
4. `NO_ACTION`：哪些内容只归档，不影响任何仓位/模拟盘。

硬约束：
- 共用抽象层，不共用具体阈值。
- 新迁移默认 `RESEARCH_TRANSFER`。
- 未通过目标市场 PIT/OOS/复盘样本验证前，不得进入模拟盘或真钱自动化。
- 若无法说明收益质量或风险控制增益，结论写“只归档，不进入交易规则”。
"""


def render_md(payload: dict[str, Any]) -> str:
    v6 = payload["v6ab_summary"]
    ash = payload["a_share_summary"]
    lines = [
        "# 跨市场研究同步包",
        "",
        f"- 日期：`{payload['asof']}`",
        "- 动作：`NO_CHANGE`，不改变 V6AB 模拟盘或 A股 Radar 信号。",
        f"- 决策：`{payload['decision']['tier']}` — {payload['decision']['action']}",
        f"- 防污染原则：`{payload['principle_doc']}`",
        "",
        "## Current State",
        "",
        f"- V6AB：PIT guarded ann `{pct(v6.get('guarded_ann'))}`，Sharpe `{v6.get('guarded_sharpe', 'n/a')}`，override candidate `{v6.get('override_candidate_tier')}`，ann delta `{pct(v6.get('override_candidate_ann_delta'))}`。",
        f"- A股 Radar：tier `{ash.get('tier')}`，review rows `{ash.get('review_rows')}`，strict tracker evaluated `{ash.get('strict_tracker_evaluated_rows')}`，blockers `{', '.join(ash.get('blockers', [])) or 'none'}`。",
        "",
        "## SHARE",
        "",
    ]
    for row in payload["shareable_insights"]:
        lines.append(
            f"- `{row['source_market']} -> {row['target_market']}` `{row['transfer_type']}`：{row['insight']} "
            f"允许：{row['allowed_scope']}；验证：{row['validation_required']}。"
        )
    lines += ["", "## QUARANTINE", ""]
    for row in payload["quarantined_items"]:
        lines.append(f"- `{row['market']}`：{row['item']} 原因：{row['reason']}")
    lines += ["", "## VALIDATION_QUEUE", ""]
    for row in payload["validation_queue"]:
        lines.append(f"- `{row['candidate']}`：{row['goal']} 下一步：{row['next_validation']}")
    lines += [
        "",
        "## Prompt",
        "",
        "```markdown",
        payload["prompt"].strip(),
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a cross-market research sync packet with contamination guardrails.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--v6ab-daily-json", type=Path, default=DEFAULT_V6AB_DAILY_JSON)
    parser.add_argument("--a-share-transfer-json", type=Path, default=DEFAULT_A_SHARE_TRANSFER_JSON)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = build_payload(args)
    md = render_md(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    (args.output_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (args.output_dir / "latest.md").write_text(md, encoding="utf-8")
    (REPORT_ROOT / "跨市场研究同步_LATEST.json").write_text(json_text, encoding="utf-8")
    (REPORT_ROOT / "跨市场研究同步_LATEST.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
