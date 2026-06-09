"""
写作上下文层（P3-5d-3）。

_bind_writing_context / get_*_block / extract_chapter_body
get_latest_chapter / _record_context_debug / count_summaries
"""

from __future__ import annotations

import re
from pathlib import Path

from app import book_io as bio
from app import paths as _paths
from app.chapters_api import list_chapters
from app_state import state
from core import context as writing_context


_USER_CHAPTER_BLOCK_RE = re.compile(
    r"^【当前章节：第(\d+)章】\s*\n+(.*?)(?:\n+【写作指令】|\Z)",
    re.DOTALL,
)


def _bind_writing_context() -> None:
    """将路径同步到 core.context（测试 patch main.*_FILE 时 paths.resolved 优先 main）。"""
    writing_context.bind(
        writing_context.BookPaths(
            world_file=_paths.resolved("WORLD_FILE"),
            style_file=_paths.resolved("STYLE_FILE"),
            characters_file=_paths.resolved("CHARACTERS_FILE"),
            char_static_file=_paths.resolved("CHAR_STATIC_FILE"),
            char_dynamic_file=_paths.resolved("CHAR_DYNAMIC_FILE"),
            char_current_file=_paths.resolved("CHAR_CURRENT_FILE"),
            summaries_archive_file=_paths.resolved("SUMMARIES_ARCHIVE_FILE"),
            summaries_recent_file=_paths.resolved("SUMMARIES_RECENT_FILE"),
            summaries_file=_paths.resolved("SUMMARIES_FILE"),
            plot_threads_locked_file=_paths.resolved("PLOT_THREADS_LOCKED_FILE"),
            plot_threads_active_file=_paths.resolved("PLOT_THREADS_ACTIVE_FILE"),
            plot_threads_file=_paths.resolved("PLOT_THREADS_FILE"),
        ),
        read_text=bio.read_text,
    )


def cache_block(text: str) -> dict:
    return writing_context.cache_block(text)


def _read_char_static() -> str:
    _bind_writing_context()
    return writing_context.read_char_static()


def _read_plot_locked() -> str:
    _bind_writing_context()
    return writing_context.read_plot_locked()


def _read_plot_active() -> str:
    _bind_writing_context()
    return writing_context.read_plot_active()


def get_latest_chapter() -> tuple[int, Path, str] | None:
    chapters = list_chapters()
    if not chapters:
        return None
    num, path = chapters[-1]
    return num, path, bio.read_text(path)


def count_summaries() -> int:
    combined = get_summaries_combined()
    return len(re.findall(r"【第\d+章", combined))


def _outline_context_ready() -> str | None:
    if get_latest_chapter() is None:
        return "没有找到章节文件"
    if count_summaries() == 0:
        return "请先生成章节概述（/summary 或 Web「生成概述」）"
    return None


def get_characters_block() -> str:
    _bind_writing_context()
    return writing_context.get_characters_block()


def get_stable_archive_block() -> str:
    _bind_writing_context()
    return writing_context.get_stable_archive_block()


def _collect_dynamic_layer_parts() -> list[dict]:
    _bind_writing_context()
    return writing_context.collect_dynamic_layer_parts()


def get_dynamic_context_block() -> str:
    _bind_writing_context()
    return writing_context.get_dynamic_context_block()


def get_char_context_for_check() -> str:
    _bind_writing_context()
    return writing_context.get_char_context_for_check()


def get_summaries_combined() -> str:
    _bind_writing_context()
    return writing_context.get_summaries_combined()


def get_world_block() -> str:
    _bind_writing_context()
    return writing_context.get_world_block()


def _record_context_debug(
    layers: list[dict],
    *,
    provider: str | None = None,
    messages: list[dict] | None = None,
    tag: str = "",
) -> None:
    from app import llm

    _bind_writing_context()
    writing_context.record_context_debug(
        layers,
        provider=provider,
        messages=messages,
        tag=tag,
        summarize_messages=llm._summarize_messages,
    )


def get_last_context_debug() -> dict:
    from app import llm

    if not state.last_context_debug:
        return {
            "ok": False,
            "error": "尚无请求记录，请先发送一次写书对话、自由聊或检查类请求",
        }
    data = dict(state.last_context_debug)
    data["ok"] = True
    data["last_call"] = llm.get_last_call_info()
    return data


def extract_chapter_body_from_user_message(content: str) -> str | None:
    """从首轮用户消息中取出附带的章节正文（不含写作指令）。"""
    m = _USER_CHAPTER_BLOCK_RE.match((content or "").strip())
    if not m:
        return None
    body = m.group(2).strip()
    return body or None
