"""日志编排。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from infra.logs import quality as quality_log
from infra.logs import runtime as runtime_log

if TYPE_CHECKING:
    from app.context import AppContext


def list_quality_entries(*, kind: str | None = None, limit: int = 80) -> dict:
    return {"entries": quality_log.list_entries(limit=limit, kind=kind)}


def get_quality_entry(entry_id: str) -> dict | None:
    return quality_log.get_entry(entry_id)


def record_quality_judgment(
    entry_id: str,
    *,
    outcome: str,
    issue_tags: list[str] | None = None,
    note: str = "",
    ctx: AppContext | None = None,
    push_highlight_on_pass: bool = True,
) -> dict:
    row = quality_log.record_judgment(
        entry_id,
        outcome=outcome,
        issue_tags=issue_tags,
        note=note,
    )
    if not row:
        return {"ok": False, "error": "记录不存在或 outcome 为空"}
    event_id = None
    highlight_result = None
    if ctx is not None:
        from core.orchestration import taste as taste_orch
        from core.orchestration import highlights as highlights_orch
        from core import plan_product
        from core.data import book_context

        event_id = taste_orch.on_quality_judgment(
            ctx,
            row,
            outcome=outcome,
            issue_tags=issue_tags,
            note=note,
        )
        kind = str(row.get("kind") or "")
        num = int(row.get("chapter_num") or 0)
        if (
            push_highlight_on_pass
            and highlights_orch.is_positive_outcome(outcome)
            and kind in ("female_fiction_review", "female_fiction_revise")
            and num > 0
        ):
            highlight_result = highlights_orch.push_on_review_pass(
                book_id=book_context.get_context().book_id,
                chapter_num=num,
                review_body=str(row.get("body") or ""),
                note=note,
                tags=issue_tags or ["hook_strong"],
            )
            try:
                plan_product.set_chapter_status(num, "drafting")
            except ValueError:
                pass
    return {
        "ok": True,
        "entry": row,
        "taste_event_id": event_id,
        "highlight": highlight_result,
    }


def list_runtime_entries(
    *,
    level: str | None = None,
    category: str | None = None,
    limit: int = 80,
) -> dict:
    return {
        "status": runtime_log.get_status(),
        "entries": runtime_log.list_entries(
            limit=limit, level=level, category=category
        ),
    }


def get_runtime_entry(entry_id: str) -> dict | None:
    return runtime_log.get_entry(entry_id)
