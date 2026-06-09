"""Prompt Cache 显式续命工具测试。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import infra.config as config
from app import runtime as rt
from core import model_routing
from infra.state import state


class PromptCacheToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_overrides = dict(model_routing.NODE_MODEL_OVERRIDES)
        model_routing.set_node_overrides({})

    def tearDown(self) -> None:
        model_routing.set_node_overrides(self._orig_overrides)

    def test_status_returns_writing_node_resolution(self) -> None:
        status = rt.get_prompt_cache_status()
        self.assertTrue(status["ok"])
        self.assertEqual(status["writing_provider"], config.PROVIDER)
        self.assertIn("cache_supported", status)
        self.assertIn("prompt_cache_auto_refresh", status)

    @patch("core.llm.call_api", return_value=".")
    @patch("core.llm.build_cached_system", return_value=[])
    @patch.object(config, "is_api_key_configured", return_value=True)
    @patch.object(config, "supports_prompt_cache", return_value=True)
    def test_refresh_success(
        self,
        _cache_ok,
        _key_ok,
        _build,
        mock_call,
    ) -> None:
        state.last_call_info = {
            "ok": True,
            "cache_ttl_remaining": 3000,
            "model": "claude-sonnet",
        }
        result = rt.refresh_prompt_cache()
        self.assertTrue(result["ok"])
        self.assertTrue(result["refreshed"])
        mock_call.assert_called_once()
        _, kwargs = mock_call.call_args
        self.assertEqual(kwargs.get("node_id"), "writing.main")

    @patch.object(config, "supports_prompt_cache", return_value=False)
    def test_refresh_skips_unsupported_provider(self, _cache) -> None:
        result = rt.refresh_prompt_cache()
        self.assertFalse(result["ok"])
        self.assertFalse(result.get("cache_supported", True))
