"""Codex 设定 HTTP 路由（全局文件 + 条目 CRUD）。"""

from __future__ import annotations

import main as core
import novel_data
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from api.deps import require_ok

router = APIRouter(tags=["codex"])

MAX_CONTENT_BYTES = 2 * 1024 * 1024
MAX_API_TEXT_CHARS = 50_000
VALID_CODEX_NAMES = frozenset(core.CODEX_FILES.keys())


def _check_file_content(v: str) -> str:
    if len(v.encode("utf-8")) > MAX_CONTENT_BYTES:
        mb = MAX_CONTENT_BYTES // 1024 // 1024
        raise ValueError(f"内容过大（上限 {mb}MB）")
    return v


def _check_api_text(v: str) -> str:
    if len(v) > MAX_API_TEXT_CHARS:
        raise ValueError(f"文本过长（上限 {MAX_API_TEXT_CHARS} 字符）")
    return v


class CodexContentBody(BaseModel):
    content: str
    chapter_num: int | None = None

    @field_validator("content")
    @classmethod
    def check_size(cls, v: str) -> str:
        return _check_file_content(v)


class CodexCreate(BaseModel):
    name: str
    content: str = ""

    _validate_name = field_validator("name")(_check_api_text)

    @field_validator("content")
    @classmethod
    def check_content(cls, v: str) -> str:
        return _check_file_content(v)


class CodexActive(BaseModel):
    active: list[str]


@router.get("/api/codex")
def codex_list() -> dict:
    return {"files": list(core.CODEX_FILES.keys())}


@router.get("/api/codex/{name}")
def get_codex(name: str) -> dict:
    if name not in VALID_CODEX_NAMES:
        raise HTTPException(400, "非法设定文件名")
    data = core.get_codex(name)
    if data is None:
        raise HTTPException(404, f"未知设定: {name}")
    return data


@router.put("/api/codex/{name}")
def put_codex(name: str, body: CodexContentBody) -> dict:
    if name not in VALID_CODEX_NAMES:
        raise HTTPException(400, "非法设定文件名")
    return require_ok(
        core.save_codex(name, body.content, chapter_num=body.chapter_num),
        "保存失败",
    )


@router.get("/api/codex-entries")
def codex_entries() -> dict:
    return {
        "entries": novel_data.list_codex_entries(),
        "active": novel_data.get_active_codex_ids(),
    }


@router.post("/api/codex-entries")
def codex_entry_create(body: CodexCreate) -> dict:
    return require_ok(
        novel_data.create_codex_entry(body.name, body.content),
        "创建失败",
    )


@router.put("/api/codex-entries/active")
def codex_set_active(body: CodexActive) -> dict:
    return novel_data.set_active_codex_ids(body.active)


@router.get("/api/codex-entries/{entry_id}")
def codex_entry_get(entry_id: str) -> dict:
    entry = novel_data.get_codex_entry(entry_id)
    if entry is None:
        raise HTTPException(404, "条目不存在")
    return entry


@router.put("/api/codex-entries/{entry_id}")
def codex_entry_save(entry_id: str, body: CodexContentBody) -> dict:
    return require_ok(
        novel_data.save_codex_entry(entry_id, body.content),
        "保存失败",
    )


@router.delete("/api/codex-entries/{entry_id}")
def codex_entry_delete(entry_id: str) -> dict:
    return require_ok(
        novel_data.delete_codex_entry(entry_id),
        "删除失败",
    )
