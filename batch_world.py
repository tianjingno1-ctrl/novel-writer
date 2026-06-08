"""世界批次：分段审阅 + 合并报告 + 批量定稿（控制上下文体积与输出截断）。"""

from __future__ import annotations

import re
from typing import Callable

import config
import novel_data
from summarizer import (
    CROSS_CHAPTER_CONTINUITY_SYSTEM,
    WORLD_BATCH_CHUNK_REVIEW_SYSTEM,
    WORLD_BATCH_MERGE_SYSTEM,
    build_cross_chapter_check_user_message,
    build_world_batch_chunk_user_message,
    build_world_batch_merge_user_message,
    truncate_context_tail,
)

_CHAPTER_SPAN_RE = re.compile(r"第(\d+)\s*[–\-—~～]\s*(\d+)\s*章")
_CHAPTER_SINGLE_RE = re.compile(r"第(\d+)\s*章")
_PREVIEW_HEAD_CHARS = 520


def estimate_tokens(text: str) -> int:
    """粗估 token（与 main._estimate_tokens 一致：中文为主约 1.6 字/token）。"""
    if not text:
        return 0
    body = text or ""
    cjk = sum(1 for c in body if "\u4e00" <= c <= "\u9fff")
    n = len(body)
    if cjk > n * 0.35:
        return max(1, int(n / 1.6))
    return max(1, int(n / 4))


def _system_text_len(system) -> int:
    if isinstance(system, list):
        return sum(len(str(b.get("content", ""))) for b in system)
    return len(system or "")


def parse_chapter_spans(text: str) -> list[tuple[int, int]]:
    """从场景 summary/beat 等文本解析章号区间。"""
    spans: list[tuple[int, int]] = []
    body = text or ""
    for m in _CHAPTER_SPAN_RE.finditer(body):
        a, b = int(m.group(1)), int(m.group(2))
        if a > b:
            a, b = b, a
        spans.append((a, b))
    for m in _CHAPTER_SINGLE_RE.finditer(body):
        n = int(m.group(1))
        if not any(a <= n <= b for a, b in spans):
            spans.append((n, n))
    return spans


def infer_world_chapter_range(*, default_to: int = 15) -> tuple[int, int]:
    """从 project.active_world 或 plan 场景推断世界章节范围。"""
    project = novel_data.get_project_meta()
    aw = project.get("active_world")
    if isinstance(aw, dict):
        try:
            cf = int(aw.get("chapter_from") or 0)
            ct = int(aw.get("chapter_to") or 0)
            if cf >= 1 and ct >= cf:
                return cf, ct
        except (TypeError, ValueError):
            pass

    max_ch = 0
    plan = novel_data.load_plan()
    for ch in plan.get("chapters", {}).values():
        for scene in ch.get("scenes") or []:
            for field in ("summary", "beat", "title"):
                for a, b in parse_chapter_spans(str(scene.get(field) or "")):
                    max_ch = max(max_ch, b)
    if max_ch >= 1:
        return 1, max_ch
    return 1, default_to


def _scene_chapter_span(scene: dict) -> tuple[int, int] | None:
    """从场景 summary/beat/title 合并推断章号区间。"""
    lo: int | None = None
    hi: int | None = None
    for field in ("summary", "beat", "title"):
        for a, b in parse_chapter_spans(str(scene.get(field) or "")):
            lo = a if lo is None else min(lo, a)
            hi = b if hi is None else max(hi, b)
    if lo is None or hi is None:
        return None
    return lo, hi


def resolve_beat_for_prose_chapter(chapter_num: int) -> dict | None:
    """将正文章号映射到 plan 场景 Beat（支持「第1-2章」跨章 Beat）。"""
    if chapter_num < 1:
        return None
    plan = novel_data.load_plan()
    matches: list[tuple[int, int, dict]] = []
    for ch_data in plan.get("chapters", {}).values():
        for scene in ch_data.get("scenes") or []:
            span = _scene_chapter_span(scene)
            if not span:
                continue
            a, b = span
            if a <= chapter_num <= b:
                matches.append((a, b, scene))
    if not matches:
        key = str(chapter_num)
        ch = plan.get("chapters", {}).get(key) or {}
        scenes = ch.get("scenes") or []
        if scenes:
            scene = scenes[0]
            beat = (scene.get("beat") or "").strip()
            if beat:
                return {
                    "scene_id": scene.get("id") or "",
                    "scene_title": scene.get("title") or "",
                    "beat": beat,
                    "pace": scene.get("pace") or "",
                    "span_from": chapter_num,
                    "span_to": chapter_num,
                    "chapter_index_in_span": 1,
                    "span_chapters": 1,
                }
        return None
    matches.sort(key=lambda x: (x[1] - x[0], x[0]))
    span_from, span_to, scene = matches[0]
    beat = (scene.get("beat") or "").strip()
    if not beat:
        return None
    return {
        "scene_id": scene.get("id") or "",
        "scene_title": scene.get("title") or "",
        "beat": beat,
        "pace": scene.get("pace") or "",
        "span_from": span_from,
        "span_to": span_to,
        "chapter_index_in_span": chapter_num - span_from + 1,
        "span_chapters": span_to - span_from + 1,
    }


