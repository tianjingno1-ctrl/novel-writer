"""审阅 Prompt 路由：书型 × 平台 → docs/review-prompts/*.md"""

from __future__ import annotations

from pathlib import Path

_BASE = Path(__file__).resolve().parent
PROMPTS_DIR = _BASE / "docs" / "review-prompts"
LEGACY_PROMPT = _BASE / "docs" / "female-fiction-review-prompt.md"
BASE_FRAGMENT = "{{BASE}}"
WORLD_TOMATO_FRAGMENT = "{{WORLD_TOMATO}}"
REVISE_APPENDIX_FILE = PROMPTS_DIR / "_revise-appendix.md"
REWRITE_ONLY_MARKER = "mode: rewrite-only"

# 直改稿 profile：system 已含全文重写规则，不再拼接 _revise-appendix
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


def resolve_profile_id(
    book_type: str | None = None,
    platform: str | None = None,
) -> str:
    """按书型+平台解析 profile id，带降级链。"""
    bt = normalize_book_type(book_type)
    pf = normalize_platform(platform)
    for candidate in (f"{bt}-{pf}", f"{bt}-general", "default"):
        if (PROMPTS_DIR / f"{candidate}.md").exists():
            return candidate
    return "default"


def profile_label(profile_id: str) -> str:
    parts = profile_id.split("-", 1)
    if len(parts) == 2:
        bt, pf = parts
        return f"{BOOK_TYPE_LABELS.get(bt, bt)} · {PLATFORM_LABELS.get(pf, pf)}"
    return profile_id


def _load_base_body() -> str:
    base_path = PROMPTS_DIR / "_base.md"
    if base_path.exists():
        return base_path.read_text(encoding="utf-8").strip()
    if LEGACY_PROMPT.exists():
        return LEGACY_PROMPT.read_text(encoding="utf-8").strip()
    return "你是一位女频网文审阅编辑，请按钩子、人设、爽点、节奏审阅用户材料。"


def _load_world_tomato_body() -> str:
    path = PROMPTS_DIR / "world-tomato.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return _load_base_body()


def is_rewrite_only_profile(profile_id: str | None) -> bool:
    pid = (profile_id or "").strip()
    if pid in REWRITE_ONLY_PROFILES:
        return True
    path = PROMPTS_DIR / f"{pid}.md"
    if path.exists() and REWRITE_ONLY_MARKER in path.read_text(encoding="utf-8"):
        return True
    return False


def load_revise_appendix() -> str:
    if REVISE_APPENDIX_FILE.exists():
        return REVISE_APPENDIX_FILE.read_text(encoding="utf-8").strip()
    return ""


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
    """加载审阅 system prompt，返回 (正文, profile_id)。include_revise 时拼接改稿附录。"""
    pid = (profile_id or "").strip()
    if not pid and project:
        pid = resolve_profile_id(project.get("type"), project.get("platform"))
    if not pid:
        pid = "default"

    path = PROMPTS_DIR / f"{pid}.md"
    if not path.exists():
        pid = resolve_profile_id(None, None)
        path = PROMPTS_DIR / f"{pid}.md"

    if path.exists():
        text = _expand_prompt_fragments(path.read_text(encoding="utf-8"))
        text = text.strip()
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
    """列出可选审阅 profile（不含 _base）。"""
    rows: list[dict] = []
    if not PROMPTS_DIR.is_dir():
        return rows
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        if path.name.startswith("_"):
            continue
        pid = path.stem
        rows.append(
            {
                "id": pid,
                "label": profile_label(pid),
                "file": str(path.relative_to(_BASE)).replace("\\", "/"),
            }
        )
    return rows


def active_profile_for_project(project: dict) -> dict:
    """当前书默认应使用的 profile 信息。"""
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
