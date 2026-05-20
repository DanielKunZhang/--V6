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
<p><b>当前纪律：</b>20个交易日纯观察期；真实仓位 0；不打板、不排板、不盯盘、不早盘抢票；只记录模拟触发和收盘复盘。</p>
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
<p>收盘后输入 <code>复盘</code>，按 SOP 更新样本。</p>
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
