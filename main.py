#!/usr/bin/env python3
"""长篇小说辅助写作工具 — 主程序。"""

from __future__ import annotations

import atexit
import json
import re
import shutil
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import config
import novel_data
from providers import TokenUsage, get_client, reset_client
from summarizer import (
    CHECK_SYSTEM,
    SUMMARY_SYSTEM,
    WRITING_INSTRUCTION,
    build_check_user_message,
    build_summary_user_message,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHAPTERS_DIR = DATA_DIR / "chapters"
BACKUPS_DIR = DATA_DIR / "backups"
COST_LOG = BASE_DIR / "cost_log.txt"
SESSION_FILE = DATA_DIR / "session_autosave.json"
SESSION_MD_FILE = DATA_DIR / "session_autosave.md"
FREE_CHAT_FILE = DATA_DIR / "free_chat.json"

WORLD_FILE = DATA_DIR / "world.md"
CHARACTERS_FILE = DATA_DIR / "characters.md"
CHAR_CURRENT_FILE = DATA_DIR / "char_current.md"
SUMMARIES_FILE = DATA_DIR / "summaries.md"
PLOT_THREADS_FILE = DATA_DIR / "plot_threads.md"

INITIAL_FILES = {
    WORLD_FILE: "# 世界观设定\n\n（在此填写世界观、魔法体系、地图等，几乎不变的内容）\n",
    CHARACTERS_FILE: "# 人物初始设定\n\n（在此填写主要人物的初始设定，只追加不修改）\n",
    CHAR_CURRENT_FILE: "# 人物当前状态\n\n（在此维护人物当前状态，可单独更新）\n",
    SUMMARIES_FILE: "# 章节概述\n\n",
    PLOT_THREADS_FILE: "# 伏笔/线索清单\n\n（手动维护伏笔与线索）\n",
}

DISCUSSION_PREFIXES = ("[讨论]", "[问答]", "[建议]")

# ── 全局状态 ──────────────────────────────────────────────
conversation_history: list[dict] = []
free_chat_history: list[dict] = []
free_chat_provider: str = config.FREE_CHAT_PROVIDER
session_includes_chapter = False
appended_indices: set[int] = set()
last_request_time = 0.0
last_user_active = time.time()
total_cost = 0.0
_cost_lock = threading.Lock()
_request_lock = threading.Lock()
_heartbeat_stop = threading.Event()
_exiting = False
_last_call_info: dict = {}

CODEX_FILES = {
    "world": WORLD_FILE,
    "characters": CHARACTERS_FILE,
    "char_current": CHAR_CURRENT_FILE,
    "summaries": SUMMARIES_FILE,
    "plot_threads": PLOT_THREADS_FILE,
}


def init_data_dirs() -> None:
    """首次运行：创建目录与空文件。"""
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    novel_data.CODEX_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in INITIAL_FILES.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    novel_data.load_plan()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def backup_file(path: Path) -> None:
    """写入前自动备份。"""
    if path.exists() and path.stat().st_size > 0:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        dest = BACKUPS_DIR / f"{path.stem}_{ts}{path.suffix}"
        shutil.copy2(path, dest)
        old = sorted(BACKUPS_DIR.glob(f"{path.stem}_*{path.suffix}"))
        for f in old[:-10]:
            f.unlink(missing_ok=True)


def write_text(path: Path, content: str, *, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_file(path)
    if append:
        with path.open("a", encoding="utf-8") as f:
            f.write(content)
    else:
        path.write_text(content, encoding="utf-8")


def load_total_cost() -> float:
    if not COST_LOG.exists():
        return 0.0
    total = 0.0
    for line in COST_LOG.read_text(encoding="utf-8").splitlines():
        m = re.search(r"费用:\s*\$?([\d.]+)\b", line)
        if m:
            total += float(m.group(1))
    return total


def log_cost(
    usage: TokenUsage,
    cost: float,
    tag: str,
    *,
    provider: str | None = None,
    silent: bool = False,
) -> None:
    global total_cost
    cache_read = usage.cache_read_input_tokens
    cache_creation = usage.cache_creation_input_tokens
    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens

    with _cost_lock:
        total_cost += cost
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = (
            f"[{ts}] [{tag}] "
            f"cache_read={cache_read} cache_write={cache_creation} "
            f"input={input_tokens} output={output_tokens} "
            f"费用: ${cost:.6f} 累计: ${total_cost:.6f}\n"
        )
        with COST_LOG.open("a", encoding="utf-8") as f:
            f.write(line)

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
        print(f"  累计总费用:   ${total_cost:.6f}")


def calc_cost(usage: TokenUsage, provider: str | None = None) -> float:
    price = config.get_price(provider)
    return (
        usage.cache_read_input_tokens / 1_000_000 * price["cache_read"]
        + usage.cache_creation_input_tokens / 1_000_000 * price["cache_write"]
        + usage.input_tokens / 1_000_000 * price["input"]
        + usage.output_tokens / 1_000_000 * price["output"]
    )


def cache_block(text: str) -> dict:
    return {
        "type": "text",
        "text": text,
        "cache_control": {"type": "ephemeral", "ttl": config.CACHE_TTL},
    }


def get_characters_block() -> str:
    """Codex 勾选条目优先；否则回退 characters.md。"""
    if config.CONTEXT_MODE == "codex" or novel_data.get_active_codex_ids():
        codex_text = novel_data.format_active_codex_text()
        if codex_text:
            return f"# 本章相关设定（Codex）\n\n{codex_text}"
    return read_text(CHARACTERS_FILE)


def get_summaries_block() -> str:
    summaries = read_text(SUMMARIES_FILE)
    if config.CONTEXT_MODE == "beats":
        scene = novel_data.get_active_scene()
        if scene and scene.get("summary"):
            summaries += f"\n\n# 当前场景概述\n{scene['summary']}"
    return summaries


def build_cached_system(instruction: str, provider: str | None = None) -> list[dict] | str:
    """三层缓存 + 本次写作指令；无缓存提供商时合并为纯文本 system。"""
    world = read_text(WORLD_FILE)
    characters = get_characters_block()
    summaries = get_summaries_block()
    extra = ""
    if config.CONTEXT_MODE in ("beats", "summaries"):
        scene_ctx = novel_data.get_scene_context_text()
        if scene_ctx:
            extra = f"\n\n# 当前场景\n{scene_ctx}"

    full_instruction = instruction + extra

    if config.supports_prompt_cache(provider):
        return [
            cache_block(world),
            cache_block(characters),
            cache_block(summaries),
            {"type": "text", "text": full_instruction},
        ]

    return (
        f"# 世界观设定\n{world}\n\n"
        f"# 人物设定\n{characters}\n\n"
        f"# 章节概述\n{summaries}\n\n"
        f"# 当前任务\n{full_instruction}"
    )


def prepare_messages_for_context(history: list[dict]) -> list[dict]:
    mode = config.CONTEXT_MODE
    if mode == "summaries":
        return trim_history(history, max(2, min(config.CHAT_CONTEXT_TURNS, 4)))
    if mode == "beats":
        return trim_history(history, max(3, config.CHAT_CONTEXT_TURNS))
    if mode == "codex":
        return trim_history(history, max(2, config.CHAT_CONTEXT_TURNS))
    return trim_history(history)


def trim_history(history: list[dict], max_turns: int | None = None) -> list[dict]:
    """保留最近 N 轮对话；首轮含章节正文时不单独特殊处理。"""
    turns = max_turns if max_turns is not None else config.CHAT_CONTEXT_TURNS
    if turns <= 0 or len(history) <= turns * 2:
        return list(history)
    return history[-(turns * 2) :]


def get_last_call_info() -> dict:
    return dict(_last_call_info)


def call_api(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    max_tokens: int | None = None,
    tag: str = "请求",
    provider: str | None = None,
    silent: bool = False,
) -> str | None:
    global last_request_time, _last_call_info

    pid = config.resolve_provider(provider)
    if not config.is_api_key_configured(pid):
        cfg = config.get_provider_config(pid)
        err = (
            f"请设置 {cfg['api_key_env']}，或在 .env / config.py 中填写 API Key"
        )
        _last_call_info = {"ok": False, "error": err, "provider": pid}
        if not silent:
            print(f"错误：{err}")
        return None

    try:
        with _request_lock:
            text, usage = get_client().create_message(
                system,
                messages,
                max_tokens=max_tokens or config.MAX_TOKENS,
                provider=pid,
            )
            last_request_time = time.time()

        cost = calc_cost(usage, provider=pid)
        log_cost(usage, cost, tag, provider=pid, silent=silent)
        cfg = config.get_provider_config(pid)
        _last_call_info = {
            "ok": True,
            "provider": pid,
            "provider_name": cfg["name"],
            "cost": cost,
            "total_cost": total_cost,
            "usage": {
                "cache_read": usage.cache_read_input_tokens,
                "cache_write": usage.cache_creation_input_tokens,
                "input": usage.input_tokens,
                "output": usage.output_tokens,
            },
        }
        return text
    except ImportError as e:
        _last_call_info = {"ok": False, "error": str(e)}
        if not silent:
            print(f"依赖缺失：{e}")
        return None
    except Exception as e:
        _last_call_info = {"ok": False, "error": str(e)}
        if not silent:
            print(f"API 错误：{e}")
        return None


def list_chapters() -> list[tuple[int, Path]]:
    chapters = []
    for p in CHAPTERS_DIR.glob("ch*.md"):
        m = re.match(r"ch(\d+)\.md$", p.name, re.IGNORECASE)
        if m:
            chapters.append((int(m.group(1)), p))
    chapters.sort(key=lambda x: x[0])
    return chapters


def get_latest_chapter() -> tuple[int, Path, str] | None:
    chapters = list_chapters()
    if not chapters:
        return None
    num, path = chapters[-1]
    return num, path, read_text(path)


def get_or_create_write_chapter() -> tuple[int, Path]:
    """获取最新章节；若不存在则创建 ch001.md。"""
    latest = get_latest_chapter()
    if latest:
        return latest[0], latest[1]
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHAPTERS_DIR / "ch001.md"
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return 1, path


def should_append_to_chapter(reply: str) -> bool:
    stripped = reply.strip()
    if not stripped or len(stripped) < 30:
        return False
    if any(stripped.startswith(p) for p in DISCUSSION_PREFIXES):
        return False
    if stripped.startswith("✅"):
        return False
    return True


def append_to_chapter(text: str, chapter_path: Path) -> int:
    """将正文追加到章节文件，返回写入字数。"""
    content = text.strip()
    if not content:
        return 0
    existing = read_text(chapter_path)
    separator = "\n\n" if existing.strip() else ""
    write_text(chapter_path, f"{separator}{content}\n", append=True)
    return len(content)


def count_unsaved_chapter_turns() -> int:
    return sum(
        1
        for i, msg in enumerate(conversation_history)
        if msg["role"] == "assistant"
        and i not in appended_indices
        and should_append_to_chapter(msg["content"])
    )


def flush_chapter_writes(*, silent: bool = False) -> int:
    """将尚未写入章节的 AI 正文批量追加到最新章节。"""
    chapter_num, chapter_path = get_or_create_write_chapter()
    total_chars = 0
    count = 0

    for i, msg in enumerate(conversation_history):
        if msg["role"] != "assistant" or i in appended_indices:
            continue
        if not should_append_to_chapter(msg["content"]):
            continue
        chars = append_to_chapter(msg["content"], chapter_path)
        if chars:
            appended_indices.add(i)
            total_chars += chars
            count += 1

    if count and not silent:
        print(
            f"💾 已保存 {count} 条正文到 data/chapters/ch{chapter_num:03d}.md"
            f"（共 +{total_chars} 字）"
        )
    return count


def save_chapter_after_reply(reply: str, msg_index: int) -> None:
    """AI 回复后自动或提醒保存到章节。"""
    if not should_append_to_chapter(reply):
        if not config.AUTO_APPEND_CHAPTER:
            return
        print("💡 本条为讨论/说明，未写入章节（如需保存请手动编辑章节文件）")
        return

    if config.AUTO_APPEND_CHAPTER:
        chapter_num, chapter_path = get_or_create_write_chapter()
        chars = append_to_chapter(reply, chapter_path)
        appended_indices.add(msg_index)
        print(
            f"💾 已自动保存到 data/chapters/ch{chapter_num:03d}.md（+{chars} 字）"
        )
    else:
        pending = count_unsaved_chapter_turns()
        print(f"💡 本条正文尚未写入章节，输入 /save 保存（待保存 {pending} 条）")


def count_summaries() -> int:
    text = read_text(SUMMARIES_FILE)
    return len(re.findall(r"【第\d+章", text))


def touch_user_active() -> None:
    global last_user_active
    last_user_active = time.time()


def _session_chapter_num() -> int:
    latest = get_latest_chapter()
    return latest[0] if latest else 0


def format_session_markdown(saved_at: str, reason: str) -> str:
    lines = [
        "# 会话自动保存\n",
        f"保存时间：{saved_at}\n",
        f"触发原因：{reason}\n",
        f"当前章节：第{_session_chapter_num()}章\n\n",
        "---\n\n",
    ]
    for i, msg in enumerate(conversation_history, 1):
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
    if not conversation_history:
        return False

    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "saved_at": saved_at,
        "reason": reason,
        "chapter_num": _session_chapter_num(),
        "session_includes_chapter": session_includes_chapter,
        "conversation_history": conversation_history,
    }

    SESSION_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    SESSION_MD_FILE.write_text(
        format_session_markdown(saved_at, reason),
        encoding="utf-8",
    )

    if not silent:
        print(f"💾 会话已保存 → {SESSION_MD_FILE}")
        print("   请将需要的正文复制到章节文件（data/chapters/）")
    return True


def clear_session_files() -> None:
    for path in (SESSION_FILE, SESSION_MD_FILE):
        if path.exists():
            path.unlink()


def load_session_from_disk() -> dict | None:
    if not SESSION_FILE.exists():
        return None
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def has_pending_session() -> bool:
    data = load_session_from_disk()
    return bool(data and data.get("conversation_history"))


def remind_pending_session_on_startup() -> None:
    data = load_session_from_disk()
    if not data or not data.get("conversation_history"):
        return

    saved_at = data.get("saved_at", "未知")
    reason = data.get("reason", "未知")
    turns = len(data["conversation_history"])
    chapter = data.get("chapter_num", "?")

    if conversation_history:
        return

    print()
    print("⚠️  检测到上次未恢复的会话（可能异常关闭）")
    print(f"   保存时间：{saved_at}（{reason}）")
    print(f"   章节：第{chapter}章，共 {turns} 条消息")
    print(f"   可读备份：{SESSION_MD_FILE}")
    print("   → 输入 /restore 恢复对话，或 /new 丢弃并开始新会话")


def do_restore() -> None:
    global session_includes_chapter

    data = load_session_from_disk()
    if not data or not data.get("conversation_history"):
        print("没有可恢复的会话备份")
        return

    conversation_history.clear()
    conversation_history.extend(data["conversation_history"])
    session_includes_chapter = data.get("session_includes_chapter", False)
    appended_indices.clear()
    pending = count_unsaved_chapter_turns()
    print(f"✅ 已恢复会话（{data.get('saved_at', '')}，{len(conversation_history)} 条消息）")
    print(f"   详细内容见：{SESSION_MD_FILE}")
    if pending:
        print(f"💡 检测到 {pending} 条正文可能未写入章节，建议输入 /save 补存")


def do_save() -> None:
    chapter_count = flush_chapter_writes()
    session_saved = save_session("manual", silent=True)
    if chapter_count or session_saved:
        if session_saved:
            print(f"💾 会话已保存 → {SESSION_MD_FILE}")
        return
    print("当前没有需要保存的内容")


def remind_unsaved_on_exit() -> None:
    if not conversation_history:
        return

    pending = count_unsaved_chapter_turns()
    chapter_num = _session_chapter_num()

    print()
    if pending > 0:
        print(f"⚠️  提醒：还有 {pending} 条 AI 正文未写入章节！")
        print("   正在尝试补存…")
        flush_chapter_writes()
        pending = count_unsaved_chapter_turns()
        if pending > 0:
            print(f"   仍有 {pending} 条未保存，请手动执行 /save 或查看 {SESSION_MD_FILE}")
    elif config.AUTO_APPEND_CHAPTER and chapter_num:
        print(f"✅ 本章正文已全部自动保存到 data/chapters/ch{chapter_num:03d}.md")
    print(f"   会话备份：{SESSION_MD_FILE}")
    print("   下次启动输入 /restore 可继续对话")


def graceful_exit(message: str = "再见！") -> None:
    global _exiting
    if _exiting:
        return
    _exiting = True
    _heartbeat_stop.set()
    save_session("exit", silent=True)
    remind_unsaved_on_exit()
    print(message)
    raise SystemExit(0)


def _handle_exit_signal(signum, frame) -> None:
    sig_name = "Ctrl+C" if signum == signal.SIGINT else f"信号{signum}"
    print(f"\n⚠️  检测到异常关闭（{sig_name}），正在保存会话…")
    graceful_exit("已保存，安全退出。")


def _atexit_save() -> None:
    if _exiting:
        return
    save_session("atexit", silent=True)
    if conversation_history:
        remind_unsaved_on_exit()


def setup_exit_handlers() -> None:
    atexit.register(_atexit_save)
    signal.signal(signal.SIGINT, _handle_exit_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_exit_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle_exit_signal)


def do_writing(instruction: str) -> None:
    global session_includes_chapter

    latest = get_latest_chapter()
    if latest is None:
        print("提示：data/chapters/ 中尚无章节文件，将仅根据指令回复。")
        chapter_num, chapter_content = 0, "（尚无章节正文）"
    else:
        chapter_num, _, chapter_content = latest

    if not session_includes_chapter:
        user_content = (
            f"【当前章节：第{chapter_num}章】\n\n"
            f"{chapter_content}\n\n"
            f"【写作指令】\n{instruction}"
        )
        session_includes_chapter = True
    else:
        user_content = instruction

    conversation_history.append({"role": "user", "content": user_content})

    system = build_cached_system(WRITING_INSTRUCTION)
    reply = call_api(system, prepare_messages_for_context(conversation_history))
    if reply is None:
        conversation_history.pop()
        return

    print(f"\n{reply}\n")
    conversation_history.append({"role": "assistant", "content": reply})
    save_chapter_after_reply(reply, len(conversation_history) - 1)
    save_session("auto", silent=True)


def writing_chat(instruction: str, scene_beat: str = "", scene_id: str = "") -> dict:
    """Web/API：结构化写作对话，返回 JSON 友好结果。"""
    global session_includes_chapter

    beat_text = scene_beat.strip()
    if not beat_text and scene_id:
        scene = novel_data.get_scene(scene_id)
        if scene:
            beat_text = scene.get("beat", "")
            novel_data.set_active_scene(scene_id)
    elif scene_id:
        novel_data.set_active_scene(scene_id)

    parts = []
    if beat_text:
        parts.append(f"【场景指令 Scene Beat】\n{beat_text}")
    if instruction.strip():
        parts.append(instruction.strip())
    full_instruction = "\n\n".join(parts)
    if not full_instruction:
        return {"ok": False, "error": "指令不能为空"}

    latest = get_latest_chapter()
    if latest is None:
        chapter_num, chapter_content = 0, "（尚无章节正文）"
    else:
        chapter_num, _, chapter_content = latest

    if not session_includes_chapter:
        user_content = (
            f"【当前章节：第{chapter_num}章】\n\n"
            f"{chapter_content}\n\n"
            f"【写作指令】\n{full_instruction}"
        )
        session_includes_chapter = True
    else:
        user_content = full_instruction

    conversation_history.append({"role": "user", "content": user_content})
    system = build_cached_system(WRITING_INSTRUCTION)
    reply = call_api(system, prepare_messages_for_context(conversation_history), silent=True)
    if reply is None:
        conversation_history.pop()
        info = get_last_call_info()
        return {"ok": False, "error": info.get("error", "API 调用失败")}

    conversation_history.append({"role": "assistant", "content": reply})
    msg_index = len(conversation_history) - 1
    save_chapter_after_reply(reply, msg_index)
    save_session("auto", silent=True)

    chapter_saved = msg_index in appended_indices
    active_scene = novel_data.get_active_scene()
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": chapter_num,
        "chapter_saved": chapter_saved,
        "context_turns": config.CHAT_CONTEXT_TURNS,
        "context_mode": config.CONTEXT_MODE,
        "active_scene_id": active_scene.get("id") if active_scene else None,
        "history_len": len(conversation_history),
        **get_last_call_info(),
    }


