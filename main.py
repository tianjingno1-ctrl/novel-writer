#!/usr/bin/env python3
"""长篇小说辅助写作工具 — 主程序。"""

from __future__ import annotations

import atexit
import json
import logging
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
from core.api import APIError, CallOptions, TokenUsage, complete, get_client, reset_client, stream
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
_cost_lock = threading.Lock()
# 串行化 LLM 请求（call_api / writing_chat_stream），避免并发写会话与费用统计
_request_lock = threading.Lock()


_heartbeat_stop = threading.Event()
_exiting = False
_context_logger = logging.getLogger("novel_writer.context")


def get_total_cost() -> float:
    return state.total_cost


def set_total_cost(value: float) -> None:
    state.total_cost = value


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


def _archive_section_for_path(path: Path) -> str | None:
    import book_context

    return book_context.section_key_for_filename(path.name)


def _sync_archive_section_from_file(path: Path) -> None:
    """双写：将独立 md 全文同步到 book_archive.md 对应小节。"""
    section = _archive_section_for_path(path)
    if not section or not ARCHIVE_FILE.exists():
        return
    if not path.exists():
        return
    try:
        import book_context

        book_id = book_context.get_context().book_id
        body = path.read_text(encoding="utf-8")
        book_context.update_archive_section(book_id, section, body)
    except RuntimeError:
        return


def read_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    section = _archive_section_for_path(path)
    if section and ARCHIVE_FILE.exists():
        try:
            import book_context

            book_id = book_context.get_context().book_id
            return book_context.get_archive_section(book_id, section)
        except RuntimeError:
            pass
    return ""


def backup_file(path: Path) -> None:
    file_utils.backup_file(path, BACKUPS_DIR)


