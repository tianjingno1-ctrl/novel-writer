"""元信息 HTTP 路由（根路径、状态、调试）。"""

from __future__ import annotations

from app import llm
from app import runtime as rt
from app import writing_ctx as _wctx
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["meta"])


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs", status_code=302)


@router.get("/api/status")
def status() -> dict:
    status_data = rt.get_app_status()
    last = llm.get_last_call_info()
    if last:
        status_data["last_call"] = last
    return status_data


@router.get("/api/debug/last_context")
def debug_last_context() -> dict:
    return _wctx.get_last_context_debug()
