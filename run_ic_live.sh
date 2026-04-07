#!/bin/bash
# 腾讯 Iron Condor 策略启动脚本
# 使用方法:
#   ./run_ic_live.sh start     # 启动
#   ./run_ic_live.sh stop     # 停止
#   ./run_ic_live.sh status  # 状态
#   ./run_ic_live.sh test    # 测试运行

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="ic_bot.pid"
LOG_FILE="logs/ic_bot.log"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_opend() {
    # 检查 Futu OpenD 是否运行
    if nc -z 127.0.0.1 11111 2>/dev/null; then
        echo -e "${GREEN}✓ Futu OpenD 运行中${NC}"
        return 0
    else
        echo -e "${RED}✗ Futu OpenD 未启动${NC}"
        echo "请先启动富途极探端 (Futu OpenD)"
        return 1
    fi
}

start() {
    echo "启动 Iron Condor 机器人..."
    
    # 检查 OpenD
    check_opend || exit 1
    
    # 检查是否已运行
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "${YELLOW}机器人已在运行中 (PID: $PID)${NC}"
            return 1
        fi
        rm -f "$PID_FILE"
    fi
    
    # 创建日志目录
    mkdir -p logs
    
    # 启动（后台运行）
    nohup python main_ic.py >> "$LOG_FILE" 2>&1 &
    PID=$!
    
    echo "$PID" > "$PID_FILE"
    echo -e "${GREEN}✓ 机器人已启动 (PID: $PID)${NC}"
    echo "日志: $LOG_FILE"
    
    # 等待2秒，检查是否成功启动
    sleep 2
    if kill -0 "$PID" 2>/dev/null; then
        echo -e "${GREEN}✓ 启动成功${NC}"
    else
        echo -e "${RED}✗ 启动失败，请检查日志${NC}"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop() {
    echo "停止 Iron Condor 机器人..."
    
    if [ ! -f "$PID_FILE" ]; then
        echo "未找到 PID 文件，可能未运行"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        sleep 1
        
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID"
        fi
        
        echo -e "${GREEN}✓ 已停止${NC}"
    else
        echo "进程已结束"
    fi
    
    rm -f "$PID_FILE"
}

status() {
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${YELLOW}机器人未运行${NC}"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    
    if kill -0 "$PID" 2>/dev/null; then
        echo -e "${GREEN}✓ 机器人运行中 (PID: $PID)${NC}"
        
        # 显示最近日志
        if [ -f "$LOG_FILE" ]; then
            echo ""
            echo "=== 最近日志 ==="
            tail -10 "$LOG_FILE"
        fi
    else
        echo -e "${RED}✗ 机器人已停止 (PID 文件过时)${NC}"
        rm -f "$PID_FILE"
    fi
}

test_run() {
    echo "测试运行（单次执行）..."
    
    check_opend || exit 1
    
    python main_ic.py --once
}

case "${1:-start}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    status)
        status
        ;;
    test)
        test_run
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    *)
        echo "用法: $0 {start|stop|status|test|restart}"
        exit 1
        ;;
esac