"""Prompt 节点配置编排。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core import prompt_nodes

if TYPE_CHECKING:
    from app.context import AppContext


def _book_dir(ctx: AppContext) -> Path:
    return ctx.store.paths.data_dir


def _load_project(ctx: AppContext) -> dict:
    import json

    path = _book_dir(ctx) / "project.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def list_nodes(ctx: AppContext) -> dict:
    book_dir = _book_dir(ctx)
    overrides = prompt_nodes.load_overrides_doc(book_dir)
    override_ids = set((overrides.get("nodes") or {}).keys())
    nodes = []
    for row in prompt_nodes.list_node_defs():
        node_id = row["node_id"]
        nodes.append({
            **row,
            "has_override": node_id in override_ids,
        })
    return {"ok": True, "nodes": nodes, "overrides_path": str(prompt_nodes.overrides_path(book_dir))}


def get_node(ctx: AppContext, node_id: str) -> dict:
    book_dir = _book_dir(ctx)
    project = _load_project(ctx)
    try:
        resolved = prompt_nodes.resolve_node(
            node_id, book_dir=book_dir, project=project,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    overrides = prompt_nodes.load_overrides_doc(book_dir)
    override = (overrides.get("nodes") or {}).get(node_id)
    return {
        "ok": True,
        "node_id": resolved.node_id,
        "system": resolved.system,
        "prompt_source": resolved.prompt_source,
        "prompt_hash": resolved.prompt_hash,
        "prompt_id": resolved.prompt_id,
        "profile_id": resolved.profile_id,
        "override": override,
    }


def put_node_override(
    ctx: AppContext,
    node_id: str,
    *,
    system: str | None = None,
    append: str | None = None,
    prepend: str | None = None,
    clear: bool = False,
) -> dict:
    book_dir = _book_dir(ctx)
    if clear:
        result = prompt_nodes.save_node_override(book_dir, node_id, clear=True)
        if not result.get("ok"):
            return result
        return get_node(ctx, node_id)

    patch: dict[str, str] = {}
    if system is not None:
        patch["system"] = system
    if append is not None:
        patch["append"] = append
    if prepend is not None:
        patch["prepend"] = prepend
    if not patch:
        return {"ok": False, "error": "无更新字段"}

    result = prompt_nodes.merge_node_override(book_dir, node_id, patch)
    if not result.get("ok"):
        return result
    return get_node(ctx, node_id)
