"""Plan / 场景 HTTP 路由。"""

from __future__ import annotations

from core.orchestration import plan as orchestration_plan
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


def _plan_err(result: dict, default: str) -> None:
    if result.get("ok", True):
        return
    status = int(result.get("status", 400))
    raise HTTPException(status, result.get("error", default))


@router.get("/api/plan")
def plan_all() -> dict:
    return orchestration_plan.list_plan_chapters()


@router.get("/api/plan/full")
def plan_full() -> dict:
    return orchestration_plan.list_plan_full()


@router.put("/api/plan/{chapter_num}/title")
def plan_update_chapter_title(
    chapter_num: int, body: ChapterTitleUpdate
) -> dict:
    result = orchestration_plan.update_chapter_title(chapter_num, body.title)
    _plan_err(result, "更新失败")
    return result


@router.put("/api/plan/{chapter_num}/reorder")
def plan_reorder_scenes(chapter_num: int, body: SceneReorder) -> dict:
    result = orchestration_plan.reorder_scenes(chapter_num, body.scene_ids)
    _plan_err(result, "重排失败")
    return result


@router.get("/api/plan/{chapter_num}")
def plan_chapter(chapter_num: int) -> dict:
    return orchestration_plan.get_chapter_plan(chapter_num)


@router.post("/api/plan/scenes")
def plan_add_scene(body: SceneCreate) -> dict:
    result = orchestration_plan.add_scene(body.chapter_num, body.title, body.beat)
    _plan_err(result, "添加失败")
    return result


@router.put("/api/plan/scenes/{scene_id}")
def plan_update_scene(scene_id: str, body: SceneUpdate) -> dict:
    result = orchestration_plan.update_scene(scene_id, **body.model_dump(exclude_unset=True))
    _plan_err(result, "更新失败")
    return result


@router.delete("/api/plan/scenes/{scene_id}")
def plan_delete_scene(scene_id: str) -> dict:
    result = orchestration_plan.delete_scene(scene_id)
    _plan_err(result, "删除失败")
    return result


@router.put("/api/plan/active/{scene_id}")
def plan_set_active(scene_id: str) -> dict:
    result = orchestration_plan.set_active_scene(scene_id)
    _plan_err(result, "设置失败")
    return result
