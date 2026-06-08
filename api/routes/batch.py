"""世界批次 / batch job HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from api.deps import get_app_context, require_ok
from app.batch_state import is_batch_job_running
from app.context import AppContext
from core.orchestration import batch as orchestration_batch

router = APIRouter(tags=["batch"])


class BatchJobRevertRequest(BaseModel):
    chapter_num: int

    @field_validator("chapter_num")
    @classmethod
    def check_chapter_num(cls, v: int) -> int:
        if v < 1:
            raise ValueError("chapter_num 须 ≥ 1")
        return v


class WorldBatchRequest(BaseModel):
    chapter_from: int | None = None
    chapter_to: int | None = None

    @field_validator("chapter_from", "chapter_to")
    @classmethod
    def check_chapter_num(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("chapter_num 须 ≥ 1")
        return v


class WorldGenerateRequest(WorldBatchRequest):
    overwrite: bool = False
    skip_existing: bool = True
    resume_job_id: str | None = None


def assert_not_running(*, message: str = "已有批次任务正在运行") -> None:
    if is_batch_job_running():
        raise HTTPException(409, message)


def require_ok_or_partial(result: dict, default_msg: str) -> dict:
    if not result.get("ok") and not result.get("partial"):
        raise HTTPException(400, result.get("error", default_msg))
    return result


@router.get("/api/batch/world/status")
def world_batch_status(ctx: AppContext = Depends(get_app_context)) -> dict:
    return orchestration_batch.get_world_batch_status(ctx)


@router.get("/api/batch/world/review/preview")
def world_batch_review_preview(
    chapter_from: int | None = None,
    chapter_to: int | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    result = orchestration_batch.preview_world_batch_review(
        ctx,
        chapter_from=chapter_from,
        chapter_to=chapter_to,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "无法生成预览"))
    return result


@router.get("/api/batch/world/generate/resumable")
def batch_world_generate_resumable(ctx: AppContext = Depends(get_app_context)) -> dict:
    return orchestration_batch.find_resumable_generate_job(ctx)


@router.get("/api/batch/jobs")
def batch_jobs_list(
    kind: str | None = None,
    limit: int = 20,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    return orchestration_batch.list_batch_jobs(ctx, kind=kind, limit=limit)


@router.get("/api/batch/jobs/{job_id}")
def batch_job_get(job_id: str, ctx: AppContext = Depends(get_app_context)) -> dict:
    result = orchestration_batch.get_batch_job(ctx, job_id)
    if not result.get("ok"):
        raise HTTPException(404, result.get("error", "任务不存在"))
    return result


@router.post("/api/batch/jobs/{job_id}/accept")
def batch_job_accept(job_id: str, ctx: AppContext = Depends(get_app_context)) -> dict:
    return require_ok(
        orchestration_batch.accept_batch_job(ctx, job_id),
        "确认失败",
    )


@router.post("/api/batch/jobs/{job_id}/revert")
def batch_job_revert(
    job_id: str,
    body: BatchJobRevertRequest,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    return require_ok(
        orchestration_batch.revert_batch_job_chapter(
            ctx, job_id, body.chapter_num
        ),
        "撤销失败",
    )


@router.post("/api/batch/world/generate")
def world_batch_generate(
    body: WorldGenerateRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    assert_not_running()
    req = body or WorldGenerateRequest()
    return require_ok_or_partial(
        orchestration_batch.run_world_batch_generate(
            ctx,
            chapter_from=req.chapter_from,
            chapter_to=req.chapter_to,
            overwrite=req.overwrite,
            skip_existing=req.skip_existing,
            resume_job_id=req.resume_job_id,
        ),
        "世界批量生成失败",
    )


@router.post("/api/batch/world/remediate")
def world_remediate(
    body: WorldBatchRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    assert_not_running(message="已有世界闭环任务正在运行")
    req = body or WorldBatchRequest()
    return require_ok_or_partial(
        orchestration_batch.run_world_remediate(
            ctx,
            chapter_from=req.chapter_from,
            chapter_to=req.chapter_to,
        ),
        "世界闭环失败",
    )


@router.post("/api/batch/world/review")
def world_batch_review(
    body: WorldBatchRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    req = body or WorldBatchRequest()
    return require_ok_or_partial(
        orchestration_batch.run_world_batch_review(
            ctx,
            chapter_from=req.chapter_from,
            chapter_to=req.chapter_to,
        ),
        "世界审阅失败",
    )


@router.post("/api/batch/world/finalize")
def world_batch_finalize(
    body: WorldBatchRequest | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    req = body or WorldBatchRequest()
    return require_ok_or_partial(
        orchestration_batch.run_world_batch_finalize(
            ctx,
            chapter_from=req.chapter_from,
            chapter_to=req.chapter_to,
        ),
        "世界定稿失败",
    )
