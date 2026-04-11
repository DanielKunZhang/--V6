#!/usr/bin/env python3
"""
美股 Iron Condor 实盘交易脚本（非对称铁鹰 + 2x杠杆版本）

策略配置（2026-04-11 HV阈值场景扫描972组最优解 — Scenario C）：
  标的: QQQ ($18k×2=36k) + IWM ($6k×2=12k) + GLD ($6k×2=12k)，名义资本$30k（2x杠杆）
  非对称OTM: Put侧 3.0%（更近，收put skew溢价）/ Call侧 6.0%（972组扫描最优）
  翼宽 Wing: 9%
  DTE: 45天（月度/季度期权）
  杠杆: 2x（实际资本$15k + 融资$15k，年化融资成本5.5%=$825/年）
  VIX硬止损: HV20 > 39% 强平（纯HV口径，与Finviz/富途一致），恢复阈值 HV20 < 28%
  HV20开仓阈值: QQQ≤25%, IWM≤25%, GLD≤18%（Scenario C，纯HV口径，去除原×1.15通胀）

回测（2010-2025，16年，$15k实际资本×2x杠杆）：
  年化收益 +30.49%  最大回撤 -6.49%  夏普 2.63  Calmar 4.70  期末 ~$1,060,000
  972组全量扫描第1名（3个HV场景 × 324参数组合，按夏普/Calmar综合最优）
  HV阈值说明：历史波动率使用纯HV20（无×1.15），BS定价时IV估算=HV20×1.15（更接近实盘IV）
"""

import time
import json
import logging
import sys
import argparse
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set

# ── IC 持仓追踪文件（只操作策略自己开的期权，不误碰 Wheel/正股）──────
_IC_STATE_FILE        = Path(__file__).parent / "logs" / "ic_open_codes.json"
_IC_COOLDOWN_FILE     = Path(__file__).parent / "logs" / "ic_cooldown_state.json"
_IC_VIX_HARDSTOP_FILE = Path(__file__).parent / "logs" / "ic_vix_hardstop.json"
_IC_OPEN_TRADE_FILE   = Path(__file__).parent / "logs" / "ic_open_trade.json"
_IC_TRADE_HISTORY_CSV = Path(__file__).parent / "logs" / "trade_history.csv"


