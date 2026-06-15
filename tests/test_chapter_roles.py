"""chapter.role 契约与 A9 序列校验。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import chapter_roles
from core import plan_product
from core.data import novel_data


def _short_plan(chapters: list[dict], *, paywall_chapter: int | None = None) -> dict:
    meta: dict = {}
    if paywall_chapter is not None:
        meta["paywall_chapter"] = paywall_chapter
    ch_map: dict = {}
    for ch in chapters:
        num = ch["num"]
        ch_map[str(num)] = {
            "title": f"第{num}章",
            "role": ch["role"],
            "scenes": [],
        }
        if ch.get("intent"):
            ch_map[str(num)]["intent"] = ch["intent"]
    return {"version": 2, "meta": meta, "chapters": ch_map}


class ChapterRolesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.book_dir = Path(self._tmp.name) / "book"
        self.book_dir.mkdir()
        novel_data.PLAN_FILE = self.book_dir / "plan.json"
        novel_data._save_json(novel_data.PLAN_FILE, {"chapters": {}})

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_paywall_side(self) -> None:
        self.assertEqual(chapter_roles.paywall_side(3, 9), "pre")
        self.assertEqual(chapter_roles.paywall_side(9, 9), "pre")
        self.assertEqual(chapter_roles.paywall_side(10, 9), "post")
        self.assertIsNone(chapter_roles.paywall_side(1, None))

    def test_valid_short_sequence_passes(self) -> None:
        plan = _short_plan([
            {"num": 1, "role": "hook_open"},
            {"num": 2, "role": "buildup"},
            {"num": 3, "role": "buildup"},
            {"num": 4, "role": "escalation"},
            {"num": 5, "role": "paywall"},
            {"num": 6, "role": "paid_open"},
            {"num": 7, "role": "climax"},
            {"num": 8, "role": "bridge"},
            {"num": 9, "role": "buildup"},
            {"num": 10, "role": "finale"},
        ], paywall_chapter=5)
        issues = chapter_roles.validate_plan_sequence(plan, book_type="short")
        self.assertEqual(chapter_roles.validation_errors(issues), [])

    def test_paywall_errors(self) -> None:
        plan = _short_plan([
            {"num": 1, "role": "hook_open"},
            {"num": 2, "role": "buildup"},
            {"num": 3, "role": "paywall"},
        ])
        issues = chapter_roles.validate_plan_sequence(plan, book_type="short")
        codes = {i["code"] for i in chapter_roles.validation_errors(issues)}
        self.assertIn("paid_open_count", codes)
        self.assertIn("paywall_position_edge", codes)
        self.assertIn("anchor_last_not_finale", codes)

    def test_no_roles_skips_paywall_checks(self) -> None:
        plan = {
            "version": 2,
            "meta": {},
            "chapters": {
                "1": {"title": "第一章", "scenes": []},
                "2": {"title": "第二章", "scenes": []},
            },
        }
        issues = chapter_roles.validate_plan_sequence(plan, book_type="short")
        self.assertEqual(issues, [])

    def test_apply_prefill_persists_role_and_paywall_meta(self) -> None:
        plan_product.apply_prefill_chapters({
            "chapters": [
                {
                    "num": 1,
                    "title": "开篇",
                    "beat": "钩子",
                    "role": "hook_open",
                    "intent": {"ai_suggest": "偷听+愤怒", "final": "配方A"},
                },
                {
                    "num": 2,
                    "title": "切割",
                    "beat": "悬念",
                    "role": "paywall",
                    "intent": {"final": "必须知道真相"},
                },
            ],
        }, replace=True)
        plan = plan_product.load_plan()
        ch1 = plan["chapters"]["1"]
        self.assertEqual(ch1["role"], "hook_open")
        self.assertEqual(ch1["intent"]["kind"], "hook_open")
        self.assertEqual(ch1["intent"]["final"], "配方A")
        self.assertEqual(plan["meta"]["paywall_chapter"], 2)
        self.assertEqual(plan["chapters"]["2"]["role"], "paywall")
        self.assertEqual(plan["chapters"]["2"]["intent"]["kind"], "paywall")

    def test_normalize_prefill_chapter(self) -> None:
        ch = chapter_roles.normalize_prefill_chapter({
            "num": 1,
            "role": "HOOK_OPEN",
            "intent_ai_suggest": "偷听+愤怒",
        })
        self.assertEqual(ch["role"], "hook_open")
        self.assertEqual(ch["intent"]["kind"], "hook_open")
        self.assertEqual(ch["intent"]["ai_suggest"], "偷听+愤怒")

        paid = chapter_roles.normalize_prefill_chapter({
            "num": 2,
            "role": "paid_open",
            "intent": {"ai_suggest": "ignored"},
        })
        self.assertEqual(paid["role"], "paid_open")
        self.assertNotIn("intent", paid)

    def test_normalize_prefill_plan_payload(self) -> None:
        payload = chapter_roles.normalize_prefill_plan_payload({
            "options": [{
                "id": "A",
                "chapters": [
                    {"num": 1, "role": "hook_open", "intent": {"ai_suggest": "x"}},
                ],
            }],
        })
        ch = payload["options"][0]["chapters"][0]
        self.assertEqual(ch["role"], "hook_open")
        self.assertEqual(ch["intent"]["ai_suggest"], "x")

    def test_build_plan_preview_blocks_invalid_apply(self) -> None:
        existing = plan_product.load_plan()
        option = {
            "chapters": [
                {"num": 1, "role": "buildup", "title": "错锚"},
                {"num": 2, "role": "paywall", "title": "切割"},
            ],
        }
        preview = chapter_roles.build_plan_preview(existing, option, replace=True)
        issues = chapter_roles.validate_plan_sequence(preview, book_type="short")
        self.assertTrue(chapter_roles.validation_errors(issues))

    def test_bow_flat_buildup_warns(self) -> None:
        same_intent = {
            "kind": "buildup",
            "final": {"conditions": "加班", "emotions": "憋屈"},
        }
        plan = _short_plan([
            {"num": 1, "role": "hook_open"},
            {"num": 2, "role": "buildup", "intent": same_intent},
            {"num": 3, "role": "buildup", "intent": dict(same_intent)},
            {"num": 4, "role": "escalation", "intent": {
                "kind": "escalation",
                "final": {"debt": "长期被忽视", "trigger": "一句谢谢"},
            }},
            {"num": 5, "role": "paywall"},
            {"num": 6, "role": "paid_open"},
            {"num": 7, "role": "finale"},
        ], paywall_chapter=5)
        issues = chapter_roles.validate_plan_sequence(plan, book_type="short")
        codes = {i["code"] for i in chapter_roles.validation_warnings(issues)}
        self.assertIn("bow_flat_buildup", codes)

    def test_bow_trigger_too_big_warns(self) -> None:
        plan = _short_plan([
            {"num": 1, "role": "hook_open"},
            {"num": 2, "role": "buildup"},
            {"num": 3, "role": "buildup"},
            {"num": 4, "role": "escalation", "intent": {
                "kind": "escalation",
                "final": {"debt": "小委屈", "trigger": "公司突然破产大战"},
            }},
            {"num": 5, "role": "paywall"},
            {"num": 6, "role": "paid_open"},
            {"num": 7, "role": "finale"},
        ], paywall_chapter=5)
        issues = chapter_roles.validate_plan_sequence(plan, book_type="short")
        codes = {i["code"] for i in chapter_roles.validation_warnings(issues)}
        self.assertIn("bow_trigger_too_big", codes)

    def test_bridge_next_seed_mismatch_warns(self) -> None:
        plan = _short_plan([
            {"num": 1, "role": "hook_open"},
            {"num": 2, "role": "climax"},
            {"num": 3, "role": "bridge", "intent": {
                "kind": "bridge",
                "final": {"next_seed": "宫廷宴会"},
            }},
            {"num": 4, "role": "buildup", "intent": {
                "kind": "buildup",
                "final": {"conditions": "加班熬夜", "emotions": "疲惫"},
            }},
            {"num": 5, "role": "finale"},
        ])
        issues = chapter_roles.validate_plan_sequence(plan, book_type="short")
        codes = {i["code"] for i in chapter_roles.validation_warnings(issues)}
        self.assertIn("bridge_next_seed_mismatch", codes)

    def test_finale_opening_gap_mismatch_warns(self) -> None:
        plan = _short_plan([
            {"num": 1, "role": "hook_open", "intent": {
                "kind": "hook_open",
                "final": "身份误会",
            }},
            {"num": 2, "role": "buildup"},
            {"num": 3, "role": "finale", "intent": {
                "kind": "finale",
                "final": {"opening_gap": "完全不同的结局主题"},
            }},
        ])
        issues = chapter_roles.validate_plan_sequence(plan, book_type="short")
        codes = {i["code"] for i in chapter_roles.validation_warnings(issues)}
        self.assertIn("finale_opening_gap_mismatch", codes)

    def test_escalation_debt_untraceable_warns(self) -> None:
        plan = _short_plan([
            {"num": 1, "role": "hook_open"},
            {"num": 2, "role": "buildup", "intent": {
                "kind": "buildup",
                "final": {"conditions": "加班", "emotions": "憋屈"},
            }},
            {"num": 3, "role": "escalation", "intent": {
                "kind": "escalation",
                "final": {"debt": "完全不同的情感", "trigger": "眼神"},
            }},
            {"num": 4, "role": "paywall"},
            {"num": 5, "role": "paid_open"},
            {"num": 6, "role": "finale"},
        ], paywall_chapter=4)
        issues = chapter_roles.validate_plan_sequence(plan, book_type="short")
        codes = {i["code"] for i in chapter_roles.validation_warnings(issues)}
        self.assertIn("escalation_debt_untraceable", codes)


if __name__ == "__main__":
    unittest.main()
