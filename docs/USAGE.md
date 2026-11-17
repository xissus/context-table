# 使用说明

> 三个平台，一套规则，一张表。

## 一句话原理

规则通过**自动加载的文件**进入模型上下文，模型自己判断该记什么，调用 MCP 工具写进同一张表。

```
AGENTS.md / MEMORY.md    → 规则（自动加载，不用你提醒）
memory-table.md          → 数据（唯一一张表）
MCP server (5 个工具)    → 读写表
```

**规则文件存规则，表存数据，两者不能混。**

## 三平台对照

| 平台 | 规则文件 | 自动加载时机 | 状态 |
|---|---|---|---|
| WorkBuddy | 用户级 `MEMORY.md` | 每次开对话 | ✅ 已通，实测写入成功 |
| Codex（含 ChatGPT 桌面） | 项目根 `AGENTS.md` | 每轮请求 | ⚠️ 配置已加，待重启验证 |
| DeepSeek Harness | 项目根 `AGENTS.md` | **每步探测，改了立刻生效** | ⚠️ 需先装 MCP 插件 |

## 日常怎么用

**什么都不用做。**

正常聊天，模型在回答末尾会带一行：

```
已记：定了 ×1（工具）
```

觉得记错了，说一句「那条删掉」或「改成 60G」。

## 想看表里有什么

| 说法 | 触发什么 |
|---|---|
| 「读一下记忆表」 | `read` 全读（≤150 条时） |
| 「翻一下之前关于 X 的」 | `search` 关键词检索 |
| 「把这一轮的状态简单说说」 | `brief` 底表 + 最近 3 天 |

## 三个平台分别怎么配

### WorkBuddy（已完成）

```
用户级 MEMORY.md：%USERPROFILE%\.workbuddy\user-8053c000-...\MEMORY.md
MCP 配置：      %USERPROFILE%\.workbuddy\mcp.json
状态：          已批准（mcp-approvals.json 有记录），5 个工具启用
```

规则区块由 `scripts/sync_auto_inject.py` 维护：

```bash
python D:\context-table\scripts\sync_auto_inject.py ^
  --append-to "%USERPROFILE%\.workbuddy\user-8053c000-039c-4a2f-ae2c-00ae1bdf3ea9-personal\MEMORY.md"
```

### Codex / ChatGPT 桌面

**配置已写入** `%USERPROFILE%\.codex\config.toml`：

```toml
[mcp_servers.context-table]
command = 'D:/Python/python.exe'
args = ['<仓库目录>/server/main.py']
startup_timeout_sec = 30
tool_timeout_sec = 60
env = { CONTEXT_TABLE_PATH = '<你的表路径>/memory-table.md', PYTHONIOENCODING = 'utf-8' }
```

**规则文件**：`AGENTS.md` 放项目根。当前已放到 `<你的项目目录>\`。

**要做的**：重启 Codex，看 `codex mcp list` 里有没有 `context-table`。

**注意**：Codex 读的是**当前项目根**的 `AGENTS.md`。换项目要复制一份过去。

### DeepSeek Harness

**不用装插件。** `@deepseek-ai/dsh-mcp-client` 是随应用内置的（新版 DSH 都有），
只要在 `%USERPROFILE%\.dsh\profiles\desktop\cordis.patch.yml` 末尾加一条：

```yaml
- insert:
    - id: mcp-context-table
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: context_table
        transport: stdio
        command: 'D:/Python/python.exe'
        args: ['<仓库目录>/server/main.py']
        env:
          CONTEXT_TABLE_PATH: '<你的表路径>/memory-table.md'
          PYTHONIOENCODING: 'utf-8'
```

三个坑：

- **必须用 `insert:` 包裹**。直接写 `- id: ...` 会被当成"覆盖已有条目"，id 不存在就整条丢弃，日志里只有一句 `patch: entry "..." not found`，界面上完全看不出来。

- **`serverName` 用下划线**，不要用连字符。带连字符会被 DSH 的函数名规范化改成带哈希的名字。
- **别再往 profile 里 `pnpm add` 这个包**。装了反而会挡住内置版本，因为它的 peer 依赖在 profile 里解析不到。

**规则文件**：写 `%USERPROFILE%\.dsh\AGENTS.md`，这是用户全局链，所有工作区都生效。

## 排错

| 现象 | 查什么 |
|---|---|
| 没有「已记」 | 规则文件加载了吗？新对话里问「你能看到记忆规则吗」 |
| 有「已记」但表没变 | 工具没接上，查 MCP 是否启用 |
| 表变了但日期格式不对 | `detect_date_fmt` 会跟随表内既有格式，检查表里是不是混了两种 |
| 记重复了 | `remember` 会拦完全重复；语义重复拦不住，要人工删 |
| 想撤销上一次写入 | `python server/main.py undo --table <表路径>` |

## 一条不能忘的

**表只有一个。** 不管在哪个平台、哪个工作区，`CONTEXT_TABLE_PATH` 都指向同一个文件。

所以三个客户端写的是同一张表，不会各记各的。
