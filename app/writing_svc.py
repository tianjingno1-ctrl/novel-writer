"""writing 路由适配层（P3-4b/c/d）。session → writing_session；chat → writing_chat。"""

from __future__ import annotations

from collections.abc import Iterator

from app import writing_chat as wc
from app import writing_session as ws


def get_chat_history() -> list[dict]:
    return ws.get_chat_history()


def get_appended_indices() -> list[int]:
    return ws.get_appended_indices()


def touch_user_active() -> None:
    ws.touch_user_active()


def writing_chat(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> dict:
    return wc.writing_chat(instruction, scene_beat, scene_id, chapter_num)


def writing_chat_stream(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> Iterator[str]:
    return wc.writing_chat_stream(instruction, scene_beat, scene_id, chapter_num)


def clear_chat_session() -> None:
    ws.clear_chat_session()


def set_write_chapter_num(num: int) -> dict:
    return ws.set_write_chapter_num(num)


def restore_chat_session() -> dict:
    return ws.restore_chat_session()


def load_chat_prompts() -> dict:
    return ws.load_chat_prompts()


def save_chat_prompts(prompts: list[dict]) -> dict:
    return ws.save_chat_prompts(prompts)
