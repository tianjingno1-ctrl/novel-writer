"""创作工坊编排：对话 LLM + 设定写盘。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infra import state as app_state
import infra.config as config
from core.data import novel_data
from core import workshop as workshop_text

if TYPE_CHECKING:
    from app.context import AppContext

_WORKSHOP_PATH_KEYS = {
    "world": "world_file",
    "characters": "characters_file",
    "style": "style_file",
}


def run_workshop_chat(
    ctx: AppContext,
    module: str,
    messages: list[dict],
    *,
    current_draft: str = "",
) -> dict:
    """创作工坊：自由输入对话 + 增量整理草稿。"""
    mod = (module or "").strip().lower()
    if mod not in workshop_text.WORKSHOP_SYSTEM_PROMPTS:
        return {"ok": False, "error": f"无效 module: {module}"}

    trimmed: list[dict] = []
    for m in messages or []:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            trimmed.append({"role": role, "content": content})
    if not trimmed or trimmed[-1]["role"] != "user":
        return {"ok": False, "error": "需要至少一条用户消息"}

    system = workshop_text.WORKSHOP_SYSTEM_PROMPTS[mod] + workshop_text.WORKSHOP_FORMAT_SUFFIX
    draft_ctx = (current_draft or "").strip()
    if draft_ctx:
        if draft_ctx.startswith("{"):
            system += f"\n\n【当前整理结果（供参考与全量更新）】\n{draft_ctx}"
        else:
            system += f"\n\n【当前草稿（供参考与增量更新）】\n{draft_ctx}"

    llm = ctx.generator_deps.llm
    pid = app_state.state.free_chat_provider or config.PROVIDER
    raw = llm.call_api(
        system,
        trimmed[-20:],
        max_tokens=config.FREE_CHAT_MAX_TOKENS,
        provider=pid,
        tag=f"创作工坊-{mod}",
        silent=True,
    )
    if raw is None:
        return {"ok": False, "error": llm.get_last_call_info().get("error", "工坊对话失败")}

    reply, extract = workshop_text.parse_workshop_response(raw)
    return {
        "ok": True,
        "reply": reply,
        "extract": extract,
        "provider": pid,
        **llm.get_last_call_info(),
    }


def run_workshop_save(
    ctx: AppContext,
    module: str = "world",
    content: str = "",
    *,
    world: str = "",
    characters: str = "",
    beats: list[dict] | None = None,
) -> dict:
    """将工坊整理结果写入设定文件与 plan.json。"""
    mod = (module or "").strip().lower()
    if mod not in workshop_text.WORKSHOP_MODULE_FILES:
        return {"ok": False, "error": f"无效 module: {module}"}

    world_body = (world or "").strip()
    chars_body = (characters or "").strip()
    legacy_body = (content or "").strip()
    if not world_body and legacy_body and mod == "world":
        world_body = legacy_body
    if not chars_body and legacy_body and mod == "characters":
        chars_body = legacy_body
    style_body = legacy_body if mod == "style" and legacy_body else ""

    if not any([world_body, chars_body, style_body, beats]):
        return {"ok": False, "error": "没有可写入的内容"}

    store = ctx.store
    p = store.paths
    written: list[str] = []
    for file_key, body in (
        ("world", world_body),
        ("characters", chars_body),
        ("style", style_body),
    ):
        if not body:
            continue
        path_attr = _WORKSHOP_PATH_KEYS.get(file_key)
        if not path_attr:
            continue
        path = getattr(p, path_attr)
        store.write(path, body, append=False, history_source="workshop_save")
        written.append(file_key)

    plan_updated = False
    if beats:
        plan_updated = novel_data.replace_scenes_from_workshop_beats(beats)

    return {
        "ok": True,
        "written": written,
        "plan_updated": plan_updated,
        "beats_count": len(beats or []),
    }


def run_write_text(ctx: AppContext, key: str, content: str) -> dict:
    """按 key（中文小节名或 module 名）写入设定文件。"""
    file_key = workshop_text.WORKSHOP_WRITE_KEY_MAP.get((key or "").strip())
    if not file_key:
        return {"ok": False, "error": f"无效 key: {key}"}
    return run_workshop_save(ctx, file_key, content)
