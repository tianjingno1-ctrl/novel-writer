"""按 prompt 节点解析 provider + model（runtime.json 可覆盖）。"""

from __future__ import annotations

from typing import Any, Callable

import infra.config as config
from core import prompt_nodes

# 节点默认 provider（未在 node_models 覆盖时使用）
_NODE_DEFAULT_PROVIDER: dict[str, Callable[[], str]] = {
    "writing.main": lambda: config.PROVIDER,
    "review.platform": lambda: config.QUALITY_PROVIDER,
    "prefill.direction": lambda: config.PROVIDER,
    "prefill.plan": lambda: config.PROVIDER,
    "maintain.summary": lambda: config.SUMMARY_PROVIDER,
    "check.continuity": lambda: config.CHECK_PROVIDER,
    "check.deconstruct": lambda: config.CHECK_PROVIDER,
    "diagnose.prompt": lambda: config.QUALITY_PROVIDER,
}

# 进程内覆盖（由 load_runtime_settings 写入）
NODE_MODEL_OVERRIDES: dict[str, dict[str, str]] = {}

# Web/Settings：是否自动续命 Prompt Cache（替代仅 CLI 后台线程的默认行为）
PROMPT_CACHE_AUTO_REFRESH: bool = False


def default_provider_for_node(node_id: str) -> str:
    fn = _NODE_DEFAULT_PROVIDER.get(node_id)
    if fn is None:
        return config.PROVIDER
    return fn()


def set_node_overrides(overrides: dict[str, dict[str, str]] | None) -> None:
    global NODE_MODEL_OVERRIDES
    NODE_MODEL_OVERRIDES = dict(overrides or {})


def _normalize_entry(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    provider = str(raw.get("provider") or "").strip()
    if not provider or provider not in config.PROVIDERS:
        return None
    model = str(raw.get("model") or "").strip()
    out: dict[str, str] = {"provider": provider}
    if model:
        out["model"] = model
    return out


def validate_node_model_entry(node_id: str, entry: dict[str, Any]) -> dict[str, str]:
    if node_id not in prompt_nodes.NODE_REGISTRY:
        raise ValueError(f"未知节点: {node_id}")
    normalized = _normalize_entry(entry)
    if not normalized:
        raise ValueError(f"节点 {node_id} 的 provider 无效")
    return normalized


def resolve_for_node(node_id: str | None) -> tuple[str, str]:
    """返回 (provider_id, effective_model)。"""
    if node_id and node_id in NODE_MODEL_OVERRIDES:
        entry = NODE_MODEL_OVERRIDES[node_id]
        pid = entry["provider"]
        model = entry.get("model") or config.get_model(pid)
        return pid, model
    if node_id:
        pid = default_provider_for_node(node_id)
        return pid, config.get_model(pid)
    pid = config.resolve_provider(None)
    return pid, config.get_model(pid)


def resolve_provider_for_node(node_id: str | None) -> str:
    return resolve_for_node(node_id)[0]


def resolve_model_for_node(node_id: str | None) -> str:
    return resolve_for_node(node_id)[1]


def list_configurable_nodes() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node_id in sorted(prompt_nodes.NODE_REGISTRY):
        defn = prompt_nodes.NODE_REGISTRY[node_id]
        pid, model = resolve_for_node(node_id)
        cfg = config.get_provider_config(pid)
        override = NODE_MODEL_OVERRIDES.get(node_id)
        rows.append({
            "node_id": node_id,
            "label": defn.label,
            "category": defn.category,
            "provider": pid,
            "provider_name": cfg["name"],
            "model": model,
            "default_provider": default_provider_for_node(node_id),
            "default_model": config.get_model(default_provider_for_node(node_id)),
            "overridden": bool(override),
            "supports_cache": config.supports_prompt_cache(pid),
            "api_key_ok": config.is_api_key_configured(pid),
        })
    return rows


def list_provider_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, cfg in config.PROVIDERS.items():
        rows.append({
            "id": key,
            "name": cfg["name"],
            "model": cfg["model"],
            "supports_cache": bool(cfg.get("supports_cache")),
            "api_key_ok": config.is_api_key_configured(key),
        })
    return rows


def apply_node_models_patch(patch: dict[str, Any]) -> dict[str, dict[str, str]]:
    """合并 node_models 覆盖；空 provider 表示删除该节点覆盖。"""
    merged = dict(NODE_MODEL_OVERRIDES)
    for node_id, entry in (patch or {}).items():
        if node_id not in prompt_nodes.NODE_REGISTRY:
            raise ValueError(f"未知节点: {node_id}")
        if entry is None:
            merged.pop(node_id, None)
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"节点 {node_id} 配置须为对象")
        if not str(entry.get("provider") or "").strip():
            merged.pop(node_id, None)
            continue
        merged[node_id] = validate_node_model_entry(node_id, entry)
    set_node_overrides(merged)
    return merged
