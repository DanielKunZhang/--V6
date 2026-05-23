#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import importlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"

PLAN_MD = REPORT_ROOT / "A股短线Radar下周一计划_LATEST.md"
PLAN_JSON = REPORT_ROOT / "A股短线Radar下周一计划_LATEST.json"
CANDIDATES_CSV = REPORT_ROOT / "A股短线Radar候选_LATEST.csv"
THEMES_CSV = REPORT_ROOT / "A股短线Radar主线评分_LATEST.csv"
REVIEW_MD = REPORT_ROOT / "A股短线Radar复盘_LATEST.md"
REVIEW_JSON = REPORT_ROOT / "A股短线Radar复盘_LATEST.json"
FEEDBACK_MD = REPORT_ROOT / "A股短线Radar复盘反哺_LATEST.md"
FEEDBACK_JSON = REPORT_ROOT / "A股短线Radar复盘反哺_LATEST.json"
BACKFILL_MD = REPORT_ROOT / "A股短线Radar_K线补齐_LATEST.md"
BACKFILL_JSON = REPORT_ROOT / "A股短线Radar_K线补齐_LATEST.json"
OFFICIAL_POLICY_JSON = REPORT_ROOT / "A股官方政策白名单扫描_LATEST.json"
PLATE_HEAT_JSON = REPORT_ROOT / "A股富途板块热度自动扫描_LATEST.json"
STRICT_TRACKER_JSON = REPORT_ROOT / "A股短线Radar规则过严样本追踪_LATEST.json"
CLASSIFICATION_LEDGER_JSON = REPORT_ROOT / "A股Radar主线分类准度Ledger_LATEST.json"

OUTPUT_DIR = ROOT / "backtest_results" / "a_share_short_radar_evening_guide"


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def df_to_html_table(df: pd.DataFrame, max_rows: int = 8) -> str:
    if df.empty:
        return "<p class='muted'>暂无数据。</p>"
    rows = df.head(max_rows).to_dict("records")
    cols = list(df.columns)
    head = "".join(f"<th>{esc(col)}</th>" for col in cols)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{esc(row.get(col, ''))}</td>" for col in cols) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def feedback_table(feedback: dict[str, Any]) -> str:
    rows = feedback.get("rows", []) if isinstance(feedback, dict) else []
    plus_rows = [row for row in rows if row.get("feedback_action") == "DATA_BACKFILL_AND_WATCH_ONLY_PLUS"]
    if not plus_rows:
        return "<p class='muted'>暂无 P0 反哺动作。</p>"
    df = pd.DataFrame(plus_rows)
    keep = [
        "symbol",
        "name",
        "theme",
        "role",
        "review_change_rate",
        "old_mode",
        "mode_after_feedback",
        "next_system_action",
    ]
    cols = [col for col in keep if col in df.columns]
    labels = {
        "symbol": "代码",
        "name": "名称",
        "theme": "主线",
        "role": "身份",
        "review_change_rate": "复盘涨跌",
        "old_mode": "原模式",
        "mode_after_feedback": "反哺模式",
        "next_system_action": "系统动作",
    }
    return df_to_html_table(df[cols].rename(columns=labels), max_rows=6)


def backfill_table(backfill: dict[str, Any]) -> str:
    rows = backfill.get("rows", []) if isinstance(backfill, dict) else []
    if not rows:
        return "<p class='muted'>暂无补 K 线任务。</p>"
    df = pd.DataFrame(rows)
    keep = ["symbol", "name", "status", "rows", "start_date", "end_date", "path", "message"]
    cols = [col for col in keep if col in df.columns]
    labels = {
        "symbol": "代码",
        "name": "名称",
        "status": "状态",
        "rows": "K线数",
        "start_date": "开始",
        "end_date": "结束",
        "path": "缓存",
        "message": "说明",
    }
    return df_to_html_table(df[cols].rename(columns=labels), max_rows=6)


def strict_tracker_table(tracker: dict[str, Any]) -> str:
    rows = tracker.get("rows", []) if isinstance(tracker, dict) else []
    if not rows:
        return "<p class='muted'>暂无规则过严追踪样本。</p>"
    df = pd.DataFrame(rows)
    keep = [
        "origin_date",
        "symbol",
        "name",
        "theme",
        "role",
        "backfill_status",
        "cached_kline_rows",
        "d1_status",
        "d1_return_pct",
        "d1_touched_plan_buy",
        "d1_gap_accel_unbuyable",
    ]
    cols = [col for col in keep if col in df.columns]
    labels = {
        "origin_date": "样本日",
        "symbol": "代码",
        "name": "名称",
        "theme": "主线",
        "role": "身份",
        "backfill_status": "补K状态",
        "cached_kline_rows": "K线数",
        "d1_status": "D1状态",
        "d1_return_pct": "D1收益",
        "d1_touched_plan_buy": "D1计划买点",
        "d1_gap_accel_unbuyable": "D1高开不可参与",
    }
    return df_to_html_table(df[cols].rename(columns=labels), max_rows=8)


