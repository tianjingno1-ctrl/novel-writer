"""聚合 flow runner 测试（不调用 LLM）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def _ctx(self) -> SimpleNamespace:
        return SimpleNamespace(
            store=SimpleNamespace(
                paths=SimpleNamespace(
                    chapters_dir=self.chapters_dir,
                    data_dir=self.book_dir,
                ),
            ),
        )

    def test_list_steps_includes_human_gates(self) -> None:
        doc = flow_runner.list_flow_steps()
        ids = {row["id"] for row in doc["steps"]}
        self.assertIn("judgment", ids)
        self.assertIn("adopt_preview", ids)
        self.assertIn("manual_apis_note", doc)

    def test_resolve_start_step_empty_chapter(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [{"num": 1, "title": "1", "beat": "a"}],
        }, replace=True)
        self.assertEqual(flow_runner.resolve_chapter_start_step(1), "write")

    def test_stop_after_precheck(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [{
                "num": 1,
                "title": "第一章",
                "beat": "男女主误会",
                "hook": "结尾反转",
                "word_count_target": 2000,
            }],
        }, replace=True)
        body = "男女主误会" + ("内容" * 900)
        (self.chapters_dir / "ch001.md").write_text(f"# 第1章\n\n{body}", encoding="utf-8")

        result = flow_runner.run_flow(
            self._ctx(),
            mode="chapter",
            chapter_num=1,
            from_step="precheck",
            stop_after="precheck",
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("stop_reason"), "stop_after")
        self.assertEqual(result.get("stopped_at"), "precheck")
        self.assertEqual(len(result.get("executed") or []), 1)
        self.assertTrue(result["executed"][0].get("ok"))

    def test_human_gate_stops_before_judgment(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [{"num": 1, "title": "1", "beat": "a"}],
        }, replace=True)
        body = "男女主误会" + ("内容" * 900)
        (self.chapters_dir / "ch001.md").write_text(f"# 第1章\n\n{body}", encoding="utf-8")

        fake_review = {
            "ok": True,
            "log_id": "ql-test-1",
            "reply": "审阅通过",
            "chapter_num": 1,
        }
        with patch(
            "core.orchestration.female_fiction.run_female_fiction_review",
            return_value=fake_review,
        ):
            result = flow_runner.run_flow(
                self._ctx(),
                mode="chapter",
                chapter_num=1,
                from_step="review",
            )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("stop_reason"), "human_gate")
        self.assertEqual(result.get("stopped_at"), "judgment")
        self.assertEqual(result.get("log_id"), "ql-test-1")
        self.assertIn("manual_apis_note", result)

    def test_rerun_mode_stop_after_prepare(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [
                {"num": 1, "title": "1", "beat": "a"},
                {"num": 2, "title": "2", "beat": "b"},
            ],
        }, replace=True)
        plan_product.set_chapter_status(1, "approved")

        result = flow_runner.run_flow(
            self._ctx(),
            mode="rerun",
            scope="from_chapter_n",
            from_chapter_num=2,
            stop_after="rerun_prepare",
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("stop_reason"), "stop_after")
        plan = plan_product.load_plan()
        self.assertEqual(plan_product.get_chapter_status(plan, 2), "drafting")


if __name__ == "__main__":
    unittest.main()
