"""费用汇总 API 测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from infra.billing.cost_summary import summarize_cost_by_book


class CostSummaryTests(unittest.TestCase):
    def test_summarize_groups_by_book_and_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "cost_log.jsonl"
            rows = [
                {"book_id": "book-a", "tag": "writing.main", "cost": 0.1},
                {"book_id": "book-a", "tag": "writing.main", "cost": 0.05},
                {"book_id": "book-a", "tag": "review.platform", "cost": 0.02},
                {"book_id": "book-b", "tag": "prefill.plan", "cost": 0.3},
                {"book_id": "", "tag": "heartbeat", "cost": 0.001},
            ]
            log.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            result = summarize_cost_by_book(log)
            self.assertTrue(result["ok"])
            books = result["by_book"]
            self.assertEqual(len(books), 3)
            self.assertEqual(books[0]["book_id"], "book-b")
            self.assertAlmostEqual(books[0]["total_cost"], 0.3)
            book_a = next(b for b in books if b["book_id"] == "book-a")
            self.assertAlmostEqual(book_a["total_cost"], 0.17)
            self.assertEqual(book_a["steps"][0]["tag"], "writing.main")
            self.assertAlmostEqual(book_a["steps"][0]["cost"], 0.15)

    def test_empty_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing.jsonl"
            result = summarize_cost_by_book(log)
            self.assertEqual(result["by_book"], [])
