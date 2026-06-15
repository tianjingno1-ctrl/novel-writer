"""review.json 结构化 gaps 解析。"""

from __future__ import annotations

import unittest

from core import review_gaps


class ReviewGapsTests(unittest.TestCase):
    def _resolved(self) -> dict:
        return {
            "hard": [
                {
                    "ref": "global:hook_strong",
                    "content": "前三段须有强钩子",
                    "weight": "hard",
                },
            ],
            "soft": [
                {
                    "ref": "local:pace_ok",
                    "content": "节奏不宜拖沓",
                    "weight": "soft",
                },
            ],
        }

    def test_parse_json_gaps_block(self) -> None:
        text = """## 审阅
钩子偏弱。

```json
{"gaps":[
  {"rule_ref":"global:hook_strong","description":"钩子出现在第450字","severity":"hard"}
]}
```"""
        gaps = review_gaps.parse_gaps_from_review(text, self._resolved())
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["rule_ref"], "global:hook_strong")
        self.assertIn("450", gaps[0]["description"])
        self.assertEqual(gaps[0]["severity"], "hard")

    def test_parse_line_with_ref(self) -> None:
        text = "- [global:hook_strong] 钩子出现过晚，读者可能划走"
        gaps = review_gaps.parse_gaps_from_review(text, self._resolved())
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["rule_ref"], "global:hook_strong")

    def test_empty_gaps_json(self) -> None:
        text = '全部达标。\n```json\n{"gaps":[]}\n```'
        gaps = review_gaps.parse_gaps_from_review(text, self._resolved())
        self.assertEqual(gaps, [])

    def test_json_gaps_skip_passing_items(self) -> None:
        text = """```json
{"gaps":[
  {"rule_ref":"global:hook_strong","description":"钩子成立 ✅","severity":"hard"},
  {"rule_ref":"local:pace_ok","description":"节奏偏弱，中段拖沓","severity":"soft"}
]}
```"""
        gaps = review_gaps.parse_gaps_from_review(text, self._resolved())
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["rule_ref"], "local:pace_ok")

    def test_gap_looks_passing(self) -> None:
        self.assertTrue(review_gaps.gap_looks_passing("首章核心冲突 ✅"))
        self.assertFalse(review_gaps.gap_looks_passing("结尾悬念偏弱"))
        self.assertFalse(review_gaps.gap_looks_passing("结尾悬念未通过"))
        self.assertTrue(review_gaps.gap_looks_passing("钩子强度通过"))

    def test_append_round_filters_passing_gaps(self) -> None:
        from core import chapter_review
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            book_dir = Path(tmp)
            chapter_review.append_round(
                book_dir,
                1,
                quality_log_id="ql-filter",
                gaps=[
                    {
                        "rule_ref": "global:hook_strong",
                        "description": "钩子成立 ✅",
                        "severity": "hard",
                    },
                    {
                        "rule_ref": "local:pace_ok",
                        "description": "节奏偏弱",
                        "severity": "soft",
                    },
                ],
            )
            doc = chapter_review.load_review(book_dir, 1)
            assert doc is not None
            stored = doc["rounds"][0]["gaps"]
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["rule_ref"], "local:pace_ok")

    def test_append_round_stores_gaps(self) -> None:
        from core import chapter_review
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            book_dir = Path(tmp)
            gaps = [
                {
                    "rule_ref": "global:hook_strong",
                    "description": "钩子偏弱",
                    "severity": "hard",
                },
            ]
            chapter_review.append_round(
                book_dir,
                2,
                quality_log_id="ql-gaps",
                gaps=gaps,
            )
            doc = chapter_review.load_review(book_dir, 2)
            assert doc is not None
            self.assertEqual(doc["rounds"][0]["gaps"], gaps)


    def test_format_gaps_revise_note(self) -> None:
        note = review_gaps.format_gaps_revise_note(
            [
                {
                    "rule_ref": "global:hook_strong",
                    "description": "开篇钩子偏弱",
                    "severity": "hard",
                },
            ],
            review_excerpt="整体节奏尚可。",
        )
        self.assertIn("开篇钩子偏弱", note)
        self.assertIn("global:hook_strong", note)
        self.assertIn("审阅摘要", note)


if __name__ == "__main__":
    unittest.main()
