"""产品 Schema HTTP 路由（无前端）。"""

from __future__ import annotations

from typing import Any

from app.bootstrap import get_app_context
from core.orchestration import product as orchestration_product
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["product"])


def _ctx(request: Request):
    return request.app.state.ctx or get_app_context()


def _err(result: dict, default: str = "操作失败") -> None:
    if result.get("ok", True):
        return
    raise HTTPException(400, result.get("error", default))


class PlanMetaBody(BaseModel):
    meta: dict[str, Any]


class ReviewCriteriaBody(BaseModel):
    platform_profile: str | None = None
    hard_rules: list[str] | None = None
    soft_rules: list[str] | None = None
    custom_checks: list[str] | None = None


class ChapterStatusBody(BaseModel):
    status: str


class PrecheckBody(BaseModel):
    content: str = ""


class ReaderPreviewBody(BaseModel):
    content: str = ""


class CompliancePreviewBody(BaseModel):
    submission_target: str = "text_editor"


class HighlightBody(BaseModel):
    text: str
    annotation: str = ""
    tags: list[str] | None = None


class RerunPreviewBody(BaseModel):
    scope: str
    from_chapter_num: int = 0
    current_chapter_num: int = 0


class DiagnosisDecideBody(BaseModel):
    accepted: bool
    rerun_scope: str = "none"
    from_chapter_num: int = 0
    apply_override: bool = True
    execute_rerun: bool = False


class RerunExecuteBody(BaseModel):
    scope: str
    from_chapter_num: int = 0
    current_chapter_num: int = 0
    reset_plan_fields: bool = False
    clear_chapter_drafts: bool = True
    auto_plan_llm: bool = True
    plan_context_note: str = ""


class FlowRunBody(BaseModel):
    mode: str = "continue"
    chapter_num: int = 0
    from_step: str = ""
    stop_after: str = ""
    scope: str = ""
    from_chapter_num: int = 0
    current_chapter_num: int = 0
    reset_plan_fields: bool = False
    clear_chapter_drafts: bool = True
    auto_plan_llm: bool = True
    plan_context_note: str = ""
    write_instruction: str = ""
    auto_adopt_write: bool = False
    judgment: dict[str, Any] | None = None
    auto_confirm_summary: bool = False


class LifecycleBody(BaseModel):
    status: str | None = None
    manuscript_id: str | None = None


@router.get("/api/plan/product")
def get_plan_product(request: Request) -> dict:
    return orchestration_product.get_plan_product(_ctx(request))


@router.put("/api/plan/meta")
def put_plan_meta(body: PlanMetaBody, request: Request) -> dict:
    return orchestration_product.put_plan_meta(_ctx(request), body.meta)


@router.put("/api/plan/review-criteria")
def put_review_criteria(body: ReviewCriteriaBody, request: Request) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "无更新字段")
    return orchestration_product.put_review_criteria(_ctx(request), fields)


@router.post("/api/plan/review-criteria/init")
def init_review_criteria(request: Request, profile_id: str = "") -> dict:
    return orchestration_product.init_review_criteria_from_profile(_ctx(request), profile_id)


