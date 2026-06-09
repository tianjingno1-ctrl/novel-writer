"""RuleRef 解析测试。"""

from __future__ import annotations

import unittest

from core.schemas import rule_refs


class RuleRefTests(unittest.TestCase):
    def test_format_and_parse(self) -> None:
        ref = rule_refs.format_rule_ref("global", "rule_001")
        self.assertEqual(ref, "global:rule_001")
        self.assertEqual(rule_refs.parse_rule_ref(ref), ("global", "rule_001"))

    def test_all_sources(self) -> None:
        for src in ("global", "local", "profile", "custom"):
            ref = f"{src}:x"
            self.assertEqual(rule_refs.parse_rule_ref(ref)[0], src)

    def test_invalid_ref(self) -> None:
        with self.assertRaises(ValueError):
            rule_refs.parse_rule_ref("rule_001")
        with self.assertRaises(ValueError):
            rule_refs.parse_rule_ref("unknown:x")

    def test_resolve_list(self) -> None:
        rows = rule_refs.resolve_rule_refs(["global:a", "local:b"])
        self.assertEqual(rows, [("global", "a"), ("local", "b")])


if __name__ == "__main__":
    unittest.main()