def chapters_with_beats(chapter_from: int, chapter_to: int) -> list[int]:
    return [
        n
        for n in range(chapter_from, chapter_to + 1)
        if resolve_beat_for_prose_chapter(n)
    ]


def get_world_batch_status(*, read_chapter) -> dict:
    """返回当前世界批次元数据（供 Web 展示）。"""
    project = novel_data.get_project_meta()
    chapter_from, chapter_to = infer_world_chapter_range()
    label = (project.get("world_label") or "").strip() or "当前世界"

    written: list[int] = []
    for num in range(chapter_from, chapter_to + 1):
        text = (read_chapter(num) or "").strip()
        if text:
            written.append(num)

    written_from = written[0] if written else 0
    written_to = written[-1] if written else 0
    beat_nums = chapters_with_beats(chapter_from, chapter_to)
    return {
        "ok": True,
        "label": label,
        "chapter_from": chapter_from,
        "chapter_to": chapter_to,
        "written_chapters": written,
        "written_count": len(written),
        "written_from": written_from,
        "written_to": written_to,
        "world_in_progress": bool(written) and written_to < chapter_to,
        "complete": bool(written) and written_to >= chapter_to,
        "beats_chapters": beat_nums,
        "beats_count": len(beat_nums),
        "chunk_size": config.BATCH_REVIEW_CHUNK_CHAPTERS,
        "input_max_chars": config.BATCH_REVIEW_INPUT_MAX_CHARS,
        "chapter_max_chars": config.BATCH_REVIEW_CHAPTER_MAX_CHARS,
    }


def iter_chapter_chunks(
    chapter_from: int, chapter_to: int, *, chunk_size: int | None = None
) -> list[tuple[int, int]]:
    size = max(1, chunk_size or config.BATCH_REVIEW_CHUNK_CHAPTERS)
    chunks: list[tuple[int, int]] = []
    start = chapter_from
    while start <= chapter_to:
        end = min(chapter_to, start + size - 1)
        chunks.append((start, end))
        start = end + 1
    return chunks


def _truncate_chapter_body(content: str, max_chars: int) -> tuple[str, bool]:
    body = (content or "").strip()
    if len(body) <= max_chars:
        return body, False
    head = max_chars // 2
    tail = max_chars - head - 40
    return (
        body[:head]
        + "\n\n…（中段已省略，因单章过长）…\n\n"
        + body[-tail:],
        True,
    )


def build_chapters_text_block(
    chapter_nums: list[int],
    read_chapter,
    *,
    max_total_chars: int | None = None,
    max_chapter_chars: int | None = None,
) -> tuple[str, bool, list[int]]:
    """拼接多章正文，返回 (文本, 是否发生截断, 实际包含的章号)。"""
    total_limit = max_total_chars or config.BATCH_REVIEW_INPUT_MAX_CHARS
    ch_limit = max_chapter_chars or config.BATCH_REVIEW_CHAPTER_MAX_CHARS
    parts: list[str] = []
    used: list[int] = []
    truncated = False
    budget = total_limit

    for num in chapter_nums:
        raw = (read_chapter(num) or "").strip()
        if not raw:
            continue
        piece, ch_trunc = _truncate_chapter_body(raw, ch_limit)
        if ch_trunc:
            truncated = True
        block = f"## 第{num}章\n{piece}"
        if len(block) > budget:
            if not parts:
                parts.append(block[:budget] + "\n…（本段输入已达上限，后续章节未纳入本段 API 输入）")
                used.append(num)
                truncated = True
            break
        parts.append(block)
        used.append(num)
        budget -= len(block) + 2

    return "\n\n".join(parts), truncated, used