def classification_ledger_table(ledger: dict[str, Any]) -> str:
    rows = ledger.get("due_reviews", []) if isinstance(ledger, dict) else []
    if not rows:
        return "<p class='muted'>暂无到期主线分类复核项。</p>"
    df = pd.DataFrame(rows)
    if "due_horizons" in df.columns:
        df["due_horizons"] = df["due_horizons"].apply(lambda value: ", ".join(value) if isinstance(value, list) else value)
    keep = [
        "discovery_date",
        "theme",
        "phase",
        "score",
        "breadth_proxy",
        "due_horizons",
        "reason",
    ]
    cols = [col for col in keep if col in df.columns]
    labels = {
        "discovery_date": "发现日",
        "theme": "主线",
        "phase": "当时阶段",
        "score": "分数",
        "breadth_proxy": "广度代理",
        "due_horizons": "到期",
        "reason": "当时理由",
    }
    return df_to_html_table(df[cols].rename(columns=labels), max_rows=8)


def official_policy_table(payload: dict[str, Any]) -> str:
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    failures = payload.get("failures", []) if isinstance(payload, dict) else []
    parts: list[str] = []
    if rows:
        df = pd.DataFrame(rows)
        keep = ["date", "source", "theme", "confidence", "needs_manual_review", "title"]
        cols = [col for col in keep if col in df.columns]
        labels = {
            "date": "日期",
            "source": "来源",
            "theme": "主题",
            "confidence": "置信度",
            "needs_manual_review": "需复核",
            "title": "标题",
        }
        parts.append(df_to_html_table(df[cols].rename(columns=labels), max_rows=8))
    else:
        parts.append("<p class='muted'>暂无官方白名单关键词命中。</p>")
    if failures:
        failed = [item for item in failures if item.get("status") == "FAILED"]
        if failed:
            items = "".join(f"<li>{esc(item.get('source'))}: {esc(item.get('reason'))}</li>" for item in failed[:5])
            parts.append(f"<p class='muted'>需人工补查的失败源：</p><ul>{items}</ul>")
    return "\n".join(parts)


def crowding_risk_table(payload: dict[str, Any]) -> str:
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    if not rows:
        status = payload.get("status", "UNKNOWN") if isinstance(payload, dict) else "UNKNOWN"
        reason = payload.get("reason", "") if isinstance(payload, dict) else ""
        return f"<p class='muted'>暂无板块拥挤数据。状态：{esc(status)} {esc(reason)}</p>"
    risky = [row for row in rows if row.get("crowding_risk") in {"EXTREME", "HIGH"}]
    if not risky:
        return "<p class='muted'>暂未发现 HIGH/EXTREME 拥挤代理；仍需结合价格位置和复盘判断。</p>"
    df = pd.DataFrame(risky)
    keep = [
        "plate_name",
        "heat_score",
        "crowding_risk",
        "crowding_reason",
        "up_ratio",
        "strong_count_5pct",
        "limit_proxy_count",
        "amount_rmb",
    ]
    cols = [col for col in keep if col in df.columns]
    labels = {
        "plate_name": "板块",
        "heat_score": "热度",
        "crowding_risk": "拥挤风险",
        "crowding_reason": "原因",
        "up_ratio": "上涨比例",
        "strong_count_5pct": "强势股",
        "limit_proxy_count": "涨停代理",
        "amount_rmb": "成交额",
    }
    return df_to_html_table(df[cols].rename(columns=labels), max_rows=8)


def compact_candidate_table(candidates: pd.DataFrame, tradable_only: bool) -> str:
    if candidates.empty:
        return "<p class='muted'>暂无候选。</p>"
    df = candidates.copy()
    if tradable_only:
        df = df[df.get("position_size_rmb", "0").astype(str) != "0"]
    else:
        df = df[df.get("position_size_rmb", "0").astype(str) == "0"]
    if df.empty:
        return "<p class='muted'>暂无。</p>"
    keep = [
        "symbol",
        "name",
        "mode",
        "theme",
        "role",
        "close",
        "action_detail",
        "exit_detail",
        "reason",
    ]
    cols = [col for col in keep if col in df.columns]
    labels = {
        "symbol": "代码",
        "name": "名称",
        "mode": "模式",
        "theme": "主线",
        "role": "身份",
        "close": "价格",
        "action_detail": "动作拆解",
        "exit_detail": "退出拆解",
        "reason": "理由",
    }
    return df_to_html_table(df[cols].rename(columns=labels), max_rows=6)


