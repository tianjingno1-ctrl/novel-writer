"""Prompt 节点注册表：全局默认 + 每书 prompt_overrides.yaml。"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core import prompts as prompt_loader
import review_prompts

logger = logging.getLogger(__name__)

_OVERRIDES_FILENAME = "prompt_overrides.yaml"


@dataclass(frozen=True)
class PromptNodeDef:
    node_id: str
    label: str
    category: str
    prompt_id: str | None = None
    prompt_id_novel: str | None = None
    review_profile: bool = False
    description: str = ""


# Phase 1 节点清单（可扩展）
NODE_REGISTRY: dict[str, PromptNodeDef] = {
    "writing.main": PromptNodeDef(
        "writing.main", "写作续写", "writing",
        prompt_id="writing",
        prompt_id_novel="writing_novel",
        description="写书对话 system prompt",
    ),
    "review.platform": PromptNodeDef(
        "review.platform", "平台审阅", "review", review_profile=True,
        description="按书 type×platform 路由的女频审阅",
    ),
    "prefill.direction": PromptNodeDef(
        "prefill.direction", "预填故事方向", "prefill",
        prompt_id="prefill_short_direction",
        prompt_id_novel="prefill_novel_direction",
    ),
    "prefill.plan": PromptNodeDef(
        "prefill.plan", "预填章规划", "prefill",
        prompt_id="prefill_short_plan",
        prompt_id_novel="prefill_novel_plan",
    ),
    "maintain.summary": PromptNodeDef(
        "maintain.summary", "生成概述", "maintain", prompt_id="summary",
    ),
    "check.continuity": PromptNodeDef(
        "check.continuity", "连续性检查", "check", prompt_id="check",
    ),
    "check.deconstruct": PromptNodeDef(
        "check.deconstruct", "参考拆文", "check", prompt_id="deconstruct",
    ),
    "diagnose.prompt": PromptNodeDef(
        "diagnose.prompt", "Prompt 归因诊断", "diagnose", prompt_id="prompt_diagnose",
        description="独立诊断，不参与写作",
    ),
}


def list_node_defs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node_id, defn in sorted(NODE_REGISTRY.items()):
        rows.append({
            "node_id": node_id,
            "label": defn.label,
            "category": defn.category,
            "prompt_id": defn.prompt_id,
            "review_profile": defn.review_profile,
            "description": defn.description,
        })
    return rows


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def overrides_path(book_dir: Path) -> Path:
    return book_dir / _OVERRIDES_FILENAME


def load_overrides_doc(book_dir: Path | None) -> dict[str, Any]:
    if not book_dir:
        return {"version": 1, "nodes": {}}
    path = overrides_path(book_dir)
    if not path.is_file():
        return {"version": 1, "nodes": {}}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("读取 prompt_overrides 失败: %s", exc)
        return {"version": 1, "nodes": {}}
    if not isinstance(raw, dict):
        return {"version": 1, "nodes": {}}
    nodes = raw.get("nodes")
    if not isinstance(nodes, dict):
        raw["nodes"] = {}
    raw.setdefault("version", 1)
    return raw


def save_node_override(
    book_dir: Path,
    node_id: str,
    *,
    system: str | None = None,
    clear: bool = False,
) -> dict[str, Any]:
    node_id = (node_id or "").strip()
    if node_id not in NODE_REGISTRY:
        return {"ok": False, "error": f"未知 prompt 节点: {node_id}"}

    doc = load_overrides_doc(book_dir)
    nodes: dict[str, Any] = doc.setdefault("nodes", {})
    if clear or not (system or "").strip():
        nodes.pop(node_id, None)
    else:
        nodes[node_id] = {"system": system.strip()}
    path = overrides_path(book_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    from infra import file_utils

    file_utils.atomic_write_text(
        path,
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
    )
    return {"ok": True, "node_id": node_id, "cleared": clear or not (system or "").strip()}


def _compose_override(base: str, node_override: dict[str, Any]) -> tuple[str, bool]:
    custom = node_override.get("system")
    if isinstance(custom, str) and custom.strip():
        return custom.strip(), True
    prepend = str(node_override.get("prepend") or "").strip()
    append = str(node_override.get("append") or "").strip()
    if prepend or append:
        parts: list[str] = []
        if prepend:
            parts.append(prepend)
        parts.append(base)
        if append:
            parts.append(append)
        return "\n\n".join(parts).strip(), True
    return base, False


def merge_node_override(
    book_dir: Path,
    node_id: str,
    override: dict[str, Any],
) -> dict[str, Any]:
    node_id = (node_id or "").strip()
    if node_id not in NODE_REGISTRY:
        return {"ok": False, "error": f"未知 prompt 节点: {node_id}"}
    if not isinstance(override, dict):
        return {"ok": False, "error": "override 须为对象"}

    doc = load_overrides_doc(book_dir)
    nodes: dict[str, Any] = doc.setdefault("nodes", {})
    cur = nodes.get(node_id) if isinstance(nodes.get(node_id), dict) else {}
    merged: dict[str, Any] = dict(cur)
    for key in ("prepend", "append", "system"):
        if key not in override:
            continue
        val = override.get(key)
        if val is None:
            continue
        text = str(val).strip()
        if key == "system":
            if text:
                merged["system"] = text
            else:
                merged.pop("system", None)
        elif text:
            merged[key] = text
        else:
            merged.pop(key, None)
    if merged:
        nodes[node_id] = merged
    else:
        nodes.pop(node_id, None)
    doc["version"] = max(int(doc.get("version") or 1), 2)
    path = overrides_path(book_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    from infra import file_utils

    file_utils.atomic_write_text(
        path,
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
    )
    return {"ok": True, "node_id": node_id, "override": merged}


@dataclass
class ResolvedPrompt:
    node_id: str
    system: str
    prompt_source: str  # global | book_override | review_profile
    prompt_hash: str
    prompt_id: str | None = None
    profile_id: str | None = None


def _prompt_book_type(project: dict | None) -> str:
    bt = review_prompts.normalize_book_type((project or {}).get("type"))
    if bt == "world":
        return "novel"
    return bt


def _resolve_prompt_id(defn: PromptNodeDef, project: dict | None) -> str:
    bt = _prompt_book_type(project)
    if bt == "novel" and defn.prompt_id_novel:
        return defn.prompt_id_novel
    if defn.prompt_id:
        return defn.prompt_id
    raise ValueError(f"节点 {defn.node_id} 未配置 prompt_id")


def resolve_node(
    node_id: str,
    *,
    book_dir: Path | None = None,
    project: dict | None = None,
    include_revise: bool = False,
) -> ResolvedPrompt:
    node_id = (node_id or "").strip()
    defn = NODE_REGISTRY.get(node_id)
    if not defn:
        raise ValueError(f"未知 prompt 节点: {node_id}")

    if project is None and book_dir is not None:
        proj_path = book_dir / "project.json"
        if proj_path.is_file():
            try:
                import json

                raw = json.loads(proj_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    project = raw
            except (OSError, json.JSONDecodeError):
                project = None

    overrides = load_overrides_doc(book_dir)
    node_override = (overrides.get("nodes") or {}).get(node_id)

    base_text = ""
    prompt_source = "global"
    profile_id: str | None = None
    prompt_id: str | None = None

    if defn.review_profile:
        profile_id = review_prompts.resolve_profile_id(
            (project or {}).get("type"),
            (project or {}).get("platform"),
        )
        base_text, active = review_prompts.load_prompt_text(
            profile_id, project=project, include_revise=include_revise,
        )
        profile_id = active
        prompt_id = active
        prompt_source = "review_profile"
    else:
        prompt_id = _resolve_prompt_id(defn, project)
        base_text = prompt_loader.load_system(prompt_id)
        prompt_source = "global"

    text = base_text
    if isinstance(node_override, dict):
        composed, applied = _compose_override(base_text, node_override)
        if applied:
            text = composed
            prompt_source = "book_override"

    return ResolvedPrompt(
        node_id=node_id,
        system=text,
        prompt_source=prompt_source,
        prompt_hash=_hash_text(text),
        prompt_id=prompt_id,
        profile_id=profile_id,
    )


def prompt_meta_dict(resolved: ResolvedPrompt) -> dict[str, str]:
    meta = {
        "prompt_node": resolved.node_id,
        "prompt_source": resolved.prompt_source,
        "prompt_hash": resolved.prompt_hash,
    }
    if resolved.prompt_id:
        meta["prompt_id"] = resolved.prompt_id
    if resolved.profile_id:
        meta["profile_id"] = resolved.profile_id
    return meta


def merge_log_extra(
    extra: dict | None,
    resolved: ResolvedPrompt | None,
    *,
    outcome: str | None = None,
    issue_tags: list[str] | None = None,
) -> dict:
    out = dict(extra or {})
    if resolved:
        out.update(prompt_meta_dict(resolved))
    if outcome:
        out["outcome"] = outcome
    if issue_tags:
        out["issue_tags"] = [t.strip() for t in issue_tags if t and str(t).strip()]
    return out
