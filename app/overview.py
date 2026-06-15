"""书架统计（GET /api/stats）。"""

from __future__ import annotations

import threading

from infra import file_utils as bio
from infra import billing as _cost
from app import paths as _paths
from app import writing_ctx as _wctx
from app.chapters_api import list_chapters
from core import stats as stats_core

_stats_cache: dict | None = None
_stats_sig: tuple | None = None
_stats_lock = threading.Lock()


def cached_stats() -> dict:
    """GET /api/stats（带 mtime 签名缓存）。"""
    global _stats_cache, _stats_sig

    with _stats_lock:
        chapters = list_chapters()
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
            read_text=bio.read_text,
            count_summaries=_wctx.count_summaries,
            get_total_cost=_cost.get_total_cost,
        )
        _stats_cache = result
        _stats_sig = sig
        return result
