#!/bin/bash
# =============================================================================
# 腾讯 Iron Condor 实盘启动脚本
# =============================================================================
#
# 使用方法:
#   ./run_live.sh start    # 启动策略
#   ./run_live.sh stop     # 停止策略
#   ./run_live.sh status   # 查看状态
#   ./run_live.sh log      # 查看日志
#
# 4月8日港股开市启动流程:
#   1. 确认 Futu OpenD 已启动并登录
#   2. 运行: ./run_live.sh start
#   3. 查看日志确认连接成功
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 日志文件
LOG_DIR="$SCRIPT_DIR/logs"
PID_FILE="$SCRIPT_DIR/wheel_bot.pid"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_opend() {
    # 检查 Futu OpenD 端口是否开放
    if ! nc -z 127.0.0.1 11111 2>/dev/null; then
        log_error "Futu OpenD 未启动！请先打开富途牛牛并登录"
        log_info "富途牛牛 -> 设置 -> OpenD API -> 启动并登录"
        return 1
    fi
    log_info "✅ Futu OpenD 已连接"
    return 0
}

check_config() {
    # 检查邮箱密码
    source "$SCRIPT_DIR/config.py" -s
    if grep -q "YOUR_EMAIL_PASSWORD" "$SCRIPT_DIR/config.py"; then
        log_warn "⚠️ 请先在 config.py 中配置邮箱 SMTP 密码"
        log_info "编辑 config.py -> NOTIFY_CONFIG -> email_password"
        return 1
    fi
    log_info "✅ 配置已就绪"
    return 0
}

start_bot() {
    log_info "🚀 启动腾讯 Iron Condor 策略..."

    check_opend || exit 1
    check_config || exit 1

    # 使用 nohup 后台运行
    nohup python3 "$SCRIPT_DIR/main.py" > "$LOG_DIR/wheel_bot.log" 2>&1 &

    # 保存 PID
    echo $! > "$PID_FILE"

    sleep 2

    # 检查是否启动成功
    if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
        log_info "✅ 策略已启动 (PID: $(cat $PID_FILE))"
        log_info "📋 日志: $LOG_DIR/wheel_bot.log"
        log_info "📊 查看实时日志: tail -f $LOG_DIR/wheel_bot.log"
    else
        log_error "❌ 启动失败，请查看日志"
        tail -50 "$LOG_DIR/wheel_bot.log"
        exit 1
    fi
}

stop_bot() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            log_info "🛑 停止策略 (PID: $PID)..."
            kill "$PID"
            sleep 1
            log_info "✅ 已停止"
        else
            log_warn "策略未运行"
        fi
        rm -f "$PID_FILE"
    else
        log_warn "未找到 PID 文件"
    fi
}

status_bot() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            log_info "🟢 策略运行中 (PID: $PID)"
            log_info "📋 最后 10 行日志:"
            tail -10 "$LOG_DIR/wheel_bot.log"
        else
            log_info "🔴 策略已停止"
        fi
    else
        log_info "🔴 策略未运行"
    fi
}

show_log() {
    if [ -f "$LOG_DIR/wheel_bot.log" ]; then
        tail -50 "$LOG_DIR/wheel_bot.log"
    else
        log_warn "暂无日志"
    fi
}

# =============================================================================
# 主入口
# =============================================================================

case "$1" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    status)
        status_bot
        ;;
    log)
        show_log
        ;;
    restart)
        stop_bot
        sleep 2
        start_bot
        ;;
    *)
        echo "用法: $0 {start|stop|status|log|restart}"
        echo ""
        echo "4月8日启动流程:"
        echo "  1. 打开富途牛牛 -> 设置 -> OpenD API -> 启动并登录"
        echo "  2. $0 start"
        echo "  3. $0 status  # 查看运行状态"
        echo "  4. $0 log     # 查看日志"
        exit 1
        ;;
esac