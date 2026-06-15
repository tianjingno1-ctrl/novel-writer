"""审阅 / 检查类 API（只读 LLM，不写章节正文）。"""

from __future__ import annotations

import infra.config as config
from core.deps import ReviewerDeps
from core.maintain import observe_items_for_auto_apply
from core.schemas.service import ChapterWork
import review_prompts
from summarizer import (
    CHARACTER_DRIFT_SYSTEM,
    CHECK_SYSTEM,
    CROSS_CHAPTER_CONTINUITY_SYSTEM,
    DECONSTRUCT_SYSTEM,
    DETAIL_EXTRACT_SYSTEM,
    EDITOR_REVIEW_SYSTEM,
    OBSERVE_SYSTEM,
    PACING_CHECK_SYSTEM,
    READER_REVIEW_SYSTEM,
    REPETITION_CHECK_SYSTEM,
    SUMMARY_SYSTEM,
    build_character_drift_user_message,
    build_check_user_message,
    build_cross_chapter_check_user_message,
    build_deconstruct_user_message,
    build_detail_extract_user_message,
    build_editor_review_user_message,
    build_female_fiction_review_user_message,
    build_observe_user_message,
    build_pacing_check_user_message,
    build_reader_review_user_message,
    build_summary_user_message,
    parse_observe_proposals,
    split_female_review_revise_reply,
)


DECONSTRUCT_MAX_CHARS = 80_000


def review_source_for_scope(
    store: object,
    chapter_num: int,
    scope: str,
    chapter_body: str,
) -> tuple[str, str]:
    """选定 scope 下的正文块 + 概述块（供读者/编辑审阅）。"""
    summaries = store.summaries_for_scope(chapter_num, scope)
    if scope == "current":
        return chapter_body, summaries
    if scope == "recent3":
        text = store.chapters_text_for_scope(chapter_num, "recent3") or ""
        return text, summaries
    return "", summaries


def scope_label(scope: str, chapter_num: int) -> str:
    if scope == "current":
        return f"第{chapter_num}章"
    if scope == "recent3":
        start = max(1, chapter_num - 2)
        return f"第{start}–{chapter_num}章"
    if scope == "all":
        return "全书"
    return scope


def run_summary(work: ChapterWork, deps: ReviewerDeps) -> dict:
    if deps.quality.short_story_skip:
        skipped = deps.quality.short_story_skip("生成概述")
        if skipped:
            skipped["chapter_num"] = work.ref.num
            return skipped

    from core import model_routing

    num = work.ref.num
    node_id = "maintain.summary"
    pid = model_routing.resolve_provider_for_node(node_id)
    system = deps.llm.build_cached_system(SUMMARY_SYSTEM, provider=pid)
    messages = [
        {"role": "user", "content": build_summary_user_message(num, work.body)}
    ]
    reply = deps.llm.call_api(
        system, messages, node_id=node_id, tag="概述", silent=True
    )
    if reply is None:
        return {"ok": False, "error": deps.llm.get_last_call_info().get("error", "生成失败")}

    summary_ok, summary_rotate = deps.store.persist_summary(num, reply.strip())
    persisted_detail = "已追加到 summaries_recent.md"
    if summary_rotate.get("rotated"):
        persisted_detail += (
            f"；{summary_rotate['rotated']} 条已归档到 summaries_archive.md"
        )
    log_id = deps.quality.log_entry(
        "summary",
        num,
        reply,
        persisted=summary_ok,
        persisted_detail=persisted_detail,
    )
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": num,
        "log_id": log_id,
        **deps.llm.get_last_call_info(),
    }


