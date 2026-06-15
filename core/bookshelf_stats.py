"""书架统计：按书目录读取 plan / lifecycle，无需切换当前书。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core import project_lifecycle

CHAPTER_STATUSES = frozenset({"pending", "drafting", "approved"})


def _load_plan(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _chapter_status(ch: dict) -> str:
    status = str(ch.get("status") or "").strip()
    if status in CHAPTER_STATUSES:
        return status
    scenes = ch.get("scenes") or []
    if scenes and all(
        isinstance(s, dict) and s.get("done") for s in scenes if isinstance(s, dict)
    ):
        return "drafting"
    return "pending"


def bookshelf_stats(book_dir: Path) -> dict[str, Any]:
    """返回书架 UI 用字段：progress_pct、shelf_status、chapter_label、wizard_step 等。"""
    plan = _load_plan(book_dir / "plan.json")
    lifecycle = project_lifecycle.get_lifecycle(book_dir)

    chapters_raw = plan.get("chapters") or {}
    nums: list[int] = []
    statuses: dict[int, str] = {}
    for key, ch in chapters_raw.items():
        if not isinstance(ch, dict):
            continue
        try:
            num = int(key)
        except (TypeError, ValueError):
            continue
        nums.append(num)
        statuses[num] = _chapter_status(ch)
    nums.sort()
    total = len(nums)
    approved = sum(1 for st in statuses.values() if st == "approved")
    progress_pct = round(approved * 100 / total) if total else 0

    meta = plan.get("meta") if isinstance(plan.get("meta"), dict) else {}
    review = (
        plan.get("review_criteria")
        if isinstance(plan.get("review_criteria"), dict)
        else {}
    )
    has_direction = bool(str(meta.get("logline") or "").strip())
    has_criteria = bool(
        review.get("hard_rules")
        or review.get("soft_rules")
        or review.get("custom_checks")
    )
    wizard_step = str(meta.get("wizard_step") or "").strip()
    wizard_complete = bool(meta.get("wizard_complete"))
    if not wizard_complete:
        wizard_complete = has_direction and total > 0 and has_criteria

    lc_status = str(lifecycle.get("status") or "drafting")
    if lc_status == "complete":
        shelf_status = "done"
        chapter_label = f"共 {total} 章 · 已完结"
    elif not wizard_complete:
        shelf_status = "draft"
        chapter_label = "草稿 · 继续向导"
    else:
        shelf_status = "active"
        next_ch = approved + 1 if approved < total else (nums[-1] if nums else 1)
        chapter_label = f"第 {next_ch} 章 · 写作中"

    return {
        "progress_pct": progress_pct,
        "shelf_status": shelf_status,
        "chapter_label": chapter_label,
        "wizard_complete": wizard_complete,
        "wizard_step": wizard_step or None,
        "chapter_total": total,
        "chapter_approved": approved,
        "lifecycle_status": lc_status,
    }
