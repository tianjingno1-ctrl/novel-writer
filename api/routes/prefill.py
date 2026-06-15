"""AI 预填 HTTP 路由。"""
from __future__ import annotations

from typing import Any

from app.bootstrap import get_app_context
from core.orchestration import prefill as orchestration_prefill
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

router = APIRouter(tags=["prefill"])

MAX_TEXT = 50_000


def _check_text(v: str) -> str:
    if len(v) > MAX_TEXT:
        raise ValueError(f"文本过长（上限 {MAX_TEXT} 字符）")
    return v


class PrefillDirectionBody(BaseModel):
    seed: str = ""
    reference_excerpt: str = ""
    chapter_count: int = 3

    _v_seed = field_validator("seed", "reference_excerpt")(_check_text)


class ApplyDirectionBody(BaseModel):
    option: dict[str, Any]
    log_id: str | None = None


class PrefillPlanBody(BaseModel):
    direction_option: dict[str, Any] | None = None
    chapter_count: int | None = None


class ApplyPlanBody(BaseModel):
    option: dict[str, Any]
    replace: bool = True
    log_id: str | None = None


def _ctx(request: Request):
    return request.app.state.ctx or get_app_context()


def _err(result: dict, default: str = "操作失败") -> None:
    if result.get("ok", True):
        return
    raise HTTPException(400, result.get("error", default))


@router.post("/api/prefill/direction")
def prefill_direction(body: PrefillDirectionBody, request: Request) -> dict:
    result = orchestration_prefill.run_prefill_direction(
        _ctx(request),
        seed=body.seed,
        reference_excerpt=body.reference_excerpt,
        chapter_count=body.chapter_count,
    )
    _err(result, "预填方向失败")
    return result


@router.post("/api/prefill/direction/apply")
def apply_direction(body: ApplyDirectionBody, request: Request) -> dict:
    result = orchestration_prefill.apply_direction_option(
        _ctx(request), body.option, log_id=body.log_id,
    )
    _err(result, "采纳方向失败")
    return result


@router.post("/api/prefill/plan")
def prefill_plan(body: PrefillPlanBody, request: Request) -> dict:
    result = orchestration_prefill.run_prefill_plan(
        _ctx(request),
        direction_option=body.direction_option,
        chapter_count=body.chapter_count,
    )
    _err(result, "预填规划失败")
    return result


@router.post("/api/prefill/plan/validate")
def validate_plan(body: ApplyPlanBody, request: Request) -> dict:
    result = orchestration_prefill.validate_plan_option(
        _ctx(request),
        body.option,
        replace=body.replace,
    )
    return result


@router.post("/api/prefill/plan/semantic-validate")
def semantic_validate_plan(body: ApplyPlanBody, request: Request) -> dict:
    result = orchestration_prefill.semantic_validate_plan_option(
        _ctx(request),
        body.option,
        replace=body.replace,
    )
    return result


@router.post("/api/prefill/plan/apply")
def apply_plan(body: ApplyPlanBody, request: Request) -> dict:
    result = orchestration_prefill.apply_plan_option(
        _ctx(request),
        body.option,
        replace=body.replace,
        log_id=body.log_id,
    )
    _err(result, "采纳规划失败")
    return result
