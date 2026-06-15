"""聚合 flow 步序测试（不调用 LLM）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import plan_product
from core.data import novel_data
from core.orchestration import flow_runner
from tests.support.path_fixture import apply_path_dict, build_default_paths, restore_paths, snapshot_paths


class FlowRunnerTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        restore_paths(self._path_snap)
        self._tmp.cleanup()

    def test_list_steps_includes_human_gates(self) -> None:
        doc = flow_runner.list_flow_steps()
        ids = {row["id"] for row in doc["steps"]}
        self.assertIn("judgment", ids)
        self.assertIn("adopt_preview", ids)
        self.assertIn("positive_highlight", ids)
        self.assertIn("rhythm_check", ids)
        self.assertIn("review", ids)
        self.assertNotIn("writing_mode", ids)
        self.assertNotIn("fast_chapter_sequence", doc)
        self.assertIn("manual_apis_note", doc)

    def test_chapter_sequence_includes_review(self) -> None:
        seq = flow_runner.chapter_step_ids_for_plan()
        self.assertIn("review", seq)
        self.assertIn("judgment", seq)
        self.assertIn("summary_confirm", seq)

    def test_short_rerun_sequence_skips_summary_confirm(self) -> None:
        from core.data import book_context

        orig_ctx = book_context._context
        try:
            book_context._context = type(
                "Ctx",
                (),
                {
                    "book_id": "test",
                    "data_dir": self.book_dir,
                    "project_file": self.book_dir / "project.json",
                },
            )()
            seq, _ = flow_runner.build_step_sequence(mode="rerun", chapter_num=1)
            self.assertIn("rerun_prepare", seq)
            self.assertNotIn("summary_confirm", seq)
            self.assertIn("finalize", seq)
        finally:
            book_context._context = orig_ctx

    def test_resolve_start_step_empty_chapter(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [{"num": 1, "title": "1", "beat": "a"}],
        }, replace=True)
        self.assertEqual(flow_runner.resolve_chapter_start_step(1), "write")

    def test_continue_mode_drafting_starts_at_review(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [{"num": 1, "title": "1", "beat": "a"}],
        }, replace=True)
        plan_product.set_chapter_status(1, "drafting")
        with unittest.mock.patch(
            "core.orchestration.flow_runner._chapter_body",
            return_value="正文" * 50,
        ):
            seq, chapter = flow_runner.build_step_sequence(mode="continue")
        self.assertEqual(chapter, 1)
        self.assertEqual(seq[0], "review")


if __name__ == "__main__":
    unittest.main()
