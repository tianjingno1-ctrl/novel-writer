"""多书管理：library/ 书库 + 当前书路径上下文。"""

from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from infra import file_utils

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parents[2]
LIBRARY_DIR = _BASE / "library"
BOOKS_DIR = LIBRARY_DIR / "books"
TRASH_DIR = LIBRARY_DIR / "trash"
INDEX_FILE = LIBRARY_DIR / "index.json"
TRASH_INDEX_FILE = TRASH_DIR / "index.json"
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
        self.quality_log_jsonl = book_dir / "quality_log.jsonl"
        self.archive_file = book_dir / "book_archive.md"
        self.prompt_overrides_file = book_dir / "prompt_overrides.yaml"
        self.taste_file = book_dir / "taste.json"

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
    from core.bookshelf_stats import bookshelf_stats

    stats = bookshelf_stats(book_dir)
    plan_path = book_dir / "plan.json"
    plan_title = ""
    if plan_path.is_file():
        try:
            plan_raw = json.loads(plan_path.read_text(encoding="utf-8"))
            if isinstance(plan_raw, dict):
                meta = plan_raw.get("meta")
                if isinstance(meta, dict):
                    plan_title = str(meta.get("title") or "").strip()
        except (json.JSONDecodeError, OSError):
            pass
    project_title = str(project.get("title") or "").strip() or "未命名小说"
    display_title = project_title
    if plan_title and project_title in ("新书", "未命名小说"):
        display_title = plan_title

    return {
        "id": book_id,
        "title": display_title,
        "world_label": project.get("world_label") or "",
        "type": book_type,
        "platform": platform,
        "tagline": project.get("tagline") or "",
        "updated_at": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
        "created_at": project.get("created_at") or "",
        **stats,
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
    from infra import file_utils as bio

    writing_context.bind(
        writing_context.BookPaths.from_book_context(ctx),
        read_text=bio.read_text,
    )


def reset_session_state() -> None:
    """切换书籍时清空进程内写作/对话状态（无快照时使用）。"""
    from infra.session_book import clear_writing_state

    clear_writing_state()


def _active_book_id() -> str | None:
    try:
        return get_context().book_id
    except RuntimeError:
        return _context.book_id if _context else None


def reinit_book_services() -> None:
    """切换书后重新绑定 change_history / quality_log 等。"""
    from core.data import change_history
    from infra.logs import quality as quality_log
    from infra.billing import _register_change_history

    ctx = get_context()
    _register_change_history()
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
        from core.data import novel_data

        return _read_project_type(novel_data.PROJECT_FILE)


def is_short_book(book_id: str | None = None) -> bool:
    return get_book_type(book_id) == "short"


def switch_book(book_id: str) -> dict:
    index = _load_index()
    known = {b.get("id") for b in index.get("books") or []}
    if book_id not in known or not (BOOKS_DIR / book_id).is_dir():
        return {"ok": False, "error": f"书籍不存在: {book_id}"}

    from infra.session_book import activate_book_session, park_book_session

    old_id = _active_book_id()
    if old_id and old_id != book_id:
        park_book_session(old_id)
    _set_context(book_id)
    apply_paths_to_modules()
    activate_book_session(book_id)
    reinit_book_services()
    from core import plan_product

    plan_product.persist_strip_legacy_meta_if_needed()

    index["active_book_id"] = book_id
    _save_index(index)

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

    from infra.session_book import activate_book_session, park_book_session

    old_id = _active_book_id()
    if old_id and old_id != book_id:
        park_book_session(old_id)
    _set_context(book_id)
    apply_paths_to_modules()
    activate_book_session(book_id)

    from app.bootstrap import init_data_dirs

    init_data_dirs()
    reinit_book_services()

    return {"ok": True, "book_id": book_id, "book": entry}


def update_book(
    book_id: str,
    *,
    title: str | None = None,
    book_type: str | None = None,
    platform: str | None = None,
    world_label: str | None = None,
    tagline: str | None = None,
) -> dict:
    import review_prompts

    book_dir = BOOKS_DIR / book_id
    if not book_dir.is_dir():
        return {"ok": False, "error": "书籍不存在"}

    from core import project_lifecycle

    doc = project_lifecycle.load_project(book_dir)
    if not doc:
        doc = dict(DEFAULT_PROJECT)

    if title is not None:
        doc["title"] = (title or "").strip() or "未命名小说"
    if book_type is not None:
        bt = (book_type or "novel").strip()
        if bt not in BOOK_TYPES:
            return {"ok": False, "error": f"type 必须是 {', '.join(sorted(BOOK_TYPES))}"}
        doc["type"] = bt
    if platform is not None:
        doc["platform"] = review_prompts.normalize_platform(platform)
    if world_label is not None:
        doc["world_label"] = (world_label or "").strip()
    if tagline is not None:
        doc["tagline"] = (tagline or "").strip()

    project_lifecycle.save_project(book_dir, doc)

    index = _load_index()
    books = list(index.get("books") or [])
    for i, meta in enumerate(books):
        if meta.get("id") == book_id:
            books[i] = _book_entry(book_id, book_dir)
            break
    index["books"] = books
    _save_index(index)

    entry = _book_entry(book_id, book_dir)
    return {"ok": True, "book_id": book_id, "book": entry}


def _load_trash_index() -> dict:
    if not TRASH_INDEX_FILE.exists():
        return {"version": 1, "items": []}
    try:
        raw = json.loads(TRASH_INDEX_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "items": []}
    return raw if isinstance(raw, dict) else {"version": 1, "items": []}


def _save_trash_index(data: dict) -> None:
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    file_utils.atomic_write_text(
        TRASH_INDEX_FILE,
        json.dumps(data, ensure_ascii=False, indent=2),
    )


def _sync_trash_index_items() -> list[dict]:
    """与 trash 目录对齐索引，返回仍存在的条目。"""
    data = _load_trash_index()
    kept: list[dict] = []
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        bid = str(item.get("id") or "").strip()
        if bid and (TRASH_DIR / bid).is_dir():
            kept.append(item)
    if kept != list(data.get("items") or []):
        data["items"] = kept
        _save_trash_index(data)
    return kept


def _activate_book_after_switch(book_id: str) -> None:
    from infra.session_book import activate_book_session

    _set_context(book_id)
    apply_paths_to_modules()
    activate_book_session(book_id)
    reinit_book_services()
    from core import plan_product

    plan_product.persist_strip_legacy_meta_if_needed()


def _clear_active_context() -> None:
    global _context
    from infra.session_book import clear_writing_state

    _context = None
    clear_writing_state()


def list_trash() -> dict:
    items: list[dict] = []
    for meta in _sync_trash_index_items():
        bid = str(meta.get("id") or "").strip()
        book_dir = TRASH_DIR / bid
        if not book_dir.is_dir():
            continue
        entry = _book_entry(bid, book_dir)
        entry["trashed_at"] = meta.get("trashed_at") or ""
        items.append(entry)
    items.sort(key=lambda b: str(b.get("trashed_at") or ""), reverse=True)
    return {"ok": True, "books": items, "trash_dir": str(TRASH_DIR)}


def trash_book(book_id: str) -> dict:
    """移入垃圾站（软删除）：目录迁至 library/trash/{id}/。"""
    result = trash_books([book_id])
    if not result.get("ok"):
        err = result.get("error")
        if result.get("failed"):
            err = result["failed"][0].get("error") or err
        return {"ok": False, "error": err or "移入垃圾站失败"}
    trashed = result.get("trashed") or []
    if not trashed:
        return {"ok": False, "error": "移入垃圾站失败"}
    one = trashed[0]
    return {
        "ok": True,
        "book_id": one.get("book_id"),
        "active_book_id": result.get("active_book_id"),
        "context_refreshed": result.get("context_refreshed"),
        "book": one.get("book"),
    }


def trash_books(book_ids: list[str]) -> dict:
    """批量移入垃圾站；一次更新 index 与 active 书。"""
    from infra.session_book import drop_book_session, park_book_session

    ids: list[str] = []
    seen: set[str] = set()
    for raw in book_ids:
        bid = (raw or "").strip()
        if not bid or bid in seen:
            continue
        seen.add(bid)
        ids.append(bid)

    if not ids:
        return {"ok": False, "error": "缺少 book_ids"}

    index = _load_index()
    books = list(index.get("books") or [])
    active = str(index.get("active_book_id") or "")
    trash_active = active in ids

    if trash_active:
        park_book_session(active)

    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    trash_data = _load_trash_index()
    trash_items = list(trash_data.get("items") or [])

    trashed: list[dict] = []
    failed: list[dict] = []
    trashed_ids: set[str] = set()

    for book_id in ids:
        book_dir = BOOKS_DIR / book_id
        if not book_dir.is_dir():
            failed.append({"book_id": book_id, "error": "书籍不存在"})
            continue
        if not any(b.get("id") == book_id for b in books):
            failed.append({"book_id": book_id, "error": "书籍不在书架"})
            continue
        dest = TRASH_DIR / book_id
        if dest.exists():
            failed.append({"book_id": book_id, "error": "该书籍已在垃圾站"})
            continue

        entry = _book_entry(book_id, book_dir)
        trashed_at = datetime.now().isoformat(timespec="seconds")
        try:
            shutil.move(str(book_dir), str(dest))
        except OSError as exc:
            failed.append({"book_id": book_id, "error": str(exc)})
            continue

        books = [b for b in books if b.get("id") != book_id]
        trash_items = [i for i in trash_items if i.get("id") != book_id]
        trash_items.append({"id": book_id, "trashed_at": trashed_at})
        trashed_ids.add(book_id)
        drop_book_session(book_id)
        trashed.append(
            {
                "book_id": book_id,
                "trashed_at": trashed_at,
                "book": {**entry, "trashed_at": trashed_at},
            }
        )

    new_active = active if active and active not in trashed_ids else ""
    if trash_active and books:
        new_active = str(books[0].get("id") or "")

    index["books"] = books
    index["active_book_id"] = new_active
    _save_index(index)

    trash_data["items"] = trash_items
    _save_trash_index(trash_data)

    context_refreshed = trash_active and bool(trashed_ids)
    if context_refreshed:
        if new_active:
            _activate_book_after_switch(new_active)
        else:
            _clear_active_context()

    ok = bool(trashed)
    return {
        "ok": ok,
        "trashed": trashed,
        "failed": failed,
        "count": len(trashed),
        "active_book_id": new_active or None,
        "context_refreshed": context_refreshed,
        "error": None if ok else "没有书籍被移入垃圾站",
    }


def restore_book(book_id: str) -> dict:
    """从垃圾站恢复到书架。"""
    book_id = (book_id or "").strip()
    trash_dir = TRASH_DIR / book_id
    if not trash_dir.is_dir():
        return {"ok": False, "error": "书籍不在垃圾站"}

    dest = BOOKS_DIR / book_id
    if dest.exists():
        return {"ok": False, "error": "书架已存在同名书籍，无法恢复"}

    shutil.move(str(trash_dir), str(dest))
    entry = _book_entry(book_id, dest)

    trash_data = _load_trash_index()
    trash_data["items"] = [
        i for i in (trash_data.get("items") or []) if i.get("id") != book_id
    ]
    _save_trash_index(trash_data)

    index = _load_index()
    books = list(index.get("books") or [])
    books.append(entry)
    index["books"] = books
    if not index.get("active_book_id"):
        index["active_book_id"] = book_id
    _save_index(index)

    return {"ok": True, "book_id": book_id, "book": entry}


def purge_book(book_id: str) -> dict:
    """从垃圾站永久删除。"""
    result = purge_books([book_id])
    if not result.get("ok"):
        err = result.get("error")
        if result.get("failed"):
            err = result["failed"][0].get("error") or err
        return {"ok": False, "error": err or "永久删除失败"}
    purged = result.get("purged") or []
    if not purged:
        return {"ok": False, "error": "永久删除失败"}
    return {"ok": True, "book_id": purged[0]}


def purge_books(book_ids: list[str]) -> dict:
    """批量从垃圾站永久删除；一次更新 trash index。"""
    from infra.session_book import drop_book_session

    ids: list[str] = []
    seen: set[str] = set()
    for raw in book_ids:
        bid = (raw or "").strip()
        if not bid or bid in seen:
            continue
        seen.add(bid)
        ids.append(bid)

    if not ids:
        return {"ok": False, "error": "缺少 book_ids"}

    trash_data = _load_trash_index()
    trash_items = list(trash_data.get("items") or [])

    purged: list[str] = []
    failed: list[dict] = []

    for book_id in ids:
        trash_dir = TRASH_DIR / book_id
        if not trash_dir.is_dir():
            failed.append({"book_id": book_id, "error": "书籍不在垃圾站"})
            continue
        shutil.rmtree(trash_dir)
        trash_items = [i for i in trash_items if i.get("id") != book_id]
        drop_book_session(book_id)
        purged.append(book_id)

    trash_data["items"] = trash_items
    _save_trash_index(trash_data)

    ok = bool(purged)
    return {
        "ok": ok,
        "purged": purged,
        "failed": failed,
        "count": len(purged),
        "error": None if ok else "没有书籍被永久删除",
    }


def purge_all_trash() -> dict:
    """清空垃圾站（永久删除全部）。"""
    from infra.session_book import drop_book_session

    removed: list[str] = []
    for meta in _sync_trash_index_items():
        bid = str(meta.get("id") or "").strip()
        trash_dir = TRASH_DIR / bid
        if trash_dir.is_dir():
            shutil.rmtree(trash_dir)
            drop_book_session(bid)
            removed.append(bid)
    _save_trash_index({"version": 1, "items": []})
    return {"ok": True, "removed": removed, "count": len(removed)}
