"""费用与变更追踪。"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from core.data import change_history
import infra.config as config
from core.data import novel_data
from app import paths as _paths
from infra.state import state
from infra.providers import TokenUsage

_cost_lock = threading.Lock()


def get_total_cost() -> float:
    return state.total_cost


def set_total_cost(value: float) -> None:
    state.total_cost = value


def _register_change_history() -> None:
    tracked = dict(_paths.resolved_codex_files())
    tracked["plan"] = novel_data.PLAN_FILE
    change_history.init_history(
        _paths.resolved("DATA_DIR"),
        tracked,
        backups_dir=_paths.resolved("BACKUPS_DIR"),
    )


def load_total_cost_from_jsonl(path: Path) -> float:
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            total += float(record.get("cost", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return total


def load_total_cost() -> float:
    cost_log_jsonl = _paths.resolved("COST_LOG_JSONL")
    if cost_log_jsonl.exists():
        return load_total_cost_from_jsonl(cost_log_jsonl)
    cost_log = _paths.resolved("COST_LOG")
    if not cost_log.exists():
        return 0.0
    total = 0.0
    for line in cost_log.read_text(encoding="utf-8").splitlines():
        m = re.search(r"费用:\s*\$?([\d.]+)\b", line)
        if not m:
            continue
        try:
            val = float(m.group(1))
            if 0 <= val < 1000:
                total += val
        except ValueError:
            pass
    return total


def log_cost(
    usage: TokenUsage,
    cost: float,
    tag: str,
    *,
    provider: str | None = None,
    silent: bool = False,
) -> None:
    cache_read = usage.cache_read_input_tokens
    cache_creation = usage.cache_creation_input_tokens
    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    pid = config.resolve_provider(provider)
    cost_log_jsonl = _paths.resolved("COST_LOG_JSONL")
    cost_log = _paths.resolved("COST_LOG")

    with _cost_lock:
        state.total_cost += cost
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        book_id = ""
        try:
            from core.data import book_context

            book_id = book_context.get_context().book_id
        except RuntimeError:
            pass
        record = {
            "ts": ts,
            "tag": tag,
            "provider": pid,
            "book_id": book_id,
            "cache_read": cache_read,
            "cache_write": cache_creation,
            "input": input_tokens,
            "output": output_tokens,
            "cost": round(cost, 6),
            "total_cost": round(state.total_cost, 6),
        }
        with cost_log_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        legacy_line = (
            f"[{ts}] [{tag}] "
            f"cache_read={cache_read} cache_write={cache_creation} "
            f"input={input_tokens} output={output_tokens} "
            f"费用: ${cost:.6f} 累计: ${state.total_cost:.6f}\n"
        )
        with cost_log.open("a", encoding="utf-8") as f:
            f.write(legacy_line)

    if not silent:
        cfg = config.get_provider_config(provider)
        print(f"\n── Token 统计 [{cfg['name']}] ──")
        if config.supports_prompt_cache(provider):
            print(f"  cache_read（命中缓存）: {cache_read}")
            print(f"  cache_write（写入缓存）: {cache_creation}")
        elif cache_read:
            print(f"  cached（命中缓存）:     {cache_read}")
        print(f"  input（未缓存输入）:    {input_tokens}")
        print(f"  output（输出）:         {output_tokens}")
        print(f"  本次预估费用: ${cost:.6f}")
        print(f"  累计总费用:   ${state.total_cost:.6f}")


def calc_cost(usage: TokenUsage, provider: str | None = None) -> float:
    price = config.get_price(provider)
    return (
        usage.cache_read_input_tokens / 1_000_000 * price["cache_read"]
        + usage.cache_creation_input_tokens / 1_000_000 * price["cache_write"]
        + usage.input_tokens / 1_000_000 * price["input"]
        + usage.output_tokens / 1_000_000 * price["output"]
    )


def calc_cost_no_cache(usage: TokenUsage, provider: str | None = None) -> float:
    """假设全部 input 按未缓存单价计费，用于对比节省比例。"""
    price = config.get_price(provider)
    total_input = (
        usage.cache_read_input_tokens
        + usage.cache_creation_input_tokens
        + usage.input_tokens
    )
    return (
        total_input / 1_000_000 * price["input"]
        + usage.output_tokens / 1_000_000 * price["output"]
    )


def _cache_ttl_seconds() -> int:
    return 3600 if config.CACHE_TTL == "1h" else 300


def _cache_ttl_remaining() -> int | None:
    if not state.cache_write_at:
        return None
    return max(0, int(_cache_ttl_seconds() - (time.time() - state.cache_write_at)))


def _build_last_call_info(usage: TokenUsage, cost: float, pid: str) -> dict:
    if usage.cache_creation_input_tokens > 0:
        state.cache_write_at = time.time()
    cost_no_cache = calc_cost_no_cache(usage, pid)
    cfg = config.get_provider_config(pid)
    ttl_remaining = _cache_ttl_remaining()
    info = {
        "ok": True,
        "provider": pid,
        "provider_name": cfg["name"],
        "model": config.get_model(pid),
        "cost": cost,
        "cost_no_cache": round(cost_no_cache, 6),
        "cost_saved": round(max(0.0, cost_no_cache - cost), 6),
        "total_cost": state.total_cost,
        "usage": {
            "cache_read": usage.cache_read_input_tokens,
            "cache_write": usage.cache_creation_input_tokens,
            "input": usage.input_tokens,
            "output": usage.output_tokens,
        },
        "cache_write_at": state.cache_write_at or None,
        "cache_ttl_seconds": _cache_ttl_seconds(),
        "cache_ttl_remaining": ttl_remaining,
        "writing_cache_supported": config.supports_prompt_cache(pid),
    }
    if cost_no_cache > 0:
        info["cache_savings_pct"] = round(
            max(0.0, (cost_no_cache - cost) / cost_no_cache) * 100, 1
        )
    else:
        info["cache_savings_pct"] = 0.0
    return info
