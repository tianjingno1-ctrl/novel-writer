#!/usr/bin/env python3
"""长篇小说辅助写作工具 — 主程序。"""

from __future__ import annotations

import atexit
import json
import re
import signal
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import config
import change_history
import quality_log
import runtime_log
import file_utils
import novel_data
from app_state import state
from core.api import TokenUsage
from core import chapters as chapter_text
from core import context as writing_context
from app import batch_state
from app.bootstrap import init_context
from app.factories import (
    apply_chapter_title,
    book_paths_view as _book_paths_view,
    book_store as _book_store,
    generator_deps as _generator_deps,
    invalidate_chapter_injection as _invalidate_chapter_injection,
    maintain_deps as _maintain_deps,
    quality_log_entry as _quality_log_entry,
    resolve_chapter_num as _resolve_chapter_num,
    reviewer_deps as _reviewer_deps,
    short_story_archive_skip as _short_story_archive_skip,
)
from app.chapter_titles import (
    refresh_chapter_file_header,
    sync_all_chapter_titles_from_files,
)
from app.chapters_api import (
    create_next_chapter,
    get_chapter_by_num,
    list_chapters,
    save_chapter_by_num,
)
from app.codex import get_codex, save_codex
from app.guide import get_guide_status
from app.free_chat import (
    _active_free_thread,
    _default_free_thread_title,
    _ensure_free_chat_threads,
    _find_free_thread,
    _free_chat_now,
    _free_thread_summary,
    _new_free_thread,
    _new_free_thread_id,
    _persist_active_thread_messages,
    _resolve_free_provider,
    _sync_free_history_from_active,
    _thread_title_from_message,
    _trim_free_history,
    clear_free_chat,
    create_free_chat_thread,
    delete_free_chat_message,
    delete_free_chat_thread,
    free_chat,
    get_free_chat_history,
    get_free_chat_provider,
    get_free_chat_state,
    get_free_chat_threads,
    load_free_chat,
    rename_free_chat_thread,
    save_free_chat,
    set_free_chat_provider,
    switch_free_chat_thread,
)
from summarizer import (
    CHECK_SYSTEM,
    OUTLINE_SYSTEM,
    SUMMARY_SYSTEM,
    WRITING_INSTRUCTION,
    build_check_user_message,
    build_outline_user_message,
    build_summary_user_message,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHAPTERS_DIR = DATA_DIR / "chapters"
BACKUPS_DIR = DATA_DIR / "backups"
COST_LOG = BASE_DIR / "cost_log.txt"
COST_LOG_JSONL = BASE_DIR / "cost_log.jsonl"
CONTEXT_LOG_JSONL = DATA_DIR / "context_log.jsonl"
SESSION_FILE = DATA_DIR / "session_autosave.json"

SESSION_MD_FILE = DATA_DIR / "session_autosave.md"
FREE_CHAT_FILE = DATA_DIR / "free_chat.json"

WORLD_FILE = DATA_DIR / "world.md"
STYLE_FILE = DATA_DIR / "style.md"
CHARACTERS_FILE = DATA_DIR / "characters.md"
CHAR_CURRENT_FILE = DATA_DIR / "char_current.md"
CHAR_STATIC_FILE = DATA_DIR / "char_static.md"
CHAR_DYNAMIC_FILE = DATA_DIR / "char_dynamic.md"
SUMMARIES_FILE = DATA_DIR / "summaries.md"
SUMMARIES_ARCHIVE_FILE = DATA_DIR / "summaries_archive.md"
SUMMARIES_RECENT_FILE = DATA_DIR / "summaries_recent.md"
PLOT_THREADS_FILE = DATA_DIR / "plot_threads.md"
PLOT_THREADS_LOCKED_FILE = DATA_DIR / "plot_threads_locked.md"
PLOT_THREADS_ACTIVE_FILE = DATA_DIR / "plot_threads_active.md"
OUTLINE_LATEST_FILE = DATA_DIR / "outline_latest.md"
CHAT_PROMPTS_FILE = DATA_DIR / "chat_prompts.json"
ARCHIVE_FILE = DATA_DIR / "book_archive.md"

DEFAULT_CHAT_PROMPTS = {
    "prompts": [
        {
            "id": "continue-style",
            "title": "续写（带文风）",
            "content": (
                "【文风参考 style.md】节奏快，女主掌控感，动作>心理，禁用心理独白堆砌。\n"
                "古代背景须遵守 style.md「语言时代约束」：禁止现代网络用语与互联网隐喻，白话章回体。\n"
                "续写 800 字，保持当前场景情绪，章内留一个小钩子。"
            ),
        },
        {
            "id": "polish-style",
            "title": "润色（去套话）",
            "content": (
                "【文风参考 style.md】润色上一段：删禁用词，缩短心理描写，"
                "加强动作与对话节奏，女主台词简洁不解释。"
            ),
        },
        {
            "id": "爽点加强",
            "title": "加强爽点",
            "content": (
                "【文风参考 style.md】加强本段爽感：短句、留白、围观反应，"
                "女主用结果反击而非解释；对照 world.md 当前世界爽点设计。"
            ),
        },
        {
            "id": "emotion-show",
            "title": "续写（情感具象）",
            "content": (
                "【文风参考 style.md】续写 600 字。\n"
                "不要直接写角色情绪名（难过/心疼/愤怒），用动作、细节、环境传递；\n"
                "遵守 char_static.md 性格锚点与禁止写法；对照 Beat 里的【节奏档位】。"
            ),
        },
        {
            "id": "repeat-check",
            "title": "套话检查",
            "content": (
                "[讨论] 请检查当前章节正文中出现频率过高的词语或句式，列出 TOP5，"
                "并给出替换建议。对照 style.md「本书已出现过多」清单，"
                "建议新增禁用的条目。"
            ),
        },
    ],
}

INITIAL_FILE_TEMPLATES = {
    "world": (
        "# 全书世界观\n\n"
        "## 主线框架\n\n"
        "- **类型**：快穿\n"
        "- **主角**：【女主名】，绑定系统，穿越各个世界完成任务\n"
        "- **核心爽点风格**：【打脸逆袭型 / 虐渣甜宠型 / 双强互撩型】\n"
        "- **全书基调**：爽文向，节奏快，不拖沓，女主永远主动掌控局面\n\n"
        "## 女主人设（全书通用）\n\n"
        "（性格、能力、底线、禁区）\n\n"
        "## 系统设定\n\n"
        "（名称、性格、任务规则、能否干预）\n\n"
        "---\n\n"
        "# 世界档案\n\n"
        "## 世界一：【世界名】\n\n"
        "### 五点骨架\n\n"
        "①入场 ②任务 ③核心冲突 ④高潮爽点 ⑤离场\n\n"
        "### 章节节拍（10–15 章）\n\n"
        "| 章节 | 核心事件 | 情绪目标 | 爽点类型 |\n\n"
        "### 爽点设计\n\n"
        "| 类型 | 具体设计 | 建议落点 |\n"
    ),
    "style": (
        "# 文风锚点文档\n\n"
        "> 写第一章正文前必须填写。续写时 AI 会参考本文件。\n\n"
        "## 一、风格定位\n\n"
        "- **整体基调**：\n"
        "- **叙事视角**：\n"
        "- **情感密度**：动作 > 对话 > 心理\n"
        "- **节奏要求**：每 500 字至少一个情绪转折或信息反转\n\n"
        "## 二、示范句\n\n"
        "（粘贴你喜欢的段落 + 不喜欢的段落）\n\n"
        "## 三、禁用词与禁用写法\n\n"
        "（列出禁用词）\n\n"
        "## 四、对话规范\n\n"
        "（男主/女主/系统台词风格）\n"
    ),
    "characters": "# 人物初始设定\n\n（在此填写主要人物的初始设定，只追加不修改）\n",
    "char_current": (
        "# 人物状态（已拆分）\n\n"
        "> 请改用：`char_static.md`（性格锚点，缓存②）+ `char_dynamic.md`（当前状态，每章更新）。\n"
        "> 本文件仅作兼容占位，续写不再读取。\n"
    ),
    "char_static": (
        "# 人物锚点（静态 · 缓存层）\n\n"
        "> 人物本质、深层软肋、禁止写法。极少改动。\n\n"
        "## 女主\n\n"
        "### 性格锚点\n"
        "- 表面：\n"
        "- 内核：\n\n"
        "### 禁止写法\n"
        "- \n\n"
        "### 深层软肋\n"
        "- \n\n"
        "### 软肋的表现方式（禁止直说）\n"
        "❌ \n"
        "✅ \n"
    ),
    "char_dynamic": (
        "# 人物动态（每章更新 · 不缓存）\n\n"
        "> 章后维护：当前状态、表层软肋、关系阶段。\n\n"
        "## 女主 · 当前\n\n"
        "- 表层软肋：\n"
        "- 当前状态：\n"
        "- 当前情绪：\n\n"
        "## 男主 · 当前\n\n"
        "- 表层软肋：\n"
        "- 当前状态：\n\n"
        "## 双方关系\n\n"
        "- 阶段：\n"
    ),
    "summaries": "# 章节概述（兼容视图）\n\n> 自动生成概述写入 `summaries_recent.md`；归档见 `summaries_archive.md`。\n",
    "summaries_archive": "# 章节概述归档（缓存层）\n\n",
    "summaries_recent": (
        "# 近期概述（最近 3–5 章）\n\n"
        "> 每章「生成概述」追加在此；旧条可剪切到 `summaries_archive.md`。\n"
    ),
    "plot_threads": (
        "# 伏笔线索（已拆分）\n\n"
        "> 请改用：`plot_threads_locked.md`（细节钉子，缓存③）+ `plot_threads_active.md`（伏笔，每章更新）。\n"
    ),
    "plot_threads_locked": (
        "# 已钉死的细节（不能改）\n\n"
        "> 每出现新的具体数字、日期、专名、外貌细节，立刻追加一行。\n\n"
        "- 女主年龄：\n"
        "- 男主身高/标志特征：\n"
    ),
    "plot_threads_active": (
        "# 活跃伏笔线索\n\n"
        "## 未回收\n\n"
        "（伏笔条目）\n\n"
        "## 已回收\n\n"
        "（暂无）\n"
    ),
}

DISCUSSION_PREFIXES = ("[讨论]", "[问答]", "[建议]", "[说明]", "[分析]")
META_LINE_PREFIXES = ("以下是", "我建议", "可以考虑", "总结：", "分析：", "注意：", "说明：")

state.free_chat_provider = config.FREE_CHAT_PROVIDER


_heartbeat_stop = threading.Event()
_exiting = False


from app.cost import (
    _register_change_history,
    calc_cost,
    calc_cost_no_cache,
    get_total_cost,
    load_total_cost,
    load_total_cost_from_jsonl,
    log_cost,
    set_total_cost,
    _build_last_call_info,
)


CODEX_FILES = {
    "world": WORLD_FILE,
    "style": STYLE_FILE,
    "characters": CHARACTERS_FILE,
    "char_static": CHAR_STATIC_FILE,
    "char_dynamic": CHAR_DYNAMIC_FILE,
    "char_current": CHAR_CURRENT_FILE,
    "summaries_archive": SUMMARIES_ARCHIVE_FILE,
    "summaries_recent": SUMMARIES_RECENT_FILE,
    "summaries": SUMMARIES_FILE,
    "plot_threads_locked": PLOT_THREADS_LOCKED_FILE,
    "plot_threads_active": PLOT_THREADS_ACTIVE_FILE,
    "plot_threads": PLOT_THREADS_FILE,
}


def bootstrap_library() -> None:
    """初始化书库并绑定当前书路径（启动时调用一次）。"""
    runtime_log.init_runtime_log(BASE_DIR)
    import book_context

    book_context.init_library()
    _wire_app_context()


def _wire_app_context() -> None:
    """注册 AppContext（依赖工厂在 app.factories，init_context 绑定引用）。"""
    init_context()


def init_data_dirs() -> None:
    """首次运行：创建目录与空文件。"""
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    novel_data.CODEX_DIR.mkdir(parents=True, exist_ok=True)
    archive_exists = ARCHIVE_FILE.exists()
    import book_context

    archived_filenames = frozenset(book_context.ARCHIVE_SECTION_BY_FILENAME.keys())
    for key, path in CODEX_FILES.items():
        content = INITIAL_FILE_TEMPLATES.get(key)
        if not content or path.exists():
            continue
        if archive_exists and path.name in archived_filenames:
            continue
        path.write_text(content, encoding="utf-8")
    if not CHAT_PROMPTS_FILE.exists():
        file_utils.atomic_write_text(
            CHAT_PROMPTS_FILE,
            json.dumps(DEFAULT_CHAT_PROMPTS, ensure_ascii=False, indent=2),
        )
    novel_data.load_plan()
    _register_change_history()
    quality_log.init_quality_log(DATA_DIR)
    change_history.ensure_baseline_snapshot()


from app.book_io import (
    _archive_section_for_path,
    _sync_archive_section_from_file,
    backup_file,
    read_text,
    write_text,
)


def _bind_writing_context() -> None:
    """将 main 模块路径同步到 core.context（测试 patch main.WORLD_FILE 时亦生效）。"""
    writing_context.bind(
        writing_context.BookPaths(
            world_file=WORLD_FILE,
            style_file=STYLE_FILE,
            characters_file=CHARACTERS_FILE,
            char_static_file=CHAR_STATIC_FILE,
            char_dynamic_file=CHAR_DYNAMIC_FILE,
            char_current_file=CHAR_CURRENT_FILE,
            summaries_archive_file=SUMMARIES_ARCHIVE_FILE,
            summaries_recent_file=SUMMARIES_RECENT_FILE,
            summaries_file=SUMMARIES_FILE,
            plot_threads_locked_file=PLOT_THREADS_LOCKED_FILE,
            plot_threads_active_file=PLOT_THREADS_ACTIVE_FILE,
            plot_threads_file=PLOT_THREADS_FILE,
        ),
        read_text=read_text,
    )


def cache_block(text: str) -> dict:
    return writing_context.cache_block(text)


def _read_char_static() -> str:
    _bind_writing_context()
    return writing_context.read_char_static()


def _read_plot_locked() -> str:
    _bind_writing_context()
    return writing_context.read_plot_locked()


def _read_plot_active() -> str:
    _bind_writing_context()
    return writing_context.read_plot_active()


def _outline_context_ready() -> str | None:
    if get_latest_chapter() is None:
        return "没有找到章节文件"
    if count_summaries() == 0:
        return "请先生成章节概述（/summary 或 Web「生成概述」）"
    return None


def get_characters_block() -> str:
    _bind_writing_context()
    return writing_context.get_characters_block()


def get_stable_archive_block() -> str:
    _bind_writing_context()
    return writing_context.get_stable_archive_block()


def _collect_dynamic_layer_parts() -> list[dict]:
    _bind_writing_context()
    return writing_context.collect_dynamic_layer_parts()


def get_dynamic_context_block() -> str:
    _bind_writing_context()
    return writing_context.get_dynamic_context_block()


def get_char_context_for_check() -> str:
    _bind_writing_context()
    return writing_context.get_char_context_for_check()


def get_summaries_combined() -> str:
    _bind_writing_context()
    return writing_context.get_summaries_combined()


def get_world_block() -> str:
    _bind_writing_context()
    return writing_context.get_world_block()


def build_cached_system(
    instruction: str,
    provider: str | None = None,
    *,
    include_scene_context: bool = True,
) -> list[dict] | str:
    from app import llm

    return llm.build_cached_system(
        instruction,
        provider,
        include_scene_context=include_scene_context,
    )


def _record_context_debug(
    layers: list[dict],
    *,
    provider: str | None = None,
    messages: list[dict] | None = None,
    tag: str = "",
) -> None:
    from app import llm

    _bind_writing_context()
    writing_context.record_context_debug(
        layers,
        provider=provider,
        messages=messages,
        tag=tag,
        summarize_messages=llm._summarize_messages,
    )


def get_last_context_debug() -> dict:
    if not state.last_context_debug:
        return {"ok": False, "error": "尚无请求记录，请先发送一次写书对话、自由聊或检查类请求"}
    data = dict(state.last_context_debug)
    data["ok"] = True
    data["last_call"] = get_last_call_info()
    return data


def _estimate_tokens(text: str) -> int:
    from app import llm

    return llm._estimate_tokens(text)


def _analyze_system(system: list[dict] | str | None) -> dict[str, int]:
    from app import llm

    return llm._analyze_system(system)


def _summarize_messages(messages: list[dict]) -> list[dict]:
    from app import llm

    return llm._summarize_messages(messages)


def _build_context_report(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    tag: str,
    provider: str | None,
) -> dict:
    from app import llm

    return llm._build_context_report(
        system, messages, tag=tag, provider=provider
    )


def log_request_context(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    tag: str = "请求",
    provider: str | None = None,
) -> dict:
    from app import llm

    return llm.log_request_context(
        system, messages, tag=tag, provider=provider
    )


_USER_CHAPTER_BLOCK_RE = re.compile(
    r"^【当前章节：第(\d+)章】\s*\n+(.*?)(?:\n+【写作指令】|\Z)",
    re.DOTALL,
)


def prepare_messages_for_context(history: list[dict]) -> list[dict]:
    from app import llm

    return llm.prepare_messages_for_context(history)


def trim_history(history: list[dict], max_turns: int | None = None) -> list[dict]:
    from app import llm

    return llm.trim_history(history, max_turns)


def get_last_call_info() -> dict:
    from app import llm

    return llm.get_last_call_info()


def _is_stream_disconnect_error(exc: Exception) -> bool:
    from app import llm

    return llm._is_stream_disconnect_error(exc)


def _record_call_usage(usage: TokenUsage, pid: str, *, tag: str = "请求") -> None:
    from app import llm

    llm._record_call_usage(usage, pid, tag=tag)


def _api_error_message(exc: Exception) -> str:
    from app import llm

    return llm._api_error_message(exc)


def call_api(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    tag: str = "请求",
    provider: str | None = None,
    silent: bool = False,
) -> str | None:
    from app import llm

    return llm.call_api(
        system,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        tag=tag,
        provider=provider,
        silent=silent,
    )


def get_latest_chapter() -> tuple[int, Path, str] | None:
    chapters = list_chapters()
    if not chapters:
        return None
    num, path = chapters[-1]
    return num, path, read_text(path)


_APPEND_INSTRUCTION_KEYWORDS = (
    "续写",
    "接着写",
    "继续写",
    "接下去",
    "往后写",
    "续上一段",
    "往下写",
)
def resolve_write_chapter_num(
    chapter_num: int | None = None, scene_id: str = ""
) -> int:
    from app import chapter_io as ch

    return ch.resolve_write_chapter_num(chapter_num, scene_id)


def get_chapter_path(chapter_num: int) -> Path:
    from app import chapter_io as ch

    return ch.get_chapter_path(chapter_num)


def read_chapter_content(chapter_num: int) -> str:
    from app import chapter_io as ch

    return ch.read_chapter_content(chapter_num)


def ensure_chapter_path(chapter_num: int) -> Path:
    from app import chapter_io as ch

    return ch.ensure_chapter_path(chapter_num)


def get_or_create_write_chapter(chapter_num: int | None = None) -> tuple[int, Path]:
    from app import chapter_io as ch

    return ch.get_or_create_write_chapter(chapter_num)


def sanitize_chapter_text(text: str) -> str:
    from app import chapter_io as ch

    return ch.sanitize_chapter_text(text)


def instruction_save_mode(instruction: str) -> str:
    from app import chapter_io as ch

    return ch.instruction_save_mode(instruction)


def should_append_to_chapter(reply: str) -> bool:
    from app import chapter_io as ch

    return ch.should_append_to_chapter(reply)


def replace_chapter_content(
    text: str,
    chapter_path: Path,
    chapter_num: int,
    *,
    msg_index: int | None = None,
) -> tuple[int, str | None]:
    from app import chapter_io as ch

    return ch.replace_chapter_content(
        text, chapter_path, chapter_num, msg_index=msg_index
    )


def append_to_chapter(
    text: str,
    chapter_path: Path,
    *,
    msg_index: int | None = None,
    chapter_num: int | None = None,
) -> tuple[int, str | None]:
    from app import chapter_io as ch

    return ch.append_to_chapter(
        text, chapter_path, msg_index=msg_index, chapter_num=chapter_num
    )


def sync_appended_indices_with_chapter() -> None:
    from app import chapter_io as ch

    ch.sync_appended_indices_with_chapter()


def undo_last_chapter_append() -> dict:
    from app import writing_turns as wt

    return wt.undo_last_chapter_append()


def extract_chapter_body_from_user_message(content: str) -> str | None:
    """从首轮用户消息中取出附带的章节正文（不含写作指令）。"""
    m = _USER_CHAPTER_BLOCK_RE.match((content or "").strip())
    if not m:
        return None
    body = m.group(2).strip()
    return body or None


def parse_chapter_header_line(line: str) -> str | None:
    return chapter_text.parse_chapter_header_line(line)


def split_chapter_markdown_header(text: str) -> tuple[str | None, str]:
    return chapter_text.split_chapter_markdown_header(text)


def extract_chapter_title_from_reply(text: str) -> tuple[str | None, str]:
    return chapter_text.extract_chapter_title_from_reply(text)


def strip_chapter_file_header(text: str) -> str:
    return chapter_text.strip_chapter_file_header(text)


def sync_chapter_title_from_file(chapter_num: int) -> str | None:
    from app import chapter_io as ch

    return ch.sync_chapter_title_from_file(chapter_num)


def prepare_chapter_body_from_reply(
    reply: str, chapter_num: int
) -> tuple[str | None, str]:
    from app import chapter_io as ch

    return ch.prepare_chapter_body_from_reply(reply, chapter_num)


def format_chapter_file(
    chapter_num: int, body: str, *, title: str | None = None
) -> str:
    from app import chapter_io as ch

    return ch.format_chapter_file(chapter_num, body, title=title)


def _clear_assistant_appended_indices() -> None:
    for i, msg in enumerate(state.conversation_history):
        if msg["role"] == "assistant":
            state.appended_indices.discard(i)


def apply_assistant_turn_to_chapter(chapter_num: int, msg_index: int) -> dict:
    """用某条 AI 回复**替换**整章正文（非追加）。"""
    from app import writing_turns as wt

    return wt.apply_assistant_turn_to_chapter(chapter_num, msg_index)


def apply_user_draft_turn_to_chapter(chapter_num: int, msg_index: int) -> dict:
    """用首轮用户消息里附带的章节草稿替换整章正文。"""
    from app import writing_turns as wt

    return wt.apply_user_draft_turn_to_chapter(chapter_num, msg_index)


def do_undo() -> None:
    from app.cli import do_undo as _fn

    _fn()


def count_unsaved_chapter_turns() -> int:
    from app import chapter_io as ch

    return ch.count_unsaved_chapter_turns()


def flush_chapter_writes(*, silent: bool = False) -> int:
    from app import chapter_io as ch

    return ch.flush_chapter_writes(silent=silent)


def save_chapter_after_reply(
    reply: str,
    msg_index: int,
    *,
    write_chapter_num: int | None = None,
    instruction: str = "",
) -> dict | None:
    """AI 回复后自动保存到目标章节。"""
    from app import writing_chat as wc

    return wc.save_chapter_after_reply(
        reply,
        msg_index,
        write_chapter_num=write_chapter_num,
        instruction=instruction,
    )


def count_summaries() -> int:
    combined = get_summaries_combined()
    return len(re.findall(r"【第\d+章", combined))


def touch_user_active() -> None:
    from app import writing_session as ws

    ws.touch_user_active()


def _session_chapter_num() -> int:
    from app import writing_session as ws

    return ws._session_chapter_num()


def format_session_markdown(saved_at: str, reason: str) -> str:
    from app import writing_session as ws

    return ws.format_session_markdown(saved_at, reason)


def save_session(reason: str = "auto", *, silent: bool = False) -> bool:
    from app import writing_session as ws

    return ws.save_session(reason, silent=silent)


def clear_session_files() -> None:
    from app import writing_session as ws

    ws.clear_session_files()


def load_session_from_disk() -> dict | None:
    from app import writing_session as ws

    return ws.load_session_from_disk()


def has_pending_session() -> bool:
    from app import writing_session as ws

    return ws.has_pending_session()


def remind_pending_session_on_startup() -> None:
    from app import writing_session as ws

    ws.remind_pending_session_on_startup()


def restore_chat_session() -> dict:
    from app import writing_session as ws

    return ws.restore_chat_session()


def auto_restore_session_if_needed() -> bool:
    from app import writing_session as ws

    return ws.auto_restore_session_if_needed()


def do_restore() -> None:
    from app.cli import do_restore as _fn

    _fn()


def do_save() -> None:
    from app.cli import do_save as _fn

    _fn()


def remind_unsaved_on_exit() -> None:
    from app.cli import remind_unsaved_on_exit as _fn

    _fn()


def graceful_exit(message: str = "再见！") -> None:
    from app.cli import graceful_exit as _fn

    _fn(message)


def _handle_exit_signal(signum, frame) -> None:
    from app.cli import _handle_exit_signal as _fn

    _fn(signum, frame)


def _atexit_save() -> None:
    from app.cli import _atexit_save as _fn

    _fn()


def setup_exit_handlers() -> None:
    from app.cli import setup_exit_handlers as _fn

    _fn()


def do_writing(instruction: str) -> None:
    from app.cli import do_writing as _fn

    _fn(instruction)


def writing_chat(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> dict:
    """Web/API：结构化写作对话，返回 JSON 友好结果。"""
    from app import writing_chat as wc

    return wc.writing_chat(instruction, scene_beat, scene_id, chapter_num)


def writing_chat_stream(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
):
    """流式写作对话，yield JSON 字符串事件。"""
    from app import writing_chat as wc

    return wc.writing_chat_stream(instruction, scene_beat, scene_id, chapter_num)


def get_chat_history() -> list[dict]:
    from app import writing_session as ws

    return ws.get_chat_history()


def load_chat_prompts() -> dict:
    from app import writing_session as ws

    return ws.load_chat_prompts()


def save_chat_prompts(prompts: list[dict]) -> dict:
    from app import writing_session as ws

    return ws.save_chat_prompts(prompts)


def get_appended_indices() -> list[int]:
    from app import writing_session as ws

    return ws.get_appended_indices()


def set_write_chapter_num(num: int) -> dict:
    from app import writing_session as ws

    return ws.set_write_chapter_num(num)


def clear_chat_session() -> None:
    from app import writing_session as ws

    ws.clear_chat_session()


def get_app_status() -> dict:
    latest = get_latest_chapter()
    cfg = config.get_provider_config()
    project = novel_data.get_project_meta()
    book_id = ""
    book_type = "novel"
    try:
        import book_context

        book_id = book_context.get_context().book_id
        book_type = book_context.get_book_type()
    except RuntimeError:
        pass
    import review_prompts

    review_profile = review_prompts.active_profile_for_project(project)
    return {
        "book_id": book_id,
        "book_type": book_type,
        "platform": project.get("platform") or "tomato",
        "review_profile": review_profile,
        "project_title": project.get("title", ""),
        "world_label": project.get("world_label", ""),
        "provider": config.PROVIDER,
        "provider_name": cfg["name"],
        "model": cfg["model"],
        "summary_provider": config.SUMMARY_PROVIDER,
        "check_provider": config.CHECK_PROVIDER,
        "maintain_provider": config.MAINTAIN_PROVIDER,
        "quality_provider": config.QUALITY_PROVIDER,
        "outline_provider": config.OUTLINE_PROVIDER,
        "context_turns": config.CHAT_CONTEXT_TURNS,
        "context_mode": config.CONTEXT_MODE,
        "free_chat_context_turns": config.FREE_CHAT_CONTEXT_TURNS,
        "max_tokens": config.MAX_TOKENS,
        "free_chat_max_tokens": config.FREE_CHAT_MAX_TOKENS,
        "total_cost": state.total_cost,
        "chapter_num": latest[0] if latest else None,
        "write_chapter_num": state.write_chapter_num or None,
        "summary_count": count_summaries(),
        "history_len": len(state.conversation_history),
        "session_on_disk": has_pending_session(),
        "session_saved_at": (
            load_session_from_disk() or {}
        ).get("saved_at")
        if has_pending_session()
        else None,
        "active_scene_id": novel_data.load_plan().get("active_scene_id"),
        "active_codex": novel_data.get_active_codex_ids(),
        "codex_count": len(novel_data.list_codex_entries()),
        "free_chat_provider": state.free_chat_provider,
        "free_chat_len": len(state.free_chat_history),
        "free_chat_thread_count": len(state.free_chat_threads),
        "free_chat_active_thread_id": state.free_chat_active_thread_id,
        "free_chat_active_thread_title": (_active_free_thread() or {}).get("title", ""),
        "api_key_ok": config.is_api_key_configured(),
        "api_keys": {
            key: config.is_api_key_configured(key) for key in config.PROVIDERS
        },
        "writing_cache_supported": config.supports_prompt_cache(config.PROVIDER),
        "batch_job_running": state.batch_job_running,
        "batch_job_id": state.batch_job_id or None,
        "runtime_log": runtime_log.get_status(),
    }


def get_chapters_text_for_scope(chapter_num: int, scope: str) -> str | None:
    return _book_store().chapters_text_for_scope(chapter_num, scope)


def ensure_chapter_file(chapter_num: int, title: str = "") -> dict:
    from app.chapters_api import _ensure_chapter_file

    return _ensure_chapter_file(chapter_num, title)


def do_summary() -> None:
    from app.cli import do_summary as _fn

    _fn()


def do_check() -> None:
    from app.cli import do_check as _fn

    _fn()


def do_outline(next_count: int = 3) -> None:
    from app.cli import do_outline as _fn

    _fn(next_count)


def do_patch(content: str) -> None:
    from app.cli import do_patch as _fn

    _fn(content)


def do_heartbeat_toggle() -> None:
    from app.cli import do_heartbeat_toggle as _fn

    _fn()


def do_provider(arg: str) -> None:
    from app.cli import do_provider as _fn

    _fn(arg)


def do_cost() -> None:
    from app.cli import do_cost as _fn

    _fn()


def backup_session_before_clear() -> None:
    from app import writing_session as ws

    ws.backup_session_before_clear()


def do_new() -> None:
    from app.cli import do_new as _fn

    _fn()


def print_help() -> None:
    from app.cli import print_help as _fn

    _fn()


def print_startup_banner() -> None:
    from app.cli import print_startup_banner as _fn

    _fn()


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
        idle = now - state.last_user_active
        since_request = now - state.last_request_time if state.last_request_time > 0 else float("inf")

        if idle > config.HEARTBEAT_IDLE_STOP:
            continue
        if since_request < config.HEARTBEAT_REFRESH_AFTER:
            continue
        if state.last_request_time == 0:
            continue

        send_heartbeat()


def start_heartbeat_thread() -> threading.Thread:
    t = threading.Thread(target=heartbeat_loop, daemon=True, name="heartbeat")
    t.start()
    return t


def main() -> None:
    from app.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()

from app import llm as _llm_module

_request_lock = _llm_module._request_lock
