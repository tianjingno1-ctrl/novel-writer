"""拆文结构化存储：library/deconstruct/{id}.json"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from infra import file_utils

_BASE = Path(__file__).resolve().parents[1]
DECONSTRUCT_DIR = _BASE / "library" / "deconstruct"

STATUSES = frozenset({"raw", "reviewed", "elevated"})


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    return f"decon-{uuid.uuid4().hex[:10]}"


def ensure_dir() -> Path:
    DECONSTRUCT_DIR.mkdir(parents=True, exist_ok=True)
    return DECONSTRUCT_DIR


def _path(doc_id: str) -> Path:
    return DECONSTRUCT_DIR / f"{(doc_id or '').strip()}.json"


def load(doc_id: str) -> dict[str, Any] | None:
    path = _path(doc_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def save(doc: dict[str, Any]) -> dict[str, Any]:
    ensure_dir()
    doc_id = str(doc.get("id") or "").strip() or _new_id()
    doc["id"] = doc_id
    doc["updated_at"] = _now()
    file_utils.atomic_write_text(
        _path(doc_id),
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    return doc


def create_from_deconstruct_reply(
    *,
    book_id: str,
    quality_log_id: str,
    reply: str,
    source_title: str = "",
    source_platform: str = "",
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from core import taste as taste_store

    patterns = taste_store._extract_deconstruct_patterns(reply)
    doc = {
        "id": _new_id(),
        "source_title": (source_title or "").strip()[:200],
        "source_platform": (source_platform or "").strip(),
        "source_url": "",
        "quality_log_id": (quality_log_id or "").strip(),
        "book_id": (book_id or "").strip(),
        "created_at": _now(),
        "status": "raw",
        "analysis": analysis or {
            "hook_pattern": "; ".join(patterns.get("hook_patterns") or [])[:500],
            "pacing_notes": "; ".join(patterns.get("structure_notes") or [])[:500],
            "notable_techniques": (patterns.get("hook_patterns") or [])[:8],
        },
        "extracted": {"rules": [], "examples": []},
    }
    return save(doc)


def list_deconstructs(*, book_id: str | None = None, limit: int = 50) -> list[dict]:
    ensure_dir()
    rows: list[dict] = []
    for path in sorted(DECONSTRUCT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, dict):
            continue
        if book_id and raw.get("book_id") != book_id:
            continue
        rows.append(raw)
        if len(rows) >= limit:
            break
    return rows


def set_status(doc_id: str, status: str) -> dict[str, Any]:
    status = (status or "").strip()
    if status not in STATUSES:
        raise ValueError(f"无效 status: {status}")
    doc = load(doc_id)
    if not doc:
        raise ValueError("拆文记录不存在")
    doc["status"] = status
    return save(doc)


def elevate_to_taste(
    doc_id: str,
    *,
    book_dir: Path | None = None,
) -> dict[str, Any]:
    """将拆文分析升格为 global rules（v2）。"""
    from core import taste as taste_store

    doc = load(doc_id)
    if not doc:
        return {"ok": False, "error": "拆文记录不存在"}

    analysis = doc.get("analysis") or {}
    created_rules: list[str] = []
    texts: list[tuple[str, str]] = []

    hook = str(analysis.get("hook_pattern") or "").strip()
    if hook:
        texts.append(("hard", hook))
    pacing = str(analysis.get("pacing_notes") or "").strip()
    if pacing:
        texts.append(("soft", pacing))
    for tech in analysis.get("notable_techniques") or []:
        s = str(tech).strip()
        if s:
            texts.append(("soft", s))

    for weight, content in texts:
        rule = taste_store.add_rule(
            content=content,
            weight=weight,
            source="deconstruct",
            tags=["deconstruct"],
        )
        created_rules.append(rule["id"])

    extracted = doc.setdefault("extracted", {})
    extracted["rules"] = list(dict.fromkeys((extracted.get("rules") or []) + created_rules))
    doc["status"] = "elevated"
    save(doc)

    if book_dir:
        from core import project_lifecycle

        project_lifecycle.add_deconstruct_ref(book_dir, doc_id)

    return {"ok": True, "deconstruct_id": doc_id, "rule_ids": created_rules}
