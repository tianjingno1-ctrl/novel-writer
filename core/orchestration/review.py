"""审阅工具编排：章号解析 + 调用 core.reviewer（经 AppContext 组装 deps）。"""

from __future__ import annotations

from core import reviewer as quality_reviewer
from core.deps import ReviewerDeps
from core.orchestration._chapter_work import chapter_work_from_num
from core.schemas.service import ChapterWork

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.context import AppContext


def build_reviewer_deps(ctx: AppContext) -> ReviewerDeps:
    """从 AppContext 取 ReviewerDeps（不从 main 直接取）。"""
    return ctx.reviewer_deps


def _resolve_work(
    chapter_num: int | None,
    ctx: AppContext,
) -> tuple[ChapterWork | None, dict | None]:
    return chapter_work_from_num(chapter_num, ctx.resolve_chapter)


def run_summary(chapter_num: int | None, ctx: AppContext) -> dict:
    work, err = _resolve_work(chapter_num, ctx)
    if err:
        return err
    return quality_reviewer.run_summary(work, build_reviewer_deps(ctx))


def run_check(
    chapter_num: int | None,
    scope: str,
    ctx: AppContext,
) -> dict:
    work, err = _resolve_work(chapter_num, ctx)
    if err:
        return err
    return quality_reviewer.run_check(work, scope, build_reviewer_deps(ctx))


def run_character_drift(chapter_num: int | None, ctx: object) -> dict:
    work, err = _resolve_work(chapter_num, ctx)
    if err:
        return err
    return quality_reviewer.run_character_drift(work, build_reviewer_deps(ctx))


def run_detail_extract(
    chapter_num: int | None,
    ctx: AppContext,
    *,
    auto_append: bool = True,
) -> dict:
    work, err = _resolve_work(chapter_num, ctx)
    if err:
        return err
    return quality_reviewer.run_detail_extract(
        work, build_reviewer_deps(ctx), auto_append=auto_append
    )


def run_repetition_check(
    chapter_num: int | None,
    scope: str,
    ctx: AppContext,
) -> dict:
    work, err = _resolve_work(chapter_num, ctx)
    if err:
        return err
    return quality_reviewer.run_repetition_check(
        work, scope, build_reviewer_deps(ctx)
    )


def run_pacing_check(ctx: object) -> dict:
    return quality_reviewer.run_pacing_check(build_reviewer_deps(ctx))


def run_observe(
    chapter_num: int | None,
    ctx: AppContext,
    *,
    auto_apply: bool = True,
) -> dict:
    work, err = _resolve_work(chapter_num, ctx)
    if err:
        return err
    return quality_reviewer.run_observe(
        work, build_reviewer_deps(ctx), auto_apply=auto_apply
    )


def run_reader_review(
    chapter_num: int | None,
    scope: str,
    ctx: AppContext,
) -> dict:
    work, err = _resolve_work(chapter_num, ctx)
    if err:
        return err
    return quality_reviewer.run_reader_review(work, scope, build_reviewer_deps(ctx))


def run_editor_review(
    chapter_num: int | None,
    scope: str,
    ctx: AppContext,
) -> dict:
    work, err = _resolve_work(chapter_num, ctx)
    if err:
        return err
    return quality_reviewer.run_editor_review(work, scope, build_reviewer_deps(ctx))


def format_quality_full_report(
    chapter_num: int,
    scope: str,
    *,
    style_text: str = "",
    continuity_text: str = "",
    character_text: str = "",
    pacing_text: str = "",
    reader_text: str = "",
    editor_text: str = "",
) -> str:
    label = quality_reviewer.scope_label(scope, chapter_num)
    lines = [f"# 质量审阅 · {label} · 第{chapter_num}章锚点", ""]
    sections = [
        ("文字层 · 套话", style_text),
        ("设定层 · 连续性", continuity_text),
        ("设定层 · 人物", character_text),
        ("叙事层 · 爽点", pacing_text),
        ("感受层 · 读者", reader_text),
        ("感受层 · 编辑", editor_text),
    ]
    for title, text in sections:
        if not (text or "").strip():
            continue
        lines.append(f"## {title}\n{text.strip()}\n")
    if len(lines) <= 2:
        lines.append("（未产生任何审阅内容）")
    return "\n".join(lines)


