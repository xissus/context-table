#!/usr/bin/env python3
"""context-table MCP server.

把记忆从模型脑子里挪到一张 Markdown 表上。规则定义在
CONTEXT_TABLE.md 的 frontmatter 里；本文件只实现通用读写与检索机制。
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

# mcp 2.x 把 FastMCP 改名为 MCPServer，两个版本都兼容
try:
    from mcp.server.mcpserver import MCPServer as _Server   # mcp >= 2
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as _Server   # mcp 1.x
    except ImportError:  # pragma: no cover
        print("缺少 mcp 包：pip install mcp", file=sys.stderr)
        sys.exit(1)

DEFAULT_COLUMNS = ["定了", "事实", "待办", "否了", "底表"]
DEFAULT_TOPICS = ["赛事", "人际", "工具", "学习", "方法", "生活"]

SECTION_NUM = {
    "定了": "一、定了",
    "事实": "二、事实",
    "待办": "三、待办",
    "否了": "四、否了",
    "底表": "五、底表",
}

TEMPLATE = """# 记忆表

> 话题只用六个：赛事 人际 工具 学习 方法 生活

## 一、定了

| 日期 | 话题 | 决定了什么 | 为什么 |
|---|---|---|---|

## 二、事实

| 记录日 | 话题 | 事实 | 备注 |
|---|---|---|---|

## 三、待办

| 日期 | 话题 | 要做什么 | 卡在哪 |
|---|---|---|---|

## 四、否了

| 日期 | 话题 | 否掉了什么 | 原因 |
|---|---|---|---|

## 五、底表

| 加入日 | 原则 |
|---|---|
"""

SMALL_TABLE = 150
STANDARD_RECENT_DAYS = 3
READ_RECENT_DAYS = 14
LOCK_TIMEOUT_SECONDS = 5.0
BACKUP_LIMIT = 50


# ---------------- 配置 ----------------

def find_table() -> Path:
    """表文件路径：--table 参数 > CONTEXT_TABLE_PATH 环境变量 > 当前目录 memory-table.md"""
    for i, arg in enumerate(sys.argv):
        if arg == "--table" and i + 1 < len(sys.argv):
            return Path(sys.argv[i + 1]).expanduser().resolve()
        if arg.startswith("--table="):
            return Path(arg.split("=", 1)[1]).expanduser().resolve()
    env = os.environ.get("CONTEXT_TABLE_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "memory-table.md").resolve()


def find_archive(table_path: Path) -> Path:
    """归档文件路径。默认与主表同目录，后缀为 -archive.md。"""
    env = os.environ.get("CONTEXT_TABLE_ARCHIVE_PATH")
    if env:
        return Path(env).expanduser().resolve()
    suffix = table_path.suffix or ".md"
    return table_path.with_name(f"{table_path.stem}-archive{suffix}")


def find_alias_file(table_path: Path) -> Path:
    """可选别名文件，一行一组，用 = 分隔同义说法。"""
    env = os.environ.get("CONTEXT_TABLE_ALIASES")
    if env:
        return Path(env).expanduser().resolve()
    suffix = table_path.suffix or ".md"
    return table_path.with_name(f"{table_path.stem}-aliases{suffix}")


def load_rules() -> tuple[list[str], list[str]]:
    """从 CONTEXT_TABLE.md 的 frontmatter 读列名和话题。找不到就用默认值。"""
    here = Path(__file__).resolve().parent.parent / "CONTEXT_TABLE.md"
    for p in (here, Path.cwd() / "CONTEXT_TABLE.md"):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
        if not m:
            continue
        cols, topics = DEFAULT_COLUMNS[:], DEFAULT_TOPICS[:]
        for line in m.group(1).splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = [x.strip() for x in val[1:-1].split(",") if x.strip()]
                if key == "columns" and items:
                    cols = items
                elif key == "topics" and items:
                    topics = items
        return cols, topics
    return DEFAULT_COLUMNS[:], DEFAULT_TOPICS[:]


COLUMNS, TOPICS = load_rules()


# ---------------- 文件安全 ----------------

@contextlib.contextmanager
def table_lock(path: Path) -> Iterator[None]:
    """跨进程锁。锁文件与表在同一目录，不依赖第三方库。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")

    # Windows 上新建的锁文件可能被杀软/索引器短暂占用，open 会抛 PermissionError。
    # 这不是逻辑错误，重试几次就好，别让它冒泡成写入失败。
    fh = None
    open_deadline = time.monotonic() + 5.0
    while fh is None:
        try:
            fh = lock_path.open("a+b")
        except PermissionError:
            if time.monotonic() >= open_deadline:
                raise
            time.sleep(0.05)

    with fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
        acquired = False
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        try:
            while not acquired:
                try:
                    fh.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    else:  # pragma: no cover - 在 Linux/macOS 上执行
                        import fcntl
                        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"等待文件锁超时：{lock_path}")
                    time.sleep(0.05)
            yield
        finally:
            if acquired:
                try:
                    fh.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                    else:  # pragma: no cover
                        import fcntl
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass


