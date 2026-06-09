"""写书对话 HTTP 路由。"""

from __future__ import annotations

import config
from app import writing_svc as ws
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from api.deps import require_ok
from api.routes.review import ChapterQualityRequest

router = APIRouter(tags=["writing"])

MAX_API_TEXT_CHARS = 50_000


def _check_api_text(v: str) -> str:
    if len(v) > MAX_API_TEXT_CHARS:
        raise ValueError(f"文本过长（上限 {MAX_API_TEXT_CHARS} 字符）")
    return v


class ChatRequest(BaseModel):
    instruction: str = ""
    scene_beat: str = ""
    scene_id: str = ""
    chapter_num: int | None = None

    _validate_instruction = field_validator("instruction")(_check_api_text)
    _validate_scene_beat = field_validator("scene_beat")(_check_api_text)


class ChatPromptItem(BaseModel):
    id: str
    title: str
    content: str = ""


class ChatPromptsBody(BaseModel):
    prompts: list[ChatPromptItem]


@router.get("/api/chat/history")
def chat_history() -> dict:
    return {
        "messages": ws.get_chat_history(),
        "appended_indices": ws.get_appended_indices(),
        "context_turns": config.CHAT_CONTEXT_TURNS,
        "context_mode": config.CONTEXT_MODE,
    }


@router.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    ws.touch_user_active()
    return require_ok(
        ws.writing_chat(
            req.instruction, req.scene_beat, req.scene_id, req.chapter_num
        ),
        "写书对话失败",
    )


@router.post("/api/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    ws.touch_user_active()

    def generate():
        for event in ws.writing_chat_stream(
            req.instruction, req.scene_beat, req.scene_id, req.chapter_num
        ):
            yield f"data: {event}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/chat/clear")
def chat_clear() -> dict:
    ws.clear_chat_session()
    return {"ok": True}


@router.put("/api/chat/write-chapter")
def set_write_chapter(body: ChapterQualityRequest) -> dict:
    if not body.chapter_num or body.chapter_num <= 0:
        raise HTTPException(400, "chapter_num 无效")
    return require_ok(
        ws.set_write_chapter_num(body.chapter_num),
        "设置写作目标章失败",
    )


@router.post("/api/chat/restore")
def chat_restore() -> dict:
    return require_ok(ws.restore_chat_session(), "恢复失败")


@router.get("/api/chat/prompts")
def get_chat_prompts() -> dict:
    return ws.load_chat_prompts()


@router.put("/api/chat/prompts")
def put_chat_prompts(body: ChatPromptsBody) -> dict:
    prompts = [p.model_dump() for p in body.prompts]
    return ws.save_chat_prompts(prompts)
