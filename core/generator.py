"""章节生成 / 改稿（单轮 LLM + 写盘，不污染写书对话历史）。"""

from __future__ import annotations

from core import chapters as chapter_text
from core.deps import GeneratorDeps


def _compose_instruction(
    instruction: str,
    *,
    scene_beat: str = "",
) -> str:
    parts: list[str] = []
    if scene_beat.strip():
        parts.append(f"【场景指令 Scene Beat】\n{scene_beat.strip()}")
    if instruction.strip():
        parts.append(instruction.strip())
    return "\n\n".join(parts)


def _run_writing_turn(
    chapter_num: int,
    full_instruction: str,
    *,
    deps: GeneratorDeps,
    api_tag: str,
) -> dict:
    if chapter_num < 1:
        return {"ok": False, "error": "章节号无效"}
    if not full_instruction.strip():
        return {"ok": False, "error": "写作指令不能为空"}

    chapter_content = deps.store.read_chapter(chapter_num)
    if not chapter_content.strip():
        chapter_content = "（本章尚无正文）"

    user_content = (
        f"【当前章节：第{chapter_num}章】\n\n"
        f"{chapter_content}\n\n"
        f"【写作指令】\n{full_instruction}"
    )
    system = deps.llm.build_cached_system(deps.writing_instruction)
    reply = deps.llm.call_api(
        system,
        [{"role": "user", "content": user_content}],
        silent=True,
        tag=api_tag,
    )
    if reply is None:
        return {
            "ok": False,
            "error": deps.llm.get_last_call_info().get("error", "生成失败"),
        }

    title, body = chapter_text.prepare_chapter_body_from_reply(
        reply,
        chapter_num,
        deps.apply_title,
    )
    chapter_text_body = chapter_text.format_chapter_file(chapter_num, body, title=title)
    deps.store.write_chapter(
        chapter_num,
        chapter_text_body,
        append=False,
    )
    deps.invalidate_injection(chapter_num)
    return {
        "ok": True,
        "chapter_num": chapter_num,
        "chars": len(chapter_text_body),
        "chapter_title": title,
        **deps.llm.get_last_call_info(),
    }


def generate_chapter(
    chapter_num: int,
    instruction: str,
    *,
    deps: GeneratorDeps,
    scene_beat: str = "",
) -> dict:
    """按 plan 场景单轮生成章节正文（replace 模式）。"""
    full = _compose_instruction(instruction, scene_beat=scene_beat)
    return _run_writing_turn(
        chapter_num,
        full,
        deps=deps,
        api_tag="批量生成",
    )


def remediate_chapter(
    chapter_num: int,
    instruction: str,
    *,
    deps: GeneratorDeps,
    scene_beat: str = "",
) -> dict:
    """世界闭环改稿：单轮 replace 写回章节。"""
    full = _compose_instruction(instruction, scene_beat=scene_beat)
    return _run_writing_turn(
        chapter_num,
        full,
        deps=deps,
        api_tag="闭环改稿",
    )


def revise_chapter(
    chapter_num: int,
    instruction: str,
    *,
    deps: GeneratorDeps,
) -> dict:
    """单轮改稿（replace 模式）。"""
    return _run_writing_turn(
        chapter_num,
        instruction.strip(),
        deps=deps,
        api_tag="改稿",
    )
