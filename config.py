"""Minimal shared compatibility config.

The old Iron Condor automation chain has been removed. This module remains only
because a few current reporting / notification utilities still import shared
Futu and email settings from `config`.
"""

from __future__ import annotations

import os

from env_utils import load_local_env


load_local_env()

FUTU_CONFIG = {
    "host": os.environ.get("FUTU_HOST", "127.0.0.1"),
    "port": int(os.environ.get("FUTU_PORT", "11111")),
    "reload": True,
    "sim_acc_id": os.environ.get("FUTU_SIM_ACC_ID", ""),
    "real_acc_id": os.environ.get("FUTU_REAL_ACC_ID", "281756481449956811"),
}

NOTIFY_CONFIG = {
    "enabled": True,
    "email_password": os.environ.get("IC_EMAIL_PASSWORD", ""),
    "wechat_webhook_url": os.environ.get("WECHAT_WEBHOOK_URL", ""),
}

# Legacy names kept only so old reporting imports fail gracefully instead of
# recreating the retired strategy.
STOCK_CONFIG: dict[str, object] = {}
WHEEL_CONFIG: dict[str, object] = {}
RISK_CONFIG: dict[str, object] = {}
RUN_MODE = {"dry_run": True}
LOG_CONFIG = {"level": "INFO"}
IRON_CONDOR_CONFIG: dict[str, object] = {}
