"""世界批次 / batch job 编排。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import batch_remediate
import batch_world
from app import batch_state
from core import chapters as chapter_text
from pipeline.checkpoint import (
    JOB_KIND_WORLD_GENERATE,
    find_resumable_job,
    job_path,
    list_jobs,
    load_job,
)
from summarizer import build_cross_chapter_check_user_message

if TYPE_CHECKING:
    from app.context import AppContext


def _char_context_for_check(ctx: AppContext) -> str:
    return ctx.store.load_snapshot(for_purpose="check").char_context_for_check


def build_world_batch_review_deps(ctx: AppContext) -> dict:
    llm = ctx.maintain_deps.llm
    p = ctx.store.paths
    return {
        "read_chapter": ctx.store.read_chapter,
        "read_text": ctx.store.read,
        "get_char_context_for_check": lambda: _char_context_for_check(ctx),
        "build_cached_system": llm.build_cached_system,
        "summaries_for_scope_fn": ctx.store.summaries_for_scope,
        "cross_chapter_user_message_fn": build_cross_chapter_check_user_message,
        "world_file": p.world_file,
        "characters_file": p.characters_file,
        "plot_locked_file": p.plot_threads_locked_file,
        "plot_active_file": p.plot_threads_active_file,
    }


def _sync_chapter_title_from_file(ctx: AppContext, chapter_num: int) -> str | None:
    import novel_data

    text = ctx.store.read_chapter(chapter_num)
    if not text.strip():
        return None
    title, _ = chapter_text.split_chapter_markdown_header(text)
    if not title:
        title, _ = chapter_text.extract_chapter_title_from_reply(text)
    if not title:
        return None
    clean = title.strip().strip("《》「」\"' ")
    if not clean or clean in {
        f"第{chapter_num}章",
        f"第{chapter_text.chapter_cn(chapter_num)}章",
    }:
        return None
    if len(clean) > 48:
        clean = clean[:48].rstrip()
    novel_data.ensure_chapter_plan(chapter_num, title=clean)
    novel_data.update_chapter_title(chapter_num, clean)
    return clean


def get_world_batch_status(ctx: AppContext) -> dict:
    return batch_world.get_world_batch_status(read_chapter=ctx.store.read_chapter)


def preview_world_batch_review(
    ctx: AppContext,
    *,
    chapter_from: int | None = None,
    chapter_to: int | None = None,
) -> dict:
    plan = batch_world.build_world_batch_review_plan(
        **build_world_batch_review_deps(ctx),
        chapter_from=chapter_from,
        chapter_to=chapter_to,
    )
    if not plan.get("ok"):
        return plan
    preview = batch_world.format_review_plan_markdown(plan)
    public = {k: v for k, v in plan.items() if k != "_calls_internal"}
    public["preview"] = preview
    return public


def list_batch_jobs(
    ctx: AppContext,
    *,
    kind: str | None = None,
    limit: int = 20,
) -> dict:
    jobs = list_jobs(ctx.store.paths.data_dir, kind=kind, limit=limit)
    return {"ok": True, "jobs": jobs}


def find_resumable_generate_job(ctx: AppContext) -> dict:
    job = find_resumable_job(ctx.store.paths.data_dir, JOB_KIND_WORLD_GENERATE)
    if not job:
        return {"ok": True, "job": None}
    return {"ok": True, "job": job}


def get_batch_job(ctx: AppContext, job_id: str) -> dict:
    data_dir = ctx.store.paths.data_dir
    job = load_job(data_dir, job_id)
    if not job:
        return {"ok": False, "error": "任务不存在"}
    root = job_path(data_dir, job_id)
    report_path = root / "report.md"
    report = job.get("report") or ""
    if not report and report_path.exists():
        report = report_path.read_text(encoding="utf-8")
    return {"ok": True, "job": job, "report": report}


def accept_batch_job(ctx: AppContext, job_id: str) -> dict:
    return batch_remediate.accept_job(ctx.store.paths.data_dir, job_id)


def revert_batch_job_chapter(
    ctx: AppContext,
    job_id: str,
    chapter_num: int,
) -> dict:
    def write_chapter(num: int, text: str) -> None:
        ctx.store.write_chapter(num, text, append=False)

    return batch_remediate.revert_chapter_from_job(
        ctx.store.paths.data_dir,
        job_id,
        chapter_num,
        write_chapter=write_chapter,
        sync_title=lambda n: _sync_chapter_title_from_file(ctx, n),
    )


def is_running() -> bool:
    return batch_state.is_batch_job_running()


def build_remediate_deps(ctx: AppContext) -> dict:
    from core import generator as chapter_generator
    from core.orchestration import archive_sync as orchestration_archive

    llm = ctx.maintain_deps.llm
    p = ctx.store.paths

    def write_chapter(num: int, text: str) -> None:
        ctx.store.write_chapter(num, text, append=False)

    return {
        "data_dir": p.data_dir,
        "read_chapter": ctx.store.read_chapter,
        "read_text": ctx.store.read,
        "get_char_context_for_check": lambda: _char_context_for_check(ctx),
        "build_cached_system": llm.build_cached_system,
        "call_api": llm.call_api,
        "get_last_call_info": llm.get_last_call_info,
        "remediate_chapter": lambda *a, **kw: chapter_generator.remediate_chapter(
            *a, deps=ctx.generator_deps, **kw
        ),
        "bulk_archive_sync": lambda nums: orchestration_archive.run_bulk_archive_sync(
            nums, ctx
        ),
        "write_chapter": write_chapter,
        "sync_title": lambda n: _sync_chapter_title_from_file(ctx, n),
        "quality_log_entry": ctx.quality_log_entry,
        "set_batch_job_running": batch_state.set_batch_job_running,
        "world_file": p.world_file,
        "characters_file": p.characters_file,
        "char_dynamic_file": p.char_dynamic_file,
        "summaries_recent_file": p.summaries_recent_file,
        "plot_locked_file": p.plot_threads_locked_file,
        "plot_active_file": p.plot_threads_active_file,
    }


def run_world_batch_generate(ctx: AppContext, **kw) -> dict:
    skip = ctx.short_story_skip("世界批量生成")
    if skip:
        return skip
    if batch_state.is_batch_job_running():
        return {"ok": False, "error": "已有批次任务正在运行，请稍后再试"}

    import batch_generate
    from core import generator as chapter_generator

    return batch_generate.run_world_batch_generate(
        data_dir=ctx.store.paths.data_dir,
        read_chapter=ctx.store.read_chapter,
        generate_chapter=lambda *a, **kw2: chapter_generator.generate_chapter(
            *a, deps=ctx.generator_deps, **kw2
        ),
        set_batch_job_running=batch_state.set_batch_job_running,
        quality_log_entry=ctx.quality_log_entry,
        **kw,
    )


def run_world_remediate(ctx: AppContext, **kw) -> dict:
    if batch_state.is_batch_job_running():
        return {"ok": False, "error": "已有世界闭环任务正在运行"}

    import batch_remediate as batch_remediate_mod

    return batch_remediate_mod.run_world_remediate(
        **build_remediate_deps(ctx),
        **kw,
    )


def run_world_batch_review(ctx: AppContext, **kw) -> dict:
    llm = ctx.maintain_deps.llm

    return batch_world.run_world_batch_review(
        **build_world_batch_review_deps(ctx),
        call_api=llm.call_api,
        get_last_call_info=llm.get_last_call_info,
        quality_log_entry=ctx.quality_log_entry,
        **kw,
    )


def run_world_batch_finalize(ctx: AppContext, **kw) -> dict:
    skip = ctx.short_story_skip("世界定稿")
    if skip:
        return skip

    from core.orchestration import archive_sync as orchestration_archive

    result = batch_world.run_world_batch_finalize(
        read_chapter=ctx.store.read_chapter,
        finalize_chapter_fn=lambda num, **kwargs: orchestration_archive.run_archive_sync(
            num, ctx
        ),
        run_pacing_on_last=False,
        **kw,
    )
    if result.get("reply"):
        w_to = (result.get("finalized_chapters") or [0])[-1]
        log_id = ctx.quality_log_entry(
            "batch_world_finalize",
            w_to,
            result["reply"],
            summary=(
                f"档案同步 · {result.get('label', '')} · "
                f"{result.get('ok_count', 0)}章"
            ),
            persisted=bool(result.get("ok_count")),
            persisted_detail=f"成功 {result.get('ok_count', 0)} 章",
            extra={
                "chapter_from": result.get("chapter_from"),
                "chapter_to": result.get("chapter_to"),
                "errors": result.get("errors"),
                "total_cost_usd": result.get("total_cost_usd"),
            },
        )
        result["log_id"] = log_id
    return result
