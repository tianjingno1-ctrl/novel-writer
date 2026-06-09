"""章节 IO CRUD 服务层（P3-3c-ii；apply-turn / undo 留 P3-4）。"""

from __future__ import annotations

import re
from pathlib import Path

import file_utils
import novel_data
from app.factories import invalidate_chapter_injection
from core import chapters as chapter_text


def list_chapters() -> list[tuple[int, Path]]:
    import main

    chapters: list[tuple[int, Path]] = []
    for p in main.CHAPTERS_DIR.glob("ch*.md"):
        m = re.match(r"ch(\d+)\.md$", p.name, re.IGNORECASE)
        if m:
            chapters.append((int(m.group(1)), p))
    chapters.sort(key=lambda x: x[0])
    return chapters


def get_chapter_by_num(num: int) -> dict | None:
    import main

    path = main.CHAPTERS_DIR / f"ch{num:03d}.md"
    if not path.exists():
        return None
    return {"num": num, "path": str(path.name), "content": main.read_text(path)}


def save_chapter_by_num(num: int, content: str) -> dict:
    import main

    path = main.CHAPTERS_DIR / f"ch{num:03d}.md"
    content = main.sanitize_chapter_text(content)
    changed = main.write_text(path, content, append=False, chapter_num=num)
    invalidate_chapter_injection(num)
    chapter_title = main.sync_chapter_title_from_file(num)
    return {"ok": True, "num": num, "chapter_title": chapter_title, "changed": changed}


def create_next_chapter() -> dict:
    import main

    chapters = list_chapters()
    next_num = (chapters[-1][0] + 1) if chapters else 1
    plan = novel_data.get_chapter_plan(next_num)
    title = (plan or {}).get("title", "") if plan else ""
    return _ensure_chapter_file(next_num, title)


def _ensure_chapter_file(chapter_num: int, title: str = "") -> dict:
    """若章节正文文件不存在则创建，并写入可编辑的标题行。"""
    import main

    path = main.CHAPTERS_DIR / f"ch{chapter_num:03d}.md"
    if path.exists():
        return {"ok": True, "num": chapter_num, "created": False, "file": path.name}
    path.parent.mkdir(parents=True, exist_ok=True)
    title = (title or "").strip()
    header = f"# 第{chapter_num}章"
    if title and title not in {
        f"第{chapter_num}章",
        f"第{chapter_text.chapter_cn(chapter_num)}章",
    }:
        header = f"{header} · {title}"
    file_utils.atomic_write_text(path, f"{header}\n\n")
    return {"ok": True, "num": chapter_num, "created": True, "file": path.name}
