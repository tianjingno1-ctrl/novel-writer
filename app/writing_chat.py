# Gate/CLI 续写主链：组消息、调 LLM（含 stream）、回复后决定是否写入章节；`/api/chat/stream` 走这里。
"""写作对话主链（P3-4d）：prepare/finalize/stream + 回复后章节保存。"""

from __future__ import annotations

import json

from infra.console import safe_print

import infra.config as config
from core.data import novel_data
from app import chapter_io as ch
from core import llm
from app import writing_session as ws
from app.factories import invalidate_chapter_injection
from infra.state import state
from core.llm import APIError, CallOptions, TokenUsage, complete, get_client, reset_client, stream
from summarizer import WRITING_INSTRUCTION

CHAPTER_REGENERATE_INSTRUCTION = (
    "根据 plan.json 中本章的规划（场景、Beat、钩子、字数目标），"
    "从零重写本章正文全文。只输出完整章节正文，覆盖旧稿；"
    "不要讨论、不要只写片段、不要在旧稿后追加内容。"
)


def _begin_chapter_regenerate(chapter_num: int | None) -> dict:
    """整章重写：清空会话与章节正文占位，后续 stream 走 replace 写盘。"""
    write_num = ch.resolve_write_chapter_num(chapter_num)
    reset_r = ch.reset_chapter_for_regenerate(write_num)
    if not reset_r.get("ok"):
        return reset_r
    state.conversation_history.clear()
    state.appended_indices.clear()
    state.session_includes_chapter = False
    state.last_injected_chapter_num = 0
    state.write_chapter_num = write_num
    return {
        "ok": True,
        "write_chapter_num": write_num,
        "instruction": CHAPTER_REGENERATE_INSTRUCTION,
    }


def _clear_assistant_appended_indices() -> None:
    for i, msg in enumerate(state.conversation_history):
        if msg["role"] == "assistant":
            state.appended_indices.discard(i)


def save_chapter_after_reply(
    reply: str,
    msg_index: int,
    *,
    write_chapter_num: int | None = None,
    instruction: str = "",
) -> dict | None:
    """AI 回复后自动保存到目标章节。"""
    if not ch.should_append_to_chapter(reply):
        if not config.AUTO_APPEND_CHAPTER:
            return None
        safe_print("💡 本条为讨论/说明，未写入章节（如需保存请手动编辑章节文件）")
        return None

    if not config.AUTO_APPEND_CHAPTER:
        pending = ch.count_unsaved_chapter_turns()
        safe_print(f"💡 本条正文尚未写入章节，输入 /save 保存（待保存 {pending} 条）")
        return None

    chapter_num, chapter_path = ch.get_or_create_write_chapter(write_chapter_num)
    mode = ch.instruction_save_mode(instruction)
    if mode == "append":
        chars, title = ch.append_to_chapter(
            reply, chapter_path, msg_index=msg_index, chapter_num=chapter_num
        )
        if chars <= 0:
            safe_print("💡 本条回复无可用正文，未写入章节")
            return None
        state.appended_indices.add(msg_index)
        title_note = f" · 《{title}》" if title else ""
        safe_print(
            f"💾 已追加到 data/chapters/ch{chapter_num:03d}.md{title_note}（+{chars} 字）"
        )
        if not title:
            title = ch.sync_chapter_title_from_file(chapter_num)
        invalidate_chapter_injection(chapter_num)
        return {"mode": "append", "title": title, "chapter_num": chapter_num}

    chars, title = ch.replace_chapter_content(
        reply, chapter_path, chapter_num, msg_index=msg_index
    )
    if chars <= 0:
        safe_print("💡 本条回复无可用正文，未写入章节")
        return None
    _clear_assistant_appended_indices()
    state.appended_indices.add(msg_index)
    title_note = f" · 《{title}》" if title else ""
    safe_print(
        f"💾 已覆盖保存到 data/chapters/ch{chapter_num:03d}.md{title_note}（{chars} 字）"
    )
    if not title:
        title = ch.sync_chapter_title_from_file(chapter_num)
    invalidate_chapter_injection(chapter_num)
    return {"mode": "replace", "title": title, "chapter_num": chapter_num}


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
    reply = ch.sanitize_chapter_text(reply)
    state.conversation_history.append({"role": "assistant", "content": reply})
    msg_index = len(state.conversation_history) - 1
    save_info = save_chapter_after_reply(
        reply,
        msg_index,
        write_chapter_num=write_chapter_num,
        instruction=instruction,
    )
    ws.save_session("auto", silent=True)

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
        **llm.get_last_call_info(),
    }


def _sync_writing_session_for_chapter(write_num: int) -> None:
    """切章时清会话；仅章号变化时同步 plan.active_scene_id。"""
    prev = state.last_injected_chapter_num or state.write_chapter_num
    if write_num != prev and (
        state.conversation_history or state.last_injected_chapter_num
    ):
        ws.reset_conversation_for_chapter(write_num)
    else:
        state.write_chapter_num = write_num
        if write_num != state.last_injected_chapter_num:
            state.session_includes_chapter = False
    if write_num != state.last_synced_active_scene_chapter:
        novel_data.set_active_scene_for_chapter(write_num)
        state.last_synced_active_scene_chapter = write_num


