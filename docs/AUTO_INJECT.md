# 规则怎么进上下文

> 目标：把「用户每次都要说『记一下』」变成「模型每轮自己看到规则」。

## 一、要解决的问题

MCP 工具只能由模型主动调用。用户不说「记一下」，`remember` 就不会被调，表就是空的。

所以需要一种**不依赖用户开口**的机制，让规则常驻在模型眼前。

## 二、各平台的自动加载点

| 平台 | 文件 | 加载时机 | 上限 |
|---|---|---|---|
| WorkBuddy | 用户级 `MEMORY.md`（`~/.workbuddy/user-<id>/`） | 每次开对话注入 | 4000 字 |
| Codex（含 ChatGPT 桌面） | 项目根 `AGENTS.md` | 每轮请求注入 | 未明确 |
| DeepSeek Harness | `AGENTS.md`（项目根或 `~/.dsh/` 全局链） | **每次 pre-step 探测，改了立刻生效** | 由 `@deepseek-ai/dsh-agent-instructions` 控制 |
| 豆包 | 无规则文件，靠连接器界面里的自定义说明 | 会话开始 | 未明确 |

### DSH 的机制细节

来自社区插件 `dsh-agents-md` 的说明，引用了官方包行为：

> The model-facing half is DSH's own workspace-instruction loader, `@deepseek-ai/dsh-agent-instructions`, which is part of the standard agent preset. It reads AGENTS.md from the project chain on the first request and **probes the instruction files on subsequent agent/pre-step boundaries**. When the saved file's version changes, it injects the updated instructions.

含义：**每次 pre-step 都探测文件版本，变了就重新注入。** 这比「每次开对话加载一次」更强——对话进行中改规则，下一轮立刻生效。

另有插件 `dsh-agents-section` 可把 `AGENTS.md` 渲染成独立的 system-prompt 段落（而不是作为 user message 注入），每次 prompt 组装都重新读盘。

## 三、统一规则文本

各平台放同一段内容，只改文件名。

```markdown
## 记忆规则（每轮执行，不要问用户）

每次回答结束前，自检这一轮有没有出现下面四种情况：

1. 用户做了一个决定
2. 出现新的事实（人名、数字、路径、时间）
3. 冒出新的待办
4. 排除了某个方案

有其中任何一条 → 直接调用 remember 存进去，不要问「要不要记」。
在回答最后用一行说明：已记：定了 ×1（工作）

没有 → 什么都不做，不要为了记而记。

如果这一轮你什么都没记，但用户后来又提起一件你本该知道的事，
说明你漏了 —— 立刻补记，并说明「补记：xxx」。
```

约 250 字，低于任何一处的上限。

## 四、分发结构

```
context-table/
├── AGENTS.md                 ← Codex + DSH 的唯一规则源
└── workbuddy/MEMORY.md       ← WorkBuddy 副本
```

一份内容，两个文件名。用脚本同步，不手工维护两套：

```bash
python scripts/sync_auto_inject.py           # 写入
python scripts/sync_auto_inject.py --check   # 只检查是否一致
```

测试会校验这几份副本完全一致、长度不超限、四个触发条件都在。

## 五、为什么这样能减少「靠人提醒」

| | 改之前 | 改之后 |
|---|---|---|
| 规则在哪 | 没人告诉模型 | 每轮自动注入 |
| 谁启动 | 用户说「记一下」 | 模型自检 |
| 用户角色 | 主动提醒 | 只纠错 |
| 用户忘了会怎样 | 这一段丢了 | 不影响 |

**关键差别：纠错比提醒容易。** 看到「已记：xxx」不对，说一句就行；但要求用户每轮都想起来「这里有结论该记」，几乎不可能持续。

## 六、边界

**1. 注入是硬的，遵守是软的。**
文件一定被加载，但模型是否照做是概率。WorkBuddy 的 `MEMORY.md` 进入系统提示，长对话里仍会被挤到中间区。

**2. 注意力衰减。**
Lost in the Middle（Liu et al., 2023）：信息在长上下文中间时利用率下降。规则写在开头，第 30 轮时距生成点已经很远。

**3. 做不到 100%。**
真正 100% 需要客户端 pre-turn hook（在模型看到用户消息之前强制注入）。四个平台都没有把这类 hook 开放给第三方插件。

**4. 三处内容会分叉。**
同一个规则写在多个文件里，改一处忘一处就会不一致。缓解办法就是上面的同步脚本——它把「记得手动改三处」变成一条命令，但不能替代人执行。

## 七、还没核实的地方

1. **Codex 的 `AGENTS.md` 作用范围**：项目根 + 所有子目录，还是只有当前工作目录？全局（`~/.codex/AGENTS.md`）是否支持？
2. **ChatGPT 桌面版是否读 `AGENTS.md`**：还是只有 Codex CLI 和 IDE 扩展读？桌面版可能只支持「自定义指令」。
3. **DSH 自定义 preset 是否一定挂载 `dsh-agent-instructions`**：插件文档说属于标准 preset，换了 preset 可能不加载。
4. **WorkBuddy 的 `MEMORY.md` 是每轮注入还是每次会话注入一次**：如果是每次会话一次，长对话里同样会衰减。

这几条按本机实测和官方文档推断，没做交叉验证。遇到不一致，以你机器上的实际行为为准。
