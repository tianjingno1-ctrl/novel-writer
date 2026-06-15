"""AI 预填编排：方向 / 章规划（多方案 JSON）。"""

from __future__ import annotations



import json

import re

from typing import TYPE_CHECKING, Any



import infra.config as config

from core import chapter_roles

from core import plan_product

from core import profiles

from core import prompt_nodes

from core.data import novel_data

from infra import file_utils



if TYPE_CHECKING:

    from app.context import AppContext





def _load_project(ctx: AppContext) -> dict:

    path = ctx.store.paths.data_dir / "project.json"

    if not path.is_file():

        return {}

    try:

        raw = json.loads(path.read_text(encoding="utf-8"))

        return raw if isinstance(raw, dict) else {}

    except (json.JSONDecodeError, OSError):

        return {}





def _read_direction_context(ctx: AppContext) -> str:

    plan = novel_data.load_plan()

    meta_text = plan_product.meta_text_for_prompt(plan)

    if meta_text:

        return meta_text

    return ""




def _word_budget_lines(
    ctx: AppContext,
    *,
    chapter_count: int | None = None,
) -> list[str]:
    plan = novel_data.load_plan()
    meta = plan_product.get_meta(plan)
    project = _load_project(ctx)
    book_type = str(project.get("type") or "short")
    max_ch = 10 if book_type == "short" else 200
    cc = int(chapter_count or meta.get("chapter_count") or 0)
    lines: list[str] = []
    if cc:
        lines.append(f"目标章数：{max(1, min(max_ch, cc))}")
    wpc = int(meta.get("word_count_per_chapter") or 0)
    if wpc:
        lines.append(f"每章目标字数：{wpc}")
    tw = int(meta.get("total_word_target") or 0)
    if tw:
        lines.append(f"全书目标总字数：{tw}")
    return lines




def _parse_json_payload(text: str) -> dict[str, Any]:

    raw = (text or "").strip()

    if not raw:

        raise ValueError("AI 返回为空")

    if raw.startswith("```"):

        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)

        raw = re.sub(r"\s*```$", "", raw).strip()

    try:

        data = json.loads(raw)

        if isinstance(data, dict):

            return data

    except json.JSONDecodeError:

        pass

    m = re.search(r"\{[\s\S]*\}", raw)

    if not m:

        raise ValueError("无法解析 AI 输出的 JSON")

    try:

        data = json.loads(m.group(0))

    except json.JSONDecodeError as exc:

        raise ValueError("无法解析 AI 输出的 JSON") from exc

    if not isinstance(data, dict):

        raise ValueError("JSON 须为对象")

    return data





def _prefill_parse_error(ctx: AppContext, exc: ValueError, reply: str) -> str:

    msg = str(exc)

    info = ctx.reviewer_deps.llm.get_last_call_info()

    if info.get("output_truncated"):

        max_tok = info.get("max_tokens") or config.MAX_TOKENS

        return (

            f"{msg}（回复在 {max_tok} token 上限处被截断，JSON 不完整。"

            "可在 .env 提高 NOVEL_PREFILL_PLAN_MAX_TOKENS，或减少章数/让 AI 只出 1 套方案后重试）"

        )

    return msg





def _call_prefill_llm(

    ctx: AppContext,

    *,

    node_id: str,

    user_content: str,

    tag: str,

    kind: str,

    max_tokens: int | None = None,

) -> dict:

    book_dir = ctx.store.paths.data_dir

    project = _load_project(ctx)

    resolved = prompt_nodes.resolve_node(node_id, book_dir=book_dir, project=project)

    from core import model_routing

    pid = model_routing.resolve_provider_for_node(node_id)

    system = ctx.reviewer_deps.llm.build_cached_system(resolved.system, provider=pid)

    messages = [{"role": "user", "content": user_content}]

    reply = ctx.reviewer_deps.llm.call_api(

        system, messages, node_id=node_id, tag=tag, silent=True,

        max_tokens=max_tokens,

    )

    if reply is None:

        return {

            "ok": False,

            "error": ctx.reviewer_deps.llm.get_last_call_info().get("error", "预填失败"),

        }

    try:

        payload = _parse_json_payload(reply)

    except ValueError as exc:

        return {

            "ok": False,

            "error": _prefill_parse_error(ctx, exc, reply),

            "raw_reply": reply,

            "output_truncated": ctx.reviewer_deps.llm.get_last_call_info().get(

                "output_truncated",

            ),

        }



    log_id = ctx.quality_log_entry(

        kind,

        0,

        reply,

        summary=f"{tag} · {len(payload.get('options') or [])} 个方案",

        persisted=False,

        prompt_node=resolved.node_id,

        prompt_hash=resolved.prompt_hash,

        prompt_source=resolved.prompt_source,

        outcome="pending",

    )

    return {

        "ok": True,

        "payload": payload,

        "options": payload.get("options") or [],

        "log_id": log_id,

        **prompt_nodes.prompt_meta_dict(resolved),

        **ctx.reviewer_deps.llm.get_last_call_info(),

    }





