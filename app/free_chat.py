"""自由聊天业务服务（有状态，依赖 app_state + app.paths.FREE_CHAT_FILE）。"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

import infra.config as config
from core import llm as _llm
from app import paths as _paths
from infra.state import state


def _free_chat_file() -> Path:
    return _paths.resolved("FREE_CHAT_FILE")


def _trim_free_history() -> list[dict]:
    turns = config.FREE_CHAT_CONTEXT_TURNS
    stored = len(state.free_chat_history)
    if turns <= 0 or stored <= turns * 2:
        trimmed = list(state.free_chat_history)
    else:
        trimmed = state.free_chat_history[-(turns * 2) :]
    return trimmed


def _resolve_free_provider(provider: str | None = None) -> str:
    pid = provider or state.free_chat_provider
    if pid not in config.PROVIDERS:
        return config.FREE_CHAT_PROVIDER
    return pid


def _free_chat_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_free_thread_id() -> str:
    return uuid.uuid4().hex[:12]


def _default_free_thread_title() -> str:
    n = len(state.free_chat_threads) + 1
    return f"新话题 {n}"


def _thread_title_from_message(text: str) -> str:
    one_line = re.sub(r"\s+", " ", text.strip())
    if not one_line:
        return _default_free_thread_title()
    return one_line[:36] + ("…" if len(one_line) > 36 else "")


def _new_free_thread(*, title: str | None = None, messages: list[dict] | None = None) -> dict:
    now = _free_chat_now()
    return {
        "id": _new_free_thread_id(),
        "title": (title or _default_free_thread_title()).strip() or _default_free_thread_title(),
        "created_at": now,
        "updated_at": now,
        "messages": list(messages or []),
    }


def _find_free_thread(thread_id: str) -> dict | None:
    for thread in state.free_chat_threads:
        if thread.get("id") == thread_id:
            return thread
    return None


def _active_free_thread() -> dict | None:
    if not state.free_chat_threads:
        return None
    thread = _find_free_thread(state.free_chat_active_thread_id)
    if thread is not None:
        return thread
    return state.free_chat_threads[0]


def _sync_free_history_from_active() -> None:
    thread = _active_free_thread()
    if thread is None:
        state.free_chat_history = []
        state.free_chat_active_thread_id = ""
        return
    state.free_chat_active_thread_id = thread["id"]
    state.free_chat_history = list(thread.get("messages", []))


def _persist_active_thread_messages() -> None:
    thread = _active_free_thread()
    if thread is None:
        return
    thread["messages"] = list(state.free_chat_history)
    thread["updated_at"] = _free_chat_now()


def _ensure_free_chat_threads() -> dict:
    if not state.free_chat_threads:
        thread = _new_free_thread(title="默认话题")
        state.free_chat_threads = [thread]
        state.free_chat_active_thread_id = thread["id"]
        state.free_chat_history = []
    _sync_free_history_from_active()
    return _active_free_thread() or state.free_chat_threads[0]


def _free_thread_summary(thread: dict) -> dict:
    messages = thread.get("messages") or []
    preview = ""
    for msg in reversed(messages):
        if (msg.get("content") or "").strip():
            preview = (msg.get("content") or "").strip().replace("\n", " ")[:80]
            break
    return {
        "id": thread.get("id", ""),
        "title": thread.get("title") or "未命名话题",
        "created_at": thread.get("created_at", ""),
        "updated_at": thread.get("updated_at", ""),
        "message_count": len(messages),
        "preview": preview,
    }


def save_free_chat() -> None:
    path = _free_chat_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    _persist_active_thread_messages()
    payload = {
        "saved_at": _free_chat_now(),
        "provider": state.free_chat_provider,
        "active_thread_id": state.free_chat_active_thread_id,
        "threads": state.free_chat_threads,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_free_chat() -> None:
    path = _free_chat_file()
    state.free_chat_threads = []
    state.free_chat_active_thread_id = ""
    state.free_chat_history = []
    if not path.exists():
        _ensure_free_chat_threads()
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        saved_provider = data.get("provider")
        if saved_provider in config.PROVIDERS:
            state.free_chat_provider = saved_provider

        raw_threads = data.get("threads")
        if isinstance(raw_threads, list) and raw_threads:
            state.free_chat_threads = [
                {
                    "id": str(t.get("id") or _new_free_thread_id()),
                    "title": (t.get("title") or "未命名话题").strip() or "未命名话题",
                    "created_at": t.get("created_at") or _free_chat_now(),
                    "updated_at": t.get("updated_at") or _free_chat_now(),
                    "messages": list(t.get("messages") or []),
                }
                for t in raw_threads
                if isinstance(t, dict)
            ]
            active_id = data.get("active_thread_id")
            if active_id and _find_free_thread(str(active_id)):
                state.free_chat_active_thread_id = str(active_id)
            else:
                state.free_chat_active_thread_id = state.free_chat_threads[0]["id"]
            _sync_free_history_from_active()
            return

        legacy_messages = list(data.get("messages") or [])
        title = "默认话题"
        for msg in legacy_messages:
            if msg.get("role") == "user" and (msg.get("content") or "").strip():
                title = _thread_title_from_message(msg["content"])
                break
        thread = _new_free_thread(title=title, messages=legacy_messages)
        state.free_chat_threads = [thread]
        state.free_chat_active_thread_id = thread["id"]
        _sync_free_history_from_active()
        save_free_chat()
    except (json.JSONDecodeError, OSError):
        state.free_chat_threads = []
        _ensure_free_chat_threads()


def get_free_chat_provider() -> str:
    return state.free_chat_provider


def set_free_chat_provider(provider: str) -> dict:
    if provider not in config.PROVIDERS:
        return {"ok": False, "error": f"未知提供商: {provider}"}
    state.free_chat_provider = provider
    save_free_chat()
    return {"ok": True, "provider": provider}


def get_free_chat_threads() -> list[dict]:
    _ensure_free_chat_threads()
    active_id = state.free_chat_active_thread_id
    threads = [_free_thread_summary(t) for t in state.free_chat_threads]
    threads.sort(key=lambda t: t.get("updated_at") or "", reverse=True)
    for item in threads:
        item["active"] = item.get("id") == active_id
    return threads


def get_free_chat_history() -> list[dict]:
    _ensure_free_chat_threads()
    return list(state.free_chat_history)


def get_free_chat_state() -> dict:
    _ensure_free_chat_threads()
    active = _active_free_thread()
    return {
        "messages": list(state.free_chat_history),
        "provider": state.free_chat_provider,
        "active_thread_id": state.free_chat_active_thread_id,
        "active_thread_title": (active or {}).get("title", ""),
        "threads": get_free_chat_threads(),
    }


def create_free_chat_thread(title: str | None = None) -> dict:
    _ensure_free_chat_threads()
    thread = _new_free_thread(title=title)
    state.free_chat_threads.append(thread)
    state.free_chat_active_thread_id = thread["id"]
    state.free_chat_history = []
    save_free_chat()
    return {"ok": True, "thread": _free_thread_summary(thread)}


def switch_free_chat_thread(thread_id: str) -> dict:
    _ensure_free_chat_threads()
    thread = _find_free_thread(thread_id)
    if thread is None:
        return {"ok": False, "error": "话题不存在"}
    _persist_active_thread_messages()
    state.free_chat_active_thread_id = thread_id
    _sync_free_history_from_active()
    save_free_chat()
    return {"ok": True, **get_free_chat_state()}


def rename_free_chat_thread(thread_id: str, title: str) -> dict:
    _ensure_free_chat_threads()
    thread = _find_free_thread(thread_id)
    if thread is None:
        return {"ok": False, "error": "话题不存在"}
    clean = title.strip()
    if not clean:
        return {"ok": False, "error": "话题名称不能为空"}
    thread["title"] = clean[:80]
    thread["updated_at"] = _free_chat_now()
    save_free_chat()
    return {"ok": True, "thread": _free_thread_summary(thread)}


def delete_free_chat_thread(thread_id: str) -> dict:
    _ensure_free_chat_threads()
    if len(state.free_chat_threads) <= 1:
        return {"ok": False, "error": "至少保留一个话题"}
    thread = _find_free_thread(thread_id)
    if thread is None:
        return {"ok": False, "error": "话题不存在"}
    if thread_id == state.free_chat_active_thread_id:
        _persist_active_thread_messages()
    state.free_chat_threads = [
        t for t in state.free_chat_threads if t.get("id") != thread_id
    ]
    if state.free_chat_active_thread_id == thread_id:
        state.free_chat_active_thread_id = state.free_chat_threads[0]["id"]
        _sync_free_history_from_active()
    save_free_chat()
    return {"ok": True, **get_free_chat_state()}


def clear_free_chat() -> dict:
    _ensure_free_chat_threads()
    state.free_chat_history.clear()
    thread = _active_free_thread()
    if thread is not None:
        thread["messages"] = []
        thread["updated_at"] = _free_chat_now()
    save_free_chat()
    return {"ok": True, **get_free_chat_state()}


def delete_free_chat_message(index: int) -> dict:
    """删除当前话题中的一条消息（按 0 起序号）。"""
    _ensure_free_chat_threads()
    n = len(state.free_chat_history)
    if index < 0 or index >= n:
        return {
            "ok": False,
            "error": f"无效的消息序号（当前共 {n} 条，有效范围 0–{max(0, n - 1)}）",
        }
    removed = state.free_chat_history[index]
    state.free_chat_history.pop(index)
    thread = _active_free_thread()
    if thread is not None:
        thread["messages"] = list(state.free_chat_history)
        thread["updated_at"] = _free_chat_now()
    save_free_chat()
    return {"ok": True, **get_free_chat_state()}


def free_chat(message: str, provider: str | None = None) -> dict:
    """自由聊天：无系统提示词，纯对话，不写章节。"""
    text = message.strip()
    if not text:
        return {"ok": False, "error": "消息不能为空"}

    _ensure_free_chat_threads()
    thread = _active_free_thread()
    if thread is None:
        return {"ok": False, "error": "无可用话题"}

    pid = _resolve_free_provider(provider)
    if provider and pid != state.free_chat_provider:
        state.free_chat_provider = pid

    if not thread.get("messages") and (thread.get("title") or "").startswith("新话题"):
        thread["title"] = _thread_title_from_message(text)

    state.free_chat_history.append({"role": "user", "content": text})
    trimmed = _trim_free_history()
    reply = _llm.call_api(
        None,
        trimmed,
        max_tokens=config.FREE_CHAT_MAX_TOKENS,
        provider=pid,
        tag="自由聊",
        silent=True,
    )
    if reply is None:
        state.free_chat_history.pop()
        return {"ok": False, "error": _llm.get_last_call_info().get("error", "发送失败")}

    state.free_chat_history.append({"role": "assistant", "content": reply})
    thread["updated_at"] = _free_chat_now()
    save_free_chat()
    return {
        "ok": True,
        "reply": reply,
        "provider": pid,
        **_llm.get_last_call_info(),
    }
