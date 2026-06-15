"""Track E3：HTTP API 冒烟（TestClient，隔离 tmp 书库）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from fastapi.testclient import TestClient

import infra.config as config
from infra.state import state
from tests.support.isolated_library import TEST_BOOK_ID, _seed_book_dir
from tests.support.path_fixture import patch_paths


def _seed_library(tmp_path: Path, book_id: str = TEST_BOOK_ID) -> Path:
    lib = tmp_path / "library"
    books = lib / "books"
    book_dir = books / book_id
    _seed_book_dir(book_dir)
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "index.json").write_text(
        json.dumps(
            {
                "version": 1,
                "active_book_id": book_id,
                "books": [{"id": book_id, "title": "Smoke Test", "type": "short"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return lib


@contextmanager
def isolated_api_client(tmp_path: Path) -> Iterator[TestClient]:
    from core.data import book_context

    _seed_library(tmp_path)
    lib = tmp_path / "library"
    snap = {
        "LIBRARY_DIR": book_context.LIBRARY_DIR,
        "BOOKS_DIR": book_context.BOOKS_DIR,
        "INDEX_FILE": book_context.INDEX_FILE,
        "_context": book_context._context,
    }
    state.conversation_history.clear()
    state.appended_indices.clear()
    state.write_chapter_num = 0

    with patch_paths(tmp_path):
        book_context.LIBRARY_DIR = lib
        book_context.BOOKS_DIR = lib / "books"
        book_context.INDEX_FILE = lib / "index.json"
        book_context._context = None

        from app.bootstrap import bootstrap_library, init_data_dirs, rebuild_context

        bootstrap_library()
        init_data_dirs()
        rebuild_context()

        from web_app import app

        with (
            patch.object(config, "WEB_TOKEN", ""),
            patch("web_app._is_local_client", return_value=True),
        ):
            with TestClient(app) as client:
                yield client

    book_context.LIBRARY_DIR = snap["LIBRARY_DIR"]
    book_context.BOOKS_DIR = snap["BOOKS_DIR"]
    book_context.INDEX_FILE = snap["INDEX_FILE"]
    book_context._context = snap["_context"]


class APISmokeTests(unittest.TestCase):
    def test_status_and_plan_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with isolated_api_client(Path(tmp)) as client:
                status = client.get("/api/status")
                self.assertEqual(status.status_code, 200)
                body = status.json()
                self.assertIn("book_id", body)
                self.assertIn("history_len", body)
                self.assertIn("session_on_disk", body)
                self.assertEqual(body["book_id"], TEST_BOOK_ID)

                plan = client.get("/api/plan/product")
                self.assertEqual(plan.status_code, 200)
                plan_body = plan.json()
                self.assertTrue(plan_body.get("ok"))
                self.assertIn("meta", plan_body)
                self.assertNotIn("writing_mode", plan_body)
                self.assertNotIn("writing_mode", plan_body.get("meta") or {})

    def test_session_restore_and_status_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with isolated_api_client(base) as client:
                session_file = (
                    base / "library" / "books" / TEST_BOOK_ID / "session_autosave.json"
                )
                session_file.write_text(
                    json.dumps(
                        {
                            "saved_at": "2026-06-10 10:00:00",
                            "write_chapter_num": 2,
                            "chapter_num": 2,
                            "conversation_history": [
                                {"role": "user", "content": "续写"},
                                {"role": "assistant", "content": "夜风从窗缝里渗进来。" * 3},
                            ],
                            "appended_indices": [],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                state.conversation_history.clear()

                status = client.get("/api/status").json()
                self.assertTrue(status["session_on_disk"])
                self.assertEqual(status["session_saved_at"], "2026-06-10 10:00:00")
                self.assertEqual(status["session_chapter_num"], 2)
                self.assertEqual(status["history_len"], 0)

                restored = client.post("/api/chat/restore")
                self.assertEqual(restored.status_code, 200)
                payload = restored.json()
                self.assertTrue(payload["ok"])
                self.assertEqual(payload.get("write_chapter_num"), 2)
                self.assertEqual(len(state.conversation_history), 2)

    def test_chapter_review_get_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with isolated_api_client(Path(tmp)) as client:
                resp = client.get("/api/chapters/1/review")
                self.assertEqual(resp.status_code, 200)
                doc = resp.json()
                self.assertTrue(doc.get("ok"))
                self.assertEqual(doc.get("chapter_num"), 1)
                self.assertEqual(doc.get("round_count"), 0)
                review = doc.get("review") or {}
                self.assertEqual(review.get("rounds") or [], [])

    def test_review_chapter_alias_delegates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with isolated_api_client(Path(tmp)) as client:
                with patch(
                    "api.routes.female_fiction.orchestration_ff.run_female_fiction_review",
                    return_value={"ok": True, "log_id": "ql-smoke", "reply": "ok"},
                ) as mock_run:
                    resp = client.post(
                        "/api/review/chapter",
                        json={"chapter_num": 1, "text": "测试正文"},
                    )
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.json().get("ok"))
                mock_run.assert_called_once()
                kwargs = mock_run.call_args.kwargs
                self.assertEqual(kwargs.get("mode"), "chapter")
                self.assertEqual(kwargs.get("chapter_num"), 1)

    def test_book_files_list_and_put(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with isolated_api_client(Path(tmp)) as client:
                listed = client.get("/api/book/files")
                self.assertEqual(listed.status_code, 200)
                files = listed.json().get("files") or []
                self.assertTrue(any(f.get("key") == "world" for f in files))

                put = client.put(
                    "/api/book/files/world",
                    json={"content": "# E2E 世界观\n"},
                )
                self.assertEqual(put.status_code, 200)
                self.assertTrue(put.json().get("ok"))

                got = client.get("/api/book/files/world")
                self.assertEqual(got.status_code, 200)
                self.assertIn("E2E", got.json().get("content") or "")

    def test_review_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with isolated_api_client(Path(tmp)) as client:
                resp = client.get("/api/review/profiles")
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertIn("profiles", body)
                self.assertIn("active", body)

    def test_plan_validate_returns_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with isolated_api_client(Path(tmp)) as client:
                resp = client.post(
                    "/api/prefill/plan/validate",
                    json={
                        "option": {
                            "chapters": [
                                {"num": 1, "role": "hook_open", "title": "开篇"},
                                {
                                    "num": 2,
                                    "role": "bridge",
                                    "title": "过渡",
                                    "intent": {
                                        "kind": "bridge",
                                        "final": {"next_seed": "宫廷宴会"},
                                    },
                                },
                                {
                                    "num": 3,
                                    "role": "buildup",
                                    "title": "铺垫",
                                    "intent": {
                                        "kind": "buildup",
                                        "final": {
                                            "conditions": "加班",
                                            "emotions": "疲惫",
                                        },
                                    },
                                },
                                {"num": 4, "role": "finale", "title": "完结"},
                            ],
                        },
                        "replace": True,
                    },
                )
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                codes = {w.get("code") for w in body.get("warnings") or []}
                self.assertIn("bridge_next_seed_mismatch", codes)

    def test_plan_semantic_validate_skipped_without_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with isolated_api_client(Path(tmp)) as client:
                resp = client.post(
                    "/api/prefill/plan/semantic-validate",
                    json={
                        "option": {
                            "chapters": [
                                {"num": 1, "role": "hook_open", "title": "开篇",
                                 "intent": {"final": "误会"}},
                                {"num": 2, "role": "finale", "title": "完结",
                                 "intent": {"final": {"opening_gap": "和解"}}},
                            ],
                        },
                        "replace": True,
                    },
                )
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertTrue(body.get("ok"))
                if body.get("skipped"):
                    self.assertIn(
                        body.get("reason"),
                        ("no_api_key", "no_pairs", "parse_failed", "llm_error"),
                    )
                else:
                    self.assertGreaterEqual(int(body.get("pairs_checked") or 0), 1)


if __name__ == "__main__":
    unittest.main()
