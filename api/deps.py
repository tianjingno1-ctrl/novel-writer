"""API 层共享依赖（HTTP 错误转换、AppContext 注入）。"""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.context import AppContext


def require_ok(result: dict, default_msg: str = "操作失败") -> dict:
    """将编排层 {ok: false, error} 统一转为 HTTPException。"""
    if not result.get("ok", True):
        raise HTTPException(400, result.get("error", default_msg))
    return result


def get_app_context(request: Request) -> AppContext:
    """从 FastAPI app.state 取 AppContext（lifespan 中 init_context 挂载）。"""
    ctx = getattr(request.app.state, "ctx", None)
    if ctx is None:
        raise HTTPException(500, "AppContext 未初始化")
    return ctx
