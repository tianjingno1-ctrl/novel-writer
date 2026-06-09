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


def resolve_default_profile_id(
    *,
    book_type: str = "short",
    platform: str = "tomato",
    submission_target: str = "text_editor",
) -> str:
    """按书型×平台×投递类型匹配 profile；无则回退 review_prompts 路由 id。"""
    ensure_profiles_dir()
    bt = (book_type or "short").strip().lower()
    pf = (platform or "tomato").strip().lower()
    st = (submission_target or "text_editor").strip().lower()

    candidates = [
        f"{pf}_{st}_v1",
        f"{pf}_{bt}_{st}_v1",
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
