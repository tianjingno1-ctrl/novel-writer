"""本章定稿 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from api.deps import get_app_context, require_ok
from app.context import AppContext
from app.hooks import build_finalize_hooks
from core.orchestration import finalize as orchestration_finalize

router = APIRouter(tags=["post-chapter"])


class FinalizeChapterRequest(BaseModel):
    chapter_num: int | None = None
    run_pacing: bool = True
    run_outline: bool = False
    repetition_scope: str = "current"
    auto_apply_observe: bool = True
    auto_append_locked: bool = True
    auto_append_plot_new: bool = True

    @field_validator("chapter_num")
    @classmethod
    def check_chapter_num(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("chapter_num 须 ≥ 1")
        return v

    @field_validator("repetition_scope")
    @classmethod
    def check_repetition_scope(cls, v: str) -> str:
        if v not in ("current", "recent3", "all"):
            raise ValueError("repetition_scope 须为 current / recent3 / all")
        return v


@router.post("/api/post-chapter/finalize")
def post_chapter_finalize(body: FinalizeChapterRequest | None = None) -> dict:
    body = body or FinalizeChapterRequest()
    result = orchestration_finalize.run_post_chapter_finalize(
        body.chapter_num,
        build_finalize_hooks(),
        run_pacing=body.run_pacing,
        run_outline=body.run_outline,
        repetition_scope=body.repetition_scope,
        auto_apply_observe=body.auto_apply_observe,
        auto_append_locked=body.auto_append_locked,
        auto_append_plot_new=body.auto_append_plot_new,
    )
    return require_ok(result, "本章定稿失败")
