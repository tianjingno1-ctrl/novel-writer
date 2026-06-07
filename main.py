#!/usr/bin/env python3
"""长篇小说辅助写作工具 — 主程序。"""

from __future__ import annotations

import atexit
import html
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
import file_utils
import novel_data
from app_state import state
from providers import APIError, TokenUsage, get_client, reset_client
from summarizer import (
    CHARACTER_DRIFT_SYSTEM,
    CHECK_SYSTEM,
    DETAIL_EXTRACT_SYSTEM,
    OBSERVE_SYSTEM,
    OUTLINE_SYSTEM,
    PACING_CHECK_SYSTEM,
    POST_CHAPTER_MAINTAIN_SYSTEM,
    QUALITY_CHECK_BUNDLE_SYSTEM,
    REPETITION_CHECK_SYSTEM,
    SUMMARY_SYSTEM,
    WRITING_INSTRUCTION,
    build_character_drift_user_message,
    build_check_user_message,
    build_detail_extract_user_message,
    build_observe_user_message,
    build_outline_user_message,
    build_pacing_check_user_message,
    build_post_chapter_maintain_user_message,
    build_quality_bundle_user_message,
    build_summary_user_message,
    count_report_issues,
    extract_plot_active_unresolved,
    parse_observe_proposals,
    parse_post_chapter_maintain,
    parse_quality_bundle,
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
            "title": "重复词检查",
            "content": (
                "[讨论] 请检查当前章节正文中出现频率过高的词语或句式，列出 TOP5，"
                "并给出替换建议。对照 style.md「本书已出现过多」清单，"
                "建议新增禁用的条目。"
            ),
        },
    ],
}

