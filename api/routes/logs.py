"""质量记录 / 运行时日志 HTTP 路由。"""

from __future__ import annotations

import quality_log
import runtime_log
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["logs"])


@router.get("/api/quality/log")
def quality_log_list(kind: str | None = None, limit: int = 80) -> dict:
    return {"entries": quality_log.list_entries(limit=limit, kind=kind)}


@router.get("/api/quality/log/{entry_id}")
def quality_log_get(entry_id: str) -> dict:
    row = quality_log.get_entry(entry_id)
    if not row:
        raise HTTPException(404, "记录不存在")
    return row


@router.get("/api/runtime-logs")
def runtime_logs_list(
    level: str | None = None,
    category: str | None = None,
    limit: int = 80,
) -> dict:
    return {
        "status": runtime_log.get_status(),
        "entries": runtime_log.list_entries(
            limit=limit, level=level, category=category
        ),
    }


@router.get("/api/runtime-logs/{entry_id}")
def runtime_logs_get(entry_id: str) -> dict:
    row = runtime_log.get_entry(entry_id)
    if not row:
        raise HTTPException(404, "日志不存在")
    return row
