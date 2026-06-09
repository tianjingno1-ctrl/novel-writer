"""运行时配置 HTTP 路由。"""

from __future__ import annotations

from typing import Any

import infra.config as config
from app import runtime as rt
from core import model_routing
from fastapi import APIRouter, HTTPException
from infra.providers import reset_client
from pydantic import BaseModel

router = APIRouter(tags=["config"])


class ContextConfig(BaseModel):
    turns: int | None = None
    mode: str | None = None
    free_chat_turns: int | None = None


class ProviderSwitch(BaseModel):
    provider: str


class NodeModelsPatch(BaseModel):
    node_models: dict[str, dict[str, Any] | None] | None = None


@router.get("/api/config/models")
def get_models_config() -> dict:
    return {
        "ok": True,
        "nodes": model_routing.list_configurable_nodes(),
        "providers": model_routing.list_provider_catalog(),
        "node_models": dict(model_routing.NODE_MODEL_OVERRIDES),
    }


@router.put("/api/config/models")
def set_models_config(body: NodeModelsPatch) -> dict:
    try:
        merged = model_routing.apply_node_models_patch(body.node_models or {})
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    config.save_runtime_settings()
    for entry in merged.values():
        pid = entry.get("provider")
        if pid:
            reset_client(pid)
    return {
        "ok": True,
        "node_models": merged,
        "nodes": model_routing.list_configurable_nodes(),
    }


@router.put("/api/config/context")
def set_context(cfg: ContextConfig) -> dict:
    if cfg.turns is not None:
        if cfg.turns < 0 or cfg.turns > 100:
            raise HTTPException(400, "写书轮数范围 0-100")
        config.CHAT_CONTEXT_TURNS = cfg.turns
    if cfg.free_chat_turns is not None:
        if cfg.free_chat_turns < 0 or cfg.free_chat_turns > 100:
            raise HTTPException(400, "自由聊轮数范围 0-100")
        config.FREE_CHAT_CONTEXT_TURNS = cfg.free_chat_turns
    if cfg.mode is not None:
        if cfg.mode not in ("turns", "summaries", "beats", "codex"):
            raise HTTPException(400, "mode 必须是 turns/summaries/beats/codex")
        config.CONTEXT_MODE = cfg.mode
    config.save_runtime_settings()
    return {
        "ok": True,
        "context_turns": config.CHAT_CONTEXT_TURNS,
        "free_chat_context_turns": config.FREE_CHAT_CONTEXT_TURNS,
        "context_mode": config.CONTEXT_MODE,
    }


@router.put("/api/config/provider")
def set_provider(body: ProviderSwitch) -> dict:
    if body.provider not in config.PROVIDERS:
        raise HTTPException(400, f"未知提供商: {body.provider}")
    config.PROVIDER = body.provider
    config.save_runtime_settings()
    from infra.providers import reset_client

    reset_client(body.provider)
    return {"ok": True, **rt.get_app_status()}
