"""续章灵感 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from api.deps import get_app_context, require_ok
from app.context import AppContext
from core.orchestration import outline as orchestration_outline

router = APIRouter(tags=["outline"])


class OutlineRequest(BaseModel):
    next_count: int = 3

    @field_validator("next_count")
    @classmethod
    def validate_next_count(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("章节数须在 1-10 之间")
        return v


class OutlineApplyRequest(BaseModel):
    offset: int = 1
    replace: bool = False
    reply: str | None = None

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("offset 须在 1-10 之间")
        return v


@router.post("/api/outline")
def run_outline(
    body: OutlineRequest,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    return require_ok(
        orchestration_outline.run_outline(ctx, next_count=body.next_count),
        "续章灵感生成失败",
    )


@router.get("/api/outline/latest")
def outline_latest(ctx: AppContext = Depends(get_app_context)) -> dict:
    return orchestration_outline.get_outline_latest(ctx)


@router.post("/api/outline/apply")
def outline_apply(
    body: OutlineApplyRequest,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    result = orchestration_outline.apply_outline(
        ctx,
        body.offset,
        replace=body.replace,
        reply=body.reply,
    )
    if result.get("need_replace"):
        raise HTTPException(409, result.get("error", "需要确认覆盖"))
    return require_ok(result, "写入 Plan 失败")
