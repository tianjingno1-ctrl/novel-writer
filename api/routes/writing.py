"""写书对话 HTTP 路由。"""

from __future__ import annotations

from core.orchestration import writing as orchestration_writing
from app import writing_svc as ws
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from api.deps import require_ok
from api.routes.maintain import ChapterQualityRequest

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
    regenerate: bool = False

    _validate_instruction = field_validator("instruction")(_check_api_text)
    _validate_scene_beat = field_validator("scene_beat")(_check_api_text)


@router.get("/api/chat/history")
def chat_history() -> dict:
    return orchestration_writing.chat_history()


@router.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    ws.touch_user_active()
    return require_ok(
        orchestration_writing.chat(
            req.instruction,
            scene_beat=req.scene_beat,
            scene_id=req.scene_id,
            chapter_num=req.chapter_num,
            regenerate=req.regenerate,
        ),
        "写书对话失败",
    )


@router.post("/api/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    ws.touch_user_active()

    def generate():
        for event in orchestration_writing.chat_stream(
            req.instruction,
            scene_beat=req.scene_beat,
            scene_id=req.scene_id,
            chapter_num=req.chapter_num,
            regenerate=req.regenerate,
        ):
            yield f"data: {event}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/chat/clear")
def chat_clear() -> dict:
    orchestration_writing.clear_chat()
    return {"ok": True}


@router.put("/api/chat/write-chapter")
def set_write_chapter(body: ChapterQualityRequest) -> dict:
    if not body.chapter_num or body.chapter_num <= 0:
        raise HTTPException(400, "chapter_num 无效")
    return require_ok(
        orchestration_writing.set_write_chapter(body.chapter_num),
        "设置写作目标章失败",
    )


@router.post("/api/chat/restore")
def chat_restore() -> dict:
    return require_ok(orchestration_writing.restore_chat(), "恢复失败")