def run_check(work: ChapterWork, scope: str, deps: ReviewerDeps) -> dict:
    if scope not in ("current", "recent3", "all"):
        return {"ok": False, "error": "scope 必须是 current / recent3 / all"}

    from core import model_routing

    num = work.ref.num
    snap = deps.store.load_snapshot(num, for_purpose="check", chapter_body=work.body)
    node_id = "check.continuity"
    pid = model_routing.resolve_provider_for_node(node_id)
    scope_lbl = scope_label(scope, num)

    if scope == "current":
        system = deps.llm.build_cached_system(CHECK_SYSTEM, provider=pid)
        user_content = build_check_user_message(
            snap.world,
            snap.characters,
            snap.char_context_for_check,
            snap.summaries_combined,
            num,
            work.body,
        )
        tag = "连续性检查"
    else:
        system = deps.llm.build_cached_system(
            CROSS_CHAPTER_CONTINUITY_SYSTEM, provider=pid
        )
        anchor = work.body if scope == "recent3" else ""
        user_content = build_cross_chapter_check_user_message(
            snap.world,
            snap.characters,
            snap.char_context_for_check,
            deps.store.summaries_for_scope(num, scope),
            snap.plot_locked,
            snap.plot_active,
            scope_lbl,
            num,
            anchor,
        )
        tag = f"跨章连续性·{scope_lbl}"

    messages = [{"role": "user", "content": user_content}]
    reply = deps.llm.call_api(
        system, messages, node_id=node_id, tag=tag, silent=True
    )
    if reply is None:
        return {"ok": False, "error": deps.llm.get_last_call_info().get("error", "检查失败")}

    log_id = deps.quality.log_entry(
        "continuity",
        num,
        reply,
        summary=f"{scope_lbl}",
        extra={"scope": scope},
    )
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": num,
        "scope": scope,
        "scope_label": scope_lbl,
        "log_id": log_id,
        **deps.llm.get_last_call_info(),
    }


def run_character_drift(work: ChapterWork, deps: ReviewerDeps) -> dict:
    num = work.ref.num
    snap = deps.store.load_snapshot(num, for_purpose="check", chapter_body=work.body)
    pid = config.CHECK_PROVIDER
    system = deps.llm.build_cached_system(CHARACTER_DRIFT_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_character_drift_user_message(
                snap.char_context_for_check, work.body
            ),
        }
    ]
    reply = deps.llm.call_api(system, messages, provider=pid, tag="人物检查", silent=True)
    if reply is None:
        return {"ok": False, "error": deps.llm.get_last_call_info().get("error", "检查失败")}
    log_id = deps.quality.log_entry("character_drift", num, reply)
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": num,
        "log_id": log_id,
        **deps.llm.get_last_call_info(),
    }


def run_detail_extract(
    work: ChapterWork,
    deps: ReviewerDeps,
    *,
    auto_append: bool = True,
) -> dict:
    num = work.ref.num
    snap = deps.store.load_snapshot(num, for_purpose="check", chapter_body=work.body)
    pid = config.SUMMARY_PROVIDER
    system = deps.llm.build_cached_system(DETAIL_EXTRACT_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_detail_extract_user_message(
                num,
                work.body,
                snap.plot_locked.strip(),
            ),
        }
    ]
    reply = deps.llm.call_api(system, messages, provider=pid, tag="提取细节", silent=True)
    if reply is None:
        return {"ok": False, "error": deps.llm.get_last_call_info().get("error", "提取失败")}
    appended = False
    if auto_append and reply.strip():
        appended = deps.store.append_plot_locked(num, reply.strip())
    log_id = deps.quality.log_entry(
        "detail_extract",
        num,
        reply,
        persisted=appended,
        persisted_detail=(
            "已追加到 plot_threads_locked.md" if appended else "未写入（正文为空）"
        ),
    )
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": num,
        "appended": appended,
        "log_id": log_id,
        **deps.llm.get_last_call_info(),
    }


