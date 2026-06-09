"""基础文件 IO：原子写盘 + 书籍 read/write/archive 双写。"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from core.data import change_history

BACKUP_KEEP = 10


def backup_file(path: Path, backups_dir: Path | None = None) -> None:
    if backups_dir is None:
        from app import paths as _paths

        backups_dir = _paths.resolved("BACKUPS_DIR")
    if not path.exists() or path.stat().st_size <= 0:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backups_dir.mkdir(parents=True, exist_ok=True)
    dest = backups_dir / f"{path.stem}_{ts}{path.suffix}"
    shutil.copy2(path, dest)
    old = sorted(backups_dir.glob(f"{path.stem}_*{path.suffix}"))
    for f in old[:-BACKUP_KEEP]:
        f.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """先写临时文件再原子替换，避免写入中途崩溃导致文件损坏。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    tmp.replace(path)


def _archive_section_for_path(path: Path) -> str | None:
    from core.data import book_context

    return book_context.section_key_for_filename(path.name)


def _sync_archive_section_from_file(path: Path) -> None:
    """双写：将独立 md 全文同步到 book_archive.md 对应小节。"""
    from app import paths as _paths

    section = _archive_section_for_path(path)
    archive_file = _paths.resolved("ARCHIVE_FILE")
    if not section or not archive_file.exists():
        return
    if not path.exists():
        return
    try:
        from core.data import book_context

        book_id = book_context.get_context().book_id
        body = path.read_text(encoding="utf-8")
        book_context.update_archive_section(book_id, section, body)
    except RuntimeError:
        return


def read_text(path: Path) -> str:
    from app import paths as _paths

    if path.exists():
        return path.read_text(encoding="utf-8")
    section = _archive_section_for_path(path)
    archive_file = _paths.resolved("ARCHIVE_FILE")
    if section and archive_file.exists():
        try:
            from core.data import book_context

            book_id = book_context.get_context().book_id
            return book_context.get_archive_section(book_id, section)
        except RuntimeError:
            pass
    return ""


def _session_chapter_num() -> int:
    from app import writing_session as ws

    return ws._session_chapter_num()


def write_text(
    path: Path,
    content: str,
    *,
    append: bool = False,
    history_source: str = "write",
    chapter_num: int | None = None,
) -> bool:
    """写入文件。返回是否实际变更磁盘内容。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    key = change_history.resolve_key(path)
    if key:
        entry_id = change_history.save_with_history(
            path,
            content,
            append=append,
            source=history_source,
            chapter_num=chapter_num if chapter_num is not None else _session_chapter_num(),
            file_key=key,
        )
        if entry_id is not None:
            _sync_archive_section_from_file(path)
        return entry_id is not None
    if append:
        existing = read_text(path)
        if not content:
            return False
        backup_file(path)
        atomic_write_text(path, f"{existing}{content}")
        _sync_archive_section_from_file(path)
        return True
    if read_text(path) == content:
        return False
    backup_file(path)
    atomic_write_text(path, content)
    _sync_archive_section_from_file(path)
    return True
