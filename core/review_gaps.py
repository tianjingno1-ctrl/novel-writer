"""从 L4 审阅正文解析结构化 gaps[]（review.json）。"""

from __future__ import annotations

import json
import re
from typing import Any

from core.schemas.rule_refs import parse_rule_ref

_REF_IN_TEXT = re.compile(
    r"\[?\s*(global|local|profile|custom)\s*:\s*([^\]\s,;，。]+)\s*\]?",
    re.IGNORECASE,
)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_GAPS_JSON = re.compile(r'\{\s*"gaps"\s*:\s*\[[\s\S]*?\]\s*\}', re.IGNORECASE)

_FAIL_HINTS = (
    "不通过",
    "未通过",
    "没过",
    "未能通过",
    "尚未通过",
    "未达标",
    "有风险",
    "需要重写",
    "需改",
    "偏弱",
    "不足",
    "缺失",
    "问题",
    "红线",
)
_PASS_MARKERS = ("✅", "☑", "✔")
_PASS_RE = re.compile(
    r"(?<![未不])通过|(?<![未不])达标|成立|无问题|\bok\b",
    re.IGNORECASE,
)


def gap_looks_passing(description: str) -> bool:
    """差距描述是否表示已达标（不应进入 gaps / 改稿指令）。"""
    text = re.sub(r"\s+", " ", (description or "").strip())
    if not text:
        return False
    if any(marker in text for marker in _PASS_MARKERS):
        return True
    if any(h in text for h in _FAIL_HINTS):
        return False
    if "⚠" in text or "❌" in text:
        return False
    if _PASS_RE.search(text):
        return True
    if re.search(r"合格(?!但)|已满足|无差距|全部达标", text):
        return True
    return False


