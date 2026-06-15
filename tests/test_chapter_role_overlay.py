"""chapter.role overlay（Track S3–S4）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import chapter_role_overlay
from core import chapter_roles
from core import plan_product
from core.data import novel_data


class ChapterRoleOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.book_dir = Path(self._tmp.name)
        novel_data.PLAN_FILE = self.book_dir / "plan.json"
        novel_data._save_json(novel_data.PLAN_FILE, {"chapters": {}})

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_paid_open_reads_paywall_intent(self) -> None:
        plan = {
            "chapters": {
                "5": {
                    "role": "paywall",
                    "intent": {"kind": "paywall", "final": "必须知道真相"},
                },
                "6": {"role": "paid_open"},
            },
            "meta": {"paywall_chapter": 5},
        }
        ctx = chapter_role_overlay.chapter_review_context(plan, 6)
        self.assertEqual(ctx["role"], "paid_open")
        self.assertEqual(ctx["paywall_side"], "post")
        self.assertEqual(ctx["intent_final"], "必须知道真相")

    def test_l4_overlay_hook_open(self) -> None:
        plan = {
            "chapters": {
                "1": {
                    "role": "hook_open",
                    "intent": {"kind": "hook_open", "final": "偷听+愤怒"},
                },
            },
        }
        block = chapter_role_overlay.l4_overlay_block(plan, 1)
        self.assertIn("hook_open", block)
        self.assertIn("偷听+愤怒", block)
        self.assertIn("额外审阅维度", block)

    def test_l4_overlay_buildup(self) -> None:
        plan = {
            "chapters": {
                "2": {
                    "role": "buildup",
                    "intent": {"kind": "buildup", "final": {"conditions": "加班", "emotions": "憋屈"}},
                },
            },
        }
        block = chapter_role_overlay.l4_overlay_block(plan, 2)
        self.assertIn("buildup", block)
        self.assertIn("自己", block)

    def test_finale_shows_hook_open_hint(self) -> None:
        plan = {
            "chapters": {
                "1": {"role": "hook_open", "intent": {"final": "身份误会"}},
                "10": {"role": "finale", "intent": {"final": "和解留白"}},
            },
        }
        block = chapter_role_overlay.l4_overlay_block(plan, 10)
        self.assertIn("首尾呼应", block)
        self.assertIn("身份误会", block)

    def test_bridge_shows_next_buildup_hint(self) -> None:
        plan = {
            "chapters": {
                "4": {"role": "bridge"},
                "5": {
                    "role": "buildup",
                    "intent": {"final": {"conditions": "宴会", "emotions": "嫉妒"}},
                },
            },
        }
        block = chapter_role_overlay.l4_overlay_block(plan, 4)
        self.assertIn("next_seed", block)
        self.assertIn("宴会", block)

    def test_escalation_intent_issues(self) -> None:
        plan = {
            "chapters": {
                "3": {
                    "role": "escalation",
                    "intent": {
                        "final": {
                            "debt": "长期被忽视",
                            "trigger": "一句谢谢",
                        },
                    },
                },
            },
        }
        issues = chapter_role_overlay.escalation_intent_issues(
            plan, 3, "她终于爆发了，情绪倾泻而出",
        )
        codes = {i["code"] for i in issues}
        severities = {i["code"]: i["severity"] for i in issues}
        self.assertIn("escalation_debt_weak", codes)
        self.assertIn("escalation_trigger_weak", codes)
        self.assertEqual(severities["escalation_debt_weak"], "hard")
        self.assertEqual(severities["escalation_trigger_weak"], "hard")

    def test_bridge_hook_hard_when_missing(self) -> None:
        plan = {"chapters": {"4": {"role": "bridge", "hook": ""}}}
        issues = chapter_role_overlay.bridge_hook_issues(plan, 4, "平淡收尾，今天就这样。")
        self.assertTrue(any(i["code"] == "bridge_no_hook" and i["severity"] == "hard" for i in issues))

    def test_l2_reader_user_prompt_includes_role(self) -> None:
        plan = {
            "chapters": {
                "2": {
                    "role": "buildup",
                    "intent": {"final": {"conditions": "宴会", "emotions": "嫉妒"}},
                },
            },
        }
        prompt = chapter_role_overlay.l2_reader_user_prompt(plan, 2, "正文")
        self.assertIn("buildup", prompt)
        self.assertIn("宴会", prompt)
        self.assertIn("读者模拟问题", prompt)

    def test_l2_questions_loaded_from_yaml(self) -> None:
        from core import chapter_role_profiles

        qs = chapter_role_profiles.role_l2_questions("paywall")
        self.assertGreaterEqual(len(qs), 2)

    def test_all_eight_roles_have_profiles(self) -> None:
        profiles = chapter_role_overlay.all_role_profiles()
        self.assertEqual(len(profiles), 8)
        for role in chapter_roles.CHAPTER_ROLE_ORDER:
            self.assertIn(role, profiles)
            self.assertTrue(profiles[role]["l4"])


    def test_l5b_mandatory_high_roles(self) -> None:
        plan = {"chapters": {"1": {"role": "hook_open"}}}
        self.assertTrue(chapter_role_overlay.l5b_mandatory(plan, 1))
        plan2 = {"chapters": {"5": {"role": "paywall"}}, "meta": {"paywall_chapter": 5}}
        self.assertTrue(chapter_role_overlay.l5b_mandatory(plan2, 5))
        plan3 = {"chapters": {"2": {"role": "buildup"}}}
        self.assertFalse(chapter_role_overlay.l5b_mandatory(plan3, 2))

    def test_hook_open_end_hook_hard(self) -> None:
        plan = {"chapters": {"1": {"role": "hook_open", "hook": ""}}}
        issues = chapter_role_overlay.hook_open_l1b_issues(
            plan, 1, "平淡的一天结束了。她回家睡觉。",
        )
        self.assertTrue(
            any(i["code"] == "hook_open_no_end_hook" and i["severity"] == "hard" for i in issues),
        )

    def test_paid_open_continuity_hard(self) -> None:
        plan = {
            "chapters": {
                "5": {"role": "paywall", "hook": "真相即将揭开", "intent": {"final": "必须知道"}},
                "6": {"role": "paid_open"},
            },
            "meta": {"paywall_chapter": 5},
        }
        issues = chapter_role_overlay.paid_open_continuity_issues(
            plan, 6, "完全不同的新场景开始了。",
        )
        self.assertTrue(
            any(i["code"] == "paid_open_no_continuity" and i["severity"] == "hard" for i in issues),
        )

    def test_finale_freeze_hard(self) -> None:
        plan = {
            "chapters": {
                "1": {"role": "hook_open", "intent": {"final": "身份误会"}},
                "10": {
                    "role": "finale",
                    "intent": {"final": {"core_task": {"opening_gap": "身份误会"}}},
                },
            },
        }
        issues = chapter_role_overlay.finale_l1b_issues(plan, 10, "他们从此幸福地生活。")
        codes = {i["code"] for i in issues}
        self.assertIn("finale_freeze_missing", codes)

    def test_bridge_change_visibility_hard(self) -> None:
        plan = {"chapters": {"4": {"role": "bridge", "hook": "然而？"}}}
        issues = chapter_role_overlay.bridge_hook_issues(
            plan, 4, "今天天气不错。大家吃了饭。各自散去。然而？",
        )
        self.assertTrue(
            any(i["code"] == "bridge_no_visible_change" for i in issues),
        )


if __name__ == "__main__":
    unittest.main()
