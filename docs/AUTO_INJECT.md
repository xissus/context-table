# 自动注入方案（三平台）

> 用途：评审。目标是把「用户每次都要说『记一下』」变成「模型每轮自动看到规则」。

## 一、要解决的问题

MCP 工具只能由模型主动调用。用户不说「记一下」，`remember` 就不会被调，表就是空的。

**用户的真实抱怨**：「说白了不还是我得去提醒他吗？我一忘那不就又失忆了。」

所以需要一种**不依赖用户开口**的机制，让规则每轮都在模型眼前。

## 二、三个平台各有自动注入点

| 平台 | 文件 | 加载时机 | 上限/限制 | 证据 |
|---|---|---|---|---|
| WorkBuddy | `.workbuddy/memory/MEMORY.md` | 每次开对话注入 | 3000 字（用户级 4000 字，超了截断） | 本机实测：`.workbuddy/memory/` 目录机制 |
| Codex（含 ChatGPT 桌面版） | `AGENTS.md`（项目根） | 每轮请求注入 | 未知 | 见下「待验证」 |
| DeepSeek Harness | `AGENTS.md`（项目根） | **每次 agent/pre-step 边界探测，改了立刻生效** | 由 `@deepseek-ai/dsh-agent-instructions` 控制 | 官方包 `@deepseek-ai/dsh-agent-instructions`，属标准 agent preset |

### DSH 的机制细节（已核实）

来自社区插件 `dsh-agents-md` 的说明，引用了官方包行为：

> The model-facing half is DSH's own workspace-instruction loader, `@deepseek-ai/dsh-agent-instructions`, which is part of the standard agent preset. It reads AGENTS.md from the project chain on the first request and **probes the instruction files on subsequent agent/pre-step boundaries**. When the saved file's version changes, it injects the updated instructions.

含义：**每次 pre-step 都探测文件版本，变了就重新注入。** 这比「每次开对话加载一次」更强——对话进行中改规则，下一轮立刻生效。

另有插件 `dsh-agents-section` 可把 `AGENTS.md` 渲染成独立的 system-prompt 段落（而不是作为 user message 注入），每次 prompt 组装都重新读盘。

## 三、统一规则文本

三处放同一段内容，只改文件名。

```markdown
## 记忆规则（每轮执行，不要问用户）

每次回答结束前，自检这一轮有没有出现下面四种情况：

1. 用户做了一个决定
2. 出现新的事实（人名、数字、路径、时间）
3. 冒出新的待办
4. 排除了某个方案

有其中任何一条 → 直接调用 remember 存进去，不要问「要不要记」。
在回答最后用一行说明：已记：定了 ×1（赛事）

没有 → 什么都不做，不要为了记而记。

如果这一轮你什么都没记，但用户后来又提起一件你本该知道的事，
说明你漏了 —— 立刻补记，并说明「补记：xxx」。
```

字数：约 300 字。远低于三处任何一处的上限。

## 四、分发结构

```
context-table/
├── AGENTS.md                    ← Codex + DSH 共用同一份
├── workbuddy/
│   └── MEMORY.md                ← 内容与 AGENTS.md 相同
└── ...
```

一份内容，两个文件名。**不维护两套。**

## 五、为什么这样能减少「靠人提醒」

| | 改之前 | 改之后 |
|---|---|---|
| 规则在哪 | 没人告诉模型 | 每轮自动注入 |
| 谁启动 | 用户说「记一下」 | 模型自检 |
| 用户角色 | 主动提醒 | 只纠错 |
| 用户忘了会怎样 | 这一段丢了 | 不影响 |

**关键差别：纠错比提醒容易。** 看到「已记：xxx」不对，说一句就行；但要求用户每轮都想起来「这里有结论该记」，几乎不可能持续。

## 六、局限（必须写清楚，不能包装成「已解决」）

**1. 注入是硬的，遵守是软的。**
文件一定被加载，但模型是否照做是概率。WorkBuddy 的 `MEMORY.md` 进入系统提示，长对话里仍会被挤到中间区。

**2. 注意力衰减。**
依据 Lost in the Middle（Liu et al., 2023）：信息在长上下文中间时利用率下降。规则写在开头，第 30 轮时距生成点已经很远。

**3. 做不到 100%。**
真正 100% 需要客户端 pre-turn hook（在模型看到用户消息之前强制注入）。三个平台都没有把这类 hook 开放给第三方插件。

**4. 三处内容会分叉。**
同一个规则写在两个文件里，改一处忘一处就会不一致。缓解办法：以 `AGENTS.md` 为准，`MEMORY.md` 只写一句「规则见 AGENTS.md」，但那样 WorkBuddy 就读不到了。这是真实取舍。

## 七、待验证清单（请评审指正）

以下几条我没有确凿证据，属于推断或部分证据：

1. **Codex 的 `AGENTS.md` 作用范围**：是「项目根 + 所有子目录」，还是只有当前工作目录？全局（`~/.codex/AGENTS.md`）是否支持？
2. **ChatGPT 桌面版是否也读 `AGENTS.md`**：还是只有 Codex CLI 和 IDE 扩展读？桌面版可能只支持「自定义指令」（Custom Instructions），那是另一套。
3. **DSH 标准 preset 是否默认挂载 `@deepseek-ai/dsh-agent-instructions`**：插件文档说「属于标准 agent preset」，但如果用户用了自定义 preset，可能不加载。
4. **WorkBuddy 的 `MEMORY.md` 是每轮注入还是每次会话注入一次**：如果是每次会话一次，长对话里同样会衰减。

## 八、请评审回答的问题

1. **这三处注入点是否准确？** 有没有第四个平台级的自动注入机制（比如某个客户端支持覆盖 system prompt 配置）？
2. **规则文本怎么写才能最大化遵守率？** 现在的写法是「四条自检 + 直接记 + 末尾标注」。有没有更有效的句式？（比如指令放在开头还是结尾、用不用编号、要不要给反例）
3. **「末尾标注已记」这个设计有没有副作用？** 它让用户能看见并纠错，但也让模型每轮多输出一行。会不会变成另一种噪音？
4. **三处内容分叉怎么解？** 现在要么重复维护，要么放弃某一个平台。
5. **有没有办法检测「模型这轮没遵守规则」？** 如果模型跳过了 `remember`，服务端不会知道这一轮发生过什么。有没有轻量的旁路验证？


## 九、本轮落地结果

已按本方案建立自动注入文件：

- `D:\context-table\AGENTS.md`：Codex 与 DSH 共用的唯一规则源。
- `D:\context-table\workbuddy\MEMORY.md`：WorkBuddy 分发副本。
- `D:\context-table\.workbuddy\memory\MEMORY.md`：WorkBuddy 项目内实际加载路径。

为避免“三处内容分叉”，新增：

```bash
python scripts/sync_auto_inject.py
python scripts/sync_auto_inject.py --check
```

`AGENTS.md` 是唯一源，另外两处由脚本同步。测试会检查三份内容完全一致、规则长度不超过 WorkBuddy 限制，并确认四个触发条件都存在。

当前规则正文 247 个字符，远低于 3000 字限制。自动注入只保证规则被加载，不保证模型一定遵守；这一点仍按第六节所述处理，不能宣传成 100% 可靠。
