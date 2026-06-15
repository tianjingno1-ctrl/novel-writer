"""路径 source of truth（P4-B）。切书经 sync_from_context；mirror_to_main 同步 main 兼容层。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.data.book_context import BookContext

_ROOT = Path(__file__).resolve().parent.parent

# 全局固定（切书不变）
BASE_DIR: Path | None = None
COST_LOG: Path | None = None
COST_LOG_JSONL: Path | None = None

# 书相关路径（切书更新）
DATA_DIR: Path | None = None
CHAPTERS_DIR: Path | None = None
BACKUPS_DIR: Path | None = None
CONTEXT_LOG_JSONL: Path | None = None
SESSION_FILE: Path | None = None
SESSION_MD_FILE: Path | None = None
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

_initialized = False


def init_default_paths() -> None:
    """从项目根目录初始化默认路径（不依赖 main）。"""
    global BASE_DIR, COST_LOG, COST_LOG_JSONL
    global DATA_DIR, CHAPTERS_DIR, BACKUPS_DIR, CONTEXT_LOG_JSONL
    global SESSION_FILE, SESSION_MD_FILE
    global WORLD_FILE, STYLE_FILE, CHARACTERS_FILE, CHAR_CURRENT_FILE
    global CHAR_STATIC_FILE, CHAR_DYNAMIC_FILE
    global SUMMARIES_FILE, SUMMARIES_ARCHIVE_FILE, SUMMARIES_RECENT_FILE
    global PLOT_THREADS_FILE, PLOT_THREADS_LOCKED_FILE, PLOT_THREADS_ACTIVE_FILE
    global OUTLINE_LATEST_FILE, CHAT_PROMPTS_FILE, ARCHIVE_FILE, CODEX_FILES
    global ND_DATA_DIR, ND_BACKUPS_DIR, ND_PLAN_FILE, ND_PROJECT_FILE
    global ND_CODEX_DIR, ND_CODEX_ACTIVE_FILE
    global _initialized

    BASE_DIR = _ROOT
    DATA_DIR = BASE_DIR / "data"
    CHAPTERS_DIR = DATA_DIR / "chapters"
    BACKUPS_DIR = DATA_DIR / "backups"
    COST_LOG = BASE_DIR / "cost_log.txt"
    COST_LOG_JSONL = BASE_DIR / "cost_log.jsonl"
    CONTEXT_LOG_JSONL = DATA_DIR / "context_log.jsonl"
    SESSION_FILE = DATA_DIR / "session_autosave.json"
    SESSION_MD_FILE = DATA_DIR / "session_autosave.md"
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

    ND_DATA_DIR = DATA_DIR
    ND_BACKUPS_DIR = BACKUPS_DIR
    ND_PLAN_FILE = DATA_DIR / "plan.json"
    ND_PROJECT_FILE = DATA_DIR / "project.json"
    ND_CODEX_DIR = DATA_DIR / "codex" / "entries"
    ND_CODEX_ACTIVE_FILE = DATA_DIR / "codex" / "active.json"
    _initialized = True


def _ensure_initialized() -> None:
    if not _initialized:
        init_default_paths()


def resolved(name: str) -> Path:
    _ensure_initialized()
    # 测试 patch main.* 时优先读 main（过渡期兼容）
    try:
        import main

        mval = getattr(main, name, None)
        if isinstance(mval, Path):
            return mval
    except ImportError:
        pass
    val = globals().get(name)
    if val is None:
        raise KeyError(f"未知路径名: {name}")
    return val  # type: ignore[return-value]


def resolved_codex_files() -> dict[str, Path]:
    _ensure_initialized()
    assert CODEX_FILES is not None
    return CODEX_FILES


def init_defaults() -> None:
    """兼容旧名：初始化默认路径。"""
    init_default_paths()


def sync_from_context(ctx: BookContext) -> None:
    """切书时从 BookContext 更新书相关路径。"""
    global DATA_DIR, CHAPTERS_DIR, BACKUPS_DIR, CONTEXT_LOG_JSONL
    global SESSION_FILE, SESSION_MD_FILE
    global WORLD_FILE, STYLE_FILE, CHARACTERS_FILE, CHAR_CURRENT_FILE
    global CHAR_STATIC_FILE, CHAR_DYNAMIC_FILE
    global SUMMARIES_FILE, SUMMARIES_ARCHIVE_FILE, SUMMARIES_RECENT_FILE
    global PLOT_THREADS_FILE, PLOT_THREADS_LOCKED_FILE, PLOT_THREADS_ACTIVE_FILE
    global OUTLINE_LATEST_FILE, CHAT_PROMPTS_FILE, ARCHIVE_FILE, CODEX_FILES
    global ND_DATA_DIR, ND_BACKUPS_DIR, ND_PLAN_FILE, ND_PROJECT_FILE
    global ND_CODEX_DIR, ND_CODEX_ACTIVE_FILE

    _ensure_initialized()

    DATA_DIR = ctx.data_dir
    CHAPTERS_DIR = ctx.chapters_dir
    BACKUPS_DIR = ctx.backups_dir
    CONTEXT_LOG_JSONL = ctx.context_log_jsonl
    SESSION_FILE = ctx.session_file
    SESSION_MD_FILE = ctx.session_md_file
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
    from core.data import novel_data

    _ensure_initialized()
    main.BASE_DIR = BASE_DIR
    main.DATA_DIR = DATA_DIR
    main.CHAPTERS_DIR = CHAPTERS_DIR
    main.BACKUPS_DIR = BACKUPS_DIR
    main.COST_LOG = COST_LOG
    main.COST_LOG_JSONL = COST_LOG_JSONL
    main.CONTEXT_LOG_JSONL = CONTEXT_LOG_JSONL
    main.SESSION_FILE = SESSION_FILE
    main.SESSION_MD_FILE = SESSION_MD_FILE
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


# 模块加载时初始化
init_default_paths()
