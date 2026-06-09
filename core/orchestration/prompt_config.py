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
    clear: bool = False,
) -> dict:
    result = prompt_nodes.save_node_override(
        _book_dir(ctx), node_id, system=system, clear=clear,
    )
    if not result.get("ok"):
        return result
    return get_node(ctx, node_id)