def _call_was_truncated(last_call_info: dict) -> bool:
    return bool(last_call_info.get("output_truncated"))


def _trim_for_merge(text: str, max_chars: int = 7000) -> str:
    body = (text or "").strip()
    if len(body) <= max_chars:
        return body
    return body[: max_chars - 20] + "\n…（分段报告已截断供合并）"


def _resolve_world_review_scope(
    read_chapter,
    chapter_from: int | None,
    chapter_to: int | None,
) -> dict:
    status = get_world_batch_status(read_chapter=read_chapter)
    cf = chapter_from if chapter_from is not None else status["chapter_from"]
    ct = chapter_to if chapter_to is not None else status["chapter_to"]
    if cf < 1 or ct < cf:
        return {"ok": False, "error": "章节范围无效"}
    written = [n for n in range(cf, ct + 1) if (read_chapter(n) or "").strip()]
    if not written:
        return {"ok": False, "error": f"第{cf}–{ct}章范围内没有正文，无法审阅"}
    return {
        "ok": True,
        "status": status,
        "chapter_from": cf,
        "chapter_to": ct,
        "written": written,
        "written_from": written[0],
        "written_to": written[-1],
        "label": status["label"],
        "world_in_progress": written[-1] < ct,
    }


def build_world_batch_review_plan(
    *,
    read_chapter,
    read_text,
    get_char_context_for_check,
    build_cached_system,
    summaries_for_scope_fn: Callable[[int, str], str],
    cross_chapter_user_message_fn: Callable[..., str],
    world_file,
    characters_file,
    plot_locked_file,
    plot_active_file,
    chapter_from: int | None = None,
    chapter_to: int | None = None,
) -> dict:
    """构建世界审阅发送计划（不调用 API），供预览与执行共用。"""
    scope = _resolve_world_review_scope(read_chapter, chapter_from, chapter_to)
    if not scope.get("ok"):
        return scope

    cf = scope["chapter_from"]
    ct = scope["chapter_to"]
    written = scope["written"]
    w_from, w_to = scope["written_from"], scope["written_to"]
    label = scope["label"]
    pid = config.CHECK_PROVIDER

    world = read_text(world_file)
    characters = read_text(characters_file)
    char_current = get_char_context_for_check()
    plot_locked = read_text(plot_locked_file)
    plot_active = read_text(plot_active_file)

    system_chunk = build_cached_system(WORLD_BATCH_CHUNK_REVIEW_SYSTEM, provider=pid)
    system_cross = build_cached_system(CROSS_CHAPTER_CONTINUITY_SYSTEM, provider=pid)
    system_merge = build_cached_system(WORLD_BATCH_MERGE_SYSTEM, provider=pid)

    calls: list[dict] = []
    total_prose_chars = 0
    any_input_truncated = False

    for chunk_from, chunk_to in iter_chapter_chunks(w_from, w_to):
        nums = [n for n in range(chunk_from, chunk_to + 1) if n in written]
        if not nums:
            continue
        chapters_text, inp_trunc, used_nums = build_chapters_text_block(nums, read_chapter)
        if inp_trunc:
            any_input_truncated = True
        if not chapters_text.strip():
            continue

        ch_char_counts = {
            str(n): len((read_chapter(n) or "").strip()) for n in used_nums
        }
        prose_chars = len(chapters_text)
        total_prose_chars += prose_chars

        user_msg = build_world_batch_chunk_user_message(
            label,
            cf,
            ct,
            chunk_from,
            chunk_to,
            world,
            characters,
            char_current,
            plot_locked,
            plot_active,
            chapters_text,
            input_truncated=inp_trunc,
        )
        sys_len = _system_text_len(system_chunk)
        user_len = len(user_msg)
        sys_text = (
            "".join(b.get("content", "") for b in system_chunk)
            if isinstance(system_chunk, list)
            else str(system_chunk or "")
        )
        est_in = estimate_tokens(user_msg) + estimate_tokens(sys_text)

        archive_chars = user_len - prose_chars
        calls.append(
            {
                "kind": "chunk_review",
                "tag": f"世界审阅·第{chunk_from}-{chunk_to}段",
                "label": f"分段审阅 · 第{chunk_from}–{chunk_to}章",
                "chapters": used_nums,
                "chapter_char_counts": ch_char_counts,
                "prose_chars": prose_chars,
                "archive_chars": max(0, archive_chars),
                "user_chars": user_len,
                "system_chars": sys_len,
                "est_input_tokens": est_in,
                "max_output_tokens": config.BATCH_REVIEW_MAX_TOKENS,
                "est_output_tokens_typical": config.BATCH_REVIEW_TYPICAL_CHUNK_OUTPUT,
                "input_truncated": inp_trunc,
                "chapters_dropped": [n for n in nums if n not in used_nums],
                "payload_parts": [
                    "世界观 world.md",
                    "人物设定 characters.md",
                    "人物当前 char_static + char_dynamic",
                    "细节钉子 plot_threads_locked",
                    "未回收伏笔 plot_threads_active",
                    f"正文 第{used_nums[0]}–{used_nums[-1]}章（{prose_chars:,} 字）",
                ],
                "user_preview_head": user_msg[:_PREVIEW_HEAD_CHARS],
                "user_message": user_msg,
                "system": system_chunk,
                "execute": True,
            }
        )

    scope_label = f"第{w_from}–{w_to}章"
    summaries_slice = summaries_for_scope_fn(w_to, "all")
    cross_user = cross_chapter_user_message_fn(
        world,
        characters,
        char_current,
        summaries_slice,
        plot_locked,
        plot_active,
        f"{label} · {scope_label}",
        w_to,
        read_chapter(w_to) or "",
    )
    cross_sys_len = _system_text_len(system_cross)
    cross_user_len = len(cross_user)
    cross_sys_text = (
        "".join(b.get("content", "") for b in system_cross)
        if isinstance(system_cross, list)
        else str(system_cross or "")
    )
    cross_est_in = estimate_tokens(cross_user) + estimate_tokens(cross_sys_text)
    calls.append(
        {
            "kind": "cross_continuity",
            "tag": "世界审阅·跨章连续性",
            "label": "跨章连续性",
            "chapters": [w_to],
            "prose_chars": len(read_chapter(w_to) or ""),
            "archive_chars": cross_user_len - len(summaries_slice),
            "user_chars": cross_user_len,
            "system_chars": cross_sys_len,
            "est_input_tokens": cross_est_in,
            "max_output_tokens": config.BATCH_REVIEW_MAX_TOKENS,
            "est_output_tokens_typical": config.BATCH_REVIEW_TYPICAL_CROSS_OUTPUT,
            "input_truncated": False,
            "payload_parts": [
                "世界观 / 人物 / 人物当前",
                f"范围内概述 summaries（{len(summaries_slice):,} 字）",
                "plot_threads_locked / active",
                f"锚点章正文 第{w_to}章",
            ],
            "user_preview_head": cross_user[:_PREVIEW_HEAD_CHARS],
            "user_message": cross_user,
            "system": system_cross,
            "execute": True,
        }
    )

    # 合并步：输入为分段报告占位（按最大典型输出估算体积）
    chunk_count = sum(1 for c in calls if c["kind"] == "chunk_review")
    merge_body_est_chars = chunk_count * min(
        3500, config.BATCH_REVIEW_TYPICAL_CHUNK_OUTPUT * 2
    ) + len(cross_user[:2000])
    merge_user_est = build_world_batch_merge_user_message(
        label,
        cf,
        ct,
        w_from,
        w_to,
        "（发送前预览：合并步将使用各分段审阅结果 + 跨章连续性结果）",
        "（跨章连续性结果）",
        world_in_progress=scope["world_in_progress"],
    )
    merge_user_len = len(merge_user_est)
    merge_sys_text = (
        "".join(b.get("content", "") for b in system_merge)
        if isinstance(system_merge, list)
        else str(system_merge or "")
    )
    merge_est_in = estimate_tokens(merge_user_est) + estimate_tokens(merge_sys_text)
    calls.append(
        {
            "kind": "merge_report",
            "tag": "世界审阅·合并报告",
            "label": "合并总报告",
            "chapters": [],
            "prose_chars": 0,
            "archive_chars": merge_body_est_chars,
            "user_chars": merge_user_len,
            "system_chars": _system_text_len(system_merge),
            "est_input_tokens": merge_est_in,
            "max_output_tokens": config.BATCH_REVIEW_MERGE_MAX_TOKENS,
            "est_output_tokens_typical": config.BATCH_REVIEW_TYPICAL_MERGE_OUTPUT,
            "input_truncated": False,
            "payload_parts": [
                f"各分段审阅结果（约 {chunk_count} 份）",
                "跨章连续性结果",
                "世界元数据（范围 / 是否写满）",
            ],
            "user_preview_head": merge_user_est[:_PREVIEW_HEAD_CHARS],
            "user_message": None,
            "system": system_merge,
            "execute": True,
        }
    )

    exec_calls = [c for c in calls if c.get("execute")]
    total_user_chars = sum(c["user_chars"] for c in exec_calls)
    total_est_input = sum(c["est_input_tokens"] for c in exec_calls)
    total_max_output = sum(c["max_output_tokens"] for c in exec_calls)
    total_typical_output = sum(c["est_output_tokens_typical"] for c in exec_calls)

    return {
        "ok": True,
        "label": label,
        "chapter_from": cf,
        "chapter_to": ct,
        "written_from": w_from,
        "written_to": w_to,
        "written_count": len(written),
        "world_in_progress": scope["world_in_progress"],
        "total_prose_chars": total_prose_chars,
        "total_user_chars": total_user_chars,
        "total_est_input_tokens": total_est_input,
        "total_max_output_tokens": total_max_output,
        "total_typical_output_tokens": total_typical_output,
        "api_call_count": len(exec_calls),
        "input_truncated": any_input_truncated,
        "token_note": (
            "中文粗估 1.6 字/token；实际以提供商计费为准。"
            "五万字正文分 3 段发送时，合计 input 约 5–6 万 token，典型回复约 1–1.2 万 token。"
        ),
        "calls": [
            {k: v for k, v in c.items() if k not in ("user_message", "system")}
            for c in calls
        ],
        "_calls_internal": calls,
    }