INITIAL_FILES = {
    WORLD_FILE: (
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
    STYLE_FILE: (
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
    CHARACTERS_FILE: "# 人物初始设定\n\n（在此填写主要人物的初始设定，只追加不修改）\n",
    CHAR_CURRENT_FILE: (
        "# 人物状态（已拆分）\n\n"
        "> 请改用：`char_static.md`（性格锚点，缓存②）+ `char_dynamic.md`（当前状态，每章更新）。\n"
        "> 本文件仅作兼容占位，续写不再读取。\n"
    ),
    CHAR_STATIC_FILE: (
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
    CHAR_DYNAMIC_FILE: (
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
    SUMMARIES_FILE: "# 章节概述（兼容视图）\n\n> 自动生成概述写入 `summaries_recent.md`；归档见 `summaries_archive.md`。\n",
    SUMMARIES_ARCHIVE_FILE: "# 章节概述归档（缓存层）\n\n",
    SUMMARIES_RECENT_FILE: (
        "# 近期概述（最近 3–5 章）\n\n"
        "> 每章「生成概述」追加在此；旧条可剪切到 `summaries_archive.md`。\n"
    ),
    PLOT_THREADS_FILE: (
        "# 伏笔线索（已拆分）\n\n"
        "> 请改用：`plot_threads_locked.md`（细节钉子，缓存③）+ `plot_threads_active.md`（伏笔，每章更新）。\n"
    ),
    PLOT_THREADS_LOCKED_FILE: (
        "# 已钉死的细节（不能改）\n\n"
        "> 每出现新的具体数字、日期、专名、外貌细节，立刻追加一行。\n\n"
        "- 女主年龄：\n"
        "- 男主身高/标志特征：\n"
    ),
    PLOT_THREADS_ACTIVE_FILE: (
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


def _dbg_stream_log(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    # #region agent log
    try:
        log_path = Path(__file__).resolve().parent / "debug-4132c7.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "4132c7",
                        "location": location,
                        "message": message,
                        "data": data,
                        "hypothesisId": hypothesis_id,
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion
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


def init_data_dirs() -> None:
    """首次运行：创建目录与空文件。"""
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    novel_data.CODEX_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in INITIAL_FILES.items():
        if not path.exists():
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


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


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
        return entry_id is not None
    if append:
        existing = read_text(path)
        if not content:
            return False
        backup_file(path)
        file_utils.atomic_write_text(path, f"{existing}{content}")
        return True
    if read_text(path) == content:
        return False
    backup_file(path)
    file_utils.atomic_write_text(path, content)
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
        record = {
            "ts": ts,
            "tag": tag,
            "provider": pid,
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


def cache_block(text: str) -> dict:
    return {
        "type": "text",
        "text": text,
        "cache_control": {"type": "ephemeral", "ttl": config.CACHE_TTL},
    }


def _read_char_static() -> str:
    text = read_text(CHAR_STATIC_FILE).strip()
    if text:
        return text
    return read_text(CHAR_CURRENT_FILE).strip()


def _read_plot_locked() -> str:
    text = read_text(PLOT_THREADS_LOCKED_FILE).strip()
    if text:
        return text
    legacy = read_text(PLOT_THREADS_FILE).strip()
    if "## 已钉死的细节" in legacy:
        start = legacy.find("## 已钉死的细节")
        end = legacy.find("## 未回收")
        if end < 0:
            end = len(legacy)
        return legacy[start:end].strip()
    return ""


def _read_plot_active() -> str:
    text = read_text(PLOT_THREADS_ACTIVE_FILE).strip()
    if text:
        return text
    legacy = read_text(PLOT_THREADS_FILE).strip()
    if "## 未回收" in legacy:
        start = legacy.find("## 未回收")
        return legacy[start:].strip()
    return ""


def get_characters_block() -> str:
    """Codex 勾选条目优先；否则回退 characters.md；附带 char_static（缓存②，极少变动）。"""
    if config.CONTEXT_MODE == "codex" or novel_data.get_active_codex_ids():
        codex_text = novel_data.format_active_codex_text()
        if codex_text:
            base = f"# 本章相关设定（Codex）\n\n{codex_text}"
        else:
            base = read_text(CHARACTERS_FILE)
    else:
        base = read_text(CHARACTERS_FILE)
    char_static = _read_char_static()
    if char_static:
        base = (
            f"{base.rstrip()}\n\n---\n\n"
            f"# 人物锚点（char_static.md）\n{char_static}"
        )
    return base


def get_stable_archive_block() -> str:
    """概述归档 + 细节钉子锁定区（缓存③，只增不改）。"""
    parts: list[str] = []
    archive = read_text(SUMMARIES_ARCHIVE_FILE).strip()
    if archive:
        parts.append(f"# 章节概述归档（summaries_archive.md）\n{archive}")
    locked = _read_plot_locked()
    if locked:
        parts.append(f"# 已钉死的细节（plot_threads_locked.md）\n{locked}")
    return "\n\n".join(parts)


def _collect_dynamic_layer_parts() -> list[dict]:
    """④ 层动态块拆分，供调试面板展示。"""
    parts: list[dict] = []
    dynamic = read_text(CHAR_DYNAMIC_FILE).strip()
    if not dynamic:
        dynamic = read_text(CHAR_CURRENT_FILE).strip()
    if dynamic:
        parts.append(
            {
                "id": "char_dynamic",
                "label": "char_dynamic",
                "content": f"# 人物动态状态（char_dynamic.md）\n{dynamic}",
            }
        )
    recent = read_text(SUMMARIES_RECENT_FILE).strip()
    if recent:
        parts.append(
            {
                "id": "summaries_recent",
                "label": "summaries_recent",
                "content": f"# 近期章节概述（summaries_recent.md）\n{recent}",
            }
        )
    active = _read_plot_active()
    if active:
        parts.append(
            {
                "id": "plot_threads_active",
                "label": "plot_threads_active",
                "content": f"# 活跃伏笔线索（plot_threads_active.md）\n{active}",
            }
        )
    if config.CONTEXT_MODE == "beats":
        scene = novel_data.get_active_scene()
        if scene and scene.get("summary"):
            parts.append(
                {
                    "id": "scene_summary",
                    "label": "场景概述",
                    "content": f"# 当前场景概述\n{scene['summary']}",
                }
            )
    return parts


def get_dynamic_context_block() -> str:
    """人物动态 + 近期概述 + 活跃伏笔（缓存④，每章变动）。"""
    return "\n\n".join(p["content"] for p in _collect_dynamic_layer_parts())


def get_char_context_for_check() -> str:
    """检查 API：静态锚点 + 动态状态。"""
    static = _read_char_static()
    dynamic = read_text(CHAR_DYNAMIC_FILE).strip()
    parts = []
    if static:
        parts.append(f"## 性格锚点（char_static）\n{static}")
    if dynamic:
        parts.append(f"## 当前状态（char_dynamic）\n{dynamic}")
    if not parts:
        legacy = read_text(CHAR_CURRENT_FILE).strip()
        if legacy:
            parts.append(legacy)
    return "\n\n".join(parts)


def get_summaries_combined() -> str:
    """检查/大纲：归档 + 近期（兼容旧 summaries.md）。"""
    parts: list[str] = []
    archive = read_text(SUMMARIES_ARCHIVE_FILE).strip()
    recent = read_text(SUMMARIES_RECENT_FILE).strip()
    if archive:
        parts.append(archive)
    if recent:
        parts.append(recent)
    if parts:
        return "\n\n".join(parts)
    return read_text(SUMMARIES_FILE).strip()


def get_world_block() -> str:
    """世界观 + 文风锚点（地基层，极少改动，与 world 同缓存块）。"""
    world = read_text(WORLD_FILE)
    style = read_text(STYLE_FILE).strip()
    if style:
        return f"{world.rstrip()}\n\n---\n\n# 文风锚点（style.md）\n{style}"
    return world


def build_cached_system(
    instruction: str,
    provider: str | None = None,
    *,
    include_scene_context: bool = True,
) -> list[dict] | str:
    """四层缓存策略：① world ② 人物锚点 ③ 归档钉子 ④ 动态任务层；无缓存时合并为纯文本。"""
    world = get_world_block()
    characters = get_characters_block()
    stable = get_stable_archive_block()
    scene_ctx = ""
    if include_scene_context and config.CONTEXT_MODE in ("beats", "summaries"):
        scene_ctx = novel_data.get_scene_context_text()
    dynamic_parts = _collect_dynamic_layer_parts()
    dynamic_ctx = "\n\n".join(p["content"] for p in dynamic_parts)
    dynamic_prefix_parts: list[str] = []
    if scene_ctx:
        dynamic_prefix_parts.append(f"# 当前场景\n{scene_ctx}")
    if dynamic_ctx:
        dynamic_prefix_parts.append(dynamic_ctx)
    dynamic = ("\n\n" + "\n\n".join(dynamic_prefix_parts)) if dynamic_prefix_parts else ""
    full_instruction = instruction + dynamic

    cache_supported = config.supports_prompt_cache(provider)
    layer4_children: list[dict] = [
        {
            "id": "writing_instruction",
            "label": "WRITING_INSTRUCTION",
            "content": instruction,
            "token_estimate": _estimate_tokens(instruction),
        }
    ]
    if scene_ctx:
        scene_block = f"# 当前场景\n{scene_ctx}"
        layer4_children.append(
            {
                "id": "scene_beat",
                "label": "Beat + 情绪锚点",
                "content": scene_block,
                "token_estimate": _estimate_tokens(scene_block),
            }
        )
    for part in dynamic_parts:
        layer4_children.append(
            {
                "id": part["id"],
                "label": part["label"],
                "content": part["content"],
                "token_estimate": _estimate_tokens(part["content"]),
            }
        )

    debug_layers: list[dict] = [
        {
            "id": "layer1",
            "label": "① world + style",
            "cached": cache_supported,
            "content": world,
        },
        {
            "id": "layer2",
            "label": "② char_static + 人物",
            "cached": cache_supported,
            "content": characters,
        },
    ]
    if stable.strip():
        debug_layers.append(
            {
                "id": "layer3",
                "label": "③ summaries_archive + plot_threads_locked",
                "cached": cache_supported,
                "content": stable,
            }
        )
    debug_layers.append(
        {
            "id": "layer4",
            "label": "④ 动态层",
            "cached": False,
            "content": full_instruction,
            "children": layer4_children,
        }
    )
    _record_context_debug(debug_layers, provider=provider)

    if cache_supported:
        blocks: list[dict] = [
            cache_block(world),
            cache_block(characters),
        ]
        if stable.strip():
            blocks.append(cache_block(stable))
        blocks.append({"type": "text", "text": full_instruction})
        return blocks

    stable_section = f"# 归档与细节钉子\n{stable}\n\n" if stable.strip() else ""
    return (
        f"# 世界观与文风\n{world}\n\n"
        f"# 人物设定\n{characters}\n\n"
        f"{stable_section}"
        f"# 当前任务\n{full_instruction}"
    )


def _record_context_debug(
    layers: list[dict],
    *,
    provider: str | None = None,
    messages: list[dict] | None = None,
    tag: str = "",
) -> None:
    pid = config.resolve_provider(provider)
    cache_supported = config.supports_prompt_cache(provider)
    debug_layers: list[dict] = []
    for layer in layers:
        content = str(layer.get("content", ""))
        entry: dict = {
            "id": layer["id"],
            "label": layer["label"],
            "cached": bool(layer.get("cached")) and cache_supported,
            "token_estimate": _estimate_tokens(content),
            "chars": len(content),
            "content": content,
        }
        children = layer.get("children")
        if children:
            entry["children"] = [
                {
                    **child,
                    "token_estimate": child.get(
                        "token_estimate", _estimate_tokens(str(child.get("content", "")))
                    ),
                    "chars": len(str(child.get("content", ""))),
                }
                for child in children
            ]
        debug_layers.append(entry)

    msg_rows = _summarize_messages(messages) if messages else []
    prev = state.last_context_debug or {}
    if not msg_rows and prev.get("messages"):
        msg_rows = prev["messages"]
    state.last_context_debug = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "tag": tag or prev.get("tag", ""),
        "provider": pid,
        "model": config.get_model(pid),
        "context_mode": config.CONTEXT_MODE,
        "writing_cache_supported": cache_supported,
        "layers": debug_layers,
        "messages": msg_rows,
        "messages_token_estimate": sum(r.get("est_tokens", 0) for r in msg_rows),
    }


def get_last_context_debug() -> dict:
    if not state.last_context_debug:
        return {"ok": False, "error": "尚无请求记录，请先发送一次写书对话、自由聊或检查类请求"}
    data = dict(state.last_context_debug)
    data["ok"] = True
    data["last_call"] = get_last_call_info()
    return data


def _estimate_tokens(text: str) -> int:
    """粗估 token 数（中文为主时约 1.6 字/token）。"""
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    n = len(text)
    if cjk > n * 0.35:
        return max(1, int(n / 1.6))
    return max(1, int(n / 4))


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


def _invalidate_chapter_injection(chapter_num: int | None = None) -> None:
    """章节文件变更或需重新注入时，清除「已含章节正文」标记。"""
    if chapter_num is None or chapter_num <= 0:
        state.session_includes_chapter = False
        return
    if state.last_injected_chapter_num == chapter_num:
        state.session_includes_chapter = False


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
    try:
        log_request_context(system, messages, tag=tag, provider=pid)
        t_before_lock = time.time()
        with _request_lock:
            lock_wait_ms = int((time.time() - t_before_lock) * 1000)
            t_api = time.time()
            text, usage = get_client().create_message(
                system,
                messages,
                max_tokens=eff_max_tokens,
                provider=pid,
            )
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
        if not silent:
            print(f"API 错误：{err}")
        return None
    except Exception as e:
        err = _api_error_message(e)
        state.last_call_info = {"ok": False, "error": err}
        if not silent:
            print(f"API 错误：{err}")
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
    """将 AI 回复或粘贴内容中的 HTML 实体还原为可读字符（如 &quot; → \"）。"""
    if not text:
        return text
    return html.unescape(text)


def instruction_save_mode(instruction: str) -> str:
    """章节保存策略：仅显式「续写」类指令追加，否则覆盖本章（避免越写越长）。"""
    text = (instruction or "").strip()
    if any(k in text for k in _APPEND_INSTRUCTION_KEYWORDS):
        return "append"
    return "replace"


def should_append_to_chapter(reply: str) -> bool:
    stripped = reply.strip()
    if not stripped or len(stripped) < 30:
        return False
    if any(stripped.startswith(p) for p in DISCUSSION_PREFIXES):
        return False
    if any(stripped.startswith(p) for p in META_LINE_PREFIXES):
        return False
    if stripped.startswith("✅"):
        return False
    first_line = stripped.split("\n", 1)[0].strip()
    if first_line.endswith("：") and len(first_line) < 24:
        return False
    return True


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
    if chapter_num > 0 and title:
        refresh_chapter_file_header(chapter_num, title)
    content = body.strip()
    if not content:
        return 0, title
    existing = read_text(chapter_path)
    separator = "\n\n" if existing.strip() else ""
    state.last_append_undo = {
        "path": str(chapter_path),
        "content": existing,
        "msg_index": msg_index,
    }
    write_text(chapter_path, f"{separator}{content}\n", append=True)
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
    if state.last_append_undo is None:
        return {"ok": False, "error": "没有可撤销的章节写入"}
    undo = state.last_append_undo
    path = Path(undo["path"])
    write_text(path, undo["content"], append=False, history_source="undo")
    msg_index = undo.get("msg_index")
    if msg_index is not None:
        state.appended_indices.discard(msg_index)
    state.last_append_undo = None
    m = re.search(r"ch(\d+)\.md", path.name)
    if m:
        _invalidate_chapter_injection(int(m.group(1)))
    return {"ok": True, "file": path.name}


def extract_chapter_body_from_user_message(content: str) -> str | None:
    """从首轮用户消息中取出附带的章节正文（不含写作指令）。"""
    m = _USER_CHAPTER_BLOCK_RE.match((content or "").strip())
    if not m:
        return None
    body = m.group(2).strip()
    return body or None


_CHAPTER_MD_HEADER_RE = re.compile(
    r"^#\s*第(?:\d+|[一二三四五六七八九十百零]+)章"
    r"(?:\s*[·•\-—]\s*|\s+)(.+?)\s*$"
)


def parse_chapter_header_line(line: str) -> str | None:
    m = _CHAPTER_MD_HEADER_RE.match((line or "").strip())
    if not m:
        return None
    title = m.group(1).strip().strip("《》「」\"' ")
    return title or None


def split_chapter_markdown_header(text: str) -> tuple[str | None, str]:
    """从正文首行 # 第X章 · 标题 拆出标题与纯正文。"""
    stripped = (text or "").strip()
    if not stripped:
        return None, ""
    lines = stripped.splitlines()
    if not lines[0].startswith("#"):
        return None, stripped
    title = parse_chapter_header_line(lines[0])
    i = 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    body = "\n".join(lines[i:]).strip()
    return title, body


def extract_chapter_title_from_reply(text: str) -> tuple[str | None, str]:
    """解析【章节标题】或 # 第X章 标题行，返回 (标题, 纯正文)。"""
    stripped = (text or "").strip()
    if not stripped:
        return None, ""
    m = re.match(r"^【章节标题】\s*(.+?)(?:\n\n|\n|$)", stripped, re.DOTALL)
    if m:
        title = m.group(1).strip().split("\n", 1)[0].strip()
        title = title.strip("《》「」\"' ")
        body = stripped[m.end() :].strip()
        return (title or None), body
    title, body = split_chapter_markdown_header(stripped)
    if title:
        return title, body
    return None, stripped


def apply_chapter_title(chapter_num: int, title: str | None) -> str | None:
    """将标题同步到 plan.json（并确保章节规划存在）。"""
    if not title:
        return None
    clean = title.strip().strip("《》「」\"' ")
    if not clean or clean in {f"第{chapter_num}章", f"第{_chapter_cn(chapter_num)}章"}:
        return None
    if len(clean) > 48:
        clean = clean[:48].rstrip()
    novel_data.ensure_chapter_plan(chapter_num, title=clean)
    novel_data.update_chapter_title(chapter_num, clean)
    return clean


def strip_chapter_file_header(text: str) -> str:
    _, body = split_chapter_markdown_header(text or "")
    return body


def sync_chapter_title_from_file(chapter_num: int) -> str | None:
    """从章节 md 首行同步标题到 plan.json。"""
    text = read_chapter_content(chapter_num)
    if not text.strip():
        return None
    title, _ = split_chapter_markdown_header(text)
    if not title:
        title, _ = extract_chapter_title_from_reply(text)
    return apply_chapter_title(chapter_num, title)


def sync_all_chapter_titles_from_files() -> None:
    for num, _ in list_chapters():
        sync_chapter_title_from_file(num)


def refresh_chapter_file_header(chapter_num: int, title: str) -> None:
    """更新章节 md 第一行标题，保留正文不变。"""
    path = get_chapter_path(chapter_num)
    if not path.exists():
        return
    body = strip_chapter_file_header(read_text(path))
    write_text(path, format_chapter_file(chapter_num, body, title=title), append=False)


def prepare_chapter_body_from_reply(
    reply: str, chapter_num: int
) -> tuple[str | None, str]:
    reply = sanitize_chapter_text(reply)
    title, body = extract_chapter_title_from_reply(reply)
    applied = apply_chapter_title(chapter_num, title)
    if not applied:
        md_title, body = split_chapter_markdown_header(body)
        applied = apply_chapter_title(chapter_num, md_title)
    return applied, body


def format_chapter_file(
    chapter_num: int, body: str, *, title: str | None = None
) -> str:
    body = body.strip()
    if not body:
        return ""
    parsed_title, body = extract_chapter_title_from_reply(body)
    md_title, body = split_chapter_markdown_header(body)
    use_title = (title or parsed_title or md_title or "").strip()
    header = f"# 第{chapter_num}章"
    if use_title and use_title not in {
        f"第{chapter_num}章",
        f"第{_chapter_cn(chapter_num)}章",
    }:
        header = f"{header} · {use_title}"
    return f"{header}\n\n{body}\n"


def _clear_assistant_appended_indices() -> None:
    for i, msg in enumerate(state.conversation_history):
        if msg["role"] == "assistant":
            state.appended_indices.discard(i)


def apply_assistant_turn_to_chapter(chapter_num: int, msg_index: int) -> dict:
    """用某条 AI 回复**替换**整章正文（非追加）。"""
    path = CHAPTERS_DIR / f"ch{chapter_num:03d}.md"
    if not path.exists():
        return {"ok": False, "error": f"章节 ch{chapter_num:03d} 不存在"}

    if msg_index < 0 or msg_index >= len(state.conversation_history):
        return {"ok": False, "error": "无效的消息序号"}
    msg = state.conversation_history[msg_index]
    if msg["role"] != "assistant":
        return {"ok": False, "error": "只能选用 AI 回复替换章节"}
    content = msg["content"].strip()
    if not should_append_to_chapter(content):
        return {"ok": False, "error": "该条为讨论/说明，不能作为章节正文"}

    title, body = prepare_chapter_body_from_reply(content, chapter_num)
    if not body.strip():
        return {"ok": False, "error": "该条没有可用正文"}
    chapter_text = format_chapter_file(chapter_num, body, title=title)
    write_text(path, chapter_text, append=False)
    state.last_append_undo = None
    _clear_assistant_appended_indices()
    state.appended_indices.add(msg_index)
    _invalidate_chapter_injection(chapter_num)
    save_session("apply_turn", silent=True)
    return {
        "ok": True,
        "num": chapter_num,
        "msg_index": msg_index,
        "chars": len(chapter_text),
        "chapter_title": title,
        "source": "assistant",
    }


def apply_user_draft_turn_to_chapter(chapter_num: int, msg_index: int) -> dict:
    """用首轮用户消息里附带的章节草稿替换整章正文。"""
    path = CHAPTERS_DIR / f"ch{chapter_num:03d}.md"
    if not path.exists():
        return {"ok": False, "error": f"章节 ch{chapter_num:03d} 不存在"}

    if msg_index < 0 or msg_index >= len(state.conversation_history):
        return {"ok": False, "error": "无效的消息序号"}
    msg = state.conversation_history[msg_index]
    if msg["role"] != "user":
        return {"ok": False, "error": "只能选用用户消息中的章节草稿"}
    body = extract_chapter_body_from_user_message(msg["content"])
    if not body:
        return {"ok": False, "error": "该轮指令里没有附带章节正文（仅首轮带全文时可用）"}

    chapter_text = format_chapter_file(chapter_num, body)
    write_text(path, chapter_text, append=False)
    state.last_append_undo = None
    _clear_assistant_appended_indices()
    _invalidate_chapter_injection(chapter_num)
    save_session("apply_turn", silent=True)
    return {
        "ok": True,
        "num": chapter_num,
        "msg_index": msg_index,
        "chars": len(chapter_text),
        "source": "user_draft",
    }


def do_undo() -> None:
    result = undo_last_chapter_append()
    if result.get("ok"):
        print(f"↩️  已撤销上次章节写入（{result['file']}）")
    else:
        print(result.get("error", "撤销失败"))


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
    if not should_append_to_chapter(reply):
        if not config.AUTO_APPEND_CHAPTER:
            return None
        print("💡 本条为讨论/说明，未写入章节（如需保存请手动编辑章节文件）")
        return None

    if not config.AUTO_APPEND_CHAPTER:
        pending = count_unsaved_chapter_turns()
        print(f"💡 本条正文尚未写入章节，输入 /save 保存（待保存 {pending} 条）")
        return None

    chapter_num, chapter_path = get_or_create_write_chapter(write_chapter_num)
    mode = instruction_save_mode(instruction)
    if mode == "append":
        chars, title = append_to_chapter(
            reply, chapter_path, msg_index=msg_index, chapter_num=chapter_num
        )
        state.appended_indices.add(msg_index)
        title_note = f" · 《{title}》" if title else ""
        print(
            f"💾 已追加到 data/chapters/ch{chapter_num:03d}.md{title_note}（+{chars} 字）"
        )
        if not title:
            title = sync_chapter_title_from_file(chapter_num)
        _invalidate_chapter_injection(chapter_num)
        return {"mode": "append", "title": title, "chapter_num": chapter_num}

    chars, title = replace_chapter_content(
        reply, chapter_path, chapter_num, msg_index=msg_index
    )
    _clear_assistant_appended_indices()
    state.appended_indices.add(msg_index)
    title_note = f" · 《{title}》" if title else ""
    print(
        f"💾 已覆盖保存到 data/chapters/ch{chapter_num:03d}.md{title_note}（{chars} 字）"
    )
    if not title:
        title = sync_chapter_title_from_file(chapter_num)
    _invalidate_chapter_injection(chapter_num)
    return {"mode": "replace", "title": title, "chapter_num": chapter_num}


def count_summaries() -> int:
    combined = get_summaries_combined()
    return len(re.findall(r"【第\d+章", combined))


def touch_user_active() -> None:
    state.last_user_active = time.time()


def _session_chapter_num() -> int:
    if state.write_chapter_num > 0:
        return state.write_chapter_num
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

    file_utils.atomic_write_text(
        SESSION_FILE,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    file_utils.atomic_write_text(
        SESSION_MD_FILE,
        format_session_markdown(saved_at, reason),
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

    print()
    print("⚠️  检测到上次未恢复的会话（可能异常关闭）")
    print(f"   保存时间：{saved_at}（{reason}）")
    print(f"   章节：第{chapter}章，共 {turns} 条消息")
    print(f"   可读备份：{SESSION_MD_FILE}")
    print("   → 输入 /restore 恢复对话，或 /new 丢弃并开始新会话")


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
            content = sanitize_chapter_text(content)
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
    sync_appended_indices_with_chapter()
    pending = count_unsaved_chapter_turns()
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


def do_restore() -> None:
    result = restore_chat_session()
    if not result.get("ok"):
        print(result.get("error", "没有可恢复的会话备份"))
        return
    print(
        f"✅ 已恢复会话（{result.get('saved_at', '')}，"
        f"{result.get('message_count', 0)} 条消息）"
    )
    print(f"   详细内容见：{SESSION_MD_FILE}")
    pending = result.get("pending_writes", 0)
    if pending:
        print(f"💡 仍有 {pending} 条正文可能未写入章节，建议输入 /save 补存")


def do_save() -> None:
    chapter_count = flush_chapter_writes()
    session_saved = save_session("manual", silent=True)
    if chapter_count or session_saved:
        if session_saved:
            print(f"💾 会话已保存 → {SESSION_MD_FILE}")
        return
    print("当前没有需要保存的内容")


def remind_unsaved_on_exit() -> None:
    if not state.conversation_history:
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
    _heartbeat_stop.set()
    save_session("atexit", silent=True)
    if state.conversation_history:
        remind_unsaved_on_exit()


def setup_exit_handlers() -> None:
    atexit.register(_atexit_save)
    signal.signal(signal.SIGINT, _handle_exit_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_exit_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle_exit_signal)


def do_writing(instruction: str) -> None:
    latest = get_latest_chapter()
    if latest is None:
        print("提示：data/chapters/ 中尚无章节文件，将仅根据指令回复。")
        chapter_num, chapter_content = 0, "（尚无章节正文）"
    else:
        chapter_num, _, chapter_content = latest

    if chapter_num > 0:
        state.write_chapter_num = chapter_num
    if not state.session_includes_chapter:
        user_content = (
            f"【当前章节：第{chapter_num}章】\n\n"
            f"{chapter_content}\n\n"
            f"【写作指令】\n{instruction}"
        )
        state.session_includes_chapter = True
        state.last_injected_chapter_num = chapter_num
    else:
        user_content = instruction

    state.conversation_history.append({"role": "user", "content": user_content})

    system = build_cached_system(WRITING_INSTRUCTION)
    reply = call_api(system, prepare_messages_for_context(state.conversation_history))
    if reply is None:
        state.conversation_history.pop()
        return

    reply = sanitize_chapter_text(reply)
    print(f"\n{reply}\n")
    state.conversation_history.append({"role": "assistant", "content": reply})
    save_chapter_after_reply(
        reply,
        len(state.conversation_history) - 1,
        write_chapter_num=chapter_num if chapter_num > 0 else None,
        instruction=instruction,
    )
    save_session("auto", silent=True)


def writing_chat(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> dict:
    """Web/API：结构化写作对话，返回 JSON 友好结果。"""
    prep = _prepare_writing_turn(
        instruction, scene_beat, scene_id, chapter_num=chapter_num
    )
    if not prep.get("ok"):
        return prep

    reply = call_api(prep["system"], prep["messages"], silent=True)
    if reply is None:
        _rollback_failed_writing_turn(prep)
        info = get_last_call_info()
        return {"ok": False, "error": info.get("error", "API 调用失败")}

    return _finalize_writing_turn(
        reply,
        write_chapter_num=prep["write_chapter_num"],
        instruction=prep.get("full_instruction", prep.get("instruction", "")),
    )


def _prepare_writing_turn(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> dict:
    """追加用户消息并构建 API 请求上下文。"""
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

    write_num = resolve_write_chapter_num(chapter_num, scene_id)
    state.write_chapter_num = write_num
    injection_snapshot = {
        "session_includes_chapter": state.session_includes_chapter,
        "last_injected_chapter_num": state.last_injected_chapter_num,
    }
    if write_num != state.last_injected_chapter_num:
        state.session_includes_chapter = False

    chapter_content = read_chapter_content(write_num)
    if not chapter_content.strip():
        chapter_content = "（本章尚无正文）"

    injected_this_turn = False
    if not state.session_includes_chapter:
        user_content = (
            f"【当前章节：第{write_num}章】\n\n"
            f"{chapter_content}\n\n"
            f"【写作指令】\n{full_instruction}"
        )
        state.session_includes_chapter = True
        state.last_injected_chapter_num = write_num
        injected_this_turn = True
    else:
        user_content = full_instruction

    state.conversation_history.append({"role": "user", "content": user_content})
    return {
        "ok": True,
        "write_chapter_num": write_num,
        "instruction": instruction.strip(),
        "full_instruction": full_instruction,
        "injected_chapter_block": injected_this_turn,
        "injection_snapshot": injection_snapshot,
        "system": build_cached_system(
            WRITING_INSTRUCTION,
            include_scene_context=not beat_text,
        ),
        "messages": prepare_messages_for_context(state.conversation_history),
    }


def _rollback_failed_writing_turn(prep: dict) -> None:
    """API 失败时回滚本轮追加的用户消息与章节注入标记。"""
    if state.conversation_history and state.conversation_history[-1].get("role") == "user":
        state.conversation_history.pop()
    snap = prep.get("injection_snapshot") or {}
    if prep.get("injected_chapter_block"):
        state.session_includes_chapter = snap.get("session_includes_chapter", False)
        state.last_injected_chapter_num = int(snap.get("last_injected_chapter_num") or 0)


def _finalize_writing_turn(
    reply: str,
    *,
    write_chapter_num: int,
    instruction: str = "",
) -> dict:
    reply = sanitize_chapter_text(reply)
    state.conversation_history.append({"role": "assistant", "content": reply})
    msg_index = len(state.conversation_history) - 1
    save_info = save_chapter_after_reply(
        reply,
        msg_index,
        write_chapter_num=write_chapter_num,
        instruction=instruction,
    )
    save_session("auto", silent=True)

    chapter_saved = msg_index in state.appended_indices
    active_scene = novel_data.get_active_scene()
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": write_chapter_num,
        "chapter_saved": chapter_saved,
        "chapter_save_mode": save_info.get("mode") if save_info else None,
        "chapter_title": save_info.get("title") if save_info else None,
        "context_turns": config.CHAT_CONTEXT_TURNS,
        "context_mode": config.CONTEXT_MODE,
        "active_scene_id": active_scene.get("id") if active_scene else None,
        "history_len": len(state.conversation_history),
        **get_last_call_info(),
    }


def writing_chat_stream(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
):
    """流式写作对话，yield JSON 字符串事件。"""
    t_stream_start = time.time()
    # #region agent log
    _dbg_stream_log(
        "main.py:writing_chat_stream",
        "stream start",
        {"chapter_num": chapter_num, "scene_id": scene_id or ""},
        "H1",
    )
    # #endregion
    prep = _prepare_writing_turn(
        instruction, scene_beat, scene_id, chapter_num=chapter_num
    )
    prep_ms = int((time.time() - t_stream_start) * 1000)
    # #region agent log
    _dbg_stream_log(
        "main.py:writing_chat_stream",
        "prep done",
        {
            "ok": prep.get("ok"),
            "prep_ms": prep_ms,
            "msg_count": len(prep.get("messages") or []),
            "write_chapter_num": prep.get("write_chapter_num"),
        },
        "H4",
    )
    # #endregion
    if not prep.get("ok"):
        yield json.dumps({"type": "error", "message": prep["error"]}, ensure_ascii=False)
        return

    pid = config.resolve_provider(None)
    key_ok = config.is_api_key_configured(pid)
    # #region agent log
    _dbg_stream_log(
        "main.py:writing_chat_stream",
        "provider resolved",
        {"provider": pid, "key_configured": key_ok},
        "H3",
    )
    # #endregion
    if not key_ok:
        _rollback_failed_writing_turn(prep)
        cfg = config.get_provider_config(pid)
        err = f"请设置 {cfg['api_key_env']}，或在 .env / config.py 中填写 API Key"
        yield json.dumps({"type": "error", "message": err}, ensure_ascii=False)
        return

    chunks: list[str] = []
    try:
        log_request_context(
            prep["system"],
            prep["messages"],
            tag="写书对话",
            provider=pid,
        )
        t_before_lock = time.time()
        with _request_lock:
            lock_wait_ms = int((time.time() - t_before_lock) * 1000)
            # #region agent log
            _dbg_stream_log(
                "main.py:writing_chat_stream",
                "lock acquired",
                {"lock_wait_ms": lock_wait_ms, "provider": pid},
                "H2",
            )
            # #endregion
            usage: TokenUsage | None = None
            try:
                t_before_api = time.time()
                first_chunk_logged = False
                for chunk in get_client().iter_message(
                    prep["system"],
                    prep["messages"],
                    max_tokens=config.MAX_TOKENS,
                    provider=pid,
                ):
                    if not first_chunk_logged:
                        # #region agent log
                        _dbg_stream_log(
                            "main.py:writing_chat_stream",
                            "first chunk",
                            {
                                "api_ttft_ms": int((time.time() - t_before_api) * 1000),
                                "total_ms": int((time.time() - t_stream_start) * 1000),
                                "chunk_len": len(chunk),
                            },
                            "H1",
                        )
                        # #endregion
                        first_chunk_logged = True
                    chunks.append(chunk)
                    yield json.dumps(
                        {"type": "chunk", "text": chunk}, ensure_ascii=False
                    )
                usage = get_client().pop_stream_usage()
            except Exception as stream_exc:
                if chunks or not _is_stream_disconnect_error(stream_exc):
                    raise
                reset_client(pid)
                text, usage = get_client().create_message(
                    prep["system"],
                    prep["messages"],
                    max_tokens=config.MAX_TOKENS,
                    provider=pid,
                )
                chunks = [text] if text else []
                if text:
                    yield json.dumps(
                        {"type": "chunk", "text": text}, ensure_ascii=False
                    )
            if usage is not None:
                _record_call_usage(usage, pid)
    except APIError as e:
        # #region agent log
        _dbg_stream_log(
            "main.py:writing_chat_stream",
            "APIError",
            {
                "kind": e.kind,
                "message": str(e)[:200],
                "total_ms": int((time.time() - t_stream_start) * 1000),
                "had_chunks": bool(chunks),
            },
            "H3",
        )
        # #endregion
        _rollback_failed_writing_turn(prep)
        yield json.dumps(
            {"type": "error", "message": _api_error_message(e)},
            ensure_ascii=False,
        )
        return
    except Exception as e:
        # #region agent log
        _dbg_stream_log(
            "main.py:writing_chat_stream",
            "Exception",
            {
                "type": type(e).__name__,
                "message": str(e)[:200],
                "total_ms": int((time.time() - t_stream_start) * 1000),
            },
            "H5",
        )
        # #endregion
        _rollback_failed_writing_turn(prep)
        yield json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
        return

    reply = "".join(chunks)
    result = _finalize_writing_turn(
        reply,
        write_chapter_num=prep["write_chapter_num"],
        instruction=prep.get("full_instruction", prep.get("instruction", "")),
    )
    yield json.dumps(
        {
            "type": "done",
            "chapter_num": result["chapter_num"],
            "chapter_saved": result["chapter_saved"],
            "chapter_save_mode": result.get("chapter_save_mode"),
            "chapter_title": result.get("chapter_title"),
            "cost": state.last_call_info.get("cost", 0),
            "cost_no_cache": state.last_call_info.get("cost_no_cache"),
            "cost_saved": state.last_call_info.get("cost_saved"),
            "cache_savings_pct": state.last_call_info.get("cache_savings_pct"),
            "cache_write_at": state.last_call_info.get("cache_write_at"),
            "cache_ttl_remaining": state.last_call_info.get("cache_ttl_remaining"),
            "total_cost": state.total_cost,
            "usage": state.last_call_info.get("usage"),
            "model": state.last_call_info.get("model"),
            "provider": pid,
            "writing_cache_supported": config.supports_prompt_cache(pid),
        },
        ensure_ascii=False,
    )


def get_chat_history() -> list[dict]:
    return list(state.conversation_history)


def load_chat_prompts() -> dict:
    if not CHAT_PROMPTS_FILE.exists():
        return dict(DEFAULT_CHAT_PROMPTS)
    try:
        data = json.loads(CHAT_PROMPTS_FILE.read_text(encoding="utf-8"))
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
    write_text(
        CHAT_PROMPTS_FILE,
        json.dumps(payload, ensure_ascii=False, indent=2),
        append=False,
    )
    return {"ok": True, **payload}


def get_appended_indices() -> list[int]:
    return sorted(state.appended_indices)


def _trim_free_history() -> list[dict]:
    turns = config.FREE_CHAT_CONTEXT_TURNS
    stored = len(state.free_chat_history)
    if turns <= 0 or stored <= turns * 2:
        trimmed = list(state.free_chat_history)
    else:
        trimmed = state.free_chat_history[-(turns * 2) :]
    return trimmed


def _resolve_free_provider(provider: str | None = None) -> str:
    pid = provider or state.free_chat_provider
    if pid not in config.PROVIDERS:
        return config.FREE_CHAT_PROVIDER
    return pid


def _free_chat_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_free_thread_id() -> str:
    return uuid.uuid4().hex[:12]


def _default_free_thread_title() -> str:
    n = len(state.free_chat_threads) + 1
    return f"新话题 {n}"


def _thread_title_from_message(text: str) -> str:
    one_line = re.sub(r"\s+", " ", text.strip())
    if not one_line:
        return _default_free_thread_title()
    return one_line[:36] + ("…" if len(one_line) > 36 else "")


def _new_free_thread(*, title: str | None = None, messages: list[dict] | None = None) -> dict:
    now = _free_chat_now()
    return {
        "id": _new_free_thread_id(),
        "title": (title or _default_free_thread_title()).strip() or _default_free_thread_title(),
        "created_at": now,
        "updated_at": now,
        "messages": list(messages or []),
    }


def _find_free_thread(thread_id: str) -> dict | None:
    for thread in state.free_chat_threads:
        if thread.get("id") == thread_id:
            return thread
    return None


def _active_free_thread() -> dict | None:
    if not state.free_chat_threads:
        return None
    thread = _find_free_thread(state.free_chat_active_thread_id)
    if thread is not None:
        return thread
    return state.free_chat_threads[0]


def _sync_free_history_from_active() -> None:
    thread = _active_free_thread()
    if thread is None:
        state.free_chat_history = []
        state.free_chat_active_thread_id = ""
        return
    state.free_chat_active_thread_id = thread["id"]
    state.free_chat_history = list(thread.get("messages", []))


def _persist_active_thread_messages() -> None:
    thread = _active_free_thread()
    if thread is None:
        return
    thread["messages"] = list(state.free_chat_history)
    thread["updated_at"] = _free_chat_now()


def _ensure_free_chat_threads() -> dict:
    if not state.free_chat_threads:
        thread = _new_free_thread(title="默认话题")
        state.free_chat_threads = [thread]
        state.free_chat_active_thread_id = thread["id"]
        state.free_chat_history = []
    _sync_free_history_from_active()
    return _active_free_thread() or state.free_chat_threads[0]


def _free_thread_summary(thread: dict) -> dict:
    messages = thread.get("messages") or []
    preview = ""
    for msg in reversed(messages):
        if (msg.get("content") or "").strip():
            preview = (msg.get("content") or "").strip().replace("\n", " ")[:80]
            break
    return {
        "id": thread.get("id", ""),
        "title": thread.get("title") or "未命名话题",
        "created_at": thread.get("created_at", ""),
        "updated_at": thread.get("updated_at", ""),
        "message_count": len(messages),
        "preview": preview,
    }


def save_free_chat() -> None:
    FREE_CHAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _persist_active_thread_messages()
    payload = {
        "saved_at": _free_chat_now(),
        "provider": state.free_chat_provider,
        "active_thread_id": state.free_chat_active_thread_id,
        "threads": state.free_chat_threads,
    }
    FREE_CHAT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_free_chat() -> None:
    state.free_chat_threads = []
    state.free_chat_active_thread_id = ""
    state.free_chat_history = []
    if not FREE_CHAT_FILE.exists():
        _ensure_free_chat_threads()
        return
    try:
        data = json.loads(FREE_CHAT_FILE.read_text(encoding="utf-8"))
        saved_provider = data.get("provider")
        if saved_provider in config.PROVIDERS:
            state.free_chat_provider = saved_provider

        raw_threads = data.get("threads")
        if isinstance(raw_threads, list) and raw_threads:
            state.free_chat_threads = [
                {
                    "id": str(t.get("id") or _new_free_thread_id()),
                    "title": (t.get("title") or "未命名话题").strip() or "未命名话题",
                    "created_at": t.get("created_at") or _free_chat_now(),
                    "updated_at": t.get("updated_at") or _free_chat_now(),
                    "messages": list(t.get("messages") or []),
                }
                for t in raw_threads
                if isinstance(t, dict)
            ]
            active_id = data.get("active_thread_id")
            if active_id and _find_free_thread(str(active_id)):
                state.free_chat_active_thread_id = str(active_id)
            else:
                state.free_chat_active_thread_id = state.free_chat_threads[0]["id"]
            _sync_free_history_from_active()
            return

        legacy_messages = list(data.get("messages") or [])
        title = "默认话题"
        for msg in legacy_messages:
            if msg.get("role") == "user" and (msg.get("content") or "").strip():
                title = _thread_title_from_message(msg["content"])
                break
        thread = _new_free_thread(title=title, messages=legacy_messages)
        state.free_chat_threads = [thread]
        state.free_chat_active_thread_id = thread["id"]
        _sync_free_history_from_active()
        save_free_chat()
    except (json.JSONDecodeError, OSError):
        state.free_chat_threads = []
        _ensure_free_chat_threads()


def get_free_chat_provider() -> str:
    return state.free_chat_provider


def set_free_chat_provider(provider: str) -> dict:
    if provider not in config.PROVIDERS:
        return {"ok": False, "error": f"未知提供商: {provider}"}
    state.free_chat_provider = provider
    save_free_chat()
    return {"ok": True, "provider": provider}


def get_free_chat_threads() -> list[dict]:
    _ensure_free_chat_threads()
    active_id = state.free_chat_active_thread_id
    threads = [_free_thread_summary(t) for t in state.free_chat_threads]
    threads.sort(key=lambda t: t.get("updated_at") or "", reverse=True)
    for item in threads:
        item["active"] = item.get("id") == active_id
    return threads


def get_free_chat_history() -> list[dict]:
    _ensure_free_chat_threads()
    return list(state.free_chat_history)


def get_free_chat_state() -> dict:
    _ensure_free_chat_threads()
    active = _active_free_thread()
    return {
        "messages": list(state.free_chat_history),
        "provider": state.free_chat_provider,
        "active_thread_id": state.free_chat_active_thread_id,
        "active_thread_title": (active or {}).get("title", ""),
        "threads": get_free_chat_threads(),
    }


def create_free_chat_thread(title: str | None = None) -> dict:
    _ensure_free_chat_threads()
    thread = _new_free_thread(title=title)
    state.free_chat_threads.append(thread)
    state.free_chat_active_thread_id = thread["id"]
    state.free_chat_history = []
    save_free_chat()
    return {"ok": True, "thread": _free_thread_summary(thread)}


def switch_free_chat_thread(thread_id: str) -> dict:
    _ensure_free_chat_threads()
    thread = _find_free_thread(thread_id)
    if thread is None:
        return {"ok": False, "error": "话题不存在"}
    _persist_active_thread_messages()
    state.free_chat_active_thread_id = thread_id
    _sync_free_history_from_active()
    save_free_chat()
    return {"ok": True, **get_free_chat_state()}


def rename_free_chat_thread(thread_id: str, title: str) -> dict:
    _ensure_free_chat_threads()
    thread = _find_free_thread(thread_id)
    if thread is None:
        return {"ok": False, "error": "话题不存在"}
    clean = title.strip()
    if not clean:
        return {"ok": False, "error": "话题名称不能为空"}
    thread["title"] = clean[:80]
    thread["updated_at"] = _free_chat_now()
    save_free_chat()
    return {"ok": True, "thread": _free_thread_summary(thread)}


def delete_free_chat_thread(thread_id: str) -> dict:
    _ensure_free_chat_threads()
    if len(state.free_chat_threads) <= 1:
        return {"ok": False, "error": "至少保留一个话题"}
    thread = _find_free_thread(thread_id)
    if thread is None:
        return {"ok": False, "error": "话题不存在"}
    if thread_id == state.free_chat_active_thread_id:
        _persist_active_thread_messages()
    state.free_chat_threads = [
        t for t in state.free_chat_threads if t.get("id") != thread_id
    ]
    if state.free_chat_active_thread_id == thread_id:
        state.free_chat_active_thread_id = state.free_chat_threads[0]["id"]
        _sync_free_history_from_active()
    save_free_chat()
    return {"ok": True, **get_free_chat_state()}


def clear_free_chat() -> dict:
    _ensure_free_chat_threads()
    state.free_chat_history.clear()
    thread = _active_free_thread()
    if thread is not None:
        thread["messages"] = []
        thread["updated_at"] = _free_chat_now()
    save_free_chat()
    return {"ok": True, **get_free_chat_state()}


def delete_free_chat_message(index: int) -> dict:
    """删除当前话题中的一条消息（按 0 起序号）。"""
    _ensure_free_chat_threads()
    n = len(state.free_chat_history)
    if index < 0 or index >= n:
        return {
            "ok": False,
            "error": f"无效的消息序号（当前共 {n} 条，有效范围 0–{max(0, n - 1)}）",
        }
    removed = state.free_chat_history[index]
    state.free_chat_history.pop(index)
    thread = _active_free_thread()
    if thread is not None:
        thread["messages"] = list(state.free_chat_history)
        thread["updated_at"] = _free_chat_now()
    save_free_chat()
    return {"ok": True, **get_free_chat_state()}


def free_chat(message: str, provider: str | None = None) -> dict:
    """自由聊天：无系统提示词，纯对话，不写章节。"""
    text = message.strip()
    if not text:
        return {"ok": False, "error": "消息不能为空"}

    _ensure_free_chat_threads()
    thread = _active_free_thread()
    if thread is None:
        return {"ok": False, "error": "无可用话题"}

    pid = _resolve_free_provider(provider)
    if provider and pid != state.free_chat_provider:
        state.free_chat_provider = pid

    if not thread.get("messages") and (thread.get("title") or "").startswith("新话题"):
        thread["title"] = _thread_title_from_message(text)

    state.free_chat_history.append({"role": "user", "content": text})
    trimmed = _trim_free_history()
    reply = call_api(
        None,
        trimmed,
        max_tokens=config.FREE_CHAT_MAX_TOKENS,
        provider=pid,
        tag="自由聊",
        silent=True,
    )
    if reply is None:
        state.free_chat_history.pop()
        return {"ok": False, "error": get_last_call_info().get("error", "发送失败")}

    state.free_chat_history.append({"role": "assistant", "content": reply})
    thread["updated_at"] = _free_chat_now()
    save_free_chat()
    return {
        "ok": True,
        "reply": reply,
        "provider": pid,
        **get_last_call_info(),
    }


def set_write_chapter_num(num: int) -> dict:
    """显式设置写作目标章（须有正文文件）。"""
    if num <= 0:
        state.write_chapter_num = 0
        return {"ok": True, "write_chapter_num": None}
    path = get_chapter_path(num)
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


def get_guide_status() -> dict:
    """写作引导：地基文件、规划、章后待办等状态（供 /api/guide/status）。"""
    import change_history

    track_keys = (
        "world",
        "char_static",
        "style",
        "char_dynamic",
        "plot_threads_active",
    )

    def _file_ready(key: str) -> bool:
        path = CODEX_FILES.get(key)
        if not path:
            return False
        text = read_text(path).strip()
        if len(text) < 20:
            return False
        placeholder = INITIAL_FILES.get(path, "").strip()
        return not placeholder or text != placeholder

    files = {key: _file_ready(key) for key in track_keys}

    plan = novel_data.load_plan()
    scene_count = sum(
        len(ch.get("scenes", [])) for ch in plan.get("chapters", {}).values()
    )
    has_plan = scene_count > 0

    latest = get_latest_chapter()
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

    recent_raw = read_text(SUMMARIES_RECENT_FILE)
    summaries_recent_count = len(re.findall(r"【第\d+章", recent_raw))

    combined_summaries = get_summaries_combined()
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


def get_app_status() -> dict:
    latest = get_latest_chapter()
    cfg = config.get_provider_config()
    project = novel_data.get_project_meta()
    return {
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
    }


def _quality_log_entry(
    kind: str,
    chapter_num: int,
    reply: str,
    *,
    summary: str = "",
    persisted: bool = False,
    persisted_detail: str = "",
    extra: dict | None = None,
) -> str:
    return quality_log.append_entry(
        kind,
        chapter_num,
        reply,
        summary=summary,
        persisted=persisted,
        persisted_detail=persisted_detail,
        extra=extra,
    )


def _finalize_call_snapshot(tag: str) -> dict | None:
    """从 state.last_call_info 提取单次 LLM 调用明细。"""
    info = get_last_call_info()
    if not info.get("ok"):
        return None
    usage = info.get("usage") or {}
    input_tokens = int(usage.get("input") or 0) + int(usage.get("cache_read") or 0)
    return {
        "tag": tag,
        "input_tokens": input_tokens,
        "output_tokens": int(usage.get("output") or 0),
        "cost_usd": round(float(info.get("cost") or 0.0), 6),
    }


def _parse_markdown_list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("- "):
            items.append(s)
    return items


def _append_plot_new_threads(
    chapter_num: int,
    plot_text: str,
    *,
    auto_append: bool,
) -> tuple[bool, list[str]]:
    items = _parse_markdown_list_items(plot_text)
    if not items:
        return False, items
    if not auto_append:
        return False, items
    block = "\n\n" + "\n".join(items) + "\n"
    wrote = write_text(
        PLOT_THREADS_ACTIVE_FILE,
        block,
        append=True,
        history_source="plot_threads",
        chapter_num=chapter_num,
    )
    return wrote, items


def _debug_c56229(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    # #region agent log
    try:
        with open(BASE_DIR / "debug-c56229.log", "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "c56229",
                        "location": location,
                        "message": message,
                        "data": data,
                        "hypothesisId": hypothesis_id,
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion


def _observe_item_has_change(item: dict) -> bool:
    """解析 has_change；缺省但有 proposed_text 时视为有变更。"""
    text = str(item.get("proposed_text") or item.get("suggestion") or "").strip()
    hc = item.get("has_change")
    if hc is None:
        return bool(text)
    if isinstance(hc, str):
        return hc.strip().lower() not in ("false", "0", "no", "否") and bool(text)
    return bool(hc) and bool(text)


def _observe_items_for_auto_apply(items: list[dict]) -> list[dict]:
    payload: list[dict] = []
    for it in items:
        if not _observe_item_has_change(it):
            continue
        text = str(it.get("proposed_text") or it.get("suggestion") or "").strip()
        if not text:
            continue
        target = str(it.get("target_file") or "char_dynamic").strip()
        if target not in ("char_static", "char_dynamic"):
            target = "char_dynamic"
        payload.append(
            {
                "id": it.get("id"),
                "target_file": target,
                "accepted": True,
                "proposed_text": it.get("proposed_text") or "",
                "edited_text": text,
            }
        )
    return payload


def _observe_fallback_apply(chapter_num: int, text: str) -> list[dict]:
    """JSON 解析失败或无结构化提案时，将摘要追加到 char_dynamic。"""
    body = (text or "").strip()
    if len(body) < 20:
        return []
    stamp = datetime.now().strftime("%Y-%m-%d")
    block = f"\n\n<!-- 角色观察 {stamp} -->\n{body[:4000]}\n"
    if write_text(
        CHAR_DYNAMIC_FILE,
        block,
        append=True,
        history_source="observe",
        chapter_num=chapter_num,
    ):
        return [{"id": "fallback_summary", "target_file": "char_dynamic"}]
    return []


def api_run_summary(chapter_num: int | None = None) -> dict:
    resolved = _resolve_chapter_num(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    chapter_num, content = resolved

    pid = config.SUMMARY_PROVIDER
    system = build_cached_system(SUMMARY_SYSTEM, provider=pid)
    messages = [{"role": "user", "content": build_summary_user_message(chapter_num, content)}]
    reply = call_api(system, messages, provider=pid, tag="概述", silent=True)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "生成失败")}

    summary_ok, summary_rotate = _persist_summary_text(chapter_num, reply.strip())
    persisted_detail = "已追加到 summaries_recent.md"
    if summary_rotate.get("rotated"):
        persisted_detail += (
            f"；{summary_rotate['rotated']} 条已归档到 summaries_archive.md"
        )
    log_id = _quality_log_entry(
        "summary",
        chapter_num,
        reply,
        persisted=summary_ok,
        persisted_detail=persisted_detail,
    )
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": chapter_num,
        "log_id": log_id,
        **get_last_call_info(),
    }


def api_run_check(chapter_num: int | None = None) -> dict:
    resolved = _resolve_chapter_num(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    chapter_num, chapter_content = resolved
    pid = config.CHECK_PROVIDER
    system = build_cached_system(CHECK_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_check_user_message(
                read_text(WORLD_FILE),
                read_text(CHARACTERS_FILE),
                get_char_context_for_check(),
                get_summaries_combined(),
                chapter_num,
                chapter_content,
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="检查", silent=True)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "检查失败")}
    log_id = _quality_log_entry("continuity", chapter_num, reply)
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": chapter_num,
        "log_id": log_id,
        **get_last_call_info(),
    }


def _resolve_chapter_num(chapter_num: int | None) -> tuple[int, str] | dict:
    if chapter_num and chapter_num > 0:
        content = read_chapter_content(chapter_num)
        if not content.strip():
            return {"ok": False, "error": f"第{chapter_num}章内容为空"}
        return chapter_num, content
    if state.write_chapter_num > 0:
        content = read_chapter_content(state.write_chapter_num)
        if content.strip():
            return state.write_chapter_num, content
    latest = get_latest_chapter()
    if latest is None:
        return {"ok": False, "error": "没有找到章节文件"}
    num, _, content = latest
    if not content.strip():
        return {"ok": False, "error": f"第{num}章内容为空"}
    return num, content


def get_chapters_text_for_scope(chapter_num: int, scope: str) -> str | None:
    if scope == "current":
        text = read_chapter_content(chapter_num)
        return text if text.strip() else None
    if scope == "recent3":
        start = max(1, chapter_num - 2)
        parts: list[str] = []
        for n in range(start, chapter_num + 1):
            c = read_chapter_content(n)
            if c.strip():
                parts.append(f"## 第{n}章\n{c}")
        return "\n\n".join(parts) if parts else None
    if scope == "all":
        parts = []
        for num, path in list_chapters():
            c = read_text(path)
            if c.strip():
                parts.append(f"## 第{num}章\n{c}")
        return "\n\n".join(parts) if parts else None
    return None


def api_run_character_drift(chapter_num: int | None = None) -> dict:
    resolved = _resolve_chapter_num(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    num, content = resolved
    pid = config.CHECK_PROVIDER
    system = build_cached_system(CHARACTER_DRIFT_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_character_drift_user_message(
                get_char_context_for_check(), content
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="人物检查", silent=True)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "检查失败")}
    log_id = _quality_log_entry("character_drift", num, reply)
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": num,
        "log_id": log_id,
        **get_last_call_info(),
    }


def api_run_observe(chapter_num: int | None = None, *, auto_apply: bool = True) -> dict:
    resolved = _resolve_chapter_num(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    num, content = resolved
    pid = config.CHECK_PROVIDER
    system = build_cached_system(OBSERVE_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_observe_user_message(
                num,
                content,
                _read_char_static(),
                read_text(CHAR_DYNAMIC_FILE).strip(),
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="角色观察", silent=True)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "分析失败")}
    items, summary = parse_observe_proposals(reply)
    applied: list[dict] = []
    persisted_detail = ""
    apply_error = ""
    if auto_apply:
        payload = _observe_items_for_auto_apply(items) if items else []
        if payload:
            apply_result = api_apply_observe(payload, chapter_num=num)
            if apply_result.get("ok"):
                applied = apply_result.get("applied", [])
                targets = "、".join(sorted({a["target_file"] for a in applied}))
                persisted_detail = f"已写入 {len(applied)} 条 → {targets}"
            else:
                apply_error = apply_result.get("error", "自动写入失败")
        elif items:
            apply_error = "有提案但无可写入内容（has_change 均为 false 且正文为空）"
        if not applied:
            fallback_text = summary or reply
            applied = _observe_fallback_apply(num, fallback_text)
            if applied:
                persisted_detail = "已写入 char_dynamic（摘要回退）"
                apply_error = ""
            elif not items:
                persisted_detail = "未解析到结构化提案"
    _debug_c56229(
        "main.py:api_run_observe",
        "observe auto_apply result",
        {
            "chapter_num": num,
            "auto_apply": auto_apply,
            "parse_ok": bool(items),
            "item_count": len(items),
            "payload_count": len(_observe_items_for_auto_apply(items)) if items else 0,
            "applied_count": len(applied),
            "apply_error": apply_error[:200],
        },
        "H1",
    )
    log_id = _quality_log_entry(
        "observe",
        num,
        reply,
        summary=summary or persisted_detail,
        persisted=bool(applied),
        persisted_detail=persisted_detail,
    )
    return {
        "ok": True,
        "chapter_num": num,
        "reply": reply,
        "summary": summary,
        "items": items,
        "parse_ok": bool(items),
        "auto_applied": applied,
        "apply_error": apply_error,
        "log_id": log_id,
        **get_last_call_info(),
    }


def api_apply_observe(items: list[dict], *, chapter_num: int | None = None) -> dict:
    if not items:
        return {"ok": False, "error": "没有可应用的提案"}
    ch = chapter_num if chapter_num and chapter_num > 0 else _session_chapter_num()
    pending: list[dict] = []
    skipped: list[str] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        if not raw.get("accepted"):
            item_id = str(raw.get("id", ""))
            if item_id:
                skipped.append(item_id)
            continue
        target = str(raw.get("target_file", "")).strip()
        if target not in ("char_static", "char_dynamic"):
            return {"ok": False, "error": f"非法 target_file: {target}"}
        text = str(raw.get("edited_text") or raw.get("proposed_text") or "").strip()
        if not text:
            skipped.append(str(raw.get("id", "?")))
            continue
        pending.append(
            {
                "id": raw.get("id"),
                "target": target,
                "text": text,
                "chapter_num": int(raw.get("chapter_num") or 0) or ch,
            }
        )
    if not pending:
        return {"ok": False, "error": "没有选中任何提案", "skipped": skipped}
    applied: list[dict] = []
    stamp = datetime.now().strftime("%Y-%m-%d")
    for item in pending:
        path = CHAR_STATIC_FILE if item["target"] == "char_static" else CHAR_DYNAMIC_FILE
        block = f"\n\n<!-- 角色观察 {stamp} -->\n{item['text']}\n"
        wrote = write_text(
            path,
            block,
            append=True,
            history_source="observe",
            chapter_num=item["chapter_num"],
        )
        # #region agent log
        _debug_c56229(
            "main.py:api_apply_observe",
            "observe item write",
            {
                "item_id": item.get("id"),
                "target": item["target"],
                "text_len": len(item["text"]),
                "wrote": wrote,
            },
            "H3",
        )
        # #endregion
        if wrote:
            applied.append({"id": item["id"], "target_file": item["target"]})
    if not applied:
        return {"ok": False, "error": "写入未生效（内容与磁盘相同或为空）", "skipped": skipped}
    return {"ok": True, "applied": applied, "skipped": skipped}


def api_run_detail_extract(
    chapter_num: int | None = None, *, auto_append: bool = True
) -> dict:
    resolved = _resolve_chapter_num(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    num, content = resolved
    pid = config.SUMMARY_PROVIDER
    system = build_cached_system(DETAIL_EXTRACT_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_detail_extract_user_message(
                num,
                content,
                read_text(PLOT_THREADS_LOCKED_FILE).strip(),
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="提取细节", silent=True)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "提取失败")}
    appended = False
    if auto_append and reply.strip():
        appended = write_text(
            PLOT_THREADS_LOCKED_FILE,
            f"\n\n{reply.strip()}\n",
            append=True,
            history_source="detail_extract",
            chapter_num=num,
        )
    _debug_c56229(
        "main.py:api_run_detail_extract",
        "detail extract append result",
        {
            "chapter_num": num,
            "auto_append": auto_append,
            "reply_chars": len(reply or ""),
            "appended": appended,
        },
        "H2",
    )
    log_id = _quality_log_entry(
        "detail_extract",
        num,
        reply,
        persisted=appended,
        persisted_detail=(
            "已追加到 plot_threads_locked.md" if appended else "未写入（正文为空）"
        ),
    )
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": num,
        "appended": appended,
        "log_id": log_id,
        **get_last_call_info(),
    }


def api_run_repetition_check(
    chapter_num: int | None = None, scope: str = "current"
) -> dict:
    if scope not in ("current", "recent3", "all"):
        return {"ok": False, "error": "scope 必须是 current / recent3 / all"}
    resolved = _resolve_chapter_num(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    num, _ = resolved
    text = get_chapters_text_for_scope(num, scope)
    if not text:
        return {"ok": False, "error": "选定范围内没有正文"}
    pid = config.CHECK_PROVIDER
    system = build_cached_system(REPETITION_CHECK_SYSTEM, provider=pid)
    messages = [{"role": "user", "content": text}]
    reply = call_api(system, messages, provider=pid, tag="重复检查", silent=True)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "检查失败")}
    log_id = _quality_log_entry("repetition", num, reply)
    return {
        "ok": True,
        "reply": reply,
        "chapter_num": num,
        "scope": scope,
        "log_id": log_id,
        **get_last_call_info(),
    }


def api_run_pacing_check() -> dict:
    summaries = get_summaries_combined()
    if not summaries or count_summaries() == 0:
        return {"ok": False, "error": "请先生成章节概述（生成概述）"}
    pid = config.CHECK_PROVIDER
    system = build_cached_system(PACING_CHECK_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_pacing_check_user_message(
                read_text(WORLD_FILE), summaries
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="爽点检查", silent=True)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "检查失败")}
    latest = get_latest_chapter()
    ch_num = latest[0] if latest else 0
    log_id = _quality_log_entry("pacing", ch_num, reply)
    return {"ok": True, "reply": reply, "log_id": log_id, **get_last_call_info()}


def _outline_context_ready() -> str | None:
    """返回 None 表示可生成；否则为错误说明。"""
    if get_latest_chapter() is None:
        return "没有找到章节文件"
    if not get_summaries_combined() or count_summaries() == 0:
        return "请先生成章节概述（/summary 或 Web「生成概述」）"
    return None


def api_run_outline(next_count: int = 3) -> dict:
    err = _outline_context_ready()
    if err:
        return {"ok": False, "error": err}

    n = max(1, min(10, next_count))
    pid = config.OUTLINE_PROVIDER
    system = build_cached_system(OUTLINE_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_outline_user_message(
                read_text(WORLD_FILE),
                get_char_context_for_check(),
                get_summaries_combined(),
                _read_plot_active(),
                n,
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="续章灵感", silent=True)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "生成失败")}
    latest = get_latest_chapter()
    chapter_num = latest[0] if latest else None
    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_text(
        OUTLINE_LATEST_FILE,
        f"# 续章灵感\n\n生成时间：{saved_at}\n当前章节：第{chapter_num or '?'}章\n\n{reply.strip()}\n",
        append=False,
    )
    suggestions = novel_data.parse_outline_suggestions(reply)
    return {
        "ok": True,
        "reply": reply,
        "saved_at": saved_at,
        "saved_to": str(OUTLINE_LATEST_FILE.relative_to(BASE_DIR)),
        "next_count": n,
        "chapter_num": chapter_num,
        "suggestions": suggestions,
        **get_last_call_info(),
    }


def get_outline_latest() -> dict:
    if not OUTLINE_LATEST_FILE.exists():
        return {"ok": True, "content": "", "saved_at": None, "suggestions": []}
    text = read_text(OUTLINE_LATEST_FILE)
    body = text
    if text.startswith("# 续章灵感"):
        body = re.sub(r"^# 续章灵感\s*\n+(?:生成时间：.*\n)?(?:当前章节：.*\n)?\n?", "", text, count=1)
    saved_at = None
    m = re.search(r"生成时间：(.+)", text)
    if m:
        saved_at = m.group(1).strip()
    return {
        "ok": True,
        "content": text,
        "body": body.strip(),
        "saved_at": saved_at,
        "suggestions": novel_data.parse_outline_suggestions(body),
    }


def api_apply_outline(
    offset: int = 1,
    *,
    replace: bool = False,
    reply: str | None = None,
) -> dict:
    text = (reply or "").strip() or read_text(OUTLINE_LATEST_FILE)
    if not text.strip():
        return {"ok": False, "error": "没有续章灵感，请先在写书对话点「续章灵感」生成"}
    if text.startswith("# 续章灵感"):
        text = re.sub(
            r"^# 续章灵感\s*\n+(?:生成时间：.*\n)?(?:当前章节：.*\n)?\n?",
            "",
            text,
            count=1,
        )
    suggestions = novel_data.parse_outline_suggestions(text)
    if not suggestions:
        return {"ok": False, "error": "无法解析续章建议，请检查 AI 输出格式或重新生成"}
    if offset < 1 or offset > len(suggestions):
        return {
            "ok": False,
            "error": f"没有第 {offset} 条续章建议（共 {len(suggestions)} 条）",
        }

    latest = get_latest_chapter()
    if latest is None:
        return {"ok": False, "error": "没有找到章节文件"}
    base_chapter = latest[0]
    target = base_chapter + 1
    suggestion = suggestions[offset - 1]

    result = novel_data.apply_outline_suggestion_to_chapter(
        base_chapter,
        suggestion,
        target_offset=1,
        replace=replace,
    )
    if result.get("ok"):
        result["target_chapter"] = target
        result["suggestion_index"] = offset
        ch_file = ensure_chapter_file(
            result["chapter_num"],
            result.get("chapter_title", ""),
        )
        result["chapter_file_created"] = ch_file.get("created", False)
        result["chapter_file"] = ch_file.get("file")
    return result


def get_chapter_by_num(num: int) -> dict | None:
    path = CHAPTERS_DIR / f"ch{num:03d}.md"
    if not path.exists():
        return None
    return {"num": num, "path": str(path.name), "content": read_text(path)}


def save_chapter_by_num(num: int, content: str) -> dict:
    path = CHAPTERS_DIR / f"ch{num:03d}.md"
    content = sanitize_chapter_text(content)
    changed = write_text(path, content, append=False, chapter_num=num)
    # #region agent log
    _debug_c56229(
        "main.py:save_chapter_by_num",
        "chapter save",
        {"num": num, "changed": changed, "content_len": len(content or "")},
        "H4",
    )
    # #endregion
    _invalidate_chapter_injection(num)
    chapter_title = sync_chapter_title_from_file(num)
    return {"ok": True, "num": num, "chapter_title": chapter_title, "changed": changed}


SUMMARIES_RECENT_KEEP = 4


def _split_summary_entries(content: str) -> tuple[str, list[str]]:
    """按「【第N章」拆分为文件头 + 各章概述块。"""
    text = content or ""
    parts = re.split(r"(?=^【第\d+章)", text, flags=re.MULTILINE)
    if len(parts) <= 1:
        return text, []
    header = parts[0]
    entries = [p.strip() for p in parts[1:] if p.strip()]
    return header, entries


def _maybe_rotate_summaries_to_archive(
    *,
    keep_recent: int = SUMMARIES_RECENT_KEEP,
    chapter_num: int = 0,
) -> dict:
    """近期概述超过 keep_recent 条时，将最旧条目追加到 summaries_archive。"""
    recent_raw = read_text(SUMMARIES_RECENT_FILE)
    header, entries = _split_summary_entries(recent_raw)
    if len(entries) <= keep_recent:
        # #region agent log
        _dbg_finalize_main(
            "main.py:_maybe_rotate_summaries_to_archive",
            "archive skip",
            {"entry_count": len(entries), "keep_recent": keep_recent},
            "H7",
        )
        # #endregion
        return {"rotated": 0, "ok": True, "recent_count": len(entries)}

    to_archive = entries[: len(entries) - keep_recent]
    kept = entries[len(entries) - keep_recent :]
    archive_body = "\n\n".join(to_archive).strip() + "\n"
    archived = write_text(
        SUMMARIES_ARCHIVE_FILE,
        f"\n\n{archive_body}",
        append=True,
        history_source="summary",
        chapter_num=chapter_num,
    )
    new_recent = header.rstrip() + "\n\n" + "\n\n".join(kept) + "\n"
    trimmed = write_text(
        SUMMARIES_RECENT_FILE,
        new_recent,
        append=False,
        history_source="summary",
        chapter_num=chapter_num,
    )
    # #region agent log
    _dbg_finalize_main(
        "main.py:_maybe_rotate_summaries_to_archive",
        "archive rotated",
        {
            "rotated": len(to_archive),
            "kept": len(kept),
            "archived": archived,
            "trimmed": trimmed,
        },
        "H7",
    )
    # #endregion
    return {
        "rotated": len(to_archive),
        "ok": archived and trimmed,
        "recent_count": len(kept),
        "archived": archived,
    }


def _persist_summary_text(chapter_num: int, summary_text: str) -> tuple[bool, dict]:
    text = (summary_text or "").strip()
    if not text:
        return False, {"rotated": 0, "ok": True, "recent_count": 0}
    append_text = f"\n{text}\n"
    w1 = write_text(
        SUMMARIES_RECENT_FILE,
        append_text,
        append=True,
        history_source="summary",
        chapter_num=chapter_num,
    )
    w2 = write_text(
        SUMMARIES_FILE,
        append_text,
        append=True,
        history_source="summary",
        chapter_num=chapter_num,
    )
    rotate = _maybe_rotate_summaries_to_archive(chapter_num=chapter_num)
    return (w1 or w2), rotate


def _apply_maintain_observe(
    chapter_num: int,
    observe_block: dict,
    *,
    auto_apply: bool,
) -> tuple[list[dict], str, str]:
    """从合并 JSON 的 observe 段写入 char_*。返回 (applied, persisted_detail, apply_error)。"""
    if not auto_apply:
        return [], "", ""
    items = observe_block.get("items") if isinstance(observe_block, dict) else []
    if not isinstance(items, list):
        items = []
    summary = str(observe_block.get("summary") or "").strip() if isinstance(observe_block, dict) else ""
    applied: list[dict] = []
    persisted_detail = ""
    apply_error = ""
    payload = _observe_items_for_auto_apply(items) if items else []
    if payload:
        apply_result = api_apply_observe(payload, chapter_num=chapter_num)
        if apply_result.get("ok"):
            applied = apply_result.get("applied", [])
            targets = "、".join(sorted({a["target_file"] for a in applied}))
            persisted_detail = f"已写入 {len(applied)} 条 → {targets}"
        else:
            apply_error = apply_result.get("error", "自动写入失败")
    elif items:
        apply_error = "有提案但无可写入内容（has_change 均为 false 且正文为空）"
    if not applied:
        fallback_text = summary
        applied = _observe_fallback_apply(chapter_num, fallback_text)
        if applied:
            persisted_detail = "已写入 char_dynamic（摘要回退）"
            apply_error = ""
    return applied, persisted_detail, apply_error


def _build_archive_context(num: int, content: str) -> dict:
    return {
        "chapter_num": num,
        "content": content,
        "char_static": _read_char_static(),
        "char_dynamic": read_text(CHAR_DYNAMIC_FILE).strip(),
        "plot_locked": read_text(PLOT_THREADS_LOCKED_FILE).strip(),
        "plot_unresolved": extract_plot_active_unresolved(
            read_text(PLOT_THREADS_ACTIVE_FILE).strip()
        ),
    }


def _call_archive_bundle(ctx: dict) -> tuple[str | None, dict | None]:
    pid = config.MAINTAIN_PROVIDER
    system = build_cached_system(POST_CHAPTER_MAINTAIN_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_post_chapter_maintain_user_message(
                ctx["chapter_num"],
                ctx["content"],
                ctx["char_static"],
                ctx["char_dynamic"],
                ctx["plot_locked"],
                ctx["plot_unresolved"],
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="档案bundle", silent=True)
    if reply is None:
        return None, None
    parsed, _ = parse_post_chapter_maintain(reply)
    return reply, parsed


def _persist_archive_payload(
    num: int,
    parsed: dict,
    *,
    auto_apply_observe: bool,
    auto_append_locked: bool,
    auto_append_plot_new: bool,
) -> tuple[dict, list[str], list[dict]]:
    """将档案 bundle 解析结果写入磁盘，返回 archive 块、errors、结构化 errors。"""
    errors: list[str] = []
    structured: list[dict] = []

    summary_text = parsed.get("summary", "")
    summary_rotate: dict = {"rotated": 0, "ok": True, "recent_count": 0}
    if summary_text:
        summary_ok, summary_rotate = _persist_summary_text(num, summary_text)
    else:
        summary_ok = False
    if summary_text and not summary_ok:
        errors.append("概述：生成成功但未写入 summaries")
        structured.append(
            {"task": "summary", "stage": "write", "message": "写入 summaries 失败"}
        )

    observe_block = parsed.get("observe") or {}
    applied, observe_detail, observe_err = _apply_maintain_observe(
        num,
        observe_block,
        auto_apply=auto_apply_observe,
    )
    observe_items = observe_block.get("items", []) if isinstance(observe_block, dict) else []
    observe_summary = (
        str(observe_block.get("summary") or "").strip()
        if isinstance(observe_block, dict)
        else ""
    )
    skipped_observe = 0
    if observe_items:
        for item in observe_items:
            if not isinstance(item, dict):
                continue
            if not item.get("has_change") and not (
                str(item.get("proposed_text") or "").strip()
            ):
                skipped_observe += 1
    if auto_apply_observe and observe_items and not applied:
        errors.append(f"角色观察：{observe_err or '未写入 char_*'}")
        structured.append(
            {
                "task": "observe",
                "stage": "write",
                "message": observe_err or "未写入 char_*",
            }
        )

    detail_text = parsed.get("detail_locked", "")
    detail_appended = False
    if auto_append_locked and detail_text.strip():
        detail_appended = write_text(
            PLOT_THREADS_LOCKED_FILE,
            f"\n\n{detail_text.strip()}\n",
            append=True,
            history_source="detail_extract",
            chapter_num=num,
        )
    if detail_text.strip() and auto_append_locked and not detail_appended:
        errors.append("提取细节：生成成功但未写入 plot_threads_locked")
        structured.append(
            {"task": "detail_locked", "stage": "write", "message": "写入 locked 失败"}
        )

    plot_new_text = parsed.get("plot_new_threads", "")
    plot_appended, plot_items = _append_plot_new_threads(
        num,
        plot_new_text,
        auto_append=auto_append_plot_new,
    )
    if plot_new_text.strip() and auto_append_plot_new and not plot_appended:
        errors.append("新伏笔：生成成功但未写入 plot_threads_active")
        structured.append(
            {
                "task": "plot_new_threads",
                "stage": "write",
                "message": "写入 active 失败",
            }
        )

    observe_out_items: list[dict] = []
    for raw in observe_items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id", ""))
        applied_ids = {str(a.get("id", "")) for a in applied}
        observe_out_items.append(
            {
                "id": item_id,
                "target_file": raw.get("target_file"),
                "has_change": bool(raw.get("has_change")),
                "proposed_text": raw.get("proposed_text", ""),
                "applied": item_id in applied_ids,
            }
        )

    archive = {
        "summary": {
            "ok": summary_ok,
            "text": summary_text[:200] if summary_text else "",
            "full_text": summary_text,
            "written_to": "summaries_recent",
            "archived_count": summary_rotate.get("rotated", 0),
            "archive_written_to": (
                "summaries_archive" if summary_rotate.get("rotated") else None
            ),
        },
        "observe": {
            "ok": bool(applied) or (bool(observe_items) and not auto_apply_observe),
            "applied_count": len(applied),
            "skipped_count": skipped_observe,
            "items": observe_out_items,
            "summary": observe_summary,
            "detail": observe_detail,
        },
        "detail_locked": {
            "ok": detail_appended or (bool(detail_text.strip()) and not auto_append_locked),
            "appended_count": len(_parse_markdown_list_items(detail_text)) or (1 if detail_appended else 0),
            "written_to": "plot_threads_locked",
            "text": detail_text,
        },
        "plot_new_threads": {
            "ok": plot_appended or (bool(plot_items) and not auto_append_plot_new),
            "appended_count": len(plot_items) if plot_appended else 0,
            "written_to": "plot_threads_active",
            "items": plot_items,
            "text": plot_new_text,
        },
    }
    return archive, errors, structured


def api_run_post_chapter_maintain(
    chapter_num: int | None = None,
    *,
    auto_apply: bool = True,
    auto_append: bool = True,
) -> dict:
    """章后维护：单次 LLM 档案 bundle（子集，不含质检）。"""
    resolved = _resolve_chapter_num(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    num, content = resolved
    if not (content or "").strip():
        return {"ok": False, "error": "章节正文为空，无法运行章后维护"}

    ctx = _build_archive_context(num, content)
    reply, parsed = _call_archive_bundle(ctx)
    if reply is None:
        return {"ok": False, "error": get_last_call_info().get("error", "章后维护失败")}
    if not parsed:
        log_id = _quality_log_entry(
            "post_chapter_maintain",
            num,
            reply,
            persisted=False,
            persisted_detail="JSON 解析失败",
        )
        return {
            "ok": False,
            "error": "未能解析章后维护 JSON，请重试或使用单独按钮",
            "chapter_num": num,
            "parse_ok": False,
            "reply": reply,
            "log_id": log_id,
            **get_last_call_info(),
        }

    archive, errors, _ = _persist_archive_payload(
        num,
        parsed,
        auto_apply_observe=auto_apply,
        auto_append_locked=auto_append,
        auto_append_plot_new=False,
    )
    persisted = {
        "summary": archive["summary"]["ok"],
        "observe": archive["observe"]["applied_count"] > 0,
        "detail_extract": archive["detail_locked"]["ok"]
        and bool(archive["detail_locked"].get("text")),
    }
    summary_r = {
        "ok": archive["summary"]["ok"],
        "reply": archive["summary"]["full_text"],
        "chapter_num": num,
    }
    observe_r = {
        "ok": True,
        "chapter_num": num,
        "summary": archive["observe"].get("summary", ""),
        "items": archive["observe"]["items"],
        "parse_ok": bool(archive["observe"]["items"]),
        "auto_applied": [
            {"id": i["id"], "target_file": i["target_file"]}
            for i in archive["observe"]["items"]
            if i.get("applied")
        ],
        "apply_error": errors[0] if errors and "角色观察" in errors[0] else "",
    }
    detail_r = {
        "ok": True,
        "reply": archive["detail_locked"].get("text", ""),
        "chapter_num": num,
        "appended": persisted["detail_extract"],
    }

    ok = persisted["summary"] or persisted["observe"] or persisted["detail_extract"]
    detail_parts = []
    if persisted["summary"]:
        detail_parts.append("概述")
    if persisted["observe"]:
        detail_parts.append(archive["observe"].get("detail") or "角色观察")
    if persisted["detail_extract"]:
        detail_parts.append("细节钉子")
    log_id = _quality_log_entry(
        "post_chapter_maintain",
        num,
        reply,
        summary=(archive["summary"]["full_text"] or "")[:200],
        persisted=ok,
        persisted_detail="、".join(detail_parts) if detail_parts else "未写入",
    )

    if not ok:
        return {
            "ok": False,
            "error": "；".join(errors) or "章后维护未写入任何文件",
            "chapter_num": num,
            "persisted": persisted,
            "errors": errors,
            "parse_ok": True,
            "unified": True,
            "log_id": log_id,
            **get_last_call_info(),
        }
    return {
        "ok": True,
        "chapter_num": num,
        "persisted": persisted,
        "errors": errors,
        "partial": bool(errors),
        "parse_ok": True,
        "unified": True,
        "summary": summary_r,
        "observe": observe_r,
        "detail_extract": detail_r,
        "log_id": log_id,
        **get_last_call_info(),
    }


def _dbg_finalize_main(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    # #region agent log
    try:
        with open(BASE_DIR / "debug-2b4904.log", "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "2b4904",
                        "location": location,
                        "message": message,
                        "data": data,
                        "hypothesisId": hypothesis_id,
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion


def api_run_post_chapter_finalize(
    chapter_num: int | None = None,
    *,
    run_pacing: bool = True,
    run_outline: bool = False,
    repetition_scope: str = "current",
    auto_apply_observe: bool = True,
    auto_append_locked: bool = True,
    auto_append_plot_new: bool = True,
) -> dict:
    """本章定稿：档案 bundle + 质检 bundle + 可选 pacing/outline。"""
    # #region agent log
    _dbg_finalize_main(
        "main.py:api_run_post_chapter_finalize",
        "finalize entry",
        {
            "chapter_num": chapter_num,
            "run_pacing": run_pacing,
            "repetition_scope": repetition_scope,
        },
        "H2",
    )
    # #endregion
    if repetition_scope not in ("current", "recent3", "all"):
        return {"ok": False, "error": "repetition_scope 必须是 current / recent3 / all"}

    resolved = _resolve_chapter_num(chapter_num)
    if isinstance(resolved, dict):
        return resolved
    num, content = resolved
    if not (content or "").strip():
        return {"ok": False, "error": "章节正文为空，无法定稿"}

    calls: list[dict] = []
    errors: list[dict] = []
    ctx = _build_archive_context(num, content)

    archive_reply: str | None = None
    archive_parsed: dict | None = None
    archive_reply, archive_parsed = _call_archive_bundle(ctx)
    snap = _finalize_call_snapshot("archive_bundle")
    if snap:
        calls.append(snap)
    if archive_reply is None:
        errors.append(
            {
                "task": "archive_bundle",
                "stage": "call",
                "message": get_last_call_info().get("error", "档案 bundle 失败"),
                "fallback_used": False,
                "raw_snippet": "",
            }
        )
    elif not archive_parsed:
        errors.append(
            {
                "task": "archive_bundle",
                "stage": "parse",
                "message": "未能解析 post-chapter-json",
                "fallback_used": False,
                "raw_snippet": (archive_reply or "")[:300],
            }
        )

    quality_reply: str | None = None
    quality_parsed: dict | None = None
    rep_text = get_chapters_text_for_scope(num, repetition_scope)
    if not rep_text:
        rep_text = content
        repetition_scope = "current"
    pid_q = config.QUALITY_PROVIDER
    system_q = build_cached_system(QUALITY_CHECK_BUNDLE_SYSTEM, provider=pid_q)
    messages_q = [
        {
            "role": "user",
            "content": build_quality_bundle_user_message(
                read_text(WORLD_FILE),
                read_text(CHARACTERS_FILE),
                get_char_context_for_check(),
                get_summaries_combined(),
                num,
                content,
                rep_text,
                repetition_scope,
            ),
        }
    ]
    quality_reply = call_api(
        system_q, messages_q, provider=pid_q, tag="质检bundle", silent=True
    )
    snap_q = _finalize_call_snapshot("quality_bundle")
    if snap_q:
        calls.append(snap_q)
    if quality_reply is None:
        errors.append(
            {
                "task": "quality_bundle",
                "stage": "call",
                "message": get_last_call_info().get("error", "质检 bundle 失败"),
                "fallback_used": False,
                "raw_snippet": "",
            }
        )
    else:
        quality_parsed, _ = parse_quality_bundle(quality_reply)
        if not quality_parsed:
            errors.append(
                {
                    "task": "quality_bundle",
                    "stage": "parse",
                    "message": "未能解析 quality-bundle-json",
                    "fallback_used": False,
                    "raw_snippet": (quality_reply or "")[:300],
                }
            )

    archive: dict = {}
    archive_errors: list[str] = []
    plot_proposal = {"advanced": "", "resolved": ""}
    summary_written = False
    if archive_parsed:
        plot_proposal["advanced"] = archive_parsed.get("plot_advanced", "")
        plot_proposal["resolved"] = archive_parsed.get("plot_resolved", "")
        archive, archive_errors, struct_a = _persist_archive_payload(
            num,
            archive_parsed,
            auto_apply_observe=auto_apply_observe,
            auto_append_locked=auto_append_locked,
            auto_append_plot_new=auto_append_plot_new,
        )
        summary_written = bool(archive.get("summary", {}).get("ok"))
        for e in struct_a:
            e.setdefault("fallback_used", False)
            e.setdefault("raw_snippet", "")
            errors.append(e)

    quality: dict = {
        "continuity": {"ok": False, "issue_count": 0, "text": ""},
        "character_drift": {"ok": False, "issue_count": 0, "text": ""},
        "repetition": {"ok": False, "issue_count": 0, "text": ""},
        "pacing": {
            "ok": False,
            "skipped": True,
            "skip_reason": "disabled",
            "text": "",
        },
    }
    if quality_parsed:
        for key, task in (
            ("continuity", "continuity"),
            ("character_drift", "character_drift"),
            ("repetition", "repetition"),
        ):
            text = quality_parsed.get(key, "")
            quality[task] = {
                "ok": bool(text),
                "issue_count": count_report_issues(text),
                "text": text,
            }

    pacing_result: dict = {
        "ok": False,
        "skipped": True,
        "skip_reason": "disabled" if not run_pacing else "summary_not_written",
        "text": "",
    }
    if run_pacing:
        if summary_written:
            pacing_r = api_run_pacing_check()
            snap_p = _finalize_call_snapshot("pacing")
            if snap_p:
                calls.append(snap_p)
            if pacing_r.get("ok"):
                pacing_text = pacing_r.get("reply", "")
                pacing_result = {
                    "ok": True,
                    "skipped": False,
                    "skip_reason": None,
                    "text": pacing_text,
                }
            else:
                errors.append(
                    {
                        "task": "pacing",
                        "stage": "call",
                        "message": pacing_r.get("error", "爽点检查失败"),
                        "fallback_used": False,
                        "raw_snippet": "",
                    }
                )
                pacing_result["skip_reason"] = None
        else:
            pacing_result["skip_reason"] = "summary_not_written"
    quality["pacing"] = pacing_result

    outline_result: dict = {
        "ok": False,
        "skipped": not run_outline,
        "skip_reason": "disabled" if not run_outline else None,
        "reply": None,
        "applied_to": None,
    }
    if run_outline:
        outline_r = api_run_outline()
        snap_o = _finalize_call_snapshot("outline")
        if snap_o:
            calls.append(snap_o)
        if outline_r.get("ok"):
            outline_result = {
                "ok": True,
                "skipped": False,
                "skip_reason": None,
                "reply": outline_r.get("reply"),
                "applied_to": "outline_latest",
            }
        else:
            errors.append(
                {
                    "task": "outline",
                    "stage": "call",
                    "message": outline_r.get("error", "续章灵感失败"),
                    "fallback_used": False,
                    "raw_snippet": "",
                }
            )

    manual_todos: list[dict] = []
    recent_raw = read_text(SUMMARIES_RECENT_FILE)
    recent_entry_count = len(re.findall(r"【第\d+章", recent_raw))
    archive_rotated = int((archive.get("summary") or {}).get("archived_count") or 0)
    if recent_entry_count >= 5 and archive_rotated <= 0:
        manual_todos.append(
            {
                "key": "archive_cut",
                "label": "归档剪切：将旧条目从 summaries_recent 移入 summaries_archive",
                "action": "open_file",
                "target": "summaries_recent",
                "dismissible": True,
            }
        )
    resolved_hint = _parse_markdown_list_items(plot_proposal.get("resolved", ""))
    if resolved_hint:
        manual_todos.append(
            {
                "key": "resolved_threads",
                "label": "伏笔回收：以下伏笔疑似已回收，请手动移至「已回收」区",
                "action": "open_file",
                "target": "plot_threads_active",
                "hint_items": resolved_hint,
                "dismissible": True,
            }
        )
    if run_outline and outline_result.get("ok"):
        manual_todos.append(
            {
                "key": "outline_apply",
                "label": "续章灵感已生成，请确认后写入下一章 Beat",
                "action": "open_outline",
                "target": "outline_latest",
                "dismissible": True,
            }
        )

    archive_any = summary_written or (
        archive.get("observe", {}).get("applied_count", 0) > 0
    ) or archive.get("detail_locked", {}).get("ok") or archive.get(
        "plot_new_threads", {}
    ).get(
        "appended_count", 0
    ) > 0
    quality_any = any(
        quality[k].get("ok") for k in ("continuity", "character_drift", "repetition")
    ) or quality["pacing"].get("ok")
    ok = archive_any or quality_any
    partial = bool(errors) and ok

    total_cost = round(sum(c.get("cost_usd", 0) for c in calls), 6)
    log_summary_parts: list[str] = []
    if archive.get("summary", {}).get("ok"):
        log_summary_parts.append("概述✓")
    if archive.get("observe", {}).get("applied_count"):
        log_summary_parts.append(f"观察×{archive['observe']['applied_count']}")
    if archive.get("plot_new_threads", {}).get("appended_count"):
        log_summary_parts.append(
            f"伏笔×{archive['plot_new_threads']['appended_count']}"
        )
    if quality.get("continuity", {}).get("issue_count"):
        log_summary_parts.append(
            f"连续性{quality['continuity']['issue_count']}条"
        )

    log_id = _quality_log_entry(
        "finalize",
        num,
        json.dumps(
            {
                "archive": {k: v.get("ok") for k, v in archive.items()} if archive else {},
                "quality_ok": quality_any,
            },
            ensure_ascii=False,
        ),
        summary=" · ".join(log_summary_parts) or "本章定稿",
        persisted=archive_any,
        persisted_detail="、".join(log_summary_parts) if log_summary_parts else "",
        extra={"calls": calls, "ok": ok, "partial": partial},
    )

    flat_errors = [f"{e.get('task', '?')}：{e.get('message', '')}" for e in errors]
    if archive_errors:
        flat_errors = list(dict.fromkeys(flat_errors + archive_errors))

    result = {
        "ok": ok,
        "chapter_num": num,
        "partial": partial,
        "errors": flat_errors,
        "structured_errors": errors,
        "calls": calls,
        "total_cost_usd": total_cost,
        "archive": archive,
        "plot_proposal": plot_proposal,
        "quality": quality,
        "outline": outline_result,
        "manual_todos": manual_todos,
        "log_id": log_id,
        **get_last_call_info(),
    }
    if not ok:
        result["error"] = "；".join(flat_errors) or "本章定稿未产生任何结果"
    # #region agent log
    _dbg_finalize_main(
        "main.py:api_run_post_chapter_finalize",
        "finalize exit",
        {
            "ok": ok,
            "partial": partial,
            "archive_summary_ok": archive.get("summary", {}).get("ok"),
            "archive_observe_applied": archive.get("observe", {}).get("applied_count"),
            "calls_count": len(calls),
        },
        "H4",
    )
    # #endregion
    return result


def _chapter_cn(n: int) -> str:
    """1–99 章中文序数（用于正文文件标题行）。"""
    if n <= 0:
        return str(n)
    if n < 10:
        return "一二三四五六七八九"[n - 1]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + _chapter_cn(n - 10)
    if n % 10 == 0:
        return _chapter_cn(n // 10) + "十"
    return _chapter_cn(n // 10) + "十" + _chapter_cn(n % 10)


def ensure_chapter_file(chapter_num: int, title: str = "") -> dict:
    """若章节正文文件不存在则创建，并写入可编辑的标题行。"""
    path = CHAPTERS_DIR / f"ch{chapter_num:03d}.md"
    if path.exists():
        return {"ok": True, "num": chapter_num, "created": False, "file": path.name}
    path.parent.mkdir(parents=True, exist_ok=True)
    title = (title or "").strip()
    header = f"# 第{chapter_num}章"
    if title and title not in {
        f"第{chapter_num}章",
        f"第{_chapter_cn(chapter_num)}章",
    }:
        header = f"{header} · {title}"
    file_utils.atomic_write_text(path, f"{header}\n\n")
    return {"ok": True, "num": chapter_num, "created": True, "file": path.name}


def create_next_chapter() -> dict:
    chapters = list_chapters()
    next_num = (chapters[-1][0] + 1) if chapters else 1
    plan = novel_data.get_chapter_plan(next_num)
    title = (plan or {}).get("title", "") if plan else ""
    return ensure_chapter_file(next_num, title)


def get_codex(name: str) -> dict | None:
    path = CODEX_FILES.get(name)
    if path is None:
        return None
    return {"name": name, "content": read_text(path)}


def _maint_file_has_user_content(file_key: str) -> bool:
    """章后维护文件是否已有用户填写（非空模板）。"""
    path = CODEX_FILES.get(file_key)
    if not path:
        return False
    text = read_text(path).strip()
    if len(text) < 30:
        return False
    placeholder = INITIAL_FILES.get(path, "").strip()
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


def save_codex(name: str, content: str, chapter_num: int | None = None) -> dict:
    path = CODEX_FILES.get(name)
    if path is None:
        return {"ok": False, "error": f"未知设定文件: {name}"}
    ch = chapter_num if chapter_num and chapter_num > 0 else _session_chapter_num()
    changed = write_text(
        path, content, append=False, history_source="codex", chapter_num=ch
    )
    # #region agent log
    try:
        with open(BASE_DIR / "debug-c56229.log", "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "c56229",
                        "location": "main.py:save_codex",
                        "message": "codex save",
                        "data": {
                            "name": name,
                            "chapter_num": ch,
                            "changed": changed,
                        },
                        "hypothesisId": "H1",
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion
    return {"ok": True, "name": name, "changed": changed}


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
    write_text(
        SUMMARIES_RECENT_FILE,
        append_text,
        append=True,
        history_source="summary",
        chapter_num=chapter_num,
    )
    write_text(
        SUMMARIES_FILE,
        append_text,
        append=True,
        history_source="summary",
        chapter_num=chapter_num,
    )
    print(f"\n概述已追加至 summaries_recent.md（{cfg['name']}）；仅④层变动，③层归档缓存可保持命中")
    print(reply)


def do_check() -> None:
    latest = get_latest_chapter()
    if latest is None:
        print("错误：没有找到章节文件")
        return

    chapter_num, _, chapter_content = latest
    world = read_text(WORLD_FILE)
    characters = read_text(CHARACTERS_FILE)
    pid = config.CHECK_PROVIDER
    system = build_cached_system(CHECK_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_check_user_message(
                world,
                characters,
                get_char_context_for_check(),
                get_summaries_combined(),
                chapter_num,
                chapter_content,
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="检查")
    if reply is not None:
        print(f"\n{reply}\n")


def do_outline(next_count: int = 3) -> None:
    err = _outline_context_ready()
    if err:
        print(f"错误：{err}")
        return

    n = max(1, min(10, next_count))
    pid = config.OUTLINE_PROVIDER
    cfg = config.get_provider_config(pid)
    system = build_cached_system(OUTLINE_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_outline_user_message(
                read_text(WORLD_FILE),
                get_char_context_for_check(),
                get_summaries_combined(),
                _read_plot_active(),
                n,
            ),
        }
    ]
    reply = call_api(system, messages, provider=pid, tag="续章灵感")
    if reply is not None:
        print(f"\n（{cfg['name']} · 后续 {n} 章建议）\n{reply}\n")


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
        print("\n用法：/provider kie | kie-opus | kie-opus-47 | kie-opus-48 | deepseek")
        print("（只切换主力写作；/summary、/check、/outline 见 config.py）")
        return

    if arg not in config.PROVIDERS:
        print(f"未知提供商：{arg}")
        print(config.list_providers())
        return

    config.PROVIDER = arg
    config.save_runtime_settings()
    reset_client(arg)
    cfg = config.get_provider_config()
    print(f"✅ 主力写作已切换至 {cfg['name']}（模型: {cfg['model']}）")
    print(
        f"   /summary → {config.SUMMARY_PROVIDER}  |  "
        f"/check → {config.CHECK_PROVIDER}  |  /outline → {config.OUTLINE_PROVIDER}（不变）"
    )
    if not config.supports_prompt_cache():
        print("   该提供商不支持 Prompt Cache，心跳已自动跳过")
    elif not config.is_api_key_configured():
        print(f"   ⚠️  请配置 {cfg['api_key_env']}")


def do_cost() -> None:
    print(f"累计总费用（预估）：${state.total_cost:.6f}")
    if COST_LOG_JSONL.exists():
        print(f"详细记录见：{COST_LOG_JSONL}")
    elif COST_LOG.exists():
        print(f"详细记录见：{COST_LOG}（旧格式）")


def backup_session_before_clear() -> None:
    if not state.conversation_history:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUPS_DIR / f"session_{ts}.md"
    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dest.write_text(format_session_markdown(saved_at, "before_new"), encoding="utf-8")
    print(f"旧会话已备份到 {dest}")


def do_new() -> None:
    pending = count_unsaved_chapter_turns()
    if pending:
        print(f"⚠️  还有 {pending} 条正文未写入章节，正在补存…")
        flush_chapter_writes()
    backup_session_before_clear()
    state.conversation_history.clear()
    state.session_includes_chapter = False
    state.write_chapter_num = 0
    state.last_injected_chapter_num = 0
    state.appended_indices.clear()
    clear_session_files()
    print("对话历史已清空（文档缓存保留）")


def print_help() -> None:
    print("""
可用命令：
  /summary   — 生成概述（默认 DeepSeek，config.SUMMARY_PROVIDER）
  /check     — 连续性检查（默认 DeepSeek，config.CHECK_PROVIDER）
  /outline [N] — 续章剧情灵感，默认后续 3 章（config.OUTLINE_PROVIDER）
  /patch     — 在 characters.md 末尾追加设定补充
  /heartbeat — 开关智能心跳（续命缓存，仅 kie）
  /provider  — 切换主力写作提供商（/summary /check 独立配置）
  /cost      — 显示累计 API 费用
  /new       — 清空对话历史（保留文档缓存）
  /save      — 将未写入的 AI 正文补存到章节 + 保存会话
  /undo      — 撤销上一次自动写入章节的正文
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
    out_cfg = config.get_provider_config(config.OUTLINE_PROVIDER)
    print("=== 小说写作助手 ===")
    print(f"🔌 主力写作：{cfg['name']}（{cfg['model']}）")
    print(
        f"📋 /summary → {sum_cfg['name']}  |  /check → {chk_cfg['name']}  |  "
        f"/outline → {out_cfg['name']}"
    )

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
    init_data_dirs()
    state.total_cost = load_total_cost()
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
            elif cmd == "/outline":
                n = 3
                if arg.strip().isdigit():
                    n = int(arg.strip())
                do_outline(n)
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
            elif cmd == "/undo":
                do_undo()
            elif cmd == "/restore":
                do_restore()
            else:
                print(f"未知命令：{cmd}，输入 /help 查看帮助")
        else:
            do_writing(user_input)


if __name__ == "__main__":
    main()
