# 使用说明

> 四个平台，一套规则，一张表。

## 一句话原理

规则通过**自动加载的文件**进入模型上下文，模型自己判断该记什么，调用 MCP 工具写进同一张表。

```
AGENTS.md / MEMORY.md    → 规则（自动加载，不用你提醒）
memory-table.md          → 数据（唯一一张表）
MCP server（5 个工具）    → 读写表
```

**规则文件存规则，表存数据，两者不能混。**

## 平台对照

| 平台 | 规则文件 | 自动加载时机 | 状态 |
|---|---|---|---|
| WorkBuddy | 用户级 `MEMORY.md` | 每次开对话 | ✅ 实测读写通过 |
| Codex（含 ChatGPT 桌面） | 项目根 `AGENTS.md` | 每轮请求 | ✅ 实测读写通过 |
| DeepSeek Harness | `AGENTS.md`（项目根或 `~/.dsh/`） | 每次 pre-step 探测 | ✅ 实测读写通过 |
| 豆包 | 界面里填，无文件 | 会话开始 | ⚠️ 未实机验证 |

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

## 手动配置

安装脚本会自动写这些。想自己配、或者脚本没覆盖到你的客户端，照下面来。

路径里的 `<仓库目录>`、`<表路径>`、`<你的 Python>` 换成自己的。

### WorkBuddy

MCP 配置写在 `~/.workbuddy/mcp.json`，规则写在用户级 `MEMORY.md`：

```bash
python <仓库目录>/scripts/sync_auto_inject.py --append-to \
  "<你的用户目录>/.workbuddy/user-<id>/MEMORY.md"
```

首次连上后，在连接器列表里给 `context-table` 点一次「信任」。

### Codex / ChatGPT 桌面

`~/.codex/config.toml`：

```toml
[mcp_servers.context-table]
command = '<你的 Python>'
args = ['<仓库目录>/server/main.py']
startup_timeout_sec = 30
tool_timeout_sec = 60
env = { CONTEXT_TABLE_PATH = '<表路径>/memory-table.md', PYTHONIOENCODING = 'utf-8' }
```

规则文件 `AGENTS.md` 放**当前项目根**。Codex 只读当前工作目录的，换项目要复制一份过去。

改完重启 Codex，`codex mcp list` 里能看到 `context-table` 就算接上了。

### DeepSeek Harness

**不用装插件。** `@deepseek-ai/dsh-mcp-client` 随应用内置，只要在
`~/.dsh/profiles/desktop/cordis.patch.yml` 末尾加一条：

```yaml
- insert:
    - id: mcp-context-table
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: context_table
        transport: stdio
        command: '<你的 Python>'
        args: ['<仓库目录>/server/main.py']
        env:
          CONTEXT_TABLE_PATH: '<表路径>/memory-table.md'
          PYTHONIOENCODING: 'utf-8'
```

三个坑：

- **必须用 `insert:` 包裹**。直接写 `- id: ...` 会被当成"覆盖已有条目"，id 不存在就整条丢弃，日志里只有一句 `patch: entry "..." not found`，界面上完全看不出来。
- **`serverName` 用下划线**，不要用连字符。带连字符会被 DSH 的函数名规范化改成带哈希的名字。
- **别再往 profile 里 `pnpm add` 这个包**。装了反而会挡住内置版本，因为它的 peer 依赖在 profile 里解析不到。

规则文件写 `~/.dsh/AGENTS.md`，那是全局链，所有工作区都生效。

### 豆包

没有配置文件，只能在界面里点，见 [`../adapters/doubao/INSTRUCTIONS.md`](../adapters/doubao/INSTRUCTIONS.md)。

## 排错

| 现象 | 查什么 |
|---|---|
| 没有「已记」 | 规则文件加载了吗？新对话里问「你能看到记忆规则吗」 |
| 有「已记」但表没变 | 工具没接上，查 MCP 是否启用 |
| 表变了但日期格式不对 | `detect_date_fmt` 会跟随表内既有格式，检查表里是不是混了两种 |
| 记重复了 | `remember` 会拦完全重复；语义重复拦不住，要人工删 |
| 想撤销上一次写入 | `python server/main.py undo --table <表路径>` |
| 提示话题不在允许列表 | 看 `CONTEXT_TABLE.md` 的 `topics:` 行，或环境变量 `CONTEXT_TABLE_TOPICS` |

## 一条不能忘的

**表只有一个。** 不管在哪个平台、哪个工作区，`CONTEXT_TABLE_PATH` 都指向同一个文件。

所以这几个客户端写的是同一张表，不会各记各的。
