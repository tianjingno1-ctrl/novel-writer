"""P3b 重跑执行：章状态变更与规划重置。"""

from __future__ import annotations

from typing import Any

from core import plan_product
from core import rerun_scope

RERUN_SCOPES = rerun_scope.RERUN_SCOPES


def _affected_chapters(
    plan: dict,
    *,
    scope: str,
    from_chapter_num: int = 0,
    current_chapter_num: int = 0,
) -> list[int]:
    scope = (scope or "").strip()
    all_nums = sorted(plan_product.list_chapter_statuses(plan))
    if scope == "chapter_only":
        n = current_chapter_num or from_chapter_num
        return [n] if n in all_nums or n > 0 else []
    if scope == "from_chapter_n":
        start = max(1, int(from_chapter_num or 0))
        return [n for n in all_nums if n >= start]
    if scope == "plan_only":
        return rerun_scope.chapters_mutable_for_plan_rerun(plan)
    return []


def execute(
    *,
    scope: str,
    from_chapter_num: int = 0,
    current_chapter_num: int = 0,
    reset_plan_fields: bool = False,
) -> dict[str, Any]:
    scope = (scope or "").strip()
    if scope not in RERUN_SCOPES or scope == "none":
        return {"ok": False, "error": f"无效或未指定 scope: {scope}"}

    plan = plan_product.load_plan()
    affected = _affected_chapters(
        plan,
        scope=scope,
        from_chapter_num=from_chapter_num,
        current_chapter_num=current_chapter_num,
    )
    if not affected:
        return {"ok": False, "error": "没有可重跑的章节"}

    locked = plan_product.locked_chapter_nums(plan)
    skipped_locked = [n for n in affected if n in locked and scope == "plan_only"]
    if scope == "plan_only" and skipped_locked:
        affected = [n for n in affected if n not in locked]

    impact = rerun_scope.build_impact_preview(
        plan,
        scope=scope,
        from_chapter_num=from_chapter_num,
        current_chapter_num=current_chapter_num,
    )

    updated: list[int] = []

    def _edit(p: dict) -> None:
        chapters = p.setdefault("chapters", {})
        for num in affected:
            key = str(num)
            ch = chapters.get(key)
            if not isinstance(ch, dict):
                continue
            if scope == "plan_only":
                ch["status"] = "pending"
                if reset_plan_fields:
                    ch["hook"] = ""
                    for scene in ch.get("scenes") or []:
                        if isinstance(scene, dict):
                            scene["done"] = False
            else:
                ch["status"] = "drafting"
            updated.append(num)

    plan_product.load_plan()
    from core.data import novel_data

    novel_data._mutate_plan(_edit)

    return {
        "ok": True,
        "scope": scope,
        "affected_chapters": updated,
        "impact_preview": impact,
        "locked_chapters": locked,
        "next_steps": rerun_scope.describe_rerun(scope, from_chapter_num=from_chapter_num),
    }
