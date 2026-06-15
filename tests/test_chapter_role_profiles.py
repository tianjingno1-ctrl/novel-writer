"""chapter role YAML profiles（Track R5）。"""

from __future__ import annotations

import unittest

from core import chapter_role_profiles
from core import chapter_roles


class ChapterRoleProfilesTests(unittest.TestCase):
    def test_load_all_eight_profiles(self) -> None:
        profiles = chapter_role_profiles.load_all_role_profiles(reload=True)
        self.assertEqual(len(profiles), 8)
        for role in chapter_roles.CHAPTER_ROLE_ORDER:
            self.assertIn(role, profiles)
            doc = profiles[role]
            self.assertTrue(str(doc.get("l4") or "").strip())
            self.assertIsInstance(doc.get("l1b"), dict)
            self.assertIsInstance(doc.get("l2"), dict)

    def test_profile_summary_matches_overlay(self) -> None:
        from core import chapter_role_overlay

        summary = chapter_role_overlay.all_role_profiles()
        self.assertEqual(len(summary), 8)
        self.assertIn("hook_open", summary["hook_open"]["l4"])


if __name__ == "__main__":
    unittest.main()
