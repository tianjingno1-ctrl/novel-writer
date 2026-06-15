"""聚合流程步序：供 rerun / work-queue 推断；单步仍走 /api/*。"""

from __future__ import annotations

from typing import Any

from core import chapter_io
from core import chapter_precheck
from core import chapter_role_overlay
from core import plan_product

# 步序 id（与 workflow 节点对应）
RERUN_PREPARE = "rerun_prepare"
PLAN_RERUN = "plan_rerun"
WRITE = "write"
PRECHECK = "precheck"
ADOPT_PREVIEW = "adopt_preview"
REVIEW = "review"
JUDGMENT = "judgment"
POSITIVE_HIGHLIGHT = "positive_highlight"
RHYTHM_CHECK = "rhythm_check"
FINALIZE = "finalize"
SUMMARY_CONFIRM = "summary_confirm"

_STANDARD_CHAPTER_STEP_IDS = (
    WRITE, PRECHECK, ADOPT_PREVIEW, REVIEW, JUDGMENT,
    POSITIVE_HIGHLIGHT, RHYTHM_CHECK, FINALIZE, SUMMARY_CONFIRM,
)
CHAPTER_STEP_IDS = _STANDARD_CHAPTER_STEP_IDS

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
        "id": PRECHECK,
        "label": "机器预检",
        "node": "L1b",
        "phase": "chapter",
        "automatable": True,
        "human_gate": False,
        "method": "POST",
        "path": "/api/chapters/{chapter_num}/precheck",
        "note": "L1b 先于用户预览",
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
        "id": POSITIVE_HIGHLIGHT,
        "label": "正向案例写入口味库",
        "node": "L5a",
        "phase": "chapter",
        "automatable": False,
        "human_gate": True,
        "method": "POST",
        "path": "/api/taste/highlights/{chapter_num}",
        "note": "含冲突检测；可传 auto_push_highlight 跳过",
    },
    {
        "id": RHYTHM_CHECK,
        "label": "节奏预警",
        "node": "L5b",
        "phase": "chapter",
        "automatable": True,
        "human_gate": False,
        "method": "POST",
        "path": "/api/chapters/{chapter_num}/rhythm-check",
        "note": "连续高风险时 human_gate 停住，可选进 P1",
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
RERUN_CHAPTER_STEP_IDS = (RERUN_PREPARE,) + _STANDARD_CHAPTER_STEP_IDS
RERUN_PLAN_STEP_IDS = (RERUN_PREPARE, PLAN_RERUN)


def _short_chapter_step_ids(steps: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(s for s in steps if s != SUMMARY_CONFIRM)


def chapter_step_ids_for_plan(
    plan: dict | None = None,
    chapter_num: int = 0,
) -> tuple[str, ...]:
    from core.data import book_context

    del plan, chapter_num
    steps = _STANDARD_CHAPTER_STEP_IDS
    if book_context.is_short_book():
        return _short_chapter_step_ids(steps)
    return steps


MANUAL_APIS_NOTE = (
    "Gate 各步仍通过 /api/* 单步接口调用；"
    "GET /api/flow/steps 列出标准章序列。"
)


def list_flow_steps() -> dict[str, Any]:
    return {
        "steps": list(FLOW_STEP_DEFS),
        "chapter_sequence": list(_STANDARD_CHAPTER_STEP_IDS),
        "rerun_chapter_sequence": list(RERUN_CHAPTER_STEP_IDS),
        "rerun_plan_sequence": list(RERUN_PLAN_STEP_IDS),
        "manual_apis_note": MANUAL_APIS_NOTE,
    }


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
            role_params=chapter_role_overlay.l1b_params(plan, chapter_num),
        )
        return WRITE if not pre.get("ok") else ADOPT_PREVIEW
    if status == "drafting":
        seq = chapter_step_ids_for_plan(plan, chapter_num)
        if REVIEW in seq:
            return REVIEW
        return POSITIVE_HIGHLIGHT if body else WRITE
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
            plan = plan_product.load_plan()
            ch = chapter_num if chapter_num > 0 else 0
            seq = [RERUN_PREPARE, *chapter_step_ids_for_plan(plan, ch)]
            chapter = chapter or None
        if from_step and from_step in seq:
            seq = seq[seq.index(from_step):]
        return seq, chapter

    if mode == "chapter":
        if chapter_num <= 0:
            raise ValueError("mode=chapter 须指定 chapter_num")
        plan = plan_product.load_plan()
        seq = list(chapter_step_ids_for_plan(plan, chapter_num))
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
    seq = list(chapter_step_ids_for_plan(wq, chapter))
    if start not in seq:
        start = WRITE
    seq = seq[seq.index(start):]
    return seq, chapter
