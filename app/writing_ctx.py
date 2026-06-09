"""P4-C shim：writing_ctx 已合并进 core.context。"""
from core.context import *  # noqa: F401,F403
from core.context import (
    _USER_CHAPTER_BLOCK_RE,
    _outline_context_ready,
    bind_writing_context as _bind_writing_context,
    count_summaries,
    extract_chapter_body_from_user_message,
    get_characters_block,
    get_char_context_for_check,
    get_dynamic_context_block,
    get_last_context_debug,
    get_latest_chapter,
    get_stable_archive_block,
    get_summaries_combined,
    get_world_block,
    cache_block,
    collect_dynamic_layer_parts as _collect_dynamic_layer_parts,
    read_char_static as _read_char_static,
    read_plot_active as _read_plot_active,
    read_plot_locked as _read_plot_locked,
    record_context_debug_bound as _record_context_debug,
)
