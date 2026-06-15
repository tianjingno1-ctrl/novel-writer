"""统一路径 fixture，替代 test_core 里散落的 main.XXX_FILE patch。"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import app.paths as app_paths
import main

# main / app.paths 共用的路径键（与 main.py 一致）
PATH_KEYS = (
    "BASE_DIR",
    "DATA_DIR",
    "CHAPTERS_DIR",
    "BACKUPS_DIR",
    "COST_LOG",
    "COST_LOG_JSONL",
    "CONTEXT_LOG_JSONL",
    "SESSION_FILE",
    "SESSION_MD_FILE",
    "WORLD_FILE",
    "STYLE_FILE",
    "CHARACTERS_FILE",
    "CHAR_CURRENT_FILE",
    "CHAR_STATIC_FILE",
    "CHAR_DYNAMIC_FILE",
    "SUMMARIES_FILE",
    "SUMMARIES_ARCHIVE_FILE",
    "SUMMARIES_RECENT_FILE",
    "PLOT_THREADS_FILE",
    "PLOT_THREADS_LOCKED_FILE",
    "PLOT_THREADS_ACTIVE_FILE",
    "OUTLINE_LATEST_FILE",
    "CHAT_PROMPTS_FILE",
    "ARCHIVE_FILE",
)


def snapshot_paths() -> dict[str, object]:
    """保存当前 main + app.paths 路径快照。"""
    snap: dict[str, object] = {}
    for key in PATH_KEYS:
        snap[key] = getattr(main, key, None)
        if hasattr(app_paths, key):
            snap[f"app.{key}"] = getattr(app_paths, key)
    snap["CODEX_FILES"] = dict(main.CODEX_FILES)
    snap["app.CODEX_FILES"] = (
        dict(app_paths.CODEX_FILES) if app_paths.CODEX_FILES else None
    )
    return snap


def restore_paths(snap: dict[str, object]) -> None:
    for key in PATH_KEYS:
        if key in snap:
            setattr(main, key, snap[key])
            if hasattr(app_paths, key):
                setattr(app_paths, key, snap[key])
    if "CODEX_FILES" in snap:
        main.CODEX_FILES = snap["CODEX_FILES"]  # type: ignore[assignment]
    if snap.get("app.CODEX_FILES") is not None:
        app_paths.CODEX_FILES = snap["app.CODEX_FILES"]  # type: ignore[assignment]


def apply_path_dict(paths: dict[str, object]) -> None:
    """同时写入 main 与 app.paths。"""
    for key, val in paths.items():
        if key == "CODEX_FILES":
            main.CODEX_FILES = val  # type: ignore[assignment]
            app_paths.CODEX_FILES = val  # type: ignore[assignment]
            continue
        setattr(main, key, val)
        if hasattr(app_paths, key):
            setattr(app_paths, key, val)


def build_default_paths(base: Path) -> dict[str, object]:
    """在 base 下建默认目录结构。"""
    data = base / "data"
    chapters = data / "chapters"
    backups = data / "backups"
    for d in (data, chapters, backups):
        d.mkdir(parents=True, exist_ok=True)
    codex = {
        "world": data / "world.md",
        "style": data / "style.md",
        "characters": data / "characters.md",
        "char_static": data / "char_static.md",
        "char_dynamic": data / "char_dynamic.md",
        "char_current": data / "char_current.md",
        "summaries_archive": data / "summaries_archive.md",
        "summaries_recent": data / "summaries_recent.md",
        "summaries": data / "summaries.md",
        "plot_threads_locked": data / "plot_threads_locked.md",
        "plot_threads_active": data / "plot_threads_active.md",
        "plot_threads": data / "plot_threads.md",
    }
    return {
        "BASE_DIR": base,
        "DATA_DIR": data,
        "CHAPTERS_DIR": chapters,
        "BACKUPS_DIR": backups,
        "COST_LOG": base / "cost_log.txt",
        "COST_LOG_JSONL": base / "cost_log.jsonl",
        "CONTEXT_LOG_JSONL": data / "context_log.jsonl",
        "SESSION_FILE": data / "session_autosave.json",
        "SESSION_MD_FILE": data / "session_autosave.md",
        "WORLD_FILE": data / "world.md",
        "STYLE_FILE": data / "style.md",
        "CHARACTERS_FILE": data / "characters.md",
        "CHAR_CURRENT_FILE": data / "char_current.md",
        "CHAR_STATIC_FILE": data / "char_static.md",
        "CHAR_DYNAMIC_FILE": data / "char_dynamic.md",
        "SUMMARIES_FILE": data / "summaries.md",
        "SUMMARIES_ARCHIVE_FILE": data / "summaries_archive.md",
        "SUMMARIES_RECENT_FILE": data / "summaries_recent.md",
        "PLOT_THREADS_FILE": data / "plot_threads.md",
        "PLOT_THREADS_LOCKED_FILE": data / "plot_threads_locked.md",
        "PLOT_THREADS_ACTIVE_FILE": data / "plot_threads_active.md",
        "OUTLINE_LATEST_FILE": data / "outline_latest.md",
        "CHAT_PROMPTS_FILE": data / "chat_prompts.json",
        "ARCHIVE_FILE": data / "book_archive.md",
        "CODEX_FILES": codex,
    }


@contextmanager
def patch_paths(tmp_path: Path, **overrides: object) -> Iterator[dict[str, object]]:
    """
    在 with 块内把 main.* 与 app.paths.* 指向 tmp_path 下的隔离目录。
    overrides 可覆盖单个路径键。
    """
    snap = snapshot_paths()
    paths = build_default_paths(tmp_path)
    paths.update(overrides)
    apply_path_dict(paths)
    try:
        yield paths
    finally:
        restore_paths(snap)


@contextmanager
def patch_path_overrides(**overrides: object) -> Iterator[None]:
    """仅覆盖部分路径，不重建整棵树。"""
    snap = snapshot_paths()
    apply_path_dict(overrides)
    try:
        yield
    finally:
        restore_paths(snap)
