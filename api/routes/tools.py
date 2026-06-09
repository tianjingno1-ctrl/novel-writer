"""工具类 HTTP 路由（Prompt Cache 续命等）。"""

from __future__ import annotations

import infra.config as config
from app import runtime as rt
from core import model_routing
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["tools"])


class PromptCacheSettings(BaseModel):
    heartbeat_enabled: bool | None = None
    prompt_cache_auto_refresh: bool | None = None


@router.get("/api/tools/prompt-cache/status")
def prompt_cache_status() -> dict:
    return rt.get_prompt_cache_status()


@router.post("/api/tools/prompt-cache/refresh")
def prompt_cache_refresh() -> dict:
    return rt.refresh_prompt_cache()


@router.put("/api/tools/prompt-cache/settings")
def prompt_cache_settings(body: PromptCacheSettings) -> dict:
    if body.heartbeat_enabled is not None:
        config.HEARTBEAT_ENABLED = body.heartbeat_enabled
    if body.prompt_cache_auto_refresh is not None:
        model_routing.PROMPT_CACHE_AUTO_REFRESH = body.prompt_cache_auto_refresh
    config.save_runtime_settings()
    return {"ok": True, **rt.get_prompt_cache_status()}
