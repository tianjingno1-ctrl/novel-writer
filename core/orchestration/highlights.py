"""L5a 亮点提取与写入。"""

from __future__ import annotations

import re
from typing import Any

from core import taste

_POSITIVE_OUTCOMES = frozenset({"accepted", "pass", "passed", "通过"})


def is_positive_outcome(outcome: str) -> bool:
    return (outcome or "").strip().lower() in {o.lower() for o in _POSITIVE_OUTCOMES}


def extract_snippets_from_review(text: str, *, limit: int = 2) -> list[dict[str, str]]:
    """从审阅报告轻量提取可作正向案例的片段。"""
    raw = (text or "").strip()
    if not raw:
        return []
    out: list[dict[str, str]] = []
    for m in re.finditer(r"[「『\"](.{20,200}?)[」』\"]", raw):
        snippet = m.group(1).strip()
        if snippet:
            out.append({"text": snippet, "annotation": "审阅报告中引用的有效片段"})
        if len(out) >= limit:
            return out
    for block in re.split(r"\n\s*\n", raw):
        s = block.strip().lstrip("-*·#").strip()
        if 40 <= len(s) <= 400 and any(k in s for k in ("钩子", "节奏", "好", "有效", "亮点", "到位")):
            out.append({"text": s[:300], "annotation": "审阅报告中的正向描述"})
            if len(out) >= limit:
                break
    return out


def push_on_review_pass(
    *,
    book_id: str,
    chapter_num: int,
    review_body: str = "",
    note: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any] | None:
    """审阅通过时写入 1 条正向案例（L5a）。"""
    annotation = (note or "").strip()
    text = ""
    if annotation and len(annotation) >= 4:
        text = annotation[:500]
        annotation = "用户标注亮点"
    else:
        candidates = extract_snippets_from_review(review_body)
        if candidates:
            text = candidates[0]["text"]
            annotation = candidates[0].get("annotation") or "审阅通过"
    if not text:
        return None
    result = taste.push_highlight_to_taste(
        book_id=book_id,
        chapter_num=chapter_num,
        text=text,
        annotation=annotation,
        tags=tags or ["hook_strong"],
    )
    return result
