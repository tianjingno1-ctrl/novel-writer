"""长短篇分叉：口味过滤、Prompt 路由、审阅 profile。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import profiles
from core import prompt_nodes
from core import taste


class BookTypeRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        taste.TASTE_DIR = self.tmp / "taste"
        taste.GLOBAL_FILE = taste.TASTE_DIR / "global.json"
        taste.EVENTS_FILE = taste.TASTE_DIR / "events.jsonl"
        profiles.PROFILES_DIR = self.tmp / "profiles"
        profiles.ensure_profiles_dir()
        taste.ensure_taste_dir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _book_dir(self, book_type: str) -> Path:
        book_dir = self.tmp / f"book-{book_type}"
        book_dir.mkdir()
        (book_dir / "project.json").write_text(
            json.dumps({"type": book_type, "platform": "tomato"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return book_dir

    def test_taste_global_rules_filter_by_book_type(self) -> None:
        taste.save_global({
            "rules": [
                {"id": "s1", "content": "短篇五章须收束", "weight": "hard", "book_types": ["short"]},
                {"id": "n1", "content": "长篇每章留追更动机", "weight": "hard", "book_types": ["novel"]},
                {"id": "a1", "content": "通用：禁止 AI 味", "weight": "soft"},
            ],
        })
        short_block = taste.build_context_block(book_dir=self._book_dir("short"))
        novel_block = taste.build_context_block(book_dir=self._book_dir("novel"))
        self.assertIn("短篇五章须收束", short_block)
        self.assertNotIn("长篇每章留追更动机", short_block)
        self.assertIn("长篇每章留追更动机", novel_block)
        self.assertNotIn("短篇五章须收束", novel_block)
        self.assertIn("禁止 AI 味", short_block)
        self.assertIn("禁止 AI 味", novel_block)

    def test_prompt_nodes_prefill_and_writing_by_type(self) -> None:
        short_dir = self._book_dir("short")
        novel_dir = self._book_dir("novel")
        short_dir_p = short_dir / "project.json"
        novel_dir_p = novel_dir / "project.json"

        short_pre = prompt_nodes.resolve_node(
            "prefill.plan", book_dir=short_dir,
            project=json.loads(short_dir_p.read_text(encoding="utf-8")),
        )
        novel_pre = prompt_nodes.resolve_node(
            "prefill.plan", book_dir=novel_dir,
            project=json.loads(novel_dir_p.read_text(encoding="utf-8")),
        )
        self.assertEqual(short_pre.prompt_id, "prefill_short_plan")
        self.assertEqual(novel_pre.prompt_id, "prefill_novel_plan")
        self.assertIn("paywall", short_pre.system)
        self.assertIn("不要求", novel_pre.system)
        self.assertIn("勿为短篇", novel_pre.system)

        short_w = prompt_nodes.resolve_node("writing.main", book_dir=short_dir)
        novel_w = prompt_nodes.resolve_node("writing.main", book_dir=novel_dir)
        self.assertEqual(short_w.prompt_id, "writing")
        self.assertEqual(novel_w.prompt_id, "writing_novel")
        self.assertIn("长篇连载", novel_w.system)

    def test_profiles_resolve_novel_vs_short(self) -> None:
        src = Path(__file__).resolve().parents[1] / "library" / "profiles"
        for name in ("tomato_text_editor_v1.yaml", "tomato_novel_text_editor_v1.yaml"):
            text = (src / name).read_text(encoding="utf-8")
            (profiles.PROFILES_DIR / name).write_text(text, encoding="utf-8")

        short_pid = profiles.resolve_default_profile_id(book_type="short", platform="tomato")
        novel_pid = profiles.resolve_default_profile_id(book_type="novel", platform="tomato")
        self.assertEqual(short_pid, "tomato_text_editor_v1")
        self.assertEqual(novel_pid, "tomato_novel_text_editor_v1")

        short_profile = profiles.load_profile(short_pid)
        novel_profile = profiles.load_profile(novel_pid)
        self.assertEqual(short_profile.get("review_prompt_id"), "short-tomato")
        self.assertEqual(novel_profile.get("review_prompt_id"), "novel-tomato")

    def test_review_platform_node_resolves_without_static_prompt_id(self) -> None:
        src = Path(__file__).resolve().parents[1] / "library" / "profiles"
        for name in ("tomato_text_editor_v1.yaml",):
            text = (src / name).read_text(encoding="utf-8")
            (profiles.PROFILES_DIR / name).write_text(text, encoding="utf-8")
        short_dir = self._book_dir("short")
        resolved = prompt_nodes.resolve_node(
            "review.platform",
            book_dir=short_dir,
            project=json.loads((short_dir / "project.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(resolved.prompt_source, "review_profile")
        self.assertEqual(resolved.profile_id, "short-tomato")
        self.assertTrue(resolved.system.strip())
        self.assertEqual(resolved.prompt_id, "short-tomato")


if __name__ == "__main__":
    unittest.main()
