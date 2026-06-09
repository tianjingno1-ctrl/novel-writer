"""多书管理：library/ 书库 + 当前书路径上下文。"""

from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import file_utils

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
LIBRARY_DIR = _BASE / "library"
BOOKS_DIR = LIBRARY_DIR / "books"
INDEX_FILE = LIBRARY_DIR / "index.json"
RUNTIME_FILE = LIBRARY_DIR / "runtime.json"
LEGACY_DATA_DIR = _BASE / "data"

BOOK_TYPES = frozenset({"short", "world", "novel"})

# 散 md 文件名 → book_archive.md 内 ### 小节标题
ARCHIVE_SECTION_BY_FILENAME: dict[str, str] = {
    "world.md": "世界观",
    "style.md": "文风锚点",
    "characters.md": "人物总表",
    "char_static.md": "人物锚点（静态）",
    "char_dynamic.md": "人物动态",
    "summaries_recent.md": "近期概述",
    "summaries_archive.md": "概述归档",
    "plot_threads_locked.md": "已锁定细节",
    "plot_threads_active.md": "活跃线索",
}

ARCHIVE_SECTION_ORDER: tuple[str, ...] = tuple(ARCHIVE_SECTION_BY_FILENAME.values())


def _section_header_pattern(section_key: str) -> re.Pattern[str]:
    return re.compile(rf"^###\s+{re.escape(section_key)}\s*\n", re.MULTILINE)


def _section_body_bounds(text: str, section_key: str) -> tuple[int, int] | None:
    """返回 section 正文在 text 中的 [start, end)，不含 ### 标题行。"""
    markers: list[tuple[int, str, int]] = []
    for key in ARCHIVE_SECTION_ORDER:
        pat = _section_header_pattern(key)
        for m in pat.finditer(text):
            markers.append((m.start(), key, m.end()))
    markers.sort(key=lambda x: x[0])
    for i, (_pos, key, body_start) in enumerate(markers):
        if key != section_key:
            continue
        if i + 1 < len(markers):
            body_end = markers[i + 1][0]
        else:
            body_end = len(text)
        return body_start, body_end
    return None


def archive_path_for_book(book_id: str) -> Path:
    return BOOKS_DIR / book_id / "book_archive.md"


def get_archive_section(book_id: str, section_key: str) -> str:
    """从 book_archive.md 提取 ### section_key 下正文（含内部 ## 标题）。"""
    path = archive_path_for_book(book_id)
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    bounds = _section_body_bounds(text, section_key)
    if not bounds:
        return ""
    start, end = bounds
    return text[start:end].strip("\n")


def update_archive_section(book_id: str, section_key: str, new_content: str) -> bool:
    """替换 book_archive.md 中指定 ### 小节正文。"""
    path = archive_path_for_book(book_id)
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    bounds = _section_body_bounds(text, section_key)
    if not bounds:
        return False
    start, end = bounds
    body = new_content.rstrip("\n")
    new_text = text[:start] + body + ("\n" if body else "\n") + text[end:]
    file_utils.atomic_write_text(
        path,
        new_text if new_text.endswith("\n") else new_text + "\n",
    )
    return True


def section_key_for_filename(filename: str) -> str | None:
    return ARCHIVE_SECTION_BY_FILENAME.get(filename)

DEFAULT_PROJECT = {
    "title": "未命名小说",
    "world_label": "",
    "tagline": "",
    "notes": "",
    "type": "novel",
    "platform": "tomato",
    "created_at": "",
    "updated_at": "",
}


