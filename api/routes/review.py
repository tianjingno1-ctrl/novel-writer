"""拆文 HTTP 路由（Canonical A 段）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_app_context, require_ok
from app.context import AppContext
from core.orchestration import review as orchestration_review

router = APIRouter(tags=["review"])


class DeconstructRequest(BaseModel):
    text: str
    source_label: str = ""
    include_book_context: bool = True


@router.post("/api/deconstruct")
def deconstruct_reference(
    body: DeconstructRequest,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    return require_ok(
        orchestration_review.run_deconstruct(
            body.text,
            ctx,
            source_label=body.source_label.strip(),
            include_book_context=body.include_book_context,
        ),
        "参考拆文失败",
    )
