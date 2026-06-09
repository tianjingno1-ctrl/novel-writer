"""Prompt 节点 HTTP 路由。"""
from __future__ import annotations

from app.bootstrap import get_app_context
from core.orchestration import prompt_config as orchestration_prompts
from core.orchestration import prompt_diagnose as orchestration_prompt_diagnose
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

router = APIRouter(tags=["prompts"])

MAX_PROMPT_CHARS = 80_000


class PromptOverrideBody(BaseModel):
    system: str | None = None
    clear: bool = False

    @field_validator("system")
    @classmethod
    def check_system(cls, v: str | None) -> str | None:
        if v is not None and len(v) > MAX_PROMPT_CHARS:
            raise ValueError(f"prompt 过长（上限 {MAX_PROMPT_CHARS} 字符）")
        return v


def _ctx(request: Request):
    return request.app.state.ctx or get_app_context()


@router.get("/api/prompts/nodes")
def list_prompt_nodes(request: Request) -> dict:
    return orchestration_prompts.list_nodes(_ctx(request))


@router.get("/api/prompts/nodes/{node_id}")
def get_prompt_node(node_id: str, request: Request) -> dict:
    result = orchestration_prompts.get_node(_ctx(request), node_id)
    if not result.get("ok"):
        raise HTTPException(404, result.get("error", "节点不存在"))
    return result


@router.put("/api/prompts/nodes/{node_id}")
def put_prompt_node(node_id: str, body: PromptOverrideBody, request: Request) -> dict:
    result = orchestration_prompts.put_node_override(
        _ctx(request),
        node_id,
        system=body.system,
        clear=body.clear,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "更新失败"))
    return result


class DiagnoseBody(BaseModel):
    quality_log_id: str = ""
    heuristic_only: bool = False


class PatchPreviewBody(BaseModel):
    node_id: str
    suggested_patch: str
    patch_mode: str = "append"
    save: bool = False

    @field_validator("suggested_patch")
    @classmethod
    def check_patch(cls, v: str) -> str:
        if len(v) > MAX_PROMPT_CHARS:
            raise ValueError(f"patch 过长（上限 {MAX_PROMPT_CHARS} 字符）")
        return v


@router.get("/api/prompts/flow")
def prompts_workflow_map() -> dict:
    return orchestration_prompt_diagnose.get_workflow_map()


@router.post("/api/prompts/diagnose")
def prompts_diagnose(body: DiagnoseBody, request: Request) -> dict:
    result = orchestration_prompt_diagnose.run_llm_diagnose(
        _ctx(request),
        quality_log_id=body.quality_log_id,
        use_heuristic_only=body.heuristic_only,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "诊断失败"))
    return result


@router.post("/api/prompts/diagnose/heuristic")
def prompts_diagnose_heuristic(body: DiagnoseBody, request: Request) -> dict:
    result = orchestration_prompt_diagnose.run_heuristic(
        _ctx(request),
        quality_log_id=body.quality_log_id,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "诊断失败"))
    return result


@router.post("/api/prompts/diagnose/preview")
def prompts_patch_preview(body: PatchPreviewBody, request: Request) -> dict:
    if body.save:
        result = orchestration_prompt_diagnose.apply_patch(
            _ctx(request),
            body.node_id,
            suggested_patch=body.suggested_patch,
            patch_mode=body.patch_mode,
            save=True,
        )
    else:
        result = orchestration_prompt_diagnose.preview_patch(
            _ctx(request),
            body.node_id,
            body.suggested_patch,
            patch_mode=body.patch_mode,
        )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "操作失败"))
    return result
