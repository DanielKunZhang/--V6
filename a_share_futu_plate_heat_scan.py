#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import multiprocessing as mp
import socket
import time
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DESKTOP_ROOT = Path("/Users/zhangkun/Desktop/AI个人投资公司")
REPORT_ROOT = DESKTOP_ROOT / "报表输出" / "LATEST"
OUTPUT_DIR = ROOT / "backtest_results" / "a_share_futu_plate_heat_scan"


def port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pick(row: dict[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)
    except Exception:
        return default


def is_mainland_common_stock(code: str) -> bool:
    if code.startswith("SH."):
        raw = code.split(".", 1)[1]
        return raw.startswith("6")
    if code.startswith("SZ."):
        raw = code.split(".", 1)[1]
        return raw.startswith(("0", "3"))
    return False


def crowding_risk(row: dict[str, Any]) -> tuple[str, str]:
    name = str(row.get("plate_name", ""))
    ai_hot_keywords = [
        "AI",
        "人工智能",
        "算力",
        "数据中心",
        "光模块",
        "CPO",
        "半导体",
        "芯片",
        "电子元件",
        "被动元件",
        "MLCC",
        "机器人",
        "液冷",
        "服务器",
    ]
    is_ai_hot = any(k.lower() in name.lower() for k in ai_hot_keywords)
    heat = safe_float(row.get("heat_score"))
    up_ratio = safe_float(row.get("up_ratio"))
    strong_ratio = safe_float(row.get("strong_ratio_5pct"))
    limit_count = int(safe_float(row.get("limit_proxy_count")))
    amount = safe_float(row.get("amount_rmb"))

    reasons: list[str] = []
    if is_ai_hot:
        reasons.append("AI/硬件/算力链热门主题")
    if heat >= 70:
        reasons.append("热度极高")
    elif heat >= 55:
        reasons.append("热度偏高")
    if up_ratio >= 0.70:
        reasons.append("板块普涨")
    if strong_ratio >= 0.25:
        reasons.append("强势股占比高")
    if limit_count >= 3:
        reasons.append("涨停代理多")
    if amount >= 100_000_000_000:
        reasons.append("成交额极高")

    if is_ai_hot and (heat >= 70 or strong_ratio >= 0.30 or limit_count >= 5):
        return "EXTREME", "；".join(reasons)
    if is_ai_hot and (heat >= 55 or strong_ratio >= 0.20 or limit_count >= 3):
        return "HIGH", "；".join(reasons)
    if heat >= 70 and (strong_ratio >= 0.25 or limit_count >= 3):
        return "HIGH", "；".join(reasons)
    if heat >= 55 or up_ratio >= 0.70 or strong_ratio >= 0.20:
        return "MED", "；".join(reasons)
    return "LOW", "未见高拥挤代理"


def scan_worker(args: dict[str, Any], queue: mp.Queue) -> None:
    from futu import Market, OpenQuoteContext, Plate, RET_OK

    host = args["host"]
    port = args["port"]
    max_plates = args["max_plates"]
    max_members = args["max_members"]
    plate_classes = [Plate.INDUSTRY, Plate.CONCEPT]

    ctx = OpenQuoteContext(host=host, port=port)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        plate_candidates: list[dict[str, Any]] = []
        for plate_class in plate_classes:
            ret, data = ctx.get_plate_list(Market.SH, plate_class)
            if ret != RET_OK:
                errors.append(f"get_plate_list({plate_class}) failed: {data}")
                continue
            for item in data.to_dict("records"):
                code = str(pick(item, "code", "plate_code"))
                name = str(pick(item, "plate_name", "name", "stock_name"))
                if not code or not name:
                    continue
                plate_candidates.append(
                    {
                        "plate_code": code,
                        "plate_name": name,
                        "plate_class": str(plate_class),
                    }
                )

        seen: set[str] = set()
        unique_plates = []
        for row in plate_candidates:
            if row["plate_code"] in seen:
                continue
            seen.add(row["plate_code"])
            unique_plates.append(row)

        for plate in unique_plates[:max_plates]:
            ret, members = ctx.get_plate_stock(plate["plate_code"])
            if ret != RET_OK:
                errors.append(f"get_plate_stock({plate['plate_code']}) failed: {members}")
                continue
            member_records = members.to_dict("records")
            codes = [str(pick(item, "code", "stock_code")) for item in member_records]
            codes = [code for code in codes if is_mainland_common_stock(code)][:max_members]
            if not codes:
                continue
            ret, snap = ctx.get_market_snapshot(codes)
            if ret != RET_OK:
                errors.append(f"get_market_snapshot({plate['plate_code']}) failed: {snap}")
                continue
            snap_rows = snap.to_dict("records")
            changes = [safe_float(pick(item, "change_rate", "chg_rate")) for item in snap_rows]
            turnovers = [safe_float(pick(item, "turnover", "amount")) for item in snap_rows]
            up_count = sum(1 for value in changes if value > 0)
            strong_count = sum(1 for value in changes if value >= 5)
            limit_proxy_count = sum(1 for value in changes if value >= 9.5)
            sample_count = len(changes)
            up_ratio = up_count / sample_count if sample_count else 0.0
            strong_ratio = strong_count / sample_count if sample_count else 0.0
            amount_rmb = sum(turnovers)
            amount_score = min(math.log10(amount_rmb + 1) / 10, 1.0) if amount_rmb > 0 else 0.0
            heat_score = round(up_ratio * 35 + strong_ratio * 25 + min(limit_proxy_count, 10) * 3 + amount_score * 10, 2)
            leaders = sorted(
                snap_rows,
                key=lambda item: safe_float(pick(item, "change_rate", "chg_rate")),
                reverse=True,
            )[:5]
            row = {
                    **plate,
                    "sample_count": sample_count,
                    "member_count_total": len(member_records),
                    "up_count": up_count,
                    "up_ratio": round(up_ratio, 4),
                    "strong_count_5pct": strong_count,
                    "strong_ratio_5pct": round(strong_ratio, 4),
                    "limit_proxy_count": limit_proxy_count,
                    "zero_change_count": sum(1 for value in changes if value == 0),
                    "amount_rmb": round(amount_rmb, 2),
                    "heat_score": heat_score,
                    "top_leaders": [
                        {
                            "code": str(pick(item, "code")),
                            "name": str(pick(item, "stock_name", "name")),
                            "change_rate": safe_float(pick(item, "change_rate", "chg_rate")),
                            "turnover": safe_float(pick(item, "turnover", "amount")),
                        }
                        for item in leaders
                    ],
            }
            risk_level, risk_reason = crowding_risk(row)
            row["crowding_risk"] = risk_level
            row["crowding_reason"] = risk_reason
            rows.append(row)
            time.sleep(args["sleep_sec"])
    finally:
        ctx.close()
    queue.put({"rows": sorted(rows, key=lambda item: item["heat_score"], reverse=True), "errors": errors})


def run_scan(args: argparse.Namespace) -> dict[str, Any]:
    if not port_open(args.host, args.port):
        return {
            "status": "SKIPPED",
            "reason": f"Futu OpenD not reachable at {args.host}:{args.port}",
            "rows": [],
            "errors": [],
        }
    queue: mp.Queue = mp.Queue()
    proc = mp.Process(
        target=scan_worker,
        args=(
            {
                "host": args.host,
                "port": args.port,
                "max_plates": args.max_plates,
                "max_members": args.max_members,
                "sleep_sec": args.sleep_sec,
            },
            queue,
        ),
    )
    proc.start()
    proc.join(args.timeout_sec)
    if proc.is_alive():
        proc.terminate()
        proc.join(3)
        return {
            "status": "TIMEOUT",
            "reason": f"Futu plate scan exceeded {args.timeout_sec}s",
            "rows": [],
            "errors": [],
        }
    if proc.exitcode != 0:
        return {
            "status": "FAILED",
            "reason": f"scan worker exitcode={proc.exitcode}",
            "rows": [],
            "errors": [],
        }
    result = queue.get() if not queue.empty() else {"rows": [], "errors": ["worker returned no payload"]}
    return {
        "status": "OK" if result.get("rows") else "EMPTY",
        "reason": "",
        "rows": result.get("rows", []),
        "errors": result.get("errors", []),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "plate_code",
        "plate_name",
        "plate_class",
        "heat_score",
        "sample_count",
        "member_count_total",
        "up_count",
        "up_ratio",
        "strong_count_5pct",
        "strong_ratio_5pct",
        "limit_proxy_count",
        "zero_change_count",
        "amount_rmb",
        "crowding_risk",
        "crowding_reason",
        "top_leaders",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            item = dict(row)
            item["top_leaders"] = json.dumps(item.get("top_leaders", []), ensure_ascii=False)
            writer.writerow(item)


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# A股富途板块热度自动扫描",
        "",
        f"- 日期：`{payload['asof']}`",
        f"- 状态：`{payload['status']}`",
        f"- 说明：`{payload.get('reason') or 'OK'}`",
        f"- 扫描板块数：`{len(payload.get('rows', []))}`",
        "- 数据源：Futu OpenD `get_plate_list/get_plate_stock/get_market_snapshot`，不拉历史 K 线。",
        "- 用途：盘面热度 evidence / 人工复核入口，不是买入信号。",
        "",
    ]
    if payload.get("errors"):
        lines.extend(["## 错误/跳过", ""])
        for err in payload["errors"][:10]:
            lines.append(f"- {err}")
        lines.append("")
    lines.extend(
        [
            "## 拥挤/抱团风险提示",
            "",
            "| 板块 | 拥挤风险 | 原因 |",
            "| --- | --- | --- |",
        ]
    )
    risky = [
        row for row in payload.get("rows", [])
        if row.get("crowding_risk") in {"EXTREME", "HIGH"}
    ][:10]
    if risky:
        for row in risky:
            lines.append(f"| {row['plate_name']} | `{row.get('crowding_risk', '')}` | {row.get('crowding_reason', '')} |")
    else:
        lines.append("| 暂无 | `LOW/MED` | 未见高拥挤代理，仍需结合价格位置和复盘判断 |")
    lines.extend(
        [
            "",
            "## 热度 Top 板块",
            "",
            "| 排名 | 板块 | 类型 | 热度 | 拥挤 | 上涨比例 | 强势股 | 涨停代理 | 成交额 | 领涨样本 |",
            "| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for idx, row in enumerate(payload.get("rows", [])[:20], start=1):
        leaders = "；".join(
            f"{item.get('name') or item.get('code')} {item.get('change_rate', 0):.1f}%"
            for item in row.get("top_leaders", [])[:3]
        )
        lines.append(
            f"| {idx} | {row['plate_name']} | {row['plate_class']} | {row['heat_score']:.2f} | `{row.get('crowding_risk', 'LOW')}` | "
            f"{row['up_ratio']:.1%} | {row['strong_count_5pct']} | {row['limit_proxy_count']} | "
            f"{row['amount_rmb']:.0f} | {leaders} |"
        )
    lines.extend(
        [
            "",
            "## 数据质量提示",
            "",
            "- 若非交易日/休市时 `change_rate` 全为 0，本报告只说明接口可用和板块成分/成交额可读，不代表真实当日强弱。",
            "- 交易日收盘后或盘中重跑，才适合用于板块热度复核。",
            "",
            "## 人工复核口径",
            "",
            "- 若 Top 板块与政策/产业线索一致，可复制摘要到 A股Radar 人工信息搜集 INBOX。",
            "- 若主题强但拥挤风险为 HIGH/EXTREME，只能降级为观察或一手级 pilot 复核，不允许追高。",
            "- 若主题强但标的无业绩/订单/政策/公告验证，不进入实盘候选。",
            "- 若只是纯涨幅榜、无政策/产业/公告支撑，不写入 theme evidence。",
            "- 若 OpenD 不可用，本报告会 SKIPPED/TIMEOUT，不阻塞 daily loop。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan A-share plate heat via Futu snapshots without K-line quota.")
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--max-plates", type=int, default=8)
    parser.add_argument("--max-members", type=int, default=80)
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--sleep-sec", type=float, default=3.2)
    args = parser.parse_args()

    result = run_scan(args)
    payload = {
        "asof": args.asof,
        "source": "Futu OpenD plate/snapshot APIs",
        "kline_used": False,
        "params": {
            "max_plates": args.max_plates,
            "max_members": args.max_members,
            "timeout_sec": args.timeout_sec,
        },
        **result,
    }
    md = render_md(payload)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    (OUTPUT_DIR / "latest.json").write_text(json_text, encoding="utf-8")
    (OUTPUT_DIR / "latest.md").write_text(md, encoding="utf-8")
    write_csv(OUTPUT_DIR / "latest.csv", payload["rows"])
    (REPORT_ROOT / "A股富途板块热度自动扫描_LATEST.json").write_text(json_text, encoding="utf-8")
    (REPORT_ROOT / "A股富途板块热度自动扫描_LATEST.md").write_text(md, encoding="utf-8")
    write_csv(REPORT_ROOT / "A股富途板块热度自动扫描_LATEST.csv", payload["rows"])
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
