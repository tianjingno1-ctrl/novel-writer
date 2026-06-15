"""稿件（IP）生命周期：状态机与持久化。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from infra import file_utils

_BASE = Path(__file__).resolve().parents[1]
MANUSCRIPTS_DIR = _BASE / "library" / "manuscripts"
INDEX_FILE = MANUSCRIPTS_DIR / "index.json"

VALID_STATES = frozenset({
    "draft",
    "complete",
    "submitting",
    "result",
    "revising",
})

SUBMISSION_TARGETS = frozenset({"text_editor", "comic_drama", "short_drama"})

# state -> allowed next states
TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"complete"}),
    "complete": frozenset({"submitting"}),
    "submitting": frozenset({"result"}),
    "result": frozenset({"revising", "complete", "submitting"}),
    "revising": frozenset({"complete", "submitting", "draft"}),
}

DEFAULT_MANUSCRIPT = {
    "id": "",
    "book_id": "",
    "title": "",
    "state": "draft",
    "language": "zh",
    "market_tags": [],
    "ip_tags": [],
    "submissions": [],
    "versions": [],
    "created_at": "",
    "updated_at": "",
    "notes": "",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ms_id() -> str:
    return f"ms-{uuid.uuid4().hex[:10]}"


def _sub_id() -> str:
    return f"sub-{uuid.uuid4().hex[:8]}"


def _load_index() -> dict:
    if not INDEX_FILE.is_file():
        return {"version": 1, "manuscripts": []}
    try:
        raw = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "manuscripts": []}
    if not isinstance(raw, dict):
        return {"version": 1, "manuscripts": []}
    raw.setdefault("version", 1)
    raw.setdefault("manuscripts", [])
    return raw


def _save_index(data: dict) -> None:
    MANUSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    file_utils.atomic_write_text(
        INDEX_FILE,
        json.dumps(data, ensure_ascii=False, indent=2),
    )


def _manuscript_path(manuscript_id: str) -> Path:
    return MANUSCRIPTS_DIR / f"{manuscript_id}.json"


def _index_row(doc: dict) -> dict:
    return {
        "id": doc.get("id", ""),
        "book_id": doc.get("book_id", ""),
        "title": doc.get("title", ""),
        "state": doc.get("state", "draft"),
        "updated_at": doc.get("updated_at", ""),
        "created_at": doc.get("created_at", ""),
    }


def _write_doc(doc: dict) -> None:
    mid = doc.get("id", "")
    if not mid:
        raise ValueError("manuscript id 为空")
    MANUSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    file_utils.atomic_write_text(
        _manuscript_path(mid),
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    index = _load_index()
    rows = [r for r in index.get("manuscripts") or [] if r.get("id") != mid]
    rows.append(_index_row(doc))
    rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    index["manuscripts"] = rows
    _save_index(index)


def load_manuscript(manuscript_id: str) -> dict | None:
    path = _manuscript_path((manuscript_id or "").strip())
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def _submission_summary(entry: dict) -> dict:
    return {
        "id": entry.get("id", ""),
        "target": entry.get("target", ""),
        "target_name": entry.get("target_name", ""),
        "platform_profile": entry.get("platform_profile", ""),
        "submitted_at": entry.get("submitted_at", ""),
        "result": entry.get("result", ""),
        "reject_reason": entry.get("reject_reason", ""),
        "reject_tags": list(entry.get("reject_tags") or []),
        "reject_kind": entry.get("reject_kind", ""),
        "diagnosis_id": entry.get("diagnosis_id", ""),
        "compliance_checked": bool(entry.get("compliance_checked")),
    }


def _last_pending_submission(doc: dict) -> dict | None:
    subs = doc.get("submissions") or []
    if not subs:
        return None
    last = subs[-1]
    if str(last.get("result") or "").strip():
        return None
    return last


def patch_last_submission(manuscript_id: str, fields: dict[str, Any]) -> dict:
    doc = load_manuscript(manuscript_id)
    if not doc:
        return {"ok": False, "error": "稿件不存在"}
    subs = doc.get("submissions") or []
    if not subs:
        return {"ok": False, "error": "无投递记录"}
    entry = subs[-1]
    for key, value in fields.items():
        if value is not None:
            entry[key] = value
    doc["updated_at"] = _now()
    _write_doc(doc)
    return {"ok": True, "manuscript": doc}


def list_manuscripts(*, book_id: str | None = None) -> list[dict]:
    index = _load_index()
    rows = list(index.get("manuscripts") or [])
    if book_id:
        rows = [r for r in rows if r.get("book_id") == book_id]
    enriched: list[dict] = []
    for row in rows:
        item = dict(row)
        doc = load_manuscript(str(row.get("id") or ""))
        if doc:
            subs = doc.get("submissions") or []
            if subs:
                summary = _submission_summary(subs[-1])
                item["submission"] = summary
                item["last_submission"] = summary
        enriched.append(item)
    return enriched


def create_from_book(
    *,
    book_id: str,
    title: str,
    snapshot_note: str = "",
) -> dict:
    book_id = (book_id or "").strip()
    if not book_id:
        return {"ok": False, "error": "book_id 不能为空"}
    now = _now()
    doc = {
        **DEFAULT_MANUSCRIPT,
        "id": _ms_id(),
        "book_id": book_id,
        "title": (title or "").strip() or "未命名稿件",
        "state": "draft",
        "created_at": now,
        "updated_at": now,
        "versions": [
            {
                "version": 1,
                "created_at": now,
                "note": snapshot_note or "从写作项目交接",
            }
        ],
    }
    _write_doc(doc)
    return {"ok": True, "manuscript": doc}


def transition_state(manuscript_id: str, new_state: str) -> dict:
    doc = load_manuscript(manuscript_id)
    if not doc:
        return {"ok": False, "error": "稿件不存在"}
    new_state = (new_state or "").strip()
    if new_state not in VALID_STATES:
        return {"ok": False, "error": f"无效状态: {new_state}"}
    current = doc.get("state", "draft")
    allowed = TRANSITIONS.get(current, frozenset())
    if new_state not in allowed and new_state != current:
        return {
            "ok": False,
            "error": f"不允许从 {current} 转到 {new_state}",
            "allowed": sorted(allowed),
        }
    doc["state"] = new_state
    doc["updated_at"] = _now()
    _write_doc(doc)
    return {"ok": True, "manuscript": doc}


def update_manuscript(manuscript_id: str, fields: dict[str, Any]) -> dict:
    doc = load_manuscript(manuscript_id)
    if not doc:
        return {"ok": False, "error": "稿件不存在"}

    if "state" in fields:
        tr = transition_state(manuscript_id, str(fields["state"]))
        if not tr.get("ok"):
            return tr
        doc = tr["manuscript"]

    for key in ("title", "notes", "language"):
        if key in fields and fields[key] is not None:
            doc[key] = str(fields[key]).strip()
    for key in ("market_tags", "ip_tags"):
        if key in fields and isinstance(fields[key], list):
            doc[key] = [str(x).strip() for x in fields[key] if str(x).strip()]

    if "submission" in fields and isinstance(fields["submission"], dict):
        sub = fields["submission"]
        target = str(sub.get("target") or sub.get("target_type") or "").strip()
        pending = _last_pending_submission(doc)
        if pending and str(sub.get("result") or "").strip():
            entry = pending
            if target:
                entry["target"] = target
            if sub.get("target_name"):
                entry["target_name"] = str(sub.get("target_name") or "").strip()
            if sub.get("platform_profile"):
                entry["platform_profile"] = str(sub.get("platform_profile") or "").strip()
            entry["result"] = str(sub.get("result", "")).strip()
            entry["reject_reason"] = str(sub.get("reject_reason", "")).strip()
            entry["reject_tags"] = [
                str(t).strip()
                for t in (sub.get("reject_tags") or [])
                if str(t).strip()
            ]
            if sub.get("reject_kind") or sub.get("rejection_kind"):
                entry["reject_kind"] = str(
                    sub.get("reject_kind") or sub.get("rejection_kind") or ""
                ).strip()
            if sub.get("notes"):
                entry["notes"] = str(sub.get("notes", "")).strip()[:500]
            if sub.get("compliance_checked"):
                entry["compliance_checked"] = True
        else:
            if target and target not in SUBMISSION_TARGETS:
                return {
                    "ok": False,
                    "error": f"无效投递类型: {target}；允许: {', '.join(sorted(SUBMISSION_TARGETS))}",
                }
            entry = {
                "id": _sub_id(),
                "target": target,
                "target_name": str(sub.get("target_name") or "").strip(),
                "platform_profile": str(sub.get("platform_profile") or "").strip(),
                "submitted_at": str(sub.get("submitted_at") or "").strip() or _now(),
                "result": str(sub.get("result", "")).strip(),
                "reject_reason": str(sub.get("reject_reason", "")).strip(),
                "reject_tags": [
                    str(t).strip()
                    for t in (sub.get("reject_tags") or [])
                    if str(t).strip()
                ],
                "reject_kind": str(
                    sub.get("reject_kind") or sub.get("rejection_kind") or ""
                ).strip(),
                "notes": str(sub.get("notes", "")).strip()[:500],
                "pushed_to_taste": False,
                "compliance_checked": bool(sub.get("compliance_checked")),
            }
            doc.setdefault("submissions", []).append(entry)

        result_val = str(entry.get("result") or "").strip().lower()
        if entry.get("result"):
            doc["state"] = "result"
        elif doc.get("state") == "complete":
            doc["state"] = "submitting"
        if result_val in ("rejected", "reject", "拒稿", "failed"):
            entry["pushed_to_taste"] = True

    if "revision" in fields and isinstance(fields["revision"], dict):
        rev = fields["revision"]
        doc.setdefault("revisions", []).append({
            "at": _now(),
            "summary": str(rev.get("summary", "")).strip()[:500],
            "related_log_ids": rev.get("related_log_ids") or [],
        })
        if doc.get("state") in ("result", "complete"):
            doc["state"] = "revising"

    doc["updated_at"] = _now()
    _write_doc(doc)
    return {"ok": True, "manuscript": doc}