def run_repetition_check(
    work: ChapterWork,
    scope: str,
    deps: ReviewerDeps,
) -> dict:
    if scope not in ("current", "recent3", "all"):
        return {"ok": False, "error": "scope 必须是 current / recent3 / all"}
    num = work.ref.num
    text = deps.store.chapters_text_for_scope(num, scope)
    if not text:
        return {"ok": False, "error": "选定范围内没有正文"}
    pid = config.CHECK_PROVIDER
    system = deps.llm.build_cached_system(REPETITION_CHECK_SYSTEM, provider=pid)
    messages = [{"role": "user", "content": text}]
    reply = deps.llm.call_api(system, messages, provider=pid, tag="套话检查", silent=True)
    if reply is None:
        return {"ok": False, "error": deps.llm.get_last_call_info().get("error", "检查失败")}
    scope_lbl = scope_label(scope, num)
    log_id = deps.quality.log_entry(
        "repetition", num, reply, summary=scope_lbl, extra={"scope": scope}
    )
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": num,
        "scope": scope,
        "scope_label": scope_lbl,
        "log_id": log_id,
        **deps.llm.get_last_call_info(),
    }


def run_pacing_check(deps: ReviewerDeps) -> dict:
    snap = deps.store.load_snapshot(for_purpose="check")
    summaries = snap.summaries_combined
    if not summaries or deps.store.count_summaries() == 0:
        return {"ok": False, "error": "请先生成章节概述（生成概述）"}
    pid = config.CHECK_PROVIDER
    system = deps.llm.build_cached_system(PACING_CHECK_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_pacing_check_user_message(snap.world, summaries),
        }
    ]
    reply = deps.llm.call_api(system, messages, provider=pid, tag="爽点检查", silent=True)
    if reply is None:
        return {"ok": False, "error": deps.llm.get_last_call_info().get("error", "检查失败")}
    ch_num = deps.store.latest_chapter_num()
    log_id = deps.quality.log_entry("pacing", ch_num, reply)
    return {"ok": True, "reply": reply, "log_id": log_id, **deps.llm.get_last_call_info()}


def run_observe(
    work: ChapterWork,
    deps: ReviewerDeps,
    *,
    auto_apply: bool = True,
) -> dict:
    num = work.ref.num
    snap = deps.store.load_snapshot(num, for_purpose="check", chapter_body=work.body)
    pid = config.CHECK_PROVIDER
    system = deps.llm.build_cached_system(OBSERVE_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_observe_user_message(
                num,
                work.body,
                snap.char_static,
                snap.char_dynamic.strip(),
            ),
        }
    ]
    reply = deps.llm.call_api(system, messages, provider=pid, tag="角色观察", silent=True)
    if reply is None:
        return {"ok": False, "error": deps.llm.get_last_call_info().get("error", "分析失败")}
    items, summary = parse_observe_proposals(reply)
    applied: list[dict] = []
    persisted_detail = ""
    apply_error = ""
    if auto_apply:
        payload = observe_items_for_auto_apply(items) if items else []
        if payload:
            apply_result = deps.store.apply_observe(payload, chapter_num=num)
            if apply_result.get("ok"):
                applied = apply_result.get("applied", [])
                targets = "、".join(sorted({a["target_file"] for a in applied}))
                persisted_detail = f"已写入 {len(applied)} 条 → {targets}"
            else:
                apply_error = apply_result.get("error", "自动写入失败")
        elif items:
            apply_error = "有提案但无可写入内容（has_change 均为 false 且正文为空）"
        if not applied:
            fallback_text = summary or reply
            applied = deps.store.observe_fallback_apply(num, fallback_text)
            if applied:
                persisted_detail = "已写入 char_dynamic（摘要回退）"
                apply_error = ""
            elif not items:
                persisted_detail = "未解析到结构化提案"
    log_id = deps.quality.log_entry(
        "observe",
        num,
        reply,
        summary=summary or persisted_detail,
        persisted=bool(applied),
        persisted_detail=persisted_detail,
    )
    return {
        "ok": True,
        "chapter_num": num,
        "reply": reply,
        "summary": summary,
        "items": items,
        "parse_ok": bool(items),
        "auto_applied": applied,
        "apply_error": apply_error,
        "log_id": log_id,
        **deps.llm.get_last_call_info(),
    }


