# 平台/投递 profile 层：`library/profiles/*.yaml`（书型×平台×投递），含审阅模板与 profile 内嵌 rules；与章 role YAML 不是同一目录。
"""平台审阅 profile（标准层）：library/profiles/*.yaml"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parents[1]
PROFILES_DIR = _BASE / "library" / "profiles"

SUBMISSION_TARGETS = frozenset({"text_editor", "comic_drama", "short_drama"})


def ensure_profiles_dir() -> Path:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILES_DIR


def _profile_path(profile_id: str) -> Path:
    pid = (profile_id or "").strip()
    if not pid:
        raise ValueError("profile_id 不能为空")
    return PROFILES_DIR / f"{pid}.yaml"


def load_profile(profile_id: str) -> dict[str, Any] | None:
    path = _profile_path(profile_id)
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("读取 profile 失败 %s: %s", path, exc)
        return None
    if not isinstance(raw, dict):
        return None
    raw.setdefault("id", profile_id)
    return raw


def list_profiles() -> list[dict[str, Any]]:
    ensure_profiles_dir()
    rows: list[dict[str, Any]] = []
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(raw, dict):
            continue
        rows.append({
            "id": raw.get("id") or path.stem,
            "platform": raw.get("platform", ""),
            "submission_target": raw.get("submission_target", ""),
            "book_types": raw.get("book_types") or [],
            "review_prompt_id": raw.get("review_prompt_id", ""),
        })
    return rows


def _profile_matches(
    profile: dict[str, Any],
    *,
    book_type: str,
    platform: str,
    submission_target: str,
) -> bool:
    types = profile.get("book_types") or []
    if types:
        allowed = {str(t).strip().lower() for t in types}
        bt = book_type if book_type != "world" else "novel"
        if bt not in allowed and not (bt == "novel" and "world" in allowed):
            return False
    pf = str(profile.get("platform") or "").strip().lower()
    if pf and pf != platform:
        return False
    st = str(profile.get("submission_target") or "text_editor").strip().lower()
    if st != submission_target:
        return False
    return True


def resolve_default_profile_id(
    *,
    book_type: str = "short",
    platform: str = "tomato",
    submission_target: str = "text_editor",
) -> str:
    """按书型×平台×投递类型匹配 profile；无则回退 review_prompts 路由 id。"""
    ensure_profiles_dir()
    bt = (book_type or "short").strip().lower()
    if bt == "world":
        bt = "novel"
    pf = (platform or "tomato").strip().lower()
    st = (submission_target or "text_editor").strip().lower()

    scored: list[tuple[int, str]] = []
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        profile = load_profile(path.stem)
        if not profile:
            continue
        if not _profile_matches(profile, book_type=bt, platform=pf, submission_target=st):
            continue
        pid = str(profile.get("id") or path.stem)
        score = 0
        types = profile.get("book_types") or []
        if types and bt in {str(t).strip().lower() for t in types}:
            score += 10
        if str(profile.get("platform") or "").strip().lower() == pf:
            score += 5
        if f"{bt}" in pid or f"_{bt}_" in pid:
            score += 3
        scored.append((score, pid))
    if scored:
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored[0][1]

    candidates = [
        f"{pf}_{bt}_{st}_v1",
        f"{pf}_{st}_v1",
        f"{bt}_{pf}_{st}_v1",
        f"{pf}_text_editor_v1",
    ]
    for cid in candidates:
        if load_profile(cid):
            return cid

    import review_prompts

    return review_prompts.resolve_profile_id(bt, pf)


def get_check_by_id(profile: dict[str, Any], check_id: str) -> dict[str, Any] | None:
    checks = profile.get("checks") or {}
    for bucket in ("hard", "soft"):
        for row in checks.get(bucket) or []:
            if isinstance(row, dict) and row.get("id") == check_id:
                return {**row, "weight": bucket}
    return None


def resolve_profile_rule_ref(profile_id: str, check_id: str) -> dict[str, Any] | None:
    profile = load_profile(profile_id)
    if not profile:
        return None
    row = get_check_by_id(profile, check_id)
    if not row:
        return None
    return {
        "ref": f"profile:{check_id}",
        "content": str(row.get("content") or "").strip(),
        "weight": row.get("weight", "hard"),
        "source": "profile",
        "profile_id": profile_id,
    }


def build_criteria_from_profile(profile_id: str) -> dict[str, Any]:
    profile = load_profile(profile_id)
    if not profile:
        return {
            "platform_profile": profile_id,
            "hard_rules": [],
            "soft_rules": [],
            "custom_checks": [],
        }
    hard: list[str] = []
    soft: list[str] = []
    checks = profile.get("checks") or {}
    for row in checks.get("hard") or []:
        if isinstance(row, dict) and row.get("id"):
            hard.append(f"profile:{row['id']}")
    for row in checks.get("soft") or []:
        if isinstance(row, dict) and row.get("id"):
            soft.append(f"profile:{row['id']}")
    return {
        "platform_profile": profile_id,
        "hard_rules": hard,
        "soft_rules": soft,
        "custom_checks": [],
    }
