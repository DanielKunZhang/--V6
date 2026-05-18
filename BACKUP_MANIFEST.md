# Backup Manifest

目的：明确哪些资产进入 Git、哪些走 iCloud/本地备份、哪些绝对不能上传，避免换机时断点，也避免隐私泄露。

## Git：应纳入版本控制

这些文件用于恢复系统能力，不应包含授权码、真实账户快照或完整个人资产明细。

- 核心脚本：`morning_brief.py`、`central_risk_board.py`、`system_health_check.py`、`collab_sync.py`
- 策略/研究脚本：V6、Radar、A股 Radar、估值辅助、健康检查相关 `.py`
- 迁移和运维文档：`MIGRATION_CHECKLIST.md`、`BACKUP_MANIFEST.md`、`README*.md`、`AI_HANDOFF_CURRENT.md`
- 事件源：`events_calendar.json`
- A股 Radar 观察样本：`investment_screener/radar_astock.json`
- 依赖清单：`requirements.txt`、子项目内 `requirements.txt`
- 配置模板：`*.example.json`、`*.example.yaml`、不含隐私的 policy/config 文件
- SOP/设计文档：A股 Radar、X Radar、Friend Alpha、Daily Board、V6 治理相关 Markdown

## iCloud / 本地备份：不进 Git，但必须迁移

这些内容包含个人投资资料、持仓、估值结论或日志。它们应由 iCloud、Time Machine、外置硬盘或加密备份迁移。

- `/Users/zhangkun/Desktop/AI个人投资公司`
- `交易决策日志/decision_log.csv`
- `朋友Alpha影子跟踪/friend_alpha_shadow_log.csv`
- `信息源扫描/X_Radar/daily/summaries/`
- `公司估值/`
- `26年阶段性组合策略计划.html`
- 税务原始文件、券商月结单、成交记录、持仓截图
- 大量回测输出：`backtest_results/`、`cash_alpha_v3_repo/backtest_results/`

## 手动恢复：本机状态，不可靠依赖 iCloud

这些项目通常不会被 Git 或 iCloud 完整恢复，换机后必须手动检查。

- Futu OpenD：安装、登录、开启 API、确认 `127.0.0.1:11111`
- 邮件授权码：`.ic_env.local`，至少包含 `IC_EMAIL_PASSWORD`
- Claude 命令：`/Users/zhangkun/.claude/commands/X扫描.md`
- Codex/Claude 本地配置与记忆
- `~/Library/LaunchAgents/*.plist`
- Python 环境和依赖包

## 禁止上传 Git

- `.ic_env.local`、`.env*`
- SMTP 授权码、API key、refresh token、secret、password
- Futu 真实账户号对应的账户快照、订单、持仓状态文件
- 税务原始文件、券商 statement、月结单
- 大型 PDF、HTML 报告、截图、缓存、临时文件
- `tmp_*`、`.claude/`、`.codex/`、`.isolated/`

## 换机验收

在新 Mac 恢复代码和资料后，进入仓库根目录执行：

```bash
python3 system_health_check.py
python3 system_health_check.py --deep
```

合格标准：

- `0 fail(s)`
- Futu OpenD warning 只有在 OpenD 未启动时允许存在
- V6 独立邮件变量 warning 只有在确认走 `IC_EMAIL_PASSWORD` fallback 时允许存在