def run_reader_review(
    work: ChapterWork,
    scope: str,
    deps: ReviewerDeps,
) -> dict:
    if scope not in ("current", "recent3", "all"):
        return {"ok": False, "error": "scope 必须是 current / recent3 / all"}
    num = work.ref.num
    primary, summaries = review_source_for_scope(
        deps.store, num, scope, work.body
    )
    if not primary.strip() and not summaries.strip():
        return {"ok": False, "error": "选定范围内没有正文或概述"}
    scope_lbl = scope_label(scope, num)
    pid = config.CHECK_PROVIDER
    system = deps.llm.build_cached_system(READER_REVIEW_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_reader_review_user_message(
                num, scope_lbl, primary, summaries
            ),
        }
    ]
    reply = deps.llm.call_api(
        system, messages, provider=pid, tag="读者审阅", silent=True
    )
    if reply is None:
        return {
            "ok": False,
            "error": deps.llm.get_last_call_info().get("error", "审阅失败"),
        }
    log_id = deps.quality.log_entry(
        "reader_review",
        num,
        reply,
        summary=scope_lbl,
        extra={"scope": scope},
    )
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": num,
        "scope": scope,
        "scope_label": scope_lbl,
        "log_id": log_id,
        **deps.llm.get_last_call_info(),
    }


def run_editor_review(
    work: ChapterWork,
    scope: str,
    deps: ReviewerDeps,
) -> dict:
    if scope not in ("current", "recent3", "all"):
        return {"ok": False, "error": "scope 必须是 current / recent3 / all"}
    num = work.ref.num
    primary, summaries = review_source_for_scope(
        deps.store, num, scope, work.body
    )
    if not primary.strip() and not summaries.strip():
        return {"ok": False, "error": "选定范围内没有正文或概述"}
    scope_lbl = scope_label(scope, num)
    snap = deps.store.load_snapshot(num, for_purpose="check", chapter_body=work.body)
    from core import plan_product
    from core import story_context

    plan = plan_product.load_plan()
    world_block = story_context.build_story_context_block(
        plan,
        snap.world,
        chapter_num=num,
        book_dir=deps.store.paths.data_dir,
    )
    pid = config.CHECK_PROVIDER
    system = deps.llm.build_cached_system(EDITOR_REVIEW_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_editor_review_user_message(
                num,
                scope_lbl,
                primary,
                summaries,
                world_block,
            ),
        }
    ]
    reply = deps.llm.call_api(
        system, messages, provider=pid, tag="编辑审阅", silent=True
    )
    if reply is None:
        return {
            "ok": False,
            "error": deps.llm.get_last_call_info().get("error", "审阅失败"),
        }
    log_id = deps.quality.log_entry(
        "editor_review",
        num,
        reply,
        summary=scope_lbl,
        extra={"scope": scope},
    )
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": num,
        "scope": scope,
        "scope_label": scope_lbl,
        "log_id": log_id,
        **deps.llm.get_last_call_info(),
    }


