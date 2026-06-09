"""Prompt 归因：证据收集、标签启发、LLM 诊断。"""

from __future__ import annotations

import json
import re
from typing import Any

from core import prompt_nodes
from core import taste

# quality_log.kind → 默认 prompt 节点（无 extra.prompt_node 时回退）
KIND_TO_NODE: dict[str, str] = {
    "prefill_direction": "prefill.direction",
    "prefill_plan": "prefill.plan",
    "female_fiction_review": "review.platform",
    "female_fiction_revise": "review.platform",
    "female_fiction_accept": "review.platform",
    "continuity": "check.continuity",
    "character_drift": "check.continuity",
    "repetition": "check.continuity",
    "pacing": "check.continuity",
    "deconstruct": "check.deconstruct",
    "summary": "maintain.summary",
    "finalize": "maintain.summary",
}

# issue_tag → 可能相关的节点（启发式，供 LLM 参考）
TAG_NODE_HINTS: dict[str, list[str]] = {
    "hook_weak": ["prefill.direction", "prefill.plan", "writing.main"],
    "hook_strong": ["prefill.plan", "writing.main"],
    "ai_tone": ["writing.main", "review.platform"],
    "pacing_slow": ["prefill.plan", "writing.main"],
    "pacing_fast": ["prefill.plan"],
    "character_off": ["prefill.direction", "writing.main", "review.platform"],
    "emotion_flat": ["writing.main", "review.platform"],
    "dialogue_stiff": ["writing.main"],
    "platform_mismatch": ["prefill.direction", "review.platform"],
    "submission_reject": ["review.platform", "writing.main", "prefill.plan"],
    "deconstruct_pattern": ["prefill.plan", "writing.main"],
}

NEGATIVE_OUTCOMES = frozenset({
    "rejected", "not_useful", "pending",
})


def node_for_log_entry(row: dict) -> str:
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    node = str(extra.get("prompt_node") or "").strip()
    if node:
        return node
    kind = str(row.get("kind") or "")
    return KIND_TO_NODE.get(kind, "")


def collect_evidence(
    log_rows: list[dict],
    *,
    taste_events: list[dict] | None = None,
    max_body_chars: int = 2500,
) -> dict[str, Any]:
    """整理诊断输入材料。"""
    entries: list[dict] = []
    tags: list[str] = []
    nodes_seen: list[str] = []

    for row in log_rows:
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        node = node_for_log_entry(row)
        if node and node not in nodes_seen:
            nodes_seen.append(node)
        for t in extra.get("issue_tags") or []:
            ts = str(t).strip()
            if ts and ts not in tags:
                tags.append(ts)
        body = str(row.get("body") or "")
        if len(body) > max_body_chars:
            body = body[:max_body_chars] + "\n…（截断）"
        entries.append({
            "id": row.get("id"),
            "kind": row.get("kind"),
            "chapter_num": row.get("chapter_num"),
            "outcome": extra.get("outcome"),
            "prompt_node": node,
            "prompt_hash": extra.get("prompt_hash"),
            "issue_tags": extra.get("issue_tags") or [],
            "summary": row.get("summary"),
            "body_excerpt": body,
        })

    event_notes: list[dict] = []
    for ev in (taste_events or [])[:15]:
        event_notes.append({
            "source": ev.get("source"),
            "outcome": ev.get("outcome"),
            "issue_tags": ev.get("issue_tags"),
            "note": ev.get("note"),
        })

    heuristic_nodes: list[str] = []
    for tag in tags:
        for nid in TAG_NODE_HINTS.get(tag, []):
            if nid not in heuristic_nodes:
                heuristic_nodes.append(nid)

    return {
        "log_entries": entries,
        "issue_tags": tags,
        "nodes_involved": nodes_seen,
        "heuristic_suspects": heuristic_nodes,
        "taste_events": event_notes,
    }


def heuristic_diagnosis(evidence: dict[str, Any]) -> dict[str, Any]:
    """无 LLM 时的规则归因（API 可单独返回）。"""
    tags = evidence.get("issue_tags") or []
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    for tag in tags:
        for nid in TAG_NODE_HINTS.get(tag, []):
            scores[nid] = scores.get(nid, 0.0) + 1.0
            reasons.setdefault(nid, []).append(f"标签 {taste.tag_label(tag)}")

    for nid in evidence.get("nodes_involved") or []:
        scores[nid] = scores.get(nid, 0.0) + 0.5
        reasons.setdefault(nid, []).append("出现在问题记录的 prompt_node")

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    max_score = ranked[0][1] if ranked else 1.0
    suspects = []
    for nid, score in ranked:
        conf = min(0.95, round(score / max(max_score, 1.0) * 0.75 + 0.1, 2))
        suspects.append({
            "node_id": nid,
            "confidence": conf,
            "reason": "；".join(reasons.get(nid, [])),
            "suggested_patch": "",
            "patch_mode": "append",
            "source": "heuristic",
        })
    return {
        "summary": f"基于 {len(tags)} 个标签的规则归因",
        "suspects": suspects,
        "avoid_nodes": [],
        "next_action": "建议调用 LLM 诊断获取具体 patch，或手动 PUT /api/prompts/nodes/{{node_id}}",
    }


def build_diagnose_user_message(
    evidence: dict[str, Any],
    *,
    book_type: str = "",
    platform: str = "",
    taste_block: str = "",
    node_snapshots: dict[str, str] | None = None,
) -> str:
    parts = [
        f"书型：{book_type or 'unknown'}",
        f"平台：{platform or 'unknown'}",
        "",
        "## 证据包",
        json.dumps(evidence, ensure_ascii=False, indent=2),
    ]
    if taste_block.strip():
        parts.extend(["", taste_block.strip()])
    if node_snapshots:
        parts.append("\n## 相关节点当前 prompt（节选）")
        for nid, text in node_snapshots.items():
            excerpt = text[:2000] + ("…" if len(text) > 2000 else "")
            parts.append(f"\n### {nid}\n{excerpt}")
    parts.append("\n请输出诊断 JSON。")
    return "\n".join(parts)


def parse_diagnose_payload(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("诊断结果为空")
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError("无法解析诊断 JSON")
    data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("诊断 JSON 须为对象")
    return data


def apply_patch_preview(
    current_system: str,
    suggested_patch: str,
    *,
    patch_mode: str = "append",
) -> str:
    patch = (suggested_patch or "").strip()
    if not patch:
        return current_system
    if patch_mode == "replace_section":
        return patch
    base = (current_system or "").rstrip()
    return f"{base}\n\n## 本书追加规则（诊断建议）\n{patch}\n"
