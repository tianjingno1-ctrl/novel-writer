"""女频审阅 HTTP 路由。"""

from __future__ import annotations

import novel_data
import review_prompts
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_app_context, require_ok
from app.context import AppContext
from core.orchestration import female_fiction as orchestration_ff

router = APIRouter(tags=["female-fiction"])


class FemaleFictionReviewRequest(BaseModel):
    mode: str = "chapter"
    text: str = ""
    chapter_num: int | None = None
    profile_id: str | None = None
    revise: bool = False
    write_back: bool = False
    sync_archive: bool = True


class FemaleFictionAcceptRequest(BaseModel):
    log_id: str
    sync_archive: bool = True


@router.post("/api/review/female-fiction")
def female_fiction_review(
    body: FemaleFictionReviewRequest,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    return require_ok(
        orchestration_ff.run_female_fiction_review(
            ctx,
            mode=body.mode,
            text=body.text,
            chapter_num=body.chapter_num,
            profile_id=body.profile_id,
            revise=body.revise,
            write_back=body.write_back,
            sync_archive=body.sync_archive,
        ),
        "女频审阅失败",
    )


@router.post("/api/review/female-fiction/accept")
def female_fiction_accept(
    body: FemaleFictionAcceptRequest,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    return require_ok(
        orchestration_ff.accept_female_fiction_rewrite(
            ctx,
            body.log_id,
            sync_archive=body.sync_archive,
        ),
        "采纳改稿失败",
    )


@router.get("/api/review/profiles")
def review_profiles(ctx: AppContext = Depends(get_app_context)) -> dict:
    del ctx
    project = novel_data.get_project_meta()
    return {
        "profiles": review_prompts.list_profiles(),
        "active": review_prompts.active_profile_for_project(project),
    }