def run_deconstruct(
    source_text: str,
    deps: ReviewerDeps,
    *,
    source_label: str = "",
    include_book_context: bool = True,
    book_title: str = "",
    world_excerpt: str = "",
    style_excerpt: str = "",
    taste_excerpt: str = "",
) -> dict:
    """参考拆文：分析外部粘贴正文，输出结构化拆解报告。"""
    text = (source_text or "").strip()
    if len(text) < 80:
        return {"ok": False, "error": "正文过短，请至少粘贴 80 字"}
    if len(text) > DECONSTRUCT_MAX_CHARS:
        text = text[:DECONSTRUCT_MAX_CHARS] + "\n\n…（后文已截断，请缩短粘贴范围）"

    from core import model_routing

    node_id = "check.deconstruct"
    pid = model_routing.resolve_provider_for_node(node_id)
    system = deps.llm.build_cached_system(DECONSTRUCT_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_deconstruct_user_message(
                text,
                source_label=source_label,
                book_title=book_title if include_book_context else "",
                world_excerpt=world_excerpt if include_book_context else "",
                style_excerpt=style_excerpt if include_book_context else "",
                taste_excerpt=taste_excerpt,
            ),
        }
    ]
    reply = deps.llm.call_api(
        system, messages, node_id=node_id, tag="参考拆文", silent=True
    )
    if reply is None:
        return {
            "ok": False,
            "error": deps.llm.get_last_call_info().get("error", "拆解失败"),
        }

    log_id = deps.quality.log_entry(
        "deconstruct",
        0,
        reply,
        summary=(source_label or "参考拆文")[:120],
        extra={
            "source_label": source_label,
            "input_chars": len(text),
            "include_book_context": include_book_context,
        },
    )
    return {
        "ok": True,
        "reply": reply,
        "source_label": source_label,
        "input_chars": len(text),
        "log_id": log_id,
        **deps.llm.get_last_call_info(),
    }


def run_female_fiction_review(
    mode: str,
    body: str,
    chapter_num: int,
    deps: ReviewerDeps,
    *,
    book_title: str = "",
    world_excerpt: str = "",
    revise: bool = False,
    rewrite_only: bool = False,
    write_back: bool = False,
    profile_id: str | None = None,
    project: dict | None = None,
    taste_excerpt: str = "",
    revise_note: str = "",
) -> dict:
    """女频审阅纯 LLM：不读档、不写盘、不记 quality_log。"""
    project = project or {}
    system_text, active_profile = review_prompts.load_prompt_text(
        profile_id, project=project, include_revise=revise
    )
    from core import model_routing

    use_writing = revise or rewrite_only
    node_id = "writing.main" if use_writing else "review.platform"
    pid = model_routing.resolve_provider_for_node(node_id)
    system = deps.llm.build_cached_system(
        system_text,
        provider=pid,
        include_scene_context=use_writing,
        chapter_num=chapter_num if chapter_num > 0 else None,
    )
    messages = [
        {
            "role": "user",
            "content": build_female_fiction_review_user_message(
                mode,
                body,
                book_title=book_title,
                chapter_num=chapter_num,
                world_excerpt=world_excerpt,
                revise=revise and not rewrite_only,
                rewrite_only=rewrite_only,
                taste_excerpt=taste_excerpt,
                revise_note=revise_note,
            ),
        }
    ]
    tag_base = {
        "chapter": "女频直改稿·章" if rewrite_only else "女频审阅·章",
        "outline": "女频审阅·大纲",
        "characters": "女频审阅·人物",
    }[mode]
    tag = f"{tag_base}+写回" if write_back else tag_base
    reply = deps.llm.call_api(
        system, messages, node_id=node_id, tag=tag, silent=True
    )
    if reply is None:
        return {
            "ok": False,
            "error": deps.llm.get_last_call_info().get("error", "审阅失败"),
        }

    review_text = reply
    revised_text = ""
    display_reply = reply

    if rewrite_only:
        revised_text = (reply or "").strip()
        display_reply = revised_text
    elif revise:
        review_text, revised_text = split_female_review_revise_reply(reply)
        display_reply = revised_text if revised_text.strip() else review_text

    profile_label = review_prompts.profile_label(active_profile)
    return {
        "ok": True,
        "reply": display_reply,
        "full_reply": reply if (revise or rewrite_only) else None,
        "review_text": review_text,
        "revised_text": revised_text or None,
        "revise": revise,
        "rewrite_only": rewrite_only,
        "mode": mode,
        "chapter_num": chapter_num or None,
        "input_chars": len(body),
        "profile_id": active_profile,
        "profile_label": profile_label,
        "tag": tag,
        **deps.llm.get_last_call_info(),
    }
