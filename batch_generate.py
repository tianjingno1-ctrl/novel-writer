"""世界批次：按 plan Beat 批量生成章节正文（不污染写书对话历史）。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import batch_world
from core.data import novel_data
from pipeline.checkpoint import (
    JOB_KIND_WORLD_GENERATE,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_RUNNING,
    create_job,
    job_path,
    load_job,
    mark_job_done,
    remaining_targets,
    save_job,
)

PREV_TAIL_CHARS = 2400


def build_chapter_generate_instruction(
    chapter_num: int,
    meta: dict,
    *,
    prev_tail: str = "",
) -> str:
    """构建单章批量生成的写作指令（scene_beat 单独注入）。"""
    title = meta.get("scene_title") or "未命名场景"
    span_from = int(meta.get("span_from") or chapter_num)
    span_to = int(meta.get("span_to") or chapter_num)
    idx = int(meta.get("chapter_index_in_span") or 1)
    parts = [
        f"【批量生成·第{chapter_num}章】",
        f"场景：{title}",
    ]
    if span_from != span_to:
        parts.append(
            f"本 Scene Beat 规划覆盖第 {span_from}–{span_to} 章，"
            f"你正在写该 Beat 的第 {idx}/{span_to - span_from + 1} 章（全书第 {chapter_num} 章）。"
            f"只写本章应覆盖的情节段，勿一次性写完整个 Beat。"
        )
    if prev_tail.strip():
        parts.append(
            "【上一章末尾（须无缝衔接，语气/人称/时态一致）】\n"
            f"{prev_tail.strip()}"
        )
    elif chapter_num <= span_from:
        parts.append(
            "【开篇】这是本段剧情的起始章，前三段须有强钩子，让读者知道在等什么。"
        )
    pace = (meta.get("pace") or "").strip()
    if pace:
        parts.append(f"【节奏档位】{pace}")
    parts.append(
        "【输出要求】\n"
        "- 写完整一章正文，约 2500–4000 字\n"
        "- 第一行必须是【章节标题】+ 简短标题\n"
        "- 空一行后只输出正文，不要解释，不要 [讨论]\n"
        "- 严格按 Scene Beat 完成本章情节；章末留小钩子"
    )
    return "\n\n".join(parts)


def format_generate_report(
    *,
    label: str,
    chapter_from: int,
    chapter_to: int,
    generated: list[dict],
    skipped: list[int],
    errors: list[str],
    total_cost_usd: float = 0.0,
) -> str:
    lines = [
        f"# 世界批量生成 · {label}",
        "",
        f"- 范围：第 {chapter_from}–{chapter_to} 章",
        f"- 成功生成：{len(generated)} 章",
        f"- 跳过（已有正文）：{len(skipped)} 章",
        f"- 失败：{len(errors)} 项",
    ]
    if total_cost_usd:
        lines.append(f"- 预估费用：${total_cost_usd:.4f}")
    lines.append("")
    if generated:
        lines.append("## 已生成")
        for row in generated:
            t = row.get("chapter_title") or ""
            lines.append(
                f"- 第 {row.get('chapter_num')} 章"
                + (f" · {t}" if t else "")
                + f" · {row.get('chars', 0)} 字"
            )
    if skipped:
        lines.append("")
        lines.append("## 已跳过")
        lines.append(", ".join(f"第{n}章" for n in skipped))
    if errors:
        lines.append("")
        lines.append("## 错误")
        for err in errors:
            lines.append(f"- {err}")
    lines.append("")
    lines.append(
        "> 下一步：通读正文 → **世界闭环** 或 **女频审阅+改稿** → **仅同步档案**。"
    )
    return "\n".join(lines)


def run_world_batch_generate(
    *,
    data_dir: Path,
    read_chapter: Callable[[int], str],
    generate_chapter: Callable[..., dict],
    set_batch_job_running: Callable[[bool, str], None],
    quality_log_entry: Callable[..., str | None],
    chapter_from: int | None = None,
    chapter_to: int | None = None,
    overwrite: bool = False,
    skip_existing: bool = True,
    resume_job_id: str | None = None,
) -> dict:
    """按世界范围与 plan Beat 逐章生成正文；支持 job 检查点续跑。"""
    job: dict | None = None
    if resume_job_id:
        job = load_job(data_dir, resume_job_id)
        if not job:
            return {"ok": False, "error": f"续跑任务不存在: {resume_job_id}"}
        if job.get("kind") != JOB_KIND_WORLD_GENERATE:
            return {"ok": False, "error": "任务类型不是世界批量生成"}
        if job.get("status") == STATUS_DONE:
            return {"ok": False, "error": "该任务已完成，无需续跑", "job_id": resume_job_id}
        chapter_from = int(job.get("chapter_from") or 0)
        chapter_to = int(job.get("chapter_to") or 0)
        label = (job.get("label") or "").strip() or "当前世界"
        skipped = list(job.get("skipped") or [])
        generated: list[dict] = list(job.get("generated") or [])
        errors: list[str] = list(job.get("errors") or [])
        total_cost = float(job.get("total_cost_usd") or 0.0)
        targets = remaining_targets(job)
        if not targets:
            mark_job_done(job, partial=bool(errors))
            save_job(data_dir, job)
            return {
                "ok": True,
                "job_id": job["id"],
                "resumed": True,
                "message": "没有待续跑章节",
                "generated": generated,
                "errors": errors,
            }
        job_id = job["id"]
    else:
        cf, ct = batch_world.infer_world_chapter_range()
        chapter_from = chapter_from or cf
        chapter_to = chapter_to or ct
        if chapter_from < 1 or chapter_to < chapter_from:
            return {"ok": False, "error": "章节范围无效"}

        project = novel_data.get_project_meta()
        label = (project.get("world_label") or "").strip() or "当前世界"
        beat_nums = batch_world.chapters_with_beats(chapter_from, chapter_to)
        if not beat_nums:
            return {
                "ok": False,
                "error": "plan 中未找到覆盖该范围的 Scene Beat，请先在规划模式填写 Beat（如「第1-2章」）",
            }

        targets = []
        skipped = []
        for num in range(chapter_from, chapter_to + 1):
            if num not in beat_nums:
                continue
            has_text = bool((read_chapter(num) or "").strip())
            if has_text and skip_existing and not overwrite:
                skipped.append(num)
                continue
            targets.append(num)

        if not targets:
            return {
                "ok": False,
                "error": "没有待生成章节（范围内章节均已有正文；勾选覆盖或清空后重试）",
                "skipped": skipped,
                "chapter_from": chapter_from,
                "chapter_to": chapter_to,
            }

        job = create_job(
            JOB_KIND_WORLD_GENERATE,
            label=label,
            chapter_from=chapter_from,
            chapter_to=chapter_to,
            targets=targets,
            extra={
                "skipped": skipped,
                "overwrite": overwrite,
                "skip_existing": skip_existing,
            },
        )
        job_id = job["id"]
        generated = []
        errors = []
        total_cost = 0.0
        job_path(data_dir, job_id).mkdir(parents=True, exist_ok=True)
        save_job(data_dir, job)

    set_batch_job_running(True, job_id)

    try:
        for num in targets:
            job["status"] = STATUS_RUNNING
            job["progress"] = {
                "current": len(job.get("completed") or []) + 1,
                "total": len(job.get("targets") or []),
            }
            save_job(data_dir, job)

            meta = batch_world.resolve_beat_for_prose_chapter(num)
            if not meta or not meta.get("beat"):
                err = f"第{num}章：无 Beat"
                errors.append(err)
                job["errors"] = errors
                save_job(data_dir, job)
                continue

            if meta.get("scene_id"):
                try:
                    novel_data.set_active_scene(meta["scene_id"])
                except Exception:
                    pass

            prev_tail = ""
            if num > chapter_from:
                prev_body = (read_chapter(num - 1) or "").strip()
                if prev_body:
                    prev_tail = prev_body[-PREV_TAIL_CHARS:]

            instruction = build_chapter_generate_instruction(num, meta, prev_tail=prev_tail)
            result = generate_chapter(
                num,
                instruction,
                scene_beat=meta.get("beat") or "",
            )
            cost = float(result.get("cost_usd") or 0)
            total_cost += cost
            job["total_cost_usd"] = total_cost

            if not result.get("ok"):
                err = f"第{num}章：{result.get('error') or '生成失败'}"
                errors.append(err)
                job["errors"] = errors
                job["status"] = STATUS_PAUSED
                save_job(data_dir, job)
                continue

            row = {
                "chapter_num": num,
                "chapter_title": result.get("chapter_title") or "",
                "chars": result.get("chars") or 0,
                "scene_id": meta.get("scene_id") or "",
            }
            generated.append(row)
            completed = list(job.get("completed") or [])
            if num not in completed:
                completed.append(num)
            job["completed"] = completed
            job["generated"] = generated
            save_job(data_dir, job)
    finally:
        set_batch_job_running(False, "")

    mark_job_done(job, partial=bool(generated) and bool(errors))
    job["generated"] = generated
    job["skipped"] = skipped
    job["errors"] = errors
    job["total_cost_usd"] = total_cost
    report = format_generate_report(
        label=label,
        chapter_from=chapter_from,
        chapter_to=chapter_to,
        generated=generated,
        skipped=skipped,
        errors=errors,
        total_cost_usd=total_cost,
    )
    job["report"] = report
    save_job(data_dir, job)
    (job_path(data_dir, job_id) / "report.md").write_text(report, encoding="utf-8")

    ok = bool(generated) and not errors
    partial = bool(generated) and bool(errors)
    log_id = quality_log_entry(
        "world_batch_generate",
        generated[-1]["chapter_num"] if generated else chapter_from,
        report,
        summary=f"世界生成 · {label} · {len(generated)}章"[:120],
        persisted=bool(generated),
        persisted_detail=f"生成 {len(generated)} 章",
        extra={
            "job_id": job_id,
            "chapter_from": chapter_from,
            "chapter_to": chapter_to,
            "generated": [g["chapter_num"] for g in generated],
            "skipped": skipped,
            "errors": errors,
            "total_cost_usd": total_cost,
            "resumed": bool(resume_job_id),
        },
    )
    return {
        "ok": ok or partial,
        "partial": partial,
        "job_id": job_id,
        "resumed": bool(resume_job_id),
        "label": label,
        "chapter_from": chapter_from,
        "chapter_to": chapter_to,
        "target_count": len(job.get("targets") or []),
        "ok_count": len(generated),
        "skipped": skipped,
        "generated": generated,
        "errors": errors,
        "report": report,
        "total_cost_usd": total_cost,
        "log_id": log_id,
    }
