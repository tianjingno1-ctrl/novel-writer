"""章节标题与 plan.json 同步（懒 import main IO）。"""

from __future__ import annotations


def sync_all_chapter_titles_from_files() -> None:
    import main

    for num, _ in main.list_chapters():
        main.sync_chapter_title_from_file(num)


def refresh_chapter_file_header(chapter_num: int, title: str) -> None:
    """更新章节 md 第一行标题，保留正文不变。"""
    import main
    from app import book_io as bio

    path = main.get_chapter_path(chapter_num)
    if not path.exists():
        return
    body = main.strip_chapter_file_header(bio.read_text(path))
    bio.write_text(
        path,
        main.format_chapter_file(chapter_num, body, title=title),
        append=False,
    )
