"""章后档案维护：概述 / 角色观察 / 细节钉子 / 新伏笔（单次 LLM bundle）。

两阶段 API（推荐）：
  1. call_bundle() — 只调 LLM + 解析，返回 MaintainPayload
  2. persist()     — 只写盘，返回 PersistOutcome

定稿流程可 call 一次、persist 多次或与其他步骤共享 payload。
"""

from __future__ import annotations

import config
from core.book_store import BookStore, parse_markdown_list_items
from core.deps import MaintainDeps
from core.schemas.llm import MaintainPayload, parse_post_chapter_maintain
from core.schemas.service import (
    BookSnapshot,
    BundleCallResult,
    DetailLockedPersistResult,
    ObservePersistResult,
    PersistOutcome,
    PlotNewThreadsPersistResult,
    SummaryPersistResult,
)
from summarizer import POST_CHAPTER_MAINTAIN_SYSTEM, build_post_chapter_maintain_user_message


def _observe_item_has_change(item: dict) -> bool:
    text = str(item.get("proposed_text") or item.get("suggestion") or "").strip()
    hc = item.get("has_change")
    if hc is None:
        return bool(text)
    if isinstance(hc, str):
        return hc.strip().lower() not in ("false", "0", "no", "否") and bool(text)
    return bool(hc) and bool(text)


def observe_items_for_auto_apply(items: list[dict]) -> list[dict]:
    payload: list[dict] = []
    for it in items:
        if not _observe_item_has_change(it):
            continue
        text = str(it.get("proposed_text") or it.get("suggestion") or "").strip()
        if not text:
            continue
        target = str(it.get("target_file") or "char_dynamic").strip()
        if target not in ("char_static", "char_dynamic"):
            target = "char_dynamic"
        payload.append(
            {
                "id": it.get("id"),
                "target_file": target,
                "accepted": True,
                "proposed_text": it.get("proposed_text") or "",
                "edited_text": text,
            }
        )
    return payload


def _count_list_items(text: str) -> int:
    return len(parse_markdown_list_items(text))


def snapshot_to_maintain_ctx(num: int, content: str, snapshot: BookSnapshot) -> dict:
    """把 BookSnapshot 转成 build_archive_context 返回的格式，字段完全对齐。"""
    return {
        "chapter_num": num,
        "content": content,
        "char_static": snapshot.char_static,
        "char_dynamic": snapshot.char_dynamic,
        "plot_locked": snapshot.plot_locked,
        "plot_unresolved": snapshot.plot_unresolved,
    }


def build_archive_context(num: int, content: str, deps: MaintainDeps) -> dict:
    snapshot = deps.store.load_snapshot(num, for_purpose="maintain", chapter_body=content)
    return snapshot_to_maintain_ctx(num, content, snapshot)


def call_bundle(
    chapter_num: int,
    content: str,
    deps: MaintainDeps,
    *,
    ctx: dict | None = None,
) -> BundleCallResult:
    """阶段一：调用 LLM 档案 bundle，解析为 MaintainPayload，不写盘。"""
    if not (content or "").strip():
        return BundleCallResult(
            ok=False,
            chapter_num=chapter_num,
            error="章节正文为空",
        )
    snap = ctx or build_archive_context(chapter_num, content, deps)
    pid = config.MAINTAIN_PROVIDER
    system = deps.llm.build_cached_system(POST_CHAPTER_MAINTAIN_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_post_chapter_maintain_user_message(
                snap["chapter_num"],
                snap["content"],
                snap["char_static"],
                snap["char_dynamic"],
                snap["plot_locked"],
                snap["plot_unresolved"],
            ),
        }
    ]
    reply = deps.llm.call_api(system, messages, provider=pid, tag="档案bundle", silent=True)
    llm_meta = deps.llm.get_last_call_info()
    if reply is None:
        return BundleCallResult(
            ok=False,
            chapter_num=chapter_num,
            error=llm_meta.get("error", "档案 bundle 失败"),
            llm_meta=llm_meta,
        )
    payload, _ = parse_post_chapter_maintain(reply)
    if not payload:
        return BundleCallResult(
            ok=False,
            chapter_num=chapter_num,
            reply=reply,
            error="未能解析 post-chapter-json",
            parse_ok=False,
            llm_meta=llm_meta,
        )
    return BundleCallResult(
        ok=True,
        chapter_num=chapter_num,
        reply=reply,
        payload=payload,
        parse_ok=True,
        llm_meta=llm_meta,
    )


