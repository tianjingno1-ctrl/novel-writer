"""稿件管理 HTTP 路由。"""
from __future__ import annotations

from typing import Any

from app.bootstrap import get_app_context
from core.orchestration import manuscript as orchestration_manuscript
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["manuscripts"])


class CreateManuscriptBody(BaseModel):
    title: str = ""


class ManuscriptPatchBody(BaseModel):
    title: str | None = None
    notes: str | None = None
    language: str | None = None
    market_tags: list[str] | None = None
    ip_tags: list[str] | None = None
    state: str | None = None
    submission: dict[str, Any] | None = None
    revision: dict[str, Any] | None = None


def _ctx(request: Request):
    return request.app.state.ctx or get_app_context()


def _err(result: dict, default: str = "操作失败") -> None:
    if result.get("ok", True):
        return
    status = 404 if "不存在" in str(result.get("error", "")) else 400
    raise HTTPException(status, result.get("error", default))


@router.get("/api/manuscripts")
def list_manuscripts(book_id: str | None = None) -> dict:
    return orchestration_manuscript.list_all(book_id=book_id)


@router.post("/api/manuscripts")
def create_manuscript(body: CreateManuscriptBody, request: Request) -> dict:
    result = orchestration_manuscript.create_from_active_book(
        _ctx(request), title=body.title,
    )
    _err(result, "创建稿件失败")
    return result


@router.get("/api/manuscripts/{manuscript_id}")
def get_manuscript(manuscript_id: str) -> dict:
    result = orchestration_manuscript.get_one(manuscript_id)
    _err(result, "稿件不存在")
    return result


@router.patch("/api/manuscripts/{manuscript_id}")
def patch_manuscript(
    manuscript_id: str, body: ManuscriptPatchBody, request: Request,
) -> dict:
    fields = body.model_dump(exclude_unset=True)
    result = orchestration_manuscript.patch(_ctx(request), manuscript_id, fields)
    _err(result, "更新稿件失败")
    return result
