"""流程对齐：写作模式、亮点冲突、拒稿分叉。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import highlight_conflict
from core import plan_product
from core import taste
from core.data import novel_data


class FlowAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.book_dir = self.tmp / "book-a"
        self.book_dir.mkdir()
        taste.TASTE_DIR = self.tmp / "taste"
        taste.GLOBAL_FILE = taste.TASTE_DIR / "global.json"
        taste.EVENTS_FILE = taste.TASTE_DIR / "events.jsonl"
        novel_data.PLAN_FILE = self.book_dir / "plan.json"
        novel_data._save_json(novel_data.PLAN_FILE, {"chapters": {}, "meta": {}})

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_writing_mode_stripped_from_meta(self) -> None:
        novel_data._save_json(
            novel_data.PLAN_FILE,
            {"chapters": {}, "meta": {"logline": "旧书", "writing_mode": "fast"}},
        )
        self.assertNotIn("writing_mode", plan_product.get_meta())
        plan_product.set_plan_meta({"logline": "更新"})
        raw = json.loads(novel_data.PLAN_FILE.read_text(encoding="utf-8"))
        self.assertNotIn("writing_mode", raw.get("meta") or {})
        self.assertEqual(raw["meta"]["logline"], "更新")

    def test_writing_mode_stripped_on_load_plan(self) -> None:
        novel_data._save_json(
            novel_data.PLAN_FILE,
            {"chapters": {}, "meta": {"logline": "只读", "writing_mode": "standard"}},
        )
        plan_product.load_plan()
        raw = json.loads(novel_data.PLAN_FILE.read_text(encoding="utf-8"))
        self.assertNotIn("writing_mode", raw.get("meta") or {})
        self.assertEqual(raw["meta"]["logline"], "只读")

    def test_highlight_conflict_detects_avoid(self) -> None:
        taste.ensure_taste_dir()
        taste.save_global({
            "preferences": {"avoid_patterns": ["仿佛"]},
            "rules": [{"content": "避免慢热", "weight": "hard"}],
        })
        report = highlight_conflict.check_highlight_conflicts(
            book_id="book-a",
            text="开头仿佛很慢",
            book_dir=self.book_dir,
        )
        self.assertTrue(report["has_conflict"])

    def test_push_highlight_blocks_on_conflict(self) -> None:
        from core.orchestration import product as product_orch
        from unittest.mock import MagicMock

        taste.ensure_taste_dir()
        taste.save_global({
            "preferences": {"avoid_patterns": ["AI腔"]},
        })
        ctx = MagicMock()
        ctx.store.paths.data_dir = self.book_dir
        with unittest.mock.patch(
            "core.data.book_context.get_context",
            return_value=MagicMock(book_id="book-a"),
        ):
            result = product_orch.push_highlight(
                ctx,
                chapter_num=1,
                text="这段 AI腔 很重",
            )
        self.assertFalse(result.get("ok"))
        self.assertTrue(result.get("conflicts"))

    def test_create_attribution_log_for_l5b(self) -> None:
        from core.orchestration import product as product_orch
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.store.paths.data_dir = self.book_dir
        ctx.quality_log_entry = MagicMock(return_value="ql-l5b-1")
        with unittest.mock.patch(
            "core.orchestration.logs.record_quality_judgment",
            return_value={"ok": True},
        ):
            result = product_orch.create_attribution_log(
                ctx,
                chapter_num=2,
                source="L5b",
                note="节奏预警测试",
            )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("log_id"), "ql-l5b-1")


if __name__ == "__main__":
    unittest.main()
