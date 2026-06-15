"""多章正文拼接（整批档案同步等）。"""

from __future__ import annotations

from typing import Callable

import infra.config as config


def _truncate_chapter_body(content: str, max_chars: int) -> tuple[str, bool]:
    body = (content or "").strip()
    if len(body) <= max_chars:
        return body, False
    head = max_chars // 2
    tail = max_chars - head - 40
    return (
        body[:head]
        + "\n\n…（中段已省略，因单章过长）…\n\n"
        + body[-tail:],
        True,
    )


def build_chapters_text_block(
    chapter_nums: list[int],
    read_chapter: Callable[[int], str],
    *,
    max_total_chars: int | None = None,
    max_chapter_chars: int | None = None,
) -> tuple[str, bool, list[int]]:
    """拼接多章正文，返回 (文本, 是否发生截断, 实际包含的章号)。"""
    total_limit = max_total_chars or config.BULK_ARCHIVE_INPUT_MAX_CHARS
    ch_limit = max_chapter_chars or config.BULK_ARCHIVE_CHAPTER_MAX_CHARS
    parts: list[str] = []
    used: list[int] = []
    truncated = False
    budget = total_limit

    for num in chapter_nums:
        raw = (read_chapter(num) or "").strip()
        if not raw:
            continue
        piece, ch_trunc = _truncate_chapter_body(raw, ch_limit)
        if ch_trunc:
            truncated = True
        block = f"## 第{num}章\n{piece}"
        if len(block) > budget:
            if not parts:
                parts.append(block[:budget] + "\n…（本段输入已达上限，后续章节未纳入本段 API 输入）")
                used.append(num)
                truncated = True
            break
        parts.append(block)
        used.append(num)
        budget -= len(block) + 2

    return "\n\n".join(parts), truncated, used
