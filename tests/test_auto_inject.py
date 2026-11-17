import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "AGENTS.md"
COPIES = (
    ROOT / "workbuddy" / "MEMORY.md",
    ROOT / ".workbuddy" / "memory" / "MEMORY.md",
)


class AutoInjectTests(unittest.TestCase):
    def test_auto_inject_copies_are_identical(self):
        source = SOURCE.read_text(encoding="utf-8")
        for copy in COPIES:
            self.assertTrue(copy.is_file(), copy)
            self.assertEqual(copy.read_text(encoding="utf-8"), source, copy)

    def test_workbuddy_rule_fits_memory_limit(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertLessEqual(len(text), 3000)

    def test_rule_contains_all_four_triggers(self):
        text = SOURCE.read_text(encoding="utf-8")
        for phrase in ("用户做了一个决定", "出现新的事实", "冒出新的待办", "排除了某个方案"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()