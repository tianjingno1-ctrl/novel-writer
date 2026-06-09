"""单一路径来源（P3-1d）。切书经 sync_from_context；mirror_to_main 兼容测试 patch main.*。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from book_context import BookContext

# 全局固定（切书不变）
BASE_DIR: Path | None = None
COST_LOG: Path | None = None
COST_LOG_JSONL: Path | None = None

# main 书相关路径（切书更新）
DATA_DIR: Path | None = None
CHAPTERS_DIR: Path | None = None
BACKUPS_DIR: Path | None = None
CONTEXT_LOG_JSONL: Path | None = None
SESSION_FILE: Path | None = None
SESSION_MD_FILE: Path | None = None
FREE_CHAT_FILE: Path | None = None
WORLD_FILE: Path | None = None
STYLE_FILE: Path | None = None
CHARACTERS_FILE: Path | None = None
CHAR_CURRENT_FILE: Path | None = None
CHAR_STATIC_FILE: Path | None = None
CHAR_DYNAMIC_FILE: Path | None = None
SUMMARIES_FILE: Path | None = None
SUMMARIES_ARCHIVE_FILE: Path | None = None
SUMMARIES_RECENT_FILE: Path | None = None
PLOT_THREADS_FILE: Path | None = None
PLOT_THREADS_LOCKED_FILE: Path | None = None
PLOT_THREADS_ACTIVE_FILE: Path | None = None
OUTLINE_LATEST_FILE: Path | None = None
CHAT_PROMPTS_FILE: Path | None = None
ARCHIVE_FILE: Path | None = None
CODEX_FILES: dict[str, Path] | None = None

# novel_data 镜像（切书更新）
ND_DATA_DIR: Path | None = None
ND_BACKUPS_DIR: Path | None = None
ND_PLAN_FILE: Path | None = None
ND_PROJECT_FILE: Path | None = None
ND_CODEX_DIR: Path | None = None
ND_CODEX_ACTIVE_FILE: Path | None = None

_fixed_initialized = False


def resolved(name: str) -> Path:
    """paths 值；若测试 patch 了 main 且与 paths 不一致，优先 main。"""
    import main

    local: Path | None = globals()[name]
    main_val: Path = getattr(main, name)
    if local is None:
        return main_val
    if main_val != local:
        return main_val
    return local


def resolved_codex_files() -> dict[str, Path]:
    """CODEX_FILES；若测试 patch 了 main.CODEX_FILES 引用，优先 main。"""
    import main

    local = CODEX_FILES
    main_val = main.CODEX_FILES
    if local is None:
        return main_val
    if main_val is not local:
        return main_val
    return local


def init_defaults() -> None:
    """启动时从 main 读取 BASE_DIR / COST_LOG（切书不变的路径）。"""
    global BASE_DIR, COST_LOG, COST_LOG_JSONL, _fixed_initialized
    import main

    BASE_DIR = main.BASE_DIR
    COST_LOG = main.COST_LOG
    COST_LOG_JSONL = main.COST_LOG_JSONL
    _fixed_initialized = True


def _ensure_fixed_paths() -> None:
    if not _fixed_initialized:
        init_defaults()


def sync_from_context(ctx: BookContext) -> None:
    """切书时从 BookContext 更新书相关路径。"""
    global DATA_DIR, CHAPTERS_DIR, BACKUPS_DIR, CONTEXT_LOG_JSONL
    global SESSION_FILE, SESSION_MD_FILE, FREE_CHAT_FILE
    global WORLD_FILE, STYLE_FILE, CHARACTERS_FILE, CHAR_CURRENT_FILE
    global CHAR_STATIC_FILE, CHAR_DYNAMIC_FILE
    global SUMMARIES_FILE, SUMMARIES_ARCHIVE_FILE, SUMMARIES_RECENT_FILE
    global PLOT_THREADS_FILE, PLOT_THREADS_LOCKED_FILE, PLOT_THREADS_ACTIVE_FILE
    global OUTLINE_LATEST_FILE, CHAT_PROMPTS_FILE, ARCHIVE_FILE, CODEX_FILES
    global ND_DATA_DIR, ND_BACKUPS_DIR, ND_PLAN_FILE, ND_PROJECT_FILE
    global ND_CODEX_DIR, ND_CODEX_ACTIVE_FILE

    _ensure_fixed_paths()

    DATA_DIR = ctx.data_dir
    CHAPTERS_DIR = ctx.chapters_dir
    BACKUPS_DIR = ctx.backups_dir
    CONTEXT_LOG_JSONL = ctx.context_log_jsonl
    SESSION_FILE = ctx.session_file
    SESSION_MD_FILE = ctx.session_md_file
    FREE_CHAT_FILE = ctx.free_chat_file
    WORLD_FILE = ctx.world_file
    STYLE_FILE = ctx.style_file
    CHARACTERS_FILE = ctx.characters_file
    CHAR_CURRENT_FILE = ctx.char_current_file
    CHAR_STATIC_FILE = ctx.char_static_file
    CHAR_DYNAMIC_FILE = ctx.char_dynamic_file
    SUMMARIES_FILE = ctx.summaries_file
    SUMMARIES_ARCHIVE_FILE = ctx.summaries_archive_file
    SUMMARIES_RECENT_FILE = ctx.summaries_recent_file
    PLOT_THREADS_FILE = ctx.plot_threads_file
    PLOT_THREADS_LOCKED_FILE = ctx.plot_threads_locked_file
    PLOT_THREADS_ACTIVE_FILE = ctx.plot_threads_active_file
    OUTLINE_LATEST_FILE = ctx.outline_latest_file
    CHAT_PROMPTS_FILE = ctx.chat_prompts_file
    ARCHIVE_FILE = ctx.archive_file
    CODEX_FILES = ctx.codex_files_map()

    ND_DATA_DIR = ctx.data_dir
    ND_BACKUPS_DIR = ctx.backups_dir
    ND_PLAN_FILE = ctx.plan_file
    ND_PROJECT_FILE = ctx.project_file
    ND_CODEX_DIR = ctx.codex_dir
    ND_CODEX_ACTIVE_FILE = ctx.codex_active_file


def mirror_to_main() -> None:
    """写回 main.* + novel_data.*（测试 patch main.CHAPTERS_DIR 仍有效）。"""
    import main
    import novel_data

    main.DATA_DIR = DATA_DIR
    main.CHAPTERS_DIR = CHAPTERS_DIR
    main.BACKUPS_DIR = BACKUPS_DIR
    main.CONTEXT_LOG_JSONL = CONTEXT_LOG_JSONL
    main.SESSION_FILE = SESSION_FILE
    main.SESSION_MD_FILE = SESSION_MD_FILE
    main.FREE_CHAT_FILE = FREE_CHAT_FILE
    main.WORLD_FILE = WORLD_FILE
    main.STYLE_FILE = STYLE_FILE
    main.CHARACTERS_FILE = CHARACTERS_FILE
    main.CHAR_CURRENT_FILE = CHAR_CURRENT_FILE
    main.CHAR_STATIC_FILE = CHAR_STATIC_FILE
    main.CHAR_DYNAMIC_FILE = CHAR_DYNAMIC_FILE
    main.SUMMARIES_FILE = SUMMARIES_FILE
    main.SUMMARIES_ARCHIVE_FILE = SUMMARIES_ARCHIVE_FILE
    main.SUMMARIES_RECENT_FILE = SUMMARIES_RECENT_FILE
    main.PLOT_THREADS_FILE = PLOT_THREADS_FILE
    main.PLOT_THREADS_LOCKED_FILE = PLOT_THREADS_LOCKED_FILE
    main.PLOT_THREADS_ACTIVE_FILE = PLOT_THREADS_ACTIVE_FILE
    main.OUTLINE_LATEST_FILE = OUTLINE_LATEST_FILE
    main.CHAT_PROMPTS_FILE = CHAT_PROMPTS_FILE
    main.ARCHIVE_FILE = ARCHIVE_FILE
    main.CODEX_FILES = CODEX_FILES

    novel_data.DATA_DIR = ND_DATA_DIR
    novel_data.BACKUPS_DIR = ND_BACKUPS_DIR
    novel_data.PLAN_FILE = ND_PLAN_FILE
    novel_data.PROJECT_FILE = ND_PROJECT_FILE
    novel_data.CODEX_DIR = ND_CODEX_DIR
    novel_data.CODEX_ACTIVE_FILE = ND_CODEX_ACTIVE_FILE