def format_review_plan_markdown(plan: dict) -> str:
    """将发送计划格式化为用户可读的预览报告。"""
    if not plan.get("ok"):
        return plan.get("error", "无法生成预览")

    lines = [
        f"# 世界审阅 · 发送预览",
        "",
        f"**{plan['label']}** · 计划第{plan['chapter_from']}–{plan['chapter_to']}章",
        f"本次正文：第{plan['written_from']}–{plan['written_to']}章（{plan['written_count']} 章）",
        f"正文合计约 **{plan['total_prose_chars']:,} 字**",
        "",
        "## 合计（发送前估算）",
        f"- API 次数：**{plan['api_call_count']}** 次（串行）",
        f"- 发送内容合计：**{plan['total_user_chars']:,} 字**（user 消息，不含 system 缓存块）",
        f"- 估算 input tokens：**≈{plan['total_est_input_tokens']:,}**",
        f"- 典型回复 tokens：**≈{plan['total_typical_output_tokens']:,}**"
        f"（上限 {plan['total_max_output_tokens']:,}）",
        "",
        f"> {plan.get('token_note', '')}",
        "",
    ]
    if plan.get("input_truncated"):
        lines.append("> ⚠️ 部分章节正文将在发送前截断（见各段说明）\n")

    for i, call in enumerate(plan.get("calls") or [], 1):
        lines.append(f"## 第 {i} 次 · {call['label']}")
        lines.append(f"- 标签：`{call['tag']}`")
        if call.get("chapters"):
            cc = call.get("chapter_char_counts") or {}
            parts = []
            for n in call["chapters"]:
                raw = cc.get(str(n), cc.get(n))
                if isinstance(raw, int):
                    parts.append(f"第{n}章({raw:,}字)")
                else:
                    parts.append(f"第{n}章")
            ch_desc = "、".join(parts)
            lines.append(f"- 章节：{ch_desc}")
        lines.append(f"- 发送包含：{'；'.join(call.get('payload_parts') or [])}")
        lines.append(
            f"- 体积：正文 {call.get('prose_chars', 0):,} 字 + "
            f"档案/其他 {call.get('archive_chars', 0):,} 字 "
            f"= user **{call['user_chars']:,} 字**"
        )
        lines.append(
            f"- 估算 input **≈{call['est_input_tokens']:,} tokens** · "
            f"回复典型 ≈{call['est_output_tokens_typical']:,}（上限 {call['max_output_tokens']:,}）"
        )
        if call.get("input_truncated"):
            lines.append("- ⚠️ 本段输入已截断")
        if call.get("chapters_dropped"):
            lines.append(f"- ⚠️ 未纳入章节：{call['chapters_dropped']}")
        head = (call.get("user_preview_head") or "").strip()
        if head:
            lines.append("")
            lines.append("```")
            lines.append(head)
            if call.get("user_chars", 0) > _PREVIEW_HEAD_CHARS:
                lines.append("…（以下省略，完整内容仅在发送时使用）")
            lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append("确认后将按以上顺序调用 API。完整正文不会在此页重复展示。")
    return "\n".join(lines)


