"""章节写入状态机（apply-turn / undo）。P3-4a：实迁函数体；main re-export 测试/CLI 兼容。"""

from __future__ import annotations

import re
from pathlib import Path

from app import paths as _paths
from app import book_io as bio
from app import chapter_io as ch
from app import writing_ctx as _wctx
from app.factories import invalidate_chapter_injection
from app_state import state


def _chapter_path(chapter_num: int) -> Path:
    return _paths.resolved("CHAPTERS_DIR") / f"ch{chapter_num:03d}.md"


def _clear_assistant_appended_indices() -> None:
    for i, msg in enumerate(state.conversation_history):
        if msg["role"] == "assistant":
            state.appended_indices.discard(i)


def undo_last_chapter_append() -> dict:
    if state.last_append_undo is None:
        return {"ok": False, "error": "没有可撤销的章节写入"}
    undo = state.last_append_undo
    path = Path(undo["path"])
    bio.write_text(path, undo["content"], append=False, history_source="undo")
    msg_index = undo.get("msg_index")
    if msg_index is not None:
        state.appended_indices.discard(msg_index)
    state.last_append_undo = None
    m = re.search(r"ch(\d+)\.md", path.name)
    if m:
        invalidate_chapter_injection(int(m.group(1)))
    return {"ok": True, "file": path.name}


def apply_assistant_turn_to_chapter(chapter_num: int, msg_index: int) -> dict:
    """用某条 AI 回复**替换**整章正文（非追加）。"""
    from app import writing_session as ws

    path = _chapter_path(chapter_num)
    if not path.exists():
        return {"ok": False, "error": f"章节 ch{chapter_num:03d} 不存在"}

    if msg_index < 0 or msg_index >= len(state.conversation_history):
        return {"ok": False, "error": "无效的消息序号"}
    msg = state.conversation_history[msg_index]
    if msg["role"] != "assistant":
        return {"ok": False, "error": "只能选用 AI 回复替换章节"}
    content = msg["content"].strip()
    if not ch.should_append_to_chapter(content):
        return {"ok": False, "error": "该条为讨论/说明，不能作为章节正文"}

    title, body = ch.prepare_chapter_body_from_reply(content, chapter_num)
    if not body.strip():
        return {"ok": False, "error": "该条没有可用正文"}
    formatted = ch.format_chapter_file(chapter_num, body, title=title)
    bio.write_text(path, formatted, append=False)
    state.last_append_undo = None
    _clear_assistant_appended_indices()
    state.appended_indices.add(msg_index)
    invalidate_chapter_injection(chapter_num)
    ws.save_session("apply_turn", silent=True)
    return {
        "ok": True,
        "num": chapter_num,
        "msg_index": msg_index,
        "chars": len(formatted),
        "chapter_title": title,
        "source": "assistant",
    }


def apply_user_draft_turn_to_chapter(chapter_num: int, msg_index: int) -> dict:
    """用首轮用户消息里附带的章节草稿替换整章正文。"""
    from app import writing_session as ws

    path = _chapter_path(chapter_num)
    if not path.exists():
        return {"ok": False, "error": f"章节 ch{chapter_num:03d} 不存在"}

    if msg_index < 0 or msg_index >= len(state.conversation_history):
        return {"ok": False, "error": "无效的消息序号"}
    msg = state.conversation_history[msg_index]
    if msg["role"] != "user":
        return {"ok": False, "error": "只能选用用户消息中的章节草稿"}
    body = _wctx.extract_chapter_body_from_user_message(msg["content"])
    if not body:
        return {"ok": False, "error": "该轮指令里没有附带章节正文（仅首轮带全文时可用）"}

    formatted = ch.format_chapter_file(chapter_num, body)
    bio.write_text(path, formatted, append=False)
    state.last_append_undo = None
    _clear_assistant_appended_indices()
    invalidate_chapter_injection(chapter_num)
    ws.save_session("apply_turn", silent=True)
    return {
        "ok": True,
        "num": chapter_num,
        "msg_index": msg_index,
        "chars": len(formatted),
        "source": "user_draft",
    }
