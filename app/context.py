"""运行时依赖容器（替代散落 main 的 *_deps 工厂）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.book_store import BookStore
    from core.deps import GeneratorDeps, MaintainDeps, ReviewerDeps


@dataclass
class AppContext:
    """CLI / API 共享的依赖入口（进程级实例；切书后 rebuild_context 重建）。"""

    store: BookStore
    reviewer_deps: ReviewerDeps
    maintain_deps: MaintainDeps
    generator_deps: GeneratorDeps
    resolve_chapter: Callable[[int | None], tuple[int, str] | dict]
    quality_log_entry: Callable[..., str | None]
    short_story_skip: Callable[[str], dict | None]
