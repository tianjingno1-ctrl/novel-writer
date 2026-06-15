"""书籍设定 md 文件读写（world / style / 人物 / 伏笔 / 概述）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.context import AppContext

MAX_FILE_BYTES = 2 * 1024 * 1024

BOOK_FILE_DEFS: tuple[dict[str, str], ...] = (
    {
        "key": "world",
        "label": "世界观",
        "group": "setting",
        "group_label": "书籍设定",
        "path_attr": "world_file",
        "hint": "节拍、爽点与世界档案（宏观；逐章以 plan Beat 为准）",
    },
    {
        "key": "style",
        "label": "文风锚点",
        "group": "setting",
        "group_label": "书籍设定",
        "path_attr": "style_file",
        "hint": "叙事视角、禁用词、句式节奏",
    },
    {
        "key": "characters",
        "label": "人物总表",
        "group": "setting",
        "group_label": "书籍设定",
        "path_attr": "characters_file",
        "hint": "主要角色关系与设定",
    },
    {
        "key": "char_static",
        "label": "人物锚点",
        "group": "setting",
        "group_label": "书籍设定",
        "path_attr": "char_static_file",
        "hint": "性格锚点与禁止写法（极少改）",
    },
    {
        "key": "char_dynamic",
        "label": "人物动态",
        "group": "setting",
        "group_label": "书籍设定",
        "path_attr": "char_dynamic_file",
        "hint": "当前状态、关系与近期变化",
    },
    {
        "key": "plot_threads_locked",
        "label": "伏笔（已钉死）",
        "group": "archive",
        "group_label": "章后档案",
        "path_attr": "plot_threads_locked_file",
        "hint": "只增不改的细节钉子；Gate 定稿可追加",
    },
    {
        "key": "plot_threads_active",
        "label": "伏笔（活跃）",
        "group": "archive",
        "group_label": "章后档案",
        "path_attr": "plot_threads_active_file",
        "hint": "未回收/已回收伏笔；可手改纠错",
    },
    {
        "key": "summaries_archive",
        "label": "概述（归档）",
        "group": "archive",
        "group_label": "章后档案",
        "path_attr": "summaries_archive_file",
        "hint": "旧章概述归档；Gate L10 确认后剪切",
    },
    {
        "key": "summaries_recent",
        "label": "概述（近期）",
        "group": "archive",
        "group_label": "章后档案",
        "path_attr": "summaries_recent_file",
        "hint": "最近 3–5 章概述；Gate 自动生成，可纠错",
    },
)

_KEYS = frozenset(d["key"] for d in BOOK_FILE_DEFS)

# 短篇：仅书籍设定；长篇/快穿(world)：设定 + 章后档案（每书独立目录，非全局共用）
_SETTING_GROUPS = frozenset({"setting"})


def _book_type_for_ctx(ctx: AppContext) -> str:
    """按当前 ctx.store 指向的书目录读 type，不依赖全局猜书。"""
    import json

    from core.data import book_context

    proj_path = ctx.store.paths.data_dir / "project.json"
    if proj_path.is_file():
        try:
            raw = json.loads(proj_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                t = str(raw.get("type") or "").strip()
                if t in book_context.BOOK_TYPES:
                    return t
        except (OSError, json.JSONDecodeError):
            pass
    try:
        return book_context.get_book_type()
    except RuntimeError:
        return "novel"


def file_defs_for_book(ctx: AppContext) -> tuple[dict[str, str], ...]:
    bt = _book_type_for_ctx(ctx)
    if bt == "short":
        return tuple(r for r in BOOK_FILE_DEFS if r.get("group") in _SETTING_GROUPS)
    return BOOK_FILE_DEFS


def _path_for_key(ctx: AppContext, key: str) -> Path | None:
    k = (key or "").strip().lower()
    if k not in _KEYS:
        return None
    for row in BOOK_FILE_DEFS:
        if row["key"] == k:
            return getattr(ctx.store.paths, row["path_attr"])
    return None


def list_book_files(ctx: AppContext) -> dict[str, Any]:
    bt = _book_type_for_ctx(ctx)
    items: list[dict[str, Any]] = []
    for row in file_defs_for_book(ctx):
        path = getattr(ctx.store.paths, row["path_attr"])
        content = ctx.store.read(path) if path.exists() else ""
        items.append({
            "key": row["key"],
            "label": row["label"],
            "group": row["group"],
            "group_label": row["group_label"],
            "hint": row["hint"],
            "filename": path.name,
            "chars": len(content),
            "exists": path.is_file(),
        })
    scope = "setting_only" if bt == "short" else "full"
    return {"ok": True, "book_type": bt, "scope": scope, "files": items}


def get_book_file(ctx: AppContext, key: str) -> dict[str, Any]:
    k = (key or "").strip().lower()
    allowed = {r["key"] for r in file_defs_for_book(ctx)}
    if k not in allowed:
        return {"ok": False, "error": f"当前书型不可访问该档案: {key}"}
    path = _path_for_key(ctx, key)
    if path is None:
        return {"ok": False, "error": f"未知设定文件: {key}"}
    content = ctx.store.read(path)
    meta = next(r for r in BOOK_FILE_DEFS if r["key"] == key.strip().lower())
    return {
        "ok": True,
        "key": meta["key"],
        "label": meta["label"],
        "group": meta["group"],
        "group_label": meta["group_label"],
        "hint": meta["hint"],
        "filename": path.name,
        "content": content,
        "chars": len(content),
    }


def put_book_file(ctx: AppContext, key: str, content: str) -> dict[str, Any]:
    k = (key or "").strip().lower()
    allowed = {r["key"] for r in file_defs_for_book(ctx)}
    if k not in allowed:
        return {"ok": False, "error": f"当前书型不可编辑该档案: {key}"}
    path = _path_for_key(ctx, key)
    if path is None:
        return {"ok": False, "error": f"未知设定文件: {key}"}
    body = content if content is not None else ""
    if len(body.encode("utf-8")) > MAX_FILE_BYTES:
        mb = MAX_FILE_BYTES // 1024 // 1024
        return {"ok": False, "error": f"内容过大（上限 {mb}MB）"}
    ctx.store.write(path, body, history_source="book_files")
    meta = next(r for r in BOOK_FILE_DEFS if r["key"] == key.strip().lower())
    return {
        "ok": True,
        "key": meta["key"],
        "label": meta["label"],
        "chars": len(body),
    }