def get_chat_history() -> list[dict]:
    return list(conversation_history)


def _trim_free_history() -> list[dict]:
    turns = config.FREE_CHAT_CONTEXT_TURNS
    if turns <= 0 or len(free_chat_history) <= turns * 2:
        return list(free_chat_history)
    return free_chat_history[-(turns * 2) :]


def _resolve_free_provider(provider: str | None = None) -> str:
    pid = provider or free_chat_provider
    if pid not in config.PROVIDERS:
        return config.FREE_CHAT_PROVIDER
    return pid


def save_free_chat() -> None:
    FREE_CHAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "provider": free_chat_provider,
        "messages": free_chat_history,
    }
    FREE_CHAT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_free_chat() -> None:
    global free_chat_history, free_chat_provider
    if not FREE_CHAT_FILE.exists():
        return
    try:
        data = json.loads(FREE_CHAT_FILE.read_text(encoding="utf-8"))
        free_chat_history = list(data.get("messages", []))
        saved_provider = data.get("provider")
        if saved_provider in config.PROVIDERS:
            free_chat_provider = saved_provider
    except (json.JSONDecodeError, OSError):
        free_chat_history = []


def get_free_chat_provider() -> str:
    return free_chat_provider


def set_free_chat_provider(provider: str) -> dict:
    global free_chat_provider
    if provider not in config.PROVIDERS:
        return {"ok": False, "error": f"未知提供商: {provider}"}
    free_chat_provider = provider
    save_free_chat()
    return {"ok": True, "provider": provider}