def run_quality_full_review(
    chapter_num: int | None,
    ctx: AppContext,
    *,
    scope: str = "current",
    run_pacing: bool = True,
    run_reader: bool = True,
    run_editor: bool = True,
) -> dict:
    """只读质量审阅：套话 + 连续性 + 人物 + 可选爽点/读者/编辑，不写档案。"""
    if scope not in ("current", "recent3", "all"):
        return {"ok": False, "error": "scope 必须是 current / recent3 / all"}
    work, err = _resolve_work(chapter_num, ctx)
    if err:
        return err
    num = work.ref.num
    scope_label = quality_reviewer.scope_label(scope, num)
    errors: list[str] = []

    style_text = ""
    style_r = run_repetition_check(num, scope, ctx)
    if style_r.get("ok"):
        style_text = style_r.get("reply") or ""
    else:
        errors.append(f"套话：{style_r.get('error', '失败')}")

    continuity_text = ""
    cont_r = run_check(num, scope, ctx)
    if cont_r.get("ok"):
        continuity_text = cont_r.get("reply") or ""
    else:
        errors.append(f"连续性：{cont_r.get('error', '失败')}")

    character_text = ""
    if scope == "current":
        char_r = run_character_drift(num, ctx)
        if char_r.get("ok"):
            character_text = char_r.get("reply") or ""
        else:
            errors.append(f"人物：{char_r.get('error', '失败')}")
    else:
        character_text = (
            "（跨章/全书范围下人物检查以锚点章正文为准，请用「当前章」范围或单独点「人物」）"
        )

    pacing_text = ""
    if run_pacing:
        pace_r = run_pacing_check(ctx)
        if pace_r.get("ok"):
            pacing_text = pace_r.get("reply") or ""
        else:
            errors.append(f"爽点：{pace_r.get('error', '失败')}")

    reader_text = ""
    if run_reader:
        reader_r = run_reader_review(num, scope, ctx)
        if reader_r.get("ok"):
            reader_text = reader_r.get("reply") or ""
        else:
            errors.append(f"读者：{reader_r.get('error', '失败')}")

    editor_text = ""
    if run_editor:
        editor_r = run_editor_review(num, scope, ctx)
        if editor_r.get("ok"):
            editor_text = editor_r.get("reply") or ""
        else:
            errors.append(f"编辑：{editor_r.get('error', '失败')}")

    report = format_quality_full_report(
        num,
        scope,
        style_text=style_text,
        continuity_text=continuity_text,
        character_text=character_text,
        pacing_text=pacing_text,
        reader_text=reader_text,
        editor_text=editor_text,
    )
    ok = bool(
        style_text
        or continuity_text
        or character_text
        or pacing_text
        or reader_text
        or editor_text
    )
    deps = build_reviewer_deps(ctx)
    log_id = deps.quality.log_entry(
        "quality_full",
        num,
        report,
        summary=f"一键全查 · {scope_label}",
        persisted=False,
        extra={"scope": scope, "errors": errors},
    )
    return {
        "ok": ok,
        "reply": report,
        "chapter_num": num,
        "scope": scope,
        "scope_label": scope_label,
        "errors": errors,
        "log_id": log_id,
        **deps.llm.get_last_call_info(),
    }


def run_deconstruct(
    source_text: str,
    ctx: AppContext,
    *,
    source_label: str = "",
    include_book_context: bool = True,
) -> dict:
    from core.data import novel_data

    store = ctx.store
    p = store.paths
    book_title = ""
    world_excerpt = ""
    style_excerpt = ""
    if include_book_context:
        project = novel_data.get_project_meta()
        book_title = (project.get("title") or "").strip()
        world_excerpt = store.read(p.world_file).strip()[:5000]
        style_excerpt = store.read(p.style_file).strip()[:3000]
    return quality_reviewer.run_deconstruct(
        source_text,
        ctx.reviewer_deps,
        source_label=source_label,
        include_book_context=include_book_context,
        book_title=book_title,
        world_excerpt=world_excerpt,
        style_excerpt=style_excerpt,
    )
