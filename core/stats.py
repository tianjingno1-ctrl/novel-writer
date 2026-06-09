"""书架统计（纯计算，无 HTTP / 缓存）。"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from core.data import novel_data


def build_stats_sig(
    chapters: list[tuple[int, object]],
    *,
    summaries_file: Path,
    cost_log: Path,
    cost_log_jsonl: Path,
) -> tuple:
    sig_parts: list[tuple] = []
    for num, path in chapters:
        st = path.stat()
        sig_parts.append((num, st.st_mtime_ns, st.st_size))
    if novel_data.PLAN_FILE.exists():
        st = novel_data.PLAN_FILE.stat()
        sig_parts.append(("plan", st.st_mtime_ns, st.st_size))
    codex_dir = novel_data.CODEX_DIR
    if codex_dir.exists():
        for p in sorted(codex_dir.glob("*.md")):
            st = p.stat()
            sig_parts.append((p.name, st.st_mtime_ns, st.st_size))
    for extra in (summaries_file, cost_log, cost_log_jsonl):
        if extra.exists():
            st = extra.stat()
            sig_parts.append((extra.name, st.st_mtime_ns, st.st_size))
    return tuple(sig_parts)


def compute_stats(
    chapters: list[tuple[int, object]],
    *,
    read_text: Callable[[Path], str],
    count_summaries: Callable[[], int],
    get_total_cost: Callable[[], float],
) -> dict:
    chapter_stats = []
    total_chars = 0
    for num, path in chapters:
        text = read_text(path)
        chars = len(re.sub(r"\s", "", text))
        total_chars += chars
        chapter_stats.append({"num": num, "chars": chars, "file": path.name})

    plan = novel_data.load_plan()
    scene_count = sum(
        len(ch.get("scenes", [])) for ch in plan.get("chapters", {}).values()
    )
    codex_count = len(novel_data.list_codex_entries())

    return {
        "total_chars": total_chars,
        "chapter_count": len(chapters),
        "scene_count": scene_count,
        "codex_count": codex_count,
        "summary_count": count_summaries(),
        "total_cost": get_total_cost(),
        "chapters": chapter_stats,
    }
