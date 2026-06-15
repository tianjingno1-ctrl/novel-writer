# 章 role 外置配置：`library/profiles/chapter_roles/*.yaml`，供 L1b/L2/L4/L5b overlay；与口味库、审阅 RuleRef 无关。
"""章 role profile：`library/profiles/chapter_roles/*.yaml`（v1.0 外置配置）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from core import chapter_roles

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parents[1]
PROFILES_DIR = _BASE / "library" / "profiles" / "chapter_roles"

_CACHE: dict[str, dict[str, Any]] | None = None


def ensure_profiles_dir() -> Path:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILES_DIR


def _profile_path(role: str) -> Path:
    rid = chapter_roles.normalize_role(role)
    if not rid:
        raise ValueError(f"无效 chapter role: {role}")
    return PROFILES_DIR / f"{rid}.yaml"


def load_role_profile(role: str, *, reload: bool = False) -> dict[str, Any] | None:
    rid = chapter_roles.normalize_role(role)
    if not rid:
        return None
    global _CACHE
    if reload:
        _CACHE = None
    if _CACHE is not None and rid in _CACHE:
        return dict(_CACHE[rid])
    path = _profile_path(rid)
    if not path.is_file():
        logger.warning("chapter role profile 缺失: %s", path)
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("读取 chapter role profile 失败 %s: %s", path, exc)
        return None
    if not isinstance(raw, dict):
        return None
    raw.setdefault("id", rid)
    if _CACHE is None:
        _CACHE = {}
    _CACHE[rid] = raw
    return dict(raw)


def load_all_role_profiles(*, reload: bool = False) -> dict[str, dict[str, Any]]:
    if reload:
        global _CACHE
        _CACHE = {}
    out: dict[str, dict[str, Any]] = {}
    for role in chapter_roles.CHAPTER_ROLE_ORDER:
        doc = load_role_profile(role)
        if doc:
            out[role] = doc
    return out


def role_label(role: str) -> str:
    doc = load_role_profile(role) or {}
    return str(doc.get("label") or chapter_roles.CHAPTER_ROLE_LABELS.get(role, role))


def role_l4(role: str) -> str:
    doc = load_role_profile(role) or {}
    return str(doc.get("l4") or "").strip()


def role_l1b(role: str) -> dict[str, Any]:
    doc = load_role_profile(role) or {}
    params = doc.get("l1b")
    return dict(params) if isinstance(params, dict) else {}


def role_l2_thresholds(role: str) -> dict[str, float]:
    doc = load_role_profile(role) or {}
    th = doc.get("l2")
    if not isinstance(th, dict):
        return {"high": 0.55, "medium": 0.35}
    return {
        "high": float(th.get("high", 0.55)),
        "medium": float(th.get("medium", 0.35)),
    }


def role_l2_focus(role: str) -> str:
    doc = load_role_profile(role) or {}
    return str(doc.get("l2_focus") or "").strip()


def role_l2_questions(role: str) -> list[str]:
    doc = load_role_profile(role) or {}
    raw = doc.get("l2_questions")
    if not isinstance(raw, list):
        return []
    return [str(q).strip() for q in raw if str(q).strip()]


def role_l5b_priority(role: str) -> str:
    doc = load_role_profile(role) or {}
    return str(doc.get("l5b_priority") or "medium")


def profile_summary(role: str) -> dict[str, Any]:
    doc = load_role_profile(role) or {}
    return {
        "label": role_label(role),
        "l4": role_l4(role),
        "l1b": role_l1b(role),
        "l2": role_l2_thresholds(role),
        "l5b_priority": role_l5b_priority(role),
        "l2_focus": role_l2_focus(role),
        "l2_questions": role_l2_questions(role),
    }
