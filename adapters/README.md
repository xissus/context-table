# Context Table Adapter

## Codex

Use `adapters/codex/context-table/` as a Codex skill. It contains a validated `SKILL.md` and UI metadata.

## WorkBuddy

Paste `adapters/workbuddy/INSTRUCTIONS.md` into the platform's persistent instruction or custom-rule area. The exact rule-file format varies by WorkBuddy version, so no unverified native bundle format is claimed here.

## DeepSeek Harness

Paste `adapters/dsh/INSTRUCTIONS.md` into the system prompt or persistent project instruction. If the harness has a tool allowlist, enable the context-table MCP tools.

## Shared limit

No adapter can force a tool call before every model turn. A reliable pre-turn read requires a host hook or a middleware that injects `brief()` output. Without it, these adapters only raise compliance probability.