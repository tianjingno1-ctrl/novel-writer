"""统一 LLM：transport + call_api。"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

import infra.config as config
from core.data import novel_data
from infra.logs import runtime as runtime_log
from infra import billing as _cost
from app import paths
from core import context as _wctx
from infra.state import state
from infra.providers import APIClient, APIError, TokenUsage, get_client, reset_client
from core import context as writing_context

__all__ = [
    "APIError", "CallOptions", "TokenUsage", "complete", "stream",
    "get_client", "reset_client", "call_api", "build_cached_system",
    "log_request_context", "prepare_messages_for_context", "trim_history",
    "get_last_call_info", "_request_lock", "_estimate_tokens",
    "_analyze_system", "_summarize_messages", "_build_context_report",
    "_is_stream_disconnect_error", "_record_call_usage", "_api_error_message",
]

@dataclass
class CallOptions:
    """单次 LLM 调用参数（业务层只通过此结构传参，勿直接调 SDK）。"""

    max_tokens: int | None = None
    temperature: float | None = None
    provider: str | None = None
    model: str | None = None
    node_id: str | None = None


def _resolve_max_tokens(options: CallOptions | None) -> int:
    opts = options or CallOptions()
    return opts.max_tokens or config.MAX_TOKENS


def _resolve_temperature(options: CallOptions | None) -> float | None:
    opts = options or CallOptions()
    return opts.temperature


def _resolve_call_target(options: CallOptions | None) -> tuple[str, str]:
    from core import model_routing

    opts = options or CallOptions()
    if opts.node_id:
        return model_routing.resolve_for_node(opts.node_id)
    pid = config.resolve_provider(opts.provider)
    return pid, config.get_model(pid, model=opts.model)


def complete(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    options: CallOptions | None = None,
    client: APIClient | None = None,
) -> tuple[str, TokenUsage]:
    opts = options or CallOptions()
    pid, model = _resolve_call_target(opts)
    return (client or get_client()).create_message(
        system,
        messages,
        max_tokens=_resolve_max_tokens(opts),
        temperature=_resolve_temperature(opts),
        provider=pid,
        model=model,
    )


def stream(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    options: CallOptions | None = None,
    client: APIClient | None = None,
) -> Iterator[str]:
    opts = options or CallOptions()
    pid, model = _resolve_call_target(opts)
    yield from (client or get_client()).iter_message(
        system,
        messages,
        max_tokens=_resolve_max_tokens(opts),
        temperature=_resolve_temperature(opts),
        provider=pid,
        model=model,
    )

_request_lock = threading.Lock()
_context_logger = logging.getLogger("novel_writer.context")


def _estimate_tokens(text: str) -> int:
    return writing_context.estimate_tokens(text)


def _analyze_system(system: list[dict] | str | None) -> dict[str, int]:
    labels = ("world", "characters", "stable_archive", "instruction")
    parts: dict[str, int] = {}
    if isinstance(system, list):
        for i, block in enumerate(system):
            key = labels[i] if i < len(labels) else f"block_{i}"
            if isinstance(block, dict):
                text = str(block.get("text", ""))
            else:
                text = str(block)
            parts[key] = len(text)
        return parts
    if isinstance(system, str) and system.strip():
        markers = (
            ("world", "# 世界观"),
            ("characters", "# 人物设定"),
            ("stable_archive", "# 归档与细节钉子"),
            ("instruction", "# 当前任务"),
        )
        lower = system
        for idx, (key, marker) in enumerate(markers):
            start = lower.find(marker)
            if start < 0:
                continue
            end = len(lower)
            for _, next_marker in markers[idx + 1 :]:
                pos = lower.find(next_marker, start + len(marker))
                if pos >= 0:
                    end = min(end, pos)
            parts[key] = len(lower[start:end].strip())
        if not parts:
            parts["system_total"] = len(system)
    return parts


def _summarize_messages(messages: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for i, msg in enumerate(messages):
        content = str(msg.get("content", ""))
        preview = content[:120].replace("\n", " ").strip()
        rows.append(
            {
                "i": i,
                "role": msg.get("role", "?"),
                "chars": len(content),
                "est_tokens": _estimate_tokens(content),
                "preview": preview,
                "has_chapter": "【当前章节" in content,
                "has_beat": "Scene Beat" in content or "场景指令" in content,
            }
        )
    return rows


def _build_context_report(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    tag: str,
    provider: str | None,
) -> dict:
    pid = config.resolve_provider(provider)
    system_parts = _analyze_system(system)
    system_chars = sum(system_parts.values())
    if not system_parts and isinstance(system, str):
        system_chars = len(system)
    msg_rows = _summarize_messages(messages)
    messages_chars = sum(r["chars"] for r in msg_rows)
    total_chars = system_chars + messages_chars
    est_tokens = _estimate_tokens(
        (system if isinstance(system, str) else json.dumps(system, ensure_ascii=False))
    ) + sum(r["est_tokens"] for r in msg_rows)
    chapter_row = next((r for r in msg_rows if r["has_chapter"]), None)
    warnings: list[str] = []
    if total_chars >= 150_000:
        warnings.append(f"总上下文约 {total_chars:,} 字，可能接近模型上限")
    if chapter_row and chapter_row["chars"] >= 60_000:
        warnings.append(
            f"首轮用户消息含章节正文 {chapter_row['chars']:,} 字，占比较大"
        )
    if len(msg_rows) > config.CHAT_CONTEXT_TURNS * 2 + 2:
        warnings.append(f"对话消息 {len(msg_rows)} 条，偏多")
    codex_ids = novel_data.get_active_codex_ids()
    scene = novel_data.get_active_scene()
    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "provider": pid,
        "model": config.get_model(pid),
        "context_mode": config.CONTEXT_MODE,
        "context_turns_limit": config.CHAT_CONTEXT_TURNS,
        "system_parts": system_parts,
        "system_chars": system_chars,
        "messages": msg_rows,
        "messages_chars": messages_chars,
        "total_chars": total_chars,
        "est_tokens": est_tokens,
        "message_count": len(msg_rows),
        "session_includes_chapter": state.session_includes_chapter,
        "active_codex_count": len(codex_ids),
        "active_codex_ids": codex_ids[:20],
        "active_scene_id": scene.get("id") if scene else None,
        "active_scene_title": scene.get("title") if scene else None,
        "warnings": warnings,
    }


def log_request_context(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    tag: str = "请求",
    provider: str | None = None,
) -> dict:
    """记录即将发出的 API 上下文体积，便于排查过长问题。"""
    report = _build_context_report(system, messages, tag=tag, provider=provider)
    if isinstance(system, list):
        layers = []
        labels = ("layer1", "layer2", "layer3", "layer4")
        titles = (
            "① world + style",
            "② char_static + 人物",
            "③ summaries_archive + plot_threads_locked",
            "④ 动态层",
        )
        for i, block in enumerate(system):
            text = str(block.get("text", "")) if isinstance(block, dict) else str(block)
            cached = isinstance(block, dict) and "cache_control" in block
            layers.append(
                {
                    "id": labels[i] if i < len(labels) else f"block_{i}",
                    "label": titles[i] if i < len(titles) else f"block {i + 1}",
                    "cached": cached,
                    "content": text,
                }
            )
        _wctx.record_context_debug_bound(
            layers, provider=provider, messages=messages, tag=tag
        )
    elif system:
        text = str(system)
        _wctx.record_context_debug_bound(
            [
                {
                    "id": "system",
                    "label": "system prompt",
                    "cached": False,
                    "content": text,
                }
            ],
            provider=provider,
            messages=messages,
            tag=tag,
        )
    else:
        _wctx.record_context_debug_bound(
            [
                {
                    "id": "none",
                    "label": "（无 system · 纯对话）",
                    "cached": False,
                    "content": "",
                }
            ],
            provider=provider,
            messages=messages,
            tag=tag,
        )
    if not config.CONTEXT_LOG_ENABLED:
        return report

    data_dir = paths.resolved("DATA_DIR")
    context_log = paths.resolved("CONTEXT_LOG_JSONL")
    line = json.dumps(report, ensure_ascii=False)
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(context_log, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    parts = report["system_parts"]
    part_txt = ", ".join(f"{k}={v:,}" for k, v in parts.items()) if parts else "—"
    warn_txt = f" ⚠ {'; '.join(report['warnings'])}" if report["warnings"] else ""
    summary = (
        f"[上下文] {tag} · {report['provider']}/{report['model']} · "
        f"{report['context_mode']} · "
        f"合计 {report['total_chars']:,} 字 / 约 {report['est_tokens']:,} tokens · "
        f"消息 {report['message_count']} 条\n"
        f"  system({report['system_chars']:,}): {part_txt}\n"
        f"  messages({report['messages_chars']:,}): "
        f"Codex勾选 {report['active_codex_count']} · "
        f"场景 {report['active_scene_title'] or '无'}"
        f"{warn_txt}"
    )
    print(summary)
    _context_logger.info(summary)
    return report


def build_cached_system(
    instruction: str,
    provider: str | None = None,
    *,
    include_scene_context: bool = True,
) -> list[dict] | str:
    _wctx.bind_writing_context()
    return writing_context.build_cached_system(
        instruction,
        provider,
        include_scene_context=include_scene_context,
        summarize_messages=_summarize_messages,
    )


def _history_has_chapter_block(history: list[dict], chapter_num: int) -> bool:
    for msg in history:
        if msg.get("role") != "user":
            continue
        m = _wctx._USER_CHAPTER_BLOCK_RE.match((msg.get("content") or "").strip())
        if m and int(m.group(1)) == chapter_num:
            return True
    return False


def _sync_chapter_injection_after_trim(trimmed: list[dict]) -> list[dict]:
    if (
        state.session_includes_chapter
        and state.last_injected_chapter_num > 0
        and not _history_has_chapter_block(trimmed, state.last_injected_chapter_num)
    ):
        state.session_includes_chapter = False
    return trimmed


def trim_history(history: list[dict], max_turns: int | None = None) -> list[dict]:
    """保留最近 N 轮对话；首轮含章节正文时不单独特殊处理。"""
    turns = max_turns if max_turns is not None else config.CHAT_CONTEXT_TURNS
    if turns <= 0 or len(history) <= turns * 2:
        return list(history)
    return history[-(turns * 2) :]


def prepare_messages_for_context(history: list[dict]) -> list[dict]:
    """按 CHAT_CONTEXT_TURNS 截断写书对话历史；0 表示不截断。"""
    return _sync_chapter_injection_after_trim(trim_history(history))


def get_last_call_info() -> dict:
    return dict(state.last_call_info)


def _is_stream_disconnect_error(exc: Exception) -> bool:
    if isinstance(exc, APIError) and exc.kind == "network":
        return True
    lower = str(exc).lower()
    return "peer closed" in lower or "incomplete chunked" in lower


def _record_call_usage(
    usage: TokenUsage,
    pid: str,
    *,
    tag: str = "请求",
    model: str | None = None,
) -> None:
    state.last_request_time = time.time()
    cost = _cost.calc_cost(usage, provider=pid)
    _cost.log_cost(usage, cost, tag, provider=pid, silent=True)
    state.last_call_info = _cost._build_last_call_info(usage, cost, pid)
    if model:
        state.last_call_info["model"] = model


def _api_error_message(exc: Exception) -> str:
    raw = str(exc)
    if "blocked" in raw.lower():
        return (
            f"{raw} — 多为 AI 服务商（kie/Cloudflare）拦截。"
            "可尝试：① 换 DeepSeek 模型 ② 检查 .env 的 KIE_API_KEY ③ 缩短/调整指令内容 ④ 稍后重试"
        )
    if isinstance(exc, APIError):
        hints = {
            "auth": "请检查 .env 中的 API Key 是否正确",
            "rate_limit": "请求过于频繁，请稍后重试",
            "timeout": "请求超时，请检查网络或稍后重试",
            "network": "网络或 AI 服务连接中断，请重试、换模型或检查 API Key/余额",
            "server_error": (
                "AI 服务商暂时异常（多为 kie 网关 500）。"
                "请稍后重试；自由聊建议切到 DeepSeek；写书可暂换 DeepSeek 或换 Sonnet/Opus 型号"
            ),
        }
        hint = hints.get(exc.kind)
        return f"{exc} — {hint}" if hint else raw
    return raw


def call_api(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    tag: str = "请求",
    provider: str | None = None,
    model: str | None = None,
    node_id: str | None = None,
    silent: bool = False,
) -> str | None:
    from core import model_routing

    if node_id:
        pid, eff_model = model_routing.resolve_for_node(node_id)
    else:
        pid = config.resolve_provider(provider)
        eff_model = config.get_model(pid, model=model)
    if not config.is_api_key_configured(pid):
        cfg = config.get_provider_config(pid)
        err = (
            f"请设置 {cfg['api_key_env']}，或在 .env / config.py 中填写 API Key"
        )
        state.last_call_info = {"ok": False, "error": err, "provider": pid}
        if not silent:
            print(f"错误：{err}")
        return None

    t_start = time.time()
    lock_wait_ms = 0
    api_ms = 0
    msg_count = len(messages)
    eff_max_tokens = max_tokens or config.MAX_TOKENS
    api_options = CallOptions(
        max_tokens=eff_max_tokens,
        temperature=temperature,
        provider=pid,
        model=eff_model,
        node_id=node_id,
    )
    try:
        log_request_context(system, messages, tag=tag, provider=pid)
        t_before_lock = time.time()
        with _request_lock:
            lock_wait_ms = int((time.time() - t_before_lock) * 1000)
            t_api = time.time()
            text, usage = complete(system, messages, options=api_options)
            api_ms = int((time.time() - t_api) * 1000)
            state.last_request_time = time.time()

        cost = _cost.calc_cost(usage, provider=pid)
        _cost.log_cost(usage, cost, tag, provider=pid, silent=silent)
        state.last_call_info = _cost._build_last_call_info(usage, cost, pid)
        state.last_call_info["model"] = eff_model
        truncated = usage.stop_reason in ("max_tokens", "length") or (
            usage.output_tokens >= max(1, int(eff_max_tokens * 0.92))
        )
        state.last_call_info["max_tokens"] = eff_max_tokens
        state.last_call_info["output_truncated"] = truncated
        return text
    except ImportError as e:
        state.last_call_info = {"ok": False, "error": str(e)}
        if not silent:
            print(f"依赖缺失：{e}")
        return None
    except APIError as e:
        err = _api_error_message(e)
        state.last_call_info = {"ok": False, "error": err, "kind": e.kind}
        runtime_log.log_api_error(
            "core/llm.py:call_api",
            err,
            kind=e.kind,
            provider=pid,
            tag=tag,
            exc=e,
        )
        if not silent:
            print(f"API 错误：{err}")
        return None
    except Exception as e:
        err = _api_error_message(e)
        state.last_call_info = {"ok": False, "error": err}
        runtime_log.log_api_error(
            "core/llm.py:call_api",
            err,
            provider=pid,
            tag=tag,
            exc=e,
        )
        if not silent:
            print(f"API 错误：{err}")
        return None
