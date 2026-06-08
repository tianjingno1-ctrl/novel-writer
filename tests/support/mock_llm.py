"""
LLM mock 工具，两层：
  mock_llm(responses)      — patch core.api.complete + stream（真 LLM 边界）
  mock_call_api(responses) — patch main.call_api（遗留兼容，支持 dict[tag, str]）
"""
from __future__ import annotations

import itertools
from contextlib import contextmanager
from typing import Callable
from unittest import mock

from providers import TokenUsage


def _make_fake_complete(responses: list[str] | Callable):
    """
    返回一个符合 core.api.complete 签名的 fake 函数。
    complete(system, messages, *, options=None, client=None) -> (str, TokenUsage)
    """
    if callable(responses):
        def fake_complete(system, messages, *, options=None, client=None):
            result = responses(system, messages)
            if isinstance(result, tuple):
                return result  # 已经是 (str, TokenUsage)
            return result, TokenUsage()

        return fake_complete

    # list[str]：顺序消费，循环使用
    pool = itertools.cycle(responses)

    def fake_complete(system, messages, *, options=None, client=None):
        return next(pool), TokenUsage()

    return fake_complete


def _make_fake_stream(responses: list[str] | Callable):
    """
    返回一个符合 core.api.stream 签名的 fake 函数。
    stream(system, messages, *, options=None, client=None) -> Iterator[str]
    每次调用 yield 整个文本作为单个 chunk。
    """
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
    """
    patch core.api.complete + core.api.stream。

    responses:
      - list[str]：顺序消费（循环），每次返回下一个字符串
      - Callable[[system, messages], str | tuple[str, TokenUsage]]：自定义逻辑

    complete 返回 (text, TokenUsage())；stream yield 整个文本作为单 chunk。
    不支持按 tag 分发（tag 只在 main.call_api 层，用 mock_call_api 代替）。
    """
    fake_complete = _make_fake_complete(responses)
    fake_stream = _make_fake_stream(responses)

    with mock.patch("core.api.complete", side_effect=fake_complete), \
         mock.patch("core.api.stream", side_effect=fake_stream):
        yield


@contextmanager
def mock_call_api(
    responses: list[str] | dict[str, str] | None = None,
    side_effect: Callable | None = None,
):
    """
    patch main.call_api（遗留兼容层）。
    call_api(system, messages, *, tag="请求", **kwargs) -> str

    responses:
      - list[str]：顺序消费（循环）
      - dict[str, str]：按 tag 参数匹配，tag 不在 dict 里返回 None
    side_effect:
      - 优先级高于 responses，直接作为 mock side_effect

    注意：fake 返回纯 str，不写 state.last_call_info。
    需要断言 last_call_info 时，在 side_effect 里手动写，或单独 patch state。
    """
    import main  # 延迟 import，避免模块级副作用

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

    with mock.patch.object(main, "call_api", side_effect=_side_effect):
        yield
