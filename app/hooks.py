"""编排层 Hooks 工厂（app 层组装依赖，core 不 import main）。"""

from __future__ import annotations

from app.bootstrap import get_app_context
from core.orchestration import outline as orchestration_outline
from core.orchestration import review as orchestration_review
from core.orchestration.finalize import FinalizeHooks


def _ensure_context():
    try:
        return get_app_context()
    except RuntimeError:
        from app.bootstrap import init_context

        return init_context()


def build_finalize_hooks() -> FinalizeHooks:
    import main

    ctx = _ensure_context()
    rd = ctx.reviewer_deps
    return FinalizeHooks(
        maintain_deps=ctx.maintain_deps,
        llm=rd.llm,
        resolve_chapter=ctx.resolve_chapter,
        short_story_skip=ctx.short_story_skip,
        chapters_text_for_scope=main.get_chapters_text_for_scope,
        load_check_snapshot=lambda num, body: ctx.store.load_snapshot(
            num, for_purpose="check", chapter_body=body
        ),
        read_summaries_recent=lambda: main.read_text(main.SUMMARIES_RECENT_FILE),
        run_pacing_check=lambda: orchestration_review.run_pacing_check(ctx),
        run_outline=lambda: orchestration_outline.run_outline(ctx, next_count=3),
        quality_log_entry=ctx.quality_log_entry,
    )
