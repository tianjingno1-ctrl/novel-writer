"""审阅工具箱 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from api.deps import get_app_context, require_ok
from app.context import AppContext
from core.orchestration import review as orchestration_review

router = APIRouter(tags=["review"])


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


class RepetitionRequest(BaseModel):
    chapter_num: int | None = None
    scope: str = "current"

    @field_validator("chapter_num")
    @classmethod
    def check_chapter_num(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("chapter_num 须 ≥ 1")
        return v

    @field_validator("scope")
    @classmethod
    def check_scope(cls, v: str) -> str:
        if v not in ("current", "recent3", "all"):
            raise ValueError("scope 必须是 current / recent3 / all")
        return v


class QualityScopeRequest(RepetitionRequest):
    """带 scope 的质量审阅请求。"""


class QualityFullRequest(QualityScopeRequest):
    run_pacing: bool = True
    run_reader: bool = True
    run_editor: bool = True


class ObserveApplyItem(BaseModel):
    id: str
    target_file: str
    accepted: bool = False
    proposed_text: str = ""
    edited_text: str | None = None

    @field_validator("target_file")
    @classmethod
    def check_target(cls, v: str) -> str:
        if v not in ("char_static", "char_dynamic"):
            raise ValueError("target_file 必须是 char_static 或 char_dynamic")
        return v


class ObserveApplyRequest(BaseModel):
    items: list[ObserveApplyItem]
    chapter_num: int | None = None


class DeconstructRequest(BaseModel):
    text: str
    source_label: str = ""
    include_book_context: bool = True


@router.post("/api/deconstruct")
def deconstruct_reference(
    body: DeconstructRequest,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    return require_ok(
        orchestration_review.run_deconstruct(
            body.text,
            ctx,
            source_label=body.source_label.strip(),
            include_book_context=body.include_book_context,
        ),
        "参考拆文失败",
    )


@router.post("/api/summary")
def run_summary(
    body: ChapterQualityRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    body = body or ChapterQualityRequest()
    return require_ok(
        orchestration_review.run_summary(body.chapter_num, ctx),
        "生成概述失败",
    )


@router.post("/api/check")
def run_check(
    body: QualityScopeRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    body = body or QualityScopeRequest()
    return require_ok(
        orchestration_review.run_check(body.chapter_num, body.scope, ctx),
        "连续性检查失败",
    )


@router.post("/api/check/character-drift")
def check_character_drift(
    body: ChapterQualityRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    body = body or ChapterQualityRequest()
    return require_ok(
        orchestration_review.run_character_drift(body.chapter_num, ctx),
        "人物检查失败",
    )


@router.post("/api/extract/details")
def extract_details(
    body: ChapterQualityRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    body = body or ChapterQualityRequest()
    return require_ok(
        orchestration_review.run_detail_extract(
            body.chapter_num, ctx, auto_append=body.auto_append
        ),
        "细节提取失败",
    )


@router.post("/api/check/repetition")
def check_repetition(
    body: RepetitionRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    body = body or RepetitionRequest()
    return require_ok(
        orchestration_review.run_repetition_check(
            body.chapter_num, body.scope, ctx
        ),
        "套话检查失败",
    )


@router.post("/api/check/pacing")
def check_pacing(ctx: AppContext = Depends(get_app_context)) -> dict:
    return require_ok(
        orchestration_review.run_pacing_check(ctx),
        "爽点检查失败",
    )


@router.post("/api/quality/reader")
def quality_reader(
    body: QualityScopeRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    body = body or QualityScopeRequest()
    return require_ok(
        orchestration_review.run_reader_review(
            body.chapter_num, body.scope, ctx
        ),
        "读者审阅失败",
    )


@router.post("/api/quality/editor")
def quality_editor(
    body: QualityScopeRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    body = body or QualityScopeRequest()
    return require_ok(
        orchestration_review.run_editor_review(
            body.chapter_num, body.scope, ctx
        ),
        "编辑审阅失败",
    )


@router.post("/api/quality/full")
def quality_full(
    body: QualityFullRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    body = body or QualityFullRequest()
    return require_ok(
        orchestration_review.run_quality_full_review(
            body.chapter_num,
            ctx,
            scope=body.scope,
            run_pacing=body.run_pacing,
            run_reader=body.run_reader,
            run_editor=body.run_editor,
        ),
        "质量审阅失败",
    )


@router.post("/api/observe")
def run_observe(
    body: ChapterQualityRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    body = body or ChapterQualityRequest()
    return require_ok(
        orchestration_review.run_observe(
            body.chapter_num, ctx, auto_apply=body.auto_apply
        ),
        "角色观察失败",
    )


@router.post("/api/observe/apply")
def apply_observe(
    body: ObserveApplyRequest,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    payload = [item.model_dump() for item in body.items]
    return require_ok(
        ctx.store.apply_observe(payload, chapter_num=body.chapter_num),
        "写入失败",
    )
