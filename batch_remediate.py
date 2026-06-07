"""世界闭环：诊断 → 改稿 → 整批档案同步 → 整批变更报告（单 job，无中途确认）。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

import config
import novel_data
from summarizer import (
    WORLD_REMEDIATE_BULK_CHANGE_LOG_SYSTEM,
    WORLD_REMEDIATE_DIAGNOSE_SYSTEM,
    build_remediate_bulk_change_log_user_message,
    build_remediate_diagnose_user_message,
    build_remediate_fix_instruction,
    format_remediate_closure_report,
    parse_remediate_bulk_change_log,
    parse_remediate_diagnose,
)

import batch_world
import runtime_log


def _dbg_remediate(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict | None = None,
) -> None:
    runtime_log.log_debug(location, message, data=data or {}, hypothesis_id=hypothesis_id)


_ARCHIVE_BULK_NAMES = (
    "summaries_recent.md",
    "char_dynamic.md",
    "plot_threads_locked.md",
    "plot_threads_active.md",
)


def jobs_dir(data_dir: Path) -> Path:
    return data_dir / "batch_jobs"


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def job_path(data_dir: Path, job_id: str) -> Path:
    return jobs_dir(data_dir) / job_id


def load_job(data_dir: Path, job_id: str) -> dict | None:
    path = job_path(data_dir, job_id) / "job.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_job(data_dir: Path, job: dict) -> None:
    jid = job.get("id")
    if not jid:
        raise ValueError("job 缺少 id")
    root = job_path(data_dir, jid)
    root.mkdir(parents=True, exist_ok=True)
    (root / "job.json").write_text(
        json.dumps(job, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _chapter_beats(chapter_num: int) -> tuple[str, str]:
    ch = novel_data.get_chapter_plan(chapter_num) or {}
    title = (ch.get("title") or "").strip()
    beats: list[str] = []
    for scene in ch.get("scenes") or []:
        beat = (scene.get("beat") or "").strip()
        if beat:
            beats.append(beat)
    return title, "\n\n".join(beats)


def snapshot_chapter_before(job_root: Path, chapter_num: int, content: str) -> None:
    before = job_root / "before"
    before.mkdir(parents=True, exist_ok=True)
    (before / f"ch{chapter_num:03d}.md").write_text(content or "", encoding="utf-8")


def snapshot_archives_pre_bulk(
    job_root: Path,
    *,
    read_text: Callable[[Path], str],
    archive_files: dict[str, Path],
) -> None:
    """整批档案同步前的一份快照（非逐章）。"""
    dest = job_root / "before" / "archives_pre_bulk"
    dest.mkdir(parents=True, exist_ok=True)
    for name, path in archive_files.items():
        (dest / name).write_text(read_text(path), encoding="utf-8")


def revert_chapter_from_job(
    data_dir: Path,
    job_id: str,
    chapter_num: int,
    *,
    write_chapter: Callable[[int, str], None],
    sync_title: Callable[[int], None],
) -> dict:
    """仅恢复正文；档案不回滚（请用 git 或重跑 bulk_archive_sync）。"""
    job = load_job(data_dir, job_id)
    if not job:
        return {"ok": False, "error": "任务不存在"}
    root = job_path(data_dir, job_id)
    body_src = root / "before" / f"ch{chapter_num:03d}.md"
    if not body_src.exists():
        return {"ok": False, "error": f"第{chapter_num}章无改前快照"}
    body = body_src.read_text(encoding="utf-8")
    write_chapter(chapter_num, body)
    sync_title(chapter_num)

    reverted_list = job.get("reverted_chapters") or []
    if chapter_num not in reverted_list:
        reverted_list.append(chapter_num)
    job["reverted_chapters"] = reverted_list
    job["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_job(data_dir, job)
    return {
        "ok": True,
        "chapter_num": chapter_num,
        "reverted": ["正文"],
        "warning": "仅恢复正文；档案未回滚，请用 git 或重跑「仅同步档案」/世界闭环档案步骤",
    }


def _apply_bulk_change_log(chapter_results: list[dict], bulk_log: dict) -> None:
    by_num = {int(c.get("num", 0)): c for c in bulk_log.get("chapters") or []}
    for ch in chapter_results:
        num = int(ch.get("num") or 0)
        row = by_num.get(num)
        if not row:
            continue
        ch["changes"] = row.get("changes") or []
        ch["skipped"] = row.get("skipped") or []


def run_world_remediate(
    *,
    data_dir: Path,
    read_chapter: Callable[[int], str],
    read_text: Callable[[Path], str],
    get_char_context_for_check: Callable[[], str],
    build_cached_system: Callable,
    call_api: Callable,
    get_last_call_info: Callable,
    remediate_chapter: Callable,
    bulk_archive_sync: Callable[[list[int]], dict],
    write_chapter: Callable[[int, str], None],
    sync_title: Callable[[int], None],
    quality_log_entry: Callable,
    set_batch_job_running: Callable[[bool, str], None],
    world_file: Path,
    characters_file: Path,
    char_dynamic_file: Path,
    summaries_recent_file: Path,
    plot_locked_file: Path,
    plot_active_file: Path,
    chapter_from: int | None = None,
    chapter_to: int | None = None,
) -> dict:
    """执行世界闭环 job（同步阻塞至完成或失败）。"""
    status = batch_world.get_world_batch_status(read_chapter=read_chapter)
    cf = chapter_from if chapter_from is not None else status["written_from"]
    ct = chapter_to if chapter_to is not None else status["written_to"]
    if not status["written_count"]:
        return {"ok": False, "error": "本世界尚无正文"}
    if cf < 1 or ct < cf:
        return {"ok": False, "error": "章节范围无效"}

    targets: list[int] = []
    for num in range(cf, ct + 1):
        if (read_chapter(num) or "").strip():
            targets.append(num)
    if not targets:
        return {"ok": False, "error": f"第{cf}–{ct}章范围内没有正文"}

    label = status["label"]
    job_id = new_job_id()
    _dbg_remediate(
        "H1",
        "batch_remediate:run_world_remediate",
        "job start",
        {
            "job_id": job_id,
            "label": label,
            "cf": cf,
            "ct": ct,
            "targets": targets,
        },
    )
    job_root = job_path(data_dir, job_id)
    job_root.mkdir(parents=True, exist_ok=True)

    job: dict = {
        "id": job_id,
        "status": "running",
        "phase": "diagnose",
        "label": label,
        "chapter_from": cf,
        "chapter_to": ct,
        "targets": targets,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "accepted": False,
        "chapters": [],
        "errors": [],
        "warnings": [],
        "total_cost_usd": 0.0,
    }
    save_job(data_dir, job)
    set_batch_job_running(True, job_id)

    archive_files = {
        "summaries_recent": summaries_recent_file,
        "char_dynamic": char_dynamic_file,
        "plot_threads_locked": plot_locked_file,
        "plot_threads_active": plot_active_file,
    }

    world = read_text(world_file)
    characters = read_text(characters_file)
    char_ctx = get_char_context_for_check()
    plot_locked = read_text(plot_locked_file)
    plot_active = read_text(plot_active_file)
    cross_notes_parts: list[str] = []
    chapter_results: list[dict] = []
    report_payloads: list[dict] = []
    fixed_nums: list[int] = []
    errors: list[str] = []
    warnings: list[str] = []
    total_cost = 0.0
    ok_count = 0
    pid_diag = config.CHECK_PROVIDER
    pid_log = config.CHECK_PROVIDER

    try:
        for idx, num in enumerate(targets):
            job["progress"] = {"current": idx + 1, "total": len(targets)}
            save_job(data_dir, job)

            content = read_chapter(num)
            ch_title, scene_beat = _chapter_beats(num)
            cross_notes = "\n".join(cross_notes_parts[-3:])

            job["phase"] = f"diagnose:{num}"
            save_job(data_dir, job)
            diag_system = build_cached_system(
                WORLD_REMEDIATE_DIAGNOSE_SYSTEM, provider=pid_diag
            )
            diag_user = build_remediate_diagnose_user_message(
                num,
                ch_title,
                scene_beat,
                world,
                characters,
                char_ctx,
                plot_locked,
                plot_active,
                content,
                cross_notes=cross_notes,
            )
            diag_reply = call_api(
                diag_system,
                [{"role": "user", "content": diag_user}],
                provider=pid_diag,
                tag=f"闭环诊断·第{num}章",
                silent=True,
            )
            info_d = get_last_call_info() or {}
            total_cost += float(info_d.get("cost") or info_d.get("cost_usd") or 0)

            if diag_reply is None:
                err = f"第{num}章诊断失败：{info_d.get('error', '未知')}"
                errors.append(err)
                chapter_results.append({"num": num, "error": err})
                continue

            diagnose, diag_parse_err = parse_remediate_diagnose(diag_reply)
            if not diagnose:
                diagnose = {
                    "num": num,
                    "action": "patch",
                    "issues": [
                        {
                            "severity": "must_fix",
                            "summary": "诊断 JSON 解析失败，按需润色",
                            "location": "全章",
                        }
                    ],
                    "skip_reason": "",
                }
                warnings.append(f"第{num}章诊断 JSON 解析失败，已按 patch 继续")

            diagnose["num"] = num
            action = diagnose.get("action") or "patch"

            snapshot_chapter_before(job_root, num, content)
            before_text = content

            ch_result: dict = {
                "num": num,
                "action": action,
                "title": ch_title,
                "diagnose": diagnose,
                "changes": [],
                "skipped": [],
            }

            if action == "skip":
                ch_result["skip_reason"] = diagnose.get("skip_reason") or "无需修改"
                chapter_results.append(ch_result)
                job["chapters"] = chapter_results
                save_job(data_dir, job)
                ok_count += 1
                for issue in diagnose.get("issues") or []:
                    if issue.get("summary"):
                        cross_notes_parts.append(f"第{num}章：{issue.get('summary')}")
                continue

            job["phase"] = f"fix:{num}"
            save_job(data_dir, job)
            fix_instruction = build_remediate_fix_instruction(
                num, ch_title, scene_beat, diagnose, cross_notes=cross_notes
            )
            fix_r = remediate_chapter(
                num,
                fix_instruction,
                scene_beat=scene_beat,
            )
            info_f = get_last_call_info() or {}
            total_cost += float(info_f.get("cost") or info_f.get("cost_usd") or 0)

            if not fix_r.get("ok"):
                err = f"第{num}章改稿失败：{fix_r.get('error', '未知')}"
                errors.append(err)
                ch_result["error"] = err
                chapter_results.append(ch_result)
                continue

            after_text = read_chapter(num)
            ch_result["chars_before"] = len(before_text)
            ch_result["chars_after"] = len(after_text)
            ch_result["title"] = fix_r.get("chapter_title") or ch_title
            fixed_nums.append(num)
            report_payloads.append(
                {
                    "num": num,
                    "action": action,
                    "diagnose": diagnose,
                    "before_text": before_text,
                    "after_text": after_text,
                }
            )
            chapter_results.append(ch_result)
            ok_count += 1
            job["chapters"] = chapter_results
            save_job(data_dir, job)

            for issue in diagnose.get("issues") or []:
                if issue.get("summary"):
                    cross_notes_parts.append(f"第{num}章：{issue.get('summary')}")

        archive_bulk: dict = {"ok": False, "fixed_nums": fixed_nums}
        if fixed_nums:
            job["phase"] = "archive:bulk"
            save_job(data_dir, job)
            snapshot_archives_pre_bulk(
                job_root,
                read_text=read_text,
                archive_files=archive_files,
            )
            arch_r = bulk_archive_sync(fixed_nums)
            info_a = get_last_call_info() or {}
            total_cost += float(info_a.get("cost") or info_a.get("cost_usd") or 0)
            archive_bulk = {
                "ok": arch_r.get("ok", False),
                "partial": arch_r.get("partial", False),
                "summaries_ok": arch_r.get("summaries_ok", False),
                "state_ok": arch_r.get("state_ok", False),
                "fixed_nums": fixed_nums,
                "summary_count": arch_r.get("summary_count", 0),
                "errors": arch_r.get("errors") or [],
                "warnings": arch_r.get("warnings") or [],
            }
            job["archive_bulk"] = archive_bulk
            save_job(data_dir, job)
            if not arch_r.get("ok"):
                msg = arch_r.get("error") or "整批档案同步失败"
                warnings.append(msg)
                for e in arch_r.get("errors") or []:
                    warnings.append(str(e))
        else:
            warnings.append("无成功改稿章节，已跳过整批档案同步")
            job["archive_bulk"] = archive_bulk
            save_job(data_dir, job)

        if report_payloads:
            job["phase"] = "report:bulk"
            save_job(data_dir, job)
            log_system = build_cached_system(
                WORLD_REMEDIATE_BULK_CHANGE_LOG_SYSTEM, provider=pid_log
            )
            log_user = build_remediate_bulk_change_log_user_message(report_payloads)
            log_reply = call_api(
                log_system,
                [{"role": "user", "content": log_user}],
                provider=pid_log,
                tag=f"闭环报告·第{cf}–{ct}章",
                silent=True,
            )
            info_l = get_last_call_info() or {}
            total_cost += float(info_l.get("cost") or info_l.get("cost_usd") or 0)
            if log_reply:
                bulk_log, _ = parse_remediate_bulk_change_log(log_reply)
                if bulk_log:
                    _apply_bulk_change_log(chapter_results, bulk_log)
                else:
                    warnings.append("整批变更报告 JSON 解析失败")
            else:
                warnings.append(
                    f"整批变更报告失败：{info_l.get('error', '未知')}"
                )
            job["chapters"] = chapter_results
            save_job(data_dir, job)

        report = format_remediate_closure_report(
            label,
            cf,
            ct,
            chapter_results,
            warnings=warnings,
            errors=errors,
        )
        if archive_bulk.get("fixed_nums"):
            report += "\n\n## 整批档案同步\n"
            if archive_bulk.get("ok"):
                report += (
                    f"- ✅ 已同步 {len(archive_bulk['fixed_nums'])} 章"
                    f"（概述 {archive_bulk.get('summary_count', 0)} 条）\n"
                )
            else:
                report += "- ⚠️ 部分失败，见 warnings\n"

        (job_root / "report.md").write_text(report, encoding="utf-8")

        job["status"] = "failed" if ok_count == 0 else "completed"
        job["phase"] = "done"
        job["report"] = report
        job["errors"] = errors
        job["warnings"] = warnings
        job["ok_count"] = ok_count
        job["total_cost_usd"] = round(total_cost, 6)
        job["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_job(data_dir, job)

        log_id = quality_log_entry(
            "world_remediate",
            targets[-1] if targets else 0,
            report,
            summary=f"{label} · 第{cf}–{ct}章 · 成功{ok_count}/{len(targets)}",
            extra={
                "job_id": job_id,
                "ok_count": ok_count,
                "targets": len(targets),
                "fixed_nums": fixed_nums,
            },
        )
        job["log_id"] = log_id
        save_job(data_dir, job)

        if errors:
            runtime_log.log_error(
                "batch",
                "batch_remediate:run_world_remediate",
                f"世界闭环 {job['status']}：{len(errors)} 个错误",
                data={"job_id": job_id, "errors": errors[:20]},
            )
        elif warnings:
            runtime_log.log_warn(
                "batch",
                "batch_remediate:run_world_remediate",
                f"世界闭环完成，{len(warnings)} 条警告",
                data={"job_id": job_id, "warnings": warnings[:20]},
            )

        return {
            "ok": job["status"] == "completed",
            "partial": bool(errors) and ok_count > 0,
            "job_id": job_id,
            "status": job["status"],
            "report": report,
            "chapters": chapter_results,
            "archive_bulk": archive_bulk,
            "errors": errors,
            "warnings": warnings,
            "ok_count": ok_count,
            "target_count": len(targets),
            "total_cost_usd": job["total_cost_usd"],
            "log_id": log_id,
        }
    finally:
        set_batch_job_running(False, "")


def accept_job(data_dir: Path, job_id: str) -> dict:
    job = load_job(data_dir, job_id)
    if not job:
        return {"ok": False, "error": "任务不存在"}
    job["accepted"] = True
    job["accepted_at"] = datetime.now().isoformat(timespec="seconds")
    job["updated_at"] = job["accepted_at"]
    save_job(data_dir, job)
    return {"ok": True, "job_id": job_id, "accepted": True}
