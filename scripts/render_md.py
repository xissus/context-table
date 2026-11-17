#!/usr/bin/env python3
"""把任意 Markdown 渲染成一页干净的 HTML，用来预览或录屏。

    python scripts/render_md.py <文件.md> [输出.html]
"""

from __future__ import annotations

import pathlib
import sys

import markdown

CSS = """
:root{
  --fg:#1f2328; --muted:#5b6570; --line:#e3e8ee; --bg:#fff;
  --head:#f7f9fb; --accent:#1a6b4f; --zebra:#fbfcfd;
}
*{box-sizing:border-box}
body{
  margin:0; padding:48px 24px 96px; background:#eef1f4; color:var(--fg);
  font:17px/1.75 -apple-system,"Segoe UI","Noto Sans SC","Microsoft YaHei",sans-serif;
}
.page{
  max-width:900px; margin:0 auto; background:var(--bg); padding:56px 64px 72px;
  border-radius:10px; box-shadow:0 1px 3px rgba(16,24,40,.06),0 12px 32px rgba(16,24,40,.08);
}
h1{font-size:30px;margin:0 0 8px;letter-spacing:-.01em}
h2{font-size:20px;margin:44px 0 6px;padding-bottom:10px;border-bottom:2px solid var(--line)}
h2:first-of-type{margin-top:32px}
h2 + p{margin-top:10px}
p{margin:10px 0}
a{color:var(--accent)}
strong{font-weight:600}
blockquote{
  margin:18px 0; padding:14px 20px; background:var(--head);
  border-left:4px solid var(--accent); border-radius:0 6px 6px 0; color:var(--muted);
  font-size:15.5px;
}
blockquote p{margin:4px 0; line-height:1.85; white-space:pre-line}
blockquote p + p{margin-top:14px; padding-top:13px; border-top:1px solid var(--line)}
blockquote strong{color:var(--fg)}
code{
  background:#f2f5f8; padding:.12em .42em; border-radius:4px;
  font-family:"Cascadia Code",Consolas,monospace; font-size:.88em; color:#9a3412;
}
hr{border:0;border-top:1px solid var(--line);margin:36px 0}
table{
  width:100%; border-collapse:separate; border-spacing:0; margin:14px 0 6px;
  font-size:15.5px; border:1px solid var(--line); border-radius:8px; overflow:hidden;
}
th{
  background:var(--head); text-align:left; font-weight:600; color:#39424e;
  padding:11px 16px; border-bottom:1px solid var(--line); white-space:nowrap;
}
td{padding:10px 16px; border-bottom:1px solid var(--line); vertical-align:top}
tr:last-child td{border-bottom:0}
tbody tr:nth-child(even) td{background:var(--zebra)}
td:first-child{white-space:nowrap; color:var(--muted); font-variant-numeric:tabular-nums}
"""


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("用法：render_md.py <文件.md> [输出.html]")
    src = pathlib.Path(sys.argv[1]).resolve()
    out = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src.with_suffix(".html")

    body = markdown.markdown(
        src.read_text(encoding="utf-8-sig"),
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    out.write_text(
        f'<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        f"<title>{src.stem}</title><style>{CSS}</style>"
        f'<div class="page">{body}</div></html>',
        encoding="utf-8",
    )
    print("已生成", out)


if __name__ == "__main__":
    main()
