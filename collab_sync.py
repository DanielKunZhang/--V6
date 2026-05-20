#!/usr/bin/env python3
"""
AI 协作同步工具
用法：
  python collab_sync.py add-gpt "GPT说了什么"          # 追加 GPT 条目
  python collab_sync.py add-claude "Claude做了什么"    # 追加 Claude 条目（Claude 自用）
  python collab_sync.py today                          # 显示今日日志
  python collab_sync.py export                         # 输出适合上传给 GPT 的摘要
  python collab_sync.py export-current                 # 刷新唯一工作同步文件
  python collab_sync.py tag [决策|代码|发现|待办|风险]  # 指定类型（配合 add-* 使用）
"""

import sys
import os
import fcntl
from datetime import datetime

LOG_FILE = os.path.join(os.path.dirname(__file__), "AI_COLLAB_LOG.md")
HANDOFF_FILE = os.path.join(os.path.dirname(__file__), "AI_HANDOFF_CURRENT.md")
CURRENT_SYNC_FILE = os.path.join(os.path.dirname(__file__), "AI_WORK_SYNC_CURRENT.md")
DESKTOP_SYNC_SOURCE_FILE = "/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/2026-05-16_系统工作同步_给其他AI冷启动.md"
UNIFIED_GOAL_FILE = "/Users/zhangkun/Desktop/AI个人投资公司/系统优化升级依据/AI个人投资公司_统一目标与系统协同原则_20260520.md"
LOCK_FILE = os.path.join(os.path.dirname(__file__), ".ai_collab_log.lock")


def get_today_header():
    return f"## {datetime.now().strftime('%Y-%m-%d')}"


def get_timestamp():
    return datetime.now().strftime("%H:%M")


def read_log():
    if not os.path.exists(LOG_FILE):
        return ""
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return f.read()


def write_log(content):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(content)


