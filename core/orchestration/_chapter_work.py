"""编排层共用：请求章号 → ChapterWork。"""

from __future__ import annotations

from collections.abc import Callable

from core.schemas.service import ChapterRef, ChapterWork


def chapter_work_from_num(
    chapter_num: int | None,
    resolve_chapter: Callable[[int | None], tuple[int, str] | dict],
) -> tuple[ChapterWork | None, dict | None]:
    resolved = resolve_chapter(chapter_num)
    if isinstance(resolved, dict):
        return None, resolved
    num, content = resolved
    return ChapterWork(ChapterRef(num=num), content), None
