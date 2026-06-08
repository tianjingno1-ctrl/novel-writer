"""变更历史 HTTP 路由。"""

from __future__ import annotations

import change_history
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import require_ok

router = APIRouter(tags=["history"])


class HistoryRevertRequest(BaseModel):
    entry_id: str
    chapter_num: int | None = None


@router.get("/api/history")
def history_list(file_key: str | None = None, limit: int = 200) -> dict:
    lim = max(1, min(500, limit))
    return change_history.list_history(file_key=file_key, limit=lim)


@router.get("/api/history/baseline")
def history_baseline() -> dict:
    return {"ok": True, **change_history.get_baseline_info()}


@router.get("/api/history/{entry_id}")
def history_entry(entry_id: str) -> dict:
    result = change_history.get_entry(entry_id)
    if not result.get("ok"):
        raise HTTPException(404, result.get("error", "记录不存在"))
    return result


@router.post("/api/history/revert")
def history_revert(body: HistoryRevertRequest) -> dict:
    return require_ok(
        change_history.revert_entry(
            body.entry_id, chapter_num=body.chapter_num
        ),
        "撤销失败",
    )


@router.post("/api/history/baseline")
def history_baseline_refresh() -> dict:
    manifest = change_history.ensure_baseline_snapshot(force=True)
    return {"ok": True, "baseline": manifest}
