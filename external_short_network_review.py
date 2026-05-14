#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_DIR = Path("/Users/zhangkun/Desktop/AI个人投资公司")
DEFAULT_REGISTRY = ROOT / "v6_strategy_lab" / "configs" / "v6b_candidate_registry_v1.json"
DEFAULT_MISSING_REVIEW = ROOT / "backtest_results" / "v6b_missing_opportunity_review" / "latest.json"
OUT_DIR = ROOT / "backtest_results" / "external_short_network_review"


COMMONALITY_FACTORS = [
    "主题/热点",
    "动能转换",
    "技术形态",
    "成交量/资金",
    "催化/叙事",
    "衍生品/短线情绪",
]


def read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_external_sample(entry: dict[str, Any]) -> bool:
    if bool(entry.get("external_sample")):
        return True
    source = str(entry.get("source") or "").lower()
    reason = str(entry.get("reason") or "").lower()
    markers = ["external", "short-term network", "friend", "trader", "外部", "朋友", "短线"]
    return any(marker in source or marker in reason for marker in markers)


def index_missing_review(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for section in ("critical_misses", "watch_misses", "active_weak", "coverage_gaps"):
        rows = review.get(section, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            ticker = str(row.get("ticker") or "")
            if not ticker:
                continue
            current = indexed.get(ticker, {})
            current[section] = row
            indexed[ticker] = current
    return indexed


def infer_gap_attribution(sample: dict[str, Any], review_rows: dict[str, Any]) -> str:
    if "coverage_gaps" in review_rows:
        reason = str(review_rows["coverage_gaps"].get("gap_reason") or "")
        if "price_cache" in reason or "history" in reason:
            return "数据缺失"
        return "覆盖缺口"
    if "critical_misses" in review_rows or "watch_misses" in review_rows:
        return "评分规则太慢或 active universe 未及时升级"
    status = str(sample.get("registry_status") or "")
    if status in {"watch_add_candidate", "observe_only"}:
        return "已进入 registry，等待数据和 scorecard 验证"
    return "待人工归因"


def infer_lifecycle(sample: dict[str, Any]) -> str:
    bucket = str(sample.get("bucket_id") or "")
    if bucket in {"core_reacceleration"}:
        return "二阶扩散"
    if bucket in {"optics_and_interconnect", "advanced_packaging", "bottleneck_diffusion"}:
        return "二阶扩散 / 三阶补涨待判定"
    return "主线阶段待判定"


def infer_initial_verdict(sample: dict[str, Any], review_rows: dict[str, Any]) -> str:
    status = str(sample.get("registry_status") or "")
    if "critical_misses" in review_rows:
        return "THEME_DIFFUSION_CONFIRMED 待人工复核"
    if "watch_misses" in review_rows:
        return "MOMENTUM_ONLY / THEME_DIFFUSION 待区分"
    if "coverage_gaps" in review_rows:
        return "数据缺失，暂不判定"
    if status == "observe_only":
        return "MOMENTUM_ONLY 待验证"
    return "待下一次 Missing Review"


def build_review(registry: dict[str, Any], missing_review: dict[str, Any]) -> dict[str, Any]:
    indexed_missing = index_missing_review(missing_review)
    samples = []
    for entry in registry.get("entries", []):
        if not isinstance(entry, dict) or not is_external_sample(entry):
            continue
        ticker = str(entry.get("ticker") or "")
        review_rows = indexed_missing.get(ticker, {})
        samples.append(
            {
                "ticker": ticker,
                "theme_id": str(entry.get("theme_id") or ""),
                "bucket_id": str(entry.get("bucket_id") or ""),
                "registry_status": str(entry.get("registry_status") or ""),
                "data_status": str(entry.get("data_status") or ""),
                "source": str(entry.get("source") or ""),
                "reason": str(entry.get("reason") or ""),
                "lifecycle": infer_lifecycle(entry),
                "gap_attribution": infer_gap_attribution(entry, review_rows),
                "commonality_factors": {factor: "待数据/人工复核" for factor in COMMONALITY_FACTORS},
                "commonality_verdict": infer_initial_verdict(entry, review_rows),
                "missing_review_sections": sorted(review_rows.keys()),
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "registry_id": registry.get("registry_id"),
        "missing_review_as_of": missing_review.get("as_of"),
        "sample_count": len(samples),
        "samples": samples,
        "method": {
            "purpose": "把外部短线网络先发现的强势票转成 Radar 可复盘样本，而不是直接交易信号。",
            "lifecycle": "主线确认 -> 龙头重估 -> 二阶扩散 -> 三阶补涨 -> 情绪尾声 -> 退潮",
            "factors": COMMONALITY_FACTORS,
            "rule": "样本满足 4/6 共性因子才进入 Radar 重点复盘；是否交易仍由 V6-B / Overlay / 人工小额实验规则决定。",
            "generalized_engine": "不预设只能是 AI。先识别当前市场主线，再沿主线受益链条寻找扩散机会。",
        },
    }


def render_md(review: dict[str, Any]) -> str:
    lines = [
        "# 外部短线网络样本复盘",
        "",
        f"- 生成时间：`{review['generated_at']}`",
        f"- Registry：`{review.get('registry_id') or 'n/a'}`",
        f"- Missing Review As Of：`{review.get('missing_review_as_of') or 'n/a'}`",
        f"- 样本数：`{review['sample_count']}`",
        "",
        "## 方法",
        "",
        f"- 目的：{review['method']['purpose']}",
        f"- 生命周期：`{review['method']['lifecycle']}`",
        f"- 规则：{review['method']['rule']}",
        f"- 泛化原则：{review['method']['generalized_engine']}",
        "",
        "## 主题无关设计",
        "",
        "系统以后必须先回答“当前市场正在奖励什么”，再回答“这条主线扩散到哪里”。",
        "",
        "| 层级 | 系统问题 | 输出 |",
        "| --- | --- | --- |",
        "| 主线识别 | 哪些行业/主题/ETF 正在跑赢市场并放量 | 候选主线列表 |",
        "| 龙头确认 | 哪些龙头已经被资金确认 | 龙头层 watchlist |",
        "| 二阶扩散 | 资金是否外溢到供应链、基础设施、上游/下游 | 二阶候选 |",
        "| 三阶补涨 | 哪些低预期小中盘刚出现动能转换 | 高弹性候选 |",
        "| 退潮识别 | 是否进入纯投机尾声 | 降权/禁止追高 |",
        "",
        "## 样本表",
        "",
        "| 标的 | 主题 | 桶 | 状态 | 数据 | 生命周期 | 漏网归因 | 初步 verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not review["samples"]:
        lines.append("| 无 | - | - | - | - | - | - | - |")
    for row in review["samples"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['ticker']}`",
                    row["theme_id"],
                    row["bucket_id"],
                    row["registry_status"],
                    row["data_status"],
                    row["lifecycle"],
                    row["gap_attribution"],
                    row["commonality_verdict"],
                ]
            )
            + " |"
        )

    lines.extend(["", "## 六因子拆解模板", ""])
    for row in review["samples"]:
        lines.extend(
            [
                f"### `{row['ticker']}`",
                "",
                f"- 来源：{row['source']}",
                f"- 入库理由：{row['reason']}",
                f"- Missing Review Sections：`{', '.join(row['missing_review_sections']) or 'none'}`",
                "",
                "| 因子 | 当前判断 |",
                "| --- | --- |",
            ]
        )
        for factor, value in row["commonality_factors"].items():
            lines.append(f"| {factor} | {value} |")
        lines.append("")

    lines.extend(
        [
            "## 下次升级方向",
            "",
            "- 如果外部样本反复落在 `数据缺失`，优先补 price cache 和 universe 覆盖。",
            "- 如果外部样本反复落在 `评分规则太慢`，优先增强相对强度、放量突破和新高附近扫描。",
            "- 如果外部样本多为 `SPECULATIVE_FLOW_ONLY`，说明朋友打法更偏短线情绪，不能直接进入 V6-B。",
            "- 如果外部样本多为 `THEME_DIFFUSION_CONFIRMED`，说明 Radar 应升级主线扩散扫描规则。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate External Short Network Sample Review.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--missing-review", default=str(DEFAULT_MISSING_REVIEW))
    parser.add_argument("--tag", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--sync-desktop", action="store_true")
    args = parser.parse_args()

    registry = read_json(Path(args.registry))
    missing_review = read_json(Path(args.missing_review))
    review = build_review(registry, missing_review)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"external_short_network_review_{args.tag}.json"
    md_path = OUT_DIR / f"external_short_network_review_{args.tag}.md"
    latest_json = OUT_DIR / "latest.json"
    latest_md = OUT_DIR / "latest.md"

    payload = json.dumps(review, ensure_ascii=False, indent=2) + "\n"
    markdown = render_md(review)
    json_path.write_text(payload, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")

    if args.sync_desktop:
        DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest_md, DESKTOP_DIR / "外部短线网络样本复盘_EXTERNAL_SHORT_NETWORK_LATEST.md")
        shutil.copy2(latest_json, DESKTOP_DIR / "外部短线网络样本复盘_EXTERNAL_SHORT_NETWORK_LATEST.json")

    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    print(f"Samples: {review['sample_count']}")
    print(f"Sync desktop: {args.sync_desktop}")


if __name__ == "__main__":
    main()
