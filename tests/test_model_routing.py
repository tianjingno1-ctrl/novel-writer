"""按节点配置模型路由测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import infra.config as config
from core import model_routing


class ModelRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.runtime_file = Path(self._tmp.name) / "runtime.json"
        self._orig_runtime = config.RUNTIME_FILE
        self._orig_overrides = dict(model_routing.NODE_MODEL_OVERRIDES)
        config.RUNTIME_FILE = self.runtime_file
        model_routing.set_node_overrides({})

    def tearDown(self) -> None:
        config.RUNTIME_FILE = self._orig_runtime
        model_routing.set_node_overrides(self._orig_overrides)
        self._tmp.cleanup()

    def test_resolve_default_for_writing_main(self) -> None:
        pid, model = model_routing.resolve_for_node("writing.main")
        self.assertEqual(pid, config.PROVIDER)
        self.assertEqual(model, config.get_model(pid))

    def test_apply_node_override_with_custom_model(self) -> None:
        merged = model_routing.apply_node_models_patch({
            "writing.main": {"provider": "deepseek", "model": "deepseek-chat"},
        })
        self.assertIn("writing.main", merged)
        pid, model = model_routing.resolve_for_node("writing.main")
        self.assertEqual(pid, "deepseek")
        self.assertEqual(model, "deepseek-chat")

    def test_clear_override_with_empty_provider(self) -> None:
        model_routing.apply_node_models_patch({
            "writing.main": {"provider": "deepseek"},
        })
        model_routing.apply_node_models_patch({
            "writing.main": {"provider": ""},
        })
        self.assertNotIn("writing.main", model_routing.NODE_MODEL_OVERRIDES)

    def test_persist_node_models_in_runtime_json(self) -> None:
        model_routing.apply_node_models_patch({
            "maintain.summary": {"provider": "kie"},
        })
        config.save_runtime_settings()
        data = json.loads(self.runtime_file.read_text(encoding="utf-8"))
        self.assertEqual(
            data["node_models"]["maintain.summary"]["provider"],
            "kie",
        )

        model_routing.set_node_overrides({})
        config.load_runtime_settings()
        pid, _ = model_routing.resolve_for_node("maintain.summary")
        self.assertEqual(pid, "kie")

    def test_list_configurable_nodes_includes_writing_main(self) -> None:
        rows = model_routing.list_configurable_nodes()
        ids = [r["node_id"] for r in rows]
        self.assertIn("writing.main", ids)
        row = next(r for r in rows if r["node_id"] == "writing.main")
        self.assertIn("provider", row)
        self.assertIn("model", row)

    def test_unknown_node_raises(self) -> None:
        with self.assertRaises(ValueError):
            model_routing.apply_node_models_patch({
                "unknown.node": {"provider": "deepseek"},
            })
