"""审阅编排：拆文 + 定稿链路透传（无 Substrate HTTP）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core import reviewer as quality_reviewer
from core.deps import ReviewerDeps
from core.orchestration._chapter_work import chapter_work_from_num

if TYPE_CHECKING:
    from app.context import AppContext


def build_reviewer_deps(ctx: AppContext) -> ReviewerDeps:
    return ctx.reviewer_deps


def run_pacing_check(ctx: AppContext) -> dict:
    return quality_reviewer.run_pacing_check(build_reviewer_deps(ctx))


def run_deconstruct(
    source_text: str,
    ctx: AppContext,
    *,
    source_label: str = "",
    include_book_context: bool = True,
) -> dict:
    from core.data import novel_data
    from core.orchestration import taste as orchestration_taste
    from core import taste as taste_store

    store = ctx.store
    p = store.paths
    book_title = ""
    world_excerpt = ""
    style_excerpt = ""
    if include_book_context:
        project = novel_data.get_project_meta()
        book_title = (project.get("title") or "").strip()
        world_excerpt = store.read(p.world_file).strip()[:5000]
        style_excerpt = store.read(p.style_file).strip()[:3000]
    result = quality_reviewer.run_deconstruct(
        source_text,
        ctx.reviewer_deps,
        source_label=source_label,
        include_book_context=include_book_context,
        book_title=book_title,
        world_excerpt=world_excerpt,
        style_excerpt=style_excerpt,
        taste_excerpt=orchestration_taste.context_block(ctx),
    )
    if result.get("ok"):
        from core import deconstruct_store
        from core import project_lifecycle
        from core.data import book_context

        book_id = book_context.get_context().book_id
        project = novel_data.get_project_meta()
        decon = deconstruct_store.create_from_deconstruct_reply(
            book_id=book_id,
            quality_log_id=str(result.get("log_id") or ""),
            reply=str(result.get("reply") or ""),
            source_title=(source_label or project.get("title") or "").strip(),
            source_platform=str(project.get("platform") or "tomato"),
        )
        taste_store.record_deconstruct_event(
            book_id=book_id,
            quality_log_id=str(result.get("log_id") or ""),
            reply=str(result.get("reply") or ""),
            source_label=source_label,
        )
        result["deconstruct_id"] = decon.get("id")
        result["patterns"] = taste_store.extract_deconstruct_patterns(
            str(result.get("reply") or ""),
        )
        project_lifecycle.add_deconstruct_ref(
            ctx.store.paths.data_dir,
            str(decon.get("id") or ""),
        )
    return result
