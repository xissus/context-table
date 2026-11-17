# 接进豆包

豆包支持**自定义连接器**，类型里有 STDIO，所以能直接跑本地 MCP 服务。

> 豆包客户端迭代很快，菜单名可能微调。认「自定义连接器」这个入口就行，位置大同小异。

**但它没有配置文件。** 连接器存在 LevelDB 里（`%LOCALAPPDATA%\Doubao\User Data\Default\Local Storage\leveldb\`），
脚本改不了，也不该去改。所以这一步只能手动，大约 3 分钟。

---

## 前置

- 装的是**豆包桌面客户端**（不是网页版）
- **先登录**。不登录的话侧边栏是精简的，根本看不到连接器入口——这是第一个坑。
- 自定义连接器**只在本机生效**，云端环境用不了。

## 步骤

**1. 打开入口**

侧边栏 →「技能·连接器·伙伴」→「我的技能」→「连接器」→ 右上角「+ 新建」→「新建自定义连接器」

**2. 传输类型选 STDIO**

默认是 HTTP。本地跑进程必须选 **STDIO**，选了之后表单才会出现
「命令 / 参数 / 环境变量」三个框。

**3. 填三个值**

| 字段 | 填什么 |
|---|---|
| 名称 | `context-table` |
| 命令 | `<安装目录>\runtime\python.exe` 的**完整路径** |
| 参数 | `<安装目录>\server\main.py` 的**完整路径** |
| 环境变量 | `CONTEXT_TABLE_PATH=<你的表路径>\memory-table.md` |

例如（便携版解压在 `D:\context-table`）：

```
命令      D:\context-table\runtime\python.exe
参数      D:\context-table\server\main.py
环境变量  CONTEXT_TABLE_PATH=D:\context-table\memory-table.md
```

**命令一定写绝对路径。** GUI 客户端启动子进程时不继承你终端里的 PATH，
写 `python.exe` 大概率报「找不到」。

**4. 保存**

第一次保存如果提示「运行失败」，别急着重填。到「我的技能 → 连接器」里
点一下「重新启动」，多数情况就恢复——这是第二个坑，属于常态。

**5. 验证**

新建对话，问：

```
你有哪些 MCP 工具？
```

看到 `remember` / `brief` / `read` / `search` / `prune` 五个就是通了。

---

## 和另外三个平台的区别

| | 配置方式 | 能不能脚本自动化 |
|---|---|---|
| WorkBuddy | `~/.workbuddy/mcp.json` | 能（首次要点「信任」） |
| Codex / ChatGPT 桌面 | `~/.codex/config.toml` | 能 |
| DeepSeek Harness | `cordis.patch.yml` | 能 |
| **豆包** | **界面里点** | **不能，只能手点** |

所以安装脚本不会动豆包，它只会在最后打印这段步骤。

---

## 常见问题

**问：能不能直接把配置写进 LevelDB？**

不建议。那是 Chromium 的存储格式，格式一变整块数据就废，而且写坏了
豆包的连接器列表会全部丢失。手点三次比这划算得多。

**问：选 HTTP 行不行？**

不行。我们这个是 stdio 的本地进程，没有 HTTP 端口。选 HTTP 会连不上。

**问：手机上能用吗？**

不能。自定义连接器依赖本机进程，手机上没有。
