"""本章定稿编排：档案 bundle + 质检 bundle + 可选 pacing / outline。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

import infra.config as config
from core import maintain as archive_maintain
from core.book_store import parse_markdown_list_items
from core.deps import LlmHooks, MaintainDeps
from summarizer import (
    QUALITY_CHECK_BUNDLE_SYSTEM,
    build_quality_bundle_user_message,
    count_report_issues,
    parse_quality_bundle,
)


@dataclass
class FinalizeHooks:
    """定稿流程所需外部能力（由 app/bootstrap 从 main 注入，core 不 import main）。"""

    maintain_deps: MaintainDeps
    llm: LlmHooks
    resolve_chapter: Callable[[int | None], tuple[int, str] | dict]
    short_story_skip: Callable[[str], dict | None]
    chapters_text_for_scope: Callable[[int, str], str | None]
    load_check_snapshot: Callable[[int, str], object]
    read_summaries_recent: Callable[[], str]
    run_pacing_check: Callable[[], dict]
    run_outline: Callable[[], dict]
    quality_log_entry: Callable[..., str | None]


def llm_call_snapshot(get_last_call_info: Callable[[], dict], tag: str) -> dict | None:
    info = get_last_call_info()
    if not info.get("ok"):
        return None
    usage = info.get("usage") or {}
    input_tokens = int(usage.get("input") or 0) + int(usage.get("cache_read") or 0)
    return {
        "tag": tag,
        "input_tokens": input_tokens,
        "output_tokens": int(usage.get("output") or 0),
        "cost_usd": round(float(info.get("cost") or 0.0), 6),
    }


def format_finalize_report_markdown(result: dict) -> str:
    num = result.get("chapter_num") or 0
    lines = [f"# 本章定稿 · 第{num}章", ""]
    a = result.get("archive") or {}
    lines.append("## 已自动写入档案")
    summary = a.get("summary") or {}
    if summary.get("ok"):
        arch = (
            f"（{summary.get('archived_count')} 条已归档 summaries_archive）"
            if summary.get("archived_count")
            else ""
        )
        body = summary.get("full_text") or summary.get("text") or ""
        lines.append(f"### 概述 → summaries_recent{arch}\n{body}")
    observe = a.get("observe") or {}
    if observe.get("applied_count"):
        lines.append(f"### 角色观察 → 已写入 {observe['applied_count']} 条")
        for it in observe.get("items") or []:
            if it.get("applied"):
                lines.append(
                    f"- {it.get('target_file')}: {(it.get('proposed_text') or '')[:120]}"
                )
    detail = a.get("detail_locked") or {}
    if detail.get("ok") and detail.get("text"):
        lines.append(f"### 细节钉子 → plot_threads_locked\n{detail.get('text')}")
    plot_new = a.get("plot_new_threads") or {}
    if plot_new.get("appended_count"):
        lines.append(f"### 新伏笔 → active ×{plot_new['appended_count']}")
        for it in plot_new.get("items") or []:
            lines.append(f"- {it}")
    pp = result.get("plot_proposal") or {}
    if pp.get("advanced"):
        lines.append(f"\n## 伏笔推进（参考）\n{pp['advanced']}")
    if pp.get("resolved"):
        lines.append(f"\n## 疑似已回收（请手动确认）\n{pp['resolved']}")
    q = result.get("quality") or {}
    lines.append("\n## 质检报告")
    for key, label in (
        ("continuity", "连续性"),
        ("character_drift", "人物"),
        ("repetition", "套话"),
        ("pacing", "爽点"),
    ):
        block = q.get(key) or {}
        if block.get("skipped"):
            continue
        text = block.get("text") or ""
        if not text:
            continue
        cnt = block.get("issue_count")
        suffix = f"（{cnt} 条）" if cnt else ""
        lines.append(f"\n### {label}{suffix}\n{text}")
    todos = result.get("manual_todos") or []
    if todos:
        lines.append("\n## 还需你处理")
        for todo in todos:
            lines.append(f"- {todo.get('label', '')}")
    if result.get("errors"):
        lines.append("\n## 错误\n" + "\n".join(f"- {e}" for e in result["errors"]))
    cost = result.get("total_cost_usd")
    if cost is not None:
        lines.append(f"\n费用合计：${float(cost):.4f}")
    return "\n".join(lines)


def run_post_chapter_finalize(
    chapter_num: int | None,
    hooks: FinalizeHooks,
    *,
    run_pacing: bool = True,
    run_outline: bool = False,
    repetition_scope: str = "current",
    auto_apply_observe: bool = True,
    auto_append_locked: bool = True,
    auto_append_plot_new: bool = True,
) -> dict:
    skipped = hooks.short_story_skip("本章定稿")
    if skipped:
        skipped["chapter_num"] = chapter_num
        return skipped
    if repetition_scope not in ("current", "recent3", "all"):
        return {"ok": False, "error": "repetition_scope 必须是 current / recent3 / all"}

    resolved = hooks.resolve_chapter(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    num, content = resolved
    if not (content or "").strip():
        return {"ok": False, "error": "章节正文为空，无法定稿"}

    calls: list[dict] = []
    errors: list[dict] = []
    maintain_deps = hooks.maintain_deps
    archive_result = archive_maintain.call_bundle(num, content, maintain_deps)
    archive_parsed = archive_result.payload if archive_result.ok else None
    snap = llm_call_snapshot(hooks.llm.get_last_call_info, "archive_bundle")
    if snap:
        calls.append(snap)
    if not archive_result.ok:
        if archive_result.reply is None:
            errors.append(
                {
                    "task": "archive_bundle",
                    "stage": "call",
                    "message": archive_result.error or "档案 bundle 失败",
                    "fallback_used": False,
                    "raw_snippet": "",
                }
            )
        else:
            errors.append(
                {
                    "task": "archive_bundle",
                    "stage": "parse",
                    "message": archive_result.error or "未能解析 post-chapter-json",
                    "fallback_used": False,
                    "raw_snippet": (archive_result.reply or "")[:300],
                }
            )

    quality_parsed: dict | None = None
    rep_scope = repetition_scope
    rep_text = hooks.chapters_text_for_scope(num, rep_scope)
    if not rep_text:
        rep_text = content
        rep_scope = "current"
    snap_check = hooks.load_check_snapshot(num, content)
    pid_q = config.QUALITY_PROVIDER
    system_q = hooks.llm.build_cached_system(QUALITY_CHECK_BUNDLE_SYSTEM, provider=pid_q)
    messages_q = [
        {
            "role": "user",
            "content": build_quality_bundle_user_message(
                snap_check.world,
                snap_check.characters,
                snap_check.char_context_for_check,
                snap_check.summaries_combined,
                num,
                content,
                rep_text,
                rep_scope,
            ),
        }
    ]
    quality_reply = hooks.llm.call_api(
        system_q, messages_q, provider=pid_q, tag="质检bundle", silent=True
    )
    snap_q = llm_call_snapshot(hooks.llm.get_last_call_info, "quality_bundle")
    if snap_q:
        calls.append(snap_q)
    if quality_reply is None:
        errors.append(
            {
                "task": "quality_bundle",
                "stage": "call",
                "message": hooks.llm.get_last_call_info().get("error", "质检 bundle 失败"),
                "fallback_used": False,
                "raw_snippet": "",
            }
        )
    else:
        quality_parsed, _ = parse_quality_bundle(quality_reply)
        if not quality_parsed:
            errors.append(
                {
                    "task": "quality_bundle",
                    "stage": "parse",
                    "message": "未能解析 quality-bundle-json",
                    "fallback_used": False,
                    "raw_snippet": (quality_reply or "")[:300],
                }
            )

    archive: dict = {}
    archive_errors: list[str] = []
    plot_proposal = {"advanced": "", "resolved": ""}
    summary_written = False
    if archive_parsed is not None:
        plot_proposal["advanced"] = archive_parsed.get("plot_advanced", "")
        plot_proposal["resolved"] = archive_parsed.get("plot_resolved", "")
        persist_outcome = archive_maintain.persist(
            num,
            archive_parsed,
            maintain_deps,
            auto_apply_observe=auto_apply_observe,
            auto_append_locked=auto_append_locked,
            auto_append_plot_new=auto_append_plot_new,
        )
        archive = persist_outcome.to_archive_dict()
        archive_errors = persist_outcome.errors
        summary_written = bool(archive.get("summary", {}).get("ok"))
        for se in persist_outcome.structured_errors:
            errors.append(
                {
                    "task": se["task"],
                    "stage": se["stage"],
                    "message": se["message"],
                    "fallback_used": se.get("fallback_used", False),
                    "raw_snippet": se.get("raw_snippet", ""),
                }
            )

    quality: dict = {
        "continuity": {"ok": False, "issue_count": 0, "text": ""},
        "character_drift": {"ok": False, "issue_count": 0, "text": ""},
        "repetition": {"ok": False, "issue_count": 0, "text": ""},
        "pacing": {
            "ok": False,
            "skipped": True,
            "skip_reason": "disabled",
            "text": "",
        },
    }
    if quality_parsed:
        for key, task in (
            ("continuity", "continuity"),
            ("character_drift", "character_drift"),
            ("repetition", "repetition"),
        ):
            text = quality_parsed.get(key, "")
            quality[task] = {
                "ok": bool(text),
                "issue_count": count_report_issues(text),
                "text": text,
            }

    pacing_result: dict = {
        "ok": False,
        "skipped": True,
        "skip_reason": "disabled" if not run_pacing else "summary_not_written",
        "text": "",
    }
    if run_pacing:
        if summary_written:
            pacing_r = hooks.run_pacing_check()
            snap_p = llm_call_snapshot(hooks.llm.get_last_call_info, "pacing")
            if snap_p:
                calls.append(snap_p)
            if pacing_r.get("ok"):
                pacing_result = {
                    "ok": True,
                    "skipped": False,
                    "skip_reason": None,
                    "text": pacing_r.get("reply", ""),
                }
            else:
                errors.append(
                    {
                        "task": "pacing",
                        "stage": "call",
                        "message": pacing_r.get("error", "爽点检查失败"),
                        "fallback_used": False,
                        "raw_snippet": "",
                    }
                )
                pacing_result["skip_reason"] = None
        else:
            pacing_result["skip_reason"] = "summary_not_written"
    quality["pacing"] = pacing_result

    outline_result: dict = {
        "ok": False,
        "skipped": not run_outline,
        "skip_reason": "disabled" if not run_outline else None,
        "reply": None,
        "applied_to": None,
    }
    if run_outline:
        outline_r = hooks.run_outline()
        snap_o = llm_call_snapshot(hooks.llm.get_last_call_info, "outline")
        if snap_o:
            calls.append(snap_o)
        if outline_r.get("ok"):
            outline_result = {
                "ok": True,
                "skipped": False,
                "skip_reason": None,
                "reply": outline_r.get("reply"),
                "applied_to": "outline_latest",
            }
        else:
            errors.append(
                {
                    "task": "outline",
                    "stage": "call",
                    "message": outline_r.get("error", "续章灵感失败"),
                    "fallback_used": False,
                    "raw_snippet": "",
                }
            )

    manual_todos: list[dict] = []
    recent_raw = hooks.read_summaries_recent()
    recent_entry_count = len(re.findall(r"【第\d+章", recent_raw))
    archive_rotated = int((archive.get("summary") or {}).get("archived_count") or 0)
    if recent_entry_count >= 5 and archive_rotated <= 0:
        manual_todos.append(
            {
                "key": "archive_cut",
                "label": "归档剪切：将旧条目从 summaries_recent 移入 summaries_archive",
                "action": "open_file",
                "target": "summaries_recent",
                "dismissible": True,
            }
        )
    resolved_hint = parse_markdown_list_items(plot_proposal.get("resolved", ""))
    if resolved_hint:
        manual_todos.append(
            {
                "key": "resolved_threads",
                "label": "伏笔回收：以下伏笔疑似已回收，请手动移至「已回收」区",
                "action": "open_file",
                "target": "plot_threads_active",
                "hint_items": resolved_hint,
                "dismissible": True,
            }
        )
    if run_outline and outline_result.get("ok"):
        manual_todos.append(
            {
                "key": "outline_apply",
                "label": "续章灵感已生成，请确认后写入下一章 Beat",
                "action": "open_outline",
                "target": "outline_latest",
                "dismissible": True,
            }
        )

    archive_any = summary_written or (
        archive.get("observe", {}).get("applied_count", 0) > 0
    ) or archive.get("detail_locked", {}).get("ok") or archive.get(
        "plot_new_threads", {}
    ).get(
        "appended_count", 0
    ) > 0
    quality_any = any(
        quality[k].get("ok") for k in ("continuity", "character_drift", "repetition")
    ) or quality["pacing"].get("ok")
    ok = archive_any or quality_any
    partial = bool(errors) and ok

    total_cost = round(sum(c.get("cost_usd", 0) for c in calls), 6)
    log_summary_parts: list[str] = []
    if archive.get("summary", {}).get("ok"):
        log_summary_parts.append("概述✓")
    if archive.get("observe", {}).get("applied_count"):
        log_summary_parts.append(f"观察×{archive['observe']['applied_count']}")
    if archive.get("plot_new_threads", {}).get("appended_count"):
        log_summary_parts.append(
            f"伏笔×{archive['plot_new_threads']['appended_count']}"
        )
    if quality.get("continuity", {}).get("issue_count"):
        log_summary_parts.append(
            f"连续性{quality['continuity']['issue_count']}条"
        )
    if quality.get("repetition", {}).get("issue_count"):
        log_summary_parts.append(f"套话{quality['repetition']['issue_count']}条")

    flat_errors = [f"{e.get('task', '?')}：{e.get('message', '')}" for e in errors]
    if archive_errors:
        flat_errors = list(dict.fromkeys(flat_errors + archive_errors))

    finalize_report_md = format_finalize_report_markdown(
        {
            "chapter_num": num,
            "archive": archive,
            "plot_proposal": plot_proposal,
            "quality": quality,
            "manual_todos": manual_todos,
            "errors": flat_errors if not ok else [],
            "total_cost_usd": total_cost,
        }
    )

    log_id = hooks.quality_log_entry(
        "finalize",
        num,
        finalize_report_md,
        summary=" · ".join(log_summary_parts) or "本章定稿",
        persisted=archive_any,
        persisted_detail="、".join(log_summary_parts) if log_summary_parts else "",
        extra={"calls": calls, "ok": ok, "partial": partial},
    )

    result = {
        "ok": ok,
        "chapter_num": num,
        "partial": partial,
        "errors": flat_errors,
        "structured_errors": errors,
        "calls": calls,
        "total_cost_usd": total_cost,
        "archive": archive,
        "plot_proposal": plot_proposal,
        "quality": quality,
        "outline": outline_result,
        "manual_todos": manual_todos,
        "log_id": log_id,
        **hooks.llm.get_last_call_info(),
    }
    if not ok:
        result["error"] = "；".join(flat_errors) or "本章定稿未产生任何结果"
    return result
