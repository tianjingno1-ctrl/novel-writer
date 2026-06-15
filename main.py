#!/usr/bin/env python3
"""CLI 入口 + 测试兼容最小 re-export。业务逻辑见 core/ infra/ app/。"""
from __future__ import annotations

from app.paths import (
    ARCHIVE_FILE, BACKUPS_DIR, BASE_DIR, CHAPTERS_DIR, CHARACTERS_FILE, CHAR_CURRENT_FILE,
    CHAR_DYNAMIC_FILE, CHAR_STATIC_FILE, CHAT_PROMPTS_FILE, CODEX_FILES, CONTEXT_LOG_JSONL,
    COST_LOG, COST_LOG_JSONL, DATA_DIR, OUTLINE_LATEST_FILE,
    PLOT_THREADS_ACTIVE_FILE, PLOT_THREADS_FILE, PLOT_THREADS_LOCKED_FILE, SESSION_FILE,
    SESSION_MD_FILE, STYLE_FILE, SUMMARIES_ARCHIVE_FILE, SUMMARIES_FILE, SUMMARIES_RECENT_FILE,
    WORLD_FILE,
)
from app.bootstrap_data import DEFAULT_CHAT_PROMPTS, INITIAL_FILE_TEMPLATES
from app.main_forwards import _ALIASES, _MODULES, resolve as _resolve_forward
from core.llm import TokenUsage, _request_lock, call_api
from infra.billing import calc_cost, calc_cost_no_cache, load_total_cost_from_jsonl
from infra.state import state


def __getattr__(name: str):
    return _resolve_forward(name)


def __dir__():
    return sorted(set(globals()) | set(_MODULES) | set(_ALIASES) | {"__getattr__", "__dir__"})


def main() -> None:
    from app.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
