"""合规预检、读者留存、作者风格资产。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import author_profile
from core import chapter_precheck
from core import compliance
from core import plan_product
from core import reader_retention
from core.data import novel_data


class ComplianceRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.book_dir = self.tmp / "data"
        self.book_dir.mkdir(parents=True)
        novel_data.PLAN_FILE = self.book_dir / "plan.json"
        novel_data._save_json(novel_data.PLAN_FILE, {"chapters": {}})
        self._author_path = author_profile.AUTHOR_PROFILE_FILE
        author_profile.AUTHOR_PROFILE_FILE = self.tmp / "author_profile.json"

    def tearDown(self) -> None:
        author_profile.AUTHOR_PROFILE_FILE = self._author_path
        self._tmp.cleanup()

    def test_ai_tone_blocks_when_over_threshold(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [{"num": 1, "title": "1", "beat": "测试", "word_count_target": 500}],
        }, replace=True)
        plan = plan_product.load_plan()
        text = "仿佛" * 30 + "不禁" * 20 + "测试内容" * 50
        result = chapter_precheck.run_precheck(
            chapter_num=1,
            content=text,
            plan=plan,
            platform="tomato",
        )
        codes = [i.get("code") for i in result.get("issues") or []]
        self.assertIn("ai_tone_high", codes)
        self.assertFalse(result["ok"])

    def test_reader_preview_and_rhythm_warning(self) -> None:
        analysis = reader_retention.analyze_reader_perspective(
            "测试" * 200,
            chapter_num=1,
        )
        self.assertIn(analysis["payoff_density"], ("low", "medium", "high"))
        reader_retention.save_retention(self.book_dir, 1, {
            **analysis,
            "drop_off_risk": "high",
        })
        reader_retention.save_retention(self.book_dir, 2, {
            **analysis,
            "chapter_num": 2,
            "drop_off_risk": "high",
        })
        reader_retention.save_retention(self.book_dir, 3, {
            **analysis,
            "chapter_num": 3,
            "drop_off_risk": "high",
        })
        warn = reader_retention.check_rhythm_warning(self.book_dir, [1, 2, 3], window=3)
        self.assertTrue(warn.get("warning"))

    def test_author_profile_extract_and_apply(self) -> None:
        taste_doc = {
            "rules": [{"content": "章末留钩子", "weight": "soft"}],
            "preferences": {"hook_patterns": ["反差开场"]},
            "examples": [{"tags": ["心动"], "annotation": "被看见"}],
            "reader_pattern": {"good_emotions": ["扬眉"]},
        }
        saved = author_profile.extract_from_book(
            book_id="b1",
            book_title="测试书",
            taste_doc=taste_doc,
            reader_pattern=taste_doc["reader_pattern"],
        )
        self.assertGreaterEqual(len(saved.get("rules") or []), 1)
        applied = author_profile.apply_to_book_taste({}, inherit_all=True)
        self.assertTrue(applied.get("rules"))
        self.assertIn("reader_pattern", applied)

    def test_compliance_scan(self) -> None:
        chapters = [
            (1, "正常正文" * 100),
            (2, "仿佛不禁" * 40 + "正文" * 50),
        ]
        scan = compliance.scan_chapters_compliance(chapters, platform="tomato")
        self.assertTrue(scan.get("ok"))
        self.assertGreaterEqual(len(scan.get("high_risk_chapters") or []), 1)


if __name__ == "__main__":
    unittest.main()
