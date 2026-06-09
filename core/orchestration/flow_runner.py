"""聚合流程 runner：可选一键串联；单步 API 不变。

- 想一键跑 → POST /api/flow/run
- 想逐步控 → 仍调原有 /api/* 单步接口
- 想中途停 → stop_after 指定步，或遇人工确认点自然停住
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core import chapter_io
from core import chapter_precheck
from core import plan_product

if TYPE_CHECKING:
    from app.context import AppContext

# 步序 id（与 workflow 节点对应，供 stop_after / continue 使用）
RERUN_PREPARE = "rerun_prepare"
PLAN_RERUN = "plan_rerun"
WRITE = "write"
ADOPT_PREVIEW = "adopt_preview"
PRECHECK = "precheck"
REVIEW = "review"
JUDGMENT = "judgment"
FINALIZE = "finalize"
SUMMARY_CONFIRM = "summary_confirm"

FLOW_STEP_DEFS: tuple[dict[str, Any], ...] = (
    {
        "id": RERUN_PREPARE,
        "label": "重跑准备（状态+草稿）",
        "node": "P4",
        "phase": "rerun",
        "automatable": True,
        "human_gate": False,
        "method": "POST",
        "path": "/api/rerun/pipeline",
    },
    {
        "id": PLAN_RERUN,
        "label": "规划 LLM 重跑",
        "node": "P4",
        "phase": "rerun",
        "automatable": True,
        "human_gate": False,
        "method": "POST",
        "path": "/api/rerun/pipeline",
        "note": "scope=plan_only 时有效",
    },
    {
        "id": WRITE,
        "label": "AI 写正文",
        "node": "L1",
        "phase": "chapter",
        "automatable": True,
        "human_gate": False,
        "method": "POST",
        "path": "/api/chat/stream",
    },
    {
        "id": ADOPT_PREVIEW,
        "label": "采纳写作预览",
        "node": "L3",
        "phase": "chapter",
        "automatable": False,
        "human_gate": True,
        "method": "POST",
        "path": "/api/chapters/{chapter_num}/apply-turn",
        "note": "AUTO_APPEND 关闭时需人工；可传 auto_adopt_write=true",
    },
    {
        "id": PRECHECK,
        "label": "机器预检",
        "node": "L1b",
        "phase": "chapter",
        "automatable": True,
        "human_gate": False,
        "method": "POST",
        "path": "/api/chapters/{chapter_num}/precheck",
    },
    {
        "id": REVIEW,
        "label": "差距审阅",
        "node": "L4-L5",
        "phase": "chapter",
        "automatable": True,
        "human_gate": False,
        "method": "POST",
        "path": "/api/review/female-fiction",
    },
    {
        "id": JUDGMENT,
        "label": "审阅判断",
        "node": "L5/L6",
        "phase": "chapter",
        "automatable": False,
        "human_gate": True,
        "method": "POST",
        "path": "/api/quality/log/{log_id}/judgment",
        "note": "可传 judgment={outcome,note} 自动代填",
    },
    {
        "id": FINALIZE,
        "label": "本章定稿",
        "node": "L10",
        "phase": "chapter",
        "automatable": True,
        "human_gate": False,
        "method": "POST",
        "path": "/api/post-chapter/finalize",
    },
    {
        "id": SUMMARY_CONFIRM,
        "label": "确认概述",
        "node": "L10b",
        "phase": "chapter",
        "automatable": False,
        "human_gate": True,
        "method": "POST",
        "path": "/api/chapters/{chapter_num}/summary/confirm",
        "note": "可传 auto_confirm_summary=true",
    },
)

STEP_BY_ID = {row["id"]: row for row in FLOW_STEP_DEFS}
CHAPTER_STEP_IDS = (
    WRITE, ADOPT_PREVIEW, PRECHECK, REVIEW, JUDGMENT, FINALIZE, SUMMARY_CONFIRM,
)
RERUN_CHAPTER_STEP_IDS = (RERUN_PREPARE,) + CHAPTER_STEP_IDS
RERUN_PLAN_STEP_IDS = (RERUN_PREPARE, PLAN_RERUN)

MANUAL_APIS_NOTE = (
    "聚合 runner 不替代单步接口；暂停后可继续调下方 next_manual 所列 API，"
    "或再次 POST /api/flow/run（mode=continue）。"
)


def list_flow_steps() -> dict[str, Any]:
    return {
        "steps": list(FLOW_STEP_DEFS),
        "chapter_sequence": list(CHAPTER_STEP_IDS),
        "rerun_chapter_sequence": list(RERUN_CHAPTER_STEP_IDS),
        "rerun_plan_sequence": list(RERUN_PLAN_STEP_IDS),
        "manual_apis_note": MANUAL_APIS_NOTE,
    }


def _format_manual_step(step_id: str, *, chapter_num: int = 0, log_id: str = "") -> dict[str, Any]:
    row = dict(STEP_BY_ID[step_id])
    path = str(row.get("path") or "")
    path = path.format(chapter_num=chapter_num, log_id=log_id or "{log_id}")
    row["path"] = path
    return row


def _chapter_body(chapter_num: int) -> str:
    raw = chapter_io.read_chapter_content(chapter_num)
    from core import chapters as chapter_text

    return chapter_text.strip_chapter_file_header(raw).strip()


def resolve_chapter_start_step(chapter_num: int) -> str | None:
    """按章状态推断 continue 模式起始步。"""
    from core.data import novel_data

    plan = plan_product.load_plan()
    project = novel_data.get_project_meta()
    status = plan_product.get_chapter_status(plan, chapter_num)
    if status == "approved":
        return None
    body = _chapter_body(chapter_num)
    if status == "pending":
        if len(body) < 80:
            return WRITE
        pre = chapter_precheck.run_precheck(
            chapter_num=chapter_num,
            content=body,
            plan=plan,
            project=project,
        )
        return WRITE if not pre.get("ok") else REVIEW
    if status == "drafting":
        return REVIEW if body else WRITE
    return WRITE


def build_step_sequence(
    *,
    mode: str,
    scope: str = "",
    chapter_num: int = 0,
    from_step: str = "",
) -> tuple[list[str], int | None]:
    mode = (mode or "continue").strip()
    chapter: int | None = chapter_num if chapter_num > 0 else None

    if mode == "rerun":
        scope = (scope or "from_chapter_n").strip()
        if scope == "plan_only":
            seq = list(RERUN_PLAN_STEP_IDS)
        else:
            seq = list(RERUN_CHAPTER_STEP_IDS)
            chapter = chapter or None
        if from_step and from_step in seq:
            seq = seq[seq.index(from_step):]
        return seq, chapter

    if mode == "chapter":
        if chapter_num <= 0:
            raise ValueError("mode=chapter 须指定 chapter_num")
        seq = list(CHAPTER_STEP_IDS)
        if from_step and from_step in seq:
            seq = seq[seq.index(from_step):]
        return seq, chapter_num

    # continue
    wq = plan_product.load_plan()
    statuses = plan_product.list_chapter_statuses(wq)
    pending = [
        n for n, st in sorted(statuses.items())
        if st in ("pending", "drafting")
    ]
    if not pending:
        return [], None
    chapter = chapter_num if chapter_num in pending else min(pending)
    start = from_step.strip() or (resolve_chapter_start_step(chapter) or WRITE)
    seq = list(CHAPTER_STEP_IDS)
    if start not in seq:
        start = WRITE
    seq = seq[seq.index(start):]
    return seq, chapter


def _stop_response(
    *,
    ok: bool,
    stop_reason: str,
    stopped_at: str,
    executed: list[dict[str, Any]],
    chapter_num: int | None,
    ctx_data: dict[str, Any],
    error: str = "",
) -> dict[str, Any]:
    log_id = str(ctx_data.get("review_log_id") or ctx_data.get("log_id") or "")
    return {
        "ok": ok,
        "stopped_at": stopped_at,
        "stop_reason": stop_reason,
        "executed": executed,
        "chapter_num": chapter_num,
        "log_id": log_id or None,
        "next_manual": _format_manual_step(stopped_at, chapter_num=chapter_num or 0, log_id=log_id),
        "manual_apis_note": MANUAL_APIS_NOTE,
        "error": error or None,
        **{k: v for k, v in ctx_data.items() if k not in ("review_log_id", "log_id")},
    }


def _execute_step(
    ctx: AppContext,
    step_id: str,
    *,
    chapter_num: int,
    ctx_data: dict[str, Any],
    rerun_kwargs: dict[str, Any],
    write_instruction: str,
    auto_adopt_write: bool,
    judgment: dict[str, Any] | None,
    auto_confirm_summary: bool,
) -> dict[str, Any]:
    if step_id == RERUN_PREPARE:
        from core.orchestration import rerun_pipeline

        scope = str(rerun_kwargs.get("scope") or "from_chapter_n")
        r = rerun_pipeline.run_pipeline(
            ctx,
            scope=scope,
            from_chapter_num=int(rerun_kwargs.get("from_chapter_num") or 0),
            current_chapter_num=int(rerun_kwargs.get("current_chapter_num") or 0),
            reset_plan_fields=bool(rerun_kwargs.get("reset_plan_fields")),
            clear_chapter_drafts=bool(rerun_kwargs.get("clear_chapter_drafts", True)),
            auto_plan_llm=False,
            plan_context_note=str(rerun_kwargs.get("plan_context_note") or ""),
        )
        if scope != "plan_only" and r.get("ok"):
            primary = (r.get("write_chapter") or {}).get("primary_chapter")
            if primary:
                ctx_data["chapter_num"] = int(primary)
        return r

    if step_id == PLAN_RERUN:
        from core.orchestration import rerun_pipeline

        scope = str(rerun_kwargs.get("scope") or "")
        if scope != "plan_only":
            return {"ok": True, "skipped": True, "reason": "非 plan_only scope"}
        affected = rerun_kwargs.get("affected_chapters")
        if not affected:
            from core import rerun_execute

            base = rerun_execute.execute(
                scope="plan_only",
                from_chapter_num=int(rerun_kwargs.get("from_chapter_num") or 0),
            )
            affected = base.get("affected_chapters") or []
        return rerun_pipeline.run_plan_rerun_llm(
            ctx,
            list(affected),
            context_note=str(rerun_kwargs.get("plan_context_note") or ""),
        )

    num = int(ctx_data.get("chapter_num") or chapter_num)

    if step_id == WRITE:
        from core.orchestration import writing as writing_orch

        instruction = (write_instruction or "").strip() or "请按 plan 写本章正文。"
        writing_orch.set_write_chapter(num)
        r = writing_orch.chat(instruction, chapter_num=num)
        if r.get("ok") and r.get("chapter_saved"):
            ctx_data["chapter_saved"] = True
        return r

    if step_id == ADOPT_PREVIEW:
        if ctx_data.get("chapter_saved"):
            return {"ok": True, "skipped": True, "reason": "正文已写入章节"}
        if not auto_adopt_write:
            return {
                "ok": False,
                "error": "需人工采纳写作预览",
                "human_gate": True,
            }
        from app import writing_turns as wt
        from app import writing_session as ws

        history = ws.get_chat_history()
        msg_index = None
        for i in range(len(history) - 1, -1, -1):
            if history[i].get("role") == "assistant":
                msg_index = i
                break
        if msg_index is None:
            return {"ok": False, "error": "无 assistant 回复可采纳"}
        r = wt.apply_assistant_turn_to_chapter(num, msg_index)
        if r.get("ok"):
            ctx_data["chapter_saved"] = True
        return r

    if step_id == PRECHECK:
        from core.orchestration import product as product_orch

        return product_orch.run_precheck(ctx, num)

    if step_id == REVIEW:
        from core.orchestration import female_fiction as ff_orch

        r = ff_orch.run_female_fiction_review(
            ctx,
            mode="chapter",
            chapter_num=num,
            skip_precheck=True,
        )
        if r.get("ok") and r.get("log_id"):
            ctx_data["log_id"] = r["log_id"]
            ctx_data["review_log_id"] = r["log_id"]
        return r

    if step_id == JUDGMENT:
        if not judgment:
            return {
                "ok": False,
                "error": "需人工审阅判断",
                "human_gate": True,
                "log_id": ctx_data.get("log_id"),
            }
        from core.orchestration import logs as logs_orch

        log_id = str(ctx_data.get("log_id") or "")
        if not log_id:
            return {"ok": False, "error": "缺少 review log_id，请先执行 review"}
        return logs_orch.record_quality_judgment(
            log_id,
            outcome=str(judgment.get("outcome") or "accepted"),
            issue_tags=judgment.get("issue_tags"),
            note=str(judgment.get("note") or ""),
            ctx=ctx,
        )

    if step_id == FINALIZE:
        from core.orchestration import finalize as finalize_orch
        from app.hooks import build_finalize_hooks

        return finalize_orch.run_post_chapter_finalize(num, build_finalize_hooks())

    if step_id == SUMMARY_CONFIRM:
        if not auto_confirm_summary:
            return {"ok": False, "error": "需人工确认概述", "human_gate": True}
        from core.orchestration import product as product_orch

        return product_orch.confirm_chapter_summary(ctx, num, push_highlights=True)

    return {"ok": False, "error": f"未知步骤: {step_id}"}


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
) -> dict[str, Any]:
    stop_after = (stop_after or "").strip()
    if stop_after and stop_after not in STEP_BY_ID:
        return {"ok": False, "error": f"无效 stop_after: {stop_after}"}

    try:
        sequence, target_chapter = build_step_sequence(
            mode=mode,
            scope=scope,
            chapter_num=chapter_num,
            from_step=from_step,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    if not sequence:
        return {
            "ok": True,
            "mode": mode,
            "completed": True,
            "executed": [],
            "message": "无待处理章节",
            "manual_apis_note": MANUAL_APIS_NOTE,
        }

    rerun_kwargs = {
        "scope": scope,
        "from_chapter_num": from_chapter_num,
        "current_chapter_num": current_chapter_num or from_chapter_num,
        "reset_plan_fields": reset_plan_fields,
        "clear_chapter_drafts": clear_chapter_drafts,
        "plan_context_note": plan_context_note,
    }
    ctx_data: dict[str, Any] = {"chapter_num": target_chapter}
    executed: list[dict[str, Any]] = []
    active_chapter = target_chapter or chapter_num

    for step_id in sequence:
        step_def = STEP_BY_ID[step_id]
        if step_def.get("human_gate"):
            auto_ok = (
                (step_id == ADOPT_PREVIEW and auto_adopt_write)
                or (step_id == JUDGMENT and judgment)
                or (step_id == SUMMARY_CONFIRM and auto_confirm_summary)
            )
            if not auto_ok:
                return _stop_response(
                    ok=True,
                    stop_reason="human_gate",
                    stopped_at=step_id,
                    executed=executed,
                    chapter_num=active_chapter,
                    ctx_data=ctx_data,
                )

        if step_id == PLAN_RERUN and not auto_plan_llm:
            executed.append({
                "step": step_id,
                "ok": True,
                "skipped": True,
                "reason": "auto_plan_llm=false",
            })
            if stop_after == step_id:
                return _stop_response(
                    ok=True,
                    stop_reason="stop_after",
                    stopped_at=step_id,
                    executed=executed,
                    chapter_num=active_chapter,
                    ctx_data=ctx_data,
                )
            continue

        num = int(ctx_data.get("chapter_num") or active_chapter or 0)
        result = _execute_step(
            ctx,
            step_id,
            chapter_num=num,
            ctx_data=ctx_data,
            rerun_kwargs=rerun_kwargs,
            write_instruction=write_instruction,
            auto_adopt_write=auto_adopt_write,
            judgment=judgment,
            auto_confirm_summary=auto_confirm_summary,
        )
        executed.append({"step": step_id, **result})

        if step_id == RERUN_PREPARE and result.get("affected_chapters"):
            rerun_kwargs["affected_chapters"] = result["affected_chapters"]
        if ctx_data.get("chapter_num"):
            active_chapter = int(ctx_data["chapter_num"])

        if result.get("human_gate"):
            return _stop_response(
                ok=True,
                stop_reason="human_gate",
                stopped_at=step_id,
                executed=executed,
                chapter_num=active_chapter,
                ctx_data=ctx_data,
            )

        if not result.get("ok"):
            return _stop_response(
                ok=False,
                stop_reason="step_failed",
                stopped_at=step_id,
                executed=executed,
                chapter_num=active_chapter,
                ctx_data=ctx_data,
                error=str(result.get("error") or "步骤失败"),
            )

        if stop_after == step_id:
            return _stop_response(
                ok=True,
                stop_reason="stop_after",
                stopped_at=step_id,
                executed=executed,
                chapter_num=active_chapter,
                ctx_data=ctx_data,
            )

    return {
        "ok": True,
        "mode": mode,
        "chapter_num": active_chapter,
        "completed": True,
        "stop_reason": "completed",
        "executed": executed,
        "manual_apis_note": MANUAL_APIS_NOTE,
    }
