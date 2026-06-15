"""口味库测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import taste
from infra import file_utils


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
            "examples": [
                {"type": "good", "text": "全局案例一", "annotation": "全局A"},
                {"type": "good", "text": "全局案例二", "annotation": "全局B"},
                {"type": "good", "text": "全局案例三", "annotation": "全局C"},
            ],
        })
        block = taste.build_context_block(book_id="")
        self.assertIn("口味库", block)
        self.assertIn("心理描写", block)
        self.assertIn("强冲突", block)
        self.assertIn("全局案例三", block)

    def test_context_block_book_examples_first(self) -> None:
        taste.ensure_taste_dir()
        taste.save_global({
            "examples": [
                {"type": "good", "text": f"全局案例{i}", "annotation": f"G{i}"}
                for i in range(1, 7)
            ],
        })
        book_dir = self.tmp / "book-b"
        book_dir.mkdir()
        file_utils.atomic_write_text(
            book_dir / taste.BOOK_TASTE_FILENAME,
            json.dumps({
                "version": 2,
                "inherit_global": True,
                "overrides": {
                    "append_examples": [
                        {"type": "good", "text": "本书亮点", "annotation": "本书"},
                    ],
                },
            }, ensure_ascii=False),
        )
        block = taste.build_context_block(book_dir=book_dir)
        self.assertIn("本书亮点", block)
        self.assertIn("全局案例6", block)
        self.assertIn("全局案例4", block)
        self.assertNotIn("全局案例1", block)
        self.assertNotIn("全局案例2", block)

    def test_context_block_merged_rules_priority(self) -> None:
        taste.ensure_taste_dir()
        taste.save_global({
            "rules": [
                {"id": "g1", "content": "全局硬性：每章结尾留钩子", "weight": "hard"},
                {"id": "g2", "content": "全局软性：节奏要快", "weight": "soft"},
            ],
        })
        book_dir = self.tmp / "book-rules"
        book_dir.mkdir()
        file_utils.atomic_write_text(
            book_dir / taste.BOOK_TASTE_FILENAME,
            json.dumps({
                "version": 2,
                "overrides": {
                    "append_rules": [
                        {"id": "b1", "content": "本书专属规则", "weight": "hard"},
                    ],
                },
            }, ensure_ascii=False),
        )
        block = taste.build_context_block(book_dir=book_dir)
        self.assertIn("# 规则来源：本书1条 / 全局2条", block)
        self.assertIn("[本书] 本书专属规则", block)
        self.assertIn("全局硬性：每章结尾留钩子", block)
        self.assertIn("写作规则（按优先级）", block)

    def test_context_block_rule_conflict_keeps_higher_priority(self) -> None:
        taste.ensure_taste_dir()
        taste.save_global({
            "rules": [
                {
                    "id": "g1",
                    "content": "每章结尾须留悬念或情绪钩子",
                    "weight": "hard",
                },
            ],
        })
        book_dir = self.tmp / "book-conflict"
        book_dir.mkdir()
        file_utils.atomic_write_text(
            book_dir / taste.BOOK_TASTE_FILENAME,
            json.dumps({
                "version": 2,
                "overrides": {
                    "append_rules": [
                        {
                            "id": "b1",
                            "content": "每章结尾须留悬念或情绪",
                            "weight": "hard",
                        },
                    ],
                },
            }, ensure_ascii=False),
        )
        block = taste.build_context_block(book_dir=book_dir)
        self.assertIn("[本书] 每章结尾须留悬念或情绪", block)
        self.assertNotIn("每章结尾须留悬念或情绪钩子", block)
        self.assertIn("# 规则来源：本书1条 / 全局0条", block)

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

    def test_import_deconstruct_patterns_filtered(self) -> None:
        taste.ensure_taste_dir()
        log_id = "filter123"
        taste.append_event(
            source="deconstruct",
            quality_log_id=log_id,
            book_id="b1",
            patterns={
                "hook_patterns": ["黄金三章：误会开局", "章末留钩子"],
                "structure_notes": ["每章一个小反转"],
            },
        )
        result = taste.import_deconstruct_patterns(
            log_id,
            merge_global=True,
            hook_patterns=["章末留钩子"],
            structure_notes=[],
        )
        self.assertTrue(result.get("ok"))
        doc = taste.load_global()
        hooks = doc["preferences"].get("hook_patterns") or []
        self.assertTrue(any("章末" in h for h in hooks))
        self.assertFalse(any("误会" in h for h in hooks))

    def test_delete_rule(self) -> None:
        taste.ensure_taste_dir()
        rule = taste.add_rule(content="章末必须有钩子", weight="hard")
        rid = rule["id"]
        removed = taste.delete_rule(rid)
        self.assertIsNotNone(removed)
        doc = taste.load_global()
        self.assertFalse(any(r.get("id") == rid for r in doc.get("rules") or []))

    def test_delete_rule_missing(self) -> None:
        taste.ensure_taste_dir()
        self.assertIsNone(taste.delete_rule("rule-missing"))

    def test_localize_rule_to_book(self) -> None:
        taste.ensure_taste_dir()
        rule = taste.add_rule(content="仅本书规则", weight="soft")
        rid = rule["id"]
        book_dir = self.tmp / "book-local"
        book_dir.mkdir()
        result = taste.localize_rule_to_book(rid, book_dir)
        self.assertEqual(result["rule"]["id"], rid)
        global_doc = taste.load_global()
        self.assertFalse(any(r.get("id") == rid for r in global_doc.get("rules") or []))
        book_doc = taste.load_book_taste(book_dir)
        append_rules = (book_doc.get("overrides") or {}).get("append_rules") or []
        self.assertTrue(any(r.get("id") == rid for r in append_rules))


if __name__ == "__main__":
    unittest.main()
