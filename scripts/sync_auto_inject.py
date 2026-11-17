#!/usr/bin/env python3
"""Synchronize the auto-injected memory rule.

AGENTS.md is the single source of truth. WorkBuddy needs MEMORY.md in its
workspace memory directory, while workbuddy/MEMORY.md is the distributable copy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "AGENTS.md"
TARGETS = (
    ROOT / "workbuddy" / "MEMORY.md",
    ROOT / ".workbuddy" / "memory" / "MEMORY.md",
    # DSH 的用户全局链：$DSH_HOME/AGENTS.md（或 ~/.dsh/AGENTS.md），所有工作区都生效
    Path.home() / ".dsh" / "AGENTS.md",
)


RULE_START = "<!-- context-table:rule:start -->"
RULE_END = "<!-- context-table:rule:end -->"


def upsert_block(target: Path, content: str, check: bool) -> bool:
    """把规则作为托管区块写进目标文件。返回是否发生了变更。"""
    block = f"{RULE_START}\n{content.strip()}\n{RULE_END}"
    text = target.read_text(encoding="utf-8-sig") if target.is_file() else ""

    if RULE_START in text and RULE_END in text:
        start = text.index(RULE_START)
        end = text.index(RULE_END) + len(RULE_END)
        new = text[:start] + block + text[end:]
    else:
        new = (text.rstrip() + "\n\n" + block + "\n") if text.strip() else block + "\n"

    if new == text:
        return False
    if not check:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new, encoding="utf-8", newline="\n")
        print(f"merged: {target}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="check without writing")
    parser.add_argument(
        "--append-to",
        action="append",
        default=[],
        metavar="PATH",
        help="把规则作为一个托管区块合并进这个 MEMORY.md（可多次指定）。"
             "不覆盖文件里已有的其它内容，重复执行只替换区块。",
    )
    args = parser.parse_args()

    if not SOURCE.is_file():
        print(f"missing source: {SOURCE}", file=sys.stderr)
        return 1
    content = SOURCE.read_text(encoding="utf-8-sig")
    stale: list[Path] = []
    for target in TARGETS:
        current = target.read_text(encoding="utf-8-sig") if target.is_file() else None
        if current != content:
            stale.append(target)
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
                print(f"updated: {target}")

    changed = [p for p in args.append_to if upsert_block(Path(p).expanduser(), content, args.check)]

    if args.check:
        if stale or changed:
            for t in stale:
                print(f"stale: {t}", file=sys.stderr)
            for t in changed:
                print(f"missing or stale block: {t}", file=sys.stderr)
            return 1
        print("auto-inject copies are in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())