class BookContext:
    """当前激活书籍的路径集合。"""

    def __init__(self, book_id: str, book_dir: Path) -> None:
        self.book_id = book_id
        self.book_dir = book_dir
        self.data_dir = book_dir
        self.chapters_dir = book_dir / "chapters"
        self.backups_dir = book_dir / "backups"
        self.context_log_jsonl = book_dir / "context_log.jsonl"
        self.session_file = book_dir / "session_autosave.json"
        self.session_md_file = book_dir / "session_autosave.md"
        self.free_chat_file = book_dir / "free_chat.json"
        self.world_file = book_dir / "world.md"
        self.style_file = book_dir / "style.md"
        self.characters_file = book_dir / "characters.md"
        self.char_current_file = book_dir / "char_current.md"
        self.char_static_file = book_dir / "char_static.md"
        self.char_dynamic_file = book_dir / "char_dynamic.md"
        self.summaries_file = book_dir / "summaries.md"
        self.summaries_archive_file = book_dir / "summaries_archive.md"
        self.summaries_recent_file = book_dir / "summaries_recent.md"
        self.plot_threads_file = book_dir / "plot_threads.md"
        self.plot_threads_locked_file = book_dir / "plot_threads_locked.md"
        self.plot_threads_active_file = book_dir / "plot_threads_active.md"
        self.outline_latest_file = book_dir / "outline_latest.md"
        self.chat_prompts_file = book_dir / "chat_prompts.json"
        self.plan_file = book_dir / "plan.json"
        self.project_file = book_dir / "project.json"
        self.codex_dir = book_dir / "codex" / "entries"
        self.codex_active_file = book_dir / "codex" / "active.json"
        self.batch_jobs_dir = book_dir / "batch_jobs"
        self.quality_log_jsonl = book_dir / "quality_log.jsonl"
        self.archive_file = book_dir / "book_archive.md"

    def codex_files_map(self) -> dict[str, Path]:
        return {
            "world": self.world_file,
            "style": self.style_file,
            "characters": self.characters_file,
            "char_static": self.char_static_file,
            "char_dynamic": self.char_dynamic_file,
            "char_current": self.char_current_file,
            "summaries_archive": self.summaries_archive_file,
            "summaries_recent": self.summaries_recent_file,
            "summaries": self.summaries_file,
            "plot_threads_locked": self.plot_threads_locked_file,
            "plot_threads_active": self.plot_threads_active_file,
            "plot_threads": self.plot_threads_file,
        }


_context: BookContext | None = None


def get_context() -> BookContext:
    if _context is None:
        raise RuntimeError("书库尚未初始化，请先调用 init_library()")
    return _context


def _slug_id(title: str) -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", (title or "").strip().lower())
    base = base.strip("-")[:32] or "book"
    return f"{base}-{uuid.uuid4().hex[:8]}"


def _load_index() -> dict:
    if not INDEX_FILE.exists():
        return {"version": 1, "active_book_id": "", "books": []}
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "active_book_id": "", "books": []}


def _save_index(data: dict) -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    file_utils.atomic_write_text(
        INDEX_FILE,
        json.dumps(data, ensure_ascii=False, indent=2),
    )


