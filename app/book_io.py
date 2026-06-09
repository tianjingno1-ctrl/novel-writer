"""
书籍文件 IO 层（P3-5d-1）。

read_text / write_text / backup_file / archive 双写从 main 实迁。
change_history 追踪、atomic write 均在此。
"""

from __future__ import annotations

from pathlib import Path

import change_history
import file_utils
from app import paths as _paths


def _archive_section_for_path(path: Path) -> str | None:
    import book_context

    return book_context.section_key_for_filename(path.name)


def _sync_archive_section_from_file(path: Path) -> None:
    """双写：将独立 md 全文同步到 book_archive.md 对应小节。"""
    section = _archive_section_for_path(path)
    archive_file = _paths.resolved("ARCHIVE_FILE")
    if not section or not archive_file.exists():
        return
    if not path.exists():
        return
    try:
        import book_context

        book_id = book_context.get_context().book_id
        body = path.read_text(encoding="utf-8")
        book_context.update_archive_section(book_id, section, body)
    except RuntimeError:
        return


def backup_file(path: Path) -> None:
    file_utils.backup_file(path, _paths.resolved("BACKUPS_DIR"))


def read_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    section = _archive_section_for_path(path)
    archive_file = _paths.resolved("ARCHIVE_FILE")
    if section and archive_file.exists():
        try:
            import book_context

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
        file_utils.atomic_write_text(path, f"{existing}{content}")
        _sync_archive_section_from_file(path)
        return True
    if read_text(path) == content:
        return False
    backup_file(path)
    file_utils.atomic_write_text(path, content)
    _sync_archive_section_from_file(path)
    return True
