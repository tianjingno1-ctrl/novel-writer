"""writing 路由适配层（P3-4b）。薄 forward，函数体留 main；P3-4c/d 逐步实迁。"""

from __future__ import annotations

from collections.abc import Iterator


def get_chat_history() -> list[dict]:
    import main

    return main.get_chat_history()


def get_appended_indices() -> list[int]:
    import main

    return main.get_appended_indices()


def touch_user_active() -> None:
    import main

    main.touch_user_active()


def writing_chat(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> dict:
    import main

    return main.writing_chat(instruction, scene_beat, scene_id, chapter_num)


def writing_chat_stream(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> Iterator[str]:
    import main

    return main.writing_chat_stream(instruction, scene_beat, scene_id, chapter_num)


def clear_chat_session() -> None:
    import main

    main.clear_chat_session()


def set_write_chapter_num(num: int) -> dict:
    import main

    return main.set_write_chapter_num(num)


def restore_chat_session() -> dict:
    import main

    return main.restore_chat_session()


def load_chat_prompts() -> dict:
    import main

    return main.load_chat_prompts()


def save_chat_prompts(prompts: list[dict]) -> dict:
    import main

    return main.save_chat_prompts(prompts)
