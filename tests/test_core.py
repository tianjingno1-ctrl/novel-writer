"""核心纯函数与工具的最小单测。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import file_utils  # noqa: E402
import main  # noqa: E402
from providers import TokenUsage  # noqa: E402


class FileUtilsTests(unittest.TestCase):
    def test_atomic_write_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            file_utils.atomic_write_text(path, "hello")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello")
            file_utils.atomic_write_text(path, "world")
            self.assertEqual(path.read_text(encoding="utf-8"), "world")


class CostTests(unittest.TestCase):
    def test_calc_cost_kie(self) -> None:
        usage = TokenUsage(
            cache_read_input_tokens=1_000_000,
            cache_creation_input_tokens=0,
            input_tokens=0,
            output_tokens=0,
        )
        cost = main.calc_cost(usage, provider="kie")
        self.assertAlmostEqual(cost, 0.30, places=4)

    def test_load_total_cost_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "cost_log.jsonl"
            log.write_text(
                "\n".join(
                    [
                        json.dumps({"cost": 0.1, "total_cost": 0.1}),
                        json.dumps({"cost": 0.2, "total_cost": 0.3}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            total = main.load_total_cost_from_jsonl(log)
            self.assertAlmostEqual(total, 0.3)


class ShouldAppendTests(unittest.TestCase):
    def test_discussion_prefix(self) -> None:
        self.assertFalse(main.should_append_to_chapter("[讨论] 这是一段很长的说明文字" * 3))

    def test_meta_prefix(self) -> None:
        self.assertFalse(main.should_append_to_chapter("我建议你可以这样写下一章的内容" * 2))

    def test_prose(self) -> None:
        text = "夜风从窗缝里渗进来，带着潮气。他握紧剑柄，听见廊下脚步声渐近。"
        self.assertTrue(main.should_append_to_chapter(text))


class TrimHistoryTests(unittest.TestCase):
    def test_trim_history(self) -> None:
        history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}] * 5
        trimmed = main.trim_history(history, max_turns=2)
        self.assertEqual(len(trimmed), 4)


class ConfigTests(unittest.TestCase):
    def test_get_price_has_cache_write(self) -> None:
        price = config.get_price("kie")
        self.assertIn("cache_write", price)
        self.assertGreater(price["input"], 0)


class PlanLockTests(unittest.TestCase):
    def test_mutate_plan_serializes(self) -> None:
        import novel_data

        novel_data._mutate_plan(lambda p: p.setdefault("chapters", {}))
        plan = novel_data.load_plan()
        self.assertIn("chapters", plan)


class CodexTests(unittest.TestCase):
    def test_sanitize_codex_name(self) -> None:
        import novel_data

        self.assertEqual(novel_data._sanitize_codex_name("a/b"), "a_b")
        self.assertEqual(novel_data._sanitize_codex_name('x:y'), "x_y")

    def test_delete_codex_entry(self) -> None:
        import novel_data

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            entries = base / "codex" / "entries"
            entries.mkdir(parents=True)
            active = base / "codex" / "active.json"
            active.write_text('{"active": ["测试条目"]}', encoding="utf-8")
            novel_data.CODEX_DIR = entries
            novel_data.CODEX_ACTIVE_FILE = active
            novel_data.BACKUPS_DIR = base / "backups"
            novel_data.create_codex_entry("测试条目", "# 测试\n")
            r = novel_data.delete_codex_entry("测试条目")
            self.assertTrue(r["ok"])
            self.assertFalse((entries / "测试条目.md").exists())
            self.assertEqual(novel_data.get_active_codex_ids(), [])


class APIErrorTests(unittest.TestCase):
    def test_classify_auth(self) -> None:
        from providers import APIError, _classify_api_error

        err = _classify_api_error(Exception("401 Unauthorized"))
        self.assertEqual(err.kind, "auth")
        self.assertIsInstance(err, APIError)


if __name__ == "__main__":
    unittest.main()