def run_prefill_direction(

    ctx: AppContext,

    *,

    seed: str = "",

    reference_excerpt: str = "",

    chapter_count: int = 3,

) -> dict:

    from core.orchestration import taste as orchestration_taste



    direction_ctx = _read_direction_context(ctx)

    project = _load_project(ctx)

    taste_block = orchestration_taste.context_block(ctx)

    parts = [

        f"书型：{project.get('type', 'short')}",

        f"平台：{project.get('platform', 'tomato')}",

    ]

    budget = _word_budget_lines(ctx, chapter_count=chapter_count)

    if budget:

        parts.extend(budget)

    else:

        parts.append(f"目标章数：{max(1, min(20, chapter_count))}")

    if taste_block:

        parts.append(taste_block)

    if direction_ctx:

        parts.append(f"已有方向：\n{direction_ctx[:4000]}")

    if seed.strip():

        parts.append(f"用户种子：\n{seed.strip()[:8000]}")

    if reference_excerpt.strip():

        parts.append(f"参考摘录：\n{reference_excerpt.strip()[:12000]}")

    return _call_prefill_llm(

        ctx,

        node_id="prefill.direction",

        user_content="\n\n".join(parts),

        tag="预填方向",

        kind="prefill_direction",

    )





def apply_direction_option(

    ctx: AppContext,

    option: dict[str, Any],

    *,

    log_id: str | None = None,

) -> dict:

    if not isinstance(option, dict) or not option:

        return {"ok": False, "error": "option 不能为空"}

    meta = plan_product.direction_option_to_meta(option)

    plan_product.set_plan_meta(meta)

    if log_id:

        from infra.logs import quality as quality_log

        from core.data import book_context

        from core import taste as taste_store



        quality_log.record_judgment(log_id, outcome="accepted", note=f"采纳方向 {option.get('id', '')}")

        taste_store.record_judgment_event(

            book_id=book_context.get_context().book_id,

            quality_log_id=log_id,

            outcome="accepted",

            note=f"采纳方向 {option.get('id', '')}",

            prompt_node="prefill.direction",

        )

    return {"ok": True, "meta": meta, "option": option}





def run_prefill_plan(

    ctx: AppContext,

    *,

    direction_option: dict[str, Any] | None = None,

    chapter_count: int | None = None,

    extra_context: str = "",

) -> dict:

    from core.orchestration import taste as orchestration_taste



    direction_ctx = _read_direction_context(ctx)

    project = _load_project(ctx)

    taste_block = orchestration_taste.context_block(ctx)

    parts = [

        f"书型：{project.get('type', 'short')}",

        f"平台：{project.get('platform', 'tomato')}",

    ]

    if taste_block:

        parts.append(taste_block)

    if direction_ctx:

        parts.append(f"已确认方向：\n{direction_ctx[:6000]}")

    if direction_option:

        parts.append(f"选定方向 JSON：\n{json.dumps(direction_option, ensure_ascii=False)}")

    budget = _word_budget_lines(ctx, chapter_count=chapter_count)

    if budget:

        parts.extend(budget)

    elif chapter_count:

        parts.append(f"目标章数：{chapter_count}")

    if extra_context.strip():

        parts.append(extra_context.strip())

    parts.append(

        "只输出 1 套完整方案（options 数组仅 1 项）；"

        "beat 每项单行简述，intent 按 role 填 ai_suggest 必要字段即可。"

    )

    result = _call_prefill_llm(

        ctx,

        node_id="prefill.plan",

        user_content="\n\n".join(parts),

        tag="预填规划",

        kind="prefill_plan",

        max_tokens=config.PREFILL_PLAN_MAX_TOKENS,

    )

    if not result.get("ok"):

        return result

    payload = chapter_roles.normalize_prefill_plan_payload(result.get("payload") or {})

    options = payload.get("options") or []

    return {

        **result,

        "payload": payload,

        "options": options,

        "option": options[0] if options else {},

    }