def get_free_chat_history() -> list[dict]:
    return list(free_chat_history)


def clear_free_chat() -> None:
    free_chat_history.clear()
    save_free_chat()


def free_chat(message: str, provider: str | None = None) -> dict:
    """自由聊天：无系统提示词，纯对话，不写章节。"""
    text = message.strip()
    if not text:
        return {"ok": False, "error": "消息不能为空"}

    global free_chat_provider
    pid = _resolve_free_provider(provider)
    if provider and pid != free_chat_provider:
        free_chat_provider = pid

    free_chat_history.append({"role": "user", "content": text})
    reply = call_api(
        None,
        _trim_free_history(),
        provider=pid,
        tag="自由聊",
        silent=True,
    )
    if reply is None:
        free_chat_history.pop()
        return {"ok": False, "error": get_last_call_info().get("error", "发送失败")}

    free_chat_history.append({"role": "assistant", "content": reply})
    save_free_chat()
    return {
        "ok": True,
        "reply": reply,
        "provider": pid,
        **get_last_call_info(),
    }


def clear_chat_session() -> None:
    global session_includes_chapter
    backup_session_before_clear()
    conversation_history.clear()
    session_includes_chapter = False
    appended_indices.clear()
    clear_session_files()


def get_app_status() -> dict:
    latest = get_latest_chapter()
    cfg = config.get_provider_config()
    return {
        "provider": config.PROVIDER,
        "provider_name": cfg["name"],
        "model": cfg["model"],
        "summary_provider": config.SUMMARY_PROVIDER,
        "check_provider": config.CHECK_PROVIDER,
        "context_turns": config.CHAT_CONTEXT_TURNS,
        "context_mode": config.CONTEXT_MODE,
        "total_cost": total_cost,
        "chapter_num": latest[0] if latest else None,
        "summary_count": count_summaries(),
        "history_len": len(conversation_history),
        "active_scene_id": novel_data.load_plan().get("active_scene_id"),
        "active_codex": novel_data.get_active_codex_ids(),
        "codex_count": len(novel_data.list_codex_entries()),
        "free_chat_provider": free_chat_provider,
        "free_chat_len": len(free_chat_history),
        "api_key_ok": config.is_api_key_configured(),
        "api_keys": {
            key: config.is_api_key_configured(key) for key in config.PROVIDERS
        },
    }