def filter_open_gaps(gaps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """仅保留未达标的差距项。"""
    out: list[dict[str, Any]] = []
    for row in gaps or []:
        if not isinstance(row, dict):
            continue
        desc = str(row.get("description") or row.get("note") or "").strip()
        if gap_looks_passing(desc):
            continue
        out.append(row)
    return out


def _known_refs(resolved: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in resolved.get("hard") or []:
        if not isinstance(row, dict):
            continue
        ref = str(row.get("ref") or "").strip()
        if ref:
            out[ref] = {**row, "severity": "hard"}
    for row in resolved.get("soft") or []:
        if not isinstance(row, dict):
            continue
        ref = str(row.get("ref") or "").strip()
        if ref:
            out[ref] = {**row, "severity": "soft"}
    return out


def _normalize_ref(raw: str) -> str | None:
    text = (raw or "").strip().strip("[]")
    if not text:
        return None
    try:
        source, rule_id = parse_rule_ref(text)
        return f"{source}:{rule_id}"
    except ValueError:
        return None


def _normalize_gap(
    raw: dict[str, Any],
    known: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    ref = _normalize_ref(str(raw.get("rule_ref") or raw.get("ref") or ""))
    if not ref:
        return None
    desc = str(raw.get("description") or raw.get("note") or raw.get("gap") or "").strip()
    desc = re.sub(r"\s+", " ", desc)[:500]
    severity = str(raw.get("severity") or raw.get("weight") or "").strip().lower()
    if severity not in ("hard", "soft"):
        row = known.get(ref) or {}
        weight = str(row.get("weight") or row.get("severity") or "hard").lower()
        severity = "soft" if weight == "soft" else "hard"
    if not desc and ref in known:
        desc = str(known[ref].get("content") or "")[:200]
    if not desc:
        return None
    if gap_looks_passing(desc):
        return None
    return {"rule_ref": ref, "description": desc, "severity": severity}


def _parse_json_gaps(text: str, known: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[str] = []
    for m in _JSON_FENCE.finditer(text):
        candidates.append(m.group(1))
    for m in _GAPS_JSON.finditer(text):
        candidates.append(m.group(0))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for blob in candidates:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        rows = data.get("gaps") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            gap = _normalize_gap(item, known)
            if gap and gap["rule_ref"] not in seen:
                seen.add(gap["rule_ref"])
                out.append(gap)
    return out


def _line_looks_like_gap(line: str) -> bool:
    if gap_looks_passing(line):
        return False
    return any(h in line for h in _FAIL_HINTS) or "❌" in line or "⚠" in line


def _description_from_line(line: str, ref: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(
        rf"\[?\s*{re.escape(ref)}\s*\]?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^[\-\*•\d\.\)、\s]+", "", cleaned)
    cleaned = re.sub(r"^[：:\-—]\s*", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()[:500]


def _parse_line_gaps(text: str, known: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not _REF_IN_TEXT.search(line):
            continue
        for m in _REF_IN_TEXT.finditer(line):
            ref = _normalize_ref(f"{m.group(1)}:{m.group(2)}")
            if not ref or ref not in known or ref in seen:
                continue
            is_list_item = bool(re.match(r"^[\-\*•\d]", line.strip()))
            if not is_list_item and not _line_looks_like_gap(line):
                continue
            desc = _description_from_line(line, ref)
            if not desc:
                desc = str(known[ref].get("content") or "")[:200]
            if not desc:
                continue
            row = known[ref]
            weight = str(row.get("weight") or row.get("severity") or "hard").lower()
            out.append({
                "rule_ref": ref,
                "description": desc,
                "severity": "soft" if weight == "soft" else "hard",
            })
            seen.add(ref)
    return out


def _parse_mention_gaps(text: str, known: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """兜底：正文出现 [ref] 且邻近语句含差距语义。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    lower = text.lower()
    for ref, row in known.items():
        if ref in seen:
            continue
        if ref.lower() not in lower and f"[{ref}]".lower() not in lower:
            continue
        idx = lower.find(ref.lower())
        if idx < 0:
            idx = lower.find(f"[{ref}]".lower())
        if idx < 0:
            continue
        window = text[max(0, idx - 80) : idx + 200]
        if not _line_looks_like_gap(window):
            continue
        desc = str(row.get("content") or "")[:200]
        for line in window.splitlines():
            if ref.lower() in line.lower() and _line_looks_like_gap(line):
                parsed = _description_from_line(line, ref)
                if parsed:
                    desc = parsed
                break
        weight = str(row.get("weight") or row.get("severity") or "hard").lower()
        out.append({
            "rule_ref": ref,
            "description": desc,
            "severity": "soft" if weight == "soft" else "hard",
        })
        seen.add(ref)
    return out


def parse_gaps_from_review(
    review_text: str,
    resolved: dict[str, Any] | None,
    *,
    max_gaps: int = 20,
) -> list[dict[str, Any]]:
    """解析审阅正文 → gaps[]；优先 JSON 块，其次带 ref 的差距行。"""
    text = (review_text or "").strip()
    if not text:
        return []
    known = _known_refs(resolved or {})
    if not known:
        return []

    has_structured_json = '"gaps"' in text and (
        "```json" in text.lower() or _GAPS_JSON.search(text)
    )
    if has_structured_json:
        return filter_open_gaps(_parse_json_gaps(text, known))[:max_gaps]

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for batch in (
        _parse_json_gaps(text, known),
        _parse_line_gaps(text, known),
        _parse_mention_gaps(text, known),
    ):
        for gap in batch:
            ref = gap["rule_ref"]
            if ref in seen:
                continue
            seen.add(ref)
            merged.append(gap)
            if len(merged) >= max_gaps:
                return filter_open_gaps(merged)
    return filter_open_gaps(merged)


def format_gaps_revise_note(
    gaps: list[dict[str, Any]] | None,
    *,
    review_excerpt: str = "",
) -> str:
    """将 L4 gaps 格式化为改稿说明，供 revise_note 注入。"""
    rows = filter_open_gaps([g for g in (gaps or []) if isinstance(g, dict)])
    lines = ["请按以下审阅差距修改本章正文（输出完整改稿）：", ""]
    if rows:
        for g in rows:
            sev = "必须" if str(g.get("severity") or "").lower() == "hard" else "建议"
            ref = str(g.get("rule_ref") or "").strip()
            desc = str(g.get("description") or ref or "未说明").strip()
            lines.append(f"- [{sev}] {ref}: {desc}")
    excerpt = (review_excerpt or "").strip()
    if excerpt:
        lines.extend(["", "## 审阅摘要", excerpt[:2000]])
    if len(lines) <= 2 and not excerpt:
        lines.append("请对照已注入的审阅标准，修正本章未达标项。")
    return "\n".join(lines).strip()


def criteria_gaps_appendix() -> str:
    """注入审阅 user 上下文，引导 LLM 输出可解析 JSON。"""
    return (
        "## 结构化差距（报告末尾必填）\n"
        "在审阅报告最后附 **唯一** JSON 代码块，仅列**未达标**项：\n"
        "```json\n"
        '{"gaps":[{"rule_ref":"global:规则id","description":"具体差距","severity":"hard|soft"}]}\n'
        "```\n"
        "rule_ref 必须来自上文审阅标准中的 `[ref]`；无差距则 `{\"gaps\":[]}`。"
    )
