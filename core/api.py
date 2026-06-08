"""统一 LLM 调用入口：temperature / max_tokens 等参数在此配置。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import config
from providers import APIClient, APIError, TokenUsage, get_client, reset_client

__all__ = [
    "APIError",
    "CallOptions",
    "TokenUsage",
    "complete",
    "get_client",
    "reset_client",
    "stream",
]


@dataclass
class CallOptions:
    """单次 LLM 调用参数（业务层只通过此结构传参，勿直接调 SDK）。"""

    max_tokens: int | None = None
    temperature: float | None = None
    provider: str | None = None


def _resolve_max_tokens(options: CallOptions | None) -> int:
    opts = options or CallOptions()
    return opts.max_tokens or config.MAX_TOKENS


def _resolve_temperature(options: CallOptions | None) -> float | None:
    opts = options or CallOptions()
    return opts.temperature


def complete(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    options: CallOptions | None = None,
    client: APIClient | None = None,
) -> tuple[str, TokenUsage]:
    opts = options or CallOptions()
    return (client or get_client()).create_message(
        system,
        messages,
        max_tokens=_resolve_max_tokens(opts),
        temperature=_resolve_temperature(opts),
        provider=opts.provider,
    )


def stream(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    options: CallOptions | None = None,
    client: APIClient | None = None,
) -> Iterator[str]:
    opts = options or CallOptions()
    yield from (client or get_client()).iter_message(
        system,
        messages,
        max_tokens=_resolve_max_tokens(opts),
        temperature=_resolve_temperature(opts),
        provider=opts.provider,
    )
