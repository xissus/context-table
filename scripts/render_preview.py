#!/usr/bin/env python3
"""把仓库里的 Markdown 渲染成一个带侧边栏的预览页。

用法：
    python scripts/render_preview.py            # 输出到 dist/preview.html
    python scripts/render_preview.py out.html

依赖：pip install markdown
"""

from __future__ import annotations

import html
import pathlib
import sys

import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent

DOCS = [
    ("README", "README.md"),
    ("核心规则", "CONTEXT_TABLE.md"),
    ("架构", "ARCHITECTURE.md"),
    ("使用说明", "docs/USAGE.md"),
    ("规则自动注入", "docs/AUTO_INJECT.md"),
    ("豆包接入", "adapters/doubao/INSTRUCTIONS.md"),
    ("平台说明", "adapters/README.md"),
]

CSS = """
:root{--fg:#1f2328;--muted:#59636e;--line:#d1d9e0;--bg:#fff;--code:#f6f8fa;--accent:#0969da}
*{box-sizing:border-box}
body{margin:0;font:16px/1.7 -apple-system,"Segoe UI","Noto Sans SC",sans-serif;color:var(--fg);background:#f6f8fa}
.wrap{display:flex;max-width:1240px;margin:0 auto;background:var(--bg);min-height:100vh}
nav{width:230px;flex:0 0 230px;padding:26px 16px;border-right:1px solid var(--line);position:sticky;top:0;height:100vh;overflow:auto;background:#fbfcfd}
nav h4{margin:0 0 14px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
nav a{display:block;padding:6px 10px;margin-bottom:2px;color:var(--fg);text-decoration:none;border-radius:6px;font-size:14px}
nav a:hover{background:#eef2f6;color:var(--accent)}
main{flex:1;min-width:0;padding:40px 52px 90px}
section{padding-bottom:44px;margin-bottom:44px;border-bottom:1px solid var(--line)}
section:last-child{border:0}
h1{font-size:28px;margin:0 0 18px;padding-bottom:10px;border-bottom:1px solid var(--line)}
h2{font-size:21px;margin:34px 0 14px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:17px;margin:24px 0 10px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
blockquote{margin:14px 0;padding:2px 16px;color:var(--muted);border-left:3px solid var(--line)}
code{background:var(--code);padding:.15em .4em;border-radius:5px;font-size:.88em;font-family:ui-monospace,Consolas,monospace}
pre{background:var(--code);padding:14px 16px;border-radius:8px;overflow:auto;line-height:1.5}
pre code{background:none;padding:0;font-size:13px}
table{border-collapse:collapse;width:100%;margin:16px 0;font-size:14.5px}
th,td{border:1px solid var(--line);padding:8px 12px;text-align:left;vertical-align:top}
th{background:#f6f8fa;font-weight:600}
tr:nth-child(even) td{background:#fcfdfe}
hr{border:0;border-top:1px solid var(--line);margin:28px 0}
.badge{display:inline-block;font-size:12px;color:var(--muted);border:1px solid var(--line);border-radius:99px;padding:1px 9px;margin-left:8px;vertical-align:middle}
"""


def render() -> str:
    parts, navs = [], []
    for title, rel in DOCS:
        path = ROOT / rel
        if not path.is_file():
            continue
        body = markdown.markdown(
            path.read_text(encoding="utf-8"),
            extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
        )
        anchor = f"doc-{len(parts)}"
        navs.append(f'<a href="#{anchor}">{html.escape(title)}</a>')
        parts.append(f'<section id="{anchor}"><div class="badge">{rel}</div>{body}</section>')

    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>context-table 预览</title><style>{CSS}</style></head>"
        f'<body><div class="wrap"><nav><h4>文档</h4>{"".join(navs)}</nav>'
        f'<main>{"".join(parts)}</main></div></body></html>'
    )


def main() -> int:
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "preview.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    print(f"已生成 {out}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
