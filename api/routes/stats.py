"""书架概览 / 统计 HTTP 路由。"""

from __future__ import annotations

import threading

import main as core
import novel_data
from fastapi import APIRouter

from core import stats as stats_core

router = APIRouter(tags=["stats"])

_stats_cache: dict | None = None
_stats_sig: tuple | None = None
_stats_lock = threading.Lock()


def _cached_stats() -> dict:
    global _stats_cache, _stats_sig

    with _stats_lock:
        chapters = core.list_chapters()
        sig = stats_core.build_stats_sig(
            chapters,
            summaries_file=core.SUMMARIES_FILE,
            cost_log=core.COST_LOG,
            cost_log_jsonl=core.COST_LOG_JSONL,
        )
        if _stats_cache is not None and _stats_sig == sig:
            return _stats_cache
        result = stats_core.compute_stats(
            chapters,
            read_text=core.read_text,
            count_summaries=core.count_summaries,
            get_total_cost=core.get_total_cost,
        )
        _stats_cache = result
        _stats_sig = sig
        return result


@router.get("/api/overview")
def bookshelf_overview() -> dict:
    import book_context

    chapters = core.list_chapters()
    stats = stats_core.compute_stats(
        chapters,
        read_text=core.read_text,
        count_summaries=core.count_summaries,
        get_total_cost=core.get_total_cost,
    )
    latest = core.get_latest_chapter()
    current = latest[0] if latest else None
    payload = novel_data.build_bookshelf_overview(
        chapters=chapters,
        chapter_stats=stats.get("chapters", []),
        summaries_text=core.get_summaries_combined(),
        world_text=core.read_text(core.WORLD_FILE),
        current_chapter=current,
    )
    payload["library"] = book_context.list_books()
    payload["book_type"] = book_context.get_book_type()
    return payload


@router.get("/api/stats")
def stats() -> dict:
    return _cached_stats()
