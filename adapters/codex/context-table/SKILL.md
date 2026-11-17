---
name: context-table
description: Maintain and consult a local Markdown memory table during long, multi-turn tasks. Use when an MCP context-table server is available and the task depends on prior decisions, facts, open todos, or rejected options.
---

# Context Table

Use the external memory table instead of assuming prior-turn context survived.

## Start of each user turn

- For a long task, call `brief(profile="standard")` before answering when the answer may depend on prior user-specific state.
- In a known continuation or cost-sensitive short loop, `brief(profile="minimal")` is enough.
- Skip memory only when the request is fully self-contained. If unsure, read.
- Never claim you read memory if the tool was not called. Tool use is model-controlled; there is no automatic pre-turn injection.

## Locate information

1. Use `search(query=..., topic=...)` before broad reads.
2. Treat search output as candidates, not proof of absence.
3. If search returns a full-table fallback for a small table, use it.
4. Use `read(topic=...)` to inspect a topic; set `include_archive=True` when old history may matter.

## Write

- Record a conclusion as soon as it is stable, not at the end of the session.
- Use only the topics declared in the table's `topics:` line (default: 工作 / 学习 / 生活 / 人际 / 工具 / 方法). Never invent a seventh.
- Decisions and rejected options require a concrete `why`.
- Do not write conversational narration or duplicate an existing row.
- For an ambiguous section or topic, ask the user instead of guessing.

## Maintain

- `prune()` only reports; it never deletes.
- Archiving runs only with two explicit switches: `prune(dry_run=False, execute_archive=True)`.
- Archiving is non-destructive and remains searchable. Never describe it as deletion.
- For a malformed table or a bad write, use the CLI: `python server/main.py validate` or `python server/main.py undo`. These are not MCP tools and do not appear in the tool list.

## Boundary

This table reduces cross-turn factual loss and factual mistakes. It does not fix reasoning, arithmetic, interpretation errors, or skipped tool calls.