# Mac Migration Checklist

目的：换新 Mac 后，尽快恢复投资系统的可用性，避免 Daily Board、X Radar、V6、邮件、Futu、复盘路由出现隐性断点。

## 迁移原则

- 唯一正式代码仓库：`/Users/zhangkun/WorkBuddy/程序化/量化程序`
- 唯一正式事件源：`/Users/zhangkun/WorkBuddy/程序化/量化程序/events_calendar.json`
- 核心资料目录：`/Users/zhangkun/Desktop/AI个人投资公司`
- Daily Board 唯一入口：`morning_brief.py` / `central_risk_board.py`
- X Radar 只写永久 summary 和必要的事件增量，不替代 Daily Board。

## 换机前

1. 确认代码仓库已备份。
   - 首选 Git 远端。
   - 次选完整复制 `/Users/zhangkun/WorkBuddy/程序化/量化程序`。

2. 确认资料目录已同步。
   - iCloud Desktop/Documents 开启时，检查 `/Users/zhangkun/Desktop/AI个人投资公司` 是否完整。
   - 重点检查：`交易决策日志/`、`公司估值/`、`信息源扫描/X_Radar/`、`朋友Alpha影子跟踪/`、`26年阶段性组合策略计划.html`。

3. 备份本机私有配置。
   - `/Users/zhangkun/WorkBuddy/程序化/量化程序/.ic_env.local`
   - `/Users/zhangkun/.claude/commands/X扫描.md`
   - 其他 Claude/Codex 自定义命令或记忆。

4. 记录自动化任务。
   - `~/Library/LaunchAgents/`
   - 仓库内 `launchd/` 和 `launch_agents/`。

5. 记录外部软件。
   - Futu OpenD：需安装、登录、开启 API，默认端口 `11111`。
   - Python 3：建议使用与旧机器一致的主版本。

## 新机恢复

1. 恢复代码仓库到相同路径。
   - 推荐路径仍为 `/Users/zhangkun/WorkBuddy/程序化/量化程序`。
   - 如果新 Mac 用户名不是 `zhangkun`，需要优先做路径参数化，否则绝对路径会断。

2. 安装 Python 依赖。
   - `python3 -m pip install -r requirements.txt`
   - 如使用子项目，再分别检查 `cash_alpha_v3_repo/requirements.txt`、`tax_calc_v1/requirements.txt`。

3. 恢复私有环境变量。
   - 将 `.ic_env.local` 放回仓库根目录。
   - 至少包含邮件授权码相关变量，例如 `IC_EMAIL_PASSWORD`。
   - 如使用 V6 独立邮件配置，恢复 `V6_EMAIL_*`。

4. 恢复 Claude/Codex 命令。
   - 确认 `/Users/zhangkun/.claude/commands/X扫描.md` 存在。
   - 确认命令内写入的是 WorkBuddy 下的 `events_calendar.json`，不是 Desktop 下的同名文件。

5. 恢复 Futu OpenD。
   - 安装富途牛牛 / Futu OpenD。
   - 登录。
   - 开启 OpenD API。
   - 确认 `127.0.0.1:11111` 可连接。

6. 恢复 launchctl 自动化。
   - 先不要直接全量加载。
   - 逐个确认 plist 里的路径仍正确。
   - 确认后再复制到 `~/Library/LaunchAgents/` 并 `launchctl bootstrap`。

## 新机验收

在仓库根目录执行：

```bash
python3 system_health_check.py
```

需要更深检查时执行：

```bash
python3 system_health_check.py --deep
```

最低验收标准：

- `events_calendar.json` 存在且 JSON 合法。
- Desktop 资料目录存在。
- `morning_brief.py --no-email` 可运行。
- `X扫描.md` 存在且指向正式事件源。
- `.ic_env.local` 存在，邮件变量可读取。
- Futu OpenD 如需要自动化交易/实时报价，端口检查通过。

## 已知高风险点

- 代码中仍有多处 `/Users/zhangkun/Desktop/AI个人投资公司` 绝对路径。
- `~/.claude`、`~/.codex`、`~/Library/LaunchAgents` 不属于代码仓库，iCloud 不一定完整迁移。
- Python 虚拟环境不建议迁移，应在新机重新安装依赖。
- Futu OpenD、邮件授权码、launchctl 权限属于本机状态，必须重配。

