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


def run_precheck(
    ctx: AppContext,
    chapter_num: int,
    content: str = "",
    *,
    skip_paywall_intent: bool = False,
) -> dict:
    if not content.strip():
        from core import chapter_io

        content = chapter_io.read_chapter_content(chapter_num)
    plan = plan_product.load_plan()
    project = project_lifecycle.load_project(_book_dir(ctx))
    from core import chapter_role_overlay

    skip_codes = (
        chapter_precheck.SKIPPABLE_PRECHECK_CODES
        if skip_paywall_intent
        else frozenset()
    )
    result = chapter_precheck.run_precheck(
        chapter_num=chapter_num,
        content=content,
        plan=plan,
        project=project,
        role_params=chapter_role_overlay.l1b_params(plan, chapter_num),
        skip_issue_codes=skip_codes,
    )
    return {
        "ok": True,
        **result,
        **chapter_role_overlay.review_context_meta(plan, chapter_num),
    }


def run_reader_preview(ctx: AppContext, chapter_num: int, content: str = "") -> dict:
    from core import chapter_role_overlay
    from core import reader_retention
    from core import taste as taste_store

    if not content.strip():
        from core import chapter_io

        content = chapter_io.read_chapter_content(chapter_num)
    book_dir = _book_dir(ctx)
    plan = plan_product.load_plan()
    ctx_meta = chapter_role_overlay.chapter_review_context(plan, chapter_num)
    taste_doc = taste_store.load_book_taste(book_dir)
    reader_pattern = taste_doc.get("reader_pattern") if isinstance(taste_doc, dict) else {}
    analysis = reader_retention.analyze_reader_perspective(
        content,
        chapter_num=chapter_num,
        reader_pattern=reader_pattern if isinstance(reader_pattern, dict) else None,
        drop_risk_thresholds=chapter_role_overlay.l2_reader_thresholds(plan, chapter_num),
        chapter_role=ctx_meta.get("role"),
    )
    llm_analysis = reader_retention.try_llm_reader_review(
        content,
        plan=plan,
        chapter_num=chapter_num,
        base=analysis,
    )
    if llm_analysis:
        analysis = llm_analysis
    reader_retention.save_retention(book_dir, chapter_num, analysis)
    return {
        "ok": True,
        "reader_preview": analysis,
        **chapter_role_overlay.review_context_meta(plan, chapter_num),
    }


def run_editor_preview(ctx: AppContext, chapter_num: int, content: str = "") -> dict:
    """L2 编辑视角：商业编辑式点评（editor_review prompt），非正文复读。"""
    from core import chapter_io
    from core import chapter_role_overlay
    from core import criteria_resolver
    from core import reviewer as quality_reviewer
    from core.orchestration.review import build_reviewer_deps
    from core.schemas.service import ChapterRef, ChapterWork

    if not content.strip():
        content = chapter_io.read_chapter_content(chapter_num)
    body = (content or "").strip()
    if not body:
        return {"ok": False, "error": "章节正文为空"}

    book_dir = _book_dir(ctx)
    plan = plan_product.load_plan()
    work = ChapterWork(ChapterRef(num=chapter_num), body)
    result = quality_reviewer.run_editor_review(work, "current", build_reviewer_deps(ctx))
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "编辑点评失败")}

    resolved = criteria_resolver.resolve_review_criteria(plan, book_dir=book_dir)
    hard = [
        str(row.get("content") or "").strip()
        for row in (resolved.get("hard") or [])
        if isinstance(row, dict) and str(row.get("content") or "").strip()
    ]
    soft = [
        str(row.get("content") or "").strip()
        for row in (resolved.get("soft") or [])
        if isinstance(row, dict) and str(row.get("content") or "").strip()
    ]
    profile_id = str(resolved.get("platform_profile") or "").strip()
    profile_label = profile_id
    if profile_id:
        from core import profiles

        prof = profiles.load_profile(profile_id)
        if prof:
            plat = str(prof.get("platform_label") or prof.get("platform") or "").strip()
            profile_label = f"{plat or profile_id} · 文字编辑" if plat else profile_id

    return {
        "ok": True,
        "editor_preview": {
            "review_text": str(result.get("reply") or "").strip(),
            "log_id": result.get("log_id"),
            "hard_criteria": hard[:8],
            "soft_criteria": soft[:8],
            "platform_profile": profile_label,
        },
        **chapter_role_overlay.review_context_meta(plan, chapter_num),
    }


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


