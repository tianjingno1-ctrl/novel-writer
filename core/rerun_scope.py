"""P3b 重跑范围：影响预览与章锁定。"""

from __future__ import annotations

from typing import Any

from core.plan_product import get_chapter_status, list_chapter_statuses, locked_chapter_nums

RERUN_SCOPES = frozenset({"chapter_only", "from_chapter_n", "plan_only", "none"})


def build_impact_preview(
    plan: dict,
    *,
    scope: str,
    from_chapter_num: int = 0,
    current_chapter_num: int = 0,
) -> str:
    scope = (scope or "").strip()
    locked = locked_chapter_nums(plan)
    locked_txt = f"第 {', '.join(str(n) for n in locked)} 章" if locked else "无"

    if scope == "none":
        return "本次不触发重跑。"
    if scope == "chapter_only":
        n = current_chapter_num or from_chapter_num
        if not n:
            return "将重跑当前章（请指定 chapter_num）。"
        st = get_chapter_status(plan, n)
        warn = "；当前章草稿可能被覆盖" if st == "drafting" else ""
        return f"将重跑第 {n} 章（写作→预检→审阅）。已锁定：{locked_txt}{warn}。"
    if scope == "from_chapter_n":
        start = max(1, int(from_chapter_num or 0))
        if not start:
            return "请指定 from_chapter_num。"
        affected = [n for n in sorted(list_chapter_statuses(plan)) if n >= start]
        drafting = [n for n in affected if get_chapter_status(plan, n) == "drafting"]
        parts = [f"将影响第 {start} 章及之后共 {len(affected)} 章的规划"]
        if locked:
            safe = [n for n in locked if n < start]
            if safe:
                parts.append(f"第 {', '.join(str(x) for x in safe)} 章已锁定不受影响")
        if drafting:
            parts.append(f"第 {', '.join(str(x) for x in drafting)} 章草稿可能被覆盖")
        return "；".join(parts) + "。"
    if scope == "plan_only":
        all_nums = sorted(list_chapter_statuses(plan))
        mutable = [n for n in all_nums if get_chapter_status(plan, n) != "approved"]
        return (
            f"仅重跑规划（Beat/钩子）。已锁定 {locked_txt} 不受影响；"
            f"将更新 {len(mutable)} 章的规划条目。"
        )
    return f"未知 scope: {scope}"


def describe_rerun(scope: str, *, from_chapter_num: int = 0) -> dict[str, Any]:
    return {
        "scope": scope,
        "from_chapter_num": int(from_chapter_num or 0),
        "actions": _actions_for_scope(scope),
    }


def _actions_for_scope(scope: str) -> list[str]:
    if scope == "chapter_only":
        return ["writing.main", "precheck", "review.platform"]
    if scope == "from_chapter_n":
        return ["writing.main", "precheck", "review.platform", "from_chapter"]
    if scope == "plan_only":
        return ["prefill.plan", "plan_update"]
    return []


def chapters_mutable_for_plan_rerun(plan: dict) -> list[int]:
    return sorted(
        n for n, st in list_chapter_statuses(plan).items() if st != "approved"
    )
