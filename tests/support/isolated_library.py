"""
隔离书库 fixture：store_only_library(tmp_path) 不碰 main 全局。
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from book_context import BookContext
    from core.book_store import BookStore

TEST_BOOK_ID = "test-book"


def _seed_book_dir(book_dir: Path) -> None:
    """在 book_dir 下建 BookContext 期望的扁平书目录结构。"""
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "chapters").mkdir(exist_ok=True)
    (book_dir / "backups").mkdir(exist_ok=True)
    (book_dir / "codex" / "entries").mkdir(parents=True, exist_ok=True)

    for name in (
        "world.md",
        "characters.md",
        "char_static.md",
        "char_dynamic.md",
        "summaries.md",
        "summaries_recent.md",
        "summaries_archive.md",
        "plot_threads_locked.md",
        "plot_threads_active.md",
    ):
        (book_dir / name).write_text("", encoding="utf-8")

    (book_dir / "plan.json").write_text(
        json.dumps({"chapters": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (book_dir / "project.json").write_text(
        json.dumps({"title": "test", "author": "test"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (book_dir / "codex" / "active.json").write_text(
        '{"active": []}',
        encoding="utf-8",
    )


def _test_read_text(path: Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def _test_write_text(
    path: Path,
    content: str,
    *,
    append: bool = False,
    history_source: str = "write",
    chapter_num: int | None = None,
    **kwargs: object,
) -> bool:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if append:
        existing = p.read_text(encoding="utf-8") if p.exists() else ""
        new_content = existing + content
    else:
        new_content = content
    if p.exists() and p.read_text(encoding="utf-8") == new_content:
        return False
    p.write_text(new_content, encoding="utf-8")
    return True


@contextmanager
def store_only_library(tmp_path: Path) -> Iterator[tuple["BookContext", "BookStore"]]:
    """
    在 tmp_path 下建完整书目录，构造 BookStore（轻量 hooks），不 apply_paths_to_modules。
    适用于：core.maintain.persist、BookStore 读写、load_snapshot(maintain)
    """
    from book_context import BookContext
    from core.book_store import BookPathsView, BookStore

    book_dir = tmp_path / "library" / "books" / TEST_BOOK_ID
    _seed_book_dir(book_dir)
    ctx = BookContext(TEST_BOOK_ID, book_dir)
    paths = BookPathsView.from_book_context(ctx)
    store = BookStore(
        paths,
        read_text=_test_read_text,
        write_text=_test_write_text,
        book_context=ctx,
    )
    yield ctx, store


def make_persist_deps(store: "BookStore") -> "MaintainDeps":
    """为 core.maintain.persist() 构造最小 MaintainDeps（仅 store 写盘路径）。"""
    from core.deps import LlmHooks, MaintainDeps, QualityHooks

    return MaintainDeps(
        llm=LlmHooks(
            build_cached_system=lambda *a, **k: "",
            call_api=lambda *a, **k: None,
            get_last_call_info=lambda: {},
        ),
        quality=QualityHooks(
            log_entry=lambda *a, **k: None,
            short_story_skip=lambda *a, **k: None,
        ),
        store=store,
        resolve_chapter=lambda n: (n or 1, ""),
    )
