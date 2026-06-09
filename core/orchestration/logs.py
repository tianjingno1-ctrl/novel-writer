"""日志编排。"""
from __future__ import annotations

from infra.logs import quality as quality_log
from infra.logs import runtime as runtime_log


def list_quality_entries(*, kind: str | None = None, limit: int = 80) -> dict:
    return {"entries": quality_log.list_entries(limit=limit, kind=kind)}


def get_quality_entry(entry_id: str) -> dict | None:
    return quality_log.get_entry(entry_id)


def list_runtime_entries(
    *,
    level: str | None = None,
    category: str | None = None,
    limit: int = 80,
) -> dict:
    return {
        "status": runtime_log.get_status(),
        "entries": runtime_log.list_entries(
            limit=limit, level=level, category=category
        ),
    }


def get_runtime_entry(entry_id: str) -> dict | None:
    return runtime_log.get_entry(entry_id)
