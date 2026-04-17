#!/usr/bin/env bash
# 投资筛选系统启动脚本
# 用法：
#   bash run.sh watchlist     # 仅监控持仓价格（每周）
#   bash run.sh universe      # 全球股池量化扫描（每季度）
#   bash run.sh all           # 两者都运行
#   bash run.sh earnings      # 季报追踪（每日）
#   bash run.sh test-email    # 测试邮件配置

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_ENV="$SCRIPT_DIR/../.ic_env.local"
LOCAL_ENV="$SCRIPT_DIR/.screener_env.local"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"

if [ ! -x "$PYTHON" ]; then
  PYTHON="$(which python3)"
fi

if [ -z "$PYTHON" ]; then
  echo "错误：未找到 python3"
  exit 1
fi

if [ -f "$ROOT_ENV" ]; then
  # shellcheck disable=SC1090
  source "$ROOT_ENV"
fi

if [ -f "$LOCAL_ENV" ]; then
  # shellcheck disable=SC1090
  source "$LOCAL_ENV"
fi

MODE="${1:-watchlist}"

case "$MODE" in
  watchlist)
    echo "[$(date)] 运行持仓价格监控..."
    "$PYTHON" "$SCRIPT_DIR/screener.py" --watchlist
    ;;
  universe)
    echo "[$(date)] 运行全球股池扫描..."
    "$PYTHON" "$SCRIPT_DIR/screener.py" --universe
    ;;
  all)
    echo "[$(date)] 运行完整扫描..."
    "$PYTHON" "$SCRIPT_DIR/screener.py" --all
    ;;
  earnings)
    echo "[$(date)] 运行季报追踪..."
    "$PYTHON" "$SCRIPT_DIR/earnings_tracker.py"
    ;;
  earnings-summary)
    echo "[$(date)] 输出季报完整日历..."
    "$PYTHON" "$SCRIPT_DIR/earnings_tracker.py" --summary
    ;;
  risk)
    echo "[$(date)] 运行组合风险监控..."
    "$PYTHON" "$SCRIPT_DIR/risk_monitor.py"
    ;;
  macro)
    echo "[$(date)] 运行宏观择时信号..."
    "$PYTHON" "$SCRIPT_DIR/macro_signal.py"
    ;;
  macro-offline)
    echo "[$(date)] 运行宏观择时信号（离线缓存模式）..."
    "$PYTHON" "$SCRIPT_DIR/macro_signal.py" --offline
    ;;
  test-email)
    echo "[$(date)] 测试邮件配置..."
    "$PYTHON" "$SCRIPT_DIR/screener.py" --test-email
    ;;
  *)
    echo "用法: bash run.sh [watchlist|universe|all|earnings|earnings-summary|risk|macro|macro-offline|test-email]"
    exit 1
    ;;
esac
