"""Prompt 归因持久化：books/{id}/diagnosis/{id}.json"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from infra import file_utils

STATUSES = frozenset({"pending", "accepted", "rejected"})
RERUN_SCOPES = frozenset({"chapter_only", "from_chapter_n", "plan_only", "none"})


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    return f"diag-{uuid.uuid4().hex[:10]}"


def diagnosis_dir(book_dir: Path) -> Path:
    return book_dir / "diagnosis"


def _path(book_dir: Path, doc_id: str) -> Path:
    return diagnosis_dir(book_dir) / f"{(doc_id or '').strip()}.json"


def load(book_dir: Path, doc_id: str) -> dict[str, Any] | None:
    path = _path(book_dir, doc_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def save(book_dir: Path, doc: dict[str, Any]) -> dict[str, Any]:
    diagnosis_dir(book_dir).mkdir(parents=True, exist_ok=True)
    doc_id = str(doc.get("id") or "").strip() or _new_id()
    doc["id"] = doc_id
    doc["updated_at"] = _now()
    file_utils.atomic_write_text(
        _path(book_dir, doc_id),
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    return doc


def create_pending(
    book_dir: Path,
    *,
    book_id: str,
    quality_log_id: str = "",
    trigger: str = "chapter_fail",
    trigger_ref: dict[str, Any] | None = None,
    issue_tags: list[str] | None = None,
    analysis: str = "",
    patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc = {
        "id": _new_id(),
        "book_id": book_id,
        "created_at": _now(),
        "quality_log_id": (quality_log_id or "").strip(),
        "trigger": trigger,
        "trigger_ref": trigger_ref or {},
        "issue_tags": [str(t).strip() for t in (issue_tags or []) if str(t).strip()],
        "analysis": (analysis or "").strip()[:4000],
        "patch": patch or {},
        "decision": {},
        "status": "pending",
    }
    return save(book_dir, doc)


def list_diagnoses(book_dir: Path, *, limit: int = 30) -> list[dict]:
    ddir = diagnosis_dir(book_dir)
    if not ddir.is_dir():
        return []
    rows: list[dict] = []
    for path in sorted(ddir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(raw, dict):
            rows.append(raw)
        if len(rows) >= limit:
            break
    return rows


def decide(
    book_dir: Path,
    doc_id: str,
    *,
    accepted: bool,
    rerun_scope: str = "none",
    rerun_from_chapter_num: int = 0,
    impact_preview: str = "",
    apply_override: bool = True,
) -> dict[str, Any]:
    from core import prompt_nodes
    from core import rerun_scope as rerun_mod

    doc = load(book_dir, doc_id)
    if not doc:
        return {"ok": False, "error": "归因记录不存在"}
    if doc.get("status") != "pending":
        return {"ok": False, "error": f"当前状态不可决策: {doc.get('status')}"}

    scope = (rerun_scope or "none").strip()
    if scope not in RERUN_SCOPES:
        return {"ok": False, "error": f"无效 rerun_scope: {scope}"}

    if not impact_preview and scope != "none":
        plan = __import__("core.plan_product", fromlist=["load_plan"]).load_plan()
        impact_preview = rerun_mod.build_impact_preview(
            plan,
            scope=scope,
            from_chapter_num=rerun_from_chapter_num,
        )

    doc["decision"] = {
        "accepted": bool(accepted),
        "rerun_scope": scope,
        "rerun_from_chapter_num": int(rerun_from_chapter_num or 0),
        "impact_preview": impact_preview,
        "decided_at": _now(),
    }
    doc["status"] = "accepted" if accepted else "rejected"

    override_result: dict[str, Any] | None = None
    if accepted and apply_override:
        patch = doc.get("patch") or {}
        node_id = str(patch.get("target_node") or "").strip()
        override = patch.get("override") if isinstance(patch.get("override"), dict) else {}
        if node_id and override:
            override_result = prompt_nodes.merge_node_override(book_dir, node_id, override)

    save(book_dir, doc)
    out: dict[str, Any] = {"ok": True, "diagnosis": doc}
    if override_result:
        out["override"] = override_result
    if accepted and scope != "none":
        out["rerun"] = rerun_mod.describe_rerun(scope, from_chapter_num=rerun_from_chapter_num)
    return out
