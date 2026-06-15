"""Prompt 加载：prompts/*.yaml 与代码分离，改文案无需动业务 .py。"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

LEGACY_NAME_TO_ID: dict[str, str] = {
    "WRITING_INSTRUCTION": "writing",
    "SUMMARY_SYSTEM": "summary",
    "CHECK_SYSTEM": "check",
    "CROSS_CHAPTER_CONTINUITY_SYSTEM": "cross_chapter_continuity",
    "READER_REVIEW_SYSTEM": "reader_review",
    "EDITOR_REVIEW_SYSTEM": "editor_review",
    "DECONSTRUCT_SYSTEM": "deconstruct",
    "OUTLINE_SYSTEM": "outline",
    "CHARACTER_DRIFT_SYSTEM": "character_drift",
    "DETAIL_EXTRACT_SYSTEM": "detail_extract",
    "REPETITION_CHECK_SYSTEM": "repetition_check",
    "PACING_CHECK_SYSTEM": "pacing_check",
    "OBSERVE_SYSTEM": "observe",
    "POST_CHAPTER_MAINTAIN_SYSTEM": "post_chapter_maintain",
    "QUALITY_CHECK_BUNDLE_SYSTEM": "quality_check_bundle",
    "BULK_ARCHIVE_SUMMARIES_SYSTEM": "bulk_archive_summaries",
    "BULK_ARCHIVE_STATE_SYSTEM": "bulk_archive_state",
}


def prompts_dir() -> Path:
    return _PROMPTS_DIR


def list_prompt_ids() -> list[str]:
    if not _PROMPTS_DIR.is_dir():
        return []
    return sorted(p.stem for p in _PROMPTS_DIR.glob("*.yaml"))


@lru_cache(maxsize=64)
def _load_yaml_file(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Prompt 文件不存在: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Prompt YAML 须为 mapping: {path}")
    return raw


def load_prompt_doc(prompt_id: str) -> dict:
    pid = (prompt_id or "").strip()
    if not pid:
        raise ValueError("prompt_id 不能为空")
    path = _PROMPTS_DIR / f"{pid}.yaml"
    doc = _load_yaml_file(path)
    doc.setdefault("id", pid)
    return doc


def load_system(prompt_id: str) -> str:
    doc = load_prompt_doc(prompt_id)
    system = doc.get("system")
    if not isinstance(system, str) or not system.strip():
        raise ValueError(f"Prompt {prompt_id!r} 缺少非空 system 字段")
    text = system.strip()
    return text


def render_user_template(prompt_id: str, **variables: object) -> str:
    doc = load_prompt_doc(prompt_id)
    tpl = doc.get("user_template")
    if not isinstance(tpl, str) or not tpl.strip():
        raise ValueError(f"Prompt {prompt_id!r} 缺少 user_template")

    def _repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        val = variables.get(key, "")
        return "" if val is None else str(val)

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", _repl, tpl)


def reload_prompts() -> None:
    _load_yaml_file.cache_clear()
