"""写书对话编排（HTTP/CLI 共用入口）。"""
from __future__ import annotations

from collections.abc import Iterator

import infra.config as config
from app import writing_svc as ws


def chat_history() -> dict:
    return {
        "messages": ws.get_chat_history(),
        "appended_indices": ws.get_appended_indices(),
        "context_turns": config.CHAT_CONTEXT_TURNS,
    }


def chat(
    instruction: str,
    *,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> dict:
    return ws.writing_chat(instruction, scene_beat, scene_id, chapter_num)


def chat_stream(
    instruction: str,
    *,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> Iterator[str]:
    return ws.writing_chat_stream(instruction, scene_beat, scene_id, chapter_num)


def clear_chat() -> dict:
    return ws.clear_chat_session()


def set_write_chapter(num: int) -> dict:
    return ws.set_write_chapter_num(num)


def restore_chat() -> dict:
    return ws.restore_chat_session()


def get_prompts() -> dict:
    return ws.load_chat_prompts()


def save_prompts(prompts: list[dict]) -> dict:
    return ws.save_chat_prompts(prompts)


def undo_last_chapter_write() -> dict:
    from app import writing_turns as wt

    return wt.undo_last_chapter_append()


def apply_chapter_turn(chapter_num: int, msg_index: int, source: str) -> dict:
    from app import writing_turns as wt

    if source == "assistant":
        return wt.apply_assistant_turn_to_chapter(chapter_num, msg_index)
    if source == "user_draft":
        return wt.apply_user_draft_turn_to_chapter(chapter_num, msg_index)
    return {"ok": False, "error": "source 必须是 assistant 或 user_draft"}
