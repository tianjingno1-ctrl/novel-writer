"""续章灵感编排：生成 / 读取 / 写入 Plan。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

import config
import novel_data
from core import chapters as chapter_text
from summarizer import OUTLINE_SYSTEM, build_outline_user_message

if TYPE_CHECKING:
    from app.context import AppContext


def _outline_context_ready(ctx: AppContext) -> str | None:
    store = ctx.store
    if not store.list_chapter_nums():
        return "没有找到章节文件"
    snap = store.load_snapshot(for_purpose="check")
    if not snap.summaries_combined or store.count_summaries() == 0:
        return "请先生成章节概述（/summary 或 Web「生成概述」）"
    return None


def run_outline(ctx: AppContext, next_count: int = 3) -> dict:
    err = _outline_context_ready(ctx)
    if err:
        return {"ok": False, "error": err}

    store = ctx.store
    deps = ctx.reviewer_deps
    n = max(1, min(10, next_count))
    snap = store.load_snapshot(for_purpose="check")
    pid = config.OUTLINE_PROVIDER
    system = deps.llm.build_cached_system(OUTLINE_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_outline_user_message(
                snap.world,
                snap.char_context_for_check,
                snap.summaries_combined,
                snap.plot_active,
                n,
            ),
        }
    ]
    reply = deps.llm.call_api(
        system, messages, provider=pid, tag="续章灵感", silent=True
    )
    if reply is None:
        return {
            "ok": False,
            "error": deps.llm.get_last_call_info().get("error", "生成失败"),
        }

    chapter_num = store.latest_chapter_num() or None
    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    outline_path = store.paths.outline_latest_file
    store.write(
        outline_path,
        (
            f"# 续章灵感\n\n生成时间：{saved_at}\n"
            f"当前章节：第{chapter_num or '?'}章\n\n{reply.strip()}\n"
        ),
        append=False,
    )
    suggestions = novel_data.parse_outline_suggestions(reply)
    return {
        "ok": True,
        "reply": reply,
        "saved_at": saved_at,
        "saved_to": str(outline_path),
        "next_count": n,
        "chapter_num": chapter_num,
        "suggestions": suggestions,
        **deps.llm.get_last_call_info(),
    }


def get_outline_latest(ctx: AppContext) -> dict:
    outline_path = ctx.store.paths.outline_latest_file
    if not outline_path.exists():
        return {"ok": True, "content": "", "saved_at": None, "suggestions": []}
    text = ctx.store.read(outline_path)
    body = text
    if text.startswith("# 续章灵感"):
        body = re.sub(
            r"^# 续章灵感\s*\n+(?:生成时间：.*\n)?(?:当前章节：.*\n)?\n?",
            "",
            text,
            count=1,
        )
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


def apply_outline(
    ctx: AppContext,
    offset: int = 1,
    *,
    replace: bool = False,
    reply: str | None = None,
) -> dict:
    store = ctx.store
    outline_path = store.paths.outline_latest_file
    text = (reply or "").strip() or store.read(outline_path)
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

    base_chapter = store.latest_chapter_num()
    if base_chapter <= 0:
        return {"ok": False, "error": "没有找到章节文件"}
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
        ch_path = store.chapter_path(result["chapter_num"])
        if not ch_path.exists():
            ch_path.parent.mkdir(parents=True, exist_ok=True)
            title = (result.get("chapter_title") or "").strip()
            num = result["chapter_num"]
            header = f"# 第{num}章"
            if title and title not in {
                f"第{num}章",
                f"{chapter_text.chapter_cn(num)}章",
            }:
                header = f"{header} · {title}"
            store.write(ch_path, f"{header}\n\n", append=False)
            result["chapter_file_created"] = True
        else:
            result["chapter_file_created"] = False
        result["chapter_file"] = ch_path.name
    return result
