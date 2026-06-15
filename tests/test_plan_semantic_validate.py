"""W5 plan intent 语义校验。"""

from __future__ import annotations

import unittest

from core import plan_semantic_validate


class PlanSemanticValidateTests(unittest.TestCase):
    def test_collect_bridge_and_finale_pairs(self) -> None:
        plan = {
            "chapters": {
                "1": {
                    "role": "hook_open",
                    "intent": {"final": "身份误会"},
                },
                "2": {
                    "role": "bridge",
                    "intent": {"final": {"next_seed": "宴会"}},
                },
                "3": {
                    "role": "buildup",
                    "intent": {"final": {"conditions": "宴会筹备", "emotions": "紧张"}},
                },
                "4": {
                    "role": "finale",
                    "intent": {
                        "final": {
                            "core_task": {"opening_gap": "身份误会"},
                        },
                    },
                },
            },
        }
        pairs = plan_semantic_validate.collect_semantic_pairs(plan)
        kinds = {p["kind"] for p in pairs}
        self.assertIn("bridge_seed_conditions", kinds)
        self.assertIn("finale_hook_open_gap", kinds)

    def test_checks_to_issues_override_heuristic(self) -> None:
        pairs = [{
            "id": "bridge_2_buildup_3_seed",
            "kind": "bridge_seed_conditions",
            "left_label": "seed",
            "right_label": "cond",
            "chapter_num": 2,
        }]
        checks = [{"id": "bridge_2_buildup_3_seed", "aligned": True, "message": "ok"}]
        warnings, overrides = plan_semantic_validate._checks_to_issues(pairs, checks)
        self.assertEqual(warnings, [])
        self.assertIn("bridge_next_seed_mismatch", overrides)

    def test_checks_to_issues_adds_semantic_warn(self) -> None:
        pairs = [{
            "id": "finale_hook_open_gap",
            "kind": "finale_hook_open_gap",
            "left_label": "hook",
            "right_label": "gap",
            "chapter_num": 4,
        }]
        checks = [{
            "id": "finale_hook_open_gap",
            "aligned": False,
            "message": "首尾主题无关",
        }]
        warnings, overrides = plan_semantic_validate._checks_to_issues(pairs, checks)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["code"], "semantic_finale_hook_open_gap")
        self.assertIn("首尾主题无关", warnings[0]["message"])
        self.assertEqual(overrides, [])


if __name__ == "__main__":
    unittest.main()
