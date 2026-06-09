"""Prompt 归因测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import prompt_diagnose
from infra.logs import quality as quality_log


class PromptDiagnoseTests(unittest.TestCase):
    def test_heuristic_from_tags(self) -> None:
        evidence = prompt_diagnose.collect_evidence([
            {
                "id": "log1",
                "kind": "female_fiction_review",
                "chapter_num": 1,
                "summary": "审阅",
                "body": "钩子弱",
                "extra": {
                    "outcome": "rejected",
                    "issue_tags": ["hook_weak", "ai_tone"],
                    "prompt_node": "review.platform",
                },
            },
        ])
        diag = prompt_diagnose.heuristic_diagnosis(evidence)
        suspects = diag.get("suspects") or []
        self.assertGreaterEqual(len(suspects), 1)
        node_ids = [s["node_id"] for s in suspects]
        self.assertTrue(
            any(n in node_ids for n in ("writing.main", "prefill.plan", "review.platform"))
        )

    def test_kind_to_node_fallback(self) -> None:
        row = {"kind": "prefill_direction", "extra": {}}
        self.assertEqual(prompt_diagnose.node_for_log_entry(row), "prefill.direction")

    def test_parse_diagnose_json(self) -> None:
        text = '分析如下\n{"summary":"test","suspects":[]}'
        data = prompt_diagnose.parse_diagnose_payload(text)
        self.assertEqual(data["summary"], "test")

    def test_apply_patch_append(self) -> None:
        out = prompt_diagnose.apply_patch_preview(
            "base prompt",
            "章末必须有钩子",
            patch_mode="append",
        )
        self.assertIn("章末必须有钩子", out)
        self.assertIn("base prompt", out)

    def test_collect_bad_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            quality_log.init_quality_log(Path(tmp))
            eid = quality_log.append_entry(
                "female_fiction_review",
                1,
                "report",
                extra={"outcome": "rejected", "issue_tags": ["hook_weak"]},
            )
            rows = []
            for preview in quality_log.list_entries(limit=10):
                full = quality_log.get_entry(preview["id"])
                if full:
                    extra = full.get("extra") or {}
                    if extra.get("issue_tags"):
                        rows.append(full)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], eid)


if __name__ == "__main__":
    unittest.main()
