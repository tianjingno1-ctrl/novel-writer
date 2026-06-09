"""会话 IO 服务层（P3-4c）。save/restore/clear/prompts/set_write_chapter_num。"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime

import file_utils
from app import chapter_io as chapter_io
from app import book_io as bio
from app import paths as _paths
from app import writing_ctx as _wctx
from app_state import state


def touch_user_active() -> None:
    state.last_user_active = time.time()


def get_chat_history() -> list[dict]:
    return list(state.conversation_history)


def get_appended_indices() -> list[int]:
    return sorted(state.appended_indices)


def _session_chapter_num() -> int:
    if state.write_chapter_num > 0:
        return state.write_chapter_num
    latest = _wctx.get_latest_chapter()
    return latest[0] if latest else 0


def format_session_markdown(saved_at: str, reason: str) -> str:
    lines = [
        "# 会话自动保存\n",
        f"保存时间：{saved_at}\n",
        f"触发原因：{reason}\n",
        f"当前章节：第{_session_chapter_num()}章\n\n",
        "---\n\n",
    ]
    for i, msg in enumerate(state.conversation_history, 1):
        role = "用户" if msg["role"] == "user" else "助手"
        lines.append(f"## [{i}] {role}\n\n{msg['content']}\n\n")
    lines.append(
        "---\n\n"
        "提示：续写正文默认自动写入 data/chapters/；未写入的可用 /save 补存。\n"
        "恢复对话：启动后输入 /restore\n"
    )
    return "".join(lines)


def save_session(reason: str = "auto", *, silent: bool = False) -> bool:
    """将会话对话写入磁盘，异常退出时可恢复。"""
    if not state.conversation_history:
        return False

    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "saved_at": saved_at,
        "reason": reason,
        "chapter_num": _session_chapter_num(),
        "session_includes_chapter": state.session_includes_chapter,
        "write_chapter_num": state.write_chapter_num,
        "last_injected_chapter_num": state.last_injected_chapter_num,
        "conversation_history": state.conversation_history,
        "appended_indices": sorted(state.appended_indices),
    }

    session_file = _paths.resolved("SESSION_FILE")
    session_md = _paths.resolved("SESSION_MD_FILE")
    file_utils.atomic_write_text(
        session_file,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    file_utils.atomic_write_text(
        session_md,
        format_session_markdown(saved_at, reason),
    )

    if not silent:
        print(f"💾 会话已保存 → {session_md}")
        print("   请将需要的正文复制到章节文件（data/chapters/）")
    return True


def clear_session_files() -> None:
    for path in (
        _paths.resolved("SESSION_FILE"),
        _paths.resolved("SESSION_MD_FILE"),
    ):
        if path.exists():
            path.unlink()


def load_session_from_disk() -> dict | None:
    session_file = _paths.resolved("SESSION_FILE")
    if not session_file.exists():
        return None
    try:
        return json.loads(session_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _session_history(data: dict) -> list | None:
    """兼容旧版 session 字段名。"""
    history = data.get("conversation_history")
    if history is None:
        history = data.get("state.conversation_history")
    return history


def has_pending_session() -> bool:
    data = load_session_from_disk()
    history = _session_history(data) if data else None
    return bool(history)


def restore_chat_session() -> dict:
    """从 session_autosave.json 恢复写书对话到内存。"""
    data = load_session_from_disk()
    history = _session_history(data) if data else None
    if not data or not history:
        return {"ok": False, "error": "没有可恢复的会话备份"}

    state.conversation_history.clear()
    for msg in history:
        content = msg.get("content", "")
        if msg.get("role") == "assistant":
            content = chapter_io.sanitize_chapter_text(content)
        state.conversation_history.append(
            {"role": msg["role"], "content": content}
        )
    state.session_includes_chapter = data.get(
        "session_includes_chapter",
        data.get("state.session_includes_chapter", False),
    )
    state.write_chapter_num = int(data.get("write_chapter_num") or 0)
    state.last_injected_chapter_num = int(
        data.get("last_injected_chapter_num") or 0
    )
    state.appended_indices.clear()
    saved_indices = data.get("appended_indices")
    if saved_indices is not None:
        state.appended_indices.update(int(i) for i in saved_indices)
    chapter_io.sync_appended_indices_with_chapter()
    pending = chapter_io.count_unsaved_chapter_turns()
    return {
        "ok": True,
        "saved_at": data.get("saved_at", ""),
        "message_count": len(state.conversation_history),
        "pending_writes": pending,
    }


def auto_restore_session_if_needed() -> bool:
    """进程内对话为空但磁盘有备份时自动恢复（Web 重启场景）。"""
    if state.conversation_history:
        return False
    if not has_pending_session():
        return False
    return restore_chat_session().get("ok", False)


def backup_session_before_clear() -> None:
    if not state.conversation_history:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = _paths.resolved("BACKUPS_DIR") / f"session_{ts}.md"
    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dest.write_text(format_session_markdown(saved_at, "before_new"), encoding="utf-8")
    print(f"旧会话已备份到 {dest}")


def load_chat_prompts() -> dict:
    from app.bootstrap_data import DEFAULT_CHAT_PROMPTS

    prompts_file = _paths.resolved("CHAT_PROMPTS_FILE")
    if not prompts_file.exists():
        return dict(DEFAULT_CHAT_PROMPTS)
    try:
        data = json.loads(prompts_file.read_text(encoding="utf-8"))
        prompts = data.get("prompts")
        if isinstance(prompts, list) and prompts:
            return {"prompts": prompts}
    except (json.JSONDecodeError, OSError):
        pass
    return dict(DEFAULT_CHAT_PROMPTS)


def save_chat_prompts(prompts: list[dict]) -> dict:
    cleaned: list[dict] = []
    seen: set[str] = set()
    for item in prompts:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()
        if not pid or pid in seen:
            pid = uuid.uuid4().hex[:10]
        while pid in seen:
            pid = uuid.uuid4().hex[:10]
        seen.add(pid)
        if not content:
            continue
        if not title:
            line = content.split("\n", 1)[0].strip()
            title = (line[:80] + "…") if len(line) > 80 else (line or "指令")
        cleaned.append({"id": pid, "title": title, "content": content})
    payload = {"prompts": cleaned}
    bio.write_text(
        _paths.resolved("CHAT_PROMPTS_FILE"),
        json.dumps(payload, ensure_ascii=False, indent=2),
        append=False,
    )
    return {"ok": True, **payload}


def set_write_chapter_num(num: int) -> dict:
    """显式设置写作目标章（须有正文文件）。"""
    if num <= 0:
        state.write_chapter_num = 0
        return {"ok": True, "write_chapter_num": None}
    path = _paths.resolved("CHAPTERS_DIR") / f"ch{num:03d}.md"
    if not path.exists():
        return {"ok": False, "error": f"第{num}章正文文件不存在"}
    state.write_chapter_num = num
    if num != state.last_injected_chapter_num:
        state.session_includes_chapter = False
    return {"ok": True, "write_chapter_num": num}


def clear_chat_session() -> None:
    backup_session_before_clear()
    state.conversation_history.clear()
    state.session_includes_chapter = False
    state.write_chapter_num = 0
    state.last_injected_chapter_num = 0
    state.appended_indices.clear()
    clear_session_files()


def remind_pending_session_on_startup() -> None:
    data = load_session_from_disk()
    history = _session_history(data) if data else None
    if not data or not history:
        return

    saved_at = data.get("saved_at", "未知")
    reason = data.get("reason", "未知")
    turns = len(history)
    chapter = data.get("chapter_num", "?")

    if state.conversation_history:
        return

    session_md = _paths.resolved("SESSION_MD_FILE")
    print()
    print("⚠️  检测到上次未恢复的会话（可能异常关闭）")
    print(f"   保存时间：{saved_at}（{reason}）")
    print(f"   章节：第{chapter}章，共 {turns} 条消息")
    print(f"   可读备份：{session_md}")
    print("   → 输入 /restore 恢复对话，或 /new 丢弃并开始新会话")