def _prepare_writing_turn(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
) -> dict:
    """追加用户消息并构建 API 请求上下文。"""
    write_num = ch.resolve_write_chapter_num(chapter_num, scene_id)
    _sync_writing_session_for_chapter(write_num)

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

    injection_snapshot = {
        "session_includes_chapter": state.session_includes_chapter,
        "last_injected_chapter_num": state.last_injected_chapter_num,
    }

    chapter_content = ch.read_chapter_content(write_num)
    if not chapter_content.strip():
        chapter_content = "（本章尚无正文）"

    prior_block = None
    try:
        from core.data import book_context

        if book_context.is_short_book() and write_num > 1:
            from app import writing_ctx as wctx

            prior_block = wctx.get_prior_chapters_block(
                write_num,
                for_user_message=True,
            )
    except RuntimeError:
        prior_block = None

    injected_this_turn = False
    if not state.session_includes_chapter:
        user_parts = [f"【当前章节：第{write_num}章】", chapter_content]
        if prior_block:
            user_parts.append(f"【已写章节正文（续写参考）】\n{prior_block}")
        user_parts.append(f"【写作指令】\n{full_instruction}")
        user_content = "\n\n".join(user_parts)
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
        "system": llm.build_cached_system(
            WRITING_INSTRUCTION,
            include_scene_context=not beat_text,
            chapter_num=write_num,
        ),
        "messages": llm.prepare_messages_for_context(state.conversation_history),
    }


def writing_chat(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
    *,
    regenerate: bool = False,
) -> dict:
    """Web/API：结构化写作对话，返回 JSON 友好结果。"""
    if regenerate:
        begin = _begin_chapter_regenerate(chapter_num)
        if not begin.get("ok"):
            return begin
        instruction = begin["instruction"]
        chapter_num = begin["write_chapter_num"]
    prep = _prepare_writing_turn(
        instruction, scene_beat, scene_id, chapter_num=chapter_num
    )
    if not prep.get("ok"):
        return prep

    reply = llm.call_api(
        prep["system"],
        prep["messages"],
        node_id="writing.main",
        silent=True,
    )
    if reply is None:
        _rollback_failed_writing_turn(prep)
        info = llm.get_last_call_info()
        return {"ok": False, "error": info.get("error", "API 调用失败")}

    return _finalize_writing_turn(
        reply,
        write_chapter_num=prep["write_chapter_num"],
        instruction=prep.get("full_instruction", prep.get("instruction", "")),
    )


def writing_chat_stream(
    instruction: str,
    scene_beat: str = "",
    scene_id: str = "",
    chapter_num: int | None = None,
    *,
    regenerate: bool = False,
) -> Iterator[str]:
    """流式写作对话，yield JSON 字符串事件（同步 generator）。"""
    if regenerate:
        begin = _begin_chapter_regenerate(chapter_num)
        if not begin.get("ok"):
            yield json.dumps(
                {"type": "error", "message": begin.get("error", "整章重写准备失败")},
                ensure_ascii=False,
            )
            return
        instruction = begin["instruction"]
        chapter_num = begin["write_chapter_num"]
        yield json.dumps(
            {
                "type": "chapter_cleared",
                "chapter_num": chapter_num,
            },
            ensure_ascii=False,
        )
    prep = _prepare_writing_turn(
        instruction, scene_beat, scene_id, chapter_num=chapter_num
    )
    if not prep.get("ok"):
        yield json.dumps({"type": "error", "message": prep["error"]}, ensure_ascii=False)
        return

    from core import model_routing

    pid, _ = model_routing.resolve_for_node("writing.main")
    key_ok = config.is_api_key_configured(pid)
    if not key_ok:
        _rollback_failed_writing_turn(prep)
        cfg = config.get_provider_config(pid)
        err = f"请设置 {cfg['api_key_env']}，或在 .env / config.py 中填写 API Key"
        yield json.dumps({"type": "error", "message": err}, ensure_ascii=False)
        return

    chunks: list[str] = []
    try:
        llm.log_request_context(
            prep["system"],
            prep["messages"],
            tag="写书对话",
            provider=pid,
        )
        with llm._request_lock:
            usage: TokenUsage | None = None
            try:
                stream_opts = CallOptions(
                    max_tokens=config.MAX_TOKENS,
                    provider=pid,
                    node_id="writing.main",
                )
                for chunk in stream(
                    prep["system"],
                    prep["messages"],
                    options=stream_opts,
                ):
                    chunks.append(chunk)
                    yield json.dumps(
                        {"type": "chunk", "text": chunk}, ensure_ascii=False
                    )
                usage = get_client().pop_stream_usage()
            except Exception as stream_exc:
                if chunks or not llm._is_stream_disconnect_error(stream_exc):
                    raise
                reset_client(pid)
                text, usage = complete(
                    prep["system"],
                    prep["messages"],
                    options=stream_opts,
                )
                chunks = [text] if text else []
                if text:
                    yield json.dumps(
                        {"type": "chunk", "text": text}, ensure_ascii=False
                    )
            if usage is not None:
                _, eff_model = model_routing.resolve_for_node("writing.main")
                llm._record_call_usage(usage, pid, model=eff_model)
    except APIError as e:
        _rollback_failed_writing_turn(prep)
        yield json.dumps(
            {"type": "error", "message": llm._api_error_message(e)},
            ensure_ascii=False,
        )
        return
    except Exception as e:
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
