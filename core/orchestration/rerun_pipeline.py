"""P4 重跑流水线：状态变更 + 规划 LLM + 写作队列。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from core import plan_product
from core import rerun_execute
from core import rerun_scope
from core.orchestration.flow_runner import CHAPTER_STEP_IDS, STEP_BY_ID
from infra import file_utils

if TYPE_CHECKING:
    from app.context import AppContext

CHAPTER_STEP_CHAIN = tuple(
    {
        "step": step_id,
        "method": STEP_BY_ID[step_id]["method"],
        "path": STEP_BY_ID[step_id]["path"],
    }
    for step_id in CHAPTER_STEP_IDS
)


def _chapter_title(plan: dict, chapter_num: int) -> str:
    ch = plan_product.get_chapter_entry(plan, chapter_num) or {}
    return str(ch.get("title") or f"第{chapter_num}章").strip()


def reset_chapter_draft(chapters_dir: Path, chapter_num: int, *, title: str = "") -> Path:
    chapters_dir.mkdir(parents=True, exist_ok=True)
    path = chapters_dir / f"ch{chapter_num:03d}.md"
    t = (title or f"第{chapter_num}章").strip()
    header = f"# 第{chapter_num}章"
    if t and t not in {f"第{chapter_num}章", header}:
        header = f"{header} · {t}"
    file_utils.atomic_write_text(path, f"{header}\n\n")
    return path


def build_chapter_work_queue(chapter_nums: list[int]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for num in sorted(chapter_nums):
        steps = []
        for row in CHAPTER_STEP_CHAIN:
            steps.append({
                **row,
                "path": row["path"].format(chapter_num=num, log_id="{log_id}"),
            })
        queue.append({"chapter_num": num, "steps": steps})
    return queue


def build_work_queue(
    plan: dict | None = None,
    *,
    book_dir: Path | None = None,
) -> dict[str, Any]:
    """按 plan 状态给出待处理章与建议下一步。"""
    p = plan if plan is not None else plan_product.load_plan()
    statuses = plan_product.list_chapter_statuses(p)
    pending_write: list[int] = []
    pending_review: list[int] = []
    for num, st in sorted(statuses.items()):
        if st == "approved":
            continue
        if st == "pending":
            pending_write.append(num)
        elif st == "drafting":
            pending_review.append(num)
    pending_summary: list[int] = []
    if book_dir is not None:
        from core import chapter_summary

        pending_summary = chapter_summary.list_pending_summary_nums(book_dir, p)
    return {
        "chapter_statuses": statuses,
        "pending_write": pending_write,
        "pending_review": pending_review,
        "pending_summary": pending_summary,
        "locked": plan_product.locked_chapter_nums(p),
        "chapter_work_queues": build_chapter_work_queue(pending_write + pending_review),
    }


def _prepare_chapter_rewrite(
    ctx: AppContext,
    chapter_nums: list[int],
    *,
    clear_drafts: bool,
) -> list[dict[str, Any]]:
    plan = plan_product.load_plan()
    chapters_dir = ctx.store.paths.chapters_dir
    prepared: list[dict[str, Any]] = []
    for num in sorted(chapter_nums):
        title = _chapter_title(plan, num)
        if clear_drafts:
            reset_chapter_draft(chapters_dir, num, title=title)
        else:
            path = chapters_dir / f"ch{num:03d}.md"
            if not path.is_file():
                reset_chapter_draft(chapters_dir, num, title=title)
        prepared.append({"chapter_num": num, "title": title, "draft_reset": clear_drafts})
    return prepared


def _bind_write_chapter(chapter_nums: list[int]) -> dict[str, Any]:
    if not chapter_nums:
        return {"ok": False, "error": "无写作章号"}
    first = min(chapter_nums)
    from app import writing_session as ws

    r = ws.set_write_chapter_num(first)
    return {**r, "primary_chapter": first}


def run_plan_rerun_llm(
    ctx: AppContext,
    chapter_nums: list[int],
    *,
    context_note: str = "",
) -> dict[str, Any]:
    from core.orchestration import prefill as prefill_orch

    if not chapter_nums:
        return {"ok": False, "error": "chapter_nums 为空"}
    plan = plan_product.load_plan()
    lines = [
        f"重跑规划：仅更新以下章节 → {chapter_nums}",
        (context_note or "").strip()[:2000],
        "",
        "当前规划摘要：",
    ]
    for num in sorted(chapter_nums):
        ch = plan_product.get_chapter_entry(plan, num) or {}
        beat = ""
        for scene in ch.get("scenes") or []:
            if isinstance(scene, dict) and scene.get("beat"):
                beat = str(scene["beat"])[:800]
                break
        lines.append(
            f"- 第{num}章《{ch.get('title', '')}》 hook={ch.get('hook', '')} beat={beat[:200]}"
        )
    lines.append("")
    lines.append("输出 JSON 的 chapters 数组时，只包含上述章号。")

    pref = prefill_orch.run_prefill_plan(
        ctx,
        chapter_count=len(chapter_nums),
        extra_context="\n".join(lines),
    )
    if not pref.get("ok"):
        return pref

    options = pref.get("options") or []
    if not options:
        payload = pref.get("payload") or {}
        options = [payload] if payload.get("chapters") else []

    if not options:
        return {
            "ok": False,
            "error": "预填规划未返回可用方案",
            "prefill": pref,
        }

    option = options[0]
    if not isinstance(option, dict):
        return {"ok": False, "error": "规划方案格式无效"}

    allowed = set(chapter_nums)
    raw_chapters = option.get("chapters") or []
    filtered = [
        ch for ch in raw_chapters
        if isinstance(ch, dict) and int(ch.get("num") or ch.get("chapter_num") or 0) in allowed
    ]
    if not filtered:
        return {
            "ok": False,
            "error": f"LLM 方案未包含目标章 {chapter_nums}",
            "prefill_log_id": pref.get("log_id"),
        }

    apply_r = prefill_orch.apply_plan_option(
        ctx,
        {"chapters": filtered, "id": option.get("id", "rerun")},
        replace=False,
        log_id=str(pref.get("log_id") or "") or None,
        init_review_criteria=False,
    )
    return {
        "ok": apply_r.get("ok", False),
        "prefill_log_id": pref.get("log_id"),
        "applied_chapters": apply_r.get("applied"),
        "plan_apply": apply_r,
        "error": apply_r.get("error"),
    }


def run_pipeline(
    ctx: AppContext,
    *,
    scope: str,
    from_chapter_num: int = 0,
    current_chapter_num: int = 0,
    reset_plan_fields: bool = False,
    clear_chapter_drafts: bool = True,
    auto_plan_llm: bool = True,
    plan_context_note: str = "",
) -> dict[str, Any]:
    """P3b 确认后的 P4：改状态 + 触发规划/写作准备。"""
    base = rerun_execute.execute(
        scope=scope,
        from_chapter_num=from_chapter_num,
        current_chapter_num=current_chapter_num,
        reset_plan_fields=reset_plan_fields,
    )
    if not base.get("ok"):
        return base

    scope = (scope or "").strip()
    affected = list(base.get("affected_chapters") or [])
    result: dict[str, Any] = {
        "ok": True,
        "scope": scope,
        "affected_chapters": affected,
        "impact_preview": base.get("impact_preview"),
        "locked_chapters": base.get("locked_chapters"),
        "status_update": base,
    }

    if scope == "plan_only":
        if auto_plan_llm:
            plan_r = run_plan_rerun_llm(
                ctx,
                affected,
                context_note=plan_context_note,
            )
            result["plan_rerun"] = plan_r
            if not plan_r.get("ok"):
                result["ok"] = False
                result["error"] = plan_r.get("error", "规划重跑失败")
        else:
            result["plan_rerun"] = {
                "ok": True,
                "skipped_llm": True,
                "hint": "POST /api/prefill/plan → /api/prefill/plan/apply (replace=false)",
                "chapter_nums": affected,
            }
        result["work_queue"] = build_work_queue()
        return result

    prepared = _prepare_chapter_rewrite(ctx, affected, clear_drafts=clear_chapter_drafts)
    bind = _bind_write_chapter(affected)
    result["chapter_prepare"] = prepared
    result["write_chapter"] = bind
    result["work_queue"] = {
        "chapters": build_chapter_work_queue(affected),
        "primary_chapter": bind.get("primary_chapter") or (min(affected) if affected else None),
        "flow": CHAPTER_STEP_CHAIN,
    }
    if not bind.get("ok"):
        result["ok"] = False
        result["error"] = bind.get("error", "无法绑定写作章")
    return result