def call_archive_bundle(ctx: dict, deps: MaintainDeps) -> tuple[str | None, MaintainPayload | None]:
    """兼容旧接口：(reply, parsed)。"""
    result = call_bundle(
        ctx["chapter_num"],
        ctx["content"],
        deps,
        ctx=ctx,
    )
    return result.reply, result.payload


def _apply_maintain_observe(
    chapter_num: int,
    observe_block: dict,
    *,
    auto_apply: bool,
    deps: MaintainDeps,
) -> tuple[list[dict], str, str]:
    if not auto_apply:
        return [], "", ""
    items = observe_block.get("items") if isinstance(observe_block, dict) else []
    if not isinstance(items, list):
        items = []
    summary = (
        str(observe_block.get("summary") or "").strip()
        if isinstance(observe_block, dict)
        else ""
    )
    applied: list[dict] = []
    persisted_detail = ""
    apply_error = ""
    payload = observe_items_for_auto_apply(items) if items else []
    if payload:
        apply_result = deps.store.apply_observe(payload, chapter_num=chapter_num)
        if apply_result.get("ok"):
            applied = apply_result.get("applied", [])
            targets = "、".join(sorted({a["target_file"] for a in applied}))
            persisted_detail = f"已写入 {len(applied)} 条 → {targets}"
        else:
            apply_error = apply_result.get("error", "自动写入失败")
    elif items:
        apply_error = "有提案但无可写入内容（has_change 均为 false 且正文为空）"
    if not applied:
        applied = deps.store.observe_fallback_apply(chapter_num, summary)
        if applied:
            persisted_detail = "已写入 char_dynamic（摘要回退）"
            apply_error = ""
    return applied, persisted_detail, apply_error