def run_world_batch_review(
    *,
    read_chapter,
    read_text,
    get_char_context_for_check,
    build_cached_system,
    call_api,
    get_last_call_info,
    summaries_for_scope_fn: Callable[[int, str], str],
    cross_chapter_user_message_fn: Callable[..., str],
    quality_log_entry: Callable[..., str],
    world_file,
    characters_file,
    plot_locked_file,
    plot_active_file,
    chapter_from: int | None = None,
    chapter_to: int | None = None,
) -> dict:
    """世界批次审阅：分段读正文 → 跨章连续性 → 合并总报告。"""
    plan = build_world_batch_review_plan(
        read_chapter=read_chapter,
        read_text=read_text,
        get_char_context_for_check=get_char_context_for_check,
        build_cached_system=build_cached_system,
        summaries_for_scope_fn=summaries_for_scope_fn,
        cross_chapter_user_message_fn=cross_chapter_user_message_fn,
        world_file=world_file,
        characters_file=characters_file,
        plot_locked_file=plot_locked_file,
        plot_active_file=plot_active_file,
        chapter_from=chapter_from,
        chapter_to=chapter_to,
    )
    if not plan.get("ok"):
        return plan

    cf = plan["chapter_from"]
    ct = plan["chapter_to"]
    w_from, w_to = plan["written_from"], plan["written_to"]
    label = plan["label"]
    world_in_progress = plan["world_in_progress"]
    written_count = plan["written_count"]
    pid = config.CHECK_PROVIDER

    chunk_reports: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    calls: list[dict] = []
    any_output_truncated = False
    any_input_truncated = bool(plan.get("input_truncated"))
    cross_text = ""
    merged: str | None = None

    for call in plan.get("_calls_internal") or []:
        kind = call.get("kind")
        tag = call.get("tag", "")

        if kind == "chunk_review":
            if call.get("chapters_dropped"):
                warnings.append(
                    f"{call['label']}：输入过长，未纳入章节 {call['chapters_dropped']}"
                )
            reply = call_api(
                call["system"],
                [{"role": "user", "content": call["user_message"]}],
                provider=pid,
                max_tokens=call["max_output_tokens"],
                tag=tag,
                silent=True,
            )
            info = dict(get_last_call_info() or {})
            calls.append(
                {
                    "tag": tag,
                    "cost_usd": info.get("cost") or info.get("cost_usd"),
                    "output_truncated": _call_was_truncated(info),
                    "est_input_tokens": call.get("est_input_tokens"),
                }
            )
            if _call_was_truncated(info):
                any_output_truncated = True
                warnings.append(
                    f"{call['label']} 回复可能被 max_tokens 截断，"
                    f"可提高 NOVEL_BATCH_REVIEW_MAX_TOKENS"
                )
            if reply is None:
                errors.append(f"{call['label']} 失败：{info.get('error', '未知错误')}")
                continue
            chs = call.get("chapters") or []
            if chs:
                chunk_reports.append(
                    f"### 分段 · 第{chs[0]}–{chs[-1]}章\n{reply.strip()}\n"
                )

        elif kind == "cross_continuity" and chunk_reports:
            reply = call_api(
                call["system"],
                [{"role": "user", "content": call["user_message"]}],
                provider=pid,
                max_tokens=call["max_output_tokens"],
                tag=tag,
                silent=True,
            )
            info_c = dict(get_last_call_info() or {})
            calls.append(
                {
                    "tag": "cross_continuity",
                    "cost_usd": info_c.get("cost") or info_c.get("cost_usd"),
                    "output_truncated": _call_was_truncated(info_c),
                    "est_input_tokens": call.get("est_input_tokens"),
                }
            )
            if _call_was_truncated(info_c):
                any_output_truncated = True
                warnings.append("跨章连续性回复可能被截断")
            if reply:
                cross_text = reply.strip()
            else:
                errors.append(
                    f"跨章连续性失败：{info_c.get('error', '未知错误')}"
                )

        elif kind == "merge_report" and chunk_reports:
            merge_body = "\n".join(_trim_for_merge(r) for r in chunk_reports)
            merge_user = build_world_batch_merge_user_message(
                label,
                cf,
                ct,
                w_from,
                w_to,
                merge_body,
                cross_text,
                world_in_progress=world_in_progress,
            )
            merge_reply = call_api(
                call["system"],
                [{"role": "user", "content": merge_user}],
                provider=pid,
                max_tokens=call["max_output_tokens"],
                tag=tag,
                silent=True,
            )
            info_m = dict(get_last_call_info() or {})
            calls.append(
                {
                    "tag": "merge",
                    "cost_usd": info_m.get("cost") or info_m.get("cost_usd"),
                    "output_truncated": _call_was_truncated(info_m),
                    "est_input_tokens": call.get("est_input_tokens"),
                }
            )
            if _call_was_truncated(info_m):
                any_output_truncated = True
                warnings.append(
                    "合并总报告可能被截断，可提高 NOVEL_BATCH_REVIEW_MERGE_MAX_TOKENS"
                )
            if merge_reply:
                merged = merge_reply.strip()
            else:
                errors.append(f"合并报告失败：{info_m.get('error', '未知错误')}")
                merged = _format_fallback_report(
                    label, cf, ct, w_from, w_to, chunk_reports, cross_text, world_in_progress
                )
        else:
            continue

    if not chunk_reports:
        return {"ok": False, "error": "未能生成分段审阅", "errors": errors}

    if merged is None:
        merged = _format_fallback_report(
            label, cf, ct, w_from, w_to, chunk_reports, cross_text, world_in_progress
        )

    meta_lines = [
        f"- 计划范围：第{cf}–{ct}章",
        f"- 本次审阅正文：第{w_from}–{w_to}章（{written_count} 章）",
        f"- 正文合计约 {plan['total_prose_chars']:,} 字",
        f"- 发送估算 input ≈{plan['total_est_input_tokens']:,} tokens（{plan['api_call_count']} 次 API）",
        f"- 分段数：{len(chunk_reports)}（每段最多 {config.BATCH_REVIEW_CHUNK_CHAPTERS} 章）",
        f"- 输入字符上限：{config.BATCH_REVIEW_INPUT_MAX_CHARS} / 章内 {config.BATCH_REVIEW_CHAPTER_MAX_CHARS}",
    ]
    if world_in_progress:
        meta_lines.append(f"- ⚠️ 世界未写满：尚有第{w_to + 1}–{ct}章未出正文")
    if any_input_truncated:
        meta_lines.append("- ⚠️ 部分正文在送入模型前已截断（见各段说明）")
    if any_output_truncated:
        meta_lines.append("- ⚠️ 部分 API 回复可能不完整（见 warnings）")

    report_parts = [
        merged,
        "",
        "---",
        "## 审阅元数据",
        "\n".join(meta_lines),
    ]
    if warnings:
        report_parts.extend(["", "## 系统提示", "\n".join(f"- {w}" for w in warnings)])
    if errors:
        report_parts.extend(["", "## 部分步骤失败", "\n".join(f"- {e}" for e in errors)])
    report = "\n".join(report_parts).strip()

    total_cost = round(
        sum(float(c.get("cost_usd") or 0) for c in calls if c.get("cost_usd") is not None),
        6,
    )
    progress_note = "进行中" if world_in_progress else "完整"
    log_id = quality_log_entry(
        "batch_world_review",
        w_to,
        report,
        summary=f"世界审阅 · {label} · 第{w_from}–{w_to}章 · {progress_note}",
        persisted=False,
        extra={
            "chapter_from": cf,
            "chapter_to": ct,
            "written_from": w_from,
            "written_to": w_to,
            "warnings": warnings,
            "errors": errors,
            "output_truncated": any_output_truncated,
            "input_truncated": any_input_truncated,
            "report_chars": len(report),
        },
    )

    return {
        "ok": bool(merged),
        "partial": bool(errors) and bool(merged),
        "reply": report,
        "log_id": log_id,
        "label": label,
        "chapter_from": cf,
        "chapter_to": ct,
        "written_from": w_from,
        "written_to": w_to,
        "written_count": written_count,
        "world_in_progress": world_in_progress,
        "warnings": warnings,
        "errors": errors,
        "output_truncated": any_output_truncated,
        "input_truncated": any_input_truncated,
        "report_chars": len(report),
        "total_cost_usd": total_cost,
        "calls": calls,
    }


