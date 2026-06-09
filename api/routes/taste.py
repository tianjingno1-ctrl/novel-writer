"""口味库 HTTP 路由。"""
from __future__ import annotations

from typing import Any

from app.bootstrap import get_app_context
from core.orchestration import taste as orchestration_taste
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["taste"])


class TastePreferencesBody(BaseModel):
    preferences: dict[str, Any] | None = None


class BookTasteBody(BaseModel):
    inherit_global: bool | None = None
    notes: str | None = None
    preferences: dict[str, Any] | None = None


class TasteEventBody(BaseModel):
    source: str = "manual"
    outcome: str = ""
    issue_tags: list[str] | None = None
    note: str = ""
    patterns: dict[str, Any] | None = None


class ImportDeconstructBody(BaseModel):
    quality_log_id: str
    merge_global: bool = True


class ApplyAuthorProfileBody(BaseModel):
    inherit_all: bool = True
    rule_ids: list[str] | None = None


class ReaderPatternBody(BaseModel):
    good_emotions: list[str] | None = None
    emotion_nodes: list[str] | None = None


def _ctx(request: Request):
    return request.app.state.ctx or get_app_context()


@router.get("/api/taste/global")
def taste_get_global() -> dict:
    return orchestration_taste.get_global()


@router.put("/api/taste/global")
def taste_put_global(body: TastePreferencesBody) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "请提供 preferences")
    return orchestration_taste.put_global(fields)


@router.get("/api/taste/book")
def taste_get_book(request: Request) -> dict:
    return orchestration_taste.get_book(_ctx(request))


@router.put("/api/taste/book")
def taste_put_book(body: BookTasteBody, request: Request) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "无更新字段")
    return orchestration_taste.put_book(_ctx(request), fields)


@router.get("/api/taste/events")
def taste_list_events(
    book_id: str | None = None,
    source: str | None = None,
    limit: int = 80,
) -> dict:
    return orchestration_taste.list_events(book_id=book_id, source=source, limit=limit)


@router.post("/api/taste/events")
def taste_post_event(body: TasteEventBody, request: Request) -> dict:
    return orchestration_taste.post_event(
        _ctx(request),
        source=body.source,
        outcome=body.outcome,
        issue_tags=body.issue_tags,
        note=body.note,
        patterns=body.patterns,
    )


@router.get("/api/taste/summary")
def taste_summary(request: Request) -> dict:
    return orchestration_taste.get_summary(_ctx(request))


@router.get("/api/taste/context")
def taste_context_preview(request: Request, max_chars: int = 3500) -> dict:
    block = orchestration_taste.context_block(_ctx(request), max_chars=max_chars)
    return {"ok": True, "context_block": block}


@router.post("/api/taste/import-deconstruct")
def taste_import_deconstruct(body: ImportDeconstructBody, request: Request) -> dict:
    result = orchestration_taste.import_deconstruct(
        _ctx(request),
        body.quality_log_id.strip(),
        merge_global=body.merge_global,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "导入失败"))
    return result


@router.get("/api/taste/author-profile")
def taste_get_author_profile() -> dict:
    return orchestration_taste.get_author_profile()


@router.post("/api/taste/author-profile/extract")
def taste_extract_author_profile(request: Request) -> dict:
    return orchestration_taste.extract_author_profile(_ctx(request))


@router.post("/api/taste/author-profile/apply")
def taste_apply_author_profile(
    body: ApplyAuthorProfileBody, request: Request,
) -> dict:
    return orchestration_taste.apply_author_profile(
        _ctx(request),
        inherit_all=body.inherit_all,
        rule_ids=body.rule_ids,
    )


@router.put("/api/taste/book/reader-pattern")
def taste_put_reader_pattern(body: ReaderPatternBody, request: Request) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "无更新字段")
    return orchestration_taste.put_reader_pattern(_ctx(request), fields)
