"""稿件 E4b 投递类型测试。"""

from __future__ import annotations

import tempfile
import unittest

from core import manuscript


class ManuscriptSubmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        manuscript.MANUSCRIPTS_DIR = __import__("pathlib").Path(self._tmp.name)
        manuscript.INDEX_FILE = manuscript.MANUSCRIPTS_DIR / "index.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_invalid_target_rejected(self) -> None:
        created = manuscript.create_from_book(book_id="b1", title="测试")
        ms_id = created["manuscript"]["id"]
        bad = manuscript.update_manuscript(ms_id, {
            "submission": {"target": "manga", "result": "pending"},
        })
        self.assertFalse(bad.get("ok"))

    def test_reject_submission_fields(self) -> None:
        created = manuscript.create_from_book(book_id="b1", title="测试")
        ms_id = created["manuscript"]["id"]
        manuscript.transition_state(ms_id, "complete")
        ok = manuscript.update_manuscript(ms_id, {
            "submission": {
                "target": "text_editor",
                "target_name": "番茄",
                "platform_profile": "tomato_text_editor_v1",
                "result": "rejected",
                "reject_tags": ["pacing_slow"],
                "reject_reason": "节奏慢",
            },
        })
        self.assertTrue(ok.get("ok"))
        doc = ok["manuscript"]
        sub = doc["submissions"][-1]
        self.assertEqual(sub["target"], "text_editor")
        self.assertTrue(sub.get("pushed_to_taste"))

    def test_pending_submission_merge_on_result(self) -> None:
        created = manuscript.create_from_book(book_id="b1", title="测试")
        ms_id = created["manuscript"]["id"]
        manuscript.transition_state(ms_id, "complete")
        manuscript.update_manuscript(ms_id, {
            "submission": {
                "target": "text_editor",
                "compliance_checked": True,
            },
        })
        ok = manuscript.update_manuscript(ms_id, {
            "submission": {"result": "passed"},
        })
        self.assertTrue(ok.get("ok"))
        doc = ok["manuscript"]
        self.assertEqual(len(doc["submissions"]), 1)
        self.assertEqual(doc["submissions"][0]["result"], "passed")
        self.assertEqual(doc["state"], "result")

    def test_list_enriches_last_submission(self) -> None:
        created = manuscript.create_from_book(book_id="b1", title="测试")
        ms_id = created["manuscript"]["id"]
        manuscript.transition_state(ms_id, "complete")
        manuscript.update_manuscript(ms_id, {
            "submission": {
                "target": "text_editor",
                "result": "rejected",
                "reject_tags": ["ai_tone"],
                "reject_reason": "AI 味重",
            },
        })
        manuscript.patch_last_submission(ms_id, {"diagnosis_id": "diag-test-1"})
        rows = manuscript.list_manuscripts()
        self.assertEqual(len(rows), 1)
        sub = rows[0]["submission"]
        self.assertEqual(sub["result"], "rejected")
        self.assertEqual(sub["diagnosis_id"], "diag-test-1")
        self.assertEqual(sub["reject_tags"], ["ai_tone"])


if __name__ == "__main__":
    unittest.main()
