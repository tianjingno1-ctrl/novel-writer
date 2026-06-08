"""章节 HTTP 路由。"""

from __future__ import annotations

import main as core
import novel_data
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from api.deps import require_ok

router = APIRouter(tags=["chapters"])

MAX_CONTENT_BYTES = 2 * 1024 * 1024


def _check_file_content(v: str) -> str:
    if len(v.encode("utf-8")) > MAX_CONTENT_BYTES:
        mb = MAX_CONTENT_BYTES // 1024 // 1024
        raise ValueError(f"内容过大（上限 {mb}MB）")
    return v


class ContentBody(BaseModel):
    content: str
    chapter_num: int | None = None

    @field_validator("content")
    @classmethod
    def check_size(cls, v: str) -> str:
        return _check_file_content(v)


class ApplyTurnBody(BaseModel):
    msg_index: int
    source: str = "assistant"  # assistant | user_draft

    @field_validator("msg_index")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("msg_index 不能为负")
        return v


@router.get("/api/chapters")
def chapters_list() -> dict:
    items = [{"num": n, "file": p.name} for n, p in core.list_chapters()]
    return {"chapters": items}


@router.get("/api/chapters/{num}")
def get_chapter(num: int) -> dict:
    ch = core.get_chapter_by_num(num)
    if ch is None:
        raise HTTPException(404, f"章节 ch{num:03d} 不存在")
    plan = novel_data.get_chapter_plan(num)
    return {**ch, "plan": plan}


@router.put("/api/chapters/{num}")
def put_chapter(num: int, body: ContentBody) -> dict:
    return core.save_chapter_by_num(num, body.content)


@router.post("/api/chapters/new")
def new_chapter() -> dict:
    r = core.create_next_chapter()
    novel_data.ensure_chapter_plan(r["num"])
    return r


@router.post("/api/chapters/undo-last")
def undo_last_chapter_write() -> dict:
    return require_ok(core.undo_last_chapter_append(), "撤销失败")


@router.post("/api/chapters/{num}/apply-turn")
def apply_chapter_turn(num: int, body: ApplyTurnBody) -> dict:
    if body.source == "user_draft":
        result = core.apply_user_draft_turn_to_chapter(num, body.msg_index)
    elif body.source == "assistant":
        result = core.apply_assistant_turn_to_chapter(num, body.msg_index)
    else:
        raise HTTPException(400, "source 必须是 assistant 或 user_draft")
    return require_ok(result, "替换章节失败")
