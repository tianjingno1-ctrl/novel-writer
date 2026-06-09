"""写作上下文组装：世界观/人物/概述分层与 Prompt Cache 块。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import infra.config as config
from core.data import novel_data
from infra.state import state

ReadTextFn = Callable[[Path], str]

_paths: BookPaths | None = None
_read_text: ReadTextFn | None = None
_path_resolver: Callable[[str], Path] | None = None

_USER_CHAPTER_BLOCK_RE = re.compile(
    r"^【当前章节：第(\d+)章】\s*\n+(.*?)(?:\n+【写作指令】|\Z)",
    re.DOTALL,
)


@dataclass
class BookPaths:
    """当前书籍相关文件路径（由 book_context 注入，避免散落全局变量）。"""

    world_file: Path
    style_file: Path
    characters_file: Path
    char_static_file: Path
    char_dynamic_file: Path
    char_current_file: Path
    summaries_archive_file: Path
    summaries_recent_file: Path
    summaries_file: Path
    plot_threads_locked_file: Path
    plot_threads_active_file: Path
    plot_threads_file: Path

    @classmethod
    def from_book_context(cls, ctx: object) -> BookPaths:
        return cls(
            world_file=ctx.world_file,
            style_file=ctx.style_file,
            characters_file=ctx.characters_file,
            char_static_file=ctx.char_static_file,
            char_dynamic_file=ctx.char_dynamic_file,
            char_current_file=ctx.char_current_file,
            summaries_archive_file=ctx.summaries_archive_file,
            summaries_recent_file=ctx.summaries_recent_file,
            summaries_file=ctx.summaries_file,
            plot_threads_locked_file=ctx.plot_threads_locked_file,
            plot_threads_active_file=ctx.plot_threads_active_file,
            plot_threads_file=ctx.plot_threads_file,
        )


def install_path_resolver(
    resolver: Callable[[str], Path], read_text: ReadTextFn
) -> None:
    """由 bootstrap 注入路径解析器（测试 patch main.*_FILE 时经 paths.resolved 生效）。"""
    global _path_resolver, _read_text
    _path_resolver = resolver
    _read_text = read_text


def bind(paths: BookPaths, *, read_text: ReadTextFn) -> None:
    global _paths, _read_text
    _paths = paths
    _read_text = read_text


def bind_writing_context() -> None:
    """从 install_path_resolver 注册的解析器同步路径到 bind()。"""
    if _path_resolver is None or _read_text is None:
        return
    bind(
        BookPaths(
            world_file=_path_resolver("WORLD_FILE"),
            style_file=_path_resolver("STYLE_FILE"),
            characters_file=_path_resolver("CHARACTERS_FILE"),
            char_static_file=_path_resolver("CHAR_STATIC_FILE"),
            char_dynamic_file=_path_resolver("CHAR_DYNAMIC_FILE"),
            char_current_file=_path_resolver("CHAR_CURRENT_FILE"),
            summaries_archive_file=_path_resolver("SUMMARIES_ARCHIVE_FILE"),
            summaries_recent_file=_path_resolver("SUMMARIES_RECENT_FILE"),
            summaries_file=_path_resolver("SUMMARIES_FILE"),
            plot_threads_locked_file=_path_resolver("PLOT_THREADS_LOCKED_FILE"),
            plot_threads_active_file=_path_resolver("PLOT_THREADS_ACTIVE_FILE"),
            plot_threads_file=_path_resolver("PLOT_THREADS_FILE"),
        ),
        read_text=_read_text,
    )


def _maybe_bind() -> None:
    global _path_resolver, _read_text
    if _path_resolver is None:
        try:
            from app import paths as book_paths
            from infra import file_utils as bio

            install_path_resolver(book_paths.resolved, bio.read_text)
        except ImportError:
            return
    bind_writing_context()


def get_paths() -> BookPaths:
    if _paths is None:
        raise RuntimeError("写作上下文未绑定路径，请先 init_library() / bind()")
    return _paths


def _rt() -> ReadTextFn:
    if _read_text is None:
        raise RuntimeError("写作上下文未绑定 read_text")
    return _read_text


def _read(path: Path) -> str:
    return _rt()(path)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    n = len(text)
    if cjk > n * 0.35:
        return max(1, int(n / 1.6))
    return max(1, int(n / 4))


def cache_block(text: str) -> dict:
    return {
        "type": "text",
        "text": text,
        "cache_control": {"type": "ephemeral", "ttl": config.CACHE_TTL},
    }


def _read_char_static() -> str:
    p = get_paths()
    text = _read(p.char_static_file).strip()
    if text:
        return text
    return _read(p.char_current_file).strip()


def _read_plot_locked() -> str:
    p = get_paths()
    text = _read(p.plot_threads_locked_file).strip()
    if text:
        return text
    legacy = _read(p.plot_threads_file).strip()
    if "## 已钉死的细节" in legacy:
        start = legacy.find("## 已钉死的细节")
        end = legacy.find("## 未回收")
        if end < 0:
            end = len(legacy)
        return legacy[start:end].strip()
    return ""


def _read_plot_active() -> str:
    p = get_paths()
    text = _read(p.plot_threads_active_file).strip()
    if text:
        return text
    legacy = _read(p.plot_threads_file).strip()
    if "## 未回收" in legacy:
        start = legacy.find("## 未回收")
        return legacy[start:].strip()
    return ""


def read_char_static() -> str:
    return _read_char_static()


def read_plot_locked() -> str:
    return _read_plot_locked()


def read_plot_active() -> str:
    return _read_plot_active()


def get_characters_block() -> str:
    _maybe_bind()
    p = get_paths()
    if config.CONTEXT_MODE == "codex" or novel_data.get_active_codex_ids():
        codex_text = novel_data.format_active_codex_text()
        if codex_text:
            base = f"# 本章相关设定（Codex）\n\n{codex_text}"
        else:
            base = _read(p.characters_file)
    else:
        base = _read(p.characters_file)
    char_static = _read_char_static()
    if char_static:
        base = (
            f"{base.rstrip()}\n\n---\n\n"
            f"# 人物锚点（char_static.md）\n{char_static}"
        )
    return base


def get_stable_archive_block() -> str:
    _maybe_bind()
    p = get_paths()
    parts: list[str] = []
    archive = _read(p.summaries_archive_file).strip()
    if archive:
        parts.append(f"# 章节概述归档（summaries_archive.md）\n{archive}")
    locked = _read_plot_locked()
    if locked:
        parts.append(f"# 已钉死的细节（plot_threads_locked.md）\n{locked}")
    return "\n\n".join(parts)


def collect_dynamic_layer_parts() -> list[dict]:
    _maybe_bind()
    p = get_paths()
    parts: list[dict] = []
    dynamic = _read(p.char_dynamic_file).strip()
    if not dynamic:
        dynamic = _read(p.char_current_file).strip()
    if dynamic:
        parts.append(
            {
                "id": "char_dynamic",
                "label": "char_dynamic",
                "content": f"# 人物动态状态（char_dynamic.md）\n{dynamic}",
            }
        )
    recent = _read(p.summaries_recent_file).strip()
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
    return "\n\n".join(p["content"] for p in collect_dynamic_layer_parts())


def get_char_context_for_check() -> str:
    _maybe_bind()
    p = get_paths()
    static = _read_char_static()
    dynamic = _read(p.char_dynamic_file).strip()
    parts = []
    if static:
        parts.append(f"## 性格锚点（char_static）\n{static}")
    if dynamic:
        parts.append(f"## 当前状态（char_dynamic）\n{dynamic}")
    if not parts:
        legacy = _read(p.char_current_file).strip()
        if legacy:
            parts.append(legacy)
    return "\n\n".join(parts)


def get_summaries_combined() -> str:
    _maybe_bind()
    p = get_paths()
    parts: list[str] = []
    archive = _read(p.summaries_archive_file).strip()
    recent = _read(p.summaries_recent_file).strip()
    if archive:
        parts.append(archive)
    if recent:
        parts.append(recent)
    if parts:
        return "\n\n".join(parts)
    return _read(p.summaries_file).strip()


def get_world_block() -> str:
    _maybe_bind()
    p = get_paths()
    world = _read(p.world_file)
    style = _read(p.style_file).strip()
    if style:
        return f"{world.rstrip()}\n\n---\n\n# 文风锚点（style.md）\n{style}"
    return world


def record_context_debug(
    layers: list[dict],
    *,
    provider: str | None = None,
    messages: list[dict] | None = None,
    tag: str = "",
    summarize_messages: Callable[[list[dict]], list[dict]] | None = None,
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
            "token_estimate": estimate_tokens(content),
            "chars": len(content),
            "content": content,
        }
        children = layer.get("children")
        if children:
            entry["children"] = [
                {
                    **child,
                    "token_estimate": child.get(
                        "token_estimate", estimate_tokens(str(child.get("content", "")))
                    ),
                    "chars": len(str(child.get("content", ""))),
                }
                for child in children
            ]
        debug_layers.append(entry)

    msg_rows: list[dict] = []
    if messages and summarize_messages:
        msg_rows = summarize_messages(messages)
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


def build_cached_system(
    instruction: str,
    provider: str | None = None,
    *,
    include_scene_context: bool = True,
    summarize_messages: Callable[[list[dict]], list[dict]] | None = None,
    messages: list[dict] | None = None,
) -> list[dict] | str:
    _maybe_bind()
    world = get_world_block()
    characters = get_characters_block()
    stable = get_stable_archive_block()
    scene_ctx = ""
    if include_scene_context and config.CONTEXT_MODE in ("beats", "summaries"):
        scene_ctx = novel_data.get_scene_context_text()
    dynamic_parts = collect_dynamic_layer_parts()
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
            "token_estimate": estimate_tokens(instruction),
        }
    ]
    if scene_ctx:
        scene_block = f"# 当前场景\n{scene_ctx}"
        layer4_children.append(
            {
                "id": "scene_beat",
                "label": "Beat + 情绪锚点",
                "content": scene_block,
                "token_estimate": estimate_tokens(scene_block),
            }
        )
    for part in dynamic_parts:
        layer4_children.append(
            {
                "id": part["id"],
                "label": part["label"],
                "content": part["content"],
                "token_estimate": estimate_tokens(part["content"]),
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
    record_context_debug(
        debug_layers,
        provider=provider,
        messages=messages,
        summarize_messages=summarize_messages,
    )

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


def get_latest_chapter() -> tuple[int, Path, str] | None:
    """返回最新章节 (num, path, content)。"""
    _maybe_bind()
    if _path_resolver is None:
        raise RuntimeError("路径解析器未安装")
    from core.chapters import list_chapter_files

    chapters_dir = _path_resolver("CHAPTERS_DIR")
    chapters = list_chapter_files(chapters_dir)
    if not chapters:
        return None
    num, path = chapters[-1]
    return num, path, _read(path)


def count_summaries() -> int:
    combined = get_summaries_combined()
    return len(re.findall(r"【第\d+章", combined))


def _outline_context_ready() -> str | None:
    if get_latest_chapter() is None:
        return "没有找到章节文件"
    if count_summaries() == 0:
        return "请先生成章节概述（/summary 或 Web「生成概述」）"
    return None


def get_last_context_debug() -> dict:
    from core import llm

    if not state.last_context_debug:
        return {
            "ok": False,
            "error": "尚无请求记录，请先发送一次写书对话、自由聊或检查类请求",
        }
    data = dict(state.last_context_debug)
    data["ok"] = True
    data["last_call"] = llm.get_last_call_info()
    return data


def extract_chapter_body_from_user_message(content: str) -> str | None:
    """从首轮用户消息中取出附带的章节正文（不含写作指令）。"""
    m = _USER_CHAPTER_BLOCK_RE.match((content or "").strip())
    if not m:
        return None
    body = m.group(2).strip()
    return body or None


def record_context_debug_bound(
    layers: list[dict],
    *,
    provider: str | None = None,
    messages: list[dict] | None = None,
    tag: str = "",
) -> None:
    from core import llm

    _maybe_bind()
    record_context_debug(
        layers,
        provider=provider,
        messages=messages,
        tag=tag,
        summarize_messages=llm._summarize_messages,
    )
