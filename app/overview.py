"""书架概览 / 统计（路由依赖适配，api/routes/stats 零 import main）。"""

from __future__ import annotations

import threading

import novel_data
from app import paths as _paths
from core import stats as stats_core

_stats_cache: dict | None = None
_stats_sig: tuple | None = None
_stats_lock = threading.Lock()


def cached_stats() -> dict:
    """GET /api/stats（带 mtime 签名缓存）。"""
    global _stats_cache, _stats_sig

    import main

    with _stats_lock:
        chapters = main.list_chapters()
        sig = stats_core.build_stats_sig(
            chapters,
            summaries_file=_paths.resolved("SUMMARIES_FILE"),
            cost_log=_paths.resolved("COST_LOG"),
            cost_log_jsonl=_paths.resolved("COST_LOG_JSONL"),
        )
        if _stats_cache is not None and _stats_sig == sig:
            return _stats_cache
        result = stats_core.compute_stats(
            chapters,
            read_text=main.read_text,
            count_summaries=main.count_summaries,
            get_total_cost=main.get_total_cost,
        )
        _stats_cache = result
        _stats_sig = sig
        return result


def bookshelf_overview() -> dict:
    """GET /api/overview。"""
    import book_context
    import main

    chapters = main.list_chapters()
    stats = stats_core.compute_stats(
        chapters,
        read_text=main.read_text,
        count_summaries=main.count_summaries,
        get_total_cost=main.get_total_cost,
    )
    latest = main.get_latest_chapter()
    current = latest[0] if latest else None
    payload = novel_data.build_bookshelf_overview(
        chapters=chapters,
        chapter_stats=stats.get("chapters", []),
        summaries_text=main.get_summaries_combined(),
        world_text=main.read_text(_paths.resolved("WORLD_FILE")),
        current_chapter=current,
    )
    payload["library"] = book_context.list_books()
    payload["book_type"] = book_context.get_book_type()
    return payload
