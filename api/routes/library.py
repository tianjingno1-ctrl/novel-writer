"""书库 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
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


class UpdateBookBody(BaseModel):
    title: str | None = None
    type: str | None = None
    platform: str | None = None
    world_label: str | None = None
    tagline: str | None = None


class BatchBookIdsBody(BaseModel):
    book_ids: list[str]


def _refresh_app_context(request: Request) -> None:
    """切书 / 新建书后重建 AppContext（单用户；TODO: 多用户 per-session）。"""
    request.app.state.ctx = rebuild_context()


@router.get("/api/library")
def library_list() -> dict:
    from core.data import book_context

    return book_context.list_books()


@router.get("/api/library/active")
def library_active() -> dict:
    from core.data import book_context

    return book_context.get_active_book_meta()


@router.post("/api/library/books")
def library_create_book(body: CreateBookBody, request: Request) -> dict:
    from core.data import book_context

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
    from core.data import book_context

    result = book_context.switch_book(body.book_id.strip())
    if result.get("ok"):
        _refresh_app_context(request)
    return require_ok(result, "切换书籍失败")


@router.patch("/api/library/books/{book_id}")
def library_update_book(book_id: str, body: UpdateBookBody) -> dict:
    from core.data import book_context

    result = book_context.update_book(
        book_id.strip(),
        title=body.title,
        book_type=body.type,
        platform=body.platform,
        world_label=body.world_label,
        tagline=body.tagline,
    )
    return require_ok(result, "更新书籍失败")


@router.post("/api/library/batch/trash")
def library_trash_books(body: BatchBookIdsBody, request: Request) -> dict:
    from core.data import book_context

    result = book_context.trash_books(body.book_ids)
    if result.get("ok") and result.get("context_refreshed"):
        _refresh_app_context(request)
    return require_ok(result, "批量移入垃圾站失败")


@router.get("/api/library/trash")
def library_trash_list() -> dict:
    from core.data import book_context

    return book_context.list_trash()


@router.post("/api/library/books/{book_id}/trash")
def library_trash_book(book_id: str, request: Request) -> dict:
    from core.data import book_context

    result = book_context.trash_book(book_id.strip())
    if result.get("ok") and result.get("context_refreshed"):
        _refresh_app_context(request)
    return require_ok(result, "移入垃圾站失败")


@router.post("/api/library/batch/purge")
def library_purge_books(body: BatchBookIdsBody) -> dict:
    from core.data import book_context

    result = book_context.purge_books(body.book_ids)
    return require_ok(result, "批量永久删除失败")


@router.post("/api/library/trash/{book_id}/restore")
def library_restore_book(book_id: str) -> dict:
    from core.data import book_context

    result = book_context.restore_book(book_id.strip())
    return require_ok(result, "恢复书籍失败")


@router.delete("/api/library/trash/{book_id}")
def library_purge_book(book_id: str) -> dict:
    from core.data import book_context

    result = book_context.purge_book(book_id.strip())
    return require_ok(result, "永久删除失败")


@router.delete("/api/library/trash")
def library_purge_all_trash() -> dict:
    from core.data import book_context

    result = book_context.purge_all_trash()
    return require_ok(result, "清空垃圾站失败")