def get_chapter_review(ctx: AppContext, chapter_num: int) -> dict:
    from core import chapter_review

    book_dir = _book_dir(ctx)
    doc = chapter_review.load_review(book_dir, chapter_num)
    rounds = chapter_review.list_rounds(book_dir, chapter_num)
    return {
        "ok": True,
        "chapter_num": chapter_num,
        "review": doc or {"chapter_num": chapter_num, "rounds": []},
        "round_count": len(rounds),
    }


def list_flow_steps() -> dict:
    from core.orchestration import flow_runner

    return {"ok": True, **flow_runner.list_flow_steps()}


def create_attribution_log(
    ctx: AppContext,
    *,
    chapter_num: int,
    source: str = "L5b",
    note: str = "",
) -> dict:
    """为 L4a/L5b 等无审阅记录的归因入口创建 quality log。"""
    from core.orchestration import logs as logs_orch

    src = (source or "L5b").strip()
    tags: list[str] = []
    if src == "L5b":
        tags = ["rhythm_warning", "retention"]
    elif src == "L4a":
        tags = ["review_gap"]
    msg = (note or f"{src} 主动 Prompt 归因").strip()
    log_id = ctx.quality_log_entry(
        "flow_attribution",
        chapter_num,
        msg,
        summary=f"{src} · 第{chapter_num}章"[:120],
        extra={
            "outcome": "rejected",
            "issue_tags": tags,
            "attribution_source": src,
        },
    )
    if not log_id:
        return {"ok": False, "error": "创建归因记录失败"}
    judged = logs_orch.record_quality_judgment(
        log_id,
        outcome="rejected",
        issue_tags=tags,
        note=msg,
        ctx=ctx,
        push_highlight_on_pass=False,
    )
    if not judged.get("ok"):
        return judged
    return {"ok": True, "log_id": log_id, "source": src}


def get_diagnosis(ctx: AppContext, diagnosis_id: str) -> dict:
    from core import diagnosis_store

    doc = diagnosis_store.load(_book_dir(ctx), diagnosis_id.strip())
    if not doc:
        return {"ok": False, "error": "归因记录不存在"}
    return {"ok": True, "diagnosis": doc}


def run_rhythm_check(ctx: AppContext, *, chapter_num: int, window: int = 3) -> dict:
    from core import chapter_role_overlay
    from core import reader_retention

    book_dir = _book_dir(ctx)
    plan = plan_product.load_plan()
    nums = sorted(
        int(k) for k in (plan.get("chapters") or {}).keys() if str(k).isdigit()
    )
    recent = [n for n in nums if n <= chapter_num][-window:]
    if chapter_num not in recent:
        recent = (recent + [chapter_num])[-window:]
    rhythm = reader_retention.check_rhythm_warning(book_dir, recent, window=window)
    meta = chapter_role_overlay.review_context_meta(plan, chapter_num)
    return {"ok": True, "rhythm_warning": rhythm, "chapters_checked": recent, **meta}


def push_highlight(
    ctx: AppContext,
    *,
    chapter_num: int,
    text: str,
    annotation: str = "",
    tags: list[str] | None = None,
    skip_conflict_check: bool = False,
) -> dict:
    from core import highlight_conflict

    book_dir = _book_dir(ctx)
    conflict_report = highlight_conflict.check_highlight_conflicts(
        book_id=_book_id(ctx),
        text=text,
        annotation=annotation,
        book_dir=book_dir,
    )
    if conflict_report.get("has_conflict") and not skip_conflict_check:
        return {
            "ok": False,
            "error": "亮点与口味库存在冲突",
            "conflicts": conflict_report.get("conflicts") or [],
        }
    result = taste.push_highlight_to_taste(
        book_id=_book_id(ctx),
        chapter_num=chapter_num,
        text=text,
        annotation=annotation,
        tags=tags,
    )
    return {"ok": True, **result, "conflicts": conflict_report.get("conflicts") or []}


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
    run_rerun_pipeline: bool = False,
    apply_author_profile: bool = False,
    author_profile_book_id: str = "",
) -> dict:
    if apply_author_profile:
        from core import author_profile

        book_dir = _book_dir(ctx)
        book_taste = taste.load_book_taste(book_dir)
        merged = author_profile.apply_to_book_taste(
            book_taste,
            inherit_all=True,
            source_book_id=author_profile_book_id.strip() or None,
        )
        taste.save_book_taste(book_dir, merged)

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
        and run_rerun_pipeline
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
