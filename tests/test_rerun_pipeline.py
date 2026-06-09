"""P4 重跑流水线测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import plan_product
from core.data import novel_data
from core.orchestration import rerun_pipeline
from infra.state import state
from tests.support.path_fixture import apply_path_dict, build_default_paths, restore_paths, snapshot_paths


class RerunPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.book_dir = self.tmp / "data"
        paths = build_default_paths(self.tmp)
        paths["DATA_DIR"] = self.book_dir
        self.chapters_dir = paths["CHAPTERS_DIR"]
        self._path_snap = snapshot_paths()
        apply_path_dict(paths)
        (self.book_dir / "project.json").write_text(
            json.dumps({"type": "short", "platform": "tomato"}, ensure_ascii=False),
            encoding="utf-8",
        )
        novel_data.PLAN_FILE = self.book_dir / "plan.json"
        novel_data._save_json(novel_data.PLAN_FILE, {"chapters": {}})
        state.write_chapter_num = 0

    def tearDown(self) -> None:
        restore_paths(self._path_snap)
        state.write_chapter_num = 0
        self._tmp.cleanup()

    def _ctx(self) -> SimpleNamespace:
        return SimpleNamespace(
            store=SimpleNamespace(
                paths=SimpleNamespace(chapters_dir=self.chapters_dir),
            ),
        )

    def test_reset_chapter_draft_writes_header(self) -> None:
        path = rerun_pipeline.reset_chapter_draft(
            self.chapters_dir, 2, title="误会",
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn("# 第2章 · 误会", text)

    def test_build_work_queue(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [
                {"num": 1, "title": "1", "beat": "a"},
                {"num": 2, "title": "2", "beat": "b"},
            ],
        }, replace=True)
        plan_product.set_chapter_status(1, "approved")
        plan_product.set_chapter_status(2, "drafting")
        wq = rerun_pipeline.build_work_queue()
        self.assertIn(2, wq["pending_review"])
        self.assertNotIn(1, wq["pending_write"] + wq["pending_review"])
        self.assertEqual(wq.get("pending_summary"), [])

    def test_pending_summary_in_work_queue(self) -> None:
        from core import chapter_summary

        plan_product.apply_prefill_chapters({
            "chapters": [{"num": 2, "title": "2", "beat": "b"}],
        }, replace=True)
        plan_product.set_chapter_status(2, "drafting")
        chapter_summary.save_summary_draft(self.book_dir, 2, "待确认概述")
        wq = rerun_pipeline.build_work_queue(book_dir=self.book_dir)
        self.assertIn(2, wq["pending_summary"])

    def test_plan_partial_apply(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [
                {"num": 1, "title": "旧1", "beat": "a"},
                {"num": 2, "title": "旧2", "beat": "b"},
            ],
        }, replace=True)
        plan_product.set_chapter_status(1, "approved")
        applied = plan_product.apply_prefill_chapters({
            "chapters": [{"num": 2, "title": "新2", "beat": "new beat", "hook": "新钩子"}],
        }, replace=False)
        self.assertEqual(len(applied), 1)
        plan = plan_product.load_plan()
        self.assertEqual(plan["chapters"]["1"]["title"], "旧1")
        self.assertEqual(plan["chapters"]["2"]["title"], "新2")
        self.assertEqual(plan_product.get_chapter_status(plan, 2), "pending")

    def test_chapter_pipeline_clears_draft_and_binds_write(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [
                {"num": 1, "title": "1", "beat": "a"},
                {"num": 2, "title": "2", "beat": "b"},
            ],
        }, replace=True)
        (self.chapters_dir / "ch002.md").write_text("# 第2章\n\n旧正文", encoding="utf-8")

        result = rerun_pipeline.run_pipeline(
            self._ctx(),
            scope="chapter_only",
            current_chapter_num=2,
            auto_plan_llm=False,
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result["write_chapter"]["write_chapter_num"], 2)
        text = (self.chapters_dir / "ch002.md").read_text(encoding="utf-8")
        self.assertNotIn("旧正文", text)
        self.assertIn("# 第2章", text)
        self.assertEqual(state.write_chapter_num, 2)
        self.assertIn("work_queue", result)
        self.assertEqual(result["work_queue"]["primary_chapter"], 2)

    def test_plan_only_pipeline_without_llm(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [
                {"num": 1, "title": "1", "beat": "a"},
                {"num": 2, "title": "2", "beat": "b"},
            ],
        }, replace=True)
        plan_product.set_chapter_status(1, "approved")

        result = rerun_pipeline.run_pipeline(
            self._ctx(),
            scope="plan_only",
            auto_plan_llm=False,
        )
        self.assertTrue(result.get("ok"))
        self.assertTrue(result["plan_rerun"].get("skipped_llm"))
        plan = plan_product.load_plan()
        self.assertEqual(plan_product.get_chapter_status(plan, 2), "pending")
        self.assertEqual(plan_product.get_chapter_status(plan, 1), "approved")


if __name__ == "__main__":
    unittest.main()
