#!/usr/bin/env python3
"""
宏观择时信号层 v1.0 — "要不要在市场里"
借鉴 GMO（CAPE择时）、Bridgewater（债务周期）、Goldman（Bull/Bear指标）框架

核心指标（均通过公开数据获取）：
  1. Shiller CAPE（美股整体估值）
  2. 高收益债利差 HY OAS（信用压力）
  3. 美债期限利差 10Y-2Y（衰退预警）
  4. VIX（恐慌情绪）
  5. 美元指数 DXY（全球流动性）
  6. 铜金比 Copper/Gold（经济增长预期）

输出：
  🟢 绿灯 - 满仓进攻（新机会积极出手）
  🟡 黄灯 - 观望（等待更好的击球区，避免加仓）
  🔴 红灯 - 减仓防御（高估值+信用收紧，严格MoS标准）

用法：
  python3 macro_signal.py              # 获取当前信号，生成报告
  python3 macro_signal.py --no-email  # 不发邮件
  python3 macro_signal.py --summary   # 强制发送邮件
  python3 macro_signal.py --offline   # 跳过网络获取，使用缓存/手动数据
"""

import json
import logging
import argparse
import time
import os
from datetime import date, datetime
from pathlib import Path

from env_utils import load_local_env

load_local_env()

SCRIPT_DIR    = Path(__file__).parent
CONFIG_PATH   = SCRIPT_DIR / "config.json"
LOG_PATH      = SCRIPT_DIR / "screener.log"
MACRO_CACHE   = SCRIPT_DIR / "macro_cache.json"   # 手动/缓存宏观数据

# ─────────────────────────────────────────────────────────────
# 指标定义与评分规则
# ─────────────────────────────────────────────────────────────

"""
每个指标给出 score: -2(极度危险) ~ +2(极度友好)，加总后：
  总分 ≥  4：🟢 绿灯
  总分 1~3：🟡 黄灯（观望）
  总分 ≤  0：🔴 红灯（防御）
"""

INDICATORS = {
    "cape": {
        "label": "Shiller CAPE（美股估值）",
        "source": "multpl.com / yfinance",
        "unit": "倍",
        "description": "CAPE>30为历史高位，GMO认为>25时预期回报显著下降",
        "thresholds": [
            # (value_upper_bound, score, label)
            (18,  2, "极度低估"),
            (22,  1, "合理偏低"),
            (27,  0, "历史均值附近"),
            (32, -1, "偏高"),
            (999,-2, "历史高位警戒"),
        ]
    },
    "hy_oas": {
        "label": "高收益债利差 HY OAS（bps）",
        "source": "FRED / ICE BofA",
        "unit": "bps",
        "description": "利差收窄=信用乐观/流动性宽松；利差扩大=信用压力/衰退预警",
        "thresholds": [
            (350,  2, "极度收窄，乐观情绪"),
            (450,  1, "正常区间"),
            (600,  0, "偏高，需关注"),
            (800, -1, "信用压力"),
            (9999,-2, "危机水平"),
        ]
    },
    "yield_curve": {
        "label": "美债期限利差 10Y-2Y（bps）",
        "source": "FRED / yfinance",
        "unit": "bps",
        "description": "倒挂（负值）是衰退预警；恢复正常=经济预期改善",
        "thresholds": [
            (-9999,-2, "严重倒挂"),
            (-50,  -1, "轻度倒挂"),
            (0,     0, "平坦"),
            (80,    1, "正常"),
            (9999,  2, "陡峭，经济乐观"),
        ],
        "reverse": True  # 值越大越好
    },
    "vix": {
        "label": "VIX 恐慌指数",
        "source": "CBOE / yfinance",
        "unit": "",
        "description": "VIX>30=恐慌（也是买入机会），VIX<15=过度自满",
        "thresholds": [
            (15,  -1, "过度乐观，自满"),  # 注：VIX低也是风险信号
            (20,   1, "正常"),
            (30,   0, "波动上升"),
            (40,  -1, "高度恐慌"),
            (9999,-2, "危机"),
        ],
        "special": "vix"  # 特殊处理：VIX<15也是警告
    },
    "dxy": {
        "label": "美元指数 DXY",
        "source": "yfinance",
        "unit": "",
        "description": "DXY强势=全球流动性收紧，对新兴市场/港股/A股不利",
        "thresholds": [
            (95,   2, "弱美元，全球流动性宽松"),
            (100,  1, "温和"),
            (105,  0, "偏强"),
            (110, -1, "强美元压力"),
            (9999,-2, "极强美元，新兴市场承压"),
        ]
    },
    "copper_gold": {
        "label": "铜金比（Dr. Copper指标）",
        "source": "yfinance (HG=F / GC=F)",
        "unit": "比值",
        "description": "铜金比上升=经济扩张预期；下降=避险/衰退担忧",
        "thresholds": [
            (0.15,  -2, "铜金比极低，避险主导"),
            (0.18,  -1, "偏低"),
            (0.22,   0, "中性"),
            (0.28,   1, "乐观"),
            (9999,   2, "强劲经济预期"),
        ]
    },
}


