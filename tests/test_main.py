import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# 测试固定用这套话题，不受 CONTEXT_TABLE.md 默认值变化影响
os.environ.setdefault("CONTEXT_TABLE_TOPICS", "赛事,人际,工具,学习,方法,生活")

import server.main as m


class ContextTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.table = self.root / "memory-table.md"
        self.old_env = {k: os.environ.get(k) for k in (
            "CONTEXT_TABLE_PATH", "CONTEXT_TABLE_ARCHIVE_PATH", "CONTEXT_TABLE_ALIASES"
        )}
        os.environ["CONTEXT_TABLE_PATH"] = str(self.table)
        os.environ.pop("CONTEXT_TABLE_ARCHIVE_PATH", None)
        os.environ.pop("CONTEXT_TABLE_ALIASES", None)
        m.read_table(self.table)

    def tearDown(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_template_validates(self):
        self.assertIn("主表结构：通过", m.validate())

    def test_remember_rejects_duplicate_unless_forced(self):
        first = m.remember("项目路径是 D:/ctx", "工具")
        duplicate = m.remember("项目路径是 D:/ctx", "工具")
        forced = m.remember("项目路径是 D:/ctx", "工具", force=True)
        self.assertIn("已记入", first)
        self.assertIn("未写入", duplicate)
        self.assertIn("已记入", forced)
        self.assertEqual(m.count_entries(self.table.read_text(encoding="utf-8")), 2)

    def test_decision_requires_why(self):
        result = m.remember("采用本地优先", "方法", "定了")
        self.assertIn("必须给 why", result)

    def test_brief_contains_bottom_recent_and_todo(self):
        m.remember("数据先本地保存", "方法", "底表", "隐私与可恢复")
        m.remember("今天确认了表结构", "工具")
        m.remember("补齐并发测试", "工具", "待办", "尚未覆盖多进程")
        result = m.brief()
        self.assertIn("数据先本地保存", result)
        self.assertIn("今天确认了表结构", result)
        self.assertIn("补齐并发测试", result)

    def test_read_topic_keeps_recent_days_from_all_topics(self):
        m.remember("近期工具事实", "工具")
        text = self.table.read_text(encoding="utf-8")
        text = m.insert_row(text, "事实", "| 2020-01-01 | 赛事 | 旧赛事事实 | 历史 |")
        m.atomic_write(self.table, text)
        result = m.read("赛事")
        self.assertIn("旧赛事事实", result)
        self.assertIn("近期工具事实", result)

    def test_search_supports_chinese_bigram_and_ascii_parts(self):
        m.remember("政府文件保存在 D:/docs", "学习")
        m.remember("路径是 D:/context-table", "工具")
        self.assertIn("政府文件", m.search("政府文件"))
        self.assertIn("D:/context-table", m.search("context table"))

    def test_alias_file_expands_search(self):
        aliases = self.root / "memory-table-aliases.md"
        aliases.write_text("政策原文 = 政府文件, 政府公告\n", encoding="utf-8")
        m.remember("政府文件保存在 D:/docs", "学习")
        result = m.search("政策原文")
        self.assertIn("政府文件保存在", result)
        self.assertNotIn("自动回退", result)

    def test_search_miss_returns_explicit_uncertainty_and_full_fallback(self):
        m.remember("苹果采购完成", "生活")
        result = m.search("政策原文")
        self.assertIn("不等于表中没有", result)
        self.assertIn("自动回退：主表全文", result)

    def test_archive_moves_but_keeps_entry_searchable(self):
        text = self.table.read_text(encoding="utf-8")
        text = m.insert_row(text, "事实", "| 2020-01-01 | 工具 | 旧事实：政府文件在 D:/docs | 历史 |")
        m.atomic_write(self.table, text)

        preview = m._archive()
        self.assertIn("将归档 1 条", preview)
        self.assertIn("旧事实", self.table.read_text(encoding="utf-8"))

        applied = m.prune(dry_run=False, execute_archive=True, older_than_days=180)
        self.assertIn("已归档 1 条", applied)
        self.assertNotIn("旧事实", self.table.read_text(encoding="utf-8"))
        archive = self.root / "memory-table-archive.md"
        self.assertIn("旧事实", archive.read_text(encoding="utf-8"))
        self.assertIn("archive/事实", m.search("旧事实"))
        self.assertIn("归档", m.validate())

    def test_undo_restores_previous_table(self):
        before = self.table.read_text(encoding="utf-8")
        m.remember("临时错误", "工具")
        result = m.undo()
        self.assertIn("已恢复", result)
        self.assertEqual(self.table.read_text(encoding="utf-8"), before)

    def test_validation_detects_invalid_topic(self):
        text = self.table.read_text(encoding="utf-8")
        text = m.insert_row(text, "事实", "| 2026-11-17 | 未知话题 | 内容 | 备注 |")
        errors, _ = m.validate_table(text)
        self.assertTrue(any("话题不在允许列表" in x for x in errors))

    def test_prune_never_deletes(self):
        text = self.table.read_text(encoding="utf-8")
        text = m.insert_row(text, "待办", "| 2020-01-01 | 工具 | 很旧的待办 | 卡住 |")
        m.atomic_write(self.table, text)
        m.prune(dry_run=False)
        self.assertIn("很旧的待办", self.table.read_text(encoding="utf-8"))

    def test_concurrent_writes_do_not_lose_entries(self):
        code = "import os, server.main as m; print(m.remember(os.environ['CT_TEST_CONTENT'], '工具'))"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        procs = []
        for i in range(8):
            child_env = env.copy()
            child_env["CT_TEST_CONTENT"] = f"并发条目 {i}"
            procs.append(subprocess.Popen(
                [sys.executable, "-c", code],
                cwd=Path(__file__).resolve().parent.parent,
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ))
        for proc in procs:
            out, err = proc.communicate(timeout=20)
            self.assertEqual(proc.returncode, 0, err.decode("utf-8", errors="replace"))
            self.assertIn("已记入", out.decode("utf-8", errors="replace"))
        self.assertEqual(m.count_entries(self.table.read_text(encoding="utf-8")), 8)
        errors, _ = m.validate_table(self.table.read_text(encoding="utf-8"))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()