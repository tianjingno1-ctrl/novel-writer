"""plan.json 产品字段：meta、review_criteria、章 status。"""

from __future__ import annotations

from typing import Any

from core.data import novel_data
from core.schemas.rule_refs import parse_rule_ref

CHAPTER_STATUSES = frozenset({"pending", "drafting", "approved"})
DEFAULT_REVIEW_CRITERIA: dict[str, Any] = {
    "platform_profile": "",
    "hard_rules": [],
    "soft_rules": [],
    "custom_checks": [],
}


def load_plan() -> dict:
    return novel_data.load_plan()


def get_meta(plan: dict | None = None) -> dict[str, Any]:
    p = plan if plan is not None else load_plan()
    meta = p.get("meta")
    return dict(meta) if isinstance(meta, dict) else {}


def get_review_criteria(plan: dict | None = None) -> dict[str, Any]:
    p = plan if plan is not None else load_plan()
    raw = p.get("review_criteria")
    if not isinstance(raw, dict):
        return dict(DEFAULT_REVIEW_CRITERIA)
    out = dict(DEFAULT_REVIEW_CRITERIA)
    out.update(raw)
    return out


def set_plan_meta(meta: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(meta, dict):
        raise ValueError("meta 须为对象")

    def _edit(plan: dict) -> None:
        plan["meta"] = meta
        if int(plan.get("version") or 0) < 2:
            plan["version"] = 2

    novel_data._mutate_plan(_edit)
    return get_meta()


def set_review_criteria(fields: dict[str, Any]) -> dict[str, Any]:
    def _edit(plan: dict) -> None:
        cur = get_review_criteria(plan)
        for key in DEFAULT_REVIEW_CRITERIA:
            if key in fields:
                cur[key] = fields[key]
        plan["review_criteria"] = cur
        if int(plan.get("version") or 0) < 2:
            plan["version"] = 2

    novel_data._mutate_plan(_edit)
    return get_review_criteria()


def get_chapter_entry(plan: dict, chapter_num: int) -> dict | None:
    ch = (plan.get("chapters") or {}).get(str(chapter_num))
    return ch if isinstance(ch, dict) else None


def get_chapter_status(plan: dict, chapter_num: int) -> str:
    ch = get_chapter_entry(plan, chapter_num)
    if not ch:
        return "pending"
    status = str(ch.get("status") or "").strip()
    if status in CHAPTER_STATUSES:
        return status
    scenes = ch.get("scenes") or []
    if scenes and all(s.get("done") for s in scenes if isinstance(s, dict)):
        return "drafting"
    return "pending"


def set_chapter_status(chapter_num: int, status: str) -> dict:
    status = (status or "").strip()
    if status not in CHAPTER_STATUSES:
        raise ValueError(f"无效章状态: {status}")

    def _edit(plan: dict) -> None:
        key = str(chapter_num)
        ch = (plan.setdefault("chapters", {})).setdefault(
            key,
            {"title": f"第{chapter_num}章", "scenes": []},
        )
        ch["status"] = status

    novel_data._mutate_plan(_edit)
    return {"chapter_num": chapter_num, "status": status}


def list_chapter_statuses(plan: dict | None = None) -> dict[int, str]:
    p = plan if plan is not None else load_plan()
    out: dict[int, str] = {}
    for key in (p.get("chapters") or {}):
        try:
            num = int(key)
        except (TypeError, ValueError):
            continue
        out[num] = get_chapter_status(p, num)
    return out


def locked_chapter_nums(plan: dict | None = None) -> list[int]:
    return sorted(
        n for n, st in list_chapter_statuses(plan).items() if st == "approved"
    )


def migrate_legacy_brief(data_dir) -> bool:
    """M2：将 legacy brief.md 一次性导入 plan.meta（不双写）。"""
    from pathlib import Path

    book_dir = Path(data_dir)
    brief_path = book_dir / "brief.md"
    if get_meta():
        return False
    if not brief_path.is_file():
        return False
    try:
        legacy = brief_path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not legacy:
        return False
    set_plan_meta({
        "logline": legacy[:4000],
        "migrated_from_brief": True,
    })
    return True


def meta_text_for_prompt(plan: dict | None = None) -> str:
    """供预填/写作注入的方向摘要。"""
    import json

    meta = get_meta(plan)
    if meta:
        return json.dumps(meta, ensure_ascii=False, indent=2)
    return ""


def direction_option_to_meta(option: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(option.get("title") or option.get("logline") or "").strip(),
        "logline": str(option.get("logline") or "").strip(),
        "sell_point": str(option.get("sell_point") or "").strip(),
        "tone": str(option.get("tone") or "").strip(),
        "chapter_count": int(option.get("chapter_count") or 0) or None,
        "word_count_per_chapter": int(option.get("word_count_per_chapter") or 0) or None,
        "option_id": str(option.get("id") or "").strip(),
        "risk_note": str(option.get("risk_note") or "").strip(),
        "characters": option.get("characters") if isinstance(option.get("characters"), list) else [],
    }


def apply_prefill_chapters(option: dict[str, Any], *, replace: bool) -> list[dict]:
    """将预填规划写入 plan.chapters（含 status/hook/target）。"""
    chapters = option.get("chapters")
    if not isinstance(chapters, list):
        raise ValueError("option.chapters 为空")

    applied: list[dict] = []

    def _edit(plan: dict) -> None:
        nonlocal applied
        if replace:
            plan["chapters"] = {}
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            num = int(ch.get("num") or ch.get("chapter_num") or 0)
            if num < 1:
                continue
            key = str(num)
            title = str(ch.get("title") or f"第{num}章").strip()
            beat = str(ch.get("beat") or "").strip()
            if not beat:
                parts = []
                if ch.get("core_event"):
                    parts.append(f"【场景目的】{ch['core_event']}")
                if ch.get("emotion"):
                    parts.append(f"【情绪锚点】{ch['emotion']}")
                if ch.get("hook"):
                    parts.append(f"【结尾钩子】{ch['hook']}")
                beat = "\n".join(parts)
            scene = novel_data.scene_from_workshop_beat(
                num, {"title": title[:14] or "主场景", "beat": beat},
            )
            hook = str(ch.get("hook") or "").strip()
            target = int(ch.get("word_count_target") or ch.get("target_words") or 0)
            plan.setdefault("chapters", {})[key] = {
                "title": title,
                "status": "pending",
                "hook": hook,
                "word_count_target": target or None,
                "scenes": [scene],
            }
            applied.append({
                "chapter_num": num,
                "title": title,
                "scene_id": scene["id"],
                "hook": hook,
            })
        if applied:
            first_key = str(applied[0]["chapter_num"])
            first_scenes = plan["chapters"][first_key].get("scenes") or []
            plan["active_scene_id"] = first_scenes[0]["id"] if first_scenes else None

    novel_data._mutate_plan(_edit)
    return applied


def validate_rule_refs(refs: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in refs or []:
        parse_rule_ref(str(item))
        out.append(str(item).strip())
    return out
