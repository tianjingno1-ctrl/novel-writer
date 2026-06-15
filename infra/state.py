"""进程内应用状态（CLI / Web 共享单例）。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class AppState:
    conversation_history: list[dict] = field(default_factory=list)
    session_includes_chapter: bool = False
    write_chapter_num: int = 0
    last_injected_chapter_num: int = 0
    last_synced_active_scene_chapter: int = -1
    appended_indices: set[int] = field(default_factory=set)
    last_request_time: float = 0.0
    last_user_active: float = field(default_factory=time.time)
    total_cost: float = 0.0
    last_call_info: dict = field(default_factory=dict)
    last_context_debug: dict = field(default_factory=dict)
    cache_write_at: float = 0.0
    last_append_undo: dict | None = None


state = AppState()
