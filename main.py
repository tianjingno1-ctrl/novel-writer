#!/usr/bin/env python3
"""长篇小说辅助写作工具 — 路径锚点 + 测试契约 re-export + CLI 入口。"""

from __future__ import annotations

from pathlib import Path

import config
from app_state import state
from core.api import TokenUsage
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
from app.chapters_api import (
    create_next_chapter,
    get_chapter_by_num,
    list_chapters,
    save_chapter_by_num,
)
from app.codex import get_codex, save_codex
from app.guide import get_guide_status
from app.free_chat import load_free_chat

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
from app.main_forwards import _ALIASES, _MODULES, resolve as _resolve_forward


def __getattr__(name: str):
    return _resolve_forward(name)


def __dir__():
    return sorted(
        set(globals()) | set(_MODULES) | set(_ALIASES) | {"__getattr__", "__dir__"}
    )


def main() -> None:
    from app.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()

from app import llm as _llm_module

_request_lock = _llm_module._request_lock
