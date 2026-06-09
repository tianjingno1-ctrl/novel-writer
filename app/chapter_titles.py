"""章节标题与 plan.json 同步。"""

from __future__ import annotations

from infra import file_utils as bio
from app.chapters_api import list_chapters
from core import chapters as chapter_text


def sync_all_chapter_titles_from_files() -> None:
    from app import chapter_io as _cio

    for num, _ in list_chapters():
        _cio.sync_chapter_title_from_file(num)


def refresh_chapter_file_header(chapter_num: int, title: str) -> None:
    """更新章节 md 第一行标题，保留正文不变。"""
    from app import chapter_io as _cio

    path = _cio.get_chapter_path(chapter_num)
    if not path.exists():
        return
    body = chapter_text.strip_chapter_file_header(bio.read_text(path))
    bio.write_text(
        path,
        _cio.format_chapter_file(chapter_num, body, title=title),
        append=False,
    )
