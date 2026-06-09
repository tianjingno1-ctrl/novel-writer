"""产品 Schema 逻辑测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import chapter_precheck
from core import criteria_resolver
from core import deconstruct_store
from core import diagnosis_store
from core import plan_product
from core import profiles
from core import project_lifecycle
from core import prompt_nodes
from core import rerun_scope
from core import taste
from core.data import novel_data


class ProductLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.book_dir = self.tmp / "book-a"
        self.book_dir.mkdir()
        (self.book_dir / "project.json").write_text(
            json.dumps({"type": "short", "platform": "tomato"}, ensure_ascii=False),
            encoding="utf-8",
        )
        taste.TASTE_DIR = self.tmp / "taste"
        taste.GLOBAL_FILE = taste.TASTE_DIR / "global.json"
        taste.EVENTS_FILE = taste.TASTE_DIR / "events.jsonl"
        profiles.PROFILES_DIR = self.tmp / "profiles"
        deconstruct_store.DECONSTRUCT_DIR = self.tmp / "deconstruct"
        novel_data.PLAN_FILE = self.book_dir / "plan.json"
        novel_data._save_json(self.book_dir / "plan.json", {"chapters": {}})

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_taste_v2_migration_and_highlight(self) -> None:
        taste.ensure_taste_dir()
        taste.save_global({
            "preferences": {"hook_patterns": ["前三段强冲突"]},
        })
        doc = taste.load_global()
        self.assertEqual(int(doc.get("version")), 2)
        self.assertTrue(any("强冲突" in r.get("content", "") for r in doc.get("rules") or []))

        pushed = taste.push_highlight_to_taste(
            book_id="book-a",
            chapter_num=1,
            text="她转身时，他抓住了她的手腕。",
            annotation="肢体冲突作钩子",
        )
        self.assertTrue(pushed["example"]["id"].startswith("ex-"))
        doc2 = taste.load_global()
        self.assertEqual(len(doc2.get("examples") or []), 1)

    def test_plan_meta_and_chapter_status(self) -> None:
        meta = plan_product.direction_option_to_meta({
            "id": "A",
            "logline": "误会开局",
            "sell_point": "虐后甜",
            "tone": "甜宠",
            "chapter_count": 5,
        })
        plan_product.set_plan_meta(meta)
        self.assertEqual(plan_product.get_meta().get("logline"), "误会开局")

        plan_product.apply_prefill_chapters({
            "chapters": [
                {"num": 1, "title": "初遇", "beat": "男女主误会", "hook": "他误会是她"},
            ],
        }, replace=True)
        plan = plan_product.load_plan()
        self.assertEqual(plan_product.get_chapter_status(plan, 1), "pending")
        plan_product.set_chapter_status(1, "approved")
        self.assertIn(1, plan_product.locked_chapter_nums())

    def test_profile_criteria_and_resolver(self) -> None:
        profiles.ensure_profiles_dir()
        (profiles.PROFILES_DIR / "tomato_text_editor_v1.yaml").write_text(
            "id: tomato_text_editor_v1\nchecks:\n  hard:\n    - id: p_hard_001\n      content: 首章必须有冲突\n",
            encoding="utf-8",
        )
        criteria = profiles.build_criteria_from_profile("tomato_text_editor_v1")
        plan_product.set_review_criteria(criteria)
        resolved = criteria_resolver.resolve_review_criteria(
            plan_product.load_plan(),
            book_dir=self.book_dir,
        )
        self.assertEqual(len(resolved["hard"]), 1)
        self.assertIn("冲突", resolved["hard"][0]["content"])

    def test_precheck_word_count(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [{
                "num": 1,
                "title": "第一章",
                "beat": "男女主误会",
                "hook": "结尾反转",
                "word_count_target": 2000,
            }],
        }, replace=True)
        plan = plan_product.load_plan()
        short = chapter_precheck.run_precheck(chapter_num=1, content="太短", plan=plan)
        self.assertFalse(short["ok"])
        long_text = "男女主误会" + ("内容" * 900)
        ok = chapter_precheck.run_precheck(chapter_num=1, content=long_text, plan=plan)
        self.assertTrue(ok["ok"])

    def test_rerun_impact_preview(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [
                {"num": 1, "title": "1", "beat": "a"},
                {"num": 2, "title": "2", "beat": "b"},
                {"num": 3, "title": "3", "beat": "c"},
            ],
        }, replace=True)
        plan_product.set_chapter_status(1, "approved")
        preview = rerun_scope.build_impact_preview(
            plan_product.load_plan(),
            scope="plan_only",
        )
        self.assertIn("锁定", preview)
        self.assertIn("1", preview)

    def test_diagnosis_decide_writes_override(self) -> None:
        doc = diagnosis_store.create_pending(
            self.book_dir,
            book_id="book-a",
            analysis="钩子弱",
            patch={
                "target_node": "writing.main",
                "diff_preview": "加强钩子",
                "override": {"prepend": "", "append": "章首100字内给冲突", "system": None},
            },
        )
        result = diagnosis_store.decide(
            self.book_dir,
            doc["id"],
            accepted=True,
            rerun_scope="none",
            apply_override=True,
        )
        self.assertTrue(result.get("ok"))
        resolved = prompt_nodes.resolve_node("writing.main", book_dir=self.book_dir)
        self.assertIn("章首100字", resolved.system)

    def test_deconstruct_elevate(self) -> None:
        doc = deconstruct_store.create_from_deconstruct_reply(
            book_id="book-a",
            quality_log_id="ql-1",
            reply="钩子：误会开局\n结构：每章小反转",
            source_title="爆文",
        )
        result = deconstruct_store.elevate_to_taste(doc["id"], book_dir=self.book_dir)
        self.assertTrue(result.get("ok"))
        rules = taste.load_global().get("rules") or []
        self.assertGreaterEqual(len(rules), 1)
        refs = project_lifecycle.get_lifecycle(self.book_dir).get("deconstruct_refs") or []
        self.assertIn(doc["id"], refs)

    def test_rerun_execute(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [
                {"num": 1, "title": "1", "beat": "a"},
                {"num": 2, "title": "2", "beat": "b"},
            ],
        }, replace=True)
        plan_product.set_chapter_status(1, "approved")
        from core import rerun_execute

        result = rerun_execute.execute(scope="from_chapter_n", from_chapter_num=2)
        self.assertTrue(result.get("ok"))
        plan = plan_product.load_plan()
        self.assertEqual(plan_product.get_chapter_status(plan, 1), "approved")
        self.assertEqual(plan_product.get_chapter_status(plan, 2), "drafting")

    def test_summary_confirm(self) -> None:
        from core import chapter_summary

        plan_product.apply_prefill_chapters({
            "chapters": [{"num": 1, "title": "1", "beat": "a"}],
        }, replace=True)
        chapter_summary.save_summary_draft(self.book_dir, 1, "本章概述测试")
        result = chapter_summary.confirm_summary(self.book_dir, 1, push_highlights=False, book_id="book-a")
        self.assertTrue(result.get("ok"))
        self.assertEqual(plan_product.get_chapter_status(plan_product.load_plan(), 1), "approved")

    def test_migrate_legacy_brief(self) -> None:
        brief = self.book_dir / "brief.md"
        brief.write_text("旧方向摘要：霸总追妻", encoding="utf-8")
        self.assertTrue(plan_product.migrate_legacy_brief(self.book_dir))
        meta = plan_product.get_meta()
        self.assertIn("霸总追妻", meta.get("logline", ""))
        self.assertTrue(meta.get("migrated_from_brief"))
        self.assertFalse(plan_product.migrate_legacy_brief(self.book_dir))

    def test_highlights_extract(self) -> None:
        from core.orchestration import highlights as h

        pushed = h.push_on_review_pass(
            book_id="book-a", chapter_num=1, note="开头钩子非常有效，读者会想继续看",
        )
        self.assertIsNotNone(pushed)
        self.assertTrue(pushed["example"]["id"].startswith("ex-"))

    def test_prompt_prepend_append(self) -> None:
        prompt_nodes.merge_node_override(
            self.book_dir,
            "writing.main",
            {"append": "【追加规则】每段不超过三句"},
        )
        resolved = prompt_nodes.resolve_node("writing.main", book_dir=self.book_dir)
        self.assertIn("【追加规则】", resolved.system)


if __name__ == "__main__":
    unittest.main()
