"""多 API 提供商统一调用层：kie.ai Claude + DeepSeek。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import config


def _or_zero(obj: object | None, attr: str) -> int:
    if obj is None:
        return 0
    val = getattr(obj, attr, None)
    return int(val) if val else 0


class APIError(Exception):
    """Provider 调用失败，kind 便于上层给出可操作建议。"""

    def __init__(self, message: str, *, kind: str = "unknown") -> None:
        super().__init__(message)
        self.kind = kind


def _classify_api_error(exc: Exception) -> APIError:
    if isinstance(exc, APIError):
        return exc
    msg = str(exc).strip() or type(exc).__name__
    lower = msg.lower()
    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError) or "timeout" in lower or "timed out" in lower:
        return APIError(msg, kind="timeout")
    if "401" in msg or "403" in msg or "authentication" in name or "permission" in lower:
        return APIError(msg, kind="auth")
    if "429" in msg or "rate" in lower or "quota" in lower:
        return APIError(msg, kind="rate_limit")
    if "connection" in lower or "connect" in name:
        return APIError(msg, kind="network")
    return APIError(msg, kind="unknown")


@dataclass
class TokenUsage:
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class _ProviderClients:
    anthropic: object | None = field(default=None)
    openai: object | None = field(default=None)


def _has_system(system: list[dict] | str | None) -> bool:
    if system is None:
        return False
    if isinstance(system, str):
        return bool(system.strip())
    return bool(_flatten_system(system).strip())


def _flatten_system(system: list[dict] | str) -> str:
    if isinstance(system, str):
        return system
    parts = []
    for block in system:
        if isinstance(block, dict):
            parts.append(block.get("text", ""))
        else:
            parts.append(str(block))
    return "\n\n".join(p for p in parts if p)


class APIClient:
    def __init__(self) -> None:
        self._pool: dict[str, _ProviderClients] = {}
        self._last_stream_usage: TokenUsage | None = None

    def pop_stream_usage(self) -> TokenUsage:
        usage = self._last_stream_usage or TokenUsage()
        self._last_stream_usage = None
        return usage

    def reset(self, provider: str | None = None) -> None:
        if provider is None:
            self._pool.clear()
        else:
            self._pool.pop(provider, None)

    def _clients_for(self, provider: str) -> _ProviderClients:
        if provider not in self._pool:
            self._pool[provider] = _ProviderClients()
        return self._pool[provider]

    def _get_anthropic(self, provider: str):
        clients = self._clients_for(provider)
        if clients.anthropic is None:
            try:
                from anthropic import Anthropic
            except ImportError as e:
                raise ImportError("请先安装：pip install anthropic") from e

            cfg = config.get_provider_config(provider)
            kwargs = {
                "api_key": config.get_api_key(provider),
                "base_url": cfg["base_url"],
            }
            if config.cache_enabled(provider):
                kwargs["default_headers"] = {
                    "anthropic-beta": "extended-cache-ttl-2025-04-11",
                }
            clients.anthropic = Anthropic(**kwargs)
        return clients.anthropic

    def _get_openai(self, provider: str):
        clients = self._clients_for(provider)
        if clients.openai is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise ImportError("请先安装：pip install openai") from e

            cfg = config.get_provider_config(provider)
            clients.openai = OpenAI(
                api_key=config.get_api_key(provider),
                base_url=cfg["base_url"],
            )
        return clients.openai

    def create_message(
        self,
        system: list[dict] | str | None,
        messages: list[dict],
        *,
        max_tokens: int,
        provider: str | None = None,
    ) -> tuple[str, TokenUsage]:
        pid = config.resolve_provider(provider)
        cfg = config.get_provider_config(pid)

        if cfg["client"] == "anthropic":
            return self._call_anthropic(system, messages, max_tokens=max_tokens, provider=pid)
        return self._call_openai(system, messages, max_tokens=max_tokens, provider=pid)

    def iter_message(
        self,
        system: list[dict] | str | None,
        messages: list[dict],
        *,
        max_tokens: int,
        provider: str | None = None,
    ) -> Iterator[str]:
        pid = config.resolve_provider(provider)
        cfg = config.get_provider_config(pid)
        if cfg["client"] == "anthropic":
            yield from self._iter_anthropic(system, messages, max_tokens=max_tokens, provider=pid)
        else:
            yield from self._iter_openai(system, messages, max_tokens=max_tokens, provider=pid)

    def _iter_anthropic(
        self,
        system: list[dict] | str | None,
        messages: list[dict],
        *,
        max_tokens: int,
        provider: str,
    ) -> Iterator[str]:
        kwargs: dict = {
            "model": config.get_model(provider),
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if _has_system(system):
            kwargs["system"] = system
        try:
            with self._get_anthropic(provider).messages.stream(**kwargs) as stream:
                yield from stream.text_stream
                final = stream.get_final_message()
        except Exception as e:
            raise _classify_api_error(e) from e
        usage_obj = final.usage
        self._last_stream_usage = TokenUsage(
            cache_read_input_tokens=_or_zero(usage_obj, "cache_read_input_tokens"),
            cache_creation_input_tokens=_or_zero(usage_obj, "cache_creation_input_tokens"),
            input_tokens=_or_zero(usage_obj, "input_tokens"),
            output_tokens=_or_zero(usage_obj, "output_tokens"),
        )

    def _iter_openai(
        self,
        system: list[dict] | str | None,
        messages: list[dict],
        *,
        max_tokens: int,
        provider: str,
    ) -> Iterator[str]:
        openai_messages: list[dict] = []
        system_text = _flatten_system(system) if _has_system(system) else ""
        if system_text.strip():
            openai_messages.append({"role": "system", "content": system_text})
        openai_messages.extend(messages)
        try:
            stream = self._get_openai(provider).chat.completions.create(
                model=config.get_model(provider),
                max_tokens=max_tokens,
                messages=openai_messages,
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as e:
            raise _classify_api_error(e) from e
        prompt_tokens = 0
        completion_tokens = 0
        cached = 0
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
            usage_obj = getattr(chunk, "usage", None)
            if usage_obj is not None:
                prompt_tokens = _or_zero(usage_obj, "prompt_tokens")
                completion_tokens = _or_zero(usage_obj, "completion_tokens")
                prompt_details = getattr(usage_obj, "prompt_tokens_details", None)
                if prompt_details is not None:
                    cached = _or_zero(prompt_details, "cached_tokens")
        self._last_stream_usage = TokenUsage(
            cache_read_input_tokens=cached,
            input_tokens=max(prompt_tokens - cached, 0),
            output_tokens=completion_tokens,
        )

    def _call_anthropic(
        self,
        system: list[dict] | str | None,
        messages: list[dict],
        *,
        max_tokens: int,
        provider: str,
    ) -> tuple[str, TokenUsage]:
        kwargs: dict = {
            "model": config.get_model(provider),
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if _has_system(system):
            kwargs["system"] = system
        try:
            response = self._get_anthropic(provider).messages.create(**kwargs)
        except Exception as e:
            raise _classify_api_error(e) from e

        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        text = "".join(text_parts)

        usage_obj = response.usage
        usage = TokenUsage(
            cache_read_input_tokens=_or_zero(usage_obj, "cache_read_input_tokens"),
            cache_creation_input_tokens=_or_zero(usage_obj, "cache_creation_input_tokens"),
            input_tokens=_or_zero(usage_obj, "input_tokens"),
            output_tokens=_or_zero(usage_obj, "output_tokens"),
        )
        return text, usage

    def _call_openai(
        self,
        system: list[dict] | str | None,
        messages: list[dict],
        *,
        max_tokens: int,
        provider: str,
    ) -> tuple[str, TokenUsage]:
        openai_messages: list[dict] = []
        system_text = _flatten_system(system) if _has_system(system) else ""
        if system_text.strip():
            openai_messages.append({"role": "system", "content": system_text})
        openai_messages.extend(messages)

        try:
            response = self._get_openai(provider).chat.completions.create(
                model=config.get_model(provider),
                max_tokens=max_tokens,
                messages=openai_messages,
            )
        except Exception as e:
            raise _classify_api_error(e) from e

        text = response.choices[0].message.content or ""
        usage_obj = response.usage
        prompt_tokens = _or_zero(usage_obj, "prompt_tokens")
        completion_tokens = _or_zero(usage_obj, "completion_tokens")
        cached = 0
        prompt_details = getattr(usage_obj, "prompt_tokens_details", None)
        if prompt_details is not None:
            cached = _or_zero(prompt_details, "cached_tokens")

        usage = TokenUsage(
            cache_read_input_tokens=cached,
            input_tokens=max(prompt_tokens - cached, 0),
            output_tokens=completion_tokens,
        )
        return text, usage


_client = APIClient()


def get_client() -> APIClient:
    return _client


def reset_client(provider: str | None = None) -> None:
    _client.reset(provider)
