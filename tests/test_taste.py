"""口味库测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import taste


class TasteLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        taste.TASTE_DIR = self.tmp / "taste"
        taste.GLOBAL_FILE = taste.TASTE_DIR / "global.json"
        taste.EVENTS_FILE = taste.TASTE_DIR / "events.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_global_save_and_merge(self) -> None:
        taste.ensure_taste_dir()
        taste.save_global({
            "preferences": {
                "likes": ["短钩子"],
                "dislikes": ["AI味"],
                "platform_notes": "番茄向",
            },
        })
        book_dir = self.tmp / "book-a"
        book_dir.mkdir()
        taste.save_book_taste(book_dir, {
            "preferences": {"likes": ["快节奏"]},
        })
        merged = taste.merge_preferences(book_dir=book_dir)
        self.assertIn("短钩子", merged["likes"])
        self.assertIn("快节奏", merged["likes"])
        self.assertIn("AI味", merged["dislikes"])

    def test_event_and_tag_stats(self) -> None:
        taste.ensure_taste_dir()
        eid = taste.append_event(
            source="judgment",
            outcome="rejected",
            issue_tags=["hook_weak", "ai_tone"],
            book_id="book-1",
            note="开头慢",
        )
        self.assertTrue(eid.startswith("evt-"))
        doc = taste.load_global()
        stats = doc.get("tag_stats") or {}
        self.assertGreaterEqual(int(stats.get("hook_weak", {}).get("count", 0)), 1)
        events = taste.list_events(book_id="book-1")
        self.assertEqual(len(events), 1)

    def test_context_block(self) -> None:
        taste.ensure_taste_dir()
        taste.save_global({
            "preferences": {
                "dislikes": ["大段心理描写"],
                "hook_patterns": ["前三段强冲突"],
            },
        })
        block = taste.build_context_block(book_id="")
        self.assertIn("口味库", block)
        self.assertIn("心理描写", block)
        self.assertIn("强冲突", block)

    def test_import_deconstruct_patterns(self) -> None:
        taste.ensure_taste_dir()
        log_id = "abc123"
        taste.append_event(
            source="deconstruct",
            quality_log_id=log_id,
            book_id="b1",
            patterns={
                "hook_patterns": ["黄金三章：误会开局"],
                "structure_notes": ["每章一个小反转"],
            },
        )
        result = taste.import_deconstruct_patterns(log_id, merge_global=True)
        self.assertTrue(result.get("ok"))
        doc = taste.load_global()
        hooks = doc["preferences"].get("hook_patterns") or []
        self.assertTrue(any("误会" in h for h in hooks))


if __name__ == "__main__":
    unittest.main()
