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
        from core.data import book_context

        taste.ensure_taste_dir()
        taste.save_global({
            "preferences": {"hook_patterns": ["前三段强冲突"]},
        })
        doc = taste.load_global()
        self.assertEqual(int(doc.get("version")), 2)
        self.assertTrue(any("强冲突" in r.get("content", "") for r in doc.get("rules") or []))

        orig_books = book_context.BOOKS_DIR
        try:
            book_context.BOOKS_DIR = self.tmp
            pushed = taste.push_highlight_to_taste(
                book_id="book-a",
                chapter_num=1,
                text="她转身时，他抓住了她的手腕。",
                annotation="肢体冲突作钩子",
            )
        finally:
            book_context.BOOKS_DIR = orig_books

        self.assertTrue(pushed["example"]["id"].startswith("ex-"))
        self.assertEqual(pushed.get("scope"), "book")
        doc2 = taste.load_global()
        self.assertEqual(len(doc2.get("examples") or []), 0)
        book_taste = taste.load_book_taste(self.book_dir)
        append_examples = (book_taste.get("overrides") or {}).get("append_examples") or []
        self.assertEqual(len(append_examples), 1)
        self.assertIn("手腕", append_examples[0].get("text", ""))

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

        plan_product.set_plan_meta({"genre": "sweet", "wizard_step": "reference"})
        merged = plan_product.get_meta()
        self.assertEqual(merged.get("logline"), "误会开局")
        self.assertEqual(merged.get("genre"), "sweet")
        self.assertEqual(merged.get("wizard_step"), "reference")
        plan_product.set_plan_meta({"genre": "invalid"})
        self.assertEqual(plan_product.get_meta().get("genre"), "")

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

    def test_decide_diagnosis_run_rerun_pipeline_not_shadowed(self) -> None:
        from unittest.mock import MagicMock, patch

        from core.orchestration import product as product_orch

        doc = diagnosis_store.create_pending(
            self.book_dir,
            book_id="book-a",
            analysis="节奏平",
            patch={
                "target_node": "writing.main",
                "override": {"append": "加快节奏"},
            },
        )
        ctx = MagicMock()
        ctx.store.paths.data_dir = self.book_dir
        mock_rerun = MagicMock(return_value={"ok": True, "affected_chapters": [1]})
        with patch.object(product_orch, "execute_rerun", mock_rerun):
            result = product_orch.decide_diagnosis(
                ctx,
                doc["id"],
                accepted=True,
                rerun_scope_name="chapter_only",
                from_chapter_num=1,
                apply_override=False,
                run_rerun_pipeline=True,
            )
        self.assertTrue(result.get("ok"), result.get("error"))
        mock_rerun.assert_called_once()

    def test_story_context_skips_world_placeholder(self) -> None:
        from core import story_context

        plan = {
            "meta": {
                "title": "离婚当天",
                "logline": "女主离婚后逆袭",
                "genre": "urban",
            },
            "chapters": {
                "1": {
                    "title": "签字",
                    "hook": "跑车钩子",
                    "scenes": [{"beat": "离婚现场"}],
                },
            },
        }
        placeholder = (
            "- **类型**：快穿\n"
            "- **主角**：【女主名】，绑定系统，穿越各个世界完成任务\n"
        )
        block = story_context.build_story_context_block(
            plan, placeholder, chapter_num=1,
        )
        self.assertIn("urban", block)
        self.assertIn("离婚当天", block)
        self.assertNotIn("绑定系统", block)

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

    def test_short_finalize_skips_summary_and_approves(self) -> None:
        from app.factories import short_story_archive_skip
        from core.deps import LlmHooks, MaintainDeps, QualityHooks
        from core.orchestration.finalize import FinalizeHooks, run_post_chapter_finalize
        from tests.support.isolated_library import make_persist_deps, store_only_library

        plan_product.apply_prefill_chapters({
            "chapters": [{"num": 1, "title": "1", "beat": "a"}],
        }, replace=True)
        plan_product.set_chapter_status(1, "drafting")
        plan_snapshot = plan_product.load_plan()

        with store_only_library(self.tmp) as (bctx, store):
            (bctx.data_dir / "project.json").write_text(
                json.dumps({"type": "short", "platform": "tomato"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (bctx.data_dir / "chapters" / "ch001.md").write_text(
                "# 第1章\n\n" + "正文足够长。" * 20,
                encoding="utf-8",
            )
            novel_data.PLAN_FILE = bctx.data_dir / "plan.json"
            novel_data._save_json(bctx.data_dir / "plan.json", plan_snapshot)

            from core.data import book_context

            orig_ctx = book_context._context
            try:
                book_context._context = bctx
                hooks = FinalizeHooks(
                    maintain_deps=make_persist_deps(store),
                    llm=LlmHooks(
                        build_cached_system=lambda *a, **k: "",
                        call_api=lambda *a, **k: None,
                        get_last_call_info=lambda: {},
                    ),
                    resolve_chapter=lambda n: (n or 1, "正文"),
                    short_story_skip=short_story_archive_skip,
                    chapters_text_for_scope=lambda *a, **k: None,
                    load_check_snapshot=lambda *a, **k: object(),
                    read_summaries_recent=lambda: "",
                    run_pacing_check=lambda: {"ok": True},
                    run_outline=lambda: {"ok": True},
                    quality_log_entry=lambda *a, **k: None,
                )
                result = run_post_chapter_finalize(1, hooks)
            finally:
                book_context._context = orig_ctx

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("skipped"))
        self.assertTrue(result.get("chapter_complete"))
        self.assertTrue(result.get("summary_skipped"))
        self.assertEqual(plan_product.get_chapter_status(plan_product.load_plan(), 1), "approved")

    def test_short_pending_summary_empty(self) -> None:
        from core import chapter_summary
        from core.data import book_context

        orig_ctx = book_context._context
        try:
            book_context._context = type(
                "Ctx",
                (),
                {"data_dir": self.book_dir, "project_file": self.book_dir / "project.json"},
            )()
            self.assertEqual(chapter_summary.list_pending_summary_nums(self.book_dir), [])
        finally:
            book_context._context = orig_ctx

    def test_short_prior_chapters_in_context(self) -> None:
        from core import context as writing_context
        from core.data import book_context
        from tests.support.isolated_library import _test_read_text, store_only_library

        with store_only_library(self.tmp) as (bctx, _store):
            (bctx.data_dir / "project.json").write_text(
                json.dumps({"type": "short", "platform": "tomato"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (bctx.data_dir / "summaries_recent.md").write_text(
                "不应注入的概述",
                encoding="utf-8",
            )
            (bctx.data_dir / "chapters" / "ch001.md").write_text(
                "# 第1章\n\n第一章正文。",
                encoding="utf-8",
            )
            orig_ctx = book_context._context
            try:
                book_context._context = bctx
                writing_context.bind(
                    writing_context.BookPaths.from_book_context(bctx),
                    read_text=_test_read_text,
                )
                parts = writing_context.collect_dynamic_layer_parts(chapter_num=2)
            finally:
                book_context._context = orig_ctx

        ids = [p["id"] for p in parts]
        self.assertIn("prior_chapters", ids)
        self.assertNotIn("summaries_recent", ids)
        prior = next(p for p in parts if p["id"] == "prior_chapters")
        self.assertIn("第一章正文", prior["content"])

    def test_short_count_summaries_and_outline_ready(self) -> None:
        from core import context as writing_context
        from core.data import book_context
        from tests.support.isolated_library import _test_read_text, store_only_library

        body = "正文足够长。" * 20
        with store_only_library(self.tmp) as (bctx, _store):
            (bctx.data_dir / "project.json").write_text(
                json.dumps({"type": "short", "platform": "tomato"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (bctx.data_dir / "chapters" / "ch001.md").write_text(
                f"# 第1章\n\n{body}",
                encoding="utf-8",
            )
            orig_ctx = book_context._context
            try:
                book_context._context = bctx
                writing_context.bind(
                    writing_context.BookPaths.from_book_context(bctx),
                    read_text=_test_read_text,
                )
                self.assertEqual(writing_context.count_short_written_chapters(), 1)
                self.assertEqual(writing_context.count_summaries(), 1)
                recall = writing_context.get_summaries_combined_for_snapshot(2)
                self.assertIn("正文足够长", recall)
            finally:
                book_context._context = orig_ctx

    def test_short_snapshot_recall(self) -> None:
        from tests.support.isolated_library import store_only_library

        body = "第一章完整正文。" * 15
        with store_only_library(self.tmp) as (bctx, store):
            (bctx.data_dir / "project.json").write_text(
                json.dumps({"type": "short"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (bctx.data_dir / "chapters" / "ch001.md").write_text(
                f"# 第1章\n\n{body}",
                encoding="utf-8",
            )
            from core.data import book_context

            orig_ctx = book_context._context
            try:
                book_context._context = bctx
                snap = store.load_snapshot(2, for_purpose="check")
                self.assertIn("第一章完整正文", snap.summaries_combined)
                self.assertEqual(store.count_summaries(), 1)
            finally:
                book_context._context = orig_ctx

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

    def test_chapter_review_rounds_and_judgment(self) -> None:
        from core import chapter_review

        chapter_review.append_round(
            self.book_dir,
            1,
            quality_log_id="ql-001",
            profile_id="short-tomato",
            review_excerpt="钩子偏弱，建议加强冲突",
            judgment="pending",
        )
        doc = chapter_review.load_review(self.book_dir, 1)
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertEqual(len(doc.get("rounds") or []), 1)
        self.assertEqual(doc["rounds"][0]["quality_log_id"], "ql-001")

        updated = chapter_review.update_round_by_log_id(
            self.book_dir,
            1,
            "ql-001",
            judgment="accepted",
            issue_tags=["hook_weak"],
            user_note="需改稿",
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["rounds"][0]["judgment"], "pass")
        self.assertIn("hook_weak", updated["rounds"][0]["issue_tags"])

    def test_prompt_merge_clears_empty_append(self) -> None:
        prompt_nodes.merge_node_override(
            self.book_dir,
            "writing.main",
            {"append": "临时规则"},
        )
        prompt_nodes.merge_node_override(self.book_dir, "writing.main", {"append": ""})
        doc = prompt_nodes.load_overrides_doc(self.book_dir)
        self.assertNotIn("writing.main", doc.get("nodes") or {})


if __name__ == "__main__":
    unittest.main()
