"""跨模块依赖注入容器（避免 pipeline / batch 直接 import main）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.book_store import BookStore


@dataclass
class LlmHooks:
    build_cached_system: Callable
    call_api: Callable
    get_last_call_info: Callable


@dataclass
class QualityHooks:
    log_entry: Callable[..., str | None]
    short_story_skip: Callable[[str], dict | None] | None = None


@dataclass
class GeneratorDeps:
    llm: LlmHooks
    store: BookStore
    writing_instruction: str
    invalidate_injection: Callable[[int | None], None]
    apply_title: Callable[[int, str | None], str | None]


@dataclass
class ReviewerDeps:
    llm: LlmHooks
    quality: QualityHooks
    store: BookStore


@dataclass
class MaintainDeps:
    """章后档案维护（概述 / 观察 / 钉子 / 伏笔 bundle）。"""

    llm: LlmHooks
    quality: QualityHooks
    store: BookStore
    resolve_chapter: Callable[[int | None], tuple[int, str] | dict]
