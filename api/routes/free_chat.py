"""自由聊 HTTP 路由。"""

from __future__ import annotations

import main as core
from app import free_chat as svc
from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from api.deps import require_ok

router = APIRouter(tags=["free-chat"])

MAX_API_TEXT_CHARS = 50_000


def _check_api_text(v: str) -> str:
    if len(v) > MAX_API_TEXT_CHARS:
        raise ValueError(f"文本过长（上限 {MAX_API_TEXT_CHARS} 字符）")
    return v


class FreeChatRequest(BaseModel):
    content: str
    provider: str | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        return _check_api_text(v)


class FreeChatThreadCreate(BaseModel):
    title: str = ""

    @field_validator("title")
    @classmethod
    def check_title(cls, v: str) -> str:
        return v.strip()


class FreeChatThreadRename(BaseModel):
    title: str

    _validate_title = field_validator("title")(_check_api_text)


class FreeChatThreadSwitch(BaseModel):
    thread_id: str


class ProviderSwitch(BaseModel):
    provider: str


@router.get("/api/free-chat/history")
def free_chat_history() -> dict:
    return svc.get_free_chat_state()


@router.put("/api/free-chat/provider")
def set_free_chat_provider(body: ProviderSwitch) -> dict:
    require_ok(svc.set_free_chat_provider(body.provider), "切换失败")
    from providers import reset_client

    reset_client(body.provider)
    return {"ok": True, **core.get_app_status()}


@router.post("/api/free-chat")
def free_chat_send(body: FreeChatRequest) -> dict:
    core.touch_user_active()
    return require_ok(
        svc.free_chat(body.content, provider=body.provider),
        "自由聊失败",
    )


@router.post("/api/free-chat/clear")
def free_chat_clear() -> dict:
    return svc.clear_free_chat()


@router.delete("/api/free-chat/messages/{index}")
def free_chat_delete_message(index: int) -> dict:
    return require_ok(
        svc.delete_free_chat_message(index),
        "删除消息失败",
    )


@router.post("/api/free-chat/threads")
def free_chat_thread_create(body: FreeChatThreadCreate) -> dict:
    title = body.title or None
    return require_ok(
        svc.create_free_chat_thread(title),
        "创建话题失败",
    )


@router.put("/api/free-chat/threads/{thread_id}")
def free_chat_thread_rename(
    thread_id: str, body: FreeChatThreadRename
) -> dict:
    return require_ok(
        svc.rename_free_chat_thread(thread_id, body.title),
        "重命名失败",
    )


@router.put("/api/free-chat/active-thread")
def free_chat_thread_switch(body: FreeChatThreadSwitch) -> dict:
    return require_ok(
        svc.switch_free_chat_thread(body.thread_id),
        "切换话题失败",
    )


@router.delete("/api/free-chat/threads/{thread_id}")
def free_chat_thread_delete(thread_id: str) -> dict:
    return require_ok(
        svc.delete_free_chat_thread(thread_id),
        "删除话题失败",
    )
