"""创作工坊 HTTP 路由。"""

from __future__ import annotations

import time

from infra import state as app_state
from core.data import book_context
from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator, model_validator

from api.deps import require_ok
from app.bootstrap import rebuild_context
from app.context import AppContext
from core.orchestration import workshop as orchestration_workshop

router = APIRouter(tags=["workshop"])

MAX_API_TEXT_CHARS = 50_000


class WorkshopMessage(BaseModel):
    role: str
    content: str


class WorkshopChatRequest(BaseModel):
    book_id: str = "default"
    module: str = "world"
    messages: list[WorkshopMessage] = []
    current_draft: str = ""

    @field_validator("module")
    @classmethod
    def check_module(cls, v: str) -> str:
        m = (v or "").strip().lower()
        if m not in ("world", "characters", "style"):
            raise ValueError("module 须为 world / characters / style")
        return m

    @field_validator("current_draft")
    @classmethod
    def check_draft(cls, v: str) -> str:
        if len(v) > MAX_API_TEXT_CHARS:
            raise ValueError(f"current_draft 过长（>{MAX_API_TEXT_CHARS} 字）")
        return v


class WorkshopBeatItem(BaseModel):
    chapter: int = 1
    title: str = ""
    beat: str = ""


class WorkshopSaveRequest(BaseModel):
    book_id: str = "default"
    module: str = "world"
    content: str = ""
    world: str = ""
    characters: str = ""
    beats: list[WorkshopBeatItem] = []

    @field_validator("module")
    @classmethod
    def check_module(cls, v: str) -> str:
        m = (v or "").strip().lower()
        if m not in ("world", "characters", "style"):
            raise ValueError("module 须为 world / characters / style")
        return m

    @field_validator("content", "world", "characters")
    @classmethod
    def check_text_fields(cls, v: str) -> str:
        if len(v) > MAX_API_TEXT_CHARS:
            raise ValueError(f"文本过长（>{MAX_API_TEXT_CHARS} 字）")
        return v

    @model_validator(mode="after")
    def check_nonempty(self) -> "WorkshopSaveRequest":
        has_beats = bool(self.beats)
        has_text = any(
            (s or "").strip()
            for s in (self.content, self.world, self.characters)
        )
        if not has_beats and not has_text:
            raise ValueError("至少提供 world、characters、content 或 beats 之一")
        return self


class WriteTextRequest(BaseModel):
    book_id: str = "default"
    key: str
    content: str


def _touch_user_active() -> None:
    app_state.state.last_user_active = time.time()


def _refresh_app_context(request: Request) -> None:
    request.app.state.ctx = rebuild_context()


def _maybe_switch_book(book_id: str, request: Request) -> dict | None:
    if book_id and book_id != book_context.get_context().book_id:
        sw = book_context.switch_book(book_id)
        if not sw.get("ok"):
            return {"ok": False, "error": f"切换书籍失败: {book_id}"}
        _refresh_app_context(request)
    return None


@router.post("/api/workshop/chat")
def workshop_chat(
    body: WorkshopChatRequest,
    request: Request,
) -> dict:
    _touch_user_active()
    sw_err = _maybe_switch_book(body.book_id, request)
    if sw_err:
        return sw_err
    ctx: AppContext = request.app.state.ctx
    msgs = [{"role": m.role, "content": m.content} for m in body.messages]
    return require_ok(
        orchestration_workshop.run_workshop_chat(
            ctx,
            body.module,
            msgs,
            current_draft=body.current_draft,
        ),
        "创作工坊对话失败",
    )


@router.post("/api/workshop/save")
def workshop_save(
    body: WorkshopSaveRequest,
    request: Request,
) -> dict:
    _touch_user_active()
    sw_err = _maybe_switch_book(body.book_id, request)
    if sw_err:
        return sw_err
    ctx: AppContext = request.app.state.ctx
    beats = [b.model_dump() for b in body.beats]
    return require_ok(
        orchestration_workshop.run_workshop_save(
            ctx,
            body.module,
            body.content,
            world=body.world,
            characters=body.characters,
            beats=beats,
        ),
        "写入档案失败",
    )


@router.post("/api/write_text")
def write_text_archive(
    body: WriteTextRequest,
    request: Request,
) -> dict:
    _touch_user_active()
    sw_err = _maybe_switch_book(body.book_id, request)
    if sw_err:
        return sw_err
    ctx: AppContext = request.app.state.ctx
    return require_ok(
        orchestration_workshop.run_write_text(ctx, body.key, body.content),
        "写入档案失败",
    )