def api_run_summary() -> dict:
    latest = get_latest_chapter()
    if latest is None:
        return {"ok": False, "error": "没有找到章节文件"}
    chapter_num, _, content = latest
    if not content.strip():
        return {"ok": False, "error": f"第{chapter_num}章内容为空"}

    pid = config.SUMMARY_PROVIDER
    system = build_cached_system(SUMMARY_SYSTEM, provider=pid)
    messages = [{"role": "user", "content": build_summary_user_message(chapter_num, content)}]
    reply = call_api(system, messages, provider=pid, tag="概述", silent=True)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "生成失败")}

    write_text(SUMMARIES_FILE, f"\n{reply.strip()}\n", append=True)
    return {"ok": True, "reply": reply, "chapter_num": chapter_num, **get_last_call_info()}


def api_run_check() -> dict:
    latest = get_latest_chapter()
    if latest is None:
        return {"ok": False, "error": "没有找到章节文件"}
    chapter_num, _, chapter_content = latest
    pid = config.CHECK_PROVIDER
    system = build_cached_system(CHECK_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_check_user_message(
                read_text(WORLD_FILE),
                read_text(CHARACTERS_FILE),
                read_text(CHAR_CURRENT_FILE),
                read_text(SUMMARIES_FILE),
                chapter_num,
                chapter_content,
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="检查", silent=True)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "检查失败")}
    return {"ok": True, "reply": reply, "chapter_num": chapter_num, **get_last_call_info()}


