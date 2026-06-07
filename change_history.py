"""档案变更留痕：基准快照 + change_history.jsonl + 可撤销。"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

import file_utils

_history_lock = threading.Lock()
_data_dir: Path | None = None
_backups_dir: Path | None = None
_tracked: dict[str, dict] = {}
HISTORY_DIR: Path | None = None
BASELINE_DIR: Path | None = None
CHANGE_LOG: Path | None = None
BASELINE_MANIFEST: Path | None = None


def init_history(
    data_dir: Path,
    tracked_files: dict[str, Path],
    *,
    backups_dir: Path | None = None,
) -> None:
    """注册可追踪文件。tier: dynamic | stable | plan"""
    global _data_dir, _backups_dir, _tracked, HISTORY_DIR, BASELINE_DIR, CHANGE_LOG, BASELINE_MANIFEST
    _data_dir = data_dir
    _backups_dir = backups_dir or data_dir / "backups"
    HISTORY_DIR = data_dir / "history"
    BASELINE_DIR = HISTORY_DIR / "baseline"
    CHANGE_LOG = HISTORY_DIR / "change_history.jsonl"
    BASELINE_MANIFEST = BASELINE_DIR / "manifest.json"

    stable = frozenset(
        {"world", "style", "char_static", "characters", "char_current"}
    )
    dynamic = frozenset(
        {
            "char_dynamic",
            "summaries",
            "summaries_recent",
            "summaries_archive",
            "plot_threads",
            "plot_threads_locked",
            "plot_threads_active",
        }
    )
    _tracked = {}
    for key, path in tracked_files.items():
        tier = "plan" if key == "plan" else ("stable" if key in stable else "dynamic")
        if key in dynamic:
            tier = "dynamic"
        _tracked[key] = {"path": path, "tier": tier}


def _read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def resolve_key(path: Path) -> str | None:
    if not _tracked:
        return None
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for key, meta in _tracked.items():
        try:
            if meta["path"].resolve() == resolved:
                return key
        except OSError:
            if meta["path"] == path:
                return key
    return None


def _baseline_copy_path(key: str) -> Path:
    assert BASELINE_DIR is not None
    suffix = _tracked[key]["path"].suffix or ".txt"
    return BASELINE_DIR / f"{key}{suffix}"


def ensure_baseline_snapshot(*, force: bool = False) -> dict:
    """第 0 章基准：首次运行或 force 时，快照所有追踪文件。"""
    assert HISTORY_DIR is not None and BASELINE_DIR is not None
    assert BASELINE_MANIFEST is not None

    with _history_lock:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        if BASELINE_MANIFEST.exists() and not force:
            try:
                return json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        files_meta: dict[str, dict] = {}
        ts = datetime.now().isoformat(timespec="seconds")
        for key, meta in _tracked.items():
            path = meta["path"]
            content = _read_file(path)
            dest = _baseline_copy_path(key)
            file_utils.atomic_write_text(dest, content)
            files_meta[key] = {
                "path": str(path.relative_to(_data_dir) if _data_dir else path),
                "tier": meta["tier"],
                "chars": len(content),
            }

        manifest = {
            "chapter_num": 0,
            "label": "第0章基准版本",
            "created_at": ts,
            "files": files_meta,
        }
        file_utils.atomic_write_text(
            BASELINE_MANIFEST,
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        return manifest


def _append_log(record: dict) -> str:
    assert CHANGE_LOG is not None
    CHANGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry_id = record.setdefault("id", uuid.uuid4().hex)
    with CHANGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return entry_id


def _load_all_entries() -> list[dict]:
    assert CHANGE_LOG is not None
    if not CHANGE_LOG.exists():
        return []
    entries: list[dict] = []
    for line in CHANGE_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _reverted_ids(entries: list[dict]) -> set[str]:
    ids: set[str] = set()
    for e in entries:
        rid = e.get("revert_of")
        if rid:
            ids.add(str(rid))
    return ids


def save_with_history(
    path: Path,
    new_content: str,
    *,
    append: bool = False,
    source: str = "unknown",
    chapter_num: int | None = None,
    file_key: str | None = None,
) -> str | None:
    """
    写入并留痕。返回变更记录 id；无变化或未追踪时返回 None。
    调用方须已处理 backup（或本函数内统一 backup）。
    """
    key = file_key or resolve_key(path)
    if not key or key not in _tracked:
        return None

    old_content = _read_file(path)
    after_content = f"{old_content}{new_content}" if append else new_content
    if old_content == after_content:
        return None

    meta = _tracked[key]
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "chapter_num": chapter_num if chapter_num is not None else 0,
        "file_key": key,
        "tier": meta["tier"],
        "path": str(path),
        "op": "append" if append else "replace",
        "source": source,
        "before": old_content,
        "after": after_content,
    }
    with _history_lock:
        file_utils.backup_file(path, _backups_dir or path.parent / "backups")
        file_utils.atomic_write_text(path, after_content)
        entry_id = _append_log(record)
    return entry_id


def list_history(*, file_key: str | None = None, limit: int = 200) -> dict:
    entries = _load_all_entries()
    reverted = _reverted_ids(entries)
    active = [e for e in entries if e.get("id") not in reverted]
    if file_key:
        active = [e for e in active if e.get("file_key") == file_key]
    active.sort(key=lambda e: e.get("ts", ""), reverse=True)
    active = active[:limit]

    by_file: dict[str, list[dict]] = {}
    for e in active:
        fk = e.get("file_key", "?")
        by_file.setdefault(fk, []).append(_public_entry(e))

    summary: dict[str, dict] = {}
    for key, meta in _tracked.items():
        file_entries = by_file.get(key, [])
        last = file_entries[0] if file_entries else None
        summary[key] = {
            "tier": meta["tier"],
            "change_count": len(file_entries),
            "last_change": _public_entry(last) if last else None,
            "unchanged_since_baseline": len(file_entries) == 0,
        }

    return {
        "ok": True,
        "baseline": get_baseline_info(),
        "summary": summary,
        "by_file": by_file,
        "entries": [_public_entry(e) for e in active],
    }


def _public_entry(entry: dict | None) -> dict | None:
    if not entry:
        return None
    before = entry.get("before", "")
    after = entry.get("after", "")
    return {
        "id": entry.get("id"),
        "ts": entry.get("ts"),
        "chapter_num": entry.get("chapter_num"),
        "file_key": entry.get("file_key"),
        "tier": entry.get("tier"),
        "op": entry.get("op"),
        "source": entry.get("source"),
        "revert_of": entry.get("revert_of"),
        "before_chars": len(before),
        "after_chars": len(after),
        "before_preview": before[:200].replace("\n", " "),
        "after_preview": after[:200].replace("\n", " "),
    }


def get_entry(entry_id: str) -> dict:
    for e in _load_all_entries():
        if e.get("id") == entry_id:
            reverted = entry_id in _reverted_ids(_load_all_entries())
            return {
                "ok": True,
                "entry": e,
                "reverted": reverted,
            }
    return {"ok": False, "error": "记录不存在"}


def revert_entry(entry_id: str, *, chapter_num: int | None = None) -> dict:
    """撤销一次变更：将文件恢复为 entry.before。"""
    detail = get_entry(entry_id)
    if not detail.get("ok"):
        return detail
    if detail.get("reverted"):
        return {"ok": False, "error": "该变更已撤销过"}
    entry = detail["entry"]
    key = entry.get("file_key")
    if not key or key not in _tracked:
        return {"ok": False, "error": "无法定位文件"}
    path = _tracked[key]["path"]
    before = entry.get("before", "")
    current = _read_file(path)
    if current == before:
        _append_log(
            {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "chapter_num": chapter_num or 0,
                "file_key": key,
                "tier": entry.get("tier"),
                "path": str(path),
                "op": "revert",
                "source": "revert",
                "revert_of": entry_id,
                "before": current,
                "after": before,
            }
        )
        return {"ok": True, "file_key": key, "message": "内容已是撤销目标状态"}

    with _history_lock:
        backups = _backups_dir or path.parent / "backups"
        file_utils.backup_file(path, backups)
        if key == "plan":
            import novel_data

            novel_data.restore_plan_json_text(before)
        else:
            file_utils.atomic_write_text(path, before)
        new_id = _append_log(
            {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "chapter_num": chapter_num or entry.get("chapter_num", 0),
                "file_key": key,
                "tier": entry.get("tier"),
                "path": str(path),
                "op": "revert",
                "source": "revert",
                "revert_of": entry_id,
                "before": current,
                "after": before,
            }
        )
    return {"ok": True, "file_key": key, "revert_entry_id": new_id}


def get_baseline_info() -> dict:
    if BASELINE_MANIFEST is None or not BASELINE_MANIFEST.exists():
        return {"exists": False}
    try:
        data = json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8"))
        return {"exists": True, **data}
    except (json.JSONDecodeError, OSError):
        return {"exists": False}
