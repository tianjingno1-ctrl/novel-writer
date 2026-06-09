"""AppContext hook 与工厂（bootstrap 组装入口）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app import paths as _paths
from core.book_store import BookPathsView, BookStore
from core.deps import GeneratorDeps, LlmHooks, MaintainDeps, QualityHooks, ReviewerDeps
from summarizer import WRITING_INSTRUCTION

if TYPE_CHECKING:
    from core.book_store import BookStore as BookStoreType


def short_story_archive_skip(feature: str) -> dict | None:
    import book_context

    if book_context.is_short_book():
        return {
            "ok": True,
            "skipped": True,
            "reason": f"短篇模式跳过{feature}",
        }
    return None


def quality_log_entry(
    kind: str,
    chapter_num: int,
    reply: str,
    *,
    summary: str = "",
    persisted: bool = False,
    persisted_detail: str = "",
    extra: dict | None = None,
) -> str:
    import quality_log

    return quality_log.append_entry(
        kind,
        chapter_num,
        reply,
        summary=summary,
        persisted=persisted,
        persisted_detail=persisted_detail,
        extra=extra,
    )


def resolve_chapter_num(chapter_num: int | None) -> tuple[int, str] | dict:
    from app import writing_ctx as _wctx
    from app_state import state

    if chapter_num and chapter_num > 0:
        import app.chapter_io as chapter_io

        content = chapter_io.read_chapter_content(chapter_num)
        if not content.strip():
            return {"ok": False, "error": f"第{chapter_num}章内容为空"}
        return chapter_num, content
    if state.write_chapter_num > 0:
        import app.chapter_io as chapter_io

        content = chapter_io.read_chapter_content(state.write_chapter_num)
        if content.strip():
            return state.write_chapter_num, content
    latest = _wctx.get_latest_chapter()
    if latest is None:
        return {"ok": False, "error": "没有找到章节文件"}
    num, _, content = latest
    if not content.strip():
        return {"ok": False, "error": f"第{num}章内容为空"}
    return num, content


def book_paths_view() -> BookPathsView:
    """当前书路径视图（与 apply_paths_to_modules 同步；测试可 patch main.*_FILE）。"""
    return BookPathsView(
        data_dir=_paths.resolved("DATA_DIR"),
        chapters_dir=_paths.resolved("CHAPTERS_DIR"),
        summaries_recent_file=_paths.resolved("SUMMARIES_RECENT_FILE"),
        summaries_archive_file=_paths.resolved("SUMMARIES_ARCHIVE_FILE"),
        summaries_file=_paths.resolved("SUMMARIES_FILE"),
        char_static_file=_paths.resolved("CHAR_STATIC_FILE"),
        char_dynamic_file=_paths.resolved("CHAR_DYNAMIC_FILE"),
        plot_threads_locked_file=_paths.resolved("PLOT_THREADS_LOCKED_FILE"),
        plot_threads_active_file=_paths.resolved("PLOT_THREADS_ACTIVE_FILE"),
        plot_threads_file=_paths.resolved("PLOT_THREADS_FILE"),
        world_file=_paths.resolved("WORLD_FILE"),
        style_file=_paths.resolved("STYLE_FILE"),
        characters_file=_paths.resolved("CHARACTERS_FILE"),
        char_current_file=_paths.resolved("CHAR_CURRENT_FILE"),
        outline_latest_file=_paths.resolved("OUTLINE_LATEST_FILE"),
    )


def book_store() -> BookStore:
    """当前书存储入口（路径由 main 全局注入 BookStore，core 不 import main）。"""
    import book_context
    from app import book_io as bio
    from app import writing_session as _wsess

    try:
        ctx = book_context.get_context()
    except RuntimeError:
        ctx = None
    return BookStore(
        book_paths_view(),
        read_text=bio.read_text,
        write_text=bio.write_text,
        session_chapter_num=_wsess._session_chapter_num,
        book_context=ctx,
    )


def invalidate_chapter_injection(chapter_num: int | None = None) -> None:
    """章节文件变更或需重新注入时，清除「已含章节正文」标记。"""
    from app_state import state

    if chapter_num is None or chapter_num <= 0:
        state.session_includes_chapter = False
        return
    if state.last_injected_chapter_num == chapter_num:
        state.session_includes_chapter = False


def apply_chapter_title(chapter_num: int, title: str | None) -> str | None:
    """将标题同步到 plan.json（并确保章节规划存在）。"""
    import novel_data
    from core import chapters as chapter_text

    if not title:
        return None
    clean = title.strip().strip("《》「」\"' ")
    if not clean or clean in {f"第{chapter_num}章", f"第{chapter_text.chapter_cn(chapter_num)}章"}:
        return None
    if len(clean) > 48:
        clean = clean[:48].rstrip()
    novel_data.ensure_chapter_plan(chapter_num, title=clean)
    novel_data.update_chapter_title(chapter_num, clean)
    return clean


def _llm_hooks() -> LlmHooks:
    import main

    return LlmHooks(
        build_cached_system=main.build_cached_system,
        call_api=main.call_api,
        get_last_call_info=main.get_last_call_info,
    )


def _quality_hooks() -> QualityHooks:
    return QualityHooks(
        log_entry=quality_log_entry,
        short_story_skip=short_story_archive_skip,
    )


def generator_deps(store: BookStoreType | None = None) -> GeneratorDeps:
    st = store if store is not None else book_store()
    return GeneratorDeps(
        llm=_llm_hooks(),
        store=st,
        writing_instruction=WRITING_INSTRUCTION,
        invalidate_injection=invalidate_chapter_injection,
        apply_title=apply_chapter_title,
    )


def reviewer_deps(store: BookStoreType | None = None) -> ReviewerDeps:
    st = store if store is not None else book_store()
    return ReviewerDeps(
        llm=_llm_hooks(),
        quality=_quality_hooks(),
        store=st,
    )


def maintain_deps(store: BookStoreType | None = None) -> MaintainDeps:
    st = store if store is not None else book_store()
    return MaintainDeps(
        llm=_llm_hooks(),
        quality=_quality_hooks(),
        store=st,
        resolve_chapter=resolve_chapter_num,
    )
