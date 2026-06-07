"""运行时 Bug / 错误日志：按环境（dev / write）分目录，便于双目录调试。"""

from __future__ import annotations

import json
import os
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import file_utils

_lock = threading.Lock()
_base_dir: Path | None = None
_log_path: Path | None = None
_runtime_env: str = "dev"
_MAX_ENTRIES = 800
_MAX_DETAIL_CHARS = 12_000

ENV_LABELS: dict[str, str] = {
    "dev": "开发环境",
    "write": "写作环境",
}

LEVEL_LABELS: dict[str, str] = {
    "error": "错误",
    "warn": "警告",
    "info": "信息",
    "debug": "调试",
}


def detect_runtime_env(base_dir: Path | None = None) -> str:
    """dev = novel_writer；write = novel_writer_write 或 NOVEL_RUNTIME_ENV=write。"""
    explicit = os.environ.get("NOVEL_RUNTIME_ENV", "").strip().lower()
    if explicit in ("write", "prod", "production", "生产", "写作"):
        return "write"
    if explicit in ("dev", "development", "开发", "测试"):
        return "dev"
    root = base_dir or Path(__file__).resolve().parent
    name = root.name.lower()
    if name.endswith("_write") or name.endswith("_prod"):
        return "write"
    return "dev"


def init_runtime_log(base_dir: Path | None = None) -> Path:
    """初始化日志目录；返回当前环境的 jsonl 路径。"""
    global _base_dir, _log_path, _runtime_env
    root = base_dir or Path(__file__).resolve().parent
    _base_dir = root
    _runtime_env = detect_runtime_env(root)
    log_dir = root / "logs" / _runtime_env
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_path = log_dir / "runtime.jsonl"
    return _log_path


def runtime_env() -> str:
    if _log_path is None:
        init_runtime_log()
    return _runtime_env


def runtime_env_label() -> str:
    return ENV_LABELS.get(runtime_env(), runtime_env())


def log_path() -> Path:
    if _log_path is None:
        init_runtime_log()
    return _log_path


def _enabled() -> bool:
    raw = os.environ.get("NOVEL_RUNTIME_LOG", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _should_log_debug() -> bool:
    raw = os.environ.get("NOVEL_RUNTIME_LOG_DEBUG", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    return runtime_env() == "dev"


def append(
    level: str,
    category: str,
    location: str,
    message: str,
    *,
    data: dict | None = None,
    detail: str = "",
    exc: BaseException | None = None,
) -> str | None:
    """追加一条日志；返回 entry id，关闭时返回 None。"""
    if not _enabled():
        return None
    if level == "debug" and not _should_log_debug():
        return None

    entry_id = uuid.uuid4().hex[:12]
    tb = ""
    if exc is not None:
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
        tb = "".join(tb)
    detail_text = (detail or tb or "").strip()
    if len(detail_text) > _MAX_DETAIL_CHARS:
        detail_text = detail_text[:_MAX_DETAIL_CHARS] + "\n…（已截断）"

    entry = {
        "id": entry_id,
        "level": level,
        "level_label": LEVEL_LABELS.get(level, level),
        "category": category,
        "location": location,
        "message": (message or "").strip()[:2000],
        "detail": detail_text,
        "data": data or {},
        "runtime_env": runtime_env(),
        "runtime_env_label": runtime_env_label(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
        _trim_file(path)
    return entry_id


def log_error(
    category: str,
    location: str,
    message: str,
    *,
    data: dict | None = None,
    exc: BaseException | None = None,
) -> str | None:
    return append("error", category, location, message, data=data, exc=exc)


def log_warn(
    category: str,
    location: str,
    message: str,
    *,
    data: dict | None = None,
) -> str | None:
    return append("warn", category, location, message, data=data)


def log_info(
    category: str,
    location: str,
    message: str,
    *,
    data: dict | None = None,
) -> str | None:
    return append("info", category, location, message, data=data)


def log_debug(
    location: str,
    message: str,
    *,
    data: dict | None = None,
    category: str = "debug",
    hypothesis_id: str = "",
) -> str | None:
    payload = dict(data or {})
    if hypothesis_id:
        payload["hypothesisId"] = hypothesis_id
    return append("debug", category, location, message, data=payload)


def log_api_error(
    location: str,
    message: str,
    *,
    kind: str = "",
    provider: str = "",
    tag: str = "",
    exc: BaseException | None = None,
) -> str | None:
    return log_error(
        "api",
        location,
        message,
        data={"kind": kind, "provider": provider, "tag": tag},
        exc=exc,
    )


def list_entries(
    *,
    limit: int = 80,
    level: str | None = None,
    category: str | None = None,
) -> list[dict]:
    path = log_path()
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if level and row.get("level") != level:
            continue
        if category and row.get("category") != category:
            continue
        summary = row.get("message", "")
        body = row.get("detail", "")
        rows.append(
            {
                "id": row.get("id", ""),
                "level": row.get("level", ""),
                "level_label": row.get("level_label", row.get("level", "")),
                "category": row.get("category", ""),
                "location": row.get("location", ""),
                "message": summary,
                "summary": summary[:240],
                "created_at": row.get("created_at", ""),
                "runtime_env": row.get("runtime_env", runtime_env()),
                "runtime_env_label": row.get(
                    "runtime_env_label", runtime_env_label()
                ),
                "has_detail": bool(body),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def get_entry(entry_id: str) -> dict | None:
    path = log_path()
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


def get_status() -> dict:
    path = log_path()
    count = 0
    last_at = ""
    if path.exists():
        try:
            lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            count = len(lines)
            if lines:
                last = json.loads(lines[-1])
                last_at = last.get("created_at", "")
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "runtime_env": runtime_env(),
        "runtime_env_label": runtime_env_label(),
        "log_path": str(path.relative_to(_base_dir or path.parent.parent.parent))
        if _base_dir and path.is_relative_to(_base_dir)
        else str(path),
        "log_enabled": _enabled(),
        "debug_enabled": _should_log_debug(),
        "entry_count": count,
        "last_at": last_at,
    }


def _trim_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= _MAX_ENTRIES:
        return
    keep = lines[-_MAX_ENTRIES:]
    file_utils.atomic_write_text(path, "\n".join(keep) + "\n")
