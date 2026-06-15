"""章后档案维护 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from api.deps import get_app_context, require_ok
from app.context import AppContext
from core.orchestration import archive_sync as orchestration_archive

router = APIRouter(tags=["post-chapter"])


class ChapterQualityRequest(BaseModel):
    chapter_num: int | None = None
    auto_append: bool = True
    auto_apply: bool = True

    @field_validator("chapter_num")
    @classmethod
    def check_chapter_num(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("chapter_num 须 ≥ 1")
        return v


@router.post("/api/post-chapter/maintain")
def post_chapter_maintain(
    body: ChapterQualityRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    body = body or ChapterQualityRequest()
    return require_ok(
        orchestration_archive.run_post_chapter_maintain(
            body.chapter_num,
            ctx,
            auto_apply=body.auto_apply,
            auto_append=body.auto_append,
        ),
        "章后维护失败",
    )
