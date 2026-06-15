"""intent.final 嵌套 schema（Track V1）。"""

from __future__ import annotations

import unittest

from core import chapter_roles
from core import intent_final


class IntentFinalTests(unittest.TestCase):
    def test_finale_nested_normalize(self) -> None:
        out = intent_final.normalize_intent_final("finale", {
            "opening_gap": "身份误会",
            "closing_payoff": "和解",
            "freeze_frame": "雨夜站台",
            "open_ending": "留白",
        })
        self.assertEqual(out["core_task"]["opening_gap"], "身份误会")
        self.assertEqual(out["freeze_frame"]["what"], "雨夜站台")
        self.assertNotIn("opening_gap", out)

    def test_finale_nested_read(self) -> None:
        raw = {
            "core_task": {"opening_gap": "配方A", "closing_payoff": "交割"},
            "freeze_frame": "定格",
        }
        self.assertEqual(intent_final.finale_opening_gap(raw), "配方A")
        self.assertEqual(intent_final.finale_closing_payoff(raw), "交割")

    def test_normalize_intent_persists_nested_finale(self) -> None:
        doc = chapter_roles.normalize_intent("finale", {
            "kind": "finale",
            "final": {"opening_gap": "缺口", "closing_payoff": "落地"},
        })
        final = doc["final"]
        self.assertIsInstance(final.get("core_task"), dict)
        self.assertEqual(final["core_task"]["opening_gap"], "缺口")

    def test_finale_gap_mismatch_with_nested(self) -> None:
        plan = {
            "version": 2,
            "meta": {},
            "chapters": {
                "1": {
                    "role": "hook_open",
                    "intent": {"final": "身份误会"},
                },
                "3": {
                    "role": "finale",
                    "intent": {
                        "final": {
                            "core_task": {"opening_gap": "完全不同的主题"},
                        },
                    },
                },
            },
        }
        issues = chapter_roles.validate_plan_sequence(plan, book_type="short")
        codes = {i["code"] for i in chapter_roles.validation_warnings(issues)}
        self.assertIn("finale_opening_gap_mismatch", codes)


    def test_bridge_nested_normalize(self) -> None:
        out = intent_final.normalize_intent_final("bridge", {
            "bridge_subtype": "情绪缓冲型",
            "micro_who": "配角甲",
            "micro_what_changed": "主动开口",
            "next_seed": "宴会邀请",
            "next_seed_hook_type": "新威胁",
            "next_seed_intensity": "低",
        })
        self.assertEqual(out["micro_change"]["who"], "配角甲")
        self.assertEqual(out["next_seed"]["text"], "宴会邀请")
        self.assertEqual(intent_final.bridge_next_seed(out), "新威胁 宴会邀请")

    def test_finale_freeze_nested_read(self) -> None:
        raw = {"freeze_frame": {"who": "男女主", "what": "外套搭肩"}}
        self.assertEqual(intent_final.finale_freeze_what(raw), "男女主 · 外套搭肩")


if __name__ == "__main__":
    unittest.main()
