"""bookshelf_stats 单元测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.bookshelf_stats import bookshelf_stats


class BookshelfStatsTests(unittest.TestCase):
    def test_draft_without_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            book_dir = Path(tmp)
            (book_dir / "project.json").write_text(
                json.dumps({"title": "测试", "lifecycle": {"status": "drafting"}}),
                encoding="utf-8",
            )
            stats = bookshelf_stats(book_dir)
            self.assertEqual(stats["shelf_status"], "draft")
            self.assertFalse(stats["wizard_complete"])

    def test_active_with_chapters_and_criteria(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            book_dir = Path(tmp)
            (book_dir / "project.json").write_text("{}", encoding="utf-8")
            (book_dir / "plan.json").write_text(
                json.dumps(
                    {
                        "meta": {"logline": "方向"},
                        "chapters": {
                            "1": {"title": "第一章", "status": "approved"},
                            "2": {"title": "第二章", "status": "pending"},
                        },
                        "review_criteria": {"hard_rules": ["钩子"]},
                    }
                ),
                encoding="utf-8",
            )
            stats = bookshelf_stats(book_dir)
            self.assertEqual(stats["shelf_status"], "active")
            self.assertTrue(stats["wizard_complete"])
            self.assertEqual(stats["progress_pct"], 50)
            self.assertIn("第 2 章", stats["chapter_label"])

    def test_done_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            book_dir = Path(tmp)
            (book_dir / "project.json").write_text(
                json.dumps({"lifecycle": {"status": "complete"}}),
                encoding="utf-8",
            )
            (book_dir / "plan.json").write_text(
                json.dumps(
                    {
                        "meta": {"logline": "x"},
                        "chapters": {"1": {"status": "approved"}},
                        "review_criteria": {"hard_rules": ["a"]},
                    }
                ),
                encoding="utf-8",
            )
            stats = bookshelf_stats(book_dir)
            self.assertEqual(stats["shelf_status"], "done")


if __name__ == "__main__":
    unittest.main()