def _format_fallback_report(
    label: str,
    cf: int,
    ct: int,
    w_from: int,
    w_to: int,
    chunk_reports: list[str],
    cross_text: str,
    world_in_progress: bool,
) -> str:
    lines = [
        f"# 世界批次审阅 · {label} · 第{w_from}–{w_to}章",
        "（合并步骤失败，以下为分段审阅原文汇总）",
        "",
    ]
    if world_in_progress:
        lines.append(
            f"> 进行中：世界计划第{cf}–{ct}章，当前仅有第{w_from}–{w_to}章正文\n"
        )
    if cross_text:
        lines.extend(["## 跨章连续性", cross_text, ""])
    lines.append("## 分段审阅")
    lines.extend(chunk_reports)
    return "\n".join(lines)


def run_world_batch_finalize(
    *,
    read_chapter,
    finalize_chapter_fn,
    chapter_from: int | None = None,
    chapter_to: int | None = None,
    skip_empty: bool = True,
    run_pacing_on_last: bool = True,
) -> dict:
    """世界批次定稿：逐章调用既有本章定稿，汇总报告。"""
    status = get_world_batch_status(read_chapter=read_chapter)
    cf = chapter_from if chapter_from is not None else status["chapter_from"]
    ct = chapter_to if chapter_to is not None else status["chapter_to"]
    if cf < 1 or ct < cf:
        return {"ok": False, "error": "章节范围无效"}

    targets: list[int] = []
    for num in range(cf, ct + 1):
        text = (read_chapter(num) or "").strip()
        if not text:
            if skip_empty:
                continue
            return {"ok": False, "error": f"第{num}章正文为空，无法定稿"}
        targets.append(num)

    if not targets:
        return {"ok": False, "error": f"第{cf}–{ct}章范围内没有正文"}

    label = status["label"]
    results: list[dict] = []
    errors: list[str] = []
    last = targets[-1]

    for num in targets:
        pacing = run_pacing_on_last and num == last
        r = finalize_chapter_fn(
            num,
            run_pacing=pacing,
            run_outline=False,
            repetition_scope="current",
        )
        results.append({"chapter_num": num, "result": r})
        if not r.get("ok"):
            errors.append(f"第{num}章：{r.get('error') or '定稿失败'}")

    ok_count = sum(1 for item in results if item["result"].get("ok"))
    partial = ok_count > 0 and len(errors) > 0
    total_cost = round(
        sum(
            float(item["result"].get("total_cost_usd") or 0)
            for item in results
        ),
        6,
    )

    lines = [
        f"# 批量档案同步 · {label}",
        f"范围：第{cf}–{ct}章 · 实际定稿：{len(targets)} 章（第{targets[0]}–{targets[-1]}章）",
        "",
        f"成功 {ok_count}/{len(targets)} 章",
        "",
    ]
    for item in results:
        num = item["chapter_num"]
        r = item["result"]
        mark = "✓" if r.get("ok") else "✗"
        parts = []
        arch = r.get("archive") or {}
        if arch.get("summary", {}).get("ok"):
            parts.append("概述")
        if arch.get("observe", {}).get("applied_count"):
            parts.append(f"观察×{arch['observe']['applied_count']}")
        if arch.get("plot_new_threads", {}).get("appended_count"):
            parts.append(f"伏笔×{arch['plot_new_threads']['appended_count']}")
        q = r.get("quality") or {}
        for key, name in (
            ("continuity", "连续性"),
            ("character_drift", "人物"),
            ("repetition", "套话"),
        ):
            block = q.get(key) or {}
            cnt = block.get("issue_count") or 0
            if cnt:
                parts.append(f"{name}{cnt}条")
        detail = "、".join(parts) if parts else (r.get("error") or "无详情")
        lines.append(f"- {mark} 第{num}章：{detail}")

    if errors:
        lines.extend(["", "## 失败", "\n".join(f"- {e}" for e in errors)])

    if status["world_in_progress"] and targets[-1] < ct:
        lines.extend(
            [
                "",
                f"> ⚠️ 世界尚未写满（计划至第{ct}章），"
                f"本次仅定稿已有正文的第{targets[0]}–{targets[-1]}章。",
            ]
        )

    report = "\n".join(lines)
    return {
        "ok": ok_count > 0,
        "partial": partial,
        "reply": report,
        "label": label,
        "chapter_from": cf,
        "chapter_to": ct,
        "finalized_chapters": targets,
        "ok_count": ok_count,
        "errors": errors,
        "total_cost_usd": total_cost,
        "results": results,
    }
