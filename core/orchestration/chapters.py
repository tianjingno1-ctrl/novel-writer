"""章节编排。"""
from __future__ import annotations

from core.data import novel_data
from app import chapters_api as ch_svc


def list_chapters() -> dict:
    items = [{"num": n, "file": p.name} for n, p in ch_svc.list_chapters()]
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
