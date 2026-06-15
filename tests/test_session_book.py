"""E7：按书 + client scope 隔离写作会话。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from infra.session_book import (
    activate_book_session,
    clear_all_snapshots,
    park_book_session,
    set_client_scope,
)
from infra.state import state


class SessionBookTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_all_snapshots()
        set_client_scope("test")
        state.conversation_history.clear()
        state.write_chapter_num = 0
        state.appended_indices.clear()

    def tearDown(self) -> None:
        clear_all_snapshots()
        state.conversation_history.clear()

    def test_park_and_activate_roundtrip(self) -> None:
        state.conversation_history.append({"role": "user", "content": "写第一章"})
        state.write_chapter_num = 2
        state.appended_indices.add(0)

        park_book_session("book-a")
        state.conversation_history.clear()
        state.write_chapter_num = 0

        activate_book_session("book-a")
        self.assertEqual(len(state.conversation_history), 1)
        self.assertEqual(state.conversation_history[0]["content"], "写第一章")
        self.assertEqual(state.write_chapter_num, 2)
        self.assertIn(0, state.appended_indices)

    def test_client_scope_isolates_same_book(self) -> None:
        set_client_scope("client-1")
        state.conversation_history.append({"role": "user", "content": "A 会话"})
        park_book_session("shared")

        activate_book_session("shared")
        self.assertEqual(state.conversation_history[0]["content"], "A 会话")

        set_client_scope("client-2")
        activate_book_session("shared")
        self.assertEqual(state.conversation_history, [])

    def test_switch_book_restores_history(self) -> None:
        from core.data import book_context

        with tempfile.TemporaryDirectory() as tmp:
            lib = Path(tmp) / "library"
            books = lib / "books"
            books.mkdir(parents=True)

            def seed_book(bid: str, title: str) -> None:
                d = books / bid
                d.mkdir()
                (d / "project.json").write_text(
                    json.dumps({"title": title, "type": "short"}, ensure_ascii=False),
                    encoding="utf-8",
                )
                (d / "chapters").mkdir(exist_ok=True)

            seed_book("a", "书A")
            seed_book("b", "书B")
            index = {
                "version": 1,
                "active_book_id": "a",
                "books": [
                    {"id": "a", "title": "书A", "type": "short"},
                    {"id": "b", "title": "书B", "type": "short"},
                ],
            }
            (lib / "index.json").write_text(
                json.dumps(index, ensure_ascii=False), encoding="utf-8"
            )

            orig_lib = book_context.LIBRARY_DIR
            orig_books = book_context.BOOKS_DIR
            orig_index = book_context.INDEX_FILE
            orig_ctx = book_context._context
            try:
                book_context.LIBRARY_DIR = lib
                book_context.BOOKS_DIR = books
                book_context.INDEX_FILE = lib / "index.json"
                book_context._context = None
                book_context.init_library(book_id="a")

                state.conversation_history.append(
                    {"role": "assistant", "content": "书A 续写内容" * 3}
                )
                state.write_chapter_num = 1

                sw = book_context.switch_book("b")
                self.assertTrue(sw.get("ok"))
                self.assertEqual(state.conversation_history, [])

                state.conversation_history.append(
                    {"role": "user", "content": "书B 独有"}
                )

                sw2 = book_context.switch_book("a")
                self.assertTrue(sw2.get("ok"))
                self.assertEqual(len(state.conversation_history), 1)
                self.assertIn("书A", state.conversation_history[0]["content"])
            finally:
                book_context.LIBRARY_DIR = orig_lib
                book_context.BOOKS_DIR = orig_books
                book_context.INDEX_FILE = orig_index
                book_context._context = orig_ctx
                clear_all_snapshots()


if __name__ == "__main__":
    unittest.main()
