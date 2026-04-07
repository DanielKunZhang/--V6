#!/bin/bash
# wheel_tencent/restart.sh
# 重启策略（电脑重启/休眠后用）

cd "$(dirname "$0")"

echo "=== 检查富途 OpenD ==="
if ! (pgrep -f "FutuOpenD" > /dev/null 2>&1); then
    echo "⚠️ 富途 OpenD 未运行，请手动启动后重试"
    exit 1
else
    echo "✅ 富途 OpenD 已在运行"
fi

echo ""
echo "=== 停止旧进程（如果存在）==="
pkill -f "run_ic.py" 2>/dev/null || true
sleep 1

echo ""
echo "=== 启动策略 ==="
python3 run_ic.py &
PID=$!
echo "✅ 策略已启动, PID: $PID"
echo "日志: logs/wheel_bot.log"

# 保存PID到文件
echo $PID > logs/wheel_bot.pid