"""章节文件 IO 与写入状态机（P4-D：从 app.chapter_io 迁入）。"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from core.data import novel_data
from infra import file_utils as bio
from infra.state import state
from core import chapters as chapter_text
from core import context as writing_context

_store_provider: Callable[[], object] | None = None
_path_resolver: Callable[[str], Path] | None = None


def configure(
    *,
    store_provider: Callable[[], object],
    path_resolver: Callable[[str], Path],
) -> None:
    global _store_provider, _path_resolver
    _store_provider = store_provider
    _path_resolver = path_resolver


def _paths(name: str) -> Path:
    if _path_resolver is None:
        raise RuntimeError("chapter_io 未 configure（需经 app.chapter_io 导入）")
    return _path_resolver(name)


def _store():
    if _store_provider is None:
        raise RuntimeError("chapter_io 未 configure（需经 app.chapter_io 导入）")
    return _store_provider()


def get_chapter_path(chapter_num: int) -> Path:
    return _paths("CHAPTERS_DIR") / f"ch{chapter_num:03d}.md"


def resolve_write_chapter_num(
    chapter_num: int | None = None, scene_id: str = ""
) -> int:
    if chapter_num and chapter_num > 0:
        return chapter_num
    if scene_id:
        scene = novel_data.get_scene(scene_id)
        if scene and scene.get("chapter_num"):
            return int(scene["chapter_num"])
    if state.write_chapter_num > 0:
        return state.write_chapter_num
    latest = writing_context.get_latest_chapter()
    return latest[0] if latest else 1


def get_chapters_text_for_scope(chapter_num: int, scope: str) -> str | None:
    return _store().chapters_text_for_scope(chapter_num, scope)


def read_chapter_content(chapter_num: int) -> str:
    path = get_chapter_path(chapter_num)
    return bio.read_text(path) if path.exists() else ""


def ensure_chapter_path(chapter_num: int) -> Path:
    chapters_dir = _paths("CHAPTERS_DIR")
    chapters_dir.mkdir(parents=True, exist_ok=True)
    path = get_chapter_path(chapter_num)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def get_or_create_write_chapter(chapter_num: int | None = None) -> tuple[int, Path]:
    num = resolve_write_chapter_num(chapter_num)
    return num, ensure_chapter_path(num)


def sanitize_chapter_text(text: str) -> str:
    return chapter_text.sanitize_chapter_text(text)


def instruction_save_mode(instruction: str) -> str:
    return chapter_text.instruction_save_mode(instruction)


def should_append_to_chapter(reply: str) -> bool:
    return chapter_text.should_append_to_chapter(reply)


def format_chapter_file(
    chapter_num: int, body: str, *, title: str | None = None
) -> str:
    return chapter_text.format_chapter_file(chapter_num, body, title=title)


def prepare_chapter_body_from_reply(
    reply: str, chapter_num: int
) -> tuple[str | None, str]:
    return chapter_text.prepare_chapter_body_from_reply(
        reply, chapter_num, chapter_text.apply_chapter_title
    )


def refresh_chapter_file_header(chapter_num: int, title: str) -> None:
    path = get_chapter_path(chapter_num)
    if not path.exists():
        return
    body = chapter_text.strip_chapter_file_header(bio.read_text(path))
    bio.write_text(
        path,
        format_chapter_file(chapter_num, body, title=title),
        append=False,
    )


def sync_chapter_title_from_file(chapter_num: int) -> str | None:
    text = read_chapter_content(chapter_num)
    if not text.strip():
        return None
    title, _ = chapter_text.split_chapter_markdown_header(text)
    if not title:
        title, _ = chapter_text.extract_chapter_title_from_reply(text)
    return chapter_text.apply_chapter_title(chapter_num, title)


def replace_chapter_content(
    text: str,
    chapter_path: Path,
    chapter_num: int,
    *,
    msg_index: int | None = None,
) -> tuple[int, str | None]:
    title, body = prepare_chapter_body_from_reply(text, chapter_num)
    if not body.strip():
        return 0, title
    formatted = format_chapter_file(chapter_num, body, title=title)
    state.last_append_undo = {
        "path": str(chapter_path),
        "content": bio.read_text(chapter_path),
        "msg_index": msg_index,
    }
    bio.write_text(chapter_path, formatted, append=False)
    return len(body), title


def append_to_chapter(
    text: str,
    chapter_path: Path,
    *,
    msg_index: int | None = None,
    chapter_num: int | None = None,
) -> tuple[int, str | None]:
    if chapter_num is None:
        m_match = re.match(r"ch(\d+)\.md$", chapter_path.name, re.IGNORECASE)
        chapter_num = int(m_match.group(1)) if m_match else 0
    if chapter_num > 0:
        title, body = prepare_chapter_body_from_reply(text, chapter_num)
    else:
        title, body = chapter_text.extract_chapter_title_from_reply(text)
    content = body.strip()
    if not content:
        return 0, title
    existing = bio.read_text(chapter_path)
    state.last_append_undo = {
        "path": str(chapter_path),
        "content": existing,
        "msg_index": msg_index,
    }
    if not existing.strip() and chapter_num > 0:
        formatted = format_chapter_file(chapter_num, content, title=title)
        bio.write_text(chapter_path, formatted, append=False)
        return len(content), title
    if chapter_num > 0 and title:
        refresh_chapter_file_header(chapter_num, title)
    bio.write_text(chapter_path, f"\n\n{content}\n", append=True)
    return len(content), title


def count_unsaved_chapter_turns() -> int:
    return sum(
        1
        for i, msg in enumerate(state.conversation_history)
        if msg["role"] == "assistant"
        and i not in state.appended_indices
        and should_append_to_chapter(msg["content"])
    )


def flush_chapter_writes(*, silent: bool = False) -> int:
    chapter_num, chapter_path = get_or_create_write_chapter()
    total_chars = 0
    count = 0

    for i, msg in enumerate(state.conversation_history):
        if msg["role"] != "assistant" or i in state.appended_indices:
            continue
        if not should_append_to_chapter(msg["content"]):
            continue
        chars = append_to_chapter(msg["content"], chapter_path, msg_index=i)
        if chars[0]:
            state.appended_indices.add(i)
            total_chars += chars[0]
            count += 1

    if count and not silent:
        print(
            f"💾 已保存 {count} 条正文到 data/chapters/ch{chapter_num:03d}.md"
            f"（共 +{total_chars} 字）"
        )
    return count


def sync_appended_indices_with_chapter() -> None:
    if not state.conversation_history:
        return
    _, chapter_path = get_or_create_write_chapter()
    body = bio.read_text(chapter_path)
    if not body.strip():
        return
    for i, msg in enumerate(state.conversation_history):
        if msg["role"] != "assistant" or i in state.appended_indices:
            continue
        if not should_append_to_chapter(msg["content"]):
            continue
        content = msg["content"].strip()
        if len(content) >= 80 and content in body:
            state.appended_indices.add(i)
