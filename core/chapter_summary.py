"""章概述侧车（L10b 确认 + highlights 引用）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from infra import file_utils


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def summary_path(book_dir: Path, chapter_num: int) -> Path:
    return book_dir / "chapters" / f"ch{chapter_num:03d}" / "summary.json"


def load_summary(book_dir: Path, chapter_num: int) -> dict[str, Any] | None:
    path = summary_path(book_dir, chapter_num)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def save_summary_draft(
    book_dir: Path,
    chapter_num: int,
    content: str,
    *,
    highlights_draft: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    path = summary_path(book_dir, chapter_num)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = load_summary(book_dir, chapter_num) or {}
    doc.update({
        "chapter_num": chapter_num,
        "status": "pending",
        "content": (content or "").strip(),
        "highlights_draft": highlights_draft or doc.get("highlights_draft") or [],
        "highlights": doc.get("highlights") or [],
    })
    file_utils.atomic_write_text(
        path,
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    return doc


def list_pending_summary_nums(book_dir: Path, plan: dict | None = None) -> list[int]:
    """E1b：有未确认概述的章（summary.json status=pending）。"""
    from core import plan_product

    p = plan if plan is not None else plan_product.load_plan()
    pending: list[int] = []
    for num, st in sorted(plan_product.list_chapter_statuses(p).items()):
        if st == "approved":
            continue
        doc = load_summary(book_dir, num)
        if doc and str(doc.get("status") or "") == "pending":
            pending.append(num)
    return pending


def confirm_summary(
    book_dir: Path,
    chapter_num: int,
    *,
    push_highlights: bool = True,
    book_id: str = "",
) -> dict[str, Any]:
    from core import plan_product
    from core.orchestration import highlights as highlights_orch

    doc = load_summary(book_dir, chapter_num)
    if not doc:
        return {"ok": False, "error": "概述不存在，请先生成"}
    doc["status"] = "confirmed"
    doc["confirmed_at"] = _now()

    pushed: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = list(doc.get("highlights") or [])
    bid = (book_id or "").strip()
    if not bid:
        try:
            from core.data import book_context

            bid = book_context.get_context().book_id
        except RuntimeError:
            bid = ""

    if push_highlights:
        for item in doc.get("highlights_draft") or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            r = highlights_orch.push_on_review_pass(
                book_id=bid,
                chapter_num=chapter_num,
                review_body=text,
                note=str(item.get("annotation") or ""),
            )
            if r:
                pushed.append(r)
                refs.append({
                    "example_id": r["example"]["id"],
                    "pushed_to_taste": True,
                    "pushed_at": _now(),
                })
        doc["highlights_draft"] = []
    doc["highlights"] = refs

    file_utils.atomic_write_text(
        summary_path(book_dir, chapter_num),
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    plan_product.set_chapter_status(chapter_num, "approved")
    return {"ok": True, "summary": doc, "pushed_highlights": pushed}
