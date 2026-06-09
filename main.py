#!/usr/bin/env python3
"""长篇小说辅助写作工具 — 主程序。"""

from __future__ import annotations

import atexit
import json
import re
import signal
import uuid
from datetime import datetime
from pathlib import Path

import config
import change_history
import quality_log
import file_utils
import novel_data
from app_state import state
from core.api import TokenUsage
from core import chapters as chapter_text
from app import batch_state
from app.bootstrap import bootstrap_library, init_context, init_data_dirs
from app.factories import (
    apply_chapter_title,
    book_paths_view as _book_paths_view,
    book_store as _book_store,
    generator_deps as _generator_deps,
    invalidate_chapter_injection as _invalidate_chapter_injection,
    maintain_deps as _maintain_deps,
    quality_log_entry as _quality_log_entry,
    resolve_chapter_num as _resolve_chapter_num,
    reviewer_deps as _reviewer_deps,
    short_story_archive_skip as _short_story_archive_skip,
)
from app.chapter_titles import (
    refresh_chapter_file_header,
    sync_all_chapter_titles_from_files,
)
from app.chapters_api import (
    create_next_chapter,
    get_chapter_by_num,
    list_chapters,
    save_chapter_by_num,
)
from app.codex import get_codex, save_codex
from app.guide import get_guide_status
from app.free_chat import (
    _active_free_thread,
    _default_free_thread_title,
    _ensure_free_chat_threads,
    _find_free_thread,
    _free_chat_now,
    _free_thread_summary,
    _new_free_thread,
    _new_free_thread_id,
    _persist_active_thread_messages,
    _resolve_free_provider,
    _sync_free_history_from_active,
    _thread_title_from_message,
    _trim_free_history,
    clear_free_chat,
    create_free_chat_thread,
    delete_free_chat_message,
    delete_free_chat_thread,
    free_chat,
    get_free_chat_history,
    get_free_chat_provider,
    get_free_chat_state,
    get_free_chat_threads,
    load_free_chat,
    rename_free_chat_thread,
    save_free_chat,
    set_free_chat_provider,
    switch_free_chat_thread,
)
from summarizer import (
    CHECK_SYSTEM,
    OUTLINE_SYSTEM,
    SUMMARY_SYSTEM,
    WRITING_INSTRUCTION,
    build_check_user_message,
    build_outline_user_message,
    build_summary_user_message,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHAPTERS_DIR = DATA_DIR / "chapters"
BACKUPS_DIR = DATA_DIR / "backups"
COST_LOG = BASE_DIR / "cost_log.txt"
COST_LOG_JSONL = BASE_DIR / "cost_log.jsonl"
CONTEXT_LOG_JSONL = DATA_DIR / "context_log.jsonl"
SESSION_FILE = DATA_DIR / "session_autosave.json"

SESSION_MD_FILE = DATA_DIR / "session_autosave.md"
FREE_CHAT_FILE = DATA_DIR / "free_chat.json"

WORLD_FILE = DATA_DIR / "world.md"
STYLE_FILE = DATA_DIR / "style.md"
CHARACTERS_FILE = DATA_DIR / "characters.md"
CHAR_CURRENT_FILE = DATA_DIR / "char_current.md"
CHAR_STATIC_FILE = DATA_DIR / "char_static.md"
CHAR_DYNAMIC_FILE = DATA_DIR / "char_dynamic.md"
SUMMARIES_FILE = DATA_DIR / "summaries.md"
SUMMARIES_ARCHIVE_FILE = DATA_DIR / "summaries_archive.md"
SUMMARIES_RECENT_FILE = DATA_DIR / "summaries_recent.md"
PLOT_THREADS_FILE = DATA_DIR / "plot_threads.md"
PLOT_THREADS_LOCKED_FILE = DATA_DIR / "plot_threads_locked.md"
PLOT_THREADS_ACTIVE_FILE = DATA_DIR / "plot_threads_active.md"
OUTLINE_LATEST_FILE = DATA_DIR / "outline_latest.md"
CHAT_PROMPTS_FILE = DATA_DIR / "chat_prompts.json"
ARCHIVE_FILE = DATA_DIR / "book_archive.md"

from app.bootstrap_data import DEFAULT_CHAT_PROMPTS, INITIAL_FILE_TEMPLATES

DISCUSSION_PREFIXES = ("[讨论]", "[问答]", "[建议]", "[说明]", "[分析]")
META_LINE_PREFIXES = ("以下是", "我建议", "可以考虑", "总结：", "分析：", "注意：", "说明：")

state.free_chat_provider = config.FREE_CHAT_PROVIDER


from app.cost import (
    _register_change_history,
    calc_cost,
    calc_cost_no_cache,
    get_total_cost,
    load_total_cost,
    load_total_cost_from_jsonl,
    log_cost,
    set_total_cost,
    _build_last_call_info,
)


CODEX_FILES = {
    "world": WORLD_FILE,
    "style": STYLE_FILE,
    "characters": CHARACTERS_FILE,
    "char_static": CHAR_STATIC_FILE,
    "char_dynamic": CHAR_DYNAMIC_FILE,
    "char_current": CHAR_CURRENT_FILE,
    "summaries_archive": SUMMARIES_ARCHIVE_FILE,
    "summaries_recent": SUMMARIES_RECENT_FILE,
    "summaries": SUMMARIES_FILE,
    "plot_threads_locked": PLOT_THREADS_LOCKED_FILE,
    "plot_threads_active": PLOT_THREADS_ACTIVE_FILE,
    "plot_threads": PLOT_THREADS_FILE,
}


from app.book_io import (
    _archive_section_for_path,
    _sync_archive_section_from_file,
    backup_file,
    read_text,
    write_text,
)
from app.writing_ctx import (
    _USER_CHAPTER_BLOCK_RE,
    _bind_writing_context,
    _collect_dynamic_layer_parts,
    _outline_context_ready,
    _read_char_static,
    _read_plot_active,
    _read_plot_locked,
    _record_context_debug,
    cache_block,
    count_summaries,
    extract_chapter_body_from_user_message,
    get_char_context_for_check,
    get_characters_block,
    get_dynamic_context_block,
    get_last_context_debug,
    get_latest_chapter,
    get_stable_archive_block,
    get_summaries_combined,
    get_world_block,
)


def build_cached_system(
    instruction: str,
    provider: str | None = None,
    *,
    include_scene_context: bool = True,
) -> list[dict] | str:
    from app import llm

    return llm.build_cached_system(
        instruction,
        provider,
        include_scene_context=include_scene_context,
    )


def _estimate_tokens(text: str) -> int:
    from app import llm

    return llm._estimate_tokens(text)


def _analyze_system(system: list[dict] | str | None) -> dict[str, int]:
    from app import llm

    return llm._analyze_system(system)


def _summarize_messages(messages: list[dict]) -> list[dict]:
    from app import llm

    return llm._summarize_messages(messages)


def _build_context_report(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    tag: str,
    provider: str | None,
) -> dict:
    from app import llm

    return llm._build_context_report(
        system, messages, tag=tag, provider=provider
    )


def log_request_context(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    tag: str = "请求",
    provider: str | None = None,
) -> dict:
    from app import llm

    return llm.log_request_context(
        system, messages, tag=tag, provider=provider
    )


def prepare_messages_for_context(history: list[dict]) -> list[dict]:
    from app import llm

    return llm.prepare_messages_for_context(history)


def trim_history(history: list[dict], max_turns: int | None = None) -> list[dict]:
    from app import llm

    return llm.trim_history(history, max_turns)


def get_last_call_info() -> dict:
    from app import llm

    return llm.get_last_call_info()


def _is_stream_disconnect_error(exc: Exception) -> bool:
    from app import llm

    return llm._is_stream_disconnect_error(exc)


def _record_call_usage(usage: TokenUsage, pid: str, *, tag: str = "请求") -> None:
    from app import llm

    llm._record_call_usage(usage, pid, tag=tag)


def _api_error_message(exc: Exception) -> str:
    from app import llm

    return llm._api_error_message(exc)


def call_api(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    tag: str = "请求",
    provider: str | None = None,
    silent: bool = False,
) -> str | None:
    from app import llm

    return llm.call_api(
        system,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        tag=tag,
        provider=provider,
        silent=silent,
    )


_APPEND_INSTRUCTION_KEYWORDS = (
    "续写",
    "接着写",
    "继续写",
    "接下去",
    "往后写",
    "续上一段",
    "往下写",
)
def resolve_write_chapter_num(
    chapter_num: int | None = None, scene_id: str = ""
) -> int:
    from app import chapter_io as ch

    return ch.resolve_write_chapter_num(chapter_num, scene_id)


def get_chapter_path(chapter_num: int) -> Path:
    from app import chapter_io as ch

    return ch.get_chapter_path(chapter_num)


def read_chapter_content(chapter_num: int) -> str:
    from app import chapter_io as ch

    return ch.read_chapter_content(chapter_num)


def ensure_chapter_path(chapter_num: int) -> Path:
    from app import chapter_io as ch

    return ch.ensure_chapter_path(chapter_num)


def get_or_create_write_chapter(chapter_num: int | None = None) -> tuple[int, Path]:
    from app import chapter_io as ch

    return ch.get_or_create_write_chapter(chapter_num)


def sanitize_chapter_text(text: str) -> str:
    from app import chapter_io as ch

    return ch.sanitize_chapter_text(text)


def instruction_save_mode(instruction: str) -> str:
    from app import chapter_io as ch

    return ch.instruction_save_mode(instruction)


def should_append_to_chapter(reply: str) -> bool:
    from app import chapter_io as ch

    return ch.should_append_to_chapter(reply)


def replace_chapter_content(
    text: str,
    chapter_path: Path,
    chapter_num: int,
    *,
    msg_index: int | None = None,
) -> tuple[int, str | None]:
    from app import chapter_io as ch

    return ch.replace_chapter_content(
        text, chapter_path, chapter_num, msg_index=msg_index
    )


def append_to_chapter(
    text: str,
    chapter_path: Path,
    *,
    msg_index: int | None = None,
    chapter_num: int | None = None,
) -> tuple[int, str | None]:
    from app import chapter_io as ch

    return ch.append_to_chapter(
        text, chapter_path, msg_index=msg_index, chapter_num=chapter_num
    )


def sync_appended_indices_with_chapter() -> None:
    from app import chapter_io as ch

    ch.sync_appended_indices_with_chapter()


def undo_last_chapter_append() -> dict:
    from app import writing_turns as wt

    return wt.undo_last_chapter_append()


def parse_chapter_header_line(line: str) -> str | None:
    return chapter_text.parse_chapter_header_line(line)


def split_chapter_markdown_header(text: str) -> tuple[str | None, str]:
    return chapter_text.split_chapter_markdown_header(text)


def extract_chapter_title_from_reply(text: str) -> tuple[str | None, str]:
    return chapter_text.extract_chapter_title_from_reply(text)


def strip_chapter_file_header(text: str) -> str:
    return chapter_text.strip_chapter_file_header(text)


def sync_chapter_title_from_file(chapter_num: int) -> str | None:
    from app import chapter_io as ch

    return ch.sync_chapter_title_from_file(chapter_num)


def prepare_chapter_body_from_reply(
    reply: str, chapter_num: int
) -> tuple[str | None, str]:
    from app import chapter_io as ch

    return ch.prepare_chapter_body_from_reply(reply, chapter_num)


def format_chapter_file(
    chapter_num: int, body: str, *, title: str | None = None
) -> str:
    from app import chapter_io as ch

    return ch.format_chapter_file(chapter_num, body, title=title)


def _clear_assistant_appended_indices() -> None:
    for i, msg in enumerate(state.conversation_history):
        if msg["role"] == "assistant":
            state.appended_indices.discard(i)


def apply_assistant_turn_to_chapter(chapter_num: int, msg_index: int) -> dict:
    """用某条 AI 回复**替换**整章正文（非追加）。"""
    from app import writing_turns as wt

    return wt.apply_assistant_turn_to_chapter(chapter_num, msg_index)


def apply_user_draft_turn_to_chapter(chapter_num: int, msg_index: int) -> dict:
    """用首轮用户消息里附带的章节草稿替换整章正文。"""
    from app import writing_turns as wt

    return wt.apply_user_draft_turn_to_chapter(chapter_num, msg_index)


def do_undo() -> None:
    from app.cli import do_undo as _fn

    _fn()


def count_unsaved_chapter_turns() -> int:
    from app import chapter_io as ch

    return ch.count_unsaved_chapter_turns()


def flush_chapter_writes(*, silent: bool = False) -> int:
    from app import chapter_io as ch

    return ch.flush_chapter_writes(silent=silent)


def save_chapter_after_reply(
    reply: str,
    msg_index: int,
    *,
    write_chapter_num: int | None = None,
    instruction: str = "",
) -> dict | None:
    """AI 回复后自动保存到目标章节。"""
    from app import writing_chat as wc

    return wc.save_chapter_after_reply(
        reply,
        msg_index,
        write_chapter_num=write_chapter_num,
        instruction=instruction,
    )


def touch_user_active() -> None:
    from app import writing_session as ws

    ws.touch_user_active()


def _session_chapter_num() -> int:
    from app import writing_session as ws

    return ws._session_chapter_num()


def format_session_markdown(saved_at: str, reason: str) -> str:
    from app import writing_session as ws

    return ws.format_session_markdown(saved_at, reason)


def save_session(reason: str = "auto", *, silent: bool = False) -> bool:
    from app import writing_session as ws

    return ws.save_session(reason, silent=silent)


def clear_session_files() -> None:
    from app import writing_session as ws

    ws.clear_session_files()


def load_session_from_disk() -> dict | None:
    from app import writing_session as ws

    return ws.load_session_from_disk()


def has_pending_session() -> bool:
    from app import writing_session as ws

    return ws.has_pending_session()


def remind_pending_session_on_startup() -> None:
    from app import writing_session as ws

    ws.remind_pending_session_on_startup()


def restore_chat_session() -> dict:
    from app import writing_session as ws

    return ws.restore_chat_session()


def auto_restore_session_if_needed() -> bool:
    from app import writing_session as ws

    return ws.auto_restore_session_if_needed()


def do_restore() -> None:
    from app.cli import do_restore as _fn

    _fn()


def do_save() -> None:
    from app.cli import do_save as _fn

    _fn()


def remind_unsaved_on_exit() -> None:
    from app.cli import remind_unsaved_on_exit as _fn

    _fn()


def graceful_exit(message: str = "再见！") -> None:
    from app.cli import graceful_exit as _fn

    _fn(message)


def _handle_exit_signal(signum, frame) -> None:
    from app.cli import _handle_exit_signal as _fn

    _fn(signum, frame)


def _atexit_save() -> None:
    from app.cli import _atexit_save as _fn

    _fn()


def setup_exit_handlers() -> None:
    from app.cli import setup_exit_handlers as _fn

    _fn()


def do_writing(instruction: str) -> None:
    from app.cli import do_writing as _fn

    _fn(instruction)


def writing_chat(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> dict:
    """Web/API：结构化写作对话，返回 JSON 友好结果。"""
    from app import writing_chat as wc

    return wc.writing_chat(instruction, scene_beat, scene_id, chapter_num)


def writing_chat_stream(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
):
    """流式写作对话，yield JSON 字符串事件。"""
    from app import writing_chat as wc

    return wc.writing_chat_stream(instruction, scene_beat, scene_id, chapter_num)


def get_chat_history() -> list[dict]:
    from app import writing_session as ws

    return ws.get_chat_history()


def load_chat_prompts() -> dict:
    from app import writing_session as ws

    return ws.load_chat_prompts()


def save_chat_prompts(prompts: list[dict]) -> dict:
    from app import writing_session as ws

    return ws.save_chat_prompts(prompts)


def get_appended_indices() -> list[int]:
    from app import writing_session as ws

    return ws.get_appended_indices()


def set_write_chapter_num(num: int) -> dict:
    from app import writing_session as ws

    return ws.set_write_chapter_num(num)


def clear_chat_session() -> None:
    from app import writing_session as ws

    ws.clear_chat_session()


from app.runtime import (
    _heartbeat_stop,
    get_app_status,
    heartbeat_loop,
    send_heartbeat,
    start_heartbeat_thread,
)


from app.chapter_io import get_chapters_text_for_scope
def ensure_chapter_file(chapter_num: int, title: str = "") -> dict:
    from app.chapters_api import _ensure_chapter_file

    return _ensure_chapter_file(chapter_num, title)


def do_summary() -> None:
    from app.cli import do_summary as _fn

    _fn()


def do_check() -> None:
    from app.cli import do_check as _fn

    _fn()


def do_outline(next_count: int = 3) -> None:
    from app.cli import do_outline as _fn

    _fn(next_count)


def do_patch(content: str) -> None:
    from app.cli import do_patch as _fn

    _fn(content)


def do_heartbeat_toggle() -> None:
    from app.cli import do_heartbeat_toggle as _fn

    _fn()


def do_provider(arg: str) -> None:
    from app.cli import do_provider as _fn

    _fn(arg)


def do_cost() -> None:
    from app.cli import do_cost as _fn

    _fn()


def backup_session_before_clear() -> None:
    from app import writing_session as ws

    ws.backup_session_before_clear()


def do_new() -> None:
    from app.cli import do_new as _fn

    _fn()


def print_help() -> None:
    from app.cli import print_help as _fn

    _fn()


def print_startup_banner() -> None:
    from app.cli import print_startup_banner as _fn

    _fn()


def main() -> None:
    from app.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()

from app import llm as _llm_module

_request_lock = _llm_module._request_lock