@router.patch("/api/plan/chapters/{chapter_num}/status")
def patch_chapter_status(
    chapter_num: int, body: ChapterStatusBody, request: Request,
) -> dict:
    try:
        return orchestration_product.set_chapter_status(
            _ctx(request), chapter_num, body.status,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/chapters/{chapter_num}/precheck")
def chapter_precheck(
    chapter_num: int, body: PrecheckBody, request: Request,
) -> dict:
    return orchestration_product.run_precheck(
        _ctx(request), chapter_num, body.content,
    )


@router.post("/api/chapters/{chapter_num}/reader-preview")
def chapter_reader_preview(
    chapter_num: int, body: ReaderPreviewBody, request: Request,
) -> dict:
    return orchestration_product.run_reader_preview(
        _ctx(request), chapter_num, body.content,
    )


@router.post("/api/compliance/preview")
def compliance_preview(body: CompliancePreviewBody, request: Request) -> dict:
    return orchestration_product.run_compliance_preview(
        _ctx(request),
        submission_target=body.submission_target,
    )


@router.post("/api/taste/highlights/{chapter_num}")
def taste_push_highlight(
    chapter_num: int, body: HighlightBody, request: Request,
) -> dict:
    if not body.text.strip():
        raise HTTPException(400, "text 不能为空")
    return orchestration_product.push_highlight(
        _ctx(request),
        chapter_num=chapter_num,
        text=body.text,
        annotation=body.annotation,
        tags=body.tags,
    )


@router.post("/api/rerun/preview")
def rerun_preview(body: RerunPreviewBody, request: Request) -> dict:
    return orchestration_product.rerun_impact_preview(
        _ctx(request),
        scope=body.scope,
        from_chapter_num=body.from_chapter_num,
        current_chapter_num=body.current_chapter_num,
    )


@router.post("/api/rerun/execute")
def rerun_execute(body: RerunExecuteBody, request: Request) -> dict:
    result = orchestration_product.execute_rerun(
        _ctx(request),
        scope=body.scope,
        from_chapter_num=body.from_chapter_num,
        current_chapter_num=body.current_chapter_num,
        reset_plan_fields=body.reset_plan_fields,
        clear_chapter_drafts=body.clear_chapter_drafts,
        auto_plan_llm=body.auto_plan_llm,
        plan_context_note=body.plan_context_note,
    )
    _err(result)
    return result


@router.post("/api/rerun/pipeline")
def rerun_pipeline(body: RerunExecuteBody, request: Request) -> dict:
    """P4 重跑流水线（与 /api/rerun/execute 等价）。"""
    return rerun_execute(body, request)


@router.get("/api/flow/work-queue")
def flow_work_queue(request: Request) -> dict:
    return orchestration_product.get_work_queue(_ctx(request))


@router.get("/api/flow/steps")
def flow_steps() -> dict:
    """聚合 runner 可用步骤（单步 /api/* 接口不受影响）。"""
    return orchestration_product.list_flow_steps()


@router.post("/api/flow/run")
def flow_run(body: FlowRunBody, request: Request) -> dict:
    """可选一键串联；stop_after 或人工确认点会停住。单步 API 仍可直接调用。"""
    result = orchestration_product.run_flow(
        _ctx(request),
        mode=body.mode,
        chapter_num=body.chapter_num,
        from_step=body.from_step,
        stop_after=body.stop_after,
        scope=body.scope,
        from_chapter_num=body.from_chapter_num,
        current_chapter_num=body.current_chapter_num,
        reset_plan_fields=body.reset_plan_fields,
        clear_chapter_drafts=body.clear_chapter_drafts,
        auto_plan_llm=body.auto_plan_llm,
        plan_context_note=body.plan_context_note,
        write_instruction=body.write_instruction,
        auto_adopt_write=body.auto_adopt_write,
        judgment=body.judgment,
        auto_confirm_summary=body.auto_confirm_summary,
    )
    if not result.get("ok") and result.get("stop_reason") != "step_failed":
        _err(result)
    if result.get("stop_reason") == "step_failed":
        raise HTTPException(400, result.get("error", "流程步骤失败"))
    return result


@router.get("/api/chapters/{chapter_num}/summary")
def get_chapter_summary(chapter_num: int, request: Request) -> dict:
    result = orchestration_product.get_chapter_summary(_ctx(request), chapter_num)
    if not result.get("ok"):
        raise HTTPException(404, result.get("error", "概述不存在"))
    return result


@router.post("/api/chapters/{chapter_num}/summary/confirm")
def confirm_summary(chapter_num: int, request: Request) -> dict:
    result = orchestration_product.confirm_chapter_summary(_ctx(request), chapter_num)
    _err(result)
    return result


@router.get("/api/profiles")
def list_profiles() -> dict:
    return orchestration_product.list_profiles()


@router.get("/api/profiles/{profile_id}")
def get_profile(profile_id: str) -> dict:
    result = orchestration_product.get_profile(profile_id)
    _err(result, "profile 不存在")
    return result


@router.get("/api/deconstruct")
def list_deconstructs(request: Request, limit: int = 50) -> dict:
    return orchestration_product.list_deconstructs(_ctx(request), limit=limit)


@router.post("/api/deconstruct/{deconstruct_id}/elevate")
def elevate_deconstruct(deconstruct_id: str, request: Request) -> dict:
    result = orchestration_product.elevate_deconstruct(_ctx(request), deconstruct_id)
    _err(result)
    return result


@router.get("/api/diagnosis")
def list_diagnoses(request: Request, limit: int = 30) -> dict:
    return orchestration_product.list_diagnoses(_ctx(request), limit=limit)


@router.post("/api/diagnosis/{diagnosis_id}/decide")
def decide_diagnosis(
    diagnosis_id: str, body: DiagnosisDecideBody, request: Request,
) -> dict:
    result = orchestration_product.decide_diagnosis(
        _ctx(request),
        diagnosis_id,
        accepted=body.accepted,
        rerun_scope_name=body.rerun_scope,
        from_chapter_num=body.from_chapter_num,
        apply_override=body.apply_override,
        execute_rerun=body.execute_rerun,
    )
    _err(result)
    return result


@router.get("/api/project/lifecycle")
def get_lifecycle(request: Request) -> dict:
    return orchestration_product.get_lifecycle(_ctx(request))


@router.put("/api/project/lifecycle")
def put_lifecycle(body: LifecycleBody, request: Request) -> dict:
    fields = body.model_dump(exclude_unset=True)
    try:
        return orchestration_product.put_lifecycle(_ctx(request), fields)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
