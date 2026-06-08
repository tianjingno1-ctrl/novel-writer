"""章后档案 / 档案同步编排。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import config
from core import maintain as archive_maintain
from core.book_store import BookStore
from summarizer import (
    BULK_ARCHIVE_STATE_SYSTEM,
    BULK_ARCHIVE_SUMMARIES_SYSTEM,
    build_bulk_state_user_message,
    build_bulk_summaries_user_message,
    extract_plot_active_unresolved,
    parse_bulk_state,
    parse_bulk_summaries,
)

if TYPE_CHECKING:
    from app.context import AppContext


def run_post_chapter_maintain(
    chapter_num: int | None,
    ctx: AppContext,
    *,
    auto_apply: bool = True,
    auto_append: bool = True,
) -> dict:
    return archive_maintain.run_post_chapter_maintain(
        chapter_num,
        ctx.maintain_deps,
        auto_apply=auto_apply,
        auto_append=auto_append,
    )


def run_archive_sync(
    chapter_num: int | None,
    ctx: AppContext,
    *,
    auto_apply_observe: bool = True,
    auto_append_locked: bool = True,
    auto_append_plot_new: bool = True,
) -> dict:
    return archive_maintain.run_archive_sync(
        chapter_num,
        ctx.maintain_deps,
        auto_apply_observe=auto_apply_observe,
        auto_append_locked=auto_append_locked,
        auto_append_plot_new=auto_append_plot_new,
    )


def persist_bulk_summaries(
    store: BookStore, parsed: dict
) -> tuple[bool, list[str], int]:
    """写入 bulk 概述；不触发 rotate。"""
    p = store.paths
    errors: list[str] = []
    count = 0
    for row in parsed.get("summaries") or []:
        if not isinstance(row, dict):
            continue
        try:
            num = int(row.get("num") or 0)
        except (TypeError, ValueError):
            continue
        if num < 1:
            continue
        text = (row.get("text") or "").strip()
        if not text:
            errors.append(f"第{num}章概述为空")
            continue
        w1 = store._upsert_summary_in_file(p.summaries_recent_file, num, text)
        w2 = store._upsert_summary_in_file(p.summaries_file, num, text)
        if w1 or w2:
            count += 1
        else:
            errors.append(f"第{num}章概述写入失败")
    return count > 0, errors, count


def persist_bulk_state(
    store: BookStore, parsed: dict, *, anchor_chapter: int
) -> tuple[bool, list[str]]:
    """写入 bulk 状态档案。"""
    p = store.paths
    errors: list[str] = []
    wrote = False

    char_dyn = (parsed.get("char_dynamic") or "").strip()
    if char_dyn:
        if store.write(
            p.char_dynamic_file,
            char_dyn if char_dyn.endswith("\n") else char_dyn + "\n",
            append=False,
            history_source="char_dynamic",
            chapter_num=anchor_chapter,
        ):
            wrote = True
        else:
            errors.append("char_dynamic 写入失败")

    plot_active = (parsed.get("plot_threads_active") or "").strip()
    if plot_active:
        if store.write(
            p.plot_threads_active_file,
            plot_active if plot_active.endswith("\n") else plot_active + "\n",
            append=False,
            history_source="plot_threads",
            chapter_num=anchor_chapter,
        ):
            wrote = True
        else:
            errors.append("plot_threads_active 写入失败")

    detail = (parsed.get("detail_locked_append") or "").strip()
    if detail:
        if store.write(
            p.plot_threads_locked_file,
            f"\n\n{detail}\n",
            append=True,
            history_source="detail_extract",
            chapter_num=anchor_chapter,
        ):
            wrote = True
        else:
            errors.append("detail_locked 追加失败")

    plot_new = (parsed.get("plot_new_threads") or "").strip()
    if plot_new:
        appended, _ = store.append_plot_new_threads(
            anchor_chapter,
            plot_new,
            auto_append=True,
        )
        if appended:
            wrote = True
        else:
            errors.append("plot_new_threads 追加失败")

    return wrote, errors


def _build_chapters_text_for_nums(
    store: BookStore, chapter_nums: list[int]
) -> tuple[str, bool]:
    import batch_world

    text, truncated, _ = batch_world.build_chapters_text_block(
        chapter_nums,
        store.read_chapter,
    )
    return text, truncated


def run_bulk_archive_sync(chapter_nums: list[int], ctx: AppContext) -> dict:
    """整批档案同步（方案 B）：先概述，再状态。"""
    skipped = ctx.short_story_skip("整批档案同步")
    if skipped:
        return skipped

    nums = sorted({int(n) for n in chapter_nums if int(n) >= 1})
    if not nums:
        return {"ok": False, "error": "无有效章节号"}

    store = ctx.store
    deps = ctx.maintain_deps
    chapters_text, truncated = _build_chapters_text_for_nums(store, nums)
    if not chapters_text.strip():
        return {"ok": False, "error": "范围内无正文"}

    pid = config.MAINTAIN_PROVIDER
    warnings: list[str] = []
    if truncated:
        warnings.append("部分章节正文在档案同步输入中已截断")

    p = store.paths
    snap = store.load_snapshot(for_purpose="maintain")
    sum_system = deps.llm.build_cached_system(BULK_ARCHIVE_SUMMARIES_SYSTEM, provider=pid)
    sum_user = build_bulk_summaries_user_message(
        nums,
        chapters_text,
        summaries_recent=snap.summaries_recent.strip(),
        char_static=snap.char_static,
    )
    sum_reply = deps.llm.call_api(
        sum_system,
        [{"role": "user", "content": sum_user}],
        provider=pid,
        tag=f"整批概述·{nums[0]}–{nums[-1]}章",
        silent=True,
    )
    if sum_reply is None:
        return {
            "ok": False,
            "error": deps.llm.get_last_call_info().get("error", "整批概述失败"),
            "fixed_nums": nums,
            **deps.llm.get_last_call_info(),
        }
    sum_parsed, sum_err = parse_bulk_summaries(sum_reply)
    if not sum_parsed:
        return {
            "ok": False,
            "error": f"整批概述 JSON 解析失败：{sum_err[:200]}",
            "fixed_nums": nums,
            "reply": sum_reply,
            **deps.llm.get_last_call_info(),
        }

    sum_ok, sum_errors, sum_count = persist_bulk_summaries(store, sum_parsed)
    summaries_blob = "\n\n".join(
        (r.get("text") or "").strip()
        for r in (sum_parsed.get("summaries") or [])
        if isinstance(r, dict) and (r.get("text") or "").strip()
    )

    state_system = deps.llm.build_cached_system(BULK_ARCHIVE_STATE_SYSTEM, provider=pid)
    state_user = build_bulk_state_user_message(
        nums,
        chapters_text,
        summaries_blob,
        snap.char_static,
        store.read(p.char_dynamic_file).strip(),
        store.read(p.plot_threads_locked_file).strip(),
        extract_plot_active_unresolved(store.read(p.plot_threads_active_file).strip()),
    )
    state_reply = deps.llm.call_api(
        state_system,
        [{"role": "user", "content": state_user}],
        provider=pid,
        tag=f"整批档案·{nums[0]}–{nums[-1]}章",
        silent=True,
    )
    if state_reply is None:
        return {
            "ok": False,
            "partial": sum_ok,
            "summaries_ok": sum_ok,
            "state_ok": False,
            "error": deps.llm.get_last_call_info().get("error", "整批状态档案失败"),
            "errors": sum_errors,
            "summary_count": sum_count,
            "fixed_nums": nums,
            "warnings": warnings,
            **deps.llm.get_last_call_info(),
        }
    state_parsed, state_err = parse_bulk_state(state_reply)
    if not state_parsed:
        return {
            "ok": False,
            "partial": sum_ok,
            "summaries_ok": sum_ok,
            "state_ok": False,
            "error": f"整批状态 JSON 解析失败：{state_err[:200]}",
            "errors": sum_errors,
            "summary_count": sum_count,
            "fixed_nums": nums,
            "warnings": warnings,
            "reply": state_reply,
            **deps.llm.get_last_call_info(),
        }

    state_ok, state_errors = persist_bulk_state(
        store, state_parsed, anchor_chapter=nums[-1]
    )
    all_errors = sum_errors + state_errors
    ok = sum_ok and state_ok
    return {
        "ok": ok,
        "partial": (sum_ok or state_ok) and not ok,
        "summaries_ok": sum_ok,
        "state_ok": state_ok,
        "summary_count": sum_count,
        "fixed_nums": nums,
        "errors": all_errors,
        "warnings": warnings,
        **deps.llm.get_last_call_info(),
    }