def atomic_write(path: Path, text: str) -> None:
    """同目录临时文件 + os.replace，避免写一半留下坏表。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        last_error = None
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                last_error = None
                break
            except PermissionError as exc:
                # Windows 搜索索引或同步软件可能短暂占用目标文件。
                last_error = exc
                if attempt == 9:
                    break
                time.sleep(0.05 * (attempt + 1))
        if last_error is not None:
            raise last_error
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def backup_dir(path: Path) -> Path:
    return path.parent / ".context-table-backups"


def backup_file(path: Path) -> Path | None:
    if not path.is_file():
        return None
    target_dir = backup_dir(path)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    target = target_dir / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, target)
    backups = sorted(target_dir.glob(f"{path.name}.*.bak"), key=lambda p: p.name)
    for old in backups[:-BACKUP_LIMIT]:
        old.unlink(missing_ok=True)
    return target


def read_table(path: Path) -> str:
    if not path.is_file():
        atomic_write(path, TEMPLATE)
        return TEMPLATE
    return path.read_text(encoding="utf-8-sig")


# ---------------- 表格解析 ----------------

def section_bounds(lines: list[str], section: str) -> tuple[int, int] | None:
    """返回该小节的 (标题行号, 结束行号)。标题层级 2~4 都认。"""
    title = SECTION_NUM.get(section, section)
    head = None
    for i, ln in enumerate(lines):
        if re.match(rf"^#{{2,4}}\s*{re.escape(title)}", ln.strip()):
            head = i
            break
    if head is None:
        for i, ln in enumerate(lines):
            if re.match(rf"^#{{2,4}}\s*{re.escape(section)}", ln.strip()):
                head = i
                break
    if head is None:
        return None
    tail = len(lines)
    for j in range(head + 1, len(lines)):
        if re.match(r"^#{1,4}\s", lines[j]):
            tail = j
            break
    return head, tail


def split_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c or "--") for c in cells)


@dataclass
class SectionTable:
    header: list[str]
    rows: list[list[str]]
    row_lines: list[int]
    separator_line: int


def section_table(text: str, section: str) -> SectionTable | None:
    lines = text.split("\n")
    bounds = section_bounds(lines, section)
    if not bounds:
        return None
    head, tail = bounds
    pipe_lines: list[tuple[int, list[str]]] = []
    for i in range(head + 1, tail):
        stripped = lines[i].strip()
        if stripped.startswith("|"):
            pipe_lines.append((i, split_cells(stripped)))
    if len(pipe_lines) < 2:
        return None
    _, header = pipe_lines[0]
    sep_idx, sep_cells = pipe_lines[1]
    if not is_separator(sep_cells):
        return None
    rows = [cells for _, cells in pipe_lines[2:] if any(cells)]
    row_lines = [idx for idx, cells in pipe_lines[2:] if any(cells)]
    return SectionTable(header=header, rows=rows, row_lines=row_lines, separator_line=sep_idx)


def parse_rows(text: str, section: str) -> list[list[str]]:
    """返回该小节表格的数据行（不含表头和分隔行）。"""
    table = section_table(text, section)
    return table.rows if table else []


def insert_row(text: str, section: str, row: str) -> str | None:
    table = section_table(text, section)
    if table is None:
        return None
    lines = text.split("\n")
    insert_at = table.row_lines[-1] + 1 if table.row_lines else table.separator_line + 1
    lines.insert(insert_at, row)
    return "\n".join(lines)


def format_rows(rows: list[list[str]]) -> str:
    return "\n".join("| " + " | ".join(r) + " |" for r in rows)


def format_table(table: SectionTable) -> str:
    sep = "|" + "|".join("---" for _ in table.header) + "|"
    return "\n".join([
        "| " + " | ".join(table.header) + " |",
        sep,
        format_rows(table.rows),
    ])


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value)).casefold().strip()


def norm_date(s: str) -> date | None:
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", s)
    if m:
        today = date.today()
        try:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
        if d > today + timedelta(days=1):
            d = d.replace(year=today.year - 1)
        return d
    return None


def detect_date_fmt(text: str) -> str:
    """看表里已有日期用的是 YYYY-MM-DD 还是 MM-DD，新行跟着走。"""
    samples = []
    for sec in COLUMNS:
        for r in parse_rows(text, sec)[:3]:
            if r and r[0]:
                samples.append(r[0].strip())
    if not samples:
        return "full"
    full = sum(1 for x in samples if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", x))
    return "full" if full * 2 >= len(samples) else "short"


def validate_table(text: str, sections: list[str] | None = None) -> tuple[list[str], list[str]]:
    """返回 (错误, 警告)。错误会阻止写入，警告只提示。"""
    errors: list[str] = []
    warnings: list[str] = []
    seen: dict[tuple[str, ...], int] = {}
    for sec in (sections if sections is not None else COLUMNS):
        table = section_table(text, sec)
        if table is None:
            errors.append(f"缺少或无法解析「{sec}」小节及其 Markdown 表格")
            continue
        for idx, row in enumerate(table.rows, start=1):
            if len(row) != len(table.header):
                errors.append(f"「{sec}」第 {idx} 行有 {len(row)} 格，表头是 {len(table.header)} 格")
            d = norm_date(row[0] if row else "")
            if d is None:
                errors.append(f"「{sec}」第 {idx} 行日期无法解析：{row[0] if row else '空'}")
            if sec != "底表":
                topic = row[1] if len(row) > 1 else ""
                if topic not in TOPICS:
                    errors.append(f"「{sec}」第 {idx} 行话题不在允许列表：{topic or '空'}")
            key = (sec,) + tuple(normalize_text(c) for c in row)
            if key in seen:
                warnings.append(f"「{sec}」第 {idx} 行与第 {seen[key]} 行完全相同")
            else:
                seen[key] = idx
    return errors, warnings


def count_entries(text: str) -> int:
    return sum(len(parse_rows(text, c)) for c in COLUMNS)
# ---------------- 条目组织 ----------------

@dataclass
class Entry:
    source: str
    section: str
    row: list[str]
    header: list[str]
    line_no: int = 0


def table_entries(text: str, source: str) -> list[Entry]:
    entries: list[Entry] = []
    for sec in COLUMNS:
        table = section_table(text, sec)
        if not table:
            continue
        for line_no, row in zip(table.row_lines, table.rows):
            entries.append(Entry(source=source, section=sec, row=row, header=table.header, line_no=line_no))
    return entries


def entry_date(entry: Entry) -> date | None:
    return norm_date(entry.row[0]) if entry.row else None


def clean_cell(value: str) -> str:
    return str(value).replace("|", "｜").replace("\n", " ").strip()


def catalog_text(text: str) -> str:
    lines = []
    for sec in COLUMNS:
        rows = parse_rows(text, sec)
        if not rows:
            continue
        if sec == "底表":
            lines.append(f"- {sec}：{len(rows)} 条（永远全读）")
            continue
        topics: dict[str, int] = {}
        for r in rows:
            t = r[1] if len(r) > 1 else "?"
            topics[t] = topics.get(t, 0) + 1
        dist = "、".join(f"{k} {v}" for k, v in sorted(topics.items(), key=lambda x: (-x[1], x[0])))
        lines.append(f"- {sec}：{len(rows)} 条（{dist}）")
    return "\n".join(lines) or "- 暂无条目"


def brief_entries(text: str, profile: str, recent_days: int) -> str:
    if profile not in ("minimal", "standard"):
        return "profile 只能是 minimal / standard。"
    recent_days = max(1, min(int(recent_days), 14))
    today = date.today()
    cutoff = today - timedelta(days=recent_days)
    all_entries = table_entries(text, "active")
    bottom = [e for e in all_entries if e.section == "底表"]
    recent = [
        e for e in all_entries
        if e.section != "底表" and (d := entry_date(e)) is not None and cutoff <= d <= today + timedelta(days=1)
    ]
    todos = [e for e in all_entries if e.section == "待办"]
    todos.sort(key=lambda e: (entry_date(e) or date.min, e.line_no), reverse=True)
    todo_limit = 15 if profile == "minimal" else 20
    selected_todos = todos[:todo_limit]

    selected: list[Entry] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for entry in bottom + ([] if profile == "minimal" else recent) + selected_todos:
        key = (entry.section, tuple(normalize_text(c) for c in entry.row))
        if key not in seen:
            seen.add(key)
            selected.append(entry)

    lines = [
        "# 本轮记忆摘要",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"模式：{profile}；主表：{count_entries(text)} 条；底表：{len(bottom)} 条",
        "",
        "## 底表（长期原则）",
    ]
    bottom_selected = [e for e in selected if e.section == "底表"]
    if bottom_selected:
        lines.extend(f"- {e.row[0]}｜{'｜'.join(e.row[1:])}" for e in bottom_selected)
    else:
        lines.append("- 暂无")

    if profile == "standard":
        lines.extend(["", f"## 最近 {recent_days} 天"])
        recent_selected = [e for e in selected if e.section != "底表" and e in recent]
        if recent_selected:
            lines.extend(f"- [{e.section}] {'｜'.join(e.row)}" for e in recent_selected)
        else:
            lines.append("- 暂无")

    lines.extend(["", "## 未完成待办"])
    if selected_todos:
        lines.extend(f"- {e.row[0]}｜{e.row[1] if len(e.row) > 1 else '?'}｜{'｜'.join(e.row[2:])}" for e in selected_todos)
        if len(todos) > len(selected_todos):
            lines.append(f"- 另有 {len(todos) - len(selected_todos)} 条未展开；按话题调用 read(topic=...)")
    else:
        lines.append("- 暂无")
    return "\n".join(lines)


def search_tokens(text: str) -> set[str]:
    """ASCII 按词，中文按 2-gram；不依赖分词库。"""
    norm = normalize_text(text)
    tokens: set[str] = set()
    for segment in re.findall(r"[\u3400-\u9fff]+|[a-z0-9]+(?:[._/-][a-z0-9]+)*", norm):
        if re.fullmatch(r"[\u3400-\u9fff]+", segment):
            if len(segment) == 1:
                tokens.add(segment)
            else:
                tokens.update(segment[i:i + 2] for i in range(len(segment) - 1))
                tokens.add(segment)
        else:
            tokens.add(segment)
            tokens.update(x for x in re.split(r"[._/-]", segment) if x)
    if not tokens and norm:
        tokens.add(norm)
    return tokens


def load_alias_groups(path: Path) -> list[list[str]]:
    if not path.is_file():
        return []
    groups: list[list[str]] = []
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            terms = [normalize_text(x) for x in line.split("=", 1)[1].split(",") if x.strip()]
            left = normalize_text(line.split("=", 1)[0])
            if left:
                terms.insert(0, left)
            if len(terms) >= 2:
                groups.append(list(dict.fromkeys(terms)))
    except OSError:
        return []
    return groups


def expand_query(query: str, groups: list[list[str]]) -> list[str]:
    q = normalize_text(query)
    variants = [query]
    for group in groups:
        if any(term and (term in q or q in term) for term in group):
            variants.extend(group)
    return list(dict.fromkeys(variants))


def score_entry(query_variants: list[str], entry: Entry) -> float:
    row_text = " ".join(entry.row)
    row_norm = normalize_text(row_text)
    row_tokens = search_tokens(row_text)
    best = 0.0
    for query in query_variants:
        q_norm = normalize_text(query)
        q_tokens = search_tokens(query)
        if not q_norm or not q_tokens:
            continue
        matched = q_tokens & row_tokens
        coverage = len(matched) / len(q_tokens)
        precision = len(matched) / max(1, len(row_tokens))
        score = coverage * 10.0 + precision * 4.0
        if q_norm in row_norm:
            score += 20.0
        if q_norm == row_norm:
            score += 10.0
        score += sum(len(t) for t in matched) / 20.0
        best = max(best, score)
    return best


def entry_line(entry: Entry) -> str:
    return f"- [{entry.source}/{entry.section}] " + "｜".join(entry.row)


# ---------------- MCP 工具 ----------------

mcp = _Server("context-table")

@mcp.tool()
def remember(content: str, topic: str, section: str = "事实", why: str = "", force: bool = False) -> str:
    """把一条内容追加进记忆表。

    写入前会检查表结构、日期、话题，并拦截完全重复的条目。写入使用文件锁、
    原子替换和自动备份，避免并发写冲突或写到一半损坏。

    Args:
        content: 要记的内容。写结论、事实或待办本身，不要写“用户说”“AI 说”。
        topic: 话题标签。只能是：赛事 / 人际 / 工具 / 学习 / 方法 / 生活。
        section: 定了 / 事实 / 待办 / 否了 / 底表。默认事实。
        why: 决定的原因、待办卡在哪、否掉的理由。定了和否了必填。
        force: 确认要保留重复条目时设为 True。默认 False。
    """
    if section not in COLUMNS:
        return f"拒绝写入：section 只能是 {' / '.join(COLUMNS)}，收到的是「{section}」。"
    if topic not in TOPICS:
        return f"拒绝写入：topic 只能是 {' / '.join(TOPICS)}，收到的是「{topic}」。"
    if not content.strip():
        return "拒绝写入：content 是空的。"
    if section in ("定了", "否了") and not why.strip():
        return f"拒绝写入：「{section}」这一列必须给 why —— 原因比结论更值得留。"

    path = find_table()
    with table_lock(path):
        text = read_table(path)
        errors, _ = validate_table(text)
        if errors:
            return "拒绝写入：表结构不合法，先用 validate() 查看并修复。\n- " + "\n- ".join(errors[:8])

        today = date.today()
        today_s = today.isoformat() if detect_date_fmt(text) == "full" else f"{today.month:02d}-{today.day:02d}"
        q = clean_cell
        if section == "底表":
            row = f"| {today_s} | {q(content)}{('　—— ' + q(why)) if why.strip() else ''} |"
        elif section == "待办":
            row = f"| {today_s} | {q(topic)} | {q(content)} | {q(why) or '—'} |"
        elif section in ("定了", "否了"):
            row = f"| {today_s} | {q(topic)} | {q(content)} | {q(why)} |"
        else:
            row = f"| {today_s} | {q(topic)} | {q(content)} | {q(why) or '—'} |"

        duplicate = None
        for old in parse_rows(text, section):
            if section == "底表":
                same = normalize_text(old[1] if len(old) > 1 else "") == normalize_text(content)
            else:
                same = (
                    len(old) > 2
                    and normalize_text(old[1]) == normalize_text(topic)
                    and normalize_text(old[2]) == normalize_text(content)
                )
            if same:
                duplicate = old
                break
        if duplicate and not force:
            return "未写入：发现重复条目，疑似已经记过。\n" + " | ".join(duplicate) + "\n如确实需要重复记录，传 force=True。"

        new = insert_row(text, section, row)
        if new is None:
            return f"写入失败：表里找不到「{section}」这一节。检查 {path} 是否被改坏。"
        backup_file(path)
        atomic_write(path, new)
        return f"已记入「{section}」（{topic}）：{q(content)[:40]}"


@mcp.tool()
def brief(profile: str = "standard", recent_days: int = STANDARD_RECENT_DAYS) -> str:
    """返回本轮所需的短记忆摘要，应在新回合开始时优先调用。

    standard 返回底表、最近 3 天和未完成待办，适合大多数长任务回合；
    minimal 只返回底表与最近待办，适合成本敏感且任务上下文已明确的回合。

    这是客户端钩子缺失时的提示词级保障：它降低漏读概率，但不能替代平台自动注入。
    """
    path = find_table()
    text = read_table(path)
    result = brief_entries(text, profile, recent_days)
    errors, warnings = validate_table(text)
    if errors:
        result += "\n\n## 表结构警告\n- " + "\n- ".join(errors[:5])
    elif warnings:
        result += "\n\n## 提示\n- " + "\n- ".join(warnings[:3])
    return result


@mcp.tool()
def read(topic: str = "", include_archive: bool = False) -> str:
    """读记忆表。

    表小于等于 150 条时一次返回全文；超过 150 条时只返回分组目录，需要指定 topic
    才给内容。include_archive=True 会把归档中的同话题条目也带回来。

    Args:
        topic: 重点看某个话题；仍会带上最近 14 天所有话题和底表。留空表示全读（表小时）或要目录（表大时）。
        include_archive: 是否同时读取归档中的同话题条目。
    """
    path = find_table()
    text = read_table(path)
    total = count_entries(text)
    archive_path = find_archive(path)
    archive_text = archive_path.read_text(encoding="utf-8-sig") if archive_path.is_file() else ""
    archive_total = count_entries(archive_text) if archive_text else 0

    if topic:
        if topic not in TOPICS:
            return f"话题只能是 {' / '.join(TOPICS)}，收到的是「{topic}」。"
        blocks = []
        active_bottom = section_table(text, "底表")
        if active_bottom and active_bottom.rows:
            blocks.append("## 底表（永远成立）\n" + format_table(active_bottom))
        recent_cutoff = date.today() - timedelta(days=READ_RECENT_DAYS)
        for sec in [c for c in COLUMNS if c != "底表"]:
            table = section_table(text, sec)
            rows = []
            for row in (table.rows if table else []):
                d = norm_date(row[0]) if row else None
                is_topic = len(row) > 1 and row[1] == topic
                is_recent = d is not None and d >= recent_cutoff
                if is_topic or is_recent:
                    rows.append(row)
            if rows and table:
                filtered = SectionTable(table.header, rows, [], 0)
                blocks.append(f"## {sec}\n" + format_table(filtered))
        if include_archive and archive_text:
            for sec in [c for c in COLUMNS if c != "底表"]:
                table = section_table(archive_text, sec)
                rows = [r for r in (table.rows if table else []) if len(r) > 1 and r[1] == topic]
                if rows and table:
                    filtered = SectionTable(table.header, rows, [], 0)
                    blocks.append(f"## 归档 · {sec}\n" + format_table(filtered))
        if not blocks:
            return f"「{topic}」这个话题下还没有条目。"
        suffix = f"，归档另 {archive_total} 条" if include_archive and archive_total else ""
        return f"（主表共 {total} 条{suffix}，返回「{topic}」+ 最近 {READ_RECENT_DAYS} 天 + 底表）\n\n" + "\n\n".join(blocks)

    if total <= SMALL_TABLE:
        suffix = f"\n\n（另有归档 {archive_total} 条；检索时用 search，或 read(topic=..., include_archive=True)）" if archive_total else ""
        return f"（主表共 {total} 条，全量返回）\n\n{text.strip()}{suffix}"

    return (
        f"（主表共 {total} 条，超过 {SMALL_TABLE} 条，不全文返回；归档 {archive_total} 条）\n\n"
        + catalog_text(text)
        + "\n\n用 read(topic=...) 取某一组，或者先 search(query=...) 定位。"
    )

@mcp.tool()
def search(query: str, topic: str = "", include_archive: bool = True, limit: int = 5) -> str:
    """按关键词找候选条目，不把“没命中”误报成“表里没有”。

    中文使用 2-gram 匹配；可在同目录的 *-aliases.md 中维护同义说法。
    没有命中且主表较小时自动回退全文；主表较大时返回明确的不确定状态、最近条目
    和目录，提示继续 read(topic=...) 或换关键词。
    """
    if not query.strip():
        return "query 不能为空。"
    if topic and topic not in TOPICS:
        return f"话题只能是 {' / '.join(TOPICS)}，收到的是「{topic}」。"
    limit = max(1, min(int(limit), 20))
    path = find_table()
    text = read_table(path)
    archive_path = find_archive(path)
    archive_text = archive_path.read_text(encoding="utf-8-sig") if include_archive and archive_path.is_file() else ""
    groups = load_alias_groups(find_alias_file(path))
    variants = expand_query(query, groups)

    entries = table_entries(text, "active")
    if archive_text:
        entries.extend(table_entries(archive_text, "archive"))
    if topic:
        entries = [e for e in entries if e.section == "底表" or (len(e.row) > 1 and e.row[1] == topic)]

    scored = [(score_entry(variants, e), e) for e in entries]
    scored = [(s, e) for s, e in scored if s > 0]
    scored.sort(key=lambda pair: (pair[0], entry_date(pair[1]) or date.min, pair[1].source == "active"), reverse=True)
    top = scored[:limit]

    if top:
        lines = [
            "（检索结果只是候选，不是“表里只有这些”的证明）",
            f"查询：{query}；命中 {len(scored)} 条；主表 {count_entries(text)} 条；归档 {count_entries(archive_text) if archive_text else 0} 条",
            "",
        ]
        lines.extend(entry_line(e) for _, e in top)
        if len(scored) > len(top):
            lines.append(f"- 另有 {len(scored) - len(top)} 条候选；缩小关键词或提高 limit。")
        return "\n".join(lines)

    active_total = count_entries(text)
    archive_total = count_entries(archive_text) if archive_text else 0
    header = [
        "（未找到候选。这不等于表中没有；可能只是措辞不同。）",
        f"查询：{query}；主表 {active_total} 条；归档 {archive_total} 条",
        "",
    ]
    if active_total <= SMALL_TABLE:
        header.append("## 自动回退：主表全文")
        header.append(text.strip())
        if archive_total:
            header.append("\n归档未全文展开；可换关键词或 read(topic=..., include_archive=True)。")
        return "\n".join(header)

    recent_cutoff = date.today() - timedelta(days=STANDARD_RECENT_DAYS)
    recent = [e for e in table_entries(text, "active") if (d := entry_date(e)) and d >= recent_cutoff]
    recent.sort(key=lambda e: entry_date(e) or date.min, reverse=True)
    header.extend(["## 主表目录", catalog_text(text), "", "## 最近条目"])
    if recent:
        header.extend(entry_line(e) for e in recent[:10])
    else:
        header.append("- 暂无")
    header.extend(["", "下一步：换一个更短的关键词，或 read(topic=...) 粗筛。"])
    return "\n".join(header)


@mcp.tool()
def prune(dry_run: bool = True, execute_archive: bool = False, older_than_days: int = 180) -> str:
    """检查并整理记忆表。默认只报告，不动任何文件。永不物理删除。

    Args:
        dry_run: True（默认）只报告。要真正执行归档，必须同时传 dry_run=False 和 execute_archive=True。
        execute_archive: 把超过 older_than_days 的流水条目移入归档文件。归档仍可被 search 找回。
        older_than_days: 归档门槛，默认 180 天。
    """
    if not dry_run and execute_archive:
        return _archive(dry_run=False, older_than_days=older_than_days)
    path = find_table()
    text = read_table(path)
    cutoff = date.today() - timedelta(days=30)
    stale_todo = [r for r in parse_rows(text, "待办") if (d := norm_date(r[0] if r else "")) and d < cutoff]
    old_rows = []
    for sec in [c for c in COLUMNS if c != "底表"]:
        for r in parse_rows(text, sec):
            d = norm_date(r[0]) if r else None
            if d and d < cutoff:
                old_rows.append((sec, r))

    lines = [f"表：{path}", f"条目总数：{count_entries(text)}", ""]
    lines.append(f"## 超过 30 天的待办（{len(stale_todo)} 条）")
    if stale_todo:
        lines.extend(f"- {' | '.join(r)}" for r in stale_todo[:20])
        if len(stale_todo) > 20:
            lines.append(f"- 另有 {len(stale_todo) - 20} 条未展开")
    else:
        lines.append("- 无")
    lines.extend(["", f"## 超过 30 天的旧条目（{len(old_rows)} 条）"])
    lines.append("建议：prune(dry_run=True) 先看，确认后 prune(dry_run=False, execute_archive=True) 执行归档。")
    lines.append("安全边界：工具从不物理删除；归档仍可由 search 找回。")
    if not dry_run:
        lines.extend(["", "注意：只传 dry_run=False 不会动文件，必须同时传 execute_archive=True。"])
    return "\n".join(lines)


def _archive(dry_run: bool = True, older_than_days: int = 180) -> str:
    """把旧的流水条目移入归档文件。默认只预览，不修改。

    归档仍保留完整原行，并会被 search(include_archive=True) 检索。底表永不归档，
    任何条目都不会被物理删除。
    """
    older_than_days = max(1, min(int(older_than_days), 3650))
    path = find_table()
    archive_path = find_archive(path)
    cutoff = date.today() - timedelta(days=older_than_days)
    with table_lock(path):
        text = read_table(path)
        errors, _ = validate_table(text)
        if errors:
            return "拒绝归档：主表结构不合法，先用 validate() 修复。\n- " + "\n- ".join(errors[:8])

        selected: list[tuple[str, list[str], int]] = []
        headers: dict[str, list[str]] = {}
        for sec in [c for c in COLUMNS if c != "底表"]:
            table = section_table(text, sec)
            if not table:
                continue
            headers[sec] = table.header
            for line_no, row in zip(table.row_lines, table.rows):
                d = norm_date(row[0]) if row else None
                if d and d < cutoff:
                    selected.append((sec, row, line_no))

        if not selected:
            return f"没有早于 {cutoff.isoformat()} 的流水条目需要归档。"

        by_section: dict[str, int] = {}
        for sec, _, _ in selected:
            by_section[sec] = by_section.get(sec, 0) + 1
        summary = "、".join(f"{k} {v}" for k, v in by_section.items())
        if dry_run:
            lines = [
                f"将归档 {len(selected)} 条（{summary}）。",
                f"截止日期：{cutoff.isoformat()}；归档文件：{archive_path}",
                "这是预览，表未修改。确认后调用 archive(dry_run=False, older_than_days=...)。",
                "",
                "## 预览",
            ]
            lines.extend(f"- [{sec}] {' | '.join(row)}" for sec, row, _ in selected[:20])
            if len(selected) > 20:
                lines.append(f"- 另有 {len(selected) - 20} 条未展开")
            return "\n".join(lines)
        archive_text = archive_path.read_text(encoding="utf-8-sig") if archive_path.is_file() else ""
        if archive_text.strip():
            archive_errors, _ = validate_table(archive_text, [c for c in COLUMNS if c != "底表"])
            if archive_errors:
                return "拒绝归档：归档文件结构不合法。\n- " + "\n- ".join(archive_errors[:8])
        else:
            archive_text = build_empty_archive(headers)

        existing = {
            (e.section, tuple(normalize_text(c) for c in e.row))
            for e in table_entries(archive_text, "archive")
        }
        new_archive = archive_text
        appended = 0
        for sec, row, _ in selected:
            key = (sec, tuple(normalize_text(c) for c in row))
            if key in existing:
                continue
            updated = insert_row(new_archive, sec, f"| {' | '.join(row)} |")
            if updated is None:
                return f"拒绝归档：归档文件中无法写入「{sec}」小节。"
            new_archive = updated
            existing.add(key)
            appended += 1

        backup_file(path)
        if archive_path.is_file():
            backup_file(archive_path)
        atomic_write(archive_path, new_archive)

        lines = text.split("\n")
        for _, _, line_no in sorted(selected, key=lambda item: item[2], reverse=True):
            del lines[line_no]
        new_text = "\n".join(lines)
        atomic_write(path, new_text)
        return (
            f"已归档 {len(selected)} 条（{summary}）；新写入归档 {appended} 条，"
            f"其余已在归档中存在。\n主表：{path}\n归档：{archive_path}\n"
            "主表条目未被物理删除，search 默认包含归档。"
        )


def build_empty_archive(headers: dict[str, list[str]]) -> str:
    lines = ["# 记忆归档", "", "> 从这里移出的旧流水条目；只增不减，可被 search 检索。", ""]
    for sec in COLUMNS:
        if sec == "底表":
            continue
        header = headers.get(sec, ["日期", "话题", "内容", "备注"])
        lines.extend([
            f"## {SECTION_NUM.get(sec, sec)}",
            "",
            "| " + " | ".join(header) + " |",
            "|" + "|".join("---" for _ in header) + "|",
            "",
        ])
    return "\n".join(lines)


def validate() -> str:
    """检查主表、归档和别名文件的结构，不修改内容。"""
    path = find_table()
    text = read_table(path)
    errors, warnings = validate_table(text)
    lines = [f"主表：{path}", f"条目数：{count_entries(text)}", ""]
    if errors:
        lines.append(f"## 错误（{len(errors)}）")
        lines.extend(f"- {x}" for x in errors)
    else:
        lines.append("## 主表结构：通过")
    if warnings:
        lines.extend(["", f"## 警告（{len(warnings)}）"])
        lines.extend(f"- {x}" for x in warnings)

    archive_path = find_archive(path)
    if archive_path.is_file():
        archive_text = archive_path.read_text(encoding="utf-8-sig")
        a_errors, a_warnings = validate_table(archive_text, [c for c in COLUMNS if c != "底表"])
        lines.extend(["", f"## 归档：{archive_path}"])
        if a_errors:
            lines.extend(f"- 错误：{x}" for x in a_errors)
        else:
            lines.append("- 结构：通过")
        lines.extend(f"- 警告：{x}" for x in a_warnings)

    alias_path = find_alias_file(path)
    if alias_path.is_file():
        groups = load_alias_groups(alias_path)
        lines.extend(["", f"## 别名：{alias_path}", f"- 已加载 {len(groups)} 组同义说法"])
    return "\n".join(lines)


def undo() -> str:
    """恢复主表最近一次写入前的自动备份。恢复前会再备份当前版本。"""
    path = find_table()
    target_dir = backup_dir(path)
    candidates = sorted(target_dir.glob(f"{path.name}.*.bak"), key=lambda p: p.name) if target_dir.is_dir() else []
    if not candidates:
        return "没有可恢复的自动备份。"
    selected = candidates[-1]
    with table_lock(path):
        backup_file(path)
        content = selected.read_text(encoding="utf-8-sig")
        atomic_write(path, content)
        used_dir = target_dir / "used"
        used_dir.mkdir(parents=True, exist_ok=True)
        selected.replace(used_dir / selected.name)
    return f"已恢复写入前版本：{selected.name}\n当前表：{path}\n被恢复的备份已移到 {used_dir}。"


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] in ("validate", "undo"):
        print(validate() if args[0] == "validate" else undo())
        sys.exit(0)
    mcp.run()