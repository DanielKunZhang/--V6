"""
通知层
支持：企业微信 Webhook / 邮件通知
"""

import logging
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Dict, Any

from config import NOTIFY_CONFIG

logger = logging.getLogger(__name__)


class EmailNotifier:
    """邮件通知器"""

    def __init__(self, smtp_server="smtp.163.com", smtp_port=465,
                 sender="quanyi_zk@163.com", password=None,
                 recipient="quanyi_zk@163.com"):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender = sender
        self.password = password or NOTIFY_CONFIG.get("email_password", "")
        self.recipient = recipient
        # 检查是否是占位符
        self.enabled = bool(self.password and self.password != "YOUR_EMAIL_PASSWORD")

    def send(self, subject: str, content: str, is_html=False) -> bool:
        """发送邮件"""
        if not self.enabled:
            logger.warning("⚠️ 未配置邮件密码，跳过通知")
            logger.info(f"📧 邮件内容: {subject} - {content[:200]}")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = self.recipient

            mime_type = "html" if is_html else "plain"
            msg.attach(MIMEText(content, mime_type))

            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.recipient, msg.as_string())

            logger.info("✅ 邮件发送成功")
            return True

        except Exception as e:
            logger.error(f"❌ 邮件发送失败: {e}")
            return False

    def notify_trade(self, action: str, option_code: str, strike: float,
                    premium: float, expiration: str) -> bool:
        """通知交易"""
        emoji_map = {"SELL_PUT": "📉", "SELL_CALL": "📈", "CLOSE": "🔄", "ASSIGNED": "⚡"}
        emoji = emoji_map.get(action, "📊")

        subject = f"{emoji} 腾讯 Iron Condor 交易 - {action}"
        content = f"""
<h3>{emoji} 腾讯 Iron Condor 交易执行</h3>
<p><b>操作</b>: {action}</p>
<p><b>期权</b>: {option_code}</p>
<p><b>行权价</b>: HKD {strike:.2f}</p>
<p><b>到期日</b>: {expiration}</p>
<p><b>权利金</b>: HKD {premium:,.2f}</p>
<p><b>时间</b>: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """
        return self.send(subject, content, is_html=True)

    def notify_alert(self, level: str, message: str, details: str = None) -> bool:
        """发送警报"""
        emoji_map = {"INFO": "ℹ️", "WARNING": "⚠️", "CRITICAL": "🚨"}
        emoji = emoji_map.get(level, "📢")

        subject = f"{emoji} 腾讯 Iron Condor 警报 - {level}"
        content = f"<h3>{emoji} 警报</h3><p><b>级别</b>: {level}</p><p><b>消息</b>: {message}</p>"
        if details:
            content += f"<p><b>详情</b>: {details}</p>"
        content += f"<p><b>时间</b>: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"

        return self.send(subject, content, is_html=True)

    def notify_daily(self, date: str, premium_collected: float,
                 total_premium: float, pnl: float = 0) -> bool:
        """每日汇总"""
        subject = f"📈 腾讯 Iron Condor 每日汇总 - {date}"
        content = f"""
<h3>📈 腾讯 Iron Condor 每日汇总</h3>
<p><b>日期</b>: {date}</p>
<p><b>今日权利金</b>: HKD {premium_collected:,.2f}</p>
<p><b>累计权利金</b>: HKD {total_premium:,.2f}</p>
<p><b>当日损益</b>: HKD {pnl:,.2f}</p>
        """
        return self.send(subject, content, is_html=True)


class WeChatNotifier:
    """企业微信 Webhook 通知器"""

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or NOTIFY_CONFIG.get("wechat_webhook_url")
        self.enabled = NOTIFY_CONFIG.get("enabled", True)

    def _send_request(self, payload: Dict) -> bool:
        """发送 POST 请求"""
        if not self.enabled:
            logger.debug("通知已禁用")
            return True

        if not self.webhook_url or self.webhook_url == "YOUR_KEY_HERE":
            logger.warning("⚠️ 未配置微信 Webhook URL，跳过通知")
            logger.info(f"消息内容: {payload}")
            return False

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            result = response.json()

            if result.get("errcode") == 0:
                logger.debug("✅ 微信通知发送成功")
                return True
            else:
                logger.error(f"❌ 微信通知失败: {result}")
                return False

        except requests.exceptions.Timeout:
            logger.error("❌ 微信通知超时")
            return False
        except Exception as e:
            logger.error(f"❌ 微信通知异常: {e}")
            return False

    def send_text(self, content: str, mentioned_list: list = None) -> bool:
        """发送文本消息"""
        payload = {
            "msgtype": "text",
            "text": {
                "content": content,
                "mentioned_list": mentioned_list or []
            }
        }
        return self._send_request(payload)

    def send_markdown(self, content: str) -> bool:
        """发送 Markdown 消息（支持更丰富的格式）"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }
        return self._send_request(payload)

    def notify_trade_executed(
        self,
        action: str,  # "SELL_PUT" | "SELL_CALL" | "CLOSE" | "ASSIGNED"
        option_code: str,
        strike: float,
        premium: float,
        expiration: str,
        quantity: int = 1
    ) -> bool:
        """通知交易执行"""
        emoji_map = {
            "SELL_PUT": "📉",
            "SELL_CALL": "📈",
            "CLOSE": "🔄",
            "ASSIGNED": "⚡",
        }
        emoji = emoji_map.get(action, "📊")

        content = f"""### {emoji} 腾讯 Wheel 交易执行

**操作**: {action.replace('_', ' ')}
**期权**: {option_code}
**行权价**: HKD {strike:.2f}
**到期日**: {expiration}
**数量**: {quantity} 张
**权利金**: HKD {premium:,.2f}
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

        return self.send_markdown(content)

    def notify_alert(
        self,
        level: str,  # "INFO" | "WARNING" | "CRITICAL"
        message: str,
        details: str = None
    ) -> bool:
        """发送警报"""
        emoji_map = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "CRITICAL": "🚨",
        }
        emoji = emoji_map.get(level, "📢")

        content = f"""### {emoji} 腾讯 Wheel 警报

**级别**: {level}
**消息**: {message}"""

        if details:
            content += f"\n**详情**: {details}"

        content += f"\n**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return self.send_markdown(content)

    def notify_status(
        self,
        state: str,
        current_price: float,
        stock_position: Dict = None,
        option_position: Dict = None,
        total_premium: float = 0
    ) -> bool:
        """发送状态报告"""
        content = f"""### 📊 腾讯 Wheel 策略状态

**状态**: {state}
**当前股价**: HKD {current_price:.2f}
**累计权利金**: HKD {total_premium:,.2f}"""

        if stock_position:
            content += f"""
**正股持仓**:
- 数量: {stock_position.get('quantity', 0)} 股
- 成本: HKD {stock_position.get('cost_basis', 0):.2f}
- 盈亏: HKD {stock_position.get('unrealized_pnl', 0):,.2f} ({stock_position.get('unrealized_pnl_pct', 0):.1f}%)"""

        if option_position:
            content += f"""
**期权持仓**:
- 类型: {option_position.get('type', 'N/A')}
- 行权价: HKD {option_position.get('strike', 0):.2f}
- 剩余天数: {option_position.get('dte', 0)} 天"""

        content += f"""
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

        return self.send_markdown(content)

    def notify_daily_summary(
        self,
        date: str,
        premium_collected: float,
        stock_pnl: float = 0,
        total_premium: float = 0
    ) -> bool:
        """发送每日汇总"""
        content = f"""### 📈 腾讯 Wheel 每日汇总

**日期**: {date}
**今日权利金**: HKD {premium_collected:,.2f}
**今日股价损益**: HKD {stock_pnl:,.2f}
**累计权利金**: HKD {total_premium:,.2f}
**更新时间**: {datetime.now().strftime('%H:%M:%S')}"""

        return self.send_markdown(content)


# 全局单例
_email_notifier: Optional[EmailNotifier] = None
_wechat_notifier: Optional[WeChatNotifier] = None


def get_notifier() -> WeChatNotifier:
    """获取微信通知器（兼容旧代码）"""
    global _wechat_notifier
    if _wechat_notifier is None:
        _wechat_notifier = WeChatNotifier()
    return _wechat_notifier


def get_email_notifier() -> EmailNotifier:
    """获取邮件通知器"""
    global _email_notifier
    if _email_notifier is None:
        _email_notifier = EmailNotifier()
    return _email_notifier


def notify_trade(action: str, option_code: str, strike: float,
              premium: float, expiration: str):
    """快捷通知交易（同时发邮件和微信）"""
    email_ok = get_email_notifier().notify_trade(action, option_code, strike, premium, expiration)
    wechat_ok = get_notifier().notify_trade_executed(
        action=action, option_code=option_code, strike=strike,
        premium=premium, expiration=expiration
    )
    return email_ok or wechat_ok


def notify_alert(level: str, message: str, details: str = None):
    """快捷发送警报"""
    email_ok = get_email_notifier().notify_alert(level, message, details)
    wechat_ok = get_notifier().notify_alert(level=level, message=message, details=details)
    return email_ok or wechat_ok


def notify_status(state: str, current_price: float, stock_position: Dict = None,
               option_position: Dict = None, total_premium: float = 0):
    """快捷发送状态"""
    return get_notifier().notify_status(
        state=state, current_price=current_price,
        stock_position=stock_position, option_position=option_position,
        total_premium=total_premium
    )


def notify_daily(date: str, premium_collected: float, total_premium: float, pnl: float = 0):
    """快捷发送每日汇总"""
    email_ok = get_email_notifier().notify_daily(date, premium_collected, total_premium, pnl)
    wechat_ok = get_notifier().notify_daily_summary(
        date=date, premium_collected=premium_collected,
        stock_pnl=pnl, total_premium=total_premium
    )
    return email_ok or wechat_ok