def persist(
    chapter_num: int,
    payload: MaintainPayload,
    deps: MaintainDeps,
    *,
    auto_apply_observe: bool,
    auto_append_locked: bool,
    auto_append_plot_new: bool,
) -> PersistOutcome:
    """阶段二：将 MaintainPayload 写入磁盘，不调用 LLM。"""
    errors: list[str] = []
    structured: list[dict] = []

    summary_text = payload.get("summary", "")
    summary_rotate: dict = {"rotated": 0, "ok": True, "recent_count": 0}
    if summary_text:
        summary_ok, summary_rotate = deps.store.persist_summary(chapter_num, summary_text)
    else:
        summary_ok = False
    if summary_text and not summary_ok:
        errors.append("概述：生成成功但未写入 summaries")
        structured.append(
            {"task": "summary", "stage": "write", "message": "写入 summaries 失败"}
        )

    observe_block = payload.get("observe") or {}
    applied, observe_detail, observe_err = _apply_maintain_observe(
        chapter_num,
        observe_block,
        auto_apply=auto_apply_observe,
        deps=deps,
    )
    observe_items = observe_block.get("items", []) if isinstance(observe_block, dict) else []
    observe_summary = (
        str(observe_block.get("summary") or "").strip()
        if isinstance(observe_block, dict)
        else ""
    )
    skipped_observe = 0
    if observe_items:
        for item in observe_items:
            if not isinstance(item, dict):
                continue
            if not item.get("has_change") and not (
                str(item.get("proposed_text") or "").strip()
            ):
                skipped_observe += 1
    if auto_apply_observe and observe_items and not applied:
        errors.append(f"角色观察：{observe_err or '未写入 char_*'}")
        structured.append(
            {
                "task": "observe",
                "stage": "write",
                "message": observe_err or "未写入 char_*",
            }
        )

    detail_text = payload.get("detail_locked", "")
    detail_appended = False
    if auto_append_locked and detail_text.strip():
        detail_appended = deps.store.append_plot_locked(chapter_num, detail_text)
    if detail_text.strip() and auto_append_locked and not detail_appended:
        errors.append("提取细节：生成成功但未写入 plot_threads_locked")
        structured.append(
            {"task": "detail_locked", "stage": "write", "message": "写入 locked 失败"}
        )

    plot_new_text = payload.get("plot_new_threads", "")
    plot_appended, plot_items = deps.store.append_plot_new_threads(
        chapter_num,
        plot_new_text,
        auto_append=auto_append_plot_new,
    )
    if plot_new_text.strip() and auto_append_plot_new and not plot_appended:
        errors.append("新伏笔：生成成功但未写入 plot_threads_active")
        structured.append(
            {
                "task": "plot_new_threads",
                "stage": "write",
                "message": "写入 active 失败",
            }
        )

    observe_out_items: list[dict] = []
    for raw in observe_items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id", ""))
        applied_ids = {str(a.get("id", "")) for a in applied}
        observe_out_items.append(
            {
                "id": item_id,
                "target_file": raw.get("target_file"),
                "has_change": bool(raw.get("has_change")),
                "proposed_text": raw.get("proposed_text", ""),
                "applied": item_id in applied_ids,
            }
        )

    return PersistOutcome(
        summary=SummaryPersistResult(
            ok=summary_ok,
            text=summary_text[:200] if summary_text else "",
            full_text=summary_text,
            written_to="summaries_recent",
            archived_count=summary_rotate.get("rotated", 0),
            archive_written_to=(
                "summaries_archive" if summary_rotate.get("rotated") else None
            ),
        ),
        observe=ObservePersistResult(
            ok=bool(applied) or (bool(observe_items) and not auto_apply_observe),
            applied_count=len(applied),
            skipped_count=skipped_observe,
            items=observe_out_items,
            summary=observe_summary,
            detail=observe_detail,
        ),
        detail_locked=DetailLockedPersistResult(
            ok=detail_appended
            or (bool(detail_text.strip()) and not auto_append_locked),
            appended_count=_count_list_items(detail_text)
            or (1 if detail_appended else 0),
            written_to="plot_threads_locked",
            text=detail_text,
        ),
        plot_new_threads=PlotNewThreadsPersistResult(
            ok=plot_appended or (bool(plot_items) and not auto_append_plot_new),
            appended_count=len(plot_items) if plot_appended else 0,
            written_to="plot_threads_active",
            items=plot_items,
            text=plot_new_text,
        ),
        errors=errors,
        structured_errors=structured,
    )


def persist_archive_payload(
    num: int,
    parsed: MaintainPayload | dict,
    deps: MaintainDeps,
    *,
    auto_apply_observe: bool,
    auto_append_locked: bool,
    auto_append_plot_new: bool,
) -> tuple[dict, list[str], list[dict]]:
    """兼容旧接口：(archive_dict, errors, structured_errors)。"""
    outcome = persist(
        num,
        parsed,
        deps,
        auto_apply_observe=auto_apply_observe,
        auto_append_locked=auto_append_locked,
        auto_append_plot_new=auto_append_plot_new,
    )
    return outcome.to_archive_dict(), outcome.errors, outcome.structured_errors


