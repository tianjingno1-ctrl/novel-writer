"""Phase 1 产品能力测试：prompt 节点、quality 判断、稿件状态机。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import manuscript, prompt_nodes
from infra.logs import quality as quality_log


class PromptNodeTests(unittest.TestCase):
    def test_resolve_global_node(self) -> None:
        resolved = prompt_nodes.resolve_node("writing.main")
        self.assertEqual(resolved.node_id, "writing.main")
        self.assertEqual(resolved.prompt_source, "global")
        self.assertTrue(resolved.system.strip())
        self.assertEqual(len(resolved.prompt_hash), 16)

    def test_book_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            book_dir = Path(tmp)
            prompt_nodes.save_node_override(
                book_dir, "writing.main", system="自定义写作 prompt",
            )
            resolved = prompt_nodes.resolve_node("writing.main", book_dir=book_dir)
            self.assertEqual(resolved.prompt_source, "book_override")
            self.assertIn("自定义", resolved.system)
            prompt_nodes.save_node_override(book_dir, "writing.main", clear=True)
            resolved2 = prompt_nodes.resolve_node("writing.main", book_dir=book_dir)
            self.assertEqual(resolved2.prompt_source, "global")


class QualityJudgmentTests(unittest.TestCase):
    def test_append_with_prompt_meta_and_judgment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            quality_log.init_quality_log(Path(tmp))
            eid = quality_log.append_entry(
                "prefill_direction",
                0,
                '{"options":[]}',
                prompt_node="prefill.direction",
                prompt_hash="abc123",
                prompt_source="global",
                outcome="pending",
            )
            row = quality_log.record_judgment(
                eid,
                outcome="accepted",
                issue_tags=["hook_weak"],
                note="方案 A 更好",
            )
            self.assertIsNotNone(row)
            extra = row.get("extra") or {}
            self.assertEqual(extra.get("outcome"), "accepted")
            self.assertEqual(extra.get("issue_tags"), ["hook_weak"])


class ManuscriptTests(unittest.TestCase):
    def test_state_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manuscript.MANUSCRIPTS_DIR = Path(tmp)
            manuscript.INDEX_FILE = Path(tmp) / "index.json"
            created = manuscript.create_from_book(book_id="book-1", title="测试短篇")
            self.assertTrue(created.get("ok"))
            ms_id = created["manuscript"]["id"]
            self.assertEqual(created["manuscript"]["state"], "draft")

            tr = manuscript.transition_state(ms_id, "complete")
            self.assertTrue(tr.get("ok"))
            self.assertEqual(tr["manuscript"]["state"], "complete")

            tr2 = manuscript.transition_state(ms_id, "submitting")
            self.assertTrue(tr2.get("ok"))

            bad = manuscript.transition_state(ms_id, "draft")
            self.assertFalse(bad.get("ok"))

            listed = manuscript.list_manuscripts(book_id="book-1")
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], ms_id)


class PrefillParseTests(unittest.TestCase):
    def test_parse_json_with_surrounding_text(self) -> None:
        from core.orchestration.prefill import _parse_json_payload

        payload = _parse_json_payload('说明文字\n{"options":[{"id":"A"}]}\n')
        self.assertEqual(payload["options"][0]["id"], "A")

    def test_parse_json_with_markdown_fence(self) -> None:
        from core.orchestration.prefill import _parse_json_payload

        payload = _parse_json_payload('```json\n{"options":[{"id":"B"}]}\n```')
        self.assertEqual(payload["options"][0]["id"], "B")


if __name__ == "__main__":
    unittest.main()
