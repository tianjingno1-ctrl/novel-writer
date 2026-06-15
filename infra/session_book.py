"""按 client scope + book_id 隔离写作会话进程态（E7）。"""

from __future__ import annotations

import copy
from contextvars import ContextVar

from infra.state import state

_client_scope: ContextVar[str] = ContextVar("novel_client_scope", default="default")
_snapshots: dict[str, dict] = {}


def set_client_scope(scope: str) -> None:
    text = (scope or "").strip() or "default"
    _client_scope.set(text)


def get_client_scope() -> str:
    return _client_scope.get()


def session_key(book_id: str) -> str:
    bid = (book_id or "").strip()
    if not bid:
        bid = "_none"
    return f"{get_client_scope()}:{bid}"


def capture_writing_state() -> dict:
    return {
        "conversation_history": copy.deepcopy(state.conversation_history),
        "session_includes_chapter": state.session_includes_chapter,
        "write_chapter_num": state.write_chapter_num,
        "last_injected_chapter_num": state.last_injected_chapter_num,
        "appended_indices": sorted(state.appended_indices),
        "last_append_undo": copy.deepcopy(state.last_append_undo),
        "last_context_debug": copy.deepcopy(state.last_context_debug),
    }


def apply_writing_state(snap: dict) -> None:
    state.conversation_history.clear()
    for msg in snap.get("conversation_history") or []:
        if isinstance(msg, dict) and msg.get("role"):
            state.conversation_history.append(
                {"role": msg["role"], "content": msg.get("content", "")}
            )
    state.session_includes_chapter = bool(snap.get("session_includes_chapter"))
    state.write_chapter_num = int(snap.get("write_chapter_num") or 0)
    state.last_injected_chapter_num = int(snap.get("last_injected_chapter_num") or 0)
    wn = state.write_chapter_num
    state.last_synced_active_scene_chapter = wn if wn > 0 else -1
    state.appended_indices.clear()
    state.appended_indices.update(int(i) for i in (snap.get("appended_indices") or []))
    state.last_append_undo = copy.deepcopy(snap.get("last_append_undo"))
    state.last_context_debug = copy.deepcopy(snap.get("last_context_debug") or {})


def clear_writing_state() -> None:
    state.conversation_history.clear()
    state.session_includes_chapter = False
    state.write_chapter_num = 0
    state.last_injected_chapter_num = 0
    state.last_synced_active_scene_chapter = -1
    state.appended_indices.clear()
    state.last_append_undo = None
    state.last_context_debug.clear()


def park_book_session(book_id: str) -> None:
    """切走前：内存快照 + 静默写盘（路径仍指向该书）。"""
    if not (book_id or "").strip():
        return
    if state.conversation_history:
        from app import writing_session as ws

        ws.save_session(reason="switch_book", silent=True)
    _snapshots[session_key(book_id)] = capture_writing_state()


def activate_book_session(book_id: str) -> None:
    """切入：优先内存快照，否则磁盘 session_autosave，否则空态。"""
    key = session_key(book_id)
    cached = _snapshots.get(key)
    if cached is not None:
        apply_writing_state(cached)
        return

    clear_writing_state()
    from app import writing_session as ws

    pending = ws.load_session_from_disk()
    if pending and _disk_session_matches_scope(pending):
        ws.restore_chat_session()


def _disk_session_matches_scope(data: dict) -> bool:
    saved_scope = str(data.get("client_scope") or "").strip()
    if not saved_scope:
        return True
    return saved_scope == get_client_scope()


def switch_book_sessions(old_book_id: str | None, new_book_id: str) -> None:
    old = (old_book_id or "").strip()
    new = (new_book_id or "").strip()
    if old and old != new:
        park_book_session(old)
    if new:
        activate_book_session(new)
    else:
        clear_writing_state()


def drop_book_session(book_id: str) -> None:
    _snapshots.pop(session_key(book_id), None)


def clear_all_snapshots() -> None:
    _snapshots.clear()