def summarize_plan(plan: dict[str, Any], themes: pd.DataFrame, candidates: pd.DataFrame) -> dict[str, Any]:
    next_trade_date = plan.get("next_trade_date", "")
    data_latest = plan.get("data_latest", "")
    live_snapshot = plan.get("live_snapshot_used", False)
    top_theme = "无"
    top_theme_score = ""
    if not themes.empty and "score" in themes.columns:
        sorted_themes = themes.sort_values("score", ascending=False)
        top = sorted_themes.iloc[0]
        top_theme = str(top.get("theme", ""))
        top_theme_score = str(top.get("score", ""))
    trade_ready = []
    watch_only = []
    if not candidates.empty:
        for _, row in candidates.iterrows():
            action = str(row.get("action", ""))
            item = f"{row.get('symbol', '')} {row.get('name', '')}：{action}"
            if "可列入" in action or "不追高" in action:
                trade_ready.append(item)
            else:
                watch_only.append(item)
    return {
        "next_trade_date": next_trade_date,
        "data_latest": data_latest,
        "live_snapshot": live_snapshot,
        "top_theme": top_theme,
        "top_theme_score": top_theme_score,
        "trade_ready": trade_ready,
        "watch_only": watch_only,
    }


def build_html(asof: str) -> tuple[str, str, dict[str, Any]]:
    plan = read_json(PLAN_JSON)
    review = read_json(REVIEW_JSON)
    feedback = read_json(FEEDBACK_JSON)
    backfill = read_json(BACKFILL_JSON)
    official_policy = read_json(OFFICIAL_POLICY_JSON)
    plate_heat = read_json(PLATE_HEAT_JSON)
    strict_tracker = read_json(STRICT_TRACKER_JSON)
    classification_ledger = read_json(CLASSIFICATION_LEDGER_JSON)
    themes = read_csv(THEMES_CSV)
    candidates = read_csv(CANDIDATES_CSV)
    summary = summarize_plan(plan, themes, candidates)

    subject = f"A股低频主线确认Radar观察计划 {summary['next_trade_date'] or asof} · 主线 {summary['top_theme']} {summary['top_theme_score']}"

    review_status = "已找到最新复盘文件" if REVIEW_MD.exists() else "未找到复盘文件，本次仅输出计划"
    trade_ready_html = "".join(f"<li>{esc(x)}</li>" for x in summary["trade_ready"]) or "<li>无可交易候选，默认观察。</li>"
    watch_only_html = "".join(f"<li>{esc(x)}</li>" for x in summary["watch_only"]) or "<li>无。</li>"

    html_content = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:#18212f; line-height:1.55; }}