# ─────────────────────────────────────────────────────────────
# 数据获取
# ─────────────────────────────────────────────────────────────

def fetch_yfinance_price(symbol: str, delay: float = 1.5) -> float | None:
    """从 yfinance 获取最新收盘价。"""
    try:
        import yfinance as yf
        time.sleep(delay)
        t = yf.Ticker(symbol)
        hist = t.history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logging.debug(f"yfinance {symbol} 失败: {e}")
        return None


def fetch_macro_data(offline: bool = False) -> dict:
    """
    尝试从 yfinance 获取宏观数据。
    若 offline=True 或获取失败，从 macro_cache.json 读取手动输入的数据。
    """
    cache = {}
    if MACRO_CACHE.exists():
        try:
            cache = json.loads(MACRO_CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass

    DEFAULTS = {
        "cape": 36.5, "hy_oas": 420, "yield_curve": 20,
        "vix": 20.0, "dxy": 103.0, "copper_gold": 0.22,
    }
    if offline:
        logging.info("离线模式：使用缓存/手动宏观数据")
        for k, v in DEFAULTS.items():
            if k not in cache:
                cache[k] = v
                logging.info(f"  {k}: 使用内置默认值 {v}")
        return cache

    data = dict(cache)  # start with cache as fallback

    logging.info("获取宏观数据...")

    # 1. CAPE — yfinance 无直接来源，使用缓存或手动值
    if "cape" not in data:
        data["cape"] = 36.5   # 2026-04 近似值，需定期手动更新
        logging.info(f"  CAPE: 使用默认值 {data['cape']}（请定期更新 macro_cache.json）")
    else:
        logging.info(f"  CAPE: {data['cape']}（来自缓存）")

    # 2. HY OAS — 无免费实时API，使用缓存/手动
    if "hy_oas" not in data:
        data["hy_oas"] = 380  # 2026-04 近似值
        logging.info(f"  HY OAS: 使用默认值 {data['hy_oas']}bps（请定期更新 macro_cache.json）")
    else:
        logging.info(f"  HY OAS: {data['hy_oas']}bps（来自缓存）")

    # 3. 收益率曲线：10Y-2Y（通过 yfinance ^TNX）
    try:
        t10 = fetch_yfinance_price("^TNX")   # 10Y Treasury yield (%)
        if t10:
            t2_rate = data.get("t2y_yield", t10 - 0.3)
            spread_bps = (t10 - t2_rate) * 100
            data["yield_curve"] = round(spread_bps, 1)
            logging.info(f"  10Y-2Y利差: {spread_bps:.1f}bps（10Y={t10:.2f}%）")
        else:
            if "yield_curve" not in data:
                data["yield_curve"] = 20  # 默认略正
            logging.info(f"  10Y-2Y利差: 使用缓存/默认值 {data['yield_curve']}bps")
    except Exception as e:
        logging.debug(f"  收益率曲线获取失败: {e}")
        if "yield_curve" not in data:
            data["yield_curve"] = 20

    # 4. VIX
    try:
        vix = fetch_yfinance_price("^VIX")
        if vix:
            data["vix"] = round(vix, 1)
            logging.info(f"  VIX: {vix:.1f}")
        else:
            if "vix" not in data:
                data["vix"] = 20.0
            logging.info(f"  VIX: 使用缓存/默认值 {data['vix']}")
    except Exception:
        if "vix" not in data:
            data["vix"] = 20.0

    # 5. DXY
    try:
        dxy = fetch_yfinance_price("DX-Y.NYB")
        if dxy:
            data["dxy"] = round(dxy, 2)
            logging.info(f"  DXY: {dxy:.2f}")
        else:
            if "dxy" not in data:
                data["dxy"] = 103.0
            logging.info(f"  DXY: 使用缓存/默认值 {data['dxy']}")
    except Exception:
        if "dxy" not in data:
            data["dxy"] = 103.0

    # 6. 铜金比
    try:
        cu = fetch_yfinance_price("HG=F")   # 铜期货
        au = fetch_yfinance_price("GC=F")   # 黄金期货
        if cu and au and au > 0:
            ratio = cu / au
            data["copper_gold"] = round(ratio, 4)
            logging.info(f"  铜金比: {ratio:.4f}（Cu={cu:.2f}, Au={au:.2f}）")
        else:
            if "copper_gold" not in data:
                data["copper_gold"] = 0.22
            logging.info(f"  铜金比: 使用缓存/默认值 {data['copper_gold']}")
    except Exception:
        if "copper_gold" not in data:
            data["copper_gold"] = 0.22

    # 保存缓存
    data["_last_updated"] = datetime.now().isoformat()[:16]
    MACRO_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return data


# ─────────────────────────────────────────────────────────────
# 评分逻辑
# ─────────────────────────────────────────────────────────────

def score_indicator(key: str, value: float) -> tuple[int, str]:
    """返回 (score, label)。"""
    ind = INDICATORS[key]
    thresholds = ind["thresholds"]
    reverse = ind.get("reverse", False)

    if key == "vix":
        # VIX 特殊：过低(自满)=-1，正常=+1，偏高=0，危机=-2
        if value <= 15:   return -1, "过度乐观，自满情绪"
        if value <= 20:   return  1, "正常区间"
        if value <= 30:   return  0, "波动性上升"
        if value <= 40:   return -1, "高度恐慌"
        return -2, "危机级恐慌"

    if reverse:
        # yield_curve: 值越大越好，阈值是下界
        prev_score, prev_label = -2, thresholds[0][2]
        for upper, score, label in thresholds:
            if value <= upper:
                return score, label
            prev_score, prev_label = score, label
        return prev_score, prev_label

    for upper, score, label in thresholds:
        if value <= upper:
            return score, label
    return thresholds[-1][1], thresholds[-1][2]


def compute_macro_signal(data: dict) -> dict:
    """计算各指标评分并汇总信号。"""
    scores = {}
    for key in INDICATORS:
        if key not in data:
            continue
        val = data[key]
        sc, lbl = score_indicator(key, val)
        scores[key] = {
            "value": val,
            "score": sc,
            "label": lbl,
            "indicator": INDICATORS[key],
        }

    total = sum(s["score"] for s in scores.values())
    n = len(scores)
    max_possible = n * 2

    if total >= 4:
        signal = "green"
        signal_text = "🟢 绿灯 — 满仓进攻"
        signal_desc = "宏观环境友好，估值合理，流动性充裕。新的高质量机会可积极出手，组合可保持满仓。"
    elif total >= 1:
        signal = "yellow"
        signal_text = "🟡 黄灯 — 观望等待"
        signal_desc = "宏观环境混合信号。维持现有持仓，但对新机会提高MoS门槛至≥40%（高于标准30%）。避免追涨，等待更好的击球区。"
    else:
        signal = "red"
        signal_text = "🔴 红灯 — 防御减仓"
        signal_desc = "宏观环境高风险（高估值+信用收紧或经济下行信号）。新机会MoS门槛提高至≥50%。考虑对冲（现金/短债/保护性期权）。即使好公司在熊市也会继续下跌。"

    return {
        "scores": scores,
        "total_score": total,
        "max_possible": max_possible,
        "signal": signal,
        "signal_text": signal_text,
        "signal_desc": signal_desc,
    }


# ─────────────────────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────────────────────

SIGNAL_STYLE = {
    "green":  {"bg": "#e8f5e9", "border": "#43a047", "header": "#1b5e20"},
    "yellow": {"bg": "#fff8e1", "border": "#f9a825", "header": "#e65100"},
    "red":    {"bg": "#ffebee", "border": "#c62828", "header": "#b71c1c"},
}

SCORE_COLOR = {2: "#2e7d32", 1: "#558b2f", 0: "#f57f17", -1: "#e65100", -2: "#c62828"}


def generate_html(result: dict, data: dict, run_date: str) -> str:
    sig = result["signal"]
    ss = SIGNAL_STYLE[sig]
    scores = result["scores"]

    # Indicator rows
    ind_rows = ""
    for key, s in scores.items():
        sc = s["score"]
        val = s["value"]
        ind = s["indicator"]
        bar_w = int((sc + 2) / 4 * 100)  # -2~+2 → 0~100%
        bar_color = SCORE_COLOR.get(sc, "#90a4ae")
        sc_text = f"+{sc}" if sc > 0 else str(sc)
        unit = ind.get("unit", "")
        ind_rows += f"""
        <tr>
          <td><strong>{ind['label']}</strong><br>
              <span style="font-size:11px;color:#90a4ae">{ind['description']}</span></td>
          <td style="font-weight:700;font-size:15px">{val:g}{unit}</td>
          <td>
            <div style="display:flex;align-items:center;gap:8px">
              <div style="background:#eceff1;border-radius:4px;height:8px;width:80px">
                <div style="width:{bar_w}%;height:8px;border-radius:4px;background:{bar_color}"></div>
              </div>
              <span style="color:{bar_color};font-weight:700">{sc_text}</span>
            </div>
          </td>
          <td><span style="font-size:12.5px;color:{bar_color}">{s['label']}</span></td>
          <td style="font-size:11px;color:#90a4ae">{ind['source']}</td>
        </tr>"""

    # Action implications
    mos_text = {
        "green":  "维持标准 MoS ≥ 30%，高质量机会可积极建仓",
        "yellow": "提高 MoS 门槛至 ≥ 40%，放慢建仓节奏",
        "red":    "MoS 门槛 ≥ 50%，考虑保持20-30%现金或对冲",
    }[sig]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>宏观择时信号 {run_date}</title>
  <style>
    * {{ box-sizing:border-box;margin:0;padding:0 }}
    body {{ font-family:-apple-system,'PingFang SC',sans-serif;background:#f4f6f9;
            padding:20px;max-width:900px;margin:0 auto }}
    .header {{ background:linear-gradient(135deg,#0d47a1,#1565c0,#1976d2);
               color:white;padding:28px 36px;border-radius:16px;margin-bottom:20px }}
    .header h1 {{ font-size:22px;margin-bottom:4px }}
    .card {{ background:white;border-radius:12px;padding:22px;
             box-shadow:0 2px 8px rgba(0,0,0,.07);margin-bottom:18px }}
    .section-title {{ font-size:14px;font-weight:700;color:#0d47a1;
                      border-bottom:2px solid #e3f2fd;padding-bottom:8px;margin-bottom:14px }}
    table {{ width:100%;border-collapse:collapse;font-size:13px }}
    th {{ background:#e3f2fd;color:#0d47a1;padding:9px 12px;text-align:left;font-weight:600 }}
    td {{ padding:9px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle }}
    tr:hover td {{ background:#f8faff }}
    .footer {{ text-align:center;color:#90a4ae;font-size:11px;padding:16px 0 }}
    .signal-box {{ background:{ss['bg']};border:2px solid {ss['border']};
                   border-radius:14px;padding:22px 28px;margin-bottom:18px }}
  </style>
</head>
<body>

<div class="header">
  <h1>🌐 宏观择时信号层</h1>
  <div style="opacity:.82;font-size:13px">{run_date} &nbsp;|&nbsp; 借鉴 GMO · Bridgewater · Goldman 框架</div>
</div>

<div class="signal-box">
  <div style="font-size:24px;font-weight:700;color:{ss['header']}">{result['signal_text']}</div>
  <div style="font-size:13.5px;color:#5d4037;margin-top:8px">{result['signal_desc']}</div>
  <div style="margin-top:12px;background:rgba(255,255,255,0.6);border-radius:8px;
              padding:10px 14px;font-size:13px;color:{ss['header']}">
    📋 仓位建议：{mos_text}
  </div>
  <div style="margin-top:8px;font-size:12px;color:#90a4ae">
    综合评分：{result['total_score']} / {result['max_possible']}（-{result['max_possible']//2}=极危险，+{result['max_possible']//2}=极友好）
  </div>
</div>

<div class="card">
  <div class="section-title">📊 宏观指标详情</div>
  <table>
    <thead>
      <tr><th width="35%">指标</th><th width="12%">当前值</th><th width="15%">评分</th><th width="20%">状态</th><th>数据源</th></tr>
    </thead>
    <tbody>{ind_rows}</tbody>
  </table>
  <p style="font-size:11.5px;color:#90a4ae;margin-top:10px">
    评分：+2=极友好 | +1=友好 | 0=中性 | -1=需关注 | -2=危险<br>
    CAPE 和 HY OAS 为手动更新（见 macro_cache.json），其余指标自动从 yfinance 获取。
  </p>
</div>

<div class="card" style="background:#f8faff;border:1px solid #e3f2fd">
  <div class="section-title">📖 框架说明</div>
  <table>
    <thead><tr><th>信号</th><th>总分</th><th>投资含义</th><th>MoS门槛</th></tr></thead>
    <tbody>
      <tr style="background:#e8f5e9">
        <td>🟢 绿灯</td><td>≥ +4</td><td>宏观顺风，积极寻找机会</td><td>≥ 30%</td>
      </tr>
      <tr style="background:#fff8e1">
        <td>🟡 黄灯</td><td>+1 ~ +3</td><td>混合信号，等待击球区</td><td>≥ 40%</td>
      </tr>
      <tr style="background:#ffebee">
        <td>🔴 红灯</td><td>≤ 0</td><td>高风险，防御优先</td><td>≥ 50%</td>
      </tr>
    </tbody>
  </table>
  <p style="font-size:12px;color:#90a4ae;margin-top:10px">
    ⚠️ 本系统是辅助决策工具，不是机械交易信号。红灯期间持有高质量股票（PDD/NVDA/腾讯）仍是正确的——
    红灯的含义是"不要急于新建仓"，而非"卖出所有持仓"。<br>
    数据来源：Shiller CAPE（multpl.com更新至上月），HY OAS（FRED，手动更新），VIX/DXY/铜金比（yfinance实时）。
  </p>
</div>

<div class="card" style="background:#fff3e0;border:1px solid #ff8f00">
  <div class="section-title" style="color:#e65100">🔧 手动更新说明</div>
  <p style="font-size:13px;color:#5d4037">
    以下指标需每月手动更新（约5分钟）：<br>
    1. <strong>CAPE</strong>：访问 <a href="https://www.multpl.com/shiller-pe">multpl.com/shiller-pe</a>，
       填入 macro_cache.json 的 "cape" 字段<br>
    2. <strong>HY OAS</strong>：访问
       <a href="https://fred.stlouisfed.org/series/BAMLH0A0HYM2">FRED BAMLH0A0HYM2</a>，
       填入 "hy_oas" 字段（单位：bps）<br>
    3. <strong>2Y国债收益率</strong>（用于精确利差计算）：
       填入 "t2y_yield" 字段（单位：%，例如 4.8）<br><br>
    <code>macro_cache.json</code> 位于 screener/ 目录，JSON格式，直接修改即可。
  </p>
</div>

<div class="footer">
  宏观择时信号层 v1.0 · {run_date}<br>
  框架参考：GMO CAPE择时 · Bridgewater债务周期 · Goldman Bull/Bear指标 · 仅供参考
</div>

</body>
</html>"""


# ─────────────────────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────────────────────

def send_email(html: str, subject: str, cfg: dict) -> bool:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    ec = cfg.get("email", {})
    if not ec.get("enabled"):
        return False
    sender = ec.get("sender", "")
    password = os.environ.get("IC_EMAIL_PASSWORD") or ec.get("password", "")
    recipients = ec.get("recipients", [])
    if not all([sender, password, recipients]) or "YOUR_" in password:
        logging.warning("邮件配置不完整，跳过")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        if ec.get("use_ssl_direct", False):
            with smtplib.SMTP_SSL(ec["smtp_host"], ec["smtp_port"]) as srv:
                srv.login(sender, password)
                srv.sendmail(sender, recipients, msg.as_string())
        else:
            with smtplib.SMTP(ec["smtp_host"], ec["smtp_port"]) as srv:
                if ec.get("use_tls", True):
                    srv.starttls()
                srv.login(sender, password)
                srv.sendmail(sender, recipients, msg.as_string())
        logging.info(f"✅ 邮件已发送至 {recipients}")
        return True
    except Exception as e:
        logging.error(f"邮件发送失败: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


def main():
    parser = argparse.ArgumentParser(description="宏观择时信号层")
    parser.add_argument("--no-email", action="store_true")
    parser.add_argument("--summary",  action="store_true", help="强制发邮件")
    parser.add_argument("--offline",  action="store_true", help="使用缓存数据，不联网")
    args = parser.parse_args()

    setup_logging()
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}

    data = fetch_macro_data(offline=args.offline)
    result = compute_macro_signal(data)

    logging.info(f"\n====== 宏观择时信号 {run_date} ======")
    logging.info(f"信号：{result['signal_text']}")
    logging.info(f"综合评分：{result['total_score']} / {result['max_possible']}")
    for key, s in result["scores"].items():
        sc_str = f"+{s['score']}" if s['score'] > 0 else str(s['score'])
        logging.info(f"  {s['indicator']['label']:30s}  {s['value']:>8g}  评分{sc_str:3s}  {s['label']}")

    html = generate_html(result, data, run_date)

    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_file = reports_dir / f"macro_{date.today().strftime('%Y%m%d')}.html"
    report_file.write_text(html, encoding="utf-8")
    logging.info(f"\n报告已保存: {report_file}")

    prefix = cfg.get("email", {}).get("subject_prefix", "[投资预警]")
    sig = result["signal"]
    should_send = args.summary or (not args.no_email and sig in ("red", "yellow"))
    if should_send:
        icon = "🔴" if sig == "red" else "🟡"
        subject = f"{prefix} {icon} 宏观择时信号：{result['signal_text']} （评分{result['total_score']}）"
        send_email(html, subject, cfg)
    elif sig == "green" and not args.no_email:
        logging.info("绿灯信号，不自动发邮件（满仓状态无需提醒）")


if __name__ == "__main__":
    main()