def get_chapter_by_num(num: int) -> dict | None:
    path = CHAPTERS_DIR / f"ch{num:03d}.md"
    if not path.exists():
        return None
    return {"num": num, "path": str(path.name), "content": read_text(path)}


def save_chapter_by_num(num: int, content: str) -> dict:
    path = CHAPTERS_DIR / f"ch{num:03d}.md"
    write_text(path, content, append=False)
    return {"ok": True, "num": num}


def create_next_chapter() -> dict:
    chapters = list_chapters()
    next_num = (chapters[-1][0] + 1) if chapters else 1
    path = CHAPTERS_DIR / f"ch{next_num:03d}.md"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return {"ok": True, "num": next_num}


def get_codex(name: str) -> dict | None:
    path = CODEX_FILES.get(name)
    if path is None:
        return None
    return {"name": name, "content": read_text(path)}


def save_codex(name: str, content: str) -> dict:
    path = CODEX_FILES.get(name)
    if path is None:
        return {"ok": False, "error": f"未知设定文件: {name}"}
    write_text(path, content, append=False)
    return {"ok": True, "name": name}


def do_summary() -> None:
    latest = get_latest_chapter()
    if latest is None:
        print("错误：没有找到章节文件（data/chapters/ch001.md 等）")
        return

    chapter_num, _, content = latest
    if not content.strip():
        print(f"错误：第{chapter_num}章内容为空")
        return

    pid = config.SUMMARY_PROVIDER
    cfg = config.get_provider_config(pid)
    system = build_cached_system(SUMMARY_SYSTEM, provider=pid)
    messages = [{"role": "user", "content": build_summary_user_message(chapter_num, content)}]
    reply = call_api(system, messages, provider=pid, tag="概述")
    if reply is None:
        return

    append_text = f"\n{reply.strip()}\n"
    write_text(SUMMARIES_FILE, append_text, append=True)
    print(f"\n概述已追加（{cfg['name']}），下次 kie 写作请求将刷新缓存")
    print(reply)


