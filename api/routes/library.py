"""书库 HTTP 路由。"""

from __future__ import annotations

from app.batch_state import is_batch_job_running
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.deps import require_ok
from app.bootstrap import rebuild_context

router = APIRouter(tags=["library"])


class CreateBookBody(BaseModel):
    title: str = "未命名小说"
    type: str = "novel"
    platform: str = "tomato"
    world_label: str = ""
    tagline: str = ""


class SwitchBookBody(BaseModel):
    book_id: str


def _refresh_app_context(request: Request) -> None:
    """切书 / 新建书后重建 AppContext（单用户；TODO: 多用户 per-session）。"""
    request.app.state.ctx = rebuild_context()


@router.get("/api/library")
def library_list() -> dict:
    import book_context

    return book_context.list_books()


@router.get("/api/library/active")
def library_active() -> dict:
    import book_context

    return book_context.get_active_book_meta()


@router.post("/api/library/books")
def library_create_book(body: CreateBookBody, request: Request) -> dict:
    import book_context

    result = book_context.create_book(
        title=body.title,
        book_type=body.type,
        platform=body.platform,
        world_label=body.world_label,
        tagline=body.tagline,
    )
    if result.get("ok"):
        _refresh_app_context(request)
    return require_ok(result, "新建书籍失败")


@router.post("/api/library/switch")
def library_switch(body: SwitchBookBody, request: Request) -> dict:
    import book_context

    if is_batch_job_running():
        raise HTTPException(409, "批量任务进行中，请完成后再切换书籍")
    result = book_context.switch_book(body.book_id.strip())
    if result.get("ok"):
        _refresh_app_context(request)
    return require_ok(result, "切换书籍失败")