def _book_entry(book_id: str, book_dir: Path) -> dict:
    project = DEFAULT_PROJECT.copy()
    if (book_dir / "project.json").exists():
        try:
            raw = json.loads((book_dir / "project.json").read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                project.update(raw)
        except (json.JSONDecodeError, OSError):
            pass
    book_type = project.get("type") or "novel"
    if book_type not in BOOK_TYPES:
        book_type = "novel"
    mtime = book_dir.stat().st_mtime if book_dir.exists() else 0
    platform = project.get("platform") or "tomato"
    return {
        "id": book_id,
        "title": project.get("title") or "未命名小说",
        "world_label": project.get("world_label") or "",
        "type": book_type,
        "platform": platform,
        "tagline": project.get("tagline") or "",
        "updated_at": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
        "created_at": project.get("created_at") or "",
    }


def _migrate_legacy_data() -> str:
    """将旧版 data/ 迁入 library/books/default/，runtime.json 提到 library/。"""
    default_id = "default"
    target = BOOKS_DIR / default_id
    if target.exists() and any(target.iterdir()):
        return default_id

    LEGACY_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not any(LEGACY_DATA_DIR.iterdir()):
        target.mkdir(parents=True, exist_ok=True)
        return default_id

    target.mkdir(parents=True, exist_ok=True)
    legacy_runtime = LEGACY_DATA_DIR / "runtime.json"
    if legacy_runtime.exists() and not RUNTIME_FILE.exists():
        shutil.copy2(legacy_runtime, RUNTIME_FILE)

    for item in LEGACY_DATA_DIR.iterdir():
        if item.name == "runtime.json":
            continue
        dest = target / item.name
        if dest.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    return default_id


def _ensure_default_book() -> str:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    index = _load_index()
    if index.get("books"):
        active = index.get("active_book_id") or index["books"][0]["id"]
        return active

    book_id = _migrate_legacy_data()
    book_dir = BOOKS_DIR / book_id
    book_dir.mkdir(parents=True, exist_ok=True)
    entry = _book_entry(book_id, book_dir)
    if not entry.get("created_at"):
        entry["created_at"] = datetime.now().isoformat(timespec="seconds")
    index = {
        "version": 1,
        "active_book_id": book_id,
        "books": [entry],
        "migrated_from_data": _legacy_data_has_book_files(),
    }
    _save_index(index)
    return book_id


def _set_context(book_id: str) -> BookContext:
    global _context
    book_dir = BOOKS_DIR / book_id
    if not book_dir.is_dir():
        raise FileNotFoundError(f"书籍不存在: {book_id}")
    _context = BookContext(book_id, book_dir)
    return _context


def apply_paths_to_modules() -> None:
    """将当前 BookContext 路径同步到 app.paths / main / novel_data。"""
    from app import paths as book_paths

    ctx = get_context()
    book_paths.sync_from_context(ctx)
    book_paths.mirror_to_main()

    import core.context as writing_context
    import main

    writing_context.bind(
        writing_context.BookPaths.from_book_context(ctx),
        read_text=main.read_text,
    )


def reset_session_state() -> None:
    """切换书籍时清空进程内写作/对话状态。"""
    from app_state import state

    state.conversation_history.clear()
    state.free_chat_history.clear()
    state.free_chat_threads.clear()
    state.free_chat_active_thread_id = ""
    state.session_includes_chapter = False
    state.write_chapter_num = 0
    state.last_injected_chapter_num = 0
    state.appended_indices.clear()
    state.last_append_undo = None
    state.batch_job_running = False
    state.batch_job_id = ""
    state.last_context_debug.clear()


def reinit_book_services() -> None:
    """切换书后重新绑定 change_history / quality_log 等。"""
    import change_history
    import main
    import quality_log

    ctx = get_context()
    main._register_change_history()
    quality_log.init_quality_log(ctx.data_dir)


def _migrate_runtime_if_needed() -> None:
    if RUNTIME_FILE.exists():
        return
    legacy = LEGACY_DATA_DIR / "runtime.json"
    if legacy.exists():
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, RUNTIME_FILE)


def _legacy_data_has_book_files() -> bool:
    """legacy data/ 是否仍含书籍内容（非空目录即视为在用）。"""
    if not LEGACY_DATA_DIR.is_dir():
        return False
    markers = (
        LEGACY_DATA_DIR / "world.md",
        LEGACY_DATA_DIR / "plan.json",
        LEGACY_DATA_DIR / "chapters",
    )
    for p in markers:
        if p.is_file() and p.stat().st_size > 0:
            return True
        if p.is_dir() and any(p.iterdir()):
            return True
    return False


def warn_if_dual_data_roots(*, active_book_id: str | None = None) -> None:
    """若 legacy data/ 与 library/ 同时有内容，打印警告（数据根应逐步统一到 library）。"""
    legacy_active = _legacy_data_has_book_files()
    library_active = INDEX_FILE.is_file() and BOOKS_DIR.is_dir() and any(BOOKS_DIR.iterdir())
    if not (legacy_active and library_active):
        return
    try:
        ctx = get_context()
        read_root = str(ctx.data_dir)
        active = active_book_id or ctx.book_id
    except RuntimeError:
        read_root = "(书库未初始化)"
        active = active_book_id or "?"
    logger.warning(
        "检测到 data/ 与 library/ 同时存在书籍数据。"
        " 当前读写目录: %s · active_book=%s · legacy=%s · library=%s",
        read_root,
        active,
        LEGACY_DATA_DIR,
        LIBRARY_DIR,
    )


