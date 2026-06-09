"""
LLM mock 工具，两层：
  mock_llm(responses)      — patch core.llm.complete + stream
  mock_call_api(responses) — patch core.llm.call_api（main.call_api 经 __getattr__ 转发）
"""
from __future__ import annotations

import itertools
from contextlib import contextmanager
from typing import Callable
from unittest import mock

from infra.providers import TokenUsage


def _make_fake_complete(responses: list[str] | Callable):
    if callable(responses):

        def fake_complete(system, messages, *, options=None, client=None):
            result = responses(system, messages)
            if isinstance(result, tuple):
                return result
            return result, TokenUsage()

        return fake_complete

    pool = itertools.cycle(responses)

    def fake_complete(system, messages, *, options=None, client=None):
        return next(pool), TokenUsage()

    return fake_complete


def _make_fake_stream(responses: list[str] | Callable):
    if callable(responses):

        def fake_stream(system, messages, *, options=None, client=None):
            result = responses(system, messages)
            text = result[0] if isinstance(result, tuple) else result
            yield text

        return fake_stream

    pool = itertools.cycle(responses)

    def fake_stream(system, messages, *, options=None, client=None):
        yield next(pool)

    return fake_stream


@contextmanager
def mock_llm(responses: list[str] | Callable):
    fake_complete = _make_fake_complete(responses)
    fake_stream = _make_fake_stream(responses)
    with mock.patch("core.llm.complete", side_effect=fake_complete), mock.patch(
        "core.llm.stream", side_effect=fake_stream
    ):
        yield


@contextmanager
def mock_call_api(
    responses: list[str] | dict[str, str] | None = None,
    side_effect: Callable | None = None,
):
    if side_effect is not None:
        _side_effect = side_effect
    elif isinstance(responses, dict):
        tag_map = responses

        def _side_effect(system, messages, *, tag="请求", **kwargs):
            return tag_map.get(tag)

    elif isinstance(responses, list):
        pool = itertools.cycle(responses)

        def _side_effect(system, messages, *, tag="请求", **kwargs):
            return next(pool)

    else:

        def _side_effect(system, messages, *, tag="请求", **kwargs):
            return None

    with mock.patch("core.llm.call_api", side_effect=_side_effect), mock.patch.object(
        __import__("main"), "call_api", side_effect=_side_effect, create=True
    ):
        yield
