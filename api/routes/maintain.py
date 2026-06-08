"""章后档案维护 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_app_context, require_ok
from api.routes.review import ChapterQualityRequest
from app.context import AppContext
from core.orchestration import archive_sync as orchestration_archive

router = APIRouter(tags=["post-chapter"])


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
