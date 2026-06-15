"""E8：书籍设定 md 文件 API。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from core.orchestration import book_files as bf
from tests.support.isolated_library import store_only_library


class BookFilesTests(unittest.TestCase):
    def test_orchestration_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with store_only_library(Path(tmp)) as (_ctx, store):
                ctx = MagicMock()
                ctx.store = store

                listed = bf.list_book_files(ctx)
                self.assertTrue(listed.get("ok"))
                keys = {f["key"] for f in listed.get("files") or []}
                self.assertIn("world", keys)
                self.assertIn("style", keys)
                self.assertIn("plot_threads_active", keys)
                self.assertIn("summaries_recent", keys)

                got = bf.get_book_file(ctx, "world")
                self.assertTrue(got.get("ok"))

                updated = bf.put_book_file(ctx, "world", "# 测试世界观\n\n节拍表")
                self.assertTrue(updated.get("ok"))

                again = bf.get_book_file(ctx, "world")
                self.assertIn("测试世界观", again.get("content") or "")

    def test_unknown_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with store_only_library(Path(tmp)) as (_ctx, store):
                ctx = MagicMock()
                ctx.store = store
                bad = bf.get_book_file(ctx, "unknown")
                self.assertFalse(bad.get("ok"))

    def test_short_book_setting_only_scope(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            with store_only_library(Path(tmp)) as (_ctx, store):
                ctx = MagicMock()
                ctx.store = store
                proj_path = store.paths.data_dir / "project.json"
                proj_path.write_text(
                    json.dumps({"title": "短篇", "type": "short"}, ensure_ascii=False),
                    encoding="utf-8",
                )

                listed = bf.list_book_files(ctx)
                keys = {f["key"] for f in listed.get("files") or []}
                self.assertEqual(listed.get("scope"), "setting_only")
                self.assertIn("world", keys)
                self.assertNotIn("summaries_recent", keys)
                self.assertNotIn("plot_threads_active", keys)

                denied = bf.get_book_file(ctx, "summaries_recent")
                self.assertFalse(denied.get("ok"))


if __name__ == "__main__":
    unittest.main()