def _load_cooldown_state() -> Dict:
    """读取各标的上次平仓日期（用于实现5天开仓冷却期）"""
    try:
        if _IC_COOLDOWN_FILE.exists():
            return json.loads(_IC_COOLDOWN_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cooldown_state(state: Dict):
    """持久化冷却状态"""
    _IC_COOLDOWN_FILE.parent.mkdir(exist_ok=True)
    _IC_COOLDOWN_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_vix_hardstop_state() -> Dict:
    """读取各标的 VIX 硬止损状态（是否处于硬止损恢复等待期）"""
    try:
        if _IC_VIX_HARDSTOP_FILE.exists():
            return json.loads(_IC_VIX_HARDSTOP_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_vix_hardstop_state(state: Dict):
    _IC_VIX_HARDSTOP_FILE.parent.mkdir(exist_ok=True)
    _IC_VIX_HARDSTOP_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _set_vix_hard_stop(asset_name: str):
    """VIX 硬止损触发时，记录进入硬止损状态"""
    state = _load_vix_hardstop_state()
    state[asset_name] = date.today().isoformat()
    _save_vix_hardstop_state(state)
    logger.info(f"[{asset_name}] 🚨 VIX 硬止损状态已记录，等待 HV20 < {VIX_COOLDOWN_HV:.0%} 恢复")


def _is_vix_hard_stopped(asset_name: str) -> bool:
    """检查标的是否处于 VIX 硬止损恢复等待期"""
    return asset_name in _load_vix_hardstop_state()


def _clear_vix_hard_stop(asset_name: str):
    """HV20 回落到冷却阈值以下时，解除 VIX 硬止损状态"""
    state = _load_vix_hardstop_state()
    if asset_name in state:
        state.pop(asset_name)
        _save_vix_hardstop_state(state)
        logger.info(f"[{asset_name}] ✅ VIX 硬止损解除")


# ── 实盘绩效持久化（trade_history.csv）─────────────────────────────────

def _load_open_trade(asset_name: str) -> Dict:
    """读取当前已开仓的交易元数据（开仓日期、行权价、权利金等）"""
    try:
        if _IC_OPEN_TRADE_FILE.exists():
            data = json.loads(_IC_OPEN_TRADE_FILE.read_text(encoding="utf-8"))
            return data.get(asset_name, {})
    except Exception:
        pass
    return {}


def _save_open_trade(asset_name: str, trade: Dict):
    """保存开仓元数据"""
    _IC_OPEN_TRADE_FILE.parent.mkdir(exist_ok=True)
    try:
        data = json.loads(_IC_OPEN_TRADE_FILE.read_text(encoding="utf-8")) if _IC_OPEN_TRADE_FILE.exists() else {}
    except Exception:
        data = {}
    data[asset_name] = trade
    _IC_OPEN_TRADE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_open_trade(asset_name: str):
    """平仓后清除开仓元数据"""
    try:
        if _IC_OPEN_TRADE_FILE.exists():
            data = json.loads(_IC_OPEN_TRADE_FILE.read_text(encoding="utf-8"))
            data.pop(asset_name, None)
            _IC_OPEN_TRADE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _append_trade_history(row: Dict):
    """追加一条交易记录到 trade_history.csv（开仓 OPEN 或平仓 CLOSE）"""
    import csv as _csv
    _IC_TRADE_HISTORY_CSV.parent.mkdir(exist_ok=True)
    fields = ["date", "time", "asset", "action", "expiry",
              "sell_put", "sell_call", "buy_put", "buy_call",
              "groups", "net_premium", "days_held", "realized_pnl", "close_reason"]
    write_header = not _IC_TRADE_HISTORY_CSV.exists()
    with open(_IC_TRADE_HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fields})


def _record_close_date(asset_name: str):
    """平仓时记录当天日期，触发冷却期计时"""
    state = _load_cooldown_state()
    state[asset_name] = date.today().isoformat()
    _save_cooldown_state(state)
    logger.info(f"[{asset_name}] 📝 冷却期开始：{state[asset_name]}")


def _load_ic_codes() -> Set[str]:
    """读取 IC 策略已开仓的期权代码集合"""
    try:
        if _IC_STATE_FILE.exists():
            data = json.loads(_IC_STATE_FILE.read_text(encoding="utf-8"))
            return set(data.get("codes", []))
    except Exception:
        pass
    return set()


def _save_ic_codes(codes: Set[str]):
    """持久化 IC 策略持仓代码"""
    _IC_STATE_FILE.parent.mkdir(exist_ok=True)
    _IC_STATE_FILE.write_text(
        json.dumps({"codes": sorted(codes)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _add_ic_codes(new_codes: List[str]):
    """开仓后追加代码"""
    existing = _load_ic_codes()
    existing.update(new_codes)
    _save_ic_codes(existing)


def _remove_ic_codes(closed_codes: List[str]):
    """平仓后移除代码"""
    existing = _load_ic_codes()
    for c in closed_codes:
        existing.discard(c)
    _save_ic_codes(existing)


def _round_option_price(price: float) -> float:
    """
    将期权价格四舍五入到富途API要求的精度。

    美股期权 Penny Pilot 规则（QQQ/IWM/GLD 均在内）：
      价格 < $3.00  → 最小报价单位 $0.01
      价格 >= $3.00 → 最小报价单位 $0.05（但交易所实际多为 $0.01，统一用 $0.01 安全）

    富途 API 拒绝超过2位小数的价格（如 $8.525），所以统一四舍五入到 $0.01。
    最低报价 $0.01，避免提交 $0.00。
    """
    rounded = round(price, 2)
    return max(rounded, 0.01)


def _escalate_close_price(close_side_is_buy: bool, bid: float, ask: float, round_num: int) -> float:
    """
    平仓递进价格（3轮）：
      round 0: mid 价（(bid+ask)/2）
      round 1: 75% 向市价方向（buy→ask, sell→bid）
      round 2: 市价 + 3% 缓冲（确保成交）
    """
    if bid <= 0 and ask <= 0:
        return 0.01
    mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else max(bid, ask)
    if close_side_is_buy:   # 买入平仓（空头期权）→ 价格向 ask 靠拢
        levels = [mid, mid + 0.5 * (ask - mid), ask * 1.03]
    else:                    # 卖出平仓（多头期权）→ 价格向 bid 靠拢
        levels = [mid, mid - 0.5 * (mid - bid), bid * 0.97]
    return _round_option_price(levels[min(round_num, 2)])


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============ 多标的配置（非对称铁鹰 P3.5%/C5.0% + 2x杠杆：324组扫描最优解，Calmar4.01，年化27.97%）============
# 三标的相关性：QQQ-IWM 0.634，QQQ-GLD 0.248，IWM-GLD 0.342
# 分散效果：GLD 最佳对冲（与股票低相关），IWM 提供小盘分散
# 回测（2010-2025，16年）：$15k实际资本×2x杠杆 → ~$1,060k，年化+30.49%，最大回撤-6.49%，夏普2.63，Calmar4.70
# 2x杠杆实现：每个标的开2x组数（QQQ 4组/IWM 2组/GLD 2组），融资$15k，名义$30k（QQQ $18k / IWM $6k / GLD $6k）
# HV20阈值说明：使用纯HV20（与Finviz/富途口径一致，无×1.15通胀），Scenario C（972组扫描最优场景）
ASSETS = [
    {"ticker": "US.QQQ", "name": "QQQ", "capital": 18_000, "max_groups": 4, "hv20_threshold": 0.25},   # 纳斯达克100: 纯HV≤25%（Scenario C）
    {"ticker": "US.IWM", "name": "IWM", "capital": 6_000,  "max_groups": 2, "hv20_threshold": 0.25},   # 罗素2000小盘: 纯HV≤25%（Scenario C）
    {"ticker": "US.GLD", "name": "GLD", "capital": 6_000,  "max_groups": 2, "hv20_threshold": 0.18},   # 黄金ETF: 纯HV≤18%（Scenario C）
]

# 兼容旧代码引用（取第一个标的）
STOCK_CONFIG = {"ticker": ASSETS[0]["ticker"], "name": ASSETS[0]["name"]}

# Iron Condor 共享参数（三个标的使用相同策略参数）
IC_CONFIG = {
    "put_otm": 0.030,                  # Put侧 3.0% OTM（972组扫描最优：Scenario C P3.0%/C6.0%/W9%/DTE45）
    "call_otm": 0.060,                 # Call侧 6.0% OTM（972组扫描最优：夏普2.63, Calmar4.70）
    "otm_distance": 0.05,              # 对称OTM fallback（慢熊防御/兼容旧代码用）
    "wing_width": 0.09,                # 9% Wing（扩宽翼宽增加期权流动性，与更长DTE配合）
    "entry_mode": "pre_expiry",        # 到期前入场
    "entry_days_before_expiry": 45,    # DTE=45（月度/季度期权，更长时间价值衰减）
    "cooldown_days": 5,                # 开仓冷却期（每标的独立计算）
    "max_groups": 1,                   # fallback默认值（实际被ASSETS[x]["max_groups"]覆盖：QQQ=4, IWM=2, GLD=2）
    "min_iv": 0.0,
    "early_close_days": 2,             # 到期前2天强制平仓
    "min_premium": 30,                 # 最低权利金（IWM/GLD权利金较小，调低门槛）
    "estimated_credit_per_group": 100, # 每组估算权利金（三标的均值）
    "profit_target_pct": 0.50,         # 50%止盈目标
    "hv20_threshold": 0.25,            # HV20上限（fallback；实际由ASSETS[x]["hv20_threshold"]覆盖）
    "slow_bear_threshold_20d": -0.07,  # 慢熊检测
    "slow_bear_defense": "increase_otm",
    "slow_bear_otm_increase": 0.25,
}

# VIX / HV20 风险控制阈值（与 composite_backtest.py 回测保持一致）
VIX_HARD_STOP_HV   = 0.39   # HV20 ≥ 39%：触发硬止损，强平所有持仓（回测中 VIX_HARD_STOP_HV）
VIX_COOLDOWN_HV    = 0.28   # HV20 < 28%：硬止损解除，恢复开仓（回测中 VIX_COOLDOWN_HV）
VIX_DELEVERAGE_HV  = 0.22   # HV20 > 22%：建议将杠杆从2x降至1x（回测中 VIX_DELEVERAGE）

# 总初始本金
REAL_CAPITAL    = 15_000  # 实际投入资本（USD）
LEVERAGE        = 2.0     # 杠杆倍率（融资$15k，名义$30k）
MARGIN_RATE     = 0.055   # 融资年利率 5.5%（富途保证金利率）
INITIAL_CAPITAL = REAL_CAPITAL  # 别名，保持与旧代码兼容

# 动态组数配置（配置F=20x上限，与回测 dynamic_composite_backtest.py 对齐）
# effective_groups = base_groups × (account_equity / total_initial_capital)，受 cap 限制
DYNAMIC_SIZING   = True   # 是否启用动态组数（False=固定组数，与旧行为一致）
GROUPS_CAP_MULT  = 20     # 组数上限倍数：base_groups × 20（QQQ=80, IWM=40, GLD=40）

# ============ 邮件通知 ============
import os
EMAIL_CONFIG = {
    "smtp_server": "smtp.163.com",
    "smtp_port": 465,
    "sender": "quanyi_zk@163.com",
    "password": os.environ.get("IC_EMAIL_PASSWORD", ""),
    "recipient": "quanyi_zk@163.com",
}


class EmailNotifier:
    """QQQ Iron Condor 邮件通知器（自包含）"""

    def __init__(self):
        self.cfg = EMAIL_CONFIG
        self.enabled = bool(self.cfg.get("password"))

    def _send(self, subject: str, body: str) -> bool:
        if not self.enabled:
            logger.warning(f"邮件未配置，跳过: {subject}")
            return False
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.cfg["sender"]
            msg["To"] = self.cfg["recipient"]
            msg.attach(MIMEText(body, "html"))
            with smtplib.SMTP_SSL(self.cfg["smtp_server"], self.cfg["smtp_port"]) as s:
                s.login(self.cfg["sender"], self.cfg["password"])
                s.sendmail(self.cfg["sender"], self.cfg["recipient"], msg.as_string())
            logger.info("📧 邮件已发送")
            return True
        except Exception as e:
            logger.error(f"📧 邮件发送失败: {e}")
            return False

    def _ts(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def send_startup(self) -> bool:
        subject = "🦅 Iron Condor 非对称策略启动（实盘 2x杠杆）"
        body = f"""
<h3>🦅 Iron Condor 非对称铁鹰策略已启动</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse">
<tr><td><b>标的</b></td><td>QQQ ($18k×4组) + IWM ($6k×2组) + GLD ($6k×2组)</td></tr>
<tr><td><b>OTM（非对称）</b></td><td>Put 3.0% / Call 6.0%，Wing=9%, DTE=45</td></tr>
<tr><td><b>实际本金</b></td><td>${REAL_CAPITAL:,} USD（2x杠杆，名义$30,000）</td></tr>
<tr><td><b>融资成本</b></td><td>{MARGIN_RATE*100:.1f}%/年 = ${REAL_CAPITAL*MARGIN_RATE:,.0f}/年</td></tr>
<tr><td><b>HV20阈值</b></td><td>QQQ/IWM: ≤25%，GLD: ≤18%（Scenario C，972组扫描最优）</td></tr>
<tr><td><b>VIX硬止损</b></td><td>HV20 ≥ 39% 强平所有持仓，< 25% 恢复开仓</td></tr>
<tr><td><b>降杠杆</b></td><td>HV20 > 22% 自动降至1x（max_groups减半）</td></tr>
<tr><td><b>价格止损</b></td><td>标的穿入翼宽50%（short strike ± 0.5×wing）</td></tr>
<tr><td><b>资金止损</b></td><td>标的亏损 > 5% 分配资金</td></tr>
</table>
<p><b>启动时间</b>: {self._ts()}</p>
"""
        return self._send(subject, body)

    def send_open(self, expiry: str, strikes: Dict, net_premium: float,
                  groups: int, hv20: float, asset: str = "QQQ",
                  current_price: float = 0.0) -> bool:
        # ── 风险指标计算 ──────────────────────────────────
        sell_put  = strikes.get("sell_put_k", 0)
        buy_put   = strikes.get("buy_put_k", 0)
        sell_call = strikes.get("sell_call_k", 0)
        buy_call  = strikes.get("buy_call_k", 0)
        wing      = sell_put - buy_put          # 翼宽（两边对称，取Put边）
        premium_per_share = net_premium / (100 * groups) if groups else 0

        max_profit = net_premium                # 最大盈利 = 收到的权利金
        max_loss   = wing * 100 * groups - net_premium   # 最大亏损（买腿封顶）
        be_lower   = sell_put  - premium_per_share       # 下轨盈亏平衡点
        be_upper   = sell_call + premium_per_share       # 上轨盈亏平衡点
        rr_ratio   = max_profit / max_loss if max_loss > 0 else 0

        # 盈利区间宽度（相对当前价格）
        profit_zone_pct = (be_upper - be_lower) / current_price * 100 if current_price > 0 else 0

        subject = (f"✅ {asset} Iron Condor 开仓 | 到期 {expiry} | "
                   f"收 ${net_premium:.0f} / 最大亏 ${max_loss:.0f}")
        body = f"""
<h3>✅ {asset} Iron Condor 开仓成功</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;min-width:360px">
<tr style="background:#f2f2f2"><td colspan="2"><b>📋 基本信息</b></td></tr>
<tr><td>标的</td><td><b>{asset}</b>{"  当前价 ${:.2f}".format(current_price) if current_price else ""}</td></tr>
<tr><td>到期日</td><td>{expiry}</td></tr>
<tr><td>开仓时 HV20</td><td>{hv20:.1%}</td></tr>

<tr style="background:#f2f2f2"><td colspan="2"><b>📐 行权价结构</b></td></tr>
<tr><td>Put 边</td><td>Buy ${buy_put:.0f} ← Sell ${sell_put:.0f}</td></tr>
<tr><td>盈利区间</td><td><b>${sell_put:.0f} ~ ${sell_call:.0f}</b>{"  ({:.1f}% 宽)".format(profit_zone_pct) if profit_zone_pct else ""}</td></tr>
<tr><td>Call 边</td><td>Sell ${sell_call:.0f} → Buy ${buy_call:.0f}</td></tr>

<tr style="background:#f2f2f2"><td colspan="2"><b>💰 盈亏指标</b></td></tr>
<tr><td>净权利金（最大盈利）</td><td style="color:#2e7d32"><b>+${max_profit:.0f}</b></td></tr>
<tr><td>最大亏损（买腿封顶）</td><td style="color:#c62828"><b>-${max_loss:.0f}</b></td></tr>
<tr><td>盈亏比（收益/风险）</td><td><b>1 : {1/rr_ratio:.1f}</b>{"  ✅" if rr_ratio >= 0.15 else "  ⚠️"}</td></tr>
<tr><td>盈亏平衡区间</td><td>${be_lower:.0f} ~ ${be_upper:.0f}</td></tr>
</table>
<p style="color:#888;font-size:12px">
  翼宽 ${wing:.0f}（{wing/current_price*100:.1f}% of 正股价）·
  止盈目标 ${max_profit*0.5:.0f}（50%）·
  止损触发 ${max_profit*2:.0f}（2倍权利金）
</p>
<p><b>时间</b>: {self._ts()}</p>
"""
        return self._send(subject, body)

    def send_alert(self, level: str, message: str, details: str = "") -> bool:
        emoji = {"WARNING": "⚠️", "CRITICAL": "🚨"}.get(level, "ℹ️")
        subject = f"{emoji} QQQ IC 警报 | {message[:50]}"
        body = f"""
<h3>{emoji} QQQ Iron Condor 警报</h3>
<p><b>级别</b>: {level}</p>
<p><b>消息</b>: {message}</p>
{"<p><b>详情</b>: " + details + "</p>" if details else ""}
<p><b>时间</b>: {self._ts()}</p>
"""
        return self._send(subject, body)

    def send_daily_summary(self, asset_results: list) -> bool:
        """每日运行摘要，无论是否开仓都发送"""
        today = datetime.now().strftime("%Y-%m-%d")
        rows = ""
        for r in asset_results:
            name    = r.get("name", "")
            action  = r.get("action", "-")
            reason  = r.get("reason", "")
            hv20    = r.get("hv20", "")
            premium = r.get("net_premium", 0)
            hv20_str = f"{hv20:.1%}" if isinstance(hv20, float) and hv20 > 0 else "-"
            premium_str = f"${premium:.0f}" if premium else "-"
            color   = "#4CAF50" if r.get("opened") else ("#FF9800" if r.get("closed") else "#555555")
            rows += (
                f"<tr>"
                f"<td><b>{name}</b></td>"
                f"<td style='color:{color}'>{action}</td>"
                f"<td>{reason}</td>"
                f"<td>{hv20_str}</td>"
                f"<td>{premium_str}</td>"
                f"</tr>"
            )
        subject = f"📊 铁鹰日报 {today} | {'有开仓' if any(r.get('opened') for r in asset_results) else '无开仓'}"
        body = f"""
<h3>📊 铁鹰策略每日运行报告</h3>
<p><b>日期</b>: {today} &nbsp;|&nbsp; <b>执行时间</b>: {self._ts()}</p>
<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:monospace;width:100%">
<tr style="background:#f2f2f2">
  <th>标的</th><th>操作</th><th>原因/备注</th><th>HV20</th><th>权利金</th>
</tr>
{rows}
</table>
<p style="color:#888;font-size:12px">自动发送 · 铁鹰量化系统</p>
"""
        return self._send(subject, body)


# ============ 数据源 ============
class FutuDataUS:
    """富途美股数据源"""
    
    def __init__(self, host="127.0.0.1", port=11111):
        from futu import OpenQuoteContext
        self.quote_ctx = OpenQuoteContext(host=host, port=port)
        self.subscribed = set()
    
    def connect(self) -> bool:
        logger.info("🔌 连接富途 OpenD (127.0.0.1:11111)...")
        self.quote_ctx.start()
        time.sleep(1)
        logger.info("✅ 已连接")
        return True
    
    def get_stock_quote(self, ticker: str) -> Dict:
        """获取正股价格"""
        from futu import RET_OK
        # 先订阅
        self.quote_ctx.subscribe([ticker], ["QUOTE"])
        time.sleep(0.5)
        
        ret, data = self.quote_ctx.get_stock_quote([ticker])
        if ret == RET_OK and not data.empty:
            return {
                "last_price": float(data.iloc[0]["last_price"]),
                "open_price": float(data.iloc[0]["open_price"]),
            }
        return {}
    
    def get_option_chain(self, ticker: str) -> Optional:
        """获取期权链"""
        from futu import RET_OK, OptionType, OptionCondType
        ret, data = self.quote_ctx.get_option_chain(
            ticker, 
            option_type=OptionType.ALL,
            option_cond_type=OptionCondType.OTM,
        )
        if ret == RET_OK and not data.empty:
            return data
        return None
    
    def get_option_expiration_dates(self, ticker: str) -> List:
        """获取美股期权到期日列表"""
        from futu import RET_OK
        from datetime import timedelta
        import pytz
        # 先订阅
        self.quote_ctx.subscribe([ticker], ["QUOTE"])
        time.sleep(0.5)

        # 用美东时间作为基准，避免北京时间与 API 服务器时间不一致导致日期偏移
        et_now = datetime.now(pytz.timezone("America/New_York"))
        today_et = et_now.date()
        ret, data = self.quote_ctx.get_option_expiration_date(ticker)
        if ret == RET_OK and not data.empty:
            expiries = []
            for _, row in data.iterrows():
                # 美股返回的是距离今天（美东）的天数
                distance = int(row.get("option_expiry_date_distance", 999))
                exp = today_et + timedelta(days=distance)
                expiries.append(exp)
            return sorted(set(expiries))
        return []
    
    def subscribe(self, codes: List[str], subtypes: List[str]) -> bool:
        """订阅行情"""
        for code in codes:
            if code not in self.subscribed:
                self.quote_ctx.subscribe([code], subtypes)
                self.subscribed.add(code)
        time.sleep(0.5)
        return True
    
    def get_order_book(self, code: str) -> Dict:
        """获取摆盘（bid/ask）"""
        from futu import RET_OK
        ret, data = self.quote_ctx.get_order_book(code)
        bid = ask = 0.0
        if ret == RET_OK and data:
            bid_list = data.get("Bid", [])
            ask_list = data.get("Ask", [])
            if bid_list:
                bid = float(bid_list[0][0])
            if ask_list:
                ask = float(ask_list[0][0])
        return {"bid": bid, "ask": ask}
    
    def close(self):
        self.quote_ctx.close()


# ============ 实盘交易核心 ============
class IronCondorTraderUS:
    """美股 Iron Condor 实盘交易"""

    def __init__(self, data: FutuDataUS):
        self.data = data
        self.config = IC_CONFIG
        self.stock = STOCK_CONFIG
        self.dry_run = True  # 默认模拟模式
        self.check_interval = 300  # 5分钟检查一次（守护模式用）
        self.notifier = EmailNotifier()
    
    def _get_account_equity(self) -> float:
        """
        通过富途 API 读取账户总资产（现金+持仓市值），用于动态组数计算。
        返回 0.0 表示查询失败（调用方会降级为基线组数）。
        """
        from config import FUTU_CONFIG
        from futu import OpenSecTradeContext, TrdEnv, RET_OK

        try:
            trd_env = TrdEnv.SIMULATE if self.dry_run else TrdEnv.REAL
            acc_id_key = "sim_acc_id" if self.dry_run else "real_acc_id"
            acc_id = int(FUTU_CONFIG.get(acc_id_key, "281756481449956811"))

            trade_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                filter_trdmarket="US",
                security_firm="FUTUSECURITIES",
            )
            ret, data = trade_ctx.accinfo_query(trd_env=trd_env, acc_id=acc_id)
            trade_ctx.close()

            if ret == RET_OK and data is not None and not data.empty:
                total_assets = float(data.iloc[0].get("total_assets", 0))
                logger.info(f"💰 账户总资产: ${total_assets:,.2f}")
                return total_assets
            else:
                logger.warning(f"⚠️ 账户查询失败: ret={ret}")
                return 0.0
        except Exception as e:
            logger.error(f"⚠️ 获取账户净值异常: {e}")
            return 0.0

    def check_existing_positions(self) -> tuple:
        """
        检查当前是否已有铁鹰持仓（QQQ期权）
        返回 (group_count, total_legs) 元组
        """
        from config import FUTU_CONFIG
        from futu import OpenSecTradeContext, TrdEnv, ModifyOrderOp

        try:
            # Futu API: dry_run 用模拟账户，实盘用真实账户
            trd_env = TrdEnv.SIMULATE if self.dry_run else TrdEnv.REAL
            acc_id_key = "sim_acc_id" if self.dry_run else "real_acc_id"
            acc_id = int(FUTU_CONFIG.get(acc_id_key, "281756481449956811"))

            trade_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                filter_trdmarket="US",
                security_firm="FUTUSECURITIES",
            )

            ret, pos_data = trade_ctx.position_list_query(
                code="",
                pl_ratio_min=None,
                pl_ratio_max=None,
                trd_env=trd_env,
                acc_id=acc_id,
                refresh_cache=True,  # SIMULATE 和 REAL 都刷新，确保数据最新
            )
            trade_ctx.close()

            if ret != 0 or pos_data is None or pos_data.empty:
                logger.info("📋 当前无持仓")
                return (0, 0)

            # 筛选当前标的期权持仓（动态匹配 ticker name），排除已平仓(qty=0)
            ticker_name = self.stock["ticker"].split(".")[1]  # "QQQ", "IWM", or "GLD"
            all_opts = pos_data[pos_data["code"].str.contains(ticker_name, na=False)]
            qqq_opts = all_opts[all_opts["qty"] != 0]  # 过滤已平仓持仓
            leg_count = len(qqq_opts)
            group_count = leg_count // 4  # 每4腿算1组 IC
            remainder = leg_count % 4
            
            logger.info(f"📋 当前{self.stock['name']}期权持仓: {leg_count} 腿 = {group_count} 组 Iron Condor")
            
            # 🔧 不平衡头寸检测
            if remainder != 0:
                logger.critical("🚨🚨🚨 检测到不平衡头寸！")
                logger.critical(f"   总腿数 {leg_count} 不是4的倍数（余{remainder}）")
                logger.critical(f"   这意味着存在不完整的 Iron Condor，可能暴露单向风险！")
                if not qqq_opts.empty:
                    for _, row in qqq_opts.iterrows():
                        logger.critical(f"     🔴 {row['code']}: {row['qty']} 张 | 可卖{row.get('can_sell_qty', 'N/A')} | 成本{row.get('cost_price', 'N/A')}")
                logger.critical("⚠️  策略将暂停新开仓，请先手动处理不平衡头寸！")
            
            if not qqq_opts.empty:
                for _, row in qqq_opts.iterrows():
                    logger.info(f"   {row['code']}: {row['qty']} 张 @ {row.get('cost_price', 'N/A')}")

            return (group_count, leg_count)
        except Exception as e:
            logger.error(f"查询持仓失败: {e}")
            return (-1, -1)  # 查询失败时返回特殊值，让调用者暂停开仓

    def _evaluate_risk(self) -> Dict:
        """
        实时风险评估（集成 ic_risk_monitor）
        
        计算当前持仓的风险指标：
        - 最大盈利/亏损
        - 盈亏平衡点
        - 亏损概率
        - 盈亏比
        
        根据阈值自动触发止损/止盈
        """
        from ic_risk_monitor import calculate_ic_metrics
        
        positions = self._get_positions_with_expiry()
        if not positions:
            return {"triggered": False, "action": "HOLD", "reason": ""}
        
        # 获取当前正股价格
        current_price = self.get_current_price()
        if not current_price:
            logger.warning("⚠️ 无法获取正股价格，跳过风险评估")
            return {"triggered": False, "action": "HOLD", "reason": "无法获取股价"}
        
        # 按到期日分组计算每组风险
        from collections import defaultdict
        groups = defaultdict(list)
        for pos in positions:
            if pos.get("expiry"):
                groups[pos["expiry"]].append(pos)
        
        total_risk_info = []
        
        import re as _re
        for expiry, legs in groups.items():
            if len(legs) < 4:
                continue

            # 解析行权价和净权利金
            strikes = {}
            net_premium_per_share = 0

            for leg in legs:
                code = leg.get("code", "")
                price = leg.get("cost_price", 0)
                qty = leg.get("qty", 0)
                side = "sell" if qty < 0 else "buy"  # Futu: qty<0=空头(卖出), qty>0=多头(买入)

                # 从期权代码解析行权价（格式：US.QQQ260508C615000 → strike=615.0）
                # 代码末尾数字为行权价×1000（整数），如 C615000 = $615
                m = _re.search(r"([CP])(\d+)$", code)
                if m:
                    option_type = m.group(1)  # "C" or "P"
                    strike = int(m.group(2)) / 1000.0
                else:
                    option_type = "C" if "C" in code.upper() else "P"
                    strike = 0

                # 判断期权类型
                if option_type == "P":
                    if side == "sell":
                        strikes["sell_put"] = strike
                        net_premium_per_share += price
                    else:
                        strikes["buy_put"] = strike
                        net_premium_per_share -= price
                else:
                    if side == "sell":
                        strikes["sell_call"] = strike
                        net_premium_per_share += price
                    else:
                        strikes["buy_call"] = strike
                        net_premium_per_share -= price
            
            if len(strikes) >= 4:
                # ── 价格穿越止损（优先级高，匹配回测 stop_loss_buffer=1.5）──────
                # 回测逻辑：stop_put  = sell_put  - 0.5 × put_wing
                #           stop_call = sell_call + 0.5 × call_wing
                # 含义：标的价格穿入翼宽的50%处即平仓（空头行权价已深度受损）
                put_w  = strikes.get("sell_put", 0)  - strikes.get("buy_put", 0)
                call_w = strikes.get("buy_call", 0)  - strikes.get("sell_call", 0)
                stop_put  = strikes.get("sell_put", 0)  - 0.5 * put_w
                stop_call = strikes.get("sell_call", 0) + 0.5 * call_w
                if put_w > 0 and call_w > 0:   # 只有四腿齐全时才检查
                    if current_price <= stop_put or current_price >= stop_call:
                        direction = "下行" if current_price <= stop_put else "上行"
                        return {
                            "triggered": True,
                            "action": "CLOSE_ALL",
                            "reason": (
                                f"价格穿越止损（{direction}）: 当前${current_price:.2f}，"
                                f"止损线 ${stop_put:.2f}~${stop_call:.2f}（翼宽50%）"
                            ),
                            "details": (
                                f"到期 {expiry}：short_put=${strikes.get('sell_put',0):.2f} "
                                f"short_call=${strikes.get('sell_call',0):.2f}，"
                                f"翼宽 put={put_w:.2f}/call={call_w:.2f}"
                            )
                        }

                # 计算风险指标（用于报告和资金止损）
                metrics = calculate_ic_metrics(
                    current_price=current_price,
                    sell_put_strike=strikes.get("sell_put", 0),
                    buy_put_strike=strikes.get("buy_put", 0),
                    sell_call_strike=strikes.get("sell_call", 0),
                    buy_call_strike=strikes.get("buy_call", 0),
                    net_premium_per_share=net_premium_per_share,
                    expiry=expiry,
                    currency="USD"
                )

                total_risk_info.append({
                    "expiry": expiry,
                    "metrics": metrics,
                    "positions": legs,
                    "strikes": strikes,
                })

                # 打印风险报告
                m = metrics
                logger.info(f"📊 到期日 {expiry} 风险分析:")
                logger.info(f"   💰 权利金: ${m['max_profit']:.0f}")
                logger.info(f"   📈 最大盈利: +${m['max_profit']:.0f}")
                logger.info(f"   📉 最大亏损: -${m['max_loss']:.0f}")
                logger.info(f"   ⚖️ 盈亏比: 1:{m['risk_reward_ratio']:.2f}")
                logger.info(f"   🎯 盈亏平衡: ${m['breakeven_lower']:.0f} ~ ${m['breakeven_upper']:.0f}")
                logger.info(f"   🛑 价格止损: ${stop_put:.2f} / ${stop_call:.2f}（翼宽50%）")

        if not total_risk_info:
            return {"triggered": False, "action": "HOLD", "reason": ""}

        # ── 资金回撤止损（匹配回测 stop_loss_pct=0.05）──────────────
        # 回测：当标的分配资金回撤超5%时平仓（QQQ $18k→$900亏损触发）
        # 注：回测的5%是从权益峰值起算的回撤；实盘用未实现亏损/标的资金近似
        stop_loss_pct  = self.config.get("stop_loss_pct", 0.05)   # 5%，与回测一致
        asset_capital  = self.config.get("capital", INITIAL_CAPITAL / len(ASSETS))
        total_unrealized_pl = sum(p.get("unrealized_pl", 0) for p in positions)

        if total_unrealized_pl < 0:
            loss_pct = abs(total_unrealized_pl) / asset_capital
            if loss_pct > stop_loss_pct:
                return {
                    "triggered": True,
                    "action": "CLOSE_ALL",
                    "reason": f"资金止损: 亏损 {loss_pct*100:.1f}% > {stop_loss_pct*100:.0f}%（${asset_capital:.0f}/标的）",
                    "details": f"未实现亏损 ${total_unrealized_pl:.0f}"
                }

        # ── 止盈（回测未建模；实盘保留作运营增强，预期提升资金效率）──
        # 50% 止盈：期权时间价值衰减后提前锁定利润，释放保证金开新仓
        # TODO: 待评估是否加入回测后纳入标准参数体系
        max_profit = max((r["metrics"]["max_profit"] for r in total_risk_info), default=0)
        profit_target_pct = self.config.get("profit_target_pct", 0.50)
        if total_unrealized_pl > 0 and max_profit > 0:
            profit_pct = total_unrealized_pl / max_profit
            if profit_pct >= profit_target_pct:
                return {
                    "triggered": True,
                    "action": "PARTIAL_CLOSE",
                    "reason": f"止盈: 盈利 {profit_pct*100:.0f}% ≥ 目标 {profit_target_pct*100:.0f}%",
                    "details": f"盈利 ${total_unrealized_pl:.0f} / 最大权利金 ${max_profit:.0f}"
                }

        return {"triggered": False, "action": "HOLD", "reason": ""}

    def get_current_price(self) -> float:
        """获取正股当前价格"""
        quote = self.data.get_stock_quote(self.stock["ticker"])
        if quote:
            return quote.get("last_price", 0)
        return 0
    
    def calculate_strikes(self, S: float, dte: int, otm: Optional[float] = None,
                          put_otm_override: float = None,
                          call_otm_override: float = None) -> Dict:
        """计算铁鹰行权价（支持非对称 put_otm / call_otm）
        otm: 可选，同时覆盖两侧OTM（兼容旧代码）
        put_otm_override/call_otm_override: 分别覆盖两侧（保留非对称，慢熊防御用）"""
        wing = self.config["wing_width"]

        if put_otm_override is not None and call_otm_override is not None:
            # 慢熊防御：按比例放大非对称 OTM，保留 put/call 比例
            put_otm = put_otm_override
            call_otm = call_otm_override
        elif otm is not None:
            # 兼容旧代码：对称覆盖
            put_otm = call_otm = otm
        else:
            # 非对称铁鹰：put 侧更近，call 侧更远
            put_otm  = self.config.get("put_otm",  self.config["otm_distance"])
            call_otm = self.config.get("call_otm", self.config["otm_distance"])

        # PUT边：sell更接近价内（行权价更高）
        buy_put_k  = round(S * (1 - put_otm  - wing), 0)  # 更虚值
        sell_put_k = round(S * (1 - put_otm),         0)  # 更接近价内

        # CALL边：sell更接近价内（行权价更低）
        sell_call_k = round(S * (1 + call_otm),         0)  # 更接近价内
        buy_call_k  = round(S * (1 + call_otm + wing),  0)  # 更虚值

        return {
            "buy_put_k": buy_put_k,
            "sell_put_k": sell_put_k,
            "sell_call_k": sell_call_k,
            "buy_call_k": buy_call_k,
            "current_price": S,
        }
    
    def find_option_codes(self, strikes: Dict, expiry: date) -> Dict:
        """通过期权链API找到对应行权价的期权代码"""
        from futu import RET_OK, OptionType
        
        codes = {}
        expiry_str = expiry.strftime("%Y-%m-%d")
        
        # 获取CALL期权链
        ret, data = self.data.quote_ctx.get_option_chain(
            self.stock["ticker"],
            option_type=OptionType.CALL,
            start=expiry_str,
            end=expiry_str,
        )
        
        if ret == RET_OK and not data.empty:
            for name, target_k in [
                ("sell_call", strikes["sell_call_k"]),
                ("buy_call", strikes["buy_call_k"]),
            ]:
                data["strike_dist"] = abs(data["strike_price"].astype(float) - target_k)
                closest = data.loc[data["strike_dist"].idxmin()]
                codes[name] = str(closest["code"])
                logger.info(f"  {name}: {closest['code']} @ ${closest['strike_price']}")
        else:
            logger.warning(f"  ⚠️ CALL期权链为空 (ret={ret}, expiry={expiry_str})")

        # 获取PUT期权链
        ret, data = self.data.quote_ctx.get_option_chain(
            self.stock["ticker"],
            option_type=OptionType.PUT,
            start=expiry_str,
            end=expiry_str,
        )

        if ret == RET_OK and not data.empty:
            for name, target_k in [
                ("sell_put", strikes["sell_put_k"]),
                ("buy_put", strikes["buy_put_k"]),
            ]:
                data["strike_dist"] = abs(data["strike_price"].astype(float) - target_k)
                closest = data.loc[data["strike_dist"].idxmin()]
                codes[name] = str(closest["code"])
                logger.info(f"  {name}: {closest['code']} @ ${closest['strike_price']}")
        else:
            logger.warning(f"  ⚠️ PUT期权链为空 (ret={ret}, expiry={expiry_str})")
        
        return codes
    
    def get_bid_ask(self, options: List[str]) -> Dict:
        """获取期权bid/ask价格"""
        prices = {}
        self.data.subscribe(options, ["ORDER_BOOK"])
        
        for code in options:
            ob = self.data.get_order_book(code)
            prices[code] = {
                "bid": ob["bid"],
                "ask": ob["ask"],
                "mid": round((ob["bid"] + ob["ask"]) / 2, 2) if ob["bid"] > 0 and ob["ask"] > 0 else 0,
            }
            logger.info(f"  {code}: bid={ob['bid']:.2f} ask={ob['ask']:.2f}")
        
        return prices
    
    def open_position(self, groups_to_open=1) -> Dict:
        """开仓 Iron Condor
        groups_to_open: 要开的组数（默认1组）"""
        ticker = self.stock["ticker"]
        
        logger.info(f"📊 计划开仓组数: {groups_to_open}")
        
        # 2. 获取正股价格
        price = self.get_current_price()
        if not price:
            logger.error("❌ 无法获取正股价格")
            return {"success": False, "reason": "无法获取正股价格"}
        
        logger.info(f"📈 {ticker} 当前价: ${price:.2f}")
        
        # 2.5 市场条件检查（HV20过滤 + 慢熊检测）
        market_cond = self._check_market_conditions()
        if not market_cond["can_open"]:
            logger.warning(f"⚠️ 市场条件不允许开仓: {market_cond['reason']}")
            return {"success": False, "reason": market_cond["reason"]}
        
        # 根据市场条件调整OTM距离（保留非对称比例）
        slow_bear_put_otm = None
        slow_bear_call_otm = None
        if market_cond["adjust_otm"] > 0:
            base_otm = self.config.get("otm_distance", 0.05)
            target_otm = market_cond["adjust_otm"]
            scale = target_otm / base_otm if base_otm > 0 else 5.0
            slow_bear_put_otm = self.config.get("put_otm", base_otm) * scale
            slow_bear_call_otm = self.config.get("call_otm", base_otm) * scale
            logger.info(
                f"🛡️ 慢熊防御：OTM按{scale:.1f}x放大，"
                f"Put {self.config.get('put_otm',0):.1%}→{slow_bear_put_otm:.1%}，"
                f"Call {self.config.get('call_otm',0):.1%}→{slow_bear_call_otm:.1%}"
            )
        
        # 3. 获取近期到期日
        expiries = self.data.get_option_expiration_dates(ticker)
        if not expiries:
            logger.error("❌ 无法获取期权到期日")
            return {"success": False, "reason": "无法获取到期日"}
        
            # 找到符合DTE的到期日（自适应：选择最接近目标DTE的）
        target_dte = self.config["entry_days_before_expiry"]
        import pytz as _pytz
        today = datetime.now(_pytz.timezone("America/New_York")).date()  # 美东日期

        # 尝试多个DTE层级（从小到大，找到第一个有流动性的）
        dte_options = [target_dte, target_dte + 7, target_dte + 14, target_dte + 21]
        
        for attempt_dte in dte_options:
            # 自适应选择最接近目标DTE的到期日
            valid_exps = [e for e in expiries if e >= today]
            if valid_exps:
                target_expiry = min(valid_exps, key=lambda e: abs((e - today).days - attempt_dte))
                actual_dte = (target_expiry - today).days
            else:
                continue
            
            logger.info(f"📅 尝试到期日: {target_expiry} (DTE={actual_dte})")
            
            # 4. 计算行权价
            strikes = self.calculate_strikes(
                price, actual_dte,
                put_otm_override=slow_bear_put_otm,
                call_otm_override=slow_bear_call_otm,
            )
            logger.info(f"  行权价: PUT {strikes['buy_put_k']}/{strikes['sell_put_k']} | CALL {strikes['sell_call_k']}/{strikes['buy_call_k']}")
            
            # 5. 获取期权代码
            codes = self.find_option_codes(strikes, target_expiry)
            logger.info(f"  期权代码: {codes}")
            
            # 6. 获取bid/ask
            # 期权代码必须找齐4条腿，否则直接认定无流动性
            if len(codes) < 4:
                logger.warning(f"⚠️ DTE={actual_dte} 期权代码不完整({len(codes)}/4)，尝试更长周期...")
                continue

            prices = self.get_bid_ask(list(codes.values()))

            # 检查是否有有效价格（必须有bid价格，否则无流动性）
            valid = bool(prices) and all(p.get("bid", 0) > 0 or p.get("ask", 0) > 0 for p in prices.values())
            if not valid:
                logger.warning(f"⚠️ DTE={actual_dte} 无流动性，尝试更长周期...")
                continue
            
            # 找到一个有流动性的就 break
            logger.info(f"✅ 找到流动性好的期权 DTE={actual_dte}")
            break
        else:
            # 所有DTE都试过了还是没流动性
            logger.warning("⚠️ 所有DTE都没有流动性，跳过开仓")
            return {"success": False, "reason": "期权无流动性"}
        
        # 7. 构建订单
        legs = []
        for name, code in codes.items():
            side = "buy" if "buy" in name else "sell"
            leg_type = name.split("_")[1]
            p = prices.get(code, {})
            # 价格策略：sell用bid（确保成交），buy用ask
            if side == "sell":
                # 卖出用买一价，四舍五入到富途要求精度
                order_price = _round_option_price(p.get("bid", p.get("mid", 0.01)))
            else:
                # 买入用卖一价，四舍五入到富途要求精度
                order_price = _round_option_price(p.get("ask", p.get("mid", 0.01)))

            # bid=0 的腿无法交易，跳过
            if side == "sell" and p.get("bid", 0) <= 0:
                logger.warning(f"⚠️ {code} 无买一价（bid=0），无流动性")
                return {"success": False, "reason": f"{code} 无流动性"}

            legs.append({
                "code": code,
                "side": side,           # buy/sell
                "type": leg_type,       # put/call
                "order_price": order_price,
                "bid_price": p.get("bid", 0),
                "ask_price": p.get("ask", 0),
            })

        # 8. 计算权利金（使用 side 字段，不依赖列表索引顺序）
        sell_credits = sum(leg["order_price"] for leg in legs if leg["side"] == "sell")
        buy_debits   = sum(leg["order_price"] for leg in legs if leg["side"] == "buy")
        net_premium = (sell_credits - buy_debits) * 100  # 1手=100股
        total_premium = net_premium * groups_to_open  # 总权利金

        logger.info(f"💰 单组权利金: ${net_premium:.2f}")
        logger.info(f"💰 预估总权利金 ({groups_to_open}组): ${total_premium:.2f}")

        # 9. 最低权利金检查（检查总权利金）
        min_premium = self.config.get("min_premium", 100)
        if total_premium < min_premium:
            logger.warning(f"⚠️ 总权利金 ${total_premium:.2f} < 最低 ${min_premium}，跳过开仓")
            return {"success": False, "reason": f"总权利金 ${total_premium:.2f} 低于最低 ${min_premium}"}

        # 10. 执行下单或模拟
        if self.dry_run:
            logger.info("\n⚠️ 模拟模式，不执行真实下单")
            return {
                "success": True,
                "dry_run": True,
                "strikes": strikes,
                "expiry": str(target_expiry),
                "codes": codes,
                "prices": prices,
                "net_premium": total_premium,
                "legs": legs,
            }
        else:
            result = self.execute_orders(legs, groups_to_open)
            if result.get("success"):
                self.notifier.send_open(
                    expiry=str(target_expiry),
                    strikes=strikes,
                    net_premium=result.get("net_premium", 0),
                    groups=groups_to_open,
                    hv20=market_cond.get("hv20", 0.0),
                    asset=self.stock.get("name", ""),
                    current_price=price,
                )
                # ── 实盘绩效持久化：记录开仓元数据 ──────────────────
                asset_name = self.stock.get("name", "")
                _save_open_trade(asset_name, {
                    "entry_date": date.today().isoformat(),
                    "expiry": str(target_expiry),
                    "sell_put":  strikes.get("sell_put_k", 0),
                    "sell_call": strikes.get("sell_call_k", 0),
                    "buy_put":   strikes.get("buy_put_k", 0),
                    "buy_call":  strikes.get("buy_call_k", 0),
                    "groups":    groups_to_open,
                    "net_credit": result.get("net_premium", 0),
                })
                _append_trade_history({
                    "date":     date.today().isoformat(),
                    "time":     datetime.now().strftime("%H:%M:%S"),
                    "asset":    asset_name,
                    "action":   "OPEN",
                    "expiry":   str(target_expiry),
                    "sell_put":  strikes.get("sell_put_k", 0),
                    "sell_call": strikes.get("sell_call_k", 0),
                    "buy_put":   strikes.get("buy_put_k", 0),
                    "buy_call":  strikes.get("buy_call_k", 0),
                    "groups":    groups_to_open,
                    "net_premium": result.get("net_premium", 0),
                    "days_held": 0,
                    "realized_pnl": "",
                    "close_reason": "",
                })
                logger.info(f"📝 [{asset_name}] 开仓记录已写入 trade_history.csv")
            return result

    def execute_orders(self, legs: List[Dict], groups_to_open=1) -> Dict:
        """
        执行4条腿的下单（美股版）
        groups_to_open: 要开的组数（默认1组）

        价格策略（3轮）：
          第1轮：中间价 (bid+ask)/2      → 挂单10分钟
          第2轮：偏激进中间价            → 挂单10分钟  (sell向bid靠，buy向ask靠，各移动价差的25%)
          第3轮：直接 sell→bid, buy→ask  → 挂单10分钟（市场价，确保成交）

        每轮10分钟未成交则撤单进入下一轮。
        """
        from config import FUTU_CONFIG
        from futu import OpenSecTradeContext, TrdSide, OrderType, RET_OK, TrdEnv, ModifyOrderOp

        logger.info("\n🚀 开始执行下单（中间价策略，每轮10分钟）...")

        acc_id = int(FUTU_CONFIG.get("real_acc_id", "281756481449956811"))
        trd_env = TrdEnv.REAL

        logger.info(f"📋 使用账户: {acc_id} (REAL)")
        
        # ========== 改进：串行提交 + 重试机制 ==========
        
        # 准备所有腿的订单信息
        all_legs_order_info = []
        for leg in legs:
            code = leg["code"]
            side = leg["side"]
            qty = groups_to_open  # 开仓组数
            order_side = TrdSide.SELL if side == "sell" else TrdSide.BUY
            
            # 所有腿用中间价下单（按最佳实践），价格四舍五入到富途要求精度
            bid = leg.get("bid_price", leg.get("bid", 0.0))
            ask = leg.get("ask_price", leg.get("ask", 0.0))
            raw_mid = (bid + ask) / 2 if bid > 0 and ask > 0 else leg.get("order_price", 0.01)
            spread = round(ask - bid, 2) if ask > bid > 0 else 0.0
            first_price = _round_option_price(raw_mid)
            
            all_legs_order_info.append({
                "leg": leg,
                "code": code,
                "side": side,
                "qty": qty,
                "order_side": order_side,
                "first_price": first_price,
                "trd_env": trd_env,
                "acc_id": acc_id,
            })
        
        # 串行提交（带重试机制）
        def submit_single_leg(order_info, trade_ctx, max_retries=5, initial_delay=0.5):
            """提交单个订单，带重试机制处理频率限制错误"""
            leg = order_info["leg"]
            code = order_info["code"]
            order_side = order_info["order_side"]
            qty = order_info["qty"]
            price = order_info["first_price"]
            trd_env = order_info["trd_env"]
            acc_id = order_info["acc_id"]

            import time
            last_error = None
            delay = initial_delay

            for attempt in range(max_retries):
                try:
                    ret, data = trade_ctx.place_order(
                        code=code,
                        price=price,
                        qty=qty,
                        trd_side=order_side,
                        order_type=OrderType.NORMAL,
                        adjust_limit=0,
                        trd_env=trd_env,
                        acc_id=acc_id,
                    )

                    if ret != RET_OK:
                        error_str = str(data)
                        last_error = error_str

                        # 检查是否是"操作过快"错误需要重试
                        if "操作过快" in error_str and attempt < max_retries - 1:
                            logger.warning(f"   ⚠️ {code} 触发频率限制，{delay:.1f}秒后重试 ({attempt+1}/{max_retries})...")
                            time.sleep(delay)
                            delay *= 2  # 指数退避
                            continue
                        else:
                            return {
                                "code": code,
                                "order_id": None,
                                "success": False,
                                "error": error_str,
                            }

                    order_id = data.iloc[0]["order_id"]
                    return {
                        "code": code,
                        "order_id": order_id,
                        "price": price,
                        "success": True,
                    }
                except Exception as e:
                    last_error = str(e)
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2
                        continue
                    return {
                        "code": code,
                        "order_id": None,
                        "success": False,
                        "error": last_error,
                    }

            return {
                "code": code,
                "order_id": None,
                "success": False,
                "error": last_error or "max retries exceeded",
            }

        # 串行提交（每条腿间隔0.3秒，避免频率限制）
        logger.info("📝 提交4条腿订单（每条腿间隔0.3秒避开频率限制）...")
        import time
        time.sleep(0.2)

        submitted_results = []
        for order_info in all_legs_order_info:
            # 每个订单使用独立的交易上下文
            from futu import OpenSecTradeContext
            thread_trade_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                security_firm="FUTUSECURITIES",
            )
            result = submit_single_leg(order_info, thread_trade_ctx)
            submitted_results.append(result)
            thread_trade_ctx.close()

            if result["success"]:
                logger.info(f"   ✅ {result['code']} 订单已提交: {result['order_id']} @ ${result.get('price', 0):.2f}")
            else:
                logger.error(f"   ❌ {result['code']} 提交失败: {result.get('error', 'unknown')}")

            # 每条腿之间间隔0.3秒
            time.sleep(0.3)
        
        # 检查是否有订单提交失败，如果有则全部撤销
        failed_count = sum(1 for r in submitted_results if not r["success"])
        if failed_count > 0:
            logger.warning(f"⚠️ {failed_count}条腿提交失败，撤销已提交的订单...")
            cancel_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                security_firm="FUTUSECURITIES",
            )
            try:
                for r in submitted_results:
                    if r["success"] and r.get("order_id"):
                        try:
                            cancel_ctx.modify_order(
                                modify_order_op=ModifyOrderOp.CANCEL,
                                order_id=r["order_id"],
                                qty=0, price=0,
                                trd_env=trd_env,
                                acc_id=acc_id,
                            )
                        except Exception:
                            pass
            finally:
                cancel_ctx.close()
            return {"success": False, "reason": "部分订单提交失败，已撤销"}
        
        # 步骤2：同时监控所有订单（最多等5分钟）
        logger.info("🔄 同时监控4条腿的成交状态（最多5分钟）...")
        
        # 创建一个新的交易上下文用于查询
        monitor_trade_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            security_firm="FUTUSECURITIES",
        )
        
        all_filled = False
        cancelled_detected = False

        for tick in range(10):  # 最多5分钟（10次×30秒）
            time.sleep(30)

            # 查询所有4条腿的状态（全部遍历完再判断，不提前 break）
            filled_count = 0
            partial_count = 0

            for r in submitted_results:
                order_id = r["order_id"]

                ret, od = monitor_trade_ctx.order_list_query(
                    order_id=order_id,
                    trd_env=trd_env,
                    acc_id=acc_id,
                )

                if ret == RET_OK and not od.empty:
                    status = str(od.iloc[0]["order_status"])
                    dealt_qty = int(od.iloc[0].get("dealt_qty", 0) or 0)
                    expected_qty = r.get("qty", 1)

                    # Futu API: FILLED_ALL=11, CANCELLED_ALL=15, FAILED=21, DELETED=23
                    if status in ["FILLED_ALL", "11"] and dealt_qty >= expected_qty:
                        # 完全成交
                        filled_count += 1
                    elif dealt_qty > 0 and dealt_qty < expected_qty:
                        # 🔴 部分成交！危险状态
                        partial_count += 1
                        logger.warning(f"   ⚠️ {r['code']} 部分成交: {dealt_qty}/{expected_qty}")
                    elif status in ["CANCELLED_ALL", "15", "FAILED", "21", "DELETED", "23"]:
                        # 终态：非成交（撤销/失败）
                        logger.warning(f"⚠️ 订单 {order_id} 终止: {status}")
                        cancelled_detected = True
                    # else: 仍在排队/等待，本轮继续

            # ── 内层循环结束，4条腿全部检查完毕，再做决策 ──
            all_filled = (filled_count == len(submitted_results))

            if all_filled:
                break  # ✅ 全成交，退出监控

            if partial_count > 0:
                logger.warning(f"🔴 发现{partial_count}条腿部分成交，提前终止等待")
                break

            if cancelled_detected:
                logger.warning("🔴 检测到订单撤销/失败，停止等待")
                break

            logger.info(f"   ⏳ {(tick+1)*30}s | 已成交: {filled_count}/{len(submitted_results)} | 部分: {partial_count}")
        
        monitor_trade_ctx.close()
        
        # 步骤3：要么全成，要么全撤
        if all_filled:
            logger.info("✅ 4条腿全部成交！铁鹰策略建仓成功")
            for r in submitted_results:
                logger.info(f"   📊 {r['code']} @ ${r.get('price', 0):.2f}")

            # 计算净权利金
            net_premium = 0
            for i, leg in enumerate(legs):
                side = leg["side"]
                price = submitted_results[i].get("price", 0)
                if side == "sell":
                    net_premium += price * 100 * groups_to_open
                else:
                    net_premium -= price * 100 * groups_to_open

            # ── 记录 IC 持仓代码（避免误碰 Wheel/正股持仓）──
            opened_codes = [r["code"] for r in submitted_results if r.get("success")]
            _add_ic_codes(opened_codes)
            logger.info(f"📝 IC 持仓代码已记录: {opened_codes}")

            return {
                "success": True,
                "legs": submitted_results,
                "net_premium": net_premium,
                "expiry": legs[0].get("expiry", "unknown"),
            }
        else:
            # 有未成交的，全部撤销
            logger.warning("⚠️ 部分订单未成交，全部撤销...")
            
            # 🔧 Bug修复：创建新的交易上下文执行撤单（原trade_ctx可能已超时断开）
            from futu import OpenSecTradeContext as OpenSecTradeContext_Cancel
            cancel_ctx = None
            cancelled_count = 0
            partial_fills = []  # 记录已成交的腿
            
            # 先检查哪些腿已经（部分）成交了
            for r in submitted_results:
                order_id = r.get("order_id")
                code = r.get("code", "")
                if not order_id:
                    continue
                    
                # 查询最终状态
                check_ctx = None
                try:
                    check_ctx = OpenSecTradeContext(
                        host=FUTU_CONFIG["host"],
                        port=FUTU_CONFIG["port"],
                        security_firm="FUTUSECURITIES",
                    )
                    ret, od = check_ctx.order_list_query(
                        order_id=order_id,
                        trd_env=trd_env,
                        acc_id=acc_id,
                    )
                    if ret == RET_OK and not od.empty:
                        status = str(od.iloc[0]["order_status"])
                        dealt_qty = int(od.iloc[0].get("dealt_qty", 0) or 0)
                        qty = r.get("qty", 1)
                        
                        if dealt_qty > 0:
                            if dealt_qty >= qty:
                                logger.warning(f"🔴 {code} 已完全成交({dealt_qty}/{qty})，无法撤销！残留头寸！")
                                partial_fills.append({
                                    "code": code,
                                    "dealt_qty": dealt_qty,
                                    "qty": qty,
                                    "order_id": order_id,
                                    "status": "FULL_FILLED",
                                    "side": r.get("side", "unknown"),
                                    "price": r.get("price", 0),
                                })
                            else:
                                logger.critical(f"🔴🔴🔴 {code} 部分成交({dealt_qty}/{qty})！不平衡头寸！")
                                partial_fills.append({
                                    "code": code,
                                    "dealt_qty": dealt_qty,
                                    "qty": qty,
                                    "order_id": order_id,
                                    "status": "PARTIAL_FILLED",
                                    "side": r.get("side", "unknown"),
                                    "price": r.get("price", 0),
                                })
                        else:
                            # 未成交，尝试撤销（带重试机制）
                            if cancel_ctx is None:
                                cancel_ctx = OpenSecTradeContext(
                                    host=FUTU_CONFIG["host"],
                                    port=FUTU_CONFIG["port"],
                                    security_firm="FUTUSECURITIES",
                                )
                            # 撤单重试机制（最多3次，每次等待1秒）
                            cancel_success = False
                            for retry in range(3):
                                try:
                                    ret_cancel = cancel_ctx.modify_order(
                                        modify_order_op=ModifyOrderOp.CANCEL,
                                        order_id=order_id,
                                        qty=0, price=0,
                                        trd_env=trd_env,
                                        acc_id=acc_id,
                                    )
                                    
                                    if ret_cancel == RET_OK:
                                        cancelled_count += 1
                                        logger.info(f"   ✅ {code} 订单已撤销")
                                        cancel_success = True
                                        break
                                    else:
                                        # 检查返回的错误信息
                                        err_msg = str(ret_cancel)
                                        # Futu API: CANCELLED_ALL 字符串或整数 15
                                        if "CANCELLED_ALL" in err_msg or "当前状态为CANCELLED_ALL" in err_msg or "15" in err_msg:
                                            # 订单已经是CANCELLED状态，说明之前已经被撤了
                                            logger.info(f"   ℹ️ 订单 {order_id} 已经是取消状态（之前已撤单）")
                                            cancelled_count += 1
                                            cancel_success = True
                                            break
                                        logger.warning(f"   ⚠️ 撤单失败 (尝试 {retry+1}/3): {order_id}, ret={ret_cancel}")
                                        time.sleep(1)  # 等待1秒后重试
                                except Exception as e:
                                    logger.warning(f"   ⚠️ 撤单异常 (尝试 {retry+1}/3): {order_id}, error={e}")
                                    time.sleep(1)
                            if not cancel_success:
                                logger.error(f"   ❌ {code} 撤单最终失败: {order_id}")
                    else:
                        logger.error(f"   ⚠️ 无法查询 {code} 订单状态 (ret={ret})")
                except Exception as e:
                    logger.error(f"   ❌ {code} 处理异常: {e}")
                finally:
                    if check_ctx:
                        check_ctx.close()
            
            if cancel_ctx:
                cancel_ctx.close()
            
            # 报告结果
            logger.warning(f"📊 撤销结果: {cancelled_count} 个已撤销, {len(partial_fills)} 个残留")
            
            if partial_fills:
                logger.critical("🚨🚨🚨 存在残留头寸！这不是完整的Iron Condor！")
                logger.critical("   请立即手动检查持仓并在富途APP处理！")
                for pf in partial_fills:
                    logger.critical(f"     - {pf['code']} ({pf['side']}): 已成交{pf['dealt_qty']}/{pf['qty']}张 @ ${pf['price']}")
                
                return {
                    "success": False, 
                    "reason": f"部分订单未成交，{cancelled_count}个已撤销，{len(partial_fills)}个残留头寸",
                    "partial_fills": partial_fills,  # 返回给调用方处理
                }
            
            return {"success": False, "reason": "部分订单未成交，已全部撤销"}

    # ============ 平仓机制（从港股脚本移植）============
    def _is_today_trading_day(self) -> bool:
        """判断今天是否为美股交易日（以美东时间为准）"""
        import pytz
        from futu import OpenQuoteContext, Market
        from config import FUTU_CONFIG

        # 美股交易日以美东时间日期为准，不能用本机北京时间
        et_today = datetime.now(pytz.timezone("America/New_York")).date()

        quote_ctx = OpenQuoteContext(host=FUTU_CONFIG["host"], port=FUTU_CONFIG["port"])
        ret, data = quote_ctx.request_trading_days(
            market=Market.US,
            start=et_today.isoformat(),
            end=et_today.isoformat(),
        )
        quote_ctx.close()

        # request_trading_days 返回可能是 list 或 DataFrame，需要兼容处理
        if ret == 0:
            if hasattr(data, 'empty'):  # DataFrame
                is_trading = not data.empty
            else:  # list
                is_trading = len(data) > 0

            if is_trading:
                logger.info(f"📅 今日（美东）{et_today} 是美股交易日")
                return True
        logger.info(f"🔴 今日（美东）{et_today} 非美股交易日（节假日或周末），跳过")
        return False

    def _get_positions_with_expiry(self) -> List[Dict]:
        """
        获取 IC 策略自己开的期权持仓（通过 ic_open_codes.json 精确匹配）。
        不会误读账户中其他标的的 Wheel Sell Put / Covered Call。
        """
        import re
        from futu import OpenSecTradeContext, TrdEnv
        from config import FUTU_CONFIG

        positions = []
        try:
            trd_env = TrdEnv.SIMULATE if self.dry_run else TrdEnv.REAL
            acc_id_key = "sim_acc_id" if self.dry_run else "real_acc_id"
            acc_id = int(FUTU_CONFIG.get(acc_id_key, "281756481449956811"))

            trade_ctx = OpenSecTradeContext(
                host=FUTU_CONFIG["host"],
                port=FUTU_CONFIG["port"],
                filter_trdmarket="US",
                security_firm="FUTUSECURITIES",
            )
            ret, pos_data = trade_ctx.position_list_query(
                trd_env=trd_env,
                acc_id=acc_id,
                refresh_cache=True,
            )
            trade_ctx.close()

            if ret != 0 or pos_data is None or pos_data.empty:
                return []

            # ── 精确过滤：只操作 IC 策略自己记录的代码 ──────────────
            ic_codes = _load_ic_codes()
            ticker_name = self.stock["ticker"].split(".")[1]

            if ic_codes:
                # 精确匹配：只取本标的（ticker_name）的 IC 代码，
                # 避免 QQQ Trader 误读 IWM/GLD 代码（三标的代码混存于同一文件）
                ic_codes_this_asset = {c for c in ic_codes if ticker_name in c}
                matched = pos_data[pos_data["code"].isin(ic_codes_this_asset)]
            else:
                # 首次运行、追踪文件不存在时，退化为名称过滤（兼容旧行为）
                logger.warning(
                    "⚠️ ic_open_codes.json 不存在，使用标的名称模糊过滤。"
                    "如账户中有同标的 Wheel 持仓，请手动确认后再运行。"
                )
                matched = pos_data[pos_data["code"].str.contains(ticker_name, na=False)]

            for _, row in matched.iterrows():
                qty = int(row.get("qty", 0))
                if qty == 0:
                    continue  # 已平仓，跳过
                code = row["code"]
                m = re.search(rf"{ticker_name}(\d{{6}})([CP])(\d+)", code)
                if m:
                    try:
                        expiry = datetime.strptime(m.group(1), "%y%m%d").date()
                    except ValueError:
                        expiry = None
                else:
                    expiry = None
                positions.append({
                    "code": code,
                    "expiry": expiry,
                    "qty": qty,
                    "side": row.get("position_side", "N/A"),
                    "unrealized_pl": float(row.get("unrealized_pl", 0) or 0),
                    "cost_price": float(row.get("cost_price", 0) or 0),
                })
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")

        return positions

    def _should_close_today(self) -> bool:
        """
        判断今天是否需要触发平仓（到期前1个美股交易日）
        
        使用 prev_n_trading_day 确保在正确的交易日平仓，
        避免假期导致无法平仓的问题。
        """
        early_close_days = self.config.get("early_close_days", 1)
        import pytz as _pytz
        today = datetime.now(_pytz.timezone("America/New_York")).date()  # 美东日期

        positions = self._get_positions_with_expiry()
        if not positions:
            return False

        # 按到期日分组
        expiry_set = set(p["expiry"] for p in positions if p["expiry"])
        for expiry in expiry_set:
            # 计算"到期前第 N 个美股交易日"
            close_trigger_day = self._prev_n_us_trading_day(expiry, n=early_close_days)
            days_left = (expiry - today).days
            # 实际提前了多少自然日（正常应 = early_close_days，长假时会更大）
            days_advanced = (expiry - close_trigger_day).days

            logger.info(
                f"📋 到期日 {expiry}：平仓触发日 = {close_trigger_day}，"
                f"今天 = {today}，剩余 {days_left} 自然日"
            )

            # 长假预警：实际提前超过预期
            if days_advanced > early_close_days + 1:
                msg = (
                    f"到期日 {expiry} 前有长假（连续 {days_advanced - early_close_days} 天不可交易），"
                    f"平仓触发日提前至 {close_trigger_day}（提前 {days_advanced} 自然日），"
                    f"预计损失部分 Theta（约 {days_advanced - early_close_days} 天）。"
                    f"如需手动调整，请在 {close_trigger_day} 前处理。"
                )
                logger.warning(f"📅 长假平仓预警: {msg}")
                self.notifier.send_alert("WARNING", "长假平仓预警", msg)

            # 平仓判断
            if today >= close_trigger_day:
                logger.warning(
                    f"⚠️ 今天({today}) >= 平仓触发日({close_trigger_day})，"
                    f"需要对 {expiry} 到期的持仓执行平仓！"
                )
                return True

        return False

    def _prev_n_us_trading_day(self, ref_date: date, n: int = 1) -> date:
        """
        从 ref_date 往前数第 n 个美股交易日

        例如：ref_date = 2026-05-01（到期日），n=1
          → 返回 2026-04-30（若为美股交易日），
            若30日是节假日则继续往前找到 29日……
        """
        from futu import OpenQuoteContext, Market
        from config import FUTU_CONFIG
        
        # 向前查询最多60个自然日
        look_back = 60
        start = ref_date - timedelta(days=look_back)
        end = ref_date - timedelta(days=1)
        
        quote_ctx = OpenQuoteContext(host=FUTU_CONFIG["host"], port=FUTU_CONFIG["port"])
        ret, data = quote_ctx.request_trading_days(
            market=Market.US,
            start=start.isoformat(),   # Futu API 标准参数名
            end=end.isoformat(),
        )
        quote_ctx.close()
        
        if ret != 0 or data is None:
            # API 失败时降级：往前数 n 个自然日
            logger.warning("美股交易日历获取失败，降级使用自然日")
            return ref_date - timedelta(days=n)

        # Futu returns list of dicts {"time": "YYYY-MM-DD"} or DataFrame
        rows = data if isinstance(data, list) else (
            data.to_dict("records") if hasattr(data, "to_dict") else []
        )
        trading_days = []
        for row in rows:
            try:
                if isinstance(row, dict):
                    t = row.get("time") or row.get("TIME") or row.get("calendar_date")
                elif isinstance(row, str):
                    t = row
                elif hasattr(row, "date"):
                    trading_days.append(row.date())
                    continue
                else:
                    t = str(row)
                if t:
                    trading_days.append(datetime.strptime(str(t)[:10], "%Y-%m-%d").date())
            except Exception:
                pass
        trading_days = sorted(set(trading_days))

        if not trading_days:
            logger.warning("美股交易日历获取失败，降级使用自然日")
            return ref_date - timedelta(days=n)
        
        if len(trading_days) >= n:
            return trading_days[-n]
        else:
            return ref_date - timedelta(days=n)

    def _check_holiday_risk(self) -> Optional[str]:
        """
        检测未来7天内是否有美股市场假期（工作日不可交易）。
        若距下一个假期 ≤ 3 个交易日，返回警告字符串；否则返回 None。
        """
        from futu import OpenQuoteContext, Market, RET_OK
        from config import FUTU_CONFIG
        import pytz

        et_today = datetime.now(pytz.timezone("America/New_York")).date()
        look_ahead_end = et_today + timedelta(days=7)

        try:
            quote_ctx = OpenQuoteContext(host=FUTU_CONFIG["host"], port=FUTU_CONFIG["port"])
            ret, data = quote_ctx.request_trading_days(
                market=Market.US,
                start=(et_today + timedelta(days=1)).isoformat(),
                end=look_ahead_end.isoformat(),
            )
            quote_ctx.close()
        except Exception as e:
            logger.warning(f"⚠️ 长假检查 API 异常: {e}")
            return None

        if ret != 0 or data is None:
            return None

        # 解析交易日集合
        rows = data if isinstance(data, list) else (
            data.to_dict("records") if hasattr(data, "to_dict") else []
        )
        trading_days_set = set()
        for row in rows:
            try:
                t = row.get("time") if isinstance(row, dict) else str(row)
                if t:
                    trading_days_set.add(datetime.strptime(str(t)[:10], "%Y-%m-%d").date())
            except Exception:
                pass

        # 找出未来7天中工作日但非交易日的日期（即假期）
        holiday_dates = []
        d = et_today + timedelta(days=1)
        while d <= look_ahead_end:
            if d.weekday() < 5 and d not in trading_days_set:
                holiday_dates.append(d)
            d += timedelta(days=1)

        if not holiday_dates:
            return None

        # 计算今天到第一个假期的交易日数
        first_holiday = holiday_dates[0]
        trading_days_until = sum(1 for d in trading_days_set if et_today < d < first_holiday)

        if trading_days_until <= 3:
            return (
                f"美国市场假期预警：{first_holiday} 休市，"
                f"距今仅 {trading_days_until} 个交易日，"
                f"期权流动性可能不足，跳过新开仓"
            )
        return None

    def close_all_positions(self, close_reason: str = "") -> Dict:
        """平仓所有QQQ期权持仓（反向下单）
        close_reason: 平仓原因（用于 trade_history.csv 记录）
        """
        from futu import OpenSecTradeContext, TrdSide, OrderType, TrdEnv, RET_OK
        from config import FUTU_CONFIG

        logger.info("=" * 50)
        logger.info(f"🔴 开始执行平仓  原因: {close_reason or '手动'}")
        logger.info("=" * 50)

        positions = self._get_positions_with_expiry()
        if not positions:
            logger.info("当前无持仓，无需平仓")
            return {"success": True, "closed": 0}

        # 记录平仓前浮盈亏（用于计算已实现盈亏）
        pre_close_pnl = sum(p.get("unrealized_pl", 0) for p in positions)
        logger.info(f"📊 平仓前浮盈亏: ${pre_close_pnl:+,.2f}")

        trd_env = TrdEnv.SIMULATE if self.dry_run else TrdEnv.REAL
        acc_id_key = "sim_acc_id" if self.dry_run else "real_acc_id"
        acc_id = int(FUTU_CONFIG.get(acc_id_key, "281756481449956811"))

        trade_ctx = OpenSecTradeContext(
            host=FUTU_CONFIG["host"],
            port=FUTU_CONFIG["port"],
            filter_trdmarket="US",
            security_firm="FUTUSECURITIES",
        )
        closed = 0
        successfully_closed_codes: List[str] = []

        submitted_orders = []  # 记录已提交订单，用于后续成交验证

        for pos in positions:
            code = pos["code"]
            holding_qty = pos["qty"]  # 负=空头(卖出), 正=多头(买入)
            qty = abs(holding_qty)
            if qty == 0:
                continue

            # 确定平仓方向：用qty符号，比position_side字符串更可靠
            # 空头(qty<0, 卖出的期权) → 买入平仓
            # 多头(qty>0, 买入的期权) → 卖出平仓
            if holding_qty < 0:
                close_side = TrdSide.BUY
                side_label = "买入平仓"
            else:
                close_side = TrdSide.SELL
                side_label = "卖出平仓"

            # 获取实时盘口
            p = self.get_bid_ask([code])
            prices = p.get(code, {})
            bid = prices.get("bid", 0.0)
            ask = prices.get("ask", 0.0)
            raw_mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0.01
            mid = _round_option_price(raw_mid)  # 富途价格精度要求：≤2位小数

            logger.info(f"📤 {side_label} {code}  数量={qty}  价格=${mid:.2f}  (bid={bid:.2f} ask={ask:.2f})")

            if self.dry_run:
                logger.info(f"   [模拟] 平仓订单已提交")
                closed += 1
                successfully_closed_codes.append(code)
                continue

            ret, data = trade_ctx.place_order(
                code=code,
                price=mid,
                qty=qty,
                trd_side=close_side,
                order_type=OrderType.NORMAL,
                adjust_limit=0,
                trd_env=trd_env,
                acc_id=acc_id,
            )
            if ret == RET_OK:
                order_id = data.iloc[0]["order_id"]
                logger.info(f"   ✅ 平仓订单已提交: {order_id}")
                closed += 1
                successfully_closed_codes.append(code)
                submitted_orders.append({
                    "code": code, "order_id": order_id, "qty": qty,
                    "close_side_is_buy": (close_side == TrdSide.BUY),
                    "bid": bid, "ask": ask,
                })
            else:
                logger.error(f"   ❌ 平仓下单失败: {data}")

        trade_ctx.close()
        logger.info(f"🔴 平仓完成：共提交 {closed}/{len(positions)} 腿")

        # ── 3轮递进价格等待成交（mid → 75%价差 → 市价+3% 缓冲）──────────
        if submitted_orders and not self.dry_run:
            from futu import ModifyOrderOp as _MOp
            verify_ctx = None
            try:
                verify_ctx = OpenSecTradeContext(
                    host=FUTU_CONFIG["host"],
                    port=FUTU_CONFIG["port"],
                    filter_trdmarket="US",
                    security_firm="FUTUSECURITIES",
                )
                pending = list(submitted_orders)  # 当前轮待验证的订单

                for round_num in range(3):
                    round_label = ["第1轮(mid价)", "第2轮(75%价差)", "第3轮(市价+3%)"][round_num]
                    logger.info(f"⏳ 平仓 {round_label}：等待120秒...")
                    time.sleep(120)

                    still_pending = []
                    for o in pending:
                        ret_q, od = verify_ctx.order_list_query(
                            order_id=o["order_id"],
                            trd_env=trd_env,
                            acc_id=acc_id,
                        )
                        if ret_q == RET_OK and not od.empty:
                            status    = str(od.iloc[0]["order_status"])
                            dealt_qty = int(od.iloc[0].get("dealt_qty", 0) or 0)
                            if dealt_qty >= o["qty"] or "FILLED_ALL" in status or status == "11":
                                logger.info(f"   ✅ {o['code']} 已成交 ({dealt_qty}张)")
                            else:
                                still_pending.append(o)
                                logger.warning(f"   ⚠️ {o['code']} 未成交 ({dealt_qty}/{o['qty']} 状态={status})")
                        else:
                            logger.warning(f"   ⚠️ 无法查询 {o['code']} 成交状态，视为未成交")
                            still_pending.append(o)

                    pending = still_pending
                    if not pending:
                        logger.info("✅ 所有平仓订单已成交")
                        break

                    if round_num < 2:
                        # 取消未成交订单，以更激进价格重新提交
                        logger.info(f"   🔄 {len(pending)} 条腿未成交，取消后以 {['第2轮','第3轮'][round_num]} 价格重新提交...")
                        new_pending = []
                        for o in pending:
                            # 1. 撤销旧订单
                            try:
                                verify_ctx.modify_order(
                                    modify_order_op=_MOp.CANCEL,
                                    order_id=o["order_id"],
                                    qty=0, price=0,
                                    trd_env=trd_env,
                                    acc_id=acc_id,
                                )
                            except Exception as _ce:
                                logger.warning(f"   ⚠️ 撤单异常 {o['code']}: {_ce}")

                            # 2. 刷新盘口，以递进价格重新提交
                            fresh = self.get_bid_ask([o["code"]])
                            fp = fresh.get(o["code"], {})
                            new_bid = fp.get("bid", o["bid"])
                            new_ask = fp.get("ask", o["ask"])
                            new_price = _escalate_close_price(o["close_side_is_buy"], new_bid, new_ask, round_num + 1)
                            logger.info(f"   💱 {o['code']} 重新提交 ${new_price:.2f}  (bid={new_bid:.2f} ask={new_ask:.2f})")

                            close_side_enum = TrdSide.BUY if o["close_side_is_buy"] else TrdSide.SELL
                            ret_new, d_new = verify_ctx.place_order(
                                code=o["code"],
                                price=new_price,
                                qty=o["qty"],
                                trd_side=close_side_enum,
                                order_type=OrderType.NORMAL,
                                adjust_limit=0,
                                trd_env=trd_env,
                                acc_id=acc_id,
                            )
                            if ret_new == RET_OK:
                                o["order_id"] = d_new.iloc[0]["order_id"]
                                o["bid"] = new_bid
                                o["ask"] = new_ask
                                new_pending.append(o)
                                logger.info(f"   ✅ {o['code']} 重新提交成功: {o['order_id']}")
                            else:
                                logger.error(f"   ❌ {o['code']} 重新提交失败: {d_new}")
                        pending = new_pending
                else:
                    # for 循环未 break → 3 轮后仍有未成交
                    if pending:
                        unfilled_codes = [o["code"] for o in pending]
                        msg = f"平仓3轮后仍有 {len(unfilled_codes)} 条腿未成交: {unfilled_codes}"
                        logger.critical(f"🚨 {msg}")
                        logger.critical("   请立即在富途APP检查并手动处理！")
                        self.notifier.send_alert("CRITICAL", "平仓3轮未成交", msg)

            except Exception as e:
                logger.error(f"成交验证异常: {e}")
            finally:
                if verify_ctx:
                    verify_ctx.close()

        # ── 只从追踪文件移除已成功提交平仓的代码 ──────────────
        # 注意：下单失败的腿保留在 ic_open_codes.json，防止持仓失控
        if successfully_closed_codes:
            _remove_ic_codes(successfully_closed_codes)
            logger.info(f"📝 IC 持仓代码已清除: {successfully_closed_codes}")
        failed_codes = [p["code"] for p in positions if p["code"] not in successfully_closed_codes]
        if failed_codes:
            logger.error(f"❌ 以下腿平仓失败，仍保留在追踪文件: {failed_codes}")
            logger.error("   请手动在富途APP平仓后，再手动清理 ic_open_codes.json")

        # ── 实盘绩效持久化：记录平仓历史 ────────────────────────
        if closed > 0:
            asset_name = self.stock["name"]
            open_trade = _load_open_trade(asset_name)
            entry_date_str = open_trade.get("entry_date", "")
            days_held = 0
            if entry_date_str:
                try:
                    days_held = (date.today() - date.fromisoformat(entry_date_str)).days
                except ValueError:
                    pass
            _append_trade_history({
                "date":         date.today().isoformat(),
                "time":         datetime.now().strftime("%H:%M:%S"),
                "asset":        asset_name,
                "action":       "CLOSE",
                "expiry":       open_trade.get("expiry", ""),
                "sell_put":     open_trade.get("sell_put", ""),
                "sell_call":    open_trade.get("sell_call", ""),
                "buy_put":      open_trade.get("buy_put", ""),
                "buy_call":     open_trade.get("buy_call", ""),
                "groups":       open_trade.get("groups", ""),
                "net_premium":  open_trade.get("net_credit", ""),
                "days_held":    days_held,
                "realized_pnl": round(pre_close_pnl, 2),
                "close_reason": close_reason,
            })
            _clear_open_trade(asset_name)
            logger.info(f"📝 [{asset_name}] 平仓记录已写入 trade_history.csv  realized_pnl=${pre_close_pnl:+,.2f}")

        # 平仓成功后记录冷却期开始日期（匹配回测 cooldown_days=5）
        if closed > 0:
            _record_close_date(self.stock["name"])

        return {"success": True, "closed": closed, "total": len(positions)}

    def _check_market_conditions(self) -> Dict:
        """
        检查市场条件：HV20波动率过滤 + 慢熊检测
        
        返回:
            {
                "can_open": bool,      # 是否可以开仓
                "adjust_otm": float,   # 需要调整的OTM距离（0表示不调整）
                "reason": str,         # 原因描述
                "hv20": float,         # 当前HV20值
                "cumulative_20d": float, # 20日累计收益率
            }
        """
        import pandas as pd
        import numpy as np
        from futu import RET_OK, KLType
        
        ticker = self.stock["ticker"]
        today = date.today()
        start_date = (today - timedelta(days=60)).isoformat()  # 取60天数据以确保有20个交易日
        
        try:
            # 获取历史K线数据
            ret, data, next_page = self.data.quote_ctx.request_history_kline(
                code=ticker,
                start=start_date,
                end=today.isoformat(),
                ktype=KLType.K_DAY,
                max_count=100,
            )
            
            if ret != RET_OK or data is None or data.empty:
                logger.warning("⚠️ 无法获取历史K线，跳过市场条件检查")
                return {"can_open": True, "adjust_otm": 0.0, "reason": "无法获取历史数据", "hv20": 0.0, "cumulative_20d": 0.0}
            
            # 提取收盘价序列
            closes = data["close"].astype(float)
            if len(closes) < 20:
                logger.warning(f"⚠️ 历史数据不足 {len(closes)} 天，跳过市场条件检查")
                return {"can_open": True, "adjust_otm": 0.0, "reason": "历史数据不足", "hv20": 0.0, "cumulative_20d": 0.0}
            
            # 计算HV20（使用backtest_real中的historical_volatility函数）
            from backtest_real import historical_volatility
            hv20 = historical_volatility(closes, window=20)
            
            # 计算20日累计收益率
            if len(closes) >= 20:
                price_20d_ago = closes.iloc[-20]
                price_current = closes.iloc[-1]
                cumulative_20d = (price_current - price_20d_ago) / price_20d_ago
            else:
                cumulative_20d = 0.0
            
            logger.info(f"📊 市场条件检查: HV20={hv20:.3f}, 20日累计收益率={cumulative_20d:.3%}")
            
            # HV20过滤
            hv20_threshold = self.config.get("hv20_threshold", 0.20)
            if hv20 > hv20_threshold:
                return {
                    "can_open": False,
                    "adjust_otm": 0.0,
                    "reason": f"HV20 {hv20:.3f} > 阈值 {hv20_threshold}（波动率过高）",
                    "hv20": hv20,
                    "cumulative_20d": cumulative_20d,
                }
            
            # 慢熊检测
            slow_bear_threshold = self.config.get("slow_bear_threshold_20d", -0.07)
            if cumulative_20d <= slow_bear_threshold:
                defense = self.config.get("slow_bear_defense", "increase_otm")
                if defense == "pause":
                    return {
                        "can_open": False,
                        "adjust_otm": 0.0,
                        "reason": f"20日累计收益率 {cumulative_20d:.3%} ≤ 阈值 {slow_bear_threshold:.1%}（慢熊市场）",
                        "hv20": hv20,
                        "cumulative_20d": cumulative_20d,
                    }
                elif defense == "increase_otm":
                    otm_increase = self.config.get("slow_bear_otm_increase", 0.25)
                    return {
                        "can_open": True,
                        "adjust_otm": otm_increase,  # 返回需要增加的OTM距离
                        "reason": f"20日累计收益率 {cumulative_20d:.3%} ≤ 阈值 {slow_bear_threshold:.1%}（慢熊市场，增大OTM至{otm_increase:.0%}）",
                        "hv20": hv20,
                        "cumulative_20d": cumulative_20d,
                    }
            
            # 所有检查通过
            return {
                "can_open": True,
                "adjust_otm": 0.0,
                "reason": "市场条件正常",
                "hv20": hv20,
                "cumulative_20d": cumulative_20d,
            }
            
        except Exception as e:
            logger.error(f"市场条件检查异常: {e}")
            # 异常时禁止开仓：宁可错过机会，不可在未知条件下开仓
            return {"can_open": False, "adjust_otm": 0.0, "reason": f"市场条件检查异常，禁止开仓: {e}", "hv20": 0.0, "cumulative_20d": 0.0}

    def _check_stop_loss(self) -> Dict:
        """
        止损检查
        
        规则1 - 单组止损：单组亏损 > 2倍权利金时强制平仓
        规则2 - 全局止损：总亏损 > 20% 时全部平仓观望
        
        返回: {"triggered": bool, "reason": str, "details": str}
        """
        positions = self._get_positions_with_expiry()
        if not positions:
            return {"triggered": False, "reason": "", "details": ""}
        
        # 统计总未实现盈亏
        total_unrealized_pl = sum(p["unrealized_pl"] for p in positions)
        
        # 估算开仓时收到的权利金
        leg_count = len(positions)
        group_count = max(1, leg_count // 4)
        # 使用配置中的估算权利金
        estimated_credit_per_group = self.config.get("estimated_credit_per_group", 1000)
        total_estimated_credit = estimated_credit_per_group * group_count
        
        logger.info(f"📊 止损检查: 未实现亏损=${total_unrealized_pl:.2f}, 估算权利金=${total_estimated_credit:.2f}")
        
        # 规则1：单组止损（亏损 > 2倍权利金）
        if group_count > 0:
            avg_loss_per_group = abs(total_unrealized_pl) / group_count
            if avg_loss_per_group > estimated_credit_per_group * 2:
                return {
                    "triggered": True,
                    "reason": f"单组亏损 ${avg_loss_per_group:.0f} > 2倍权利金 ${estimated_credit_per_group * 2}",
                    "details": f"总亏损 ${total_unrealized_pl:.0f}，共 {group_count} 组，平均 ${avg_loss_per_group:.0f}/组"
                }
        
        # 规则2：全局止损（单标的亏损 > 20%）
        # 使用各标的独立资金（QQQ $9k / IWM $3k / GLD $3k）而非总资金
        asset_capital = self.config.get("capital", INITIAL_CAPITAL / len(ASSETS))
        total_loss_pct = abs(total_unrealized_pl) / asset_capital
        if total_loss_pct > 0.20:
            return {
                "triggered": True,
                "reason": f"标的亏损 {total_loss_pct*100:.1f}% > 止损线 20%（${asset_capital:.0f}/标的）",
                "details": f"未实现亏损 ${total_unrealized_pl:.0f}，标的资金 ${asset_capital:.0f}"
            }
        
        return {"triggered": False, "reason": "", "details": ""}

    def check_and_manage(self) -> Dict:
        """
        检查并管理单个标的的仓位（每次循环调用）

        流程：
          0. VIX硬止损检查（HV20≥39% → 强平所有持仓）
          1. 风险评估 → 止盈/止损平仓
          2. 到期前平仓检查
          3. 开仓检查
        注意：交易日校验由调用方（run_all_assets）统一做一次
        """
        ticker = self.stock["ticker"]
        name   = self.stock["name"]

        # ── VIX 硬止损检查（优先级最高，匹配回测 VIX_HARD_STOP_HV=0.39）──────
        market_cond = self._check_market_conditions()
        hv20 = market_cond.get("hv20", 0.0)

        if hv20 >= VIX_HARD_STOP_HV:
            if not _is_vix_hard_stopped(name):
                _set_vix_hard_stop(name)
            positions = self._get_positions_with_expiry()
            if positions:
                msg = f"HV20={hv20:.1%} >= {VIX_HARD_STOP_HV:.0%}，触发VIX硬止损，强平所有持仓"
                logger.critical(f"[{name}] 🚨 {msg}")
                self.notifier.send_alert("CRITICAL", f"[{name}] VIX硬止损触发", msg)
                return self.close_all_positions(close_reason="VIX_HARD_STOP")
            else:
                logger.info(f"[{name}] 🚨 VIX硬止损中（HV20={hv20:.1%}），无持仓，等待恢复")
                return {"success": True, "skipped": True,
                        "reason": f"[{name}] VIX硬止损中，等待HV20<{VIX_COOLDOWN_HV:.0%}"}

        # ── VIX 硬止损恢复检查（HV20 必须降至 28% 以下才解除，与回测对齐）──
        if _is_vix_hard_stopped(name):
            if hv20 < VIX_COOLDOWN_HV:
                _clear_vix_hard_stop(name)
                logger.info(f"[{name}] ✅ VIX恢复，HV20={hv20:.1%} < {VIX_COOLDOWN_HV:.0%}，解除硬止损")
            else:
                logger.info(
                    f"[{name}] 🚨 VIX硬止损恢复等待中，HV20={hv20:.1%} >= {VIX_COOLDOWN_HV:.0%}，"
                    f"需降至{VIX_COOLDOWN_HV:.0%}以下才恢复开仓"
                )
                return {"success": True, "skipped": True,
                        "reason": f"[{name}] VIX硬止损恢复等待（HV20={hv20:.1%}，需<{VIX_COOLDOWN_HV:.0%}）"}

        # ── 动态组数计算（配置F=20x，与回测对齐）──────────────────
        base_groups = self.config["max_groups"]
        groups_cap = base_groups * GROUPS_CAP_MULT
        if DYNAMIC_SIZING:
            account_equity = self._get_account_equity()
            if account_equity > 0:
                total_initial = sum(a["capital"] for a in ASSETS)
                scale = account_equity / max(total_initial, 1)
                full_max_groups = min(groups_cap, max(base_groups, int(base_groups * scale)))
                logger.info(
                    f"[{name}] 📈 动态组数: 账户${account_equity:,.0f} / 初始${total_initial:,} "
                    f"= {scale:.2f}x → {full_max_groups}组 (base={base_groups}, cap={groups_cap})"
                )
            else:
                full_max_groups = base_groups
                logger.warning(f"[{name}] ⚠️ 无法获取账户净值，使用基线组数 {base_groups}")
        else:
            full_max_groups = base_groups

        # ── 降杠杆控制（HV20 > 22% 时组数减半，与回测对齐）──────────
        if hv20 > VIX_DELEVERAGE_HV:
            effective_max_groups = max(1, full_max_groups // 2)
            logger.warning(
                f"[{name}] ⚠️ HV20={hv20:.1%} > {VIX_DELEVERAGE_HV:.0%}，"
                f"降杠杆：max_groups {full_max_groups}→{effective_max_groups}"
            )
        else:
            effective_max_groups = full_max_groups

        # ── 风险评估（止盈/止损）────────────────────────
        risk_result = self._evaluate_risk()
        if risk_result.get("action") == "CLOSE_ALL":
            logger.warning(f"[{name}] 🛑 触发自动止损: {risk_result['reason']}")
            self.notifier.send_alert("CRITICAL", f"[{name}] 触发自动止损: {risk_result['reason']}", risk_result.get("details", ""))
            return self.close_all_positions(close_reason="STOP_LOSS")
        elif risk_result.get("action") == "PARTIAL_CLOSE":
            logger.warning(f"[{name}] ⚠️ 触发提前平仓: {risk_result['reason']}")
            self.notifier.send_alert("WARNING", f"[{name}] 提前平仓: {risk_result['reason']}", risk_result.get("details", ""))
            return self.close_all_positions(close_reason="PROFIT_TARGET")

        # 注意：不再调用 _check_stop_loss()（使用估算权利金$100，易误触发）
        # _evaluate_risk() 已实现：价格穿越止损（翼宽50%）+ 5%资金止损，与回测一致

        # ── 到期平仓检查 ──────────────────────────────
        if self._should_close_today():
            logger.info(f"[{name}] 🔴 触发到期平仓...")
            self.notifier.send_alert("WARNING", f"[{name}] 到期前平仓触发", "持仓已到平仓触发日")
            return self.close_all_positions(close_reason="EXPIRY")

        # ── 冷却期检查（匹配回测 cooldown_days=5：任意平仓后5天内不开新仓）──
        cooldown_days = self.config.get("cooldown_days", 5)
        cooldown_state = _load_cooldown_state()
        last_close_str = cooldown_state.get(name)
        if last_close_str:
            try:
                last_close = date.fromisoformat(last_close_str)
                days_since = (date.today() - last_close).days
                if days_since < cooldown_days:
                    remaining = cooldown_days - days_since
                    logger.info(
                        f"[{name}] ⏳ 冷却期中（{days_since}/{cooldown_days}天），"
                        f"还剩{remaining}天，跳过开仓"
                    )
                    return {"success": True, "skipped": True,
                            "reason": f"[{name}] 冷却期中（还剩{remaining}天）"}
            except ValueError:
                pass

        # ── 长假风险检查（距假期≤3个交易日时跳过开仓，邮件预警）──────
        holiday_warning = self._check_holiday_risk()
        if holiday_warning:
            logger.warning(f"[{name}] 📅 {holiday_warning}")
            self.notifier.send_alert("WARNING", f"[{name}] 长假风险预警", holiday_warning)
            return {"success": True, "skipped": True, "reason": f"[{name}] 长假风险预警"}

        # ── 开仓检查 ─────────────────────────────────
        existing, total_legs = self.check_existing_positions()

        if existing == -1 or total_legs == -1:
            logger.critical(f"[{name}] 🛑 持仓查询失败，暂停新开仓！")
            return {"success": False, "skipped": True, "reason": f"[{name}] 持仓查询失败"}

        if total_legs > 0 and (total_legs % 4 != 0):
            logger.critical(f"[{name}] 🛑 不平衡头寸（{total_legs}腿），暂停新开仓！")
            return {"success": False, "skipped": True, "reason": f"[{name}] 不平衡头寸({total_legs}腿)"}

        if existing >= effective_max_groups:
            logger.info(f"[{name}] ⚠️ 已有{existing}组持仓，达到上限({effective_max_groups})，跳过")
            return {"success": True, "skipped": True, "reason": f"[{name}] 已达持仓上限({effective_max_groups}组)"}

        # ── 开盘时间检查（仅美东 9:33 后才允许开仓）────────────
        import pytz
        et_now = datetime.now(pytz.timezone("America/New_York"))
        et_open = et_now.replace(hour=9, minute=33, second=0, microsecond=0)
        et_close = et_now.replace(hour=16, minute=0, second=0, microsecond=0)
        if not (et_open <= et_now < et_close):
            logger.info(f"[{name}] ⏰ 当前美东时间 {et_now.strftime('%H:%M')}，不在开仓窗口(09:33-16:00)，跳过开仓")
            return {"success": True, "skipped": True, "reason": f"[{name}] 非开仓时段 (ET {et_now.strftime('%H:%M')})"}

        # ── 执行开仓 ─────────────────────────────────
        groups_to_open = effective_max_groups - existing
        logger.info(f"[{name}] 📊 可开仓组数: {groups_to_open} (现有{existing}组，上限{effective_max_groups}组{'，降杠杆模式' if effective_max_groups < full_max_groups else ''})")
        result = self.open_position(groups_to_open)

        if not result.get("success") and result.get("partial_fills"):
            pf_list = result["partial_fills"]
            logger.critical(f"[{name}] 🚨 不平衡头寸警报！共 {len(pf_list)} 条残留腿，请立即在富途APP处理！")
            for pf in pf_list:
                logger.critical(f"  - {pf['code']} ({pf['side']}): {pf['dealt_qty']}/{pf['qty']}张 @ ${pf['price']}")

        return result


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="美股 Iron Condor 实盘交易")
    parser.add_argument("--dry-run", action="store_true", help="模拟模式，不真实下单")
    parser.add_argument("--once", action="store_true", help="执行一次退出")
    parser.add_argument("--daemon", action="store_true", help="常驻运行（默认）")
    args = parser.parse_args()

    # 默认模式
    if not args.daemon and not args.once:
        args.once = True

    logger.info("="*50)
    logger.info("🦅 美股 Iron Condor 实盘交易")
    logger.info("="*50)
    if args.dry_run:
        logger.info("⚠️ 模拟模式 (--dry-run)")
    if args.once:
        logger.info("🔄 单次执行模式 (--once)")
    if args.daemon:
        logger.info("👁️ 常驻运行模式 (--daemon)")

    # 连接数据源
    data = FutuDataUS()
    if not data.connect():
        logger.error("连接失败")
        return

    check_interval = 300  # 5分钟

    def run_one_cycle(send_email: bool = True):
        """执行一轮检查，返回 True 表示应继续运行"""
        # ── 交易日检查 ────────────────────────────────────────────
        _trader_check = IronCondorTraderUS(data)
        _trader_check.dry_run = args.dry_run
        if not _trader_check._is_today_trading_day():
            logger.info("🔴 今日非美股交易日，本轮跳过")
            return True  # 继续运行，等待下一个交易日

        # ── 逐标的执行检查/管理 ──────────────────────────────────
        asset_results = []
        notifier = _trader_check.notifier

        for asset in ASSETS:
            logger.info("")
            logger.info(f"{'─'*50}")
            logger.info(f"[{asset['name']}] 🦅 开始处理 {asset['ticker']}")
            logger.info(f"{'─'*50}")

            trader = IronCondorTraderUS(data)
            trader.dry_run = args.dry_run
            trader.stock = {"ticker": asset["ticker"], "name": asset["name"]}
            trader.config = {**IC_CONFIG, "max_groups": asset["max_groups"], "hv20_threshold": asset.get("hv20_threshold", IC_CONFIG["hv20_threshold"]), "capital": asset["capital"]}

            result = trader.check_and_manage()

            # 收集市场条件（用于日报）
            try:
                mc = trader._check_market_conditions()
                hv20 = mc.get("hv20", 0.0)
            except Exception:
                hv20 = 0.0

            summary_entry = {"name": asset["name"], "hv20": hv20}

            if result.get("success"):
                if result.get("skipped"):
                    logger.info(f"[{asset['name']}] ⏭️ 跳过: {result.get('reason', '')}")
                    summary_entry.update({"action": "跳过", "reason": result.get("reason", ""), "opened": False, "closed": False})
                else:
                    net_premium = result.get("net_premium", 0)
                    logger.info(f"[{asset['name']}] ✅ 流程完成  到期日={result.get('expiry','N/A')}  权利金=${net_premium:.2f}")
                    summary_entry.update({"action": "✅ 开仓", "reason": f"到期日={result.get('expiry','N/A')}", "net_premium": net_premium, "opened": True, "closed": False})
            else:
                logger.warning(f"[{asset['name']}] ⚠️ 未执行: {result.get('reason','')}")
                closed = "close" in str(result.get("reason", "")).lower() or result.get("closed", False)
                summary_entry.update({"action": "🔴 平仓" if closed else "⚠️ 未开仓", "reason": result.get("reason", ""), "opened": False, "closed": closed})

            asset_results.append(summary_entry)

        # ── 日报邮件 ──────────────────────────────────────────────
        if send_email and not args.dry_run:
            notifier.send_daily_summary(asset_results)

        return True

    try:
        if args.daemon:
            # 实盘启动通知（仅一次）
            if not args.dry_run:
                IronCondorTraderUS(data).notifier.send_startup()

            cycle = 0
            last_email_date = None  # 记录上次发邮件的日期，每天只发一次
            while True:
                cycle += 1
                now = datetime.now()
                logger.info(f"🔄 [Daemon] 第 {cycle} 轮检查 {now.strftime('%Y-%m-%d %H:%M:%S')}")
                try:
                    today = now.date()
                    should_email = (today != last_email_date)  # 每天首轮才发日报
                    run_one_cycle(send_email=should_email)
                    if should_email:
                        last_email_date = today
                except Exception as e:
                    logger.error(f"❌ 本轮异常: {e}", exc_info=True)
                # 非交易时段（周末/深夜美股休市）拉长间隔至30分钟，减少空转
                hour_utc8 = datetime.now().hour
                is_us_session = 21 <= hour_utc8 or hour_utc8 < 6  # 美股交易时段（北京时间）
                sleep_sec = check_interval if is_us_session else 1800
                logger.info(f"⏳ 等待 {sleep_sec} 秒后进行下一轮检查...")
                time.sleep(sleep_sec)
        else:
            # --once 模式（默认）
            if not args.dry_run:
                IronCondorTraderUS(data).notifier.send_startup()
            run_one_cycle(send_email=True)

    finally:
        data.close()


if __name__ == "__main__":
    main()