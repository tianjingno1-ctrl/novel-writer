"""章节编排。"""
from __future__ import annotations

import re

from core import chapters as chapter_text
from core.data import novel_data
from app import chapters_api as ch_svc


def _count_body_chars(content: str) -> int:
    body = chapter_text.strip_chapter_file_header(content or "")
    return len(re.sub(r"\s+", "", body))


def list_chapters() -> dict:
    plan = novel_data.load_plan()
    plan_chapters = plan.get("chapters") or {}
    items: list[dict] = []
    seen: set[int] = set()

    for num, path in ch_svc.list_chapters():
        seen.add(num)
        ch_plan = plan_chapters.get(str(num)) if isinstance(plan_chapters.get(str(num)), dict) else {}
        raw = ch_svc.get_chapter_by_num(num)
        content = (raw or {}).get("content") or ""
        target = int((ch_plan or {}).get("word_count_target") or 0)
        items.append({
            "num": num,
            "file": path.name,
            "title": str((ch_plan or {}).get("title") or "").strip(),
            "chars": _count_body_chars(content),
            "word_count_target": target or None,
        })

    for key in sorted(plan_chapters.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
        try:
            num = int(key)
        except ValueError:
            continue
        if num in seen:
            continue
        ch_plan = plan_chapters[key]
        if not isinstance(ch_plan, dict):
            continue
        target = int(ch_plan.get("word_count_target") or 0)
        items.append({
            "num": num,
            "file": "",
            "title": str(ch_plan.get("title") or "").strip(),
            "chars": 0,
            "word_count_target": target or None,
        })

    items.sort(key=lambda row: row["num"])
    return {"chapters": items}


def get_chapter(num: int) -> dict | None:
    ch = ch_svc.get_chapter_by_num(num)
    if ch is None:
        return None
    plan = novel_data.get_chapter_plan(num)
    return {**ch, "plan": plan}


def save_chapter(num: int, content: str) -> dict:
    return ch_svc.save_chapter_by_num(num, content)


def create_next_chapter() -> dict:
    r = ch_svc.create_next_chapter()
    novel_data.ensure_chapter_plan(r["num"])
    return r