.box {{ border:1px solid #d8dee9; border-radius:12px; padding:16px; margin:14px 0; }}
.warn {{ background:#fff7e6; border-color:#f0b45b; }}
.ok {{ background:#edf8f1; border-color:#72bd89; }}
.muted {{ color:#667085; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th, td {{ border:1px solid #e5e7eb; padding:7px; text-align:left; }}
th {{ background:#f8fafc; }}
code {{ background:#f2f4f7; padding:2px 4px; border-radius:4px; }}
</style>
</head>
<body>
<h2>A股低频主线确认 Radar 晚间观察指导</h2>
<p class="muted">生成日期：{esc(asof)}；计划交易日：<code>{esc(summary['next_trade_date'])}</code>；K线最新日期：<code>{esc(summary['data_latest'])}</code>；Level A 快照：<code>{esc(summary['live_snapshot'])}</code></p>

<div class="box warn">
<h3>一页结论</h3>
<p><b>最强主线：</b>{esc(summary['top_theme'])} / {esc(summary['top_theme_score'])}</p>
<p><b>复盘状态：</b>{esc(review_status)}</p>
<p><b>当前纪律：</b>Phase 1A 中频主题轮动训练期；真实仓位 0；不打板、不排板、不盯盘、不早盘抢票；只记录模拟触发和收盘复盘。30 笔完整样本前不改规则，只做诊断。</p>
<p><b>概念校验：</b>不一刀切排除概念，先判断是否有政策/产业支撑、板块扩散、龙头/中军/补涨结构；硬排除短命游资题材和计划外追高。</p>
<p><b>拥挤校验：</b>AI硬件、光模块、算力链、半导体设备、MLCC 等主题即使强，也不等于安全；若出现极端拥挤，只能观察或一手级 pilot 复核，不追高。</p>
<p><b>理想节奏：</b>提前埋伏、启动初入、冷却退出；每天只需低频确认，不做秒级决策。</p>
</div>

<div class="box ok">
<h3>明日可重点看的动作</h3>
<ul>{trade_ready_html}</ul>
{compact_candidate_table(candidates, tradable_only=True)}
</div>

<div class="box warn">
<h3>复盘反哺 / 数据补齐优先级</h3>
<p class="muted">这里不是买入指令；只把收盘复盘暴露的规则过严和数据缺口转成明日系统动作。</p>
{feedback_table(feedback)}
<h3>K线补齐状态</h3>
{backfill_table(backfill)}
<h3>官方政策/公告白名单扫描</h3>
<p class="muted">官方源只提供主线证据和人工复核入口；不是买入信号。若与板块热度和候选结构共振，再进入主线持续性观察。</p>
{official_policy_table(official_policy)}
<h3>拥挤/抱团风险</h3>
<p class="muted">主线仍强不等于安全。强主线 + 极端拥挤时，只允许降级为观察或一手级 pilot 复核；主题强但无业绩/订单/政策/公告验证，不进实盘候选。</p>
{crowding_risk_table(plate_heat)}
<h3>规则过严样本追踪</h3>
{strict_tracker_table(strict_tracker)}
<h3>主线分类准度 Ledger</h3>
<p class="muted">到期后只复核当时阶段判断是否正确，不据此临时改规则；30 条完整样本前只统计错误类型。</p>
{classification_ledger_table(classification_ledger)}
</div>

<div class="box">
<h3>只观察 / 不交易候选</h3>
<ul>{watch_only_html}</ul>
{compact_candidate_table(candidates, tradable_only=False)}
</div>

<div class="box">
<h3>主线评分</h3>
{df_to_html_table(themes, max_rows=6)}
</div>

<div class="box">
<h3>候选明细</h3>
{df_to_html_table(candidates, max_rows=8)}
</div>

<div class="box warn">
<h3>执行口令</h3>
<p>开盘前若主线集体低于预期，全部取消，只复盘。若候选高开加速，不追。当前阶段即使触发计划买点，也只记录为模拟触发，不做真实交易。</p>
<p>收盘后输入 <code>复盘</code>，按 SOP 更新样本，并记录信号执行、止损/失效、主观干预和复盘覆盖。</p>
</div>
</body>
</html>"""

    payload = {
        "asof": asof,
        "subject": subject,
        "summary": summary,
        "review_present": REVIEW_MD.exists(),
        "inputs": {
            "plan_md": str(PLAN_MD),
            "plan_json": str(PLAN_JSON),
            "candidates_csv": str(CANDIDATES_CSV),
            "themes_csv": str(THEMES_CSV),
            "review_md": str(REVIEW_MD),
            "feedback_md": str(FEEDBACK_MD),
            "feedback_json": str(FEEDBACK_JSON),
            "backfill_md": str(BACKFILL_MD),
            "backfill_json": str(BACKFILL_JSON),
            "official_policy_json": str(OFFICIAL_POLICY_JSON),
            "plate_heat_json": str(PLATE_HEAT_JSON),
            "strict_tracker_json": str(STRICT_TRACKER_JSON),
            "classification_ledger_json": str(CLASSIFICATION_LEDGER_JSON),
        },
    }
    return subject, html_content, payload


def send_email(subject: str, html_content: str) -> dict[str, Any]:
    try:
        notifier = importlib.import_module("notifier").EmailNotifier()
        sent = bool(notifier.send(subject, html_content, is_html=True))
        return {
            "attempted": True,
            "sent": sent,
            "recipient": getattr(notifier, "recipient", ""),
            "enabled": bool(getattr(notifier, "enabled", False)),
            "error": "" if sent else "notifier_send_false",
        }
    except Exception as exc:
        return {"attempted": True, "sent": False, "recipient": "", "enabled": False, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/send A-share short Radar evening guide email.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--send-email", action="store_true")
    args = parser.parse_args()

    subject, html_content, payload = build_html(args.asof)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "latest_evening_guide.html").write_text(html_content, encoding="utf-8")
    (OUTPUT_DIR / "latest_evening_guide.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_ROOT / "A股短线Radar晚间操作指导_LATEST.html").write_text(html_content, encoding="utf-8")
    (REPORT_ROOT / "A股短线Radar晚间操作指导_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    email_result = {"attempted": False, "sent": False}
    if args.send_email:
        email_result = send_email(subject, html_content)
    payload["email"] = email_result
    (OUTPUT_DIR / "latest_evening_guide.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_ROOT / "A股短线Radar晚间操作指导_LATEST.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"subject": subject, "outputs": [str(REPORT_ROOT / "A股短线Radar晚间操作指导_LATEST.html")], "email": email_result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
