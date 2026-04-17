#!/bin/bash
echo "❌ 已废弃：restart.sh 属于旧港股/Wheel 入口。"
echo "✅ 当前生产系统由 scheduler.py + start_scheduler.sh 管理。"
echo "   如需重启，请先：pkill -f \"scheduler.py\""
echo "   再执行：bash start_scheduler.sh"
exit 1
