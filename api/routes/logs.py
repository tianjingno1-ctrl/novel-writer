"""质量记录 / 运行时日志 HTTP 路由。"""

from __future__ import annotations

from core.orchestration import logs as orchestration_logs
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["logs"])


@router.get("/api/quality/log")
def quality_log_list(kind: str | None = None, limit: int = 80) -> dict:
    return orchestration_logs.list_quality_entries(kind=kind, limit=limit)


@router.get("/api/quality/log/{entry_id}")
def quality_log_get(entry_id: str) -> dict:
    row = orchestration_logs.get_quality_entry(entry_id)
    if not row:
        raise HTTPException(404, "记录不存在")
    return row


@router.get("/api/runtime-logs")
def runtime_logs_list(
    level: str | None = None,
    category: str | None = None,
    limit: int = 80,
) -> dict:
    return orchestration_logs.list_runtime_entries(
        level=level, category=category, limit=limit
    )


@router.get("/api/runtime-logs/{entry_id}")
def runtime_logs_get(entry_id: str) -> dict:
    row = orchestration_logs.get_runtime_entry(entry_id)
    if not row:
        raise HTTPException(404, "日志不存在")
    return row