def with_log_lock(fn):
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    with open(LOCK_FILE, "w", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def add_entry(source: str, tag: str, content: str):
    def update():
        log = read_log()
        today = get_today_header()
        source_header = f"### {source}"
        entry = f"- [{get_timestamp()}] [{tag}] {content}"

        if today not in log:
            # 新的一天，在文件末尾追加日期块
            log = log.rstrip() + f"\n\n---\n\n{today}\n\n{source_header}\n\n{entry}\n"
        elif source_header not in log.split(today)[-1]:
            # 今天存在但这个 source 还没有
            today_idx = log.rfind(today)
            insert_pos = log.find("\n---\n", today_idx)
            if insert_pos == -1:
                insert_pos = len(log)
            block = f"\n\n{source_header}\n\n{entry}"
            log = log[:insert_pos] + block + log[insert_pos:]
        else:
            # 今天的这个 source 已存在，追加条目
            today_section = log.split(today)[-1]
            source_idx = today_section.rfind(source_header)
            # 找到该 source 下最后一个条目之后插入
            after_source = today_section[source_idx:]
            # 找下一个 ### 或 --- 的位置
            next_section = -1
            for marker in ["\n### ", "\n---"]:
                pos = after_source.find(marker, len(source_header))
                if pos != -1 and (next_section == -1 or pos < next_section):
                    next_section = pos

            if next_section == -1:
                # 末尾直接追加
                log = log.rstrip() + f"\n{entry}\n"
            else:
                insert_at = len(log) - len(today_section) + source_idx + next_section
                log = log[:insert_at] + f"\n{entry}" + log[insert_at:]

        write_log(log)

    with_log_lock(update)
    print(f"✓ 已追加 [{source}] [{tag}] {content}")


def show_today():
    log = read_log()
    today = get_today_header()
    if today not in log:
        print(f"今日（{today}）暂无记录")
        return
    today_content = log.split(today)[-1]
    # 截取到下一个 --- 之前
    end = today_content.find("\n---\n")
    if end != -1:
        today_content = today_content[:end]
    print(f"{today}{today_content}")


def export_for_gpt():
    """输出适合上传给 GPT 的精简摘要（最近 3 天）"""
    log = read_log()
    lines = log.split("\n")
    output = ["# AI 协作摘要（供 GPT 读取）", ""]

    # 提取最近的日期块
    date_blocks = []
    current_block = []
    for line in lines:
        if line.startswith("## 20"):
            if current_block:
                date_blocks.append("\n".join(current_block))
            current_block = [line]
        elif line == "---" and current_block:
            date_blocks.append("\n".join(current_block))
            current_block = []
        else:
            current_block.append(line)
    if current_block:
        date_blocks.append("\n".join(current_block))

    # 取最近3天
    recent = date_blocks[-3:] if len(date_blocks) >= 3 else date_blocks
    output.extend(recent)

    result = "\n".join(output)
    export_path = os.path.join(os.path.dirname(__file__), "AI_COLLAB_EXPORT_FOR_GPT.md")
    with open(export_path, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"✓ 已导出至 {export_path}")
    print("  → 上传这个文件给 GPT 即可同步近期协作状态")
    return result


def recent_log_blocks(days: int = 3) -> str:
    log = read_log()
    lines = log.split("\n")
    date_blocks = []
    current_block = []
    for line in lines:
        if line.startswith("## 20"):
            if current_block:
                date_blocks.append("\n".join(current_block).strip())
            current_block = [line]
        elif line == "---" and current_block:
            date_blocks.append("\n".join(current_block).strip())
            current_block = []
        else:
            current_block.append(line)
    if current_block:
        date_blocks.append("\n".join(current_block).strip())
    recent = date_blocks[-days:] if len(date_blocks) >= days else date_blocks
    return "\n\n---\n\n".join(block for block in recent if block)


def read_text_if_exists(path: str, max_chars: int | None = None) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n\n...（后文略，详见原文件）"
    return text


def export_current_sync():
    """刷新唯一工作同步文件：给 GPT、Claude 或其他 AI 直接冷启动。"""
    handoff = read_text_if_exists(HANDOFF_FILE, max_chars=18000)
    unified_goal = read_text_if_exists(UNIFIED_GOAL_FILE, max_chars=8000)
    latest_system_sync = read_text_if_exists(DESKTOP_SYNC_SOURCE_FILE, max_chars=22000)
    recent_logs = recent_log_blocks(days=4)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = f"""# AI 工作同步 CURRENT

- Last updated: `{generated_at}`
- Canonical file: `{CURRENT_SYNC_FILE}`
- 用途：这是唯一对外同步文件。给 GPT、Claude 或任何新 AI 时，优先上传/读取这一份。

## 使用规则

- 新 AI 先读本文件，不需要同时打开完整聊天记录。
- `AI_COLLAB_LOG.md` 是底层流水账，本文件是当前可执行摘要。
- 每次重要工作结束后，运行：

```bash
python3 collab_sync.py export-current
```

- 如果新增重大决策，先写入 `AI_COLLAB_LOG.md`，再刷新本文件。
- 如果投资系统文档有新的主线进展，也应同步到本文件。

## 当前 AI 协作分工

- `GPT`：负责方向、边界、原则、优先级、最终判断，以及把用户真实目标函数制度化。
- `Claude`：更适合工程执行、跑数、报告生成、查错和批判性审查。
- `高层判断规则`：Claude 对“根本冲突 / 方向偏离 / 投资哲学冲突”等高层判断不能直接作为最终结论，必须回到用户目标函数和主从关系，由 GPT 侧做最终解释和制度化。
- `协作口径`：Claude 负责挑战系统风险；GPT 负责判断这些风险是否构成方向偏离；用户最终确认目标函数。

## 当前最新系统同步

### 统一目标与系统协同原则

{unified_goal or '暂无统一目标文件。'}

### 冷启动系统同步

{latest_system_sync or '暂无桌面系统同步文档。'}

---

## 当前 Handoff 快照

{handoff or '暂无 AI_HANDOFF_CURRENT.md。'}

---

## 最近协作日志

{recent_logs or '暂无近期协作日志。'}
"""
    with open(CURRENT_SYNC_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✓ 已刷新唯一工作同步文件：{CURRENT_SYNC_FILE}")
    print("  → 以后给其他 AI 直接上传/引用这个文件即可")
    return content


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]

    # 解析可选 tag
    tag = "发现"
    content_args = args[1:]
    if "--tag" in content_args:
        tag_idx = content_args.index("--tag")
        tag = content_args[tag_idx + 1]
        content_args = content_args[:tag_idx] + content_args[tag_idx + 2:]
    elif len(content_args) >= 2 and content_args[0] in ["决策", "代码", "发现", "待办", "风险"]:
        tag = content_args[0]
        content_args = content_args[1:]

    content = " ".join(content_args) if content_args else ""

    if cmd == "add-gpt":
        if not content:
            print("用法: python collab_sync.py add-gpt [类型] \"内容\"")
            return
        add_entry("GPT", tag, content)

    elif cmd == "add-claude":
        if not content:
            print("用法: python collab_sync.py add-claude [类型] \"内容\"")
            return
        add_entry("Claude", tag, content)

    elif cmd == "today":
        show_today()

    elif cmd == "export":
        export_for_gpt()

    elif cmd == "export-current":
        export_current_sync()

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
