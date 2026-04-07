#!/bin/bash
# 铁鹰调度器启动脚本（由 launchd 调用）
# 手动测试: bash start_scheduler.sh

export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/logs/scheduler_daemon.log"
mkdir -p "$SCRIPT_DIR/logs"

echo "$(date '+%Y-%m-%d %H:%M:%S') | 调度器启动" >> "$LOG"
exec python3 "$SCRIPT_DIR/scheduler.py" >> "$LOG" 2>&1
