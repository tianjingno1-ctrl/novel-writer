# L4 审阅标准解析：把 plan.review_criteria 里的 RuleRef 展开成 hard/soft 条目（读 taste / profiles / custom）；不存盘、不改规则。
"""审阅标准 RuleRef → 可执行条目。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import profiles
from core import taste
from core.plan_product import get_review_criteria
from core.schemas.rule_refs import parse_rule_ref


def resolve_rule_ref_content(
    ref: str,
    *,
    book_dir: Path | None = None,
    plan: dict | None = None,
) -> dict[str, Any] | None:
    source, rule_id = parse_rule_ref(ref)

    if source == "global":
        doc = taste.load_global()
        for row in doc.get("rules") or []:
            if isinstance(row, dict) and row.get("id") == rule_id:
                return {**row, "ref": ref, "source": "global"}
        return None

    if source == "local":
        bdoc = taste.load_book_taste(book_dir)
        overrides = bdoc.get("overrides") if isinstance(bdoc.get("overrides"), dict) else {}
        for row in overrides.get("append_rules") or []:
            if isinstance(row, dict) and row.get("id") == rule_id:
                weight = row.get("weight", "hard")
                return {
                    "ref": ref,
                    "id": rule_id,
                    "content": row.get("content", ""),
                    "weight": weight,
                    "source": "local",
                }
        for row in overrides.get("rules") or []:
            if isinstance(row, dict) and row.get("ref") == f"global:{rule_id}":
                base = resolve_rule_ref_content(f"global:{rule_id}", book_dir=book_dir, plan=plan)
                if base:
                    base = dict(base)
                    if row.get("weight"):
                        base["weight"] = row["weight"]
                    base["ref"] = ref
                    return base
        return None

    if source == "profile":
        criteria = get_review_criteria(plan)
        profile_id = str(criteria.get("platform_profile") or "").strip()
        if not profile_id:
            return None
        row = profiles.resolve_profile_rule_ref(profile_id, rule_id)
        return row

    if source == "custom":
        criteria = get_review_criteria(plan)
        checks = criteria.get("custom_checks") or []
        try:
            idx = int(rule_id)
            if 0 <= idx < len(checks):
                return {
                    "ref": ref,
                    "content": str(checks[idx]),
                    "weight": "hard",
                    "source": "custom",
                }
        except ValueError:
            pass
        for i, text in enumerate(checks):
            if str(text).strip() == rule_id:
                return {
                    "ref": ref,
                    "content": str(text),
                    "weight": "hard",
                    "source": "custom",
                }
        return None

    return None


def resolve_review_criteria(
    plan: dict,
    *,
    book_dir: Path | None = None,
) -> dict[str, Any]:
    criteria = get_review_criteria(plan)
    hard: list[dict] = []
    soft: list[dict] = []
    for ref in criteria.get("hard_rules") or []:
        row = resolve_rule_ref_content(str(ref), book_dir=book_dir, plan=plan)
        if row:
            hard.append(row)
    for ref in criteria.get("soft_rules") or []:
        row = resolve_rule_ref_content(str(ref), book_dir=book_dir, plan=plan)
        if row:
            soft.append(row)
    for i, text in enumerate(criteria.get("custom_checks") or []):
        hard.append({
            "ref": f"custom:{i}",
            "content": str(text),
            "weight": "hard",
            "source": "custom",
        })
    return {
        "platform_profile": criteria.get("platform_profile", ""),
        "hard": hard,
        "soft": soft,
    }
