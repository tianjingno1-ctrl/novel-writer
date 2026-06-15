"""tests/support 基建自验证"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.support.isolated_library import store_only_library


class StoreOnlyLibraryTests(unittest.TestCase):
    def test_creates_book_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with store_only_library(tmp_path) as (ctx, store):
                self.assertTrue(store.paths.world_file.exists())

    def test_write_and_read_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with store_only_library(tmp_path) as (ctx, store):
                store.paths.world_file.write_text("test world", encoding="utf-8")
                content = store.paths.world_file.read_text(encoding="utf-8")
                self.assertEqual(content, "test world")
                self.assertIn(str(tmp_path), str(store.paths.world_file))

    def test_does_not_pollute_main_globals(self) -> None:
        import main

        orig_data_dir = main.DATA_DIR
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with store_only_library(tmp_path) as (ctx, store):
                self.assertEqual(main.DATA_DIR, orig_data_dir)
        self.assertEqual(main.DATA_DIR, orig_data_dir)


class MockLlmTests(unittest.TestCase):
    def test_mock_llm_complete_returns_tuple(self) -> None:
        """mock_llm patch 后 core.llm.call_api 返回 (str, TokenUsage)"""
        from tests.support.mock_llm import mock_llm
        import core.llm as api

        with mock_llm(["hello"]):
            text, usage = api.complete(None, [{"role": "user", "content": "hi"}])
            self.assertEqual(text, "hello")
            self.assertEqual(usage.input_tokens, 0)

    def test_mock_llm_cycles_responses(self) -> None:
        """list[str] 循环消费"""
        from tests.support.mock_llm import mock_llm
        import core.llm as api

        with mock_llm(["a", "b"]):
            t1, _ = api.complete(None, [])
            t2, _ = api.complete(None, [])
            t3, _ = api.complete(None, [])  # 循环回 "a"
            self.assertEqual([t1, t2, t3], ["a", "b", "a"])

    def test_mock_call_api_list(self) -> None:
        """mock_call_api list 模式顺序消费"""
        from tests.support.mock_llm import mock_call_api
        import main

        with mock_call_api(["resp1", "resp2"]):
            r1 = main.call_api(None, [], tag="test")
            r2 = main.call_api(None, [], tag="test")
            self.assertEqual(r1, "resp1")
            self.assertEqual(r2, "resp2")

    def test_mock_call_api_dict_by_tag(self) -> None:
        """mock_call_api dict 模式按 tag 分发"""
        from tests.support.mock_llm import mock_call_api
        import main

        with mock_call_api({"档案bundle": "archive_json", "质检bundle": "quality_json"}):
            r1 = main.call_api(None, [], tag="档案bundle")
            r2 = main.call_api(None, [], tag="质检bundle")
            r3 = main.call_api(None, [], tag="未知")
            self.assertEqual(r1, "archive_json")
            self.assertEqual(r2, "quality_json")
            self.assertIsNone(r3)

    def test_mock_llm_does_not_pollute_after_exit(self) -> None:
        """with 块退出后 patch 已撤销"""
        import core.llm as api
        from tests.support.mock_llm import mock_llm

        original = api.complete
        with mock_llm(["x"]):
            pass
        self.assertIs(api.complete, original)


if __name__ == "__main__":
    unittest.main()
