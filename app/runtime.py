"""Web/CLI 运行态：应用状态聚合、Prompt Cache 心跳。"""

from __future__ import annotations

import threading
import time

import infra.config as config
from core.data import novel_data
from infra.logs import runtime as runtime_log
from infra.state import state

_exiting = False
_heartbeat_stop = threading.Event()


def get_app_status() -> dict:
    from app import writing_ctx as _wctx
    from app import writing_session as ws
    from app.free_chat import _active_free_thread

    latest = _wctx.get_latest_chapter()
    cfg = config.get_provider_config()
    project = novel_data.get_project_meta()
    book_id = ""
    book_type = "novel"
    try:
        from core.data import book_context

        book_id = book_context.get_context().book_id
        book_type = book_context.get_book_type()
    except RuntimeError:
        pass
    import review_prompts

    review_profile = review_prompts.active_profile_for_project(project)
    return {
        "book_id": book_id,
        "book_type": book_type,
        "platform": project.get("platform") or "tomato",
        "review_profile": review_profile,
        "project_title": project.get("title", ""),
        "world_label": project.get("world_label", ""),
        "provider": config.PROVIDER,
        "provider_name": cfg["name"],
        "model": cfg["model"],
        "summary_provider": config.SUMMARY_PROVIDER,
        "check_provider": config.CHECK_PROVIDER,
        "maintain_provider": config.MAINTAIN_PROVIDER,
        "quality_provider": config.QUALITY_PROVIDER,
        "outline_provider": config.OUTLINE_PROVIDER,
        "context_turns": config.CHAT_CONTEXT_TURNS,
        "context_mode": config.CONTEXT_MODE,
        "free_chat_context_turns": config.FREE_CHAT_CONTEXT_TURNS,
        "max_tokens": config.MAX_TOKENS,
        "free_chat_max_tokens": config.FREE_CHAT_MAX_TOKENS,
        "total_cost": state.total_cost,
        "chapter_num": latest[0] if latest else None,
        "write_chapter_num": state.write_chapter_num or None,
        "summary_count": _wctx.count_summaries(),
        "history_len": len(state.conversation_history),
        "session_on_disk": ws.has_pending_session(),
        "session_saved_at": (
            ws.load_session_from_disk() or {}
        ).get("saved_at")
        if ws.has_pending_session()
        else None,
        "active_scene_id": novel_data.load_plan().get("active_scene_id"),
        "active_codex": novel_data.get_active_codex_ids(),
        "codex_count": len(novel_data.list_codex_entries()),
        "free_chat_provider": state.free_chat_provider,
        "free_chat_len": len(state.free_chat_history),
        "free_chat_thread_count": len(state.free_chat_threads),
        "free_chat_active_thread_id": state.free_chat_active_thread_id,
        "free_chat_active_thread_title": (_active_free_thread() or {}).get("title", ""),
        "api_key_ok": config.is_api_key_configured(),
        "api_keys": {
            key: config.is_api_key_configured(key) for key in config.PROVIDERS
        },
        "writing_cache_supported": config.supports_prompt_cache(config.PROVIDER),
        "batch_job_running": state.batch_job_running,
        "batch_job_id": state.batch_job_id or None,
        "runtime_log": runtime_log.get_status(),
    }


def get_prompt_cache_status() -> dict:
    from core import llm
    from core import model_routing

    pid, model = model_routing.resolve_for_node("writing.main")
    last = llm.get_last_call_info() or {}
    return {
        "ok": True,
        "writing_provider": pid,
        "writing_model": model,
        "cache_supported": config.supports_prompt_cache(pid),
        "cache_enabled": config.cache_enabled(pid),
        "heartbeat_enabled": config.HEARTBEAT_ENABLED,
        "prompt_cache_auto_refresh": model_routing.PROMPT_CACHE_AUTO_REFRESH,
        "last_call": last,
        "cache_ttl_remaining": last.get("cache_ttl_remaining"),
        "cache_write_at": last.get("cache_write_at"),
    }


def refresh_prompt_cache() -> dict:
    """显式续命 Prompt Cache（原 CLI 心跳的单次触发）。"""
    from core import llm
    from core import model_routing
    from summarizer import WRITING_INSTRUCTION

    pid, model = model_routing.resolve_for_node("writing.main")
    if not config.supports_prompt_cache(pid):
        return {
            "ok": False,
            "error": f"当前写作模型 {pid}/{model} 不支持 Prompt Cache",
            "cache_supported": False,
        }
    if not config.is_api_key_configured(pid):
        return {"ok": False, "error": "写作模型 API Key 未配置"}

    system = llm.build_cached_system(WRITING_INSTRUCTION, provider=pid)
    messages = [{"role": "user", "content": "."}]
    reply = llm.call_api(
        system,
        messages,
        max_tokens=1,
        tag="心跳",
        node_id="writing.main",
        silent=True,
    )
    last = llm.get_last_call_info() or {}
    if reply is None and not last.get("ok"):
        return {
            "ok": False,
            "error": last.get("error", "续命请求失败"),
            "last_call": last,
        }
    return {
        "ok": True,
        "refreshed": True,
        "last_call": last,
        "cache_ttl_remaining": last.get("cache_ttl_remaining"),
    }


def send_heartbeat() -> None:
    refresh_prompt_cache()


def heartbeat_loop() -> None:
    while not _heartbeat_stop.is_set():
        _heartbeat_stop.wait(config.HEARTBEAT_INTERVAL)
        if _heartbeat_stop.is_set():
            break

        from core import model_routing

        auto = model_routing.PROMPT_CACHE_AUTO_REFRESH
        pid, _ = model_routing.resolve_for_node("writing.main")
        if (
            not config.HEARTBEAT_ENABLED
            or not auto
            or not config.cache_enabled(pid)
        ):
            continue

        now = time.time()
        idle = now - state.last_user_active
        since_request = (
            now - state.last_request_time
            if state.last_request_time > 0
            else float("inf")
        )

        if idle > config.HEARTBEAT_IDLE_STOP:
            continue
        if since_request < config.HEARTBEAT_REFRESH_AFTER:
            continue
        if state.last_request_time == 0:
            continue

        send_heartbeat()


def start_heartbeat_thread() -> threading.Thread:
    t = threading.Thread(target=heartbeat_loop, daemon=True, name="heartbeat")
    t.start()
    return t
