"""产品 Schema 编排（无前端）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from core import chapter_precheck
from core import criteria_resolver
from core import deconstruct_store
from core import diagnosis_store
from core import plan_product
from core import profiles
from core import project_lifecycle
from core import rerun_scope
from core import taste

if TYPE_CHECKING:
    from app.context import AppContext


def _book_dir(ctx: AppContext) -> Path:
    return ctx.store.paths.data_dir


def _book_id(ctx: AppContext) -> str:
    from core.data import book_context

    return book_context.get_context().book_id


def get_plan_product(ctx: AppContext) -> dict:
    plan = plan_product.load_plan()
    return {
        "ok": True,
        "meta": plan_product.get_meta(plan),
        "review_criteria": plan_product.get_review_criteria(plan),
        "chapter_statuses": plan_product.list_chapter_statuses(plan),
        "resolved_criteria": criteria_resolver.resolve_review_criteria(
            plan, book_dir=_book_dir(ctx),
        ),
    }


def put_plan_meta(ctx: AppContext, meta: dict[str, Any]) -> dict:
    saved = plan_product.set_plan_meta(meta)
    return {"ok": True, "meta": saved}


def put_review_criteria(ctx: AppContext, fields: dict[str, Any]) -> dict:
    if "hard_rules" in fields:
        fields["hard_rules"] = plan_product.validate_rule_refs(fields.get("hard_rules"))
    if "soft_rules" in fields:
        fields["soft_rules"] = plan_product.validate_rule_refs(fields.get("soft_rules"))
    saved = plan_product.set_review_criteria(fields)
    plan = plan_product.load_plan()
    return {
        "ok": True,
        "review_criteria": saved,
        "resolved": criteria_resolver.resolve_review_criteria(plan, book_dir=_book_dir(ctx)),
    }


def init_review_criteria_from_profile(ctx: AppContext, profile_id: str = "") -> dict:
    project = project_lifecycle.load_project(_book_dir(ctx))
    pid = profile_id.strip() or profiles.resolve_default_profile_id(
        book_type=str(project.get("type") or "short"),
        platform=str(project.get("platform") or "tomato"),
    )
    criteria = profiles.build_criteria_from_profile(pid)
    saved = plan_product.set_review_criteria(criteria)
    return {"ok": True, "profile_id": pid, "review_criteria": saved}


def set_chapter_status(ctx: AppContext, chapter_num: int, status: str) -> dict:
    row = plan_product.set_chapter_status(chapter_num, status)
    return {"ok": True, **row}


def run_precheck(ctx: AppContext, chapter_num: int, content: str = "") -> dict:
    if not content.strip():
        from core import chapter_io

        content = chapter_io.read_chapter_content(chapter_num)
    plan = plan_product.load_plan()
    project = project_lifecycle.load_project(_book_dir(ctx))
    result = chapter_precheck.run_precheck(
        chapter_num=chapter_num,
        content=content,
        plan=plan,
        project=project,
    )
    return {"ok": True, **result}


def run_reader_preview(ctx: AppContext, chapter_num: int, content: str = "") -> dict:
    from core import reader_retention
    from core import taste as taste_store

    if not content.strip():
        from core import chapter_io

        content = chapter_io.read_chapter_content(chapter_num)
    book_dir = _book_dir(ctx)
    taste_doc = taste_store.load_book_taste(book_dir)
    reader_pattern = taste_doc.get("reader_pattern") if isinstance(taste_doc, dict) else {}
    analysis = reader_retention.analyze_reader_perspective(
        content,
        chapter_num=chapter_num,
        reader_pattern=reader_pattern if isinstance(reader_pattern, dict) else None,
    )
    reader_retention.save_retention(book_dir, chapter_num, analysis)
    return {"ok": True, "reader_preview": analysis}


def run_compliance_preview(
    ctx: AppContext,
    *,
    submission_target: str = "text_editor",
) -> dict:
    from core import chapter_io
    from core import compliance

    plan = plan_product.load_plan()
    project = project_lifecycle.load_project(_book_dir(ctx))
    platform = compliance.resolve_platform_slug(
        plan_meta=plan_product.get_meta(plan),
        project=project,
    )
    chapters: list[tuple[int, str]] = []
    for key in sorted((plan.get("chapters") or {}).keys(), key=lambda k: int(k)):
        try:
            num = int(key)
        except (TypeError, ValueError):
            continue
        body = chapter_io.read_chapter_content(num).strip()
        if body:
            chapters.append((num, body))
    scan = compliance.scan_chapters_compliance(chapters, platform=platform)
    scan["submission_target"] = submission_target
    return scan


def rerun_impact_preview(
    ctx: AppContext,
    *,
    scope: str,
    from_chapter_num: int = 0,
    current_chapter_num: int = 0,
) -> dict:
    plan = plan_product.load_plan()
    preview = rerun_scope.build_impact_preview(
        plan,
        scope=scope,
        from_chapter_num=from_chapter_num,
        current_chapter_num=current_chapter_num,
    )
    return {
        "ok": True,
        "impact_preview": preview,
        "locked_chapters": plan_product.locked_chapter_nums(plan),
        "mutable_for_plan": rerun_scope.chapters_mutable_for_plan_rerun(plan),
    }


def execute_rerun(
    ctx: AppContext,
    *,
    scope: str,
    from_chapter_num: int = 0,
    current_chapter_num: int = 0,
    reset_plan_fields: bool = False,
    clear_chapter_drafts: bool = True,
    auto_plan_llm: bool = True,
    plan_context_note: str = "",
) -> dict:
    from core.orchestration import rerun_pipeline

    return rerun_pipeline.run_pipeline(
        ctx,
        scope=scope,
        from_chapter_num=from_chapter_num,
        current_chapter_num=current_chapter_num,
        reset_plan_fields=reset_plan_fields,
        clear_chapter_drafts=clear_chapter_drafts,
        auto_plan_llm=auto_plan_llm,
        plan_context_note=plan_context_note,
    )


def get_work_queue(ctx: AppContext) -> dict:
    from core.orchestration import rerun_pipeline
    from core import reader_retention

    book_dir = _book_dir(ctx)
    plan = plan_product.load_plan()
    wq = rerun_pipeline.build_work_queue(plan, book_dir=book_dir)
    approved = [
        n for n, st in plan_product.list_chapter_statuses(plan).items() if st == "approved"
    ]
    rhythm = reader_retention.check_rhythm_warning(book_dir, approved, window=3)
    return {"ok": True, **wq, "rhythm_warning": rhythm}


def get_chapter_summary(ctx: AppContext, chapter_num: int) -> dict:
    from core import chapter_summary

    doc = chapter_summary.load_summary(_book_dir(ctx), chapter_num)
    if not doc:
        return {"ok": False, "error": "概述不存在"}
    return {"ok": True, "summary": doc}


def list_flow_steps() -> dict:
    from core.orchestration import flow_runner

    return {"ok": True, **flow_runner.list_flow_steps()}


def run_flow(
    ctx: AppContext,
    *,
    mode: str = "continue",
    chapter_num: int = 0,
    from_step: str = "",
    stop_after: str = "",
    scope: str = "",
    from_chapter_num: int = 0,
    current_chapter_num: int = 0,
    reset_plan_fields: bool = False,
    clear_chapter_drafts: bool = True,
    auto_plan_llm: bool = True,
    plan_context_note: str = "",
    write_instruction: str = "",
    auto_adopt_write: bool = False,
    judgment: dict[str, Any] | None = None,
    auto_confirm_summary: bool = False,
) -> dict:
    from core.orchestration import flow_runner

    return flow_runner.run_flow(
        ctx,
        mode=mode,
        chapter_num=chapter_num,
        from_step=from_step,
        stop_after=stop_after,
        scope=scope,
        from_chapter_num=from_chapter_num,
        current_chapter_num=current_chapter_num,
        reset_plan_fields=reset_plan_fields,
        clear_chapter_drafts=clear_chapter_drafts,
        auto_plan_llm=auto_plan_llm,
        plan_context_note=plan_context_note,
        write_instruction=write_instruction,
        auto_adopt_write=auto_adopt_write,
        judgment=judgment,
        auto_confirm_summary=auto_confirm_summary,
    )


def push_highlight(
    ctx: AppContext,
    *,
    chapter_num: int,
    text: str,
    annotation: str = "",
    tags: list[str] | None = None,
) -> dict:
    result = taste.push_highlight_to_taste(
        book_id=_book_id(ctx),
        chapter_num=chapter_num,
        text=text,
        annotation=annotation,
        tags=tags,
    )
    return {"ok": True, **result}


def list_deconstructs(ctx: AppContext, limit: int = 50) -> dict:
    rows = deconstruct_store.list_deconstructs(book_id=_book_id(ctx), limit=limit)
    return {"ok": True, "deconstructs": rows}


def elevate_deconstruct(ctx: AppContext, deconstruct_id: str) -> dict:
    result = deconstruct_store.elevate_to_taste(
        deconstruct_id,
        book_dir=_book_dir(ctx),
    )
    return result


def list_diagnoses(ctx: AppContext, limit: int = 30) -> dict:
    rows = diagnosis_store.list_diagnoses(_book_dir(ctx), limit=limit)
    return {"ok": True, "diagnoses": rows}


def decide_diagnosis(
    ctx: AppContext,
    diagnosis_id: str,
    *,
    accepted: bool,
    rerun_scope_name: str = "none",
    from_chapter_num: int = 0,
    apply_override: bool = True,
    execute_rerun: bool = False,
) -> dict:
    plan = plan_product.load_plan()
    preview = ""
    if rerun_scope_name != "none":
        preview = rerun_scope.build_impact_preview(
            plan,
            scope=rerun_scope_name,
            from_chapter_num=from_chapter_num,
        )
    result = diagnosis_store.decide(
        _book_dir(ctx),
        diagnosis_id,
        accepted=accepted,
        rerun_scope=rerun_scope_name,
        rerun_from_chapter_num=from_chapter_num,
        impact_preview=preview,
        apply_override=apply_override,
    )
    if (
        result.get("ok")
        and accepted
        and execute_rerun
        and rerun_scope_name not in ("none", "")
    ):
        exec_r = execute_rerun(
            ctx,
            scope=rerun_scope_name,
            from_chapter_num=from_chapter_num,
            current_chapter_num=from_chapter_num,
            auto_plan_llm=True,
            plan_context_note=str(
                (result.get("diagnosis") or {}).get("analysis") or ""
            )[:500],
        )
        result["rerun_pipeline"] = exec_r
        if not exec_r.get("ok"):
            result["ok"] = False
            result["error"] = exec_r.get("error", "重跑流水线失败")
    return result


def confirm_chapter_summary(
    ctx: AppContext,
    chapter_num: int,
    *,
    push_highlights: bool = True,
) -> dict:
    from core import chapter_summary

    return chapter_summary.confirm_summary(
        _book_dir(ctx),
        chapter_num,
        push_highlights=push_highlights,
    )


def get_lifecycle(ctx: AppContext) -> dict:
    lc = project_lifecycle.get_lifecycle(_book_dir(ctx))
    return {"ok": True, "lifecycle": lc}


def put_lifecycle(ctx: AppContext, fields: dict[str, Any]) -> dict:
    lc = project_lifecycle.update_lifecycle(_book_dir(ctx), fields)
    return {"ok": True, "lifecycle": lc}


def list_profiles() -> dict:
    return {"ok": True, "profiles": profiles.list_profiles()}


def get_profile(profile_id: str) -> dict:
    doc = profiles.load_profile(profile_id)
    if not doc:
        return {"ok": False, "error": "profile 不存在"}
    return {"ok": True, "profile": doc}
