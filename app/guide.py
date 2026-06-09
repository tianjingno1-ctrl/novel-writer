"""写作引导状态（/api/guide/status）。"""

from __future__ import annotations

import re

import novel_data
from app_state import state


def _maint_file_has_user_content(file_key: str) -> bool:
    """章后维护文件是否已有用户填写（非空模板）。"""
    import main

    path = main.CODEX_FILES.get(file_key)
    if not path:
        return False
    text = main.read_text(path).strip()
    if len(text) < 30:
        return False
    placeholder = (main.INITIAL_FILE_TEMPLATES.get(file_key) or "").strip()
    if text == placeholder:
        return False
    if file_key == "char_dynamic":
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("-") and "：" in line:
                val = line.split("：", 1)[1].strip()
                if val:
                    return True
        return False
    if file_key == "plot_threads_active":
        in_unresolved = False
        skip = {
            "（伏笔条目）",
            "（第一世界写到哪记到哪，开书暂空）",
            "（暂无）",
        }
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("## 未回收"):
                in_unresolved = True
                continue
            if s.startswith("##"):
                in_unresolved = False
                continue
            if (
                in_unresolved
                and s
                and not s.startswith("（")
                and s not in skip
            ):
                return True
        return False
    return text != placeholder


def get_guide_status() -> dict:
    """写作引导：地基文件、规划、章后待办等状态（供 /api/guide/status）。"""
    import change_history
    import main

    track_keys = (
        "world",
        "char_static",
        "style",
        "char_dynamic",
        "plot_threads_active",
    )

    def _file_ready(key: str) -> bool:
        path = main.CODEX_FILES.get(key)
        if not path:
            return False
        text = main.read_text(path).strip()
        if len(text) < 20:
            return False
        placeholder = (main.INITIAL_FILE_TEMPLATES.get(key) or "").strip()
        return not placeholder or text != placeholder

    files = {key: _file_ready(key) for key in track_keys}

    plan = novel_data.load_plan()
    scene_count = sum(
        len(ch.get("scenes", [])) for ch in plan.get("chapters", {}).values()
    )
    has_plan = scene_count > 0

    latest = main.get_latest_chapter()
    latest_chapter_num = latest[0] if latest else 0

    def _last_update_chapter(file_key: str) -> int:
        try:
            hist = change_history.list_history(file_key=file_key, limit=50)
            summary = hist.get("summary", {}).get(file_key, {})
            last = summary.get("last_change")
            if not last:
                return 0
            ch = last.get("chapter_num")
            if ch is None:
                return 0
            return int(ch) if int(ch) > 0 else 0
        except Exception:
            pass
        return 0

    def _effective_maint_chapter(file_key: str) -> int:
        hist = _last_update_chapter(file_key)
        if hist > 0:
            return hist
        if latest_chapter_num > 0 and _maint_file_has_user_content(file_key):
            return latest_chapter_num
        return 0

    char_dynamic_last = _effective_maint_chapter("char_dynamic")
    plot_threads_last = _effective_maint_chapter("plot_threads_active")

    recent_raw = main.read_text(main.SUMMARIES_RECENT_FILE)
    summaries_recent_count = len(re.findall(r"【第\d+章", recent_raw))

    combined_summaries = main.get_summaries_combined()
    summary_nums = {int(n) for n in re.findall(r"【第(\d+)章", combined_summaries)}
    last_summary_chapter = max(summary_nums) if summary_nums else 0
    latest_chapter_has_summary = (
        latest_chapter_num <= 0 or latest_chapter_num in summary_nums
    )

    post_chapter_todos = {
        "summary": not latest_chapter_has_summary,
        "char_dynamic": (
            latest_chapter_num > 0
            and char_dynamic_last > 0
            and (latest_chapter_num - char_dynamic_last) >= 2
        ),
        "plot_threads": (
            latest_chapter_num > 0
            and plot_threads_last > 0
            and (latest_chapter_num - plot_threads_last) >= 2
        ),
        "char_dynamic_never": latest_chapter_num > 0 and char_dynamic_last == 0,
        "plot_threads_never": latest_chapter_num > 0 and plot_threads_last == 0,
        "archive": summaries_recent_count >= 5,
    }

    if not files["world"]:
        stage = "setup"
    elif not has_plan:
        stage = "planning"
    elif latest_chapter_num == 0:
        stage = "first_chapter"
    else:
        stage = "writing"

    return {
        "ok": True,
        "stage": stage,
        "files": files,
        "has_plan": has_plan,
        "scene_count": scene_count,
        "latest_chapter_num": latest_chapter_num,
        "current_chapter_num": state.write_chapter_num or latest_chapter_num,
        "char_dynamic_last_chapter": char_dynamic_last,
        "plot_threads_last_chapter": plot_threads_last,
        "char_dynamic_never_updated": char_dynamic_last == 0,
        "plot_threads_never_updated": plot_threads_last == 0,
        "summaries_recent_count": summaries_recent_count,
        "summaries_need_archive": summaries_recent_count >= 5,
        "last_summary_chapter": last_summary_chapter,
        "latest_chapter_has_summary": latest_chapter_has_summary,
        "post_chapter_todos": post_chapter_todos,
    }
