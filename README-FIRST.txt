表格法 · 便携版
================

这个包里带着完整的 Python 运行时，你电脑上不用装 Python。

先看两件事
----------

1. **这个文件夹别删。** 你的记忆表 memory-table.md 就建在这里面，
   删了目录等于删了表（安装完可以把 zip 删掉，解压出来的目录留着）。

2. **先打开一次你要用的客户端**（WorkBuddy / Codex / DSH），让它把用户目录建出来，
   再回来双击 install.bat。没打开过的话，规则文件没地方放，会跳过。


使用步骤
--------

1. 解压到任意目录（路径可以带中文，但别放在 C:/Program Files 下，
   那里写文件需要管理员权限）

2. 双击 install\install.bat
   它会：建表 → 写三个客户端的配置 → 装规则文件
   已有的配置会跳过，不覆盖；改之前先备份

3. 重启你用到的客户端（WorkBuddy / Codex / DSH）

3.5 豆包要手动加（脚本改不了，它没有配置文件）：
   侧边栏「技能·连接器·伙伴」→ 新建自定义连接器 → 传输类型选 STDIO
   命令      <本目录>\runtime\python.exe
   参数      <本目录>\server\main.py
   环境变量  CONTEXT_TABLE_PATH=<本目录>\memory-table.md
   注意：先登录才能看到入口；命令要写完整路径；首次保存提示"运行失败"就点重新启动

4. WorkBuddy 里还要点一次「信任」：
   连接器 → 自定义连接器 → context-table → 信任
   只有它需要点，另外两个不用


怎么确认成了
------------

新开一个对话，说一句有结论的话，例如：

  这个项目以后只用本地文件，不走云同步。

回答末尾出现「已记：定了 ×1（工具）」就是通了。

再问一句「我们昨天聊了什么」，看它有没有先读表。表里没有昨天的记录时，
它应该说没有，而不是编一个。


怎么卸
------

1. 删掉三个配置文件里名为 context-table 的条目：
   %USERPROFILE%\.workbuddy\mcp.json
   %USERPROFILE%\.codex\config.toml
   %USERPROFILE%\.dsh\profiles\desktop\cordis.patch.yml
   （安装时都留了 .bak 备份，可以直接还原）

2. 删掉 %USERPROFILE%\.dsh\AGENTS.md 里被
   <!-- context-table:rule:start --> 包住的那一段

3. 豆包如果加过，要在界面里把那个自定义连接器删掉（没有配置文件可改）

4. 删除本目录（表在里面，确认不要了再删）

想看安装器会改什么、不改什么，用：
   install\install.bat -DryRun
