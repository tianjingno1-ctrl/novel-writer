"""Prompt 归因诊断编排。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import infra.config as config
from core import prompt_diagnose
from core import prompt_nodes
from core import taste
from infra.logs import quality as quality_log

if TYPE_CHECKING:
    from app.context import AppContext


def _book_dir(ctx: AppContext) -> Path:
    return ctx.store.paths.data_dir


def _load_project(ctx: AppContext) -> dict:
    path = _book_dir(ctx) / "project.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _collect_bad_logs(limit: int = 20) -> list[dict]:
    rows: list[dict] = []
    for preview in quality_log.list_entries(limit=200):
        full = quality_log.get_entry(preview.get("id", ""))
        if not full:
            continue
        extra = full.get("extra") if isinstance(full.get("extra"), dict) else {}
        outcome = str(extra.get("outcome") or "").strip()
        tags = extra.get("issue_tags") or []
        if outcome in prompt_diagnose.NEGATIVE_OUTCOMES or tags:
            rows.append(full)
        if len(rows) >= limit:
            break
    return rows


def run_heuristic(ctx: AppContext, *, quality_log_id: str = "") -> dict:
    rows: list[dict] = []
    if quality_log_id:
        row = quality_log.get_entry(quality_log_id.strip())
        if not row:
            return {"ok": False, "error": "quality_log 记录不存在"}
        rows = [row]
    else:
        rows = _collect_bad_logs()

    if not rows:
        return {"ok": False, "error": "没有带 outcome/tags 的问题记录，请先 POST /api/quality/log/{id}/judgment"}

    from core.data import book_context

    events = taste.list_events(book_id=book_context.get_context().book_id, limit=30)
    evidence = prompt_diagnose.collect_evidence(rows, taste_events=events)
    result = prompt_diagnose.heuristic_diagnosis(evidence)
    return {"ok": True, "mode": "heuristic", "evidence": evidence, "diagnosis": result}


def run_llm_diagnose(
    ctx: AppContext,
    *,
    quality_log_id: str = "",
    use_heuristic_only: bool = False,
) -> dict:
    if use_heuristic_only:
        return run_heuristic(ctx, quality_log_id=quality_log_id)

    base = run_heuristic(ctx, quality_log_id=quality_log_id)
    if not base.get("ok"):
        return base

    evidence = base["evidence"]
    project = _load_project(ctx)
    book_dir = _book_dir(ctx)

    node_ids = list(dict.fromkeys(
        (evidence.get("heuristic_suspects") or [])
        + (evidence.get("nodes_involved") or [])
    ))[:4]
    snapshots: dict[str, str] = {}
    for nid in node_ids:
        try:
            resolved = prompt_nodes.resolve_node(
                nid, book_dir=book_dir, project=project,
            )
            snapshots[nid] = resolved.system
        except ValueError:
            continue

    taste_block = taste.build_context_block(book_dir=book_dir)
    user_msg = prompt_diagnose.build_diagnose_user_message(
        evidence,
        book_type=str(project.get("type") or ""),
        platform=str(project.get("platform") or ""),
        taste_block=taste_block,
        node_snapshots=snapshots,
    )

    from core import model_routing

    node_id = "diagnose.prompt"
    resolved = prompt_nodes.resolve_node(node_id, book_dir=book_dir, project=project)
    system_text = resolved.system
    pid = model_routing.resolve_provider_for_node(node_id)
    system = ctx.reviewer_deps.llm.build_cached_system(system_text, provider=pid)
    reply = ctx.reviewer_deps.llm.call_api(
        system,
        [{"role": "user", "content": user_msg}],
        node_id=node_id,
        tag="Prompt归因",
        silent=True,
    )
    if reply is None:
        return {
            "ok": False,
            "error": ctx.reviewer_deps.llm.get_last_call_info().get("error", "诊断失败"),
            "heuristic": base.get("diagnosis"),
        }

    try:
        diagnosis = prompt_diagnose.parse_diagnose_payload(reply)
    except ValueError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "raw_reply": reply,
            "heuristic": base.get("diagnosis"),
        }

    log_id = ctx.quality_log_entry(
        "prompt_diagnose",
        0,
        reply,
        summary=(diagnosis.get("summary") or "Prompt 归因")[:120],
        prompt_node="diagnose.prompt",
        prompt_hash=resolved.prompt_hash,
        prompt_source="global",
        outcome="pending",
        extra={"evidence_ids": [e.get("id") for e in evidence.get("log_entries") or []]},
    )

    from core import diagnosis_store
    from core.data import book_context

    suspects = diagnosis.get("suspects") or []
    primary = suspects[0] if suspects else {}
    node_id = str(primary.get("node_id") or "writing.main").strip()
    patch_text = str(primary.get("suggested_patch") or "").strip()
    tags: list[str] = []
    for row in evidence.get("log_entries") or []:
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        tags.extend(extra.get("issue_tags") or [])
    tags = list(dict.fromkeys(str(t).strip() for t in tags if str(t).strip()))

    diag_doc = diagnosis_store.create_pending(
        book_dir,
        book_id=book_context.get_context().book_id,
        quality_log_id=log_id,
        trigger="chapter_fail",
        issue_tags=tags,
        analysis=str(diagnosis.get("summary") or "").strip(),
        patch={
            "target_node": node_id,
            "diff_preview": patch_text[:800] or str(diagnosis.get("summary") or "")[:800],
            "override": {
                "prepend": "",
                "append": patch_text,
                "system": None,
            },
        },
    )

    return {
        "ok": True,
        "mode": "llm",
        "evidence": evidence,
        "diagnosis": diagnosis,
        "heuristic": base.get("diagnosis"),
        "log_id": log_id,
        "diagnosis_id": diag_doc.get("id"),
        "diagnosis_record": diag_doc,
        **ctx.reviewer_deps.llm.get_last_call_info(),
    }


def preview_patch(
    ctx: AppContext,
    node_id: str,
    suggested_patch: str,
    *,
    patch_mode: str = "append",
) -> dict:
    book_dir = _book_dir(ctx)
    project = _load_project(ctx)
    try:
        resolved = prompt_nodes.resolve_node(node_id, book_dir=book_dir, project=project)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    preview = prompt_diagnose.apply_patch_preview(
        resolved.system,
        suggested_patch,
        patch_mode=patch_mode,
    )
    return {
        "ok": True,
        "node_id": node_id,
        "patch_mode": patch_mode,
        "current_hash": resolved.prompt_hash,
        "preview_system": preview,
        "preview_hash": prompt_nodes._hash_text(preview),
    }


def apply_patch(
    ctx: AppContext,
    node_id: str,
    *,
    suggested_patch: str,
    patch_mode: str = "append",
    save: bool = False,
) -> dict:
    preview_r = preview_patch(
        ctx, node_id, suggested_patch, patch_mode=patch_mode,
    )
    if not preview_r.get("ok"):
        return preview_r
    if not save:
        return {**preview_r, "saved": False}

    book_dir = _book_dir(ctx)
    mode = (patch_mode or "append").strip().lower()
    if mode in ("append", "prepend"):
        result = prompt_nodes.merge_node_override(
            book_dir,
            node_id,
            {mode: suggested_patch},
        )
    else:
        result = prompt_nodes.save_node_override(
            book_dir,
            node_id,
            system=str(preview_r.get("preview_system") or ""),
        )
    if not result.get("ok"):
        return result
    return {**preview_r, "saved": True, "message": "已写入 prompt_overrides.yaml"}


def get_workflow_map() -> dict[str, Any]:
    """机器可读的全流程说明（与 docs/workflow.md 定稿图对齐）。"""
    return {
        "doc": "docs/workflow.md",
        "data_schema": "docs/data-schema.md",
        "role": "读者+审核者",
        "principles": [
            "AI 预填，人确认",
            "预览后采纳才写盘",
            "L1b 机器预检后再给人预览",
            "L5a 审阅通过 → 正向案例进口味库",
            "E7 拒稿与 L6 改规则统一走 P1 归因",
            "P3b 重跑前选范围",
        ],
        "patches": [
            {"id": "L5a", "name": "正向案例写入口味库", "status": "implemented"},
            {"id": "L5b", "name": "节奏预警", "status": "implemented"},
            {"id": "A10c", "name": "写作模式（已移除）", "status": "removed"},
            {"id": "E4b", "name": "投递类型与模板", "status": "implemented"},
            {"id": "L1b", "name": "字数与大纲关键词预检", "status": "implemented"},
            {"id": "P3b", "name": "重跑范围选择", "status": "implemented"},
            {"id": "E7_P1", "name": "拒稿归因复用 PROMPT", "status": "implemented"},
        ],
        "rerun_scopes": ["chapter_only", "from_chapter_n", "plan_only"],
        "submission_targets": ["text_editor", "comic_drama", "short_drama"],
        "plan_schema_target": {
            "meta": "已确认方向（目标：合并原 brief）",
            "chapters": "章/Beat",
            "review_criteria": "审阅标准清单（概念；落盘文件名由实现决定）",
        },
        "phases": [
            {
                "id": "A_open",
                "name": "开书",
                "steps": [
                    {"action": "POST /api/library/books"},
                    {"action": "POST /api/deconstruct", "optional": True},
                    {"action": "POST /api/taste/import-deconstruct", "optional": True},
                    {"action": "PUT /api/taste/global", "optional": True},
                    {"action": "POST /api/prefill/direction", "writes": "plan.meta (target)", "current": "brief.md"},
                    {"action": "POST /api/prefill/plan/apply", "writes": "plan.chapters"},
                    {"action": "confirm review_criteria", "node": "A10b"},
                ],
            },
            {
                "id": "B_chapter_loop",
                "name": "章循环",
                "steps": [
                    {"action": "POST /api/chat/stream", "node": "L1"},
                    {"action": "POST /api/chapters/{n}/precheck", "node": "L1b", "status": "implemented"},
                    {"action": "user_preview_adopt", "node": "L2-L3"},
                    {"action": "POST /api/review/female-fiction", "node": "L4-L5"},
                    {"action": "POST /api/taste/highlights/{n}", "node": "L5a", "status": "implemented"},
                    {"action": "POST /api/chapters/{n}/rhythm-check", "node": "L5b", "status": "implemented"},
                    {"action": "POST /api/chapters/{n}/attribution-log", "node": "L4a/L5b→P1", "status": "implemented"},
                    {"action": "summary_confirm", "node": "L10-L10b"},
                    {"action": "POST /api/quality/log/{id}/judgment", "when": "L6 改本章"},
                    {"action": "goto P1", "when": "L6 改规则 / L4a / L5b / E7a 内容"},
                ],
            },
            {
                "id": "C_prompt_loop",
                "name": "Prompt 归因",
                "entry": ["L6 改规则", "E7 拒稿"],
                "steps": [
                    {"action": "POST /api/prompts/diagnose", "node": "P1"},
                    {"action": "POST /api/prompts/diagnose/preview", "node": "P2-P3"},
                    {"action": "select_rerun_scope", "node": "P3b", "status": "implemented"},
                    {"action": "POST /api/rerun/pipeline", "node": "P4", "status": "implemented"},
                    {"action": "GET /api/flow/work-queue", "node": "P4", "status": "implemented"},
                    {"action": "GET /api/flow/steps", "node": "flow", "status": "implemented"},
                ],
            },
            {
                "id": "D_manuscript",
                "name": "完结与稿件",
                "steps": [
                    {"action": "pending_summary_gate", "node": "E1b-E1d", "status": "planned"},
                    {"action": "POST /api/manuscripts", "node": "E2"},
                    {"action": "PATCH state=complete", "node": "E3"},
                    {"action": "select_submission_target", "node": "E4b", "status": "implemented"},
                    {"action": "PATCH submission", "node": "E5-E6"},
                    {"action": "reject_tags_taste", "node": "E7"},
                    {"action": "E7a fork", "node": "E7a", "note": "content→P1 / strategy→E4b", "status": "implemented"},
                    {"action": "POST /api/compliance/preview", "node": "E4c", "status": "implemented"},
                ],
            },
        ],
        "prompt_nodes": prompt_nodes.list_node_defs(),
        "issue_tag_hints": prompt_diagnose.TAG_NODE_HINTS,
    }
