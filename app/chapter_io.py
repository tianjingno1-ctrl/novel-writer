"""P4-D shim：注入依赖后 re-export core.chapter_io。"""
from __future__ import annotations

from app import factories, paths
from core import chapter_io as _core

_core.configure(
    store_provider=factories.book_store,
    path_resolver=paths.resolved,
)

from core.chapter_io import *  # noqa: F401,F403
