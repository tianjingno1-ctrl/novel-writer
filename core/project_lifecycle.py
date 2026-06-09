"""project.json lifecycle 扩展（无 per-book index.json）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from infra import file_utils

LIFECYCLE_STATUSES = frozenset({"drafting", "writing", "complete", "archived"})


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_project(book_dir: Path) -> dict[str, Any]:
    path = book_dir / "project.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_project(book_dir: Path, doc: dict[str, Any]) -> dict[str, Any]:
    doc["updated_at"] = _now()
    path = book_dir / "project.json"
    file_utils.atomic_write_text(
        path,
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    return doc


def get_lifecycle(book_dir: Path) -> dict[str, Any]:
    doc = load_project(book_dir)
    lc = doc.get("lifecycle")
    if not isinstance(lc, dict):
        lc = {}
    lc.setdefault("status", "drafting")
    lc.setdefault("manuscript_id", None)
    lc.setdefault("deconstruct_refs", [])
    return lc


def update_lifecycle(book_dir: Path, fields: dict[str, Any]) -> dict[str, Any]:
    doc = load_project(book_dir)
    lc = get_lifecycle(book_dir)
    if "status" in fields:
        st = str(fields["status"] or "").strip()
        if st and st not in LIFECYCLE_STATUSES:
            raise ValueError(f"无效 lifecycle.status: {st}")
        if st:
            lc["status"] = st
    if "manuscript_id" in fields:
        val = fields["manuscript_id"]
        lc["manuscript_id"] = (str(val).strip() or None) if val else None
    if "deconstruct_refs" in fields and isinstance(fields["deconstruct_refs"], list):
        lc["deconstruct_refs"] = [str(x).strip() for x in fields["deconstruct_refs"] if str(x).strip()]
    doc["lifecycle"] = lc
    save_project(book_dir, doc)
    return lc


def add_deconstruct_ref(book_dir: Path, deconstruct_id: str) -> dict[str, Any]:
    lc = get_lifecycle(book_dir)
    refs = list(lc.get("deconstruct_refs") or [])
    did = (deconstruct_id or "").strip()
    if did and did not in refs:
        refs.append(did)
    return update_lifecycle(book_dir, {"deconstruct_refs": refs})
