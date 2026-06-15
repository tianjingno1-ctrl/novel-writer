"""女频审阅编排：读档、LLM、写回、档案、quality_log。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.data import novel_data
import review_prompts
from core import chapters as chapter_text
from core import criteria_resolver
from core import chapter_precheck
from core import plan_product
from core import reviewer as quality_reviewer
from core.orchestration import archive_sync as orchestration_archive
from core.reviewer import DECONSTRUCT_MAX_CHARS

if TYPE_CHECKING:
    from app.context import AppContext

_FEMALE_REVIEW_MODES = frozenset({"chapter", "outline", "characters"})

import re

_REVIEW_BODY_MARKERS = re.compile(
    r"^#\s*女频审阅|^profile\s*[:：]|^##\s*一、|^##\s*开篇",
    re.IGNORECASE | re.MULTILINE,
)


def _looks_like_chapter_body(body: str) -> bool:
    """采纳改稿时排除误写入的审阅报告。"""
    text = (body or "").strip()
    if len(text) < 40:
        return False
    head = text[:800]
    if _REVIEW_BODY_MARKERS.search(head):
        return False
    if head.count("## ") >= 3 and "读者情绪" in head:
        return False
    return True


def _apply_chapter_title(chapter_num: int, title: str | None) -> str | None:
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


def _format_plan_outline_text() -> str:
    plan = novel_data.load_plan()
    lines: list[str] = []
    for key in sorted(plan.get("chapters", {}), key=lambda x: int(x)):
        ch = plan["chapters"][key]
        num = int(key)
        title = (ch.get("title") or "").strip() or f"第{num}章"
        lines.append(f"## 第{num}章 · {title}")
        for scene in ch.get("scenes") or []:
            st = (scene.get("title") or "").strip()
            beat = (scene.get("beat") or "").strip()
            summary = (scene.get("summary") or "").strip()
            lines.append(f"- 场景：{st}")
            if summary:
                lines.append(f"  概述：{summary}")
            if beat:
                lines.append(f"  Beat：{beat}")
        lines.append("")
    return "\n".join(lines).strip()


def _build_review_body(
    ctx: AppContext,
    *,
    mode: str,
    text: str,
    chapter_num: int | None,
) -> tuple[int, str] | dict:
    body = (text or "").strip()
    num = 0

    if mode == "chapter":
        if body:
            if chapter_num and chapter_num > 0:
                num = chapter_num
        else:
            resolved = ctx.resolve_chapter(chapter_num)
            if isinstance(resolved, dict):
                return resolved
            num, body = resolved
            if not body.strip():
                return {"ok": False, "error": "章节正文为空"}
    elif mode == "outline":
        if not body:
            body = _format_plan_outline_text()
            if not body:
                return {
                    "ok": False,
                    "error": "plan.json 尚无章节/场景，请先规划或粘贴大纲",
                }
    elif mode == "characters":
        if not body:
            store = ctx.store
            p = store.paths
            parts = []
            chars = store.read(p.characters_file).strip()
            static = store.read(p.char_static_file).strip()
            dynamic = store.read(p.char_dynamic_file).strip()
            if chars:
                parts.append(f"## characters.md\n{chars}")
            if static:
                parts.append(f"## char_static.md\n{static}")
            if dynamic:
                parts.append(f"## char_dynamic.md\n{dynamic}")
            body = "\n\n".join(parts)
            if not body:
                return {"ok": False, "error": "人物文件为空，请填写或粘贴设定"}

    if len(body) < 40:
        return {"ok": False, "error": "审阅材料过短"}
    if len(body) > DECONSTRUCT_MAX_CHARS:
        body = body[:DECONSTRUCT_MAX_CHARS] + "\n\n…（后文已截断）"

    return num, body


def _criteria_context_block(ctx: AppContext) -> str:
    plan = novel_data.load_plan()
    resolved = criteria_resolver.resolve_review_criteria(
        plan, book_dir=ctx.store.paths.data_dir,
    )
    lines = ["## 审阅标准（差距分析须逐项对照）", ""]
    if resolved.get("hard"):
        lines.append("**硬性**")
        for row in resolved["hard"]:
            lines.append(f"- [{row.get('ref', '')}] {row.get('content', '')}")
        lines.append("")
    if resolved.get("soft"):
        lines.append("**软性**")
        for row in resolved["soft"]:
            lines.append(f"- [{row.get('ref', '')}] {row.get('content', '')}")
        lines.append("")
    if resolved.get("hard") or resolved.get("soft"):
        from core import review_gaps

        lines.append(review_gaps.criteria_gaps_appendix())
    return "\n".join(lines).strip()


def run_female_fiction_review(
    ctx: AppContext,
    *,
    mode: str = "chapter",
    text: str = "",
    chapter_num: int | None = None,
    profile_id: str | None = None,
    revise: bool = False,
    write_back: bool = False,
    sync_archive: bool = True,
    skip_precheck: bool = False,
    skip_paywall_intent: bool = False,
    revise_note: str = "",
) -> dict:
    if mode not in _FEMALE_REVIEW_MODES:
        return {"ok": False, "error": "mode 必须是 chapter / outline / characters"}
    if write_back and not revise:
        project = novel_data.get_project_meta()
        pid = (profile_id or "").strip() or review_prompts.resolve_profile_id(
            project.get("type"), project.get("platform")
        )
        if not review_prompts.is_rewrite_only_profile(pid):
            return {"ok": False, "error": "写回章节须先开启「审阅并改稿」"}
    if write_back and mode != "chapter":
        return {"ok": False, "error": "写回章节仅支持章节正文模式"}

    built = _build_review_body(ctx, mode=mode, text=text, chapter_num=chapter_num)
    if isinstance(built, dict):
        return built
    num, body = built

    if mode == "chapter" and num > 0 and not skip_precheck:
        project = novel_data.get_project_meta()
        plan = novel_data.load_plan()
        from core import chapter_role_overlay

        skip_codes = (
            chapter_precheck.SKIPPABLE_PRECHECK_CODES
            if skip_paywall_intent
            else frozenset()
        )
        pre = chapter_precheck.run_precheck(
            chapter_num=num,
            content=body,
            plan=plan,
            project=project,
            role_params=chapter_role_overlay.l1b_params(plan, num),
            skip_issue_codes=skip_codes,
        )
        if not pre.get("ok"):
            return {
                "ok": False,
                "error": "机器预检未通过，请先改稿再审阅",
                "precheck": pre,
                "chapter_num": num,
                "should_rewrite": True,
            }

    project = novel_data.get_project_meta()
    book_title = (project.get("title") or "").strip()
    world_excerpt = ctx.store.read(ctx.store.paths.world_file).strip()[:3000]

    active_profile = (profile_id or "").strip() or review_prompts.resolve_profile_id(
        project.get("type"), project.get("platform")
    )
    rewrite_only = review_prompts.is_rewrite_only_profile(active_profile)
    if rewrite_only:
        write_back = False
        sync_archive = False

    profile_meta = review_prompts.active_profile_for_project(project)
    if profile_id:
        profile_meta = {**profile_meta, "rewrite_only": rewrite_only}

    from core.orchestration import taste as orchestration_taste

    taste_block = orchestration_taste.context_block(ctx)
    criteria_block = _criteria_context_block(ctx)
    if criteria_block:
        taste_block = f"{taste_block}\n\n{criteria_block}".strip() if taste_block else criteria_block

    if mode == "chapter" and num > 0:
        from core import chapter_role_overlay

        plan = novel_data.load_plan()
        overlay = chapter_role_overlay.l4_overlay_block(plan, num)
        if overlay:
            taste_block = f"{taste_block}\n\n{overlay}".strip() if taste_block else overlay

    llm_r = quality_reviewer.run_female_fiction_review(
        mode,
        body,
        num,
        ctx.reviewer_deps,
        book_title=book_title,
        world_excerpt=world_excerpt,
        revise=revise,
        rewrite_only=rewrite_only,
        write_back=write_back,
        profile_id=profile_id,
        project=project,
        taste_excerpt=taste_block,
        revise_note=revise_note,
    )
    if not llm_r.get("ok"):
        return llm_r

    revised_text = (llm_r.get("revised_text") or "").strip()
    display_reply = llm_r.get("reply") or ""
    review_text = llm_r.get("review_text") or ""
    written_back = False
    chapter_title = ""
    active_profile = llm_r.get("profile_id") or active_profile
    tag = llm_r.get("tag") or ""
    profile_label = llm_r.get("profile_label") or ""

    if revise and not rewrite_only and not revised_text and not write_back:
        return {
            "ok": False,
            "error": "改稿未生成独立正文（须在审阅后输出 # 改稿正文），请重试",
            "revise": True,
            "reply": display_reply,
            "review_text": review_text or None,
            "chapter_num": num or None,
            "profile_id": active_profile,
            "profile_label": profile_label,
        }

    if write_back and num > 0 and revised_text:
        write_r = chapter_text.write_chapter_from_review_text(
            ctx.store,
            num,
            revised_text,
            apply_title=_apply_chapter_title,
            after_write=ctx.generator_deps.invalidate_injection,
        )
        if write_r.get("ok"):
            written_back = True
            chapter_title = write_r.get("chapter_title") or ""
            try:
                plan_product.set_chapter_status(num, "drafting")
            except ValueError:
                pass

    archive_result: dict | None = None
    archive_synced = False
    if written_back and sync_archive and num > 0:
        archive_result = orchestration_archive.run_archive_sync(num, ctx)
        archive_synced = bool(archive_result.get("ok"))

    pending_accept = bool(
        rewrite_only
        and (revised_text or display_reply).strip()
        and not written_back
    )
    if revise and not rewrite_only:
        pending_accept = bool(revised_text and not written_back)
    from core import prompt_nodes

    review_prompt = prompt_nodes.resolve_node(
        "review.platform",
        book_dir=ctx.store.paths.data_dir,
        project=project,
        include_revise=revise and not rewrite_only,
    )
    log_kind = "female_fiction_revise" if rewrite_only else "female_fiction_review"
    log_body = display_reply if rewrite_only else (review_text if revise else display_reply)
    log_id = ctx.quality_log_entry(
        log_kind,
        num,
        log_body,
        summary=f"{tag} · {profile_label} · {book_title or '未命名'}"[:120],
        persisted=written_back,
        persisted_detail="已写回章节" if written_back else ("待采纳" if pending_accept else ""),
        prompt_node=review_prompt.node_id,
        prompt_hash=review_prompt.prompt_hash,
        prompt_source=review_prompt.prompt_source,
        extra={
            "mode": mode,
            "input_chars": len(body),
            "profile_id": active_profile,
            "profile_label": profile_label,
            "revise": revise,
            "rewrite_only": rewrite_only,
            "write_back": written_back,
            "archive_synced": archive_synced,
            "pending_accept": pending_accept,
        },
    )
    revise_log_id: str | None = None
    if revise and revised_text and not rewrite_only:
        revise_log_id = ctx.quality_log_entry(
            "female_fiction_revise",
            num,
            revised_text,
            summary=f"女频改稿 · 第{num}章 · {profile_label}"[:120],
            persisted=written_back,
            persisted_detail="已写回章节" if written_back else ("待采纳" if pending_accept else ""),
            prompt_node=review_prompt.node_id,
            prompt_hash=review_prompt.prompt_hash,
            prompt_source=review_prompt.prompt_source,
            extra={
                "profile_id": active_profile,
                "write_back": written_back,
                "parent_log_id": log_id,
                "pending_accept": pending_accept and not written_back,
            },
        )
    elif rewrite_only:
        revise_log_id = log_id
    accept_log_id = revise_log_id if (pending_accept and revise_log_id) else log_id

    if mode == "chapter" and num > 0 and log_id:
        from core import chapter_review
        from core import review_gaps

        excerpt = (review_text if revise else display_reply) or ""
        source_text = review_text.strip() if review_text.strip() else excerpt
        plan = novel_data.load_plan()
        resolved = criteria_resolver.resolve_review_criteria(
            plan, book_dir=ctx.store.paths.data_dir,
        )
        gaps = review_gaps.parse_gaps_from_review(source_text, resolved)
        try:
            chapter_review.append_round(
                ctx.store.paths.data_dir,
                num,
                quality_log_id=str(log_id),
                profile_id=active_profile,
                revise=revise,
                rewrite_only=rewrite_only,
                review_excerpt=excerpt[:2000],
                gaps=gaps,
                judgment="pending",
            )
        except (ValueError, OSError):
            pass

    from core import chapter_role_overlay

    role_meta: dict = {}
    if mode == "chapter" and num > 0:
        role_meta = chapter_role_overlay.review_context_meta(novel_data.load_plan(), num)

    return {
        "ok": True,
        "reply": display_reply,
        "full_reply": llm_r.get("full_reply"),
        "revised_text": llm_r.get("revised_text"),
        "revise": revise,
        "rewrite_only": rewrite_only,
        "write_back": written_back,
        "chapter_title": chapter_title or None,
        "sync_archive": sync_archive and written_back,
        "archive_synced": archive_synced,
        "archive": archive_result.get("archive") if archive_result else None,
        "archive_errors": archive_result.get("errors") if archive_result else None,
        "mode": mode,
        "chapter_num": num or None,
        "input_chars": len(body),
        "profile_id": active_profile,
        "profile_label": profile_label,
        "book_type": profile_meta.get("book_type"),
        "platform": profile_meta.get("platform"),
        "log_id": accept_log_id,
        "review_log_id": log_id if accept_log_id != log_id else None,
        "pending_accept": pending_accept,
        **role_meta,
        **ctx.reviewer_deps.llm.get_last_call_info(),
    }


def accept_female_fiction_rewrite(
    ctx: AppContext,
    log_id: str,
    *,
    sync_archive: bool = True,
) -> dict:
    from infra.logs import quality as quality_log

    row = quality_log.get_entry((log_id or "").strip())
    if not row:
        return {"ok": False, "error": "质量记录不存在"}

    kind = row.get("kind") or ""
    if kind not in ("female_fiction_revise", "female_fiction_review"):
        return {"ok": False, "error": "该记录不是女频改稿预览"}

    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    if extra.get("accepted"):
        return {"ok": False, "error": "该改稿已采纳"}

    num = int(row.get("chapter_num") or 0)
    if num < 1:
        return {"ok": False, "error": "章节号无效"}

    body = (row.get("body") or "").strip()
    if len(body) < 40:
        return {"ok": False, "error": "改稿正文过短，无法采纳"}
    if not _looks_like_chapter_body(body):
        return {
            "ok": False,
            "error": "改稿正文像审阅报告而非章节，请重新改稿",
        }

    write_r = chapter_text.write_chapter_from_review_text(
        ctx.store,
        num,
        body,
        apply_title=_apply_chapter_title,
        after_write=ctx.generator_deps.invalidate_injection,
    )
    if not write_r.get("ok"):
        return write_r

    try:
        plan_product.set_chapter_status(num, "drafting")
    except ValueError:
        pass

    archive_result: dict | None = None
    archive_synced = False
    if sync_archive:
        archive_result = orchestration_archive.run_archive_sync(num, ctx)
        archive_synced = bool(archive_result.get("ok"))

    profile_label = extra.get("profile_label") or ""
    accept_log_id = ctx.quality_log_entry(
        "female_fiction_accept",
        num,
        f"已采纳改稿（来源记录 {log_id}）",
        summary=f"女频采纳 · 第{num}章 · {profile_label}"[:120],
        persisted=True,
        persisted_detail=(
            "已写回章节"
            + ("；档案已同步" if archive_synced else "；档案同步未完成")
        ),
        extra={
            "source_log_id": log_id,
            "sync_archive": sync_archive,
            "archive_synced": archive_synced,
            "chapter_title": write_r.get("chapter_title"),
        },
    )
    return {
        "ok": True,
        "chapter_num": num,
        "chapter_title": write_r.get("chapter_title"),
        "chars": write_r.get("chars"),
        "write_back": True,
        "sync_archive": sync_archive,
        "archive_synced": archive_synced,
        "archive": archive_result.get("archive") if archive_result else None,
        "archive_errors": archive_result.get("errors") if archive_result else None,
        "source_log_id": log_id,
        "log_id": accept_log_id,
        **ctx.reviewer_deps.llm.get_last_call_info(),
    }