def run_post_chapter_maintain(
    chapter_num: int | None,
    deps: MaintainDeps,
    *,
    auto_apply: bool = True,
    auto_append: bool = True,
) -> dict:
    if deps.quality.short_story_skip:
        skipped = deps.quality.short_story_skip("章后维护")
        if skipped:
            skipped["chapter_num"] = chapter_num
            return skipped

    resolved = deps.resolve_chapter(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    num, content = resolved

    bundle = call_bundle(num, content, deps)
    if not bundle.ok:
        if bundle.reply and not bundle.parse_ok:
            log_id = deps.quality.log_entry(
                "post_chapter_maintain",
                num,
                bundle.reply,
                persisted=False,
                persisted_detail="JSON 解析失败",
            )
            return {
                "ok": False,
                "error": bundle.error or "未能解析章后维护 JSON，请重试或使用单独按钮",
                "chapter_num": num,
                "parse_ok": False,
                "reply": bundle.reply,
                "log_id": log_id,
                **bundle.llm_meta,
            }
        return {"ok": False, "error": bundle.error, "chapter_num": num, **bundle.llm_meta}

    outcome = persist(
        num,
        bundle.payload,
        deps,
        auto_apply_observe=auto_apply,
        auto_append_locked=auto_append,
        auto_append_plot_new=False,
    )
    archive = outcome.to_archive_dict()
    errors = outcome.errors
    persisted = {
        "summary": archive["summary"]["ok"],
        "observe": archive["observe"]["applied_count"] > 0,
        "detail_extract": archive["detail_locked"]["ok"]
        and bool(archive["detail_locked"].get("text")),
    }
    summary_r = {
        "ok": archive["summary"]["ok"],
        "reply": archive["summary"]["full_text"],
        "chapter_num": num,
    }
    observe_r = {
        "ok": True,
        "chapter_num": num,
        "summary": archive["observe"].get("summary", ""),
        "items": archive["observe"]["items"],
        "parse_ok": bool(archive["observe"]["items"]),
        "auto_applied": [
            {"id": i["id"], "target_file": i["target_file"]}
            for i in archive["observe"]["items"]
            if i.get("applied")
        ],
        "apply_error": errors[0] if errors and "角色观察" in errors[0] else "",
    }
    detail_r = {
        "ok": True,
        "reply": archive["detail_locked"].get("text", ""),
        "chapter_num": num,
        "appended": persisted["detail_extract"],
    }

    ok = persisted["summary"] or persisted["observe"] or persisted["detail_extract"]
    detail_parts = []
    if persisted["summary"]:
        detail_parts.append("概述")
    if persisted["observe"]:
        detail_parts.append(archive["observe"].get("detail") or "角色观察")
    if persisted["detail_extract"]:
        detail_parts.append("细节钉子")
    log_id = deps.quality.log_entry(
        "post_chapter_maintain",
        num,
        bundle.reply or "",
        summary=(archive["summary"]["full_text"] or "")[:200],
        persisted=ok,
        persisted_detail="、".join(detail_parts) if detail_parts else "未写入",
    )

    if not ok:
        return {
            "ok": False,
            "error": "；".join(errors) or "章后维护未写入任何文件",
            "chapter_num": num,
            "persisted": persisted,
            "errors": errors,
            "parse_ok": True,
            "unified": True,
            "log_id": log_id,
            **bundle.llm_meta,
        }
    return {
        "ok": True,
        "chapter_num": num,
        "persisted": persisted,
        "errors": errors,
        "partial": bool(errors),
        "parse_ok": True,
        "unified": True,
        "summary": summary_r,
        "observe": observe_r,
        "detail_extract": detail_r,
        "log_id": log_id,
        **bundle.llm_meta,
    }


def run_archive_sync(
    chapter_num: int | None,
    deps: MaintainDeps,
    *,
    auto_apply_observe: bool = True,
    auto_append_locked: bool = True,
    auto_append_plot_new: bool = True,
) -> dict:
    if deps.quality.short_story_skip:
        skipped = deps.quality.short_story_skip("档案同步")
        if skipped:
            skipped["chapter_num"] = chapter_num
            return skipped

    resolved = deps.resolve_chapter(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    num, content = resolved

    bundle = call_bundle(num, content, deps)
    if not bundle.ok:
        if bundle.reply and not bundle.parse_ok:
            return {
                "ok": False,
                "error": bundle.error or "未能解析档案 JSON",
                "chapter_num": num,
                "reply": bundle.reply,
                **bundle.llm_meta,
            }
        return {"ok": False, "error": bundle.error, "chapter_num": num, **bundle.llm_meta}

    outcome = persist(
        num,
        bundle.payload,
        deps,
        auto_apply_observe=auto_apply_observe,
        auto_append_locked=auto_append_locked,
        auto_append_plot_new=auto_append_plot_new,
    )
    archive = outcome.to_archive_dict()
    ok = (
        archive.get("summary", {}).get("ok")
        or archive.get("observe", {}).get("applied_count", 0) > 0
        or archive.get("detail_locked", {}).get("ok")
        or archive.get("plot_new_threads", {}).get("appended_count", 0) > 0
    )
    return {
        "ok": ok,
        "chapter_num": num,
        "archive": archive,
        "errors": outcome.errors,
        "partial": bool(outcome.errors) and ok,
        **bundle.llm_meta,
    }
