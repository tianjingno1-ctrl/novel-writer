"""作者级风格资产：从单书口味库提炼，开书时可继承（E8 → A4）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from infra import file_utils

_BASE = Path(__file__).resolve().parents[1]
AUTHOR_PROFILE_FILE = _BASE / "library" / "author_profile.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_author_profile() -> dict[str, Any]:
    if not AUTHOR_PROFILE_FILE.is_file():
        return {"version": 1, "updated_at": "", "rules": [], "reader_patterns": [], "books": []}
    try:
        raw = json.loads(AUTHOR_PROFILE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "updated_at": "", "rules": [], "reader_patterns": [], "books": []}
    if not isinstance(raw, dict):
        return {"version": 1, "updated_at": "", "rules": [], "reader_patterns": [], "books": []}
    raw.setdefault("version", 1)
    raw.setdefault("rules", [])
    raw.setdefault("reader_patterns", [])
    raw.setdefault("books", [])
    return raw


def save_author_profile(doc: dict[str, Any]) -> dict[str, Any]:
    AUTHOR_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    doc = dict(doc)
    doc["updated_at"] = _now()
    file_utils.atomic_write_text(
        AUTHOR_PROFILE_FILE,
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    return doc


def extract_from_book(
    *,
    book_id: str,
    book_title: str,
    taste_doc: dict[str, Any],
    reader_pattern: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从本书 taste 提炼可跨书复用的规律。"""
    rules: list[dict[str, Any]] = []
    for row in taste_doc.get("rules") or []:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or "").strip()
        if content:
            rules.append({
                "content": content,
                "weight": row.get("weight") or "soft",
                "source_book_id": book_id,
            })
    prefs = taste_doc.get("preferences") or {}
    for pat in prefs.get("hook_patterns") or []:
        s = str(pat).strip()
        if s:
            rules.append({"content": s, "weight": "soft", "kind": "hook", "source_book_id": book_id})
    for pat in prefs.get("avoid_patterns") or []:
        s = str(pat).strip()
        if s:
            rules.append({"content": s, "weight": "hard", "kind": "avoid", "source_book_id": book_id})

    examples = taste_doc.get("examples") or []
    emotion_nodes: list[str] = []
    for ex in examples:
        if not isinstance(ex, dict):
            continue
        tags = ex.get("tags") or []
        for t in tags:
            s = str(t).strip()
            if s and s not in emotion_nodes:
                emotion_nodes.append(s)
        note = str(ex.get("annotation") or ex.get("note") or "").strip()
        if note and len(note) <= 40 and note not in emotion_nodes:
            emotion_nodes.append(note)

    rp = reader_pattern if isinstance(reader_pattern, dict) else {}
    for key in ("good_emotions", "emotion_nodes"):
        for item in rp.get(key) or []:
            s = str(item).strip()
            if s and s not in emotion_nodes:
                emotion_nodes.append(s)

    profile = load_author_profile()
    seen_rules = {r.get("content") for r in profile.get("rules") or []}
    for r in rules:
        if r["content"] not in seen_rules:
            profile.setdefault("rules", []).append(r)
            seen_rules.add(r["content"])
    if emotion_nodes:
        profile.setdefault("reader_patterns", []).append({
            "book_id": book_id,
            "book_title": book_title,
            "good_emotions": emotion_nodes[:12],
            "extracted_at": _now(),
        })
    books = [b for b in profile.get("books") or [] if b.get("book_id") != book_id]
    books.append({"book_id": book_id, "book_title": book_title, "extracted_at": _now()})
    profile["books"] = books[-20:]
    return save_author_profile(profile)


def apply_to_book_taste(
    book_taste: dict[str, Any],
    *,
    rule_ids: list[str] | None = None,
    inherit_all: bool = True,
) -> dict[str, Any]:
    """将作者资产写入本书 taste（A4 继承）。"""
    profile = load_author_profile()
    selected = profile.get("rules") or []
    if rule_ids:
        id_set = set(rule_ids)
        selected = [r for i, r in enumerate(selected) if str(i) in id_set or r.get("content") in id_set]
    elif not inherit_all:
        selected = []

    out = dict(book_taste) if isinstance(book_taste, dict) else {}
    out.setdefault("rules", [])
    out.setdefault("preferences", {})
    existing = {str(r.get("content")) for r in out["rules"] if isinstance(r, dict)}
    for r in selected:
        c = str(r.get("content") or "").strip()
        if c and c not in existing:
            out["rules"].append({
                "id": f"author-{len(out['rules'])+1}",
                "content": c,
                "weight": r.get("weight") or "soft",
                "source": "author_profile",
            })
            existing.add(c)

    rp_list = profile.get("reader_patterns") or []
    if rp_list:
        latest = rp_list[-1]
        out["reader_pattern"] = {
            "good_emotions": latest.get("good_emotions") or [],
            "source": "author_profile",
        }
    return out