def validate_plan_option(
    ctx: AppContext,
    option: dict[str, Any],
    *,
    replace: bool = True,
) -> dict:
    if not isinstance(option, dict):
        return {"ok": False, "error": "option 须为对象"}
    project = _load_project(ctx)
    book_type = str(project.get("type") or "short")
    preview = chapter_roles.build_plan_preview(
        plan_product.load_plan(),
        option,
        replace=replace,
    )
    validation = chapter_roles.validate_plan_sequence(preview, book_type=book_type)
    errors = chapter_roles.validation_errors(validation)
    warnings = chapter_roles.validation_warnings(validation)
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "validation": validation,
        "error": chapter_roles.format_validation_error(errors) if errors else "",
    }


def semantic_validate_plan_option(
    ctx: AppContext,
    option: dict[str, Any],
    *,
    replace: bool = True,
) -> dict:
    if not isinstance(option, dict):
        return {"ok": False, "error": "option 须为对象"}
    from core import plan_semantic_validate

    preview = chapter_roles.build_plan_preview(
        plan_product.load_plan(),
        option,
        replace=replace,
    )
    return plan_semantic_validate.run_semantic_validation(preview)


def apply_plan_option(

    ctx: AppContext,

    option: dict[str, Any],

    *,

    replace: bool = True,

    log_id: str | None = None,

    init_review_criteria: bool = True,

) -> dict:

    if not isinstance(option, dict):

        return {"ok": False, "error": "option 须为对象"}

    project = _load_project(ctx)

    book_type = str(project.get("type") or "short")

    preview = chapter_roles.build_plan_preview(
        plan_product.load_plan(),
        option,
        replace=replace,
    )

    validation = chapter_roles.validate_plan_sequence(preview, book_type=book_type)

    if chapter_roles.validation_errors(validation):

        return {
            "ok": False,
            "error": chapter_roles.format_validation_error(validation),
            "validation": validation,
        }

    try:

        applied = plan_product.apply_prefill_chapters(option, replace=replace)

    except ValueError as exc:

        return {"ok": False, "error": str(exc)}

    if not applied and replace:

        return {"ok": False, "error": "option.chapters 为空"}

    if init_review_criteria:

        profile_id = profiles.resolve_default_profile_id(

            book_type=str(project.get("type") or "short"),

            platform=str(project.get("platform") or "tomato"),

        )

        plan_product.set_review_criteria(

            profiles.build_criteria_from_profile(profile_id),

        )



    chapters_dir = ctx.store.paths.chapters_dir

    chapters_dir.mkdir(parents=True, exist_ok=True)

    for item in applied:

        num = item["chapter_num"]

        ch_path = chapters_dir / f"ch{num:03d}.md"

        if not ch_path.exists():

            header = f"# 第{num}章"

            title = item.get("title", "")

            if title and title not in {f"第{num}章"}:

                header = f"{header} · {title}"

            file_utils.atomic_write_text(ch_path, f"{header}\n\n")



    if log_id:

        from infra.logs import quality as quality_log

        from core.data import book_context

        from core import taste as taste_store



        quality_log.record_judgment(

            log_id, outcome="accepted", note=f"采纳规划 {option.get('id', '')}",

        )

        taste_store.record_judgment_event(

            book_id=book_context.get_context().book_id,

            quality_log_id=log_id,

            outcome="accepted",

            note=f"采纳规划 {option.get('id', '')}",

            prompt_node="prefill.plan",

        )

    out: dict[str, Any] = {

        "ok": True,

        "applied": applied,

        "option_id": option.get("id", ""),

        "chapter_count": len(applied),

        "review_criteria": plan_product.get_review_criteria(),

    }

    warns = chapter_roles.validation_warnings(validation)

    if warns:

        out["validation_warnings"] = warns

    return out

