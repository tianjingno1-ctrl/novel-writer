"""书架概览 / 统计 HTTP 路由。"""

from __future__ import annotations

from app import overview as overview_svc
from fastapi import APIRouter

router = APIRouter(tags=["stats"])


@router.get("/api/overview")
def bookshelf_overview() -> dict:
    return overview_svc.bookshelf_overview()


@router.get("/api/stats")
def stats() -> dict:
    return overview_svc.cached_stats()
