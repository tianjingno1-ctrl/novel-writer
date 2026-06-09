"""Plan / 场景编排（api 层不直接碰 novel_data）。"""
from __future__ import annotations

from core.data import novel_data
from app.chapter_titles import (
    refresh_chapter_file_header,
    sync_all_chapter_titles_from_files,
)


def list_plan_chapters() -> dict:
    return {"chapters": novel_data.list_plan_chapters()}


def list_plan_full() -> dict:
    sync_all_chapter_titles_from_files()
    return {"chapters": novel_data.list_plan_details()}


def update_chapter_title(chapter_num: int, title: str) -> dict:
    title = title.strip()
    if not title:
        return {"ok": False, "error": "标题不能为空"}
    if novel_data.update_chapter_title(chapter_num, title) is None:
        return {"ok": False, "error": "章节不存在", "status": 404}
    refresh_chapter_file_header(chapter_num, title)
    return {"ok": True, "title": title}


def reorder_scenes(chapter_num: int, scene_ids: list[str]) -> dict:
    if not novel_data.reorder_scenes(chapter_num, scene_ids):
        return {"ok": False, "error": "章节不存在", "status": 404}
    return {"ok": True}


def get_chapter_plan(chapter_num: int) -> dict:
    ch = novel_data.get_chapter_plan(chapter_num)
    if ch is None:
        ch = novel_data.ensure_chapter_plan(chapter_num)["chapters"][str(chapter_num)]
        ch = {"num": chapter_num, **ch}
    return ch


def add_scene(chapter_num: int, title: str, beat: str) -> dict:
    title = title.strip()
    if not title:
        return {"ok": False, "error": "场景标题不能为空"}
    scene = novel_data.add_scene(chapter_num, title, beat)
    return {"ok": True, "scene": scene}


def update_scene(scene_id: str, **fields) -> dict:
    if "title" in fields and not str(fields["title"]).strip():
        return {"ok": False, "error": "场景标题不能为空"}
    scene = novel_data.update_scene(scene_id, **fields)
    if scene is None:
        return {"ok": False, "error": "场景不存在", "status": 404}
    return {"ok": True, "scene": scene}


def delete_scene(scene_id: str) -> dict:
    if not novel_data.delete_scene(scene_id):
        return {"ok": False, "error": "场景不存在", "status": 404}
    return {"ok": True}


def set_active_scene(scene_id: str) -> dict:
    if novel_data.get_scene(scene_id) is None:
        return {"ok": False, "error": "场景不存在", "status": 404}
    return novel_data.set_active_scene(scene_id)
