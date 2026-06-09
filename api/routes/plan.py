"""Plan / 场景 HTTP 路由。"""

from __future__ import annotations

import novel_data
from app.chapter_titles import (
    refresh_chapter_file_header,
    sync_all_chapter_titles_from_files,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

router = APIRouter(tags=["plan"])

MAX_API_TEXT_CHARS = 50_000


def _check_api_text(v: str) -> str:
    if len(v) > MAX_API_TEXT_CHARS:
        raise ValueError(f"文本过长（上限 {MAX_API_TEXT_CHARS} 字符）")
    return v


class ChapterTitleUpdate(BaseModel):
    title: str

    _validate_title = field_validator("title")(_check_api_text)


class SceneCreate(BaseModel):
    chapter_num: int
    title: str = "新场景"
    beat: str = ""

    _validate_title = field_validator("title")(_check_api_text)
    _validate_beat = field_validator("beat")(_check_api_text)


class SceneUpdate(BaseModel):
    title: str | None = None
    beat: str | None = None
    pace: str | None = None
    emotion_anchor: dict | None = None
    summary: str | None = None
    done: bool | None = None

    @field_validator("title", "beat", "summary")
    @classmethod
    def check_optional_text(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _check_api_text(v)

    @field_validator("pace")
    @classmethod
    def check_pace(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("快", "中", "慢"):
            raise ValueError("pace 必须是 快 / 中 / 慢")
        return v

    @field_validator("emotion_anchor")
    @classmethod
    def check_emotion_anchor(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        if not isinstance(v, dict):
            raise ValueError("emotion_anchor 必须是对象")
        target = str(v.get("target", "")).strip()
        how = str(v.get("how", "")).strip()
        if len(target) > 500 or len(how) > 1000:
            raise ValueError("情绪锚点过长")
        return {"target": target, "how": how}


class SceneReorder(BaseModel):
    scene_ids: list[str]


@router.get("/api/plan")
def plan_all() -> dict:
    return {"chapters": novel_data.list_plan_chapters()}


@router.get("/api/plan/full")
def plan_full() -> dict:
    sync_all_chapter_titles_from_files()
    return {"chapters": novel_data.list_plan_details()}


@router.put("/api/plan/{chapter_num}/title")
def plan_update_chapter_title(
    chapter_num: int, body: ChapterTitleUpdate
) -> dict:
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "标题不能为空")
    if novel_data.update_chapter_title(chapter_num, title) is None:
        raise HTTPException(404, "章节不存在")
    refresh_chapter_file_header(chapter_num, title)
    return {"ok": True, "title": title}


@router.put("/api/plan/{chapter_num}/reorder")
def plan_reorder_scenes(chapter_num: int, body: SceneReorder) -> dict:
    if not novel_data.reorder_scenes(chapter_num, body.scene_ids):
        raise HTTPException(404, "章节不存在")
    return {"ok": True}


@router.get("/api/plan/{chapter_num}")
def plan_chapter(chapter_num: int) -> dict:
    ch = novel_data.get_chapter_plan(chapter_num)
    if ch is None:
        ch = novel_data.ensure_chapter_plan(chapter_num)["chapters"][
            str(chapter_num)
        ]
        ch = {"num": chapter_num, **ch}
    return ch


@router.post("/api/plan/scenes")
def plan_add_scene(body: SceneCreate) -> dict:
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "场景标题不能为空")
    scene = novel_data.add_scene(body.chapter_num, title, body.beat)
    return {"ok": True, "scene": scene}


@router.put("/api/plan/scenes/{scene_id}")
def plan_update_scene(scene_id: str, body: SceneUpdate) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if "title" in fields and not str(fields["title"]).strip():
        raise HTTPException(400, "场景标题不能为空")
    scene = novel_data.update_scene(scene_id, **fields)
    if scene is None:
        raise HTTPException(404, "场景不存在")
    return {"ok": True, "scene": scene}


@router.delete("/api/plan/scenes/{scene_id}")
def plan_delete_scene(scene_id: str) -> dict:
    if not novel_data.delete_scene(scene_id):
        raise HTTPException(404, "场景不存在")
    return {"ok": True}


@router.put("/api/plan/active/{scene_id}")
def plan_set_active(scene_id: str) -> dict:
    if novel_data.get_scene(scene_id) is None:
        raise HTTPException(404, "场景不存在")
    return novel_data.set_active_scene(scene_id)
