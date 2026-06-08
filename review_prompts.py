"""审阅 Prompt 路由：书型 × 平台 → prompts/review/*.yaml（回退 docs/review-prompts/*.md）"""

from __future__ import annotations

from pathlib import Path

import yaml

_BASE = Path(__file__).resolve().parent
REVIEW_PROMPTS_DIR = _BASE / "prompts" / "review"
LEGACY_PROMPTS_DIR = _BASE / "docs" / "review-prompts"
LEGACY_PROMPT = _BASE / "docs" / "female-fiction-review-prompt.md"
BASE_FRAGMENT = "{{BASE}}"
WORLD_TOMATO_FRAGMENT = "{{WORLD_TOMATO}}"
REWRITE_ONLY_MARKER = "mode: rewrite-only"

REWRITE_ONLY_PROFILES = frozenset({"world-tomato", "world-qimao"})

BOOK_TYPES = frozenset({"short", "world", "novel"})
BOOK_TYPE_LABELS = {
    "short": "短篇",
    "world": "快穿",
    "novel": "长篇",
}

PLATFORMS = frozenset({"tomato", "qimao", "jjwxc", "general"})
PLATFORM_LABELS = {
    "tomato": "番茄",
    "qimao": "七猫",
    "jjwxc": "晋江",
    "general": "通用",
}


def normalize_book_type(value: str | None) -> str:
    t = (value or "novel").strip().lower()
    return t if t in BOOK_TYPES else "novel"


def normalize_platform(value: str | None) -> str:
    p = (value or "tomato").strip().lower()
    return p if p in PLATFORMS else "tomato"


def _profile_yaml(profile_id: str) -> Path:
    return REVIEW_PROMPTS_DIR / f"{profile_id}.yaml"


def _profile_md(profile_id: str) -> Path:
    return LEGACY_PROMPTS_DIR / f"{profile_id}.md"


def profile_exists(profile_id: str) -> bool:
    pid = (profile_id or "").strip()
    return _profile_yaml(pid).is_file() or _profile_md(pid).is_file()


def resolve_profile_id(
    book_type: str | None = None,
    platform: str | None = None,
) -> str:
    bt = normalize_book_type(book_type)
    pf = normalize_platform(platform)
    for candidate in (f"{bt}-{pf}", f"{bt}-general", "default"):
        if profile_exists(candidate):
            return candidate
    return "default"


def profile_label(profile_id: str) -> str:
    parts = profile_id.split("-", 1)
    if len(parts) == 2:
        bt, pf = parts
        return f"{BOOK_TYPE_LABELS.get(bt, bt)} · {PLATFORM_LABELS.get(pf, pf)}"
    return profile_id


def _load_yaml_doc(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"审阅 YAML 须为 mapping: {path}")
    return raw


def _load_fragment_body(fragment_id: str) -> str:
    yaml_path = REVIEW_PROMPTS_DIR / f"{fragment_id}.yaml"
    if yaml_path.is_file():
        doc = _load_yaml_doc(yaml_path)
        system = doc.get("system")
        if isinstance(system, str) and system.strip():
            return system.strip()
    md_path = LEGACY_PROMPTS_DIR / f"{fragment_id}.md"
    if md_path.is_file():
        return md_path.read_text(encoding="utf-8").strip()
    if fragment_id == "_base" and LEGACY_PROMPT.is_file():
        return LEGACY_PROMPT.read_text(encoding="utf-8").strip()
    return "你是一位女频网文审阅编辑，请按钩子、人设、爽点、节奏审阅用户材料。"


def _load_base_body() -> str:
    return _load_fragment_body("_base")


def _load_world_tomato_body() -> str:
    if profile_exists("world-tomato"):
        text, _ = _load_profile_raw("world-tomato")
        return text
    return _load_base_body()


def _load_profile_raw(profile_id: str) -> tuple[str, dict | None]:
    """读取 profile 正文（未展开 fragment），返回 (text, yaml_doc|None)。"""
    yaml_path = _profile_yaml(profile_id)
    if yaml_path.is_file():
        doc = _load_yaml_doc(yaml_path)
        system = doc.get("system")
        if not isinstance(system, str) or not system.strip():
            raise ValueError(f"审阅 prompt {profile_id!r} 缺少 system")
        return system.strip(), doc
    md_path = _profile_md(profile_id)
    if md_path.is_file():
        return md_path.read_text(encoding="utf-8").strip(), None
    return _load_base_body(), None


def is_rewrite_only_profile(profile_id: str | None) -> bool:
    pid = (profile_id or "").strip()
    if pid in REWRITE_ONLY_PROFILES:
        return True
    yaml_path = _profile_yaml(pid)
    if yaml_path.is_file():
        doc = _load_yaml_doc(yaml_path)
        if doc.get("mode") == "rewrite-only":
            return True
    md_path = _profile_md(pid)
    if md_path.is_file() and REWRITE_ONLY_MARKER in md_path.read_text(encoding="utf-8"):
        return True
    return False


def load_revise_appendix() -> str:
    return _load_fragment_body("_revise-appendix")


def _expand_prompt_fragments(text: str) -> str:
    if WORLD_TOMATO_FRAGMENT in text:
        text = text.replace(WORLD_TOMATO_FRAGMENT, _load_world_tomato_body())
    if BASE_FRAGMENT in text:
        text = text.replace(BASE_FRAGMENT, _load_base_body())
    return text


def load_prompt_text(
    profile_id: str | None = None,
    *,
    project: dict | None = None,
    include_revise: bool = False,
) -> tuple[str, str]:
    pid = (profile_id or "").strip()
    if not pid and project:
        pid = resolve_profile_id(project.get("type"), project.get("platform"))
    if not pid:
        pid = "default"

    if not profile_exists(pid):
        pid = resolve_profile_id(None, None)

    if profile_exists(pid):
        text = _expand_prompt_fragments(_load_profile_raw(pid)[0])
        rewrite_only = is_rewrite_only_profile(pid)
        if include_revise and not rewrite_only:
            appendix = load_revise_appendix()
            if appendix:
                text = f"{text}\n\n{appendix}"
        return text, pid

    body = _load_base_body()
    if include_revise:
        appendix = load_revise_appendix()
        if appendix:
            body = f"{body}\n\n{appendix}"
    return body, "legacy"


def list_profiles() -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()

    if REVIEW_PROMPTS_DIR.is_dir():
        for path in sorted(REVIEW_PROMPTS_DIR.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            pid = path.stem
            seen.add(pid)
            rows.append(
                {
                    "id": pid,
                    "label": profile_label(pid),
                    "file": str(path.relative_to(_BASE)).replace("\\", "/"),
                }
            )

    if LEGACY_PROMPTS_DIR.is_dir():
        for path in sorted(LEGACY_PROMPTS_DIR.glob("*.md")):
            if path.name.startswith("_"):
                continue
            pid = path.stem
            if pid in seen:
                continue
            rows.append(
                {
                    "id": pid,
                    "label": profile_label(pid),
                    "file": str(path.relative_to(_BASE)).replace("\\", "/"),
                }
            )
    return rows


def active_profile_for_project(project: dict) -> dict:
    bt = normalize_book_type(project.get("type"))
    pf = normalize_platform(project.get("platform"))
    pid = resolve_profile_id(bt, pf)
    return {
        "profile_id": pid,
        "label": profile_label(pid),
        "book_type": bt,
        "book_type_label": BOOK_TYPE_LABELS.get(bt, bt),
        "platform": pf,
        "platform_label": PLATFORM_LABELS.get(pf, pf),
        "rewrite_only": is_rewrite_only_profile(pid),
    }