def write_text(
    path: Path,
    content: str,
    *,
    append: bool = False,
    history_source: str = "write",
    chapter_num: int | None = None,
) -> bool:
    """写入文件。返回是否实际变更磁盘内容。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    key = change_history.resolve_key(path)
    if key:
        entry_id = change_history.save_with_history(
            path,
            content,
            append=append,
            source=history_source,
            chapter_num=chapter_num if chapter_num is not None else _session_chapter_num(),
            file_key=key,
        )
        if entry_id is not None:
            _sync_archive_section_from_file(path)
        return entry_id is not None
    if append:
        existing = read_text(path)
        if not content:
            return False
        backup_file(path)
        file_utils.atomic_write_text(path, f"{existing}{content}")
        _sync_archive_section_from_file(path)
        return True
    if read_text(path) == content:
        return False
    backup_file(path)
    file_utils.atomic_write_text(path, content)
    _sync_archive_section_from_file(path)
    return True


def _register_change_history() -> None:
    tracked = dict(CODEX_FILES)
    tracked["plan"] = novel_data.PLAN_FILE
    change_history.init_history(DATA_DIR, tracked, backups_dir=BACKUPS_DIR)


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
    if COST_LOG_JSONL.exists():
        return load_total_cost_from_jsonl(COST_LOG_JSONL)
    if not COST_LOG.exists():
        return 0.0
    total = 0.0
    for line in COST_LOG.read_text(encoding="utf-8").splitlines():
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

    with _cost_lock:
        state.total_cost += cost
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        book_id = ""
        try:
            import book_context

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
        with COST_LOG_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        legacy_line = (
            f"[{ts}] [{tag}] "
            f"cache_read={cache_read} cache_write={cache_creation} "
            f"input={input_tokens} output={output_tokens} "
            f"费用: ${cost:.6f} 累计: ${state.total_cost:.6f}\n"
        )
        with COST_LOG.open("a", encoding="utf-8") as f:
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
    _bind_writing_context()
    return writing_context.build_cached_system(
        instruction,
        provider,
        include_scene_context=include_scene_context,
        summarize_messages=_summarize_messages,
    )


def _record_context_debug(
    layers: list[dict],
    *,
    provider: str | None = None,
    messages: list[dict] | None = None,
    tag: str = "",
) -> None:
    _bind_writing_context()
    writing_context.record_context_debug(
        layers,
        provider=provider,
        messages=messages,
        tag=tag,
        summarize_messages=_summarize_messages,
    )


def get_last_context_debug() -> dict:
    if not state.last_context_debug:
        return {"ok": False, "error": "尚无请求记录，请先发送一次写书对话、自由聊或检查类请求"}
    data = dict(state.last_context_debug)
    data["ok"] = True
    data["last_call"] = get_last_call_info()
    return data


def _estimate_tokens(text: str) -> int:
    return writing_context.estimate_tokens(text)


def _analyze_system(system: list[dict] | str | None) -> dict[str, int]:
    labels = ("world", "characters", "stable_archive", "instruction")
    parts: dict[str, int] = {}
    if isinstance(system, list):
        for i, block in enumerate(system):
            key = labels[i] if i < len(labels) else f"block_{i}"
            if isinstance(block, dict):
                text = str(block.get("text", ""))
            else:
                text = str(block)
            parts[key] = len(text)
        return parts
    if isinstance(system, str) and system.strip():
        markers = (
            ("world", "# 世界观"),
            ("characters", "# 人物设定"),
            ("stable_archive", "# 归档与细节钉子"),
            ("instruction", "# 当前任务"),
        )
        lower = system
        for idx, (key, marker) in enumerate(markers):
            start = lower.find(marker)
            if start < 0:
                continue
            end = len(lower)
            for _, next_marker in markers[idx + 1 :]:
                pos = lower.find(next_marker, start + len(marker))
                if pos >= 0:
                    end = min(end, pos)
            parts[key] = len(lower[start:end].strip())
        if not parts:
            parts["system_total"] = len(system)
    return parts


def _summarize_messages(messages: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for i, msg in enumerate(messages):
        content = str(msg.get("content", ""))
        preview = content[:120].replace("\n", " ").strip()
        rows.append(
            {
                "i": i,
                "role": msg.get("role", "?"),
                "chars": len(content),
                "est_tokens": _estimate_tokens(content),
                "preview": preview,
                "has_chapter": "【当前章节" in content,
                "has_beat": "Scene Beat" in content or "场景指令" in content,
            }
        )
    return rows


def _build_context_report(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    tag: str,
    provider: str | None,
) -> dict:
    pid = config.resolve_provider(provider)
    system_parts = _analyze_system(system)
    system_chars = sum(system_parts.values())
    if not system_parts and isinstance(system, str):
        system_chars = len(system)
    msg_rows = _summarize_messages(messages)
    messages_chars = sum(r["chars"] for r in msg_rows)
    total_chars = system_chars + messages_chars
    est_tokens = _estimate_tokens(
        (system if isinstance(system, str) else json.dumps(system, ensure_ascii=False))
    ) + sum(r["est_tokens"] for r in msg_rows)
    chapter_row = next((r for r in msg_rows if r["has_chapter"]), None)
    warnings: list[str] = []
    if total_chars >= 150_000:
        warnings.append(f"总上下文约 {total_chars:,} 字，可能接近模型上限")
    if chapter_row and chapter_row["chars"] >= 60_000:
        warnings.append(
            f"首轮用户消息含章节正文 {chapter_row['chars']:,} 字，占比较大"
        )
    if len(msg_rows) > config.CHAT_CONTEXT_TURNS * 2 + 2:
        warnings.append(f"对话消息 {len(msg_rows)} 条，偏多")
    codex_ids = novel_data.get_active_codex_ids()
    scene = novel_data.get_active_scene()
    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "provider": pid,
        "model": config.get_model(pid),
        "context_mode": config.CONTEXT_MODE,
        "context_turns_limit": config.CHAT_CONTEXT_TURNS,
        "system_parts": system_parts,
        "system_chars": system_chars,
        "messages": msg_rows,
        "messages_chars": messages_chars,
        "total_chars": total_chars,
        "est_tokens": est_tokens,
        "message_count": len(msg_rows),
        "session_includes_chapter": state.session_includes_chapter,
        "active_codex_count": len(codex_ids),
        "active_codex_ids": codex_ids[:20],
        "active_scene_id": scene.get("id") if scene else None,
        "active_scene_title": scene.get("title") if scene else None,
        "warnings": warnings,
    }


def log_request_context(
    system: list[dict] | str | None,
    messages: list[dict],
    *,
    tag: str = "请求",
    provider: str | None = None,
) -> dict:
    """记录即将发出的 API 上下文体积，便于排查过长问题。"""
    report = _build_context_report(system, messages, tag=tag, provider=provider)
    if isinstance(system, list):
        layers = []
        labels = ("layer1", "layer2", "layer3", "layer4")
        titles = (
            "① world + style",
            "② char_static + 人物",
            "③ summaries_archive + plot_threads_locked",
            "④ 动态层",
        )
        for i, block in enumerate(system):
            text = str(block.get("text", "")) if isinstance(block, dict) else str(block)
            cached = isinstance(block, dict) and "cache_control" in block
            layers.append(
                {
                    "id": labels[i] if i < len(labels) else f"block_{i}",
                    "label": titles[i] if i < len(titles) else f"block {i + 1}",
                    "cached": cached,
                    "content": text,
                }
            )
        _record_context_debug(layers, provider=provider, messages=messages, tag=tag)
    elif system:
        text = str(system)
        _record_context_debug(
            [
                {
                    "id": "system",
                    "label": "system prompt",
                    "cached": False,
                    "content": text,
                }
            ],
            provider=provider,
            messages=messages,
            tag=tag,
        )
    else:
        _record_context_debug(
            [
                {
                    "id": "none",
                    "label": "（无 system · 纯对话）",
                    "cached": False,
                    "content": "",
                }
            ],
            provider=provider,
            messages=messages,
            tag=tag,
        )
    if not config.CONTEXT_LOG_ENABLED:
        return report

    line = json.dumps(report, ensure_ascii=False)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONTEXT_LOG_JSONL, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    parts = report["system_parts"]
    part_txt = ", ".join(f"{k}={v:,}" for k, v in parts.items()) if parts else "—"
    warn_txt = f" ⚠ {'; '.join(report['warnings'])}" if report["warnings"] else ""
    summary = (
        f"[上下文] {tag} · {report['provider']}/{report['model']} · "
        f"{report['context_mode']} · "
        f"合计 {report['total_chars']:,} 字 / 约 {report['est_tokens']:,} tokens · "
        f"消息 {report['message_count']} 条\n"
        f"  system({report['system_chars']:,}): {part_txt}\n"
        f"  messages({report['messages_chars']:,}): "
        f"Codex勾选 {report['active_codex_count']} · "
        f"场景 {report['active_scene_title'] or '无'}"
        f"{warn_txt}"
    )
    print(summary)
    _context_logger.info(summary)
    return report


_USER_CHAPTER_BLOCK_RE = re.compile(
    r"^【当前章节：第(\d+)章】\s*\n+(.*?)(?:\n+【写作指令】|\Z)",
    re.DOTALL,
)


def _history_has_chapter_block(history: list[dict], chapter_num: int) -> bool:
    for msg in history:
        if msg.get("role") != "user":
            continue
        m = _USER_CHAPTER_BLOCK_RE.match((msg.get("content") or "").strip())
        if m and int(m.group(1)) == chapter_num:
            return True
    return False


def _sync_chapter_injection_after_trim(trimmed: list[dict]) -> list[dict]:
    if (
        state.session_includes_chapter
        and state.last_injected_chapter_num > 0
        and not _history_has_chapter_block(trimmed, state.last_injected_chapter_num)
    ):
        state.session_includes_chapter = False
    return trimmed


def prepare_messages_for_context(history: list[dict]) -> list[dict]:
    """按 CHAT_CONTEXT_TURNS 截断写书对话历史；0 表示不截断。"""
    return _sync_chapter_injection_after_trim(trim_history(history))


def trim_history(history: list[dict], max_turns: int | None = None) -> list[dict]:
    """保留最近 N 轮对话；首轮含章节正文时不单独特殊处理。"""
    turns = max_turns if max_turns is not None else config.CHAT_CONTEXT_TURNS
    if turns <= 0 or len(history) <= turns * 2:
        return list(history)
    return history[-(turns * 2) :]


def get_last_call_info() -> dict:
    return dict(state.last_call_info)


def _is_stream_disconnect_error(exc: Exception) -> bool:
    if isinstance(exc, APIError) and exc.kind == "network":
        return True
    lower = str(exc).lower()
    return "peer closed" in lower or "incomplete chunked" in lower


def _record_call_usage(usage: TokenUsage, pid: str, *, tag: str = "请求") -> None:
    state.last_request_time = time.time()
    cost = calc_cost(usage, provider=pid)
    log_cost(usage, cost, tag, provider=pid, silent=True)
    state.last_call_info = _build_last_call_info(usage, cost, pid)


def _api_error_message(exc: Exception) -> str:
    raw = str(exc)
    if "blocked" in raw.lower():
        return (
            f"{raw} — 多为 AI 服务商（kie/Cloudflare）拦截。"
            "可尝试：① 换 DeepSeek 模型 ② 检查 .env 的 KIE_API_KEY ③ 缩短/调整指令内容 ④ 稍后重试"
        )
    if isinstance(exc, APIError):
        hints = {
            "auth": "请检查 .env 中的 API Key 是否正确",
            "rate_limit": "请求过于频繁，请稍后重试",
            "timeout": "请求超时，请检查网络或稍后重试",
            "network": "网络或 AI 服务连接中断，请重试、换模型或检查 API Key/余额",
            "server_error": (
                "AI 服务商暂时异常（多为 kie 网关 500）。"
                "请稍后重试；自由聊建议切到 DeepSeek；写书可暂换 DeepSeek 或换 Sonnet/Opus 型号"
            ),
        }
        hint = hints.get(exc.kind)
        return f"{exc} — {hint}" if hint else raw
    return raw


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
    pid = config.resolve_provider(provider)
    if not config.is_api_key_configured(pid):
        cfg = config.get_provider_config(pid)
        err = (
            f"请设置 {cfg['api_key_env']}，或在 .env / config.py 中填写 API Key"
        )
        state.last_call_info = {"ok": False, "error": err, "provider": pid}
        if not silent:
            print(f"错误：{err}")
        return None

    t_start = time.time()
    lock_wait_ms = 0
    api_ms = 0
    msg_count = len(messages)
    eff_max_tokens = max_tokens or config.MAX_TOKENS
    api_options = CallOptions(
        max_tokens=eff_max_tokens,
        temperature=temperature,
        provider=pid,
    )
    try:
        log_request_context(system, messages, tag=tag, provider=pid)
        t_before_lock = time.time()
        with _request_lock:
            lock_wait_ms = int((time.time() - t_before_lock) * 1000)
            t_api = time.time()
            text, usage = complete(system, messages, options=api_options)
            api_ms = int((time.time() - t_api) * 1000)
            state.last_request_time = time.time()

        cost = calc_cost(usage, provider=pid)
        log_cost(usage, cost, tag, provider=pid, silent=silent)
        state.last_call_info = _build_last_call_info(usage, cost, pid)
        truncated = usage.stop_reason in ("max_tokens", "length") or (
            usage.output_tokens >= max(1, int(eff_max_tokens * 0.92))
        )
        state.last_call_info["max_tokens"] = eff_max_tokens
        state.last_call_info["output_truncated"] = truncated
        return text
    except ImportError as e:
        state.last_call_info = {"ok": False, "error": str(e)}
        if not silent:
            print(f"依赖缺失：{e}")
        return None
    except APIError as e:
        err = _api_error_message(e)
        state.last_call_info = {"ok": False, "error": err, "kind": e.kind}
        runtime_log.log_api_error(
            "main.py:call_api",
            err,
            kind=e.kind,
            provider=pid,
            tag=tag,
            exc=e,
        )
        if not silent:
            print(f"API 错误：{err}")
        return None
    except Exception as e:
        err = _api_error_message(e)
        state.last_call_info = {"ok": False, "error": err}
        runtime_log.log_api_error(
            "main.py:call_api",
            err,
            provider=pid,
            tag=tag,
            exc=e,
        )
        if not silent:
            print(f"API 错误：{err}")
        return None


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
    """确定本次写入/注入的目标章节：显式章号 > 场景章 > 会话章 > 最新章。"""
    if chapter_num and chapter_num > 0:
        return chapter_num
    if scene_id:
        scene = novel_data.get_scene(scene_id)
        if scene and scene.get("chapter_num"):
            return int(scene["chapter_num"])
    if state.write_chapter_num > 0:
        return state.write_chapter_num
    latest = get_latest_chapter()
    return latest[0] if latest else 1


def get_chapter_path(chapter_num: int) -> Path:
    return CHAPTERS_DIR / f"ch{chapter_num:03d}.md"


def read_chapter_content(chapter_num: int) -> str:
    path = get_chapter_path(chapter_num)
    return read_text(path) if path.exists() else ""


def ensure_chapter_path(chapter_num: int) -> Path:
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    path = get_chapter_path(chapter_num)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def get_or_create_write_chapter(chapter_num: int | None = None) -> tuple[int, Path]:
    """获取目标章节路径；未指定时用 resolve_write_chapter_num。"""
    num = resolve_write_chapter_num(chapter_num)
    return num, ensure_chapter_path(num)


def sanitize_chapter_text(text: str) -> str:
    return chapter_text.sanitize_chapter_text(text)


def instruction_save_mode(instruction: str) -> str:
    return chapter_text.instruction_save_mode(instruction)


def should_append_to_chapter(reply: str) -> bool:
    return chapter_text.should_append_to_chapter(reply)


def replace_chapter_content(
    text: str,
    chapter_path: Path,
    chapter_num: int,
    *,
    msg_index: int | None = None,
) -> tuple[int, str | None]:
    """用 AI 回复覆盖整章正文（非追加）。返回 (正文字数, 标题)。"""
    title, body = prepare_chapter_body_from_reply(text, chapter_num)
    if not body.strip():
        return 0, title
    chapter_text = format_chapter_file(chapter_num, body, title=title)
    state.last_append_undo = {
        "path": str(chapter_path),
        "content": read_text(chapter_path),
        "msg_index": msg_index,
    }
    write_text(chapter_path, chapter_text, append=False)
    return len(body), title


def append_to_chapter(
    text: str,
    chapter_path: Path,
    *,
    msg_index: int | None = None,
    chapter_num: int | None = None,
) -> tuple[int, str | None]:
    """将正文追加到章节文件。返回 (正文字数, 标题)。"""
    if chapter_num is None:
        m = re.match(r"ch(\d+)\.md$", chapter_path.name, re.IGNORECASE)
        chapter_num = int(m.group(1)) if m else 0
    if chapter_num > 0:
        title, body = prepare_chapter_body_from_reply(text, chapter_num)
    else:
        title, body = extract_chapter_title_from_reply(text)
    content = body.strip()
    if not content:
        return 0, title
    existing = read_text(chapter_path)
    state.last_append_undo = {
        "path": str(chapter_path),
        "content": existing,
        "msg_index": msg_index,
    }
    if not existing.strip() and chapter_num > 0:
        chapter_text = format_chapter_file(chapter_num, content, title=title)
        write_text(chapter_path, chapter_text, append=False)
        return len(content), title
    if chapter_num > 0 and title:
        refresh_chapter_file_header(chapter_num, title)
    write_text(chapter_path, f"\n\n{content}\n", append=True)
    return len(content), title


def sync_appended_indices_with_chapter() -> None:
    """若章节中已含某条助手正文，则标记为已写入，避免 /restore 后重复追加。"""
    if not state.conversation_history:
        return
    _, chapter_path = get_or_create_write_chapter()
    chapter_text = read_text(chapter_path)
    if not chapter_text.strip():
        return
    for i, msg in enumerate(state.conversation_history):
        if msg["role"] != "assistant" or i in state.appended_indices:
            continue
        if not should_append_to_chapter(msg["content"]):
            continue
        content = msg["content"].strip()
        if len(content) >= 80 and content in chapter_text:
            state.appended_indices.add(i)


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
    """从章节 md 首行同步标题到 plan.json。"""
    text = read_chapter_content(chapter_num)
    if not text.strip():
        return None
    title, _ = split_chapter_markdown_header(text)
    if not title:
        title, _ = extract_chapter_title_from_reply(text)
    return apply_chapter_title(chapter_num, title)


def prepare_chapter_body_from_reply(
    reply: str, chapter_num: int
) -> tuple[str | None, str]:
    return chapter_text.prepare_chapter_body_from_reply(
        reply, chapter_num, apply_chapter_title
    )


def format_chapter_file(
    chapter_num: int, body: str, *, title: str | None = None
) -> str:
    return chapter_text.format_chapter_file(chapter_num, body, title=title)


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
    return sum(
        1
        for i, msg in enumerate(state.conversation_history)
        if msg["role"] == "assistant"
        and i not in state.appended_indices
        and should_append_to_chapter(msg["content"])
    )


def flush_chapter_writes(*, silent: bool = False) -> int:
    """将尚未写入章节的 AI 正文批量追加到最新章节。"""
    chapter_num, chapter_path = get_or_create_write_chapter()
    total_chars = 0
    count = 0

    for i, msg in enumerate(state.conversation_history):
        if msg["role"] != "assistant" or i in state.appended_indices:
            continue
        if not should_append_to_chapter(msg["content"]):
            continue
        chars = append_to_chapter(msg["content"], chapter_path, msg_index=i)
        if chars[0]:
            state.appended_indices.add(i)
            total_chars += chars[0]
            count += 1

    if count and not silent:
        print(
            f"💾 已保存 {count} 条正文到 data/chapters/ch{chapter_num:03d}.md"
            f"（共 +{total_chars} 字）"
        )
    return count


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