def init_library(*, book_id: str | None = None) -> BookContext:
    """启动时初始化书库并激活一本书。"""
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_runtime_if_needed()
    active = book_id or _ensure_default_book()
    ctx = _set_context(active)
    apply_paths_to_modules()
    warn_if_dual_data_roots(active_book_id=active)
    return ctx


def list_books() -> dict:
    index = _load_index()
    books: list[dict] = []
    for meta in index.get("books") or []:
        bid = meta.get("id")
        if not bid:
            continue
        book_dir = BOOKS_DIR / bid
        if book_dir.is_dir():
            books.append(_book_entry(bid, book_dir))
    active = index.get("active_book_id") or (books[0]["id"] if books else "")
    return {
        "ok": True,
        "active_book_id": active,
        "books": books,
        "library_dir": str(LIBRARY_DIR),
    }


def get_active_book_meta() -> dict:
    ctx = get_context()
    entry = _book_entry(ctx.book_id, ctx.book_dir)
    return {"ok": True, "book": entry, "book_id": ctx.book_id}


def _read_project_type(project_file: Path) -> str:
    project = DEFAULT_PROJECT.copy()
    if project_file.exists():
        try:
            raw = json.loads(project_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                project.update(raw)
        except (json.JSONDecodeError, OSError):
            pass
    t = project.get("type") or "novel"
    return t if t in BOOK_TYPES else "novel"


def get_book_type(book_id: str | None = None) -> str:
    if book_id:
        return _read_project_type(BOOKS_DIR / book_id / "project.json")
    try:
        return _read_project_type(get_context().project_file)
    except RuntimeError:
        import novel_data

        return _read_project_type(novel_data.PROJECT_FILE)


def is_short_book(book_id: str | None = None) -> bool:
    return get_book_type(book_id) == "short"


def switch_book(book_id: str) -> dict:
    index = _load_index()
    known = {b.get("id") for b in index.get("books") or []}
    if book_id not in known or not (BOOKS_DIR / book_id).is_dir():
        return {"ok": False, "error": f"书籍不存在: {book_id}"}

    reset_session_state()
    _set_context(book_id)
    apply_paths_to_modules()
    reinit_book_services()

    index["active_book_id"] = book_id
    _save_index(index)

    import main
    from app.free_chat import load_free_chat

    load_free_chat()
    return {
        "ok": True,
        "book_id": book_id,
        "book": _book_entry(book_id, BOOKS_DIR / book_id),
    }


def create_book(
    *,
    title: str = "未命名小说",
    book_type: str = "novel",
    platform: str = "tomato",
    world_label: str = "",
    tagline: str = "",
) -> dict:
    if book_type not in BOOK_TYPES:
        return {"ok": False, "error": f"type 必须是 {', '.join(sorted(BOOK_TYPES))}"}
    import review_prompts

    platform = review_prompts.normalize_platform(platform)

    book_id = _slug_id(title)
    book_dir = BOOKS_DIR / book_id
    if book_dir.exists():
        return {"ok": False, "error": "书籍 ID 冲突，请重试"}

    book_dir.mkdir(parents=True)
    now = datetime.now().isoformat(timespec="seconds")
    project = {
        **DEFAULT_PROJECT,
        "title": title.strip() or "未命名小说",
        "world_label": world_label.strip(),
        "tagline": tagline.strip(),
        "type": book_type,
        "platform": platform,
        "created_at": now,
        "updated_at": now,
    }
    file_utils.atomic_write_text(
        book_dir / "project.json",
        json.dumps(project, ensure_ascii=False, indent=2),
    )

    index = _load_index()
    entry = _book_entry(book_id, book_dir)
    books = list(index.get("books") or [])
    books.append(entry)
    index["books"] = books
    index["active_book_id"] = book_id
    _save_index(index)

    reset_session_state()
    _set_context(book_id)
    apply_paths_to_modules()

    import main
    from app.free_chat import load_free_chat

    main.init_data_dirs()
    reinit_book_services()
    load_free_chat()

    return {"ok": True, "book_id": book_id, "book": entry}
