"""元信息 HTTP 路由（根路径、状态、调试）。"""

from __future__ import annotations

import main as core
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["meta"])


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs", status_code=302)


@router.get("/api/status")
def status() -> dict:
    status_data = core.get_app_status()
    last = core.get_last_call_info()
    if last:
        status_data["last_call"] = last
    return status_data


@router.get("/api/debug/last_context")
def debug_last_context() -> dict:
    return core.get_last_context_debug()
