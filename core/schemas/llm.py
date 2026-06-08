"""LLM 结构化输出：fence 标记对应的类型定义与 parse/normalize 函数。

从 summarizer.py 迁移而来；summarizer 仍保留原实现以保持兼容，新代码请 import 本模块。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, TypedDict


# ---------------------------------------------------------------------------
# TypedDict / dataclass 契约
# ---------------------------------------------------------------------------


class ObserveItem(TypedDict, total=False):
    id: str
    target_file: Literal["char_static", "char_dynamic"]
    has_change: bool
    proposed_text: str
    accepted: bool
    edited_text: str
    chapter_num: int


class ObserveBlock(TypedDict):
    summary: str
    items: list[ObserveItem]


class MaintainPayload(TypedDict):
    summary: str
    observe: ObserveBlock
    detail_locked: str
    plot_new_threads: str
    plot_advanced: str
    plot_resolved: str


class QualityPayload(TypedDict):
    continuity: str
    character_drift: str
    repetition: str


class RemediateDiagnosePayload(TypedDict, total=False):
    num: int
    action: Literal["patch", "full_rewrite", "skip"]
    issues: list[dict[str, Any]]
    skip_reason: str


class RemediateChangeLogPayload(TypedDict, total=False):
    num: int
    action: str
    changes: list[dict[str, Any]]
    skipped: list[dict[str, Any]]


class BulkSummariesPayload(TypedDict):
    summaries: list[dict[str, Any]]


class BulkStatePayload(TypedDict, total=False):
    char_dynamic: str
    plot_threads_active: str
    detail_locked_append: str
    plot_new_threads: str


@dataclass
class BundleParseResult:
    """LLM 回复 + 解析结果。"""

    reply: str
    payload: MaintainPayload | None
    parse_ok: bool
    raw_on_fail: str = ""


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------


def normalize_maintain_payload(data: dict) -> MaintainPayload:
    observe = data.get("observe")
    if isinstance(observe, list):
        observe = {"summary": "", "items": observe}
    elif not isinstance(observe, dict):
        observe = {"summary": "", "items": []}
    items = observe.get("items", [])
    if not isinstance(items, list):
        items = []
    return {
        "summary": str(data.get("summary") or "").strip(),
        "observe": {
            "summary": str(observe.get("summary") or "").strip(),
            "items": items,
        },
        "detail_locked": str(data.get("detail_locked") or "").strip(),
        "plot_new_threads": str(data.get("plot_new_threads") or "").strip(),
        "plot_advanced": str(data.get("plot_advanced") or "").strip(),
        "plot_resolved": str(data.get("plot_resolved") or "").strip(),
    }


def normalize_quality_payload(data: dict) -> QualityPayload:
    return {
        "continuity": str(data.get("continuity") or "").strip(),
        "character_drift": str(data.get("character_drift") or "").strip(),
        "repetition": str(data.get("repetition") or "").strip(),
    }


def count_report_issues(text: str) -> int:
    """粗估报告中的问题条数（供前端展示）。"""
    body = (text or "").strip()
    if not body or "未发现明显矛盾" in body or "无明显漂移" in body:
        return 0
    count = 0
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("- [") or s.startswith("- 【") or "⚠️" in s:
            count += 1
    return count


# ---------------------------------------------------------------------------
# parse（fence → 结构化 payload）
# ---------------------------------------------------------------------------


def parse_observe_proposals(reply: str) -> tuple[list[ObserveItem], str]:
    """解析 observe-json 块，返回 (items, 给用户看的 Markdown 摘要)。"""
    text = reply.strip()
    for pattern in (r"```observe-json\s*([\s\S]*?)```", r"```json\s*([\s\S]*?)```"):
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            items = data.get("items", [])
            if isinstance(items, list):
                summary = text[: match.start()].strip()
                return items, summary
        except json.JSONDecodeError:
            continue
    return [], text


def parse_post_chapter_maintain(reply: str) -> tuple[MaintainPayload | None, str]:
    """解析 post-chapter-json。返回 (payload, 解析失败时的原文/备注)。"""
    text = (reply or "").strip()
    if not text:
        return None, ""

    for fence in ("post-chapter-json", "json"):
        match = re.search(rf"```{re.escape(fence)}\s*([\s\S]*?)```", text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict) and (
                data.get("summary")
                or data.get("observe")
                or data.get("detail_locked")
                or data.get("plot_new_threads")
            ):
                return normalize_maintain_payload(data), ""
        except json.JSONDecodeError:
            continue

    brace = re.search(r"\{[\s\S]*\"summary\"[\s\S]*\}", text)
    if brace:
        try:
            data = json.loads(brace.group(0))
            if isinstance(data, dict):
                return normalize_maintain_payload(data), ""
        except json.JSONDecodeError:
            pass

    return None, text


def parse_quality_bundle(reply: str) -> tuple[QualityPayload | None, str]:
    """解析 quality-bundle-json。"""
    text = (reply or "").strip()
    if not text:
        return None, ""

    for fence in ("quality-bundle-json", "json"):
        match = re.search(rf"```{re.escape(fence)}\s*([\s\S]*?)```", text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict) and (
                data.get("continuity")
                or data.get("character_drift")
                or data.get("repetition")
            ):
                return normalize_quality_payload(data), ""
        except json.JSONDecodeError:
            continue

    brace = re.search(
        r"\{[\s\S]*\"continuity\"[\s\S]*\"character_drift\"[\s\S]*\}", text
    )
    if brace:
        try:
            data = json.loads(brace.group(0))
            if isinstance(data, dict):
                return normalize_quality_payload(data), ""
        except json.JSONDecodeError:
            pass

    return None, text


def parse_bulk_summaries(reply: str) -> tuple[BulkSummariesPayload | None, str]:
    text = (reply or "").strip()
    for fence in ("bulk-summaries-json", "json"):
        match = re.search(rf"```{fence}\s*([\s\S]*?)```", text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict):
                rows = data.get("summaries")
                if isinstance(rows, list):
                    data["summaries"] = [r for r in rows if isinstance(r, dict)]
                    return data, ""
        except json.JSONDecodeError:
            continue
    return None, text


def parse_bulk_state(reply: str) -> tuple[BulkStatePayload | None, str]:
    text = (reply or "").strip()
    for fence in ("bulk-state-json", "json"):
        match = re.search(rf"```{fence}\s*([\s\S]*?)```", text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict):
                return data, ""
        except json.JSONDecodeError:
            continue
    return None, text


def parse_remediate_bulk_change_log(reply: str) -> tuple[dict | None, str]:
    text = (reply or "").strip()
    for fence in ("remediate-bulk-change-json", "json"):
        match = re.search(rf"```{fence}\s*([\s\S]*?)```", text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict):
                chapters = data.get("chapters")
                if isinstance(chapters, list):
                    data["chapters"] = [c for c in chapters if isinstance(c, dict)]
                    return data, ""
        except json.JSONDecodeError:
            continue
    return None, text


def parse_remediate_diagnose(reply: str) -> tuple[RemediateDiagnosePayload | None, str]:
    text = (reply or "").strip()
    for fence in ("remediate-diagnose-json", "json"):
        match = re.search(rf"```{fence}\s*([\s\S]*?)```", text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict):
                action = str(data.get("action") or "patch").strip()
                if action not in ("patch", "full_rewrite", "skip"):
                    action = "patch"
                data["action"] = action
                data["issues"] = (
                    data.get("issues") if isinstance(data.get("issues"), list) else []
                )
                return data, ""
        except json.JSONDecodeError:
            continue
    return None, text


def parse_remediate_change_log(reply: str) -> tuple[RemediateChangeLogPayload | None, str]:
    text = (reply or "").strip()
    for fence in ("remediate-change-json", "json"):
        match = re.search(rf"```{fence}\s*([\s\S]*?)```", text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict):
                data["changes"] = (
                    data.get("changes") if isinstance(data.get("changes"), list) else []
                )
                data["skipped"] = (
                    data.get("skipped") if isinstance(data.get("skipped"), list) else []
                )
                return data, ""
        except json.JSONDecodeError:
            continue
    return None, text
