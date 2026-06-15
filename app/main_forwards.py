"""main.py PEP 562 转发表（测试 patch main.* 仍有效）。"""

from __future__ import annotations

import importlib
from typing import Any

# module path → 同名属性；特殊映射见 _ALIASES
_MODULES: dict[str, str] = {
    # app.llm
    "build_cached_system": "core.llm",
    "_estimate_tokens": "core.llm",
    "_analyze_system": "core.llm",
    "_summarize_messages": "core.llm",
    "_build_context_report": "core.llm",
    "log_request_context": "core.llm",
    "prepare_messages_for_context": "core.llm",
    "trim_history": "core.llm",
    "get_last_call_info": "core.llm",
    "_is_stream_disconnect_error": "core.llm",
    "_record_call_usage": "core.llm",
    "_api_error_message": "core.llm",
    "call_api": "core.llm",
    # app.chapter_io（shim 注入 configure）
    "resolve_write_chapter_num": "app.chapter_io",
    "get_chapter_path": "app.chapter_io",
    "read_chapter_content": "app.chapter_io",
    "ensure_chapter_path": "app.chapter_io",
    "get_or_create_write_chapter": "app.chapter_io",
    "sanitize_chapter_text": "app.chapter_io",
    "instruction_save_mode": "app.chapter_io",
    "should_append_to_chapter": "app.chapter_io",
    "replace_chapter_content": "app.chapter_io",
    "append_to_chapter": "app.chapter_io",
    "sync_appended_indices_with_chapter": "app.chapter_io",
    "sync_chapter_title_from_file": "app.chapter_io",
    "prepare_chapter_body_from_reply": "app.chapter_io",
    "format_chapter_file": "app.chapter_io",
    "count_unsaved_chapter_turns": "app.chapter_io",
    "flush_chapter_writes": "app.chapter_io",
    "get_chapters_text_for_scope": "app.chapter_io",
    # core.context
    "get_last_context_debug": "core.context",
    "get_world_block": "core.context",
    "get_characters_block": "core.context",
    "extract_chapter_body_from_user_message": "core.context",
    # app.codex / chapters_api / bootstrap_data
    "save_codex": "app.codex",
    "get_codex": "app.codex",
    "save_chapter_by_num": "app.chapters_api",
    "get_chapter_by_num": "app.chapters_api",
    "list_chapters": "app.chapters_api",
    "create_next_chapter": "app.chapters_api",
    "INITIAL_FILE_TEMPLATES": "app.bootstrap_data",
    "DEFAULT_CHAT_PROMPTS": "app.bootstrap_data",
    # app.writing_turns
    "undo_last_chapter_append": "app.writing_turns",
    "apply_assistant_turn_to_chapter": "app.writing_turns",
    "apply_user_draft_turn_to_chapter": "app.writing_turns",
    "_clear_assistant_appended_indices": "app.writing_turns",
    # core.chapters
    "parse_chapter_header_line": "core.chapters",
    "split_chapter_markdown_header": "core.chapters",
    "extract_chapter_title_from_reply": "core.chapters",
    "strip_chapter_file_header": "core.chapters",
    # app.writing_session
    "touch_user_active": "app.writing_session",
    "_session_chapter_num": "app.writing_session",
    "format_session_markdown": "app.writing_session",
    "save_session": "app.writing_session",
    "clear_session_files": "app.writing_session",
    "load_session_from_disk": "app.writing_session",
    "has_pending_session": "app.writing_session",
    "remind_pending_session_on_startup": "app.writing_session",
    "restore_chat_session": "app.writing_session",
    "auto_restore_session_if_needed": "app.writing_session",
    "get_chat_history": "app.writing_session",
    "load_chat_prompts": "app.writing_session",
    "save_chat_prompts": "app.writing_session",
    "get_appended_indices": "app.writing_session",
    "set_write_chapter_num": "app.writing_session",
    "clear_chat_session": "app.writing_session",
    "backup_session_before_clear": "app.writing_session",
    # app.writing_chat
    "save_chapter_after_reply": "app.writing_chat",
    "writing_chat": "app.writing_chat",
    "writing_chat_stream": "app.writing_chat",
    # app.runtime
    "get_app_status": "app.runtime",
    "send_heartbeat": "app.runtime",
    "heartbeat_loop": "app.runtime",
    "start_heartbeat_thread": "app.runtime",
    "_heartbeat_stop": "app.runtime",
    "_exiting": "app.runtime",
    # app.cli
    "do_undo": "app.cli",
    "do_restore": "app.cli",
    "do_save": "app.cli",
    "remind_unsaved_on_exit": "app.cli",
    "graceful_exit": "app.cli",
    "_handle_exit_signal": "app.cli",
    "_atexit_save": "app.cli",
    "setup_exit_handlers": "app.cli",
    "do_writing": "app.cli",
    "do_summary": "app.cli",
    "do_check": "app.cli",
    "do_outline": "app.cli",
    "do_patch": "app.cli",
    "do_heartbeat_toggle": "app.cli",
    "do_provider": "app.cli",
    "do_cost": "app.cli",
    "do_new": "app.cli",
    "print_help": "app.cli",
    "print_startup_banner": "app.cli",
}

_ALIASES: dict[str, tuple[str, str]] = {
    "ensure_chapter_file": ("app.chapters_api", "_ensure_chapter_file"),
    "_book_store": ("app.factories", "book_store"),
    "_resolve_chapter_num": ("app.factories", "resolve_chapter_num"),
    "_generator_deps": ("app.factories", "generator_deps"),
    "_reviewer_deps": ("app.factories", "reviewer_deps"),
    "_maintain_deps": ("app.factories", "maintain_deps"),
    "apply_chapter_title": ("app.factories", "apply_chapter_title"),
}

_mod_cache: dict[str, object] = {}


def _import(mod_path: str):
    if mod_path not in _mod_cache:
        _mod_cache[mod_path] = importlib.import_module(mod_path)
    return _mod_cache[mod_path]


def resolve(name: str) -> Any:
    if name in _ALIASES:
        mod_path, attr = _ALIASES[name]
        return getattr(_import(mod_path), attr)
    mod_path = _MODULES.get(name)
    if mod_path is None:
        raise AttributeError(f"module 'main' has no attribute {name!r}")
    return getattr(_import(mod_path), name)
