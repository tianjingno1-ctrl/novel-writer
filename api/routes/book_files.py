"""书籍设定 md 文件 HTTP 路由（E8）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from api.deps import get_app_context, require_ok
from app.context import AppContext
from core.orchestration import book_files as orchestration_book_files

router = APIRouter(tags=["book-files"])

MAX_CONTENT_BYTES = orchestration_book_files.MAX_FILE_BYTES


class BookFileBody(BaseModel):
    content: str = ""

    @field_validator("content")
    @classmethod
    def check_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > MAX_CONTENT_BYTES:
            mb = MAX_CONTENT_BYTES // 1024 // 1024
            raise ValueError(f"内容过大（上限 {mb}MB）")
        return v


@router.get("/api/book/files")
def list_book_files(ctx: AppContext = Depends(get_app_context)) -> dict:
    return orchestration_book_files.list_book_files(ctx)


@router.get("/api/book/files/{key}")
def get_book_file(key: str, ctx: AppContext = Depends(get_app_context)) -> dict:
    result = orchestration_book_files.get_book_file(ctx, key)
    if not result.get("ok"):
        raise HTTPException(404, result.get("error", "文件不存在"))
    return result


@router.put("/api/book/files/{key}")
def put_book_file(
    key: str,
    body: BookFileBody,
    ctx: AppContext = Depends(get_app_context),
) -> dict:
    return require_ok(
        orchestration_book_files.put_book_file(ctx, key, body.content),
        "保存失败",
    )
