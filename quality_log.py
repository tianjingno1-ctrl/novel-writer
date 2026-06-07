"""质量工具运行记录：生成结果持久化，供 Web 侧栏回看。"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

import file_utils

_lock = threading.Lock()
_log_path: Path | None = None
_MAX_BODY_CHARS = 120_000
_MAX_ENTRIES = 500

KIND_LABELS: dict[str, str] = {
    "finalize": "本章定稿",
    "post_chapter_maintain": "章后维护",
    "observe": "角色观察",
    "detail_extract": "提取细节",
    "summary": "生成概述",
    "continuity": "连续性检查",
    "character_drift": "人物检查",
    "repetition": "重复检查",
    "pacing": "爽点检查",
}


def init_quality_log(data_dir: Path) -> None:
    global _log_path
    _log_path = data_dir / "quality_log.jsonl"


def _path() -> Path:
    global _log_path
    if _log_path is None:
        init_quality_log(Path(__file__).resolve().parent / "data")
    return _log_path


def append_entry(
    kind: str,
    chapter_num: int,
    body: str,
    *,
    summary: str = "",
    persisted: bool = False,
    persisted_detail: str = "",
    extra: dict | None = None,
) -> str:
    """追加一条记录，返回 entry id。"""
    entry_id = uuid.uuid4().hex[:12]
    text = (body or "").strip()
    if len(text) > _MAX_BODY_CHARS:
        text = text[: _MAX_BODY_CHARS] + "\n\n…（已截断）"
    entry = {
        "id": entry_id,
        "kind": kind,
        "label": KIND_LABELS.get(kind, kind),
        "chapter_num": int(chapter_num) if chapter_num else 0,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": (summary or "").strip()[:800],
        "body": text,
        "persisted": bool(persisted),
        "persisted_detail": (persisted_detail or "").strip()[:400],
    }
    if extra:
        entry["extra"] = extra
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _lock:
        existing = ""
        if path.exists():
            try:
                existing = path.read_text(encoding="utf-8")
            except OSError:
                existing = ""
        file_utils.atomic_write_text(path, existing + line)
        _trim_if_needed(path)
    return entry_id


def _trim_if_needed(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= _MAX_ENTRIES:
        return
    kept = lines[-_MAX_ENTRIES:]
    file_utils.atomic_write_text(path, "\n".join(kept) + "\n")


def list_entries(*, limit: int = 80, kind: str | None = None) -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    lim = max(1, min(200, limit))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if kind and row.get("kind") != kind:
            continue
        preview = (row.get("body") or "")[:120].replace("\n", " ")
        out.append(
            {
                "id": row.get("id", ""),
                "kind": row.get("kind", ""),
                "label": row.get("label") or KIND_LABELS.get(row.get("kind", ""), ""),
                "chapter_num": row.get("chapter_num", 0),
                "created_at": row.get("created_at", ""),
                "summary": row.get("summary", ""),
                "preview": preview,
                "persisted": row.get("persisted", False),
                "persisted_detail": row.get("persisted_detail", ""),
            }
        )
        if len(out) >= lim:
            break
    return out


def get_entry(entry_id: str) -> dict | None:
    if not entry_id:
        return None
    path = _path()
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("id") == entry_id:
            return row
    return None
