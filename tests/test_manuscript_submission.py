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


if __name__ == "__main__":
    unittest.main()
