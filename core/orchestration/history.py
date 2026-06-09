"""变更历史编排。"""
from __future__ import annotations

from core.data import change_history


def list_history(*, file_key: str | None = None, limit: int = 200) -> dict:
    lim = max(1, min(500, limit))
    return change_history.list_history(file_key=file_key, limit=lim)


def baseline_info() -> dict:
    return {"ok": True, **change_history.get_baseline_info()}


def get_entry(entry_id: str) -> dict:
    return change_history.get_entry(entry_id)


def revert_entry(entry_id: str, *, chapter_num: int | None = None) -> dict:
    return change_history.revert_entry(entry_id, chapter_num=chapter_num)


def refresh_baseline() -> dict:
    manifest = change_history.ensure_baseline_snapshot(force=True)
    return {"ok": True, "baseline": manifest}
