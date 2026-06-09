"""AI 预填编排：方向 / 章规划（多方案 JSON）。"""

from __future__ import annotations



import json

import re

from typing import TYPE_CHECKING, Any



import infra.config as config

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

    path = ctx.store.paths.data_dir / "brief.md"

    if path.is_file():

        legacy = path.read_text(encoding="utf-8").strip()

        if legacy:

            return f"（legacy brief.md）\n{legacy[:4000]}"

    return ""





def _parse_json_payload(text: str) -> dict[str, Any]:

    raw = (text or "").strip()

    if not raw:

        raise ValueError("AI 返回为空")

    try:

        data = json.loads(raw)

        if isinstance(data, dict):

            return data

    except json.JSONDecodeError:

        pass

    m = re.search(r"\{[\s\S]*\}", raw)

    if not m:

        raise ValueError("无法解析 AI 输出的 JSON")

    data = json.loads(m.group(0))

    if not isinstance(data, dict):

        raise ValueError("JSON 须为对象")

    return data





def _call_prefill_llm(

    ctx: AppContext,

    *,

    node_id: str,

    user_content: str,

    tag: str,

    kind: str,

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

    )

    if reply is None:

        return {

            "ok": False,

            "error": ctx.reviewer_deps.llm.get_last_call_info().get("error", "预填失败"),

        }

    try:

        payload = _parse_json_payload(reply)

    except ValueError as exc:

        return {"ok": False, "error": str(exc), "raw_reply": reply}



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

        f"目标章数：{max(1, min(20, chapter_count))}",

    ]

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

    if chapter_count:

        parts.append(f"目标章数：{chapter_count}")

    if extra_context.strip():

        parts.append(extra_context.strip())

    return _call_prefill_llm(

        ctx,

        node_id="prefill.plan",

        user_content="\n\n".join(parts),

        tag="预填规划",

        kind="prefill_plan",

    )





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

    try:

        applied = plan_product.apply_prefill_chapters(option, replace=replace)

    except ValueError as exc:

        return {"ok": False, "error": str(exc)}

    if not applied and replace:

        return {"ok": False, "error": "option.chapters 为空"}



    project = _load_project(ctx)

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

    return {

        "ok": True,

        "applied": applied,

        "option_id": option.get("id", ""),

        "chapter_count": len(applied),

        "review_criteria": plan_product.get_review_criteria(),

    }

