"""章节 HTTP 路由。"""

from __future__ import annotations

from core.orchestration import chapters as orchestration_chapters
from core.orchestration import writing as orchestration_writing
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
    source: str = "assistant"

    @field_validator("msg_index")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("msg_index 不能为负")
        return v


@router.get("/api/chapters")
def chapters_list() -> dict:
    return orchestration_chapters.list_chapters()


@router.get("/api/chapters/{num}")
def get_chapter(num: int) -> dict:
    ch = orchestration_chapters.get_chapter(num)
    if ch is None:
        raise HTTPException(404, f"章节 ch{num:03d} 不存在")
    return ch


@router.put("/api/chapters/{num}")
def put_chapter(num: int, body: ContentBody) -> dict:
    return orchestration_chapters.save_chapter(num, body.content)


@router.post("/api/chapters/new")
def new_chapter() -> dict:
    return orchestration_chapters.create_next_chapter()


@router.post("/api/chapters/undo-last")
def undo_last_chapter_write() -> dict:
    return require_ok(orchestration_writing.undo_last_chapter_write(), "撤销失败")


@router.post("/api/chapters/{num}/apply-turn")
def apply_chapter_turn(num: int, body: ApplyTurnBody) -> dict:
    result = orchestration_writing.apply_chapter_turn(
        num, body.msg_index, body.source
    )
    if not result.get("ok") and result.get("error") == "source 必须是 assistant 或 user_draft":
        raise HTTPException(400, result["error"])
    return require_ok(result, "替换章节失败")