def do_check() -> None:
    latest = get_latest_chapter()
    if latest is None:
        print("错误：没有找到章节文件")
        return

    chapter_num, _, chapter_content = latest
    world = read_text(WORLD_FILE)
    characters = read_text(CHARACTERS_FILE)
    summaries = read_text(SUMMARIES_FILE)

    pid = config.CHECK_PROVIDER
    system = build_cached_system(CHECK_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_check_user_message(
                world,
                characters,
                read_text(CHAR_CURRENT_FILE),
                summaries,
                chapter_num,
                chapter_content,
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="检查")
    if reply is not None:
        print(f"\n{reply}\n")


def do_patch(content: str) -> None:
    if not content.strip():
        print("用法：/patch 补充内容...")
        return

    draft_num = len(re.findall(r"【设定补充-第\d+稿", read_text(CHARACTERS_FILE))) + 1
    date_str = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n【设定补充-第{draft_num}稿-{date_str}】：{content.strip()}\n"
    write_text(CHARACTERS_FILE, entry, append=True)
    print(f"已追加到 characters.md（第{draft_num}稿）")


def do_heartbeat_toggle() -> None:
    if not config.supports_prompt_cache():
        print("当前提供商不支持 Prompt Cache，心跳无意义")
        return
    config.HEARTBEAT_ENABLED = not config.HEARTBEAT_ENABLED
    status = "已开启" if config.HEARTBEAT_ENABLED else "已关闭"
    print(f"智能心跳{status}")


def do_provider(arg: str) -> None:
    arg = arg.strip().lower()
    if not arg:
        print("可用提供商：")
        print(config.list_providers())
        print("\n用法：/provider kie  或  /provider deepseek")
        print("（只切换主力写作；/summary、/check 见 config.py 的 SUMMARY_PROVIDER、CHECK_PROVIDER）")
        return

    if arg not in config.PROVIDERS:
        print(f"未知提供商：{arg}")
        print(config.list_providers())
        return

    config.PROVIDER = arg
    reset_client(arg)
    cfg = config.get_provider_config()
    print(f"✅ 主力写作已切换至 {cfg['name']}（模型: {cfg['model']}）")
    print(f"   /summary → {config.SUMMARY_PROVIDER}  |  /check → {config.CHECK_PROVIDER}（不变）")
    if not config.supports_prompt_cache():
        print("   该提供商不支持 Prompt Cache，心跳已自动跳过")
    elif not config.is_api_key_configured():
        print(f"   ⚠️  请配置 {cfg['api_key_env']}")


def do_cost() -> None:
    print(f"累计总费用：${total_cost:.6f}")
    if COST_LOG.exists():
        print(f"详细记录见：{COST_LOG}")


def backup_session_before_clear() -> None:
    if not conversation_history:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUPS_DIR / f"session_{ts}.md"
    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dest.write_text(format_session_markdown(saved_at, "before_new"), encoding="utf-8")
    print(f"旧会话已备份到 {dest}")


def do_new() -> None:
    global session_includes_chapter
    pending = count_unsaved_chapter_turns()
    if pending:
        print(f"⚠️  还有 {pending} 条正文未写入章节，正在补存…")
        flush_chapter_writes()
    backup_session_before_clear()
    conversation_history.clear()
    session_includes_chapter = False
    appended_indices.clear()
    clear_session_files()
    print("对话历史已清空（文档缓存保留）")


def print_help() -> None:
    print("""
可用命令：
  /summary   — 生成概述（默认 DeepSeek，config.SUMMARY_PROVIDER）
  /check     — 连续性检查（默认 DeepSeek，config.CHECK_PROVIDER）
  /patch     — 在 characters.md 末尾追加设定补充
  /heartbeat — 开关智能心跳（续命缓存，仅 kie）
  /provider  — 切换主力写作提供商（/summary /check 独立配置）
  /cost      — 显示累计 API 费用
  /new       — 清空对话历史（保留文档缓存）
  /save      — 将未写入的 AI 正文补存到章节 + 保存会话
  /restore   — 恢复上次自动保存的会话
  /help      — 显示此帮助
  /quit      — 退出程序

直接输入文字即为写作指令（默认模式）。
""")


def print_startup_banner() -> None:
    latest = get_latest_chapter()
    chapter_str = f"第{latest[0]}章" if latest else "（尚无章节）"
    summary_count = count_summaries()

    cfg = config.get_provider_config()
    sum_cfg = config.get_provider_config(config.SUMMARY_PROVIDER)
    chk_cfg = config.get_provider_config(config.CHECK_PROVIDER)
    print("=== 小说写作助手 ===")
    print(f"🔌 主力写作：{cfg['name']}（{cfg['model']}）")
    print(f"📋 /summary → {sum_cfg['name']}  |  /check → {chk_cfg['name']}")

    if config.supports_prompt_cache():
        if config.HEARTBEAT_ENABLED:
            cache_ttl = "1h" if config.USE_1H_CACHE else "5m"
            idle_min = config.HEARTBEAT_IDLE_STOP // 60
            print(f"💓 智能心跳已开启（缓存:{cache_ttl}，离开{idle_min}分钟自动停）")
        else:
            print("💓 智能心跳已关闭")
    else:
        print("💓 Prompt Cache 不可用（DeepSeek 模式，心跳已跳过）")
    print(f"当前章节：{chapter_str}（自动检测最新章节）")
    print(f"已加载概述：{summary_count}章")
    if config.AUTO_APPEND_CHAPTER:
        print("💾 续写正文将自动保存到最新章节（写入前自动备份）")
    else:
        print("💡 续写正文需手动 /save 才会写入章节")
    print("输入你的写作指令，或输入 /help 查看命令")
    remind_pending_session_on_startup()


def send_heartbeat() -> None:
    system = build_cached_system(WRITING_INSTRUCTION)
    messages = [{"role": "user", "content": "."}]
    call_api(system, messages, max_tokens=1, tag="心跳", silent=True)


def heartbeat_loop() -> None:
    while not _heartbeat_stop.is_set():
        _heartbeat_stop.wait(config.HEARTBEAT_INTERVAL)
        if _heartbeat_stop.is_set():
            break

        if not config.HEARTBEAT_ENABLED or not config.cache_enabled():
            continue

        now = time.time()
        idle = now - last_user_active
        since_request = now - last_request_time if last_request_time > 0 else float("inf")

        if idle > config.HEARTBEAT_IDLE_STOP:
            continue
        if since_request < config.HEARTBEAT_REFRESH_AFTER:
            continue
        if last_request_time == 0:
            continue

        send_heartbeat()


def start_heartbeat_thread() -> threading.Thread:
    t = threading.Thread(target=heartbeat_loop, daemon=True, name="heartbeat")
    t.start()
    return t


def main() -> None:
    global total_cost, last_request_time

    init_data_dirs()
    total_cost = load_total_cost()
    setup_exit_handlers()

    print_startup_banner()
    start_heartbeat_thread()

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            graceful_exit()
            break

        if not user_input:
            continue

        touch_user_active()

        if user_input.startswith("/"):
            cmd_parts = user_input.split(maxsplit=1)
            cmd = cmd_parts[0].lower()
            arg = cmd_parts[1] if len(cmd_parts) > 1 else ""

            if cmd in ("/quit", "/exit", "/q"):
                graceful_exit()
            elif cmd == "/help":
                print_help()
            elif cmd == "/summary":
                do_summary()
            elif cmd == "/check":
                do_check()
            elif cmd == "/patch":
                do_patch(arg)
            elif cmd == "/heartbeat":
                do_heartbeat_toggle()
            elif cmd == "/provider":
                do_provider(arg)
            elif cmd == "/cost":
                do_cost()
            elif cmd == "/new":
                do_new()
            elif cmd == "/save":
                do_save()
            elif cmd == "/restore":
                do_restore()
            else:
                print(f"未知命令：{cmd}，输入 /help 查看帮助")
        else:
            do_writing(user_input)


if __name__ == "__main__":
    main()
