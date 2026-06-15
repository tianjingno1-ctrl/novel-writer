"""Plan 场景与正文章号映射（向导 / Gate 共用，非批量专用）。"""

from __future__ import annotations

import re

from core.data import novel_data

_CHAPTER_SPAN_RE = re.compile(r"第(\d+)\s*[–\-—~～]\s*(\d+)\s*章")
_CHAPTER_SINGLE_RE = re.compile(r"第(\d+)\s*章")


def parse_chapter_spans(text: str) -> list[tuple[int, int]]:
    """从场景 summary/beat 等文本解析章号区间。"""
    spans: list[tuple[int, int]] = []
    body = text or ""
    for m in _CHAPTER_SPAN_RE.finditer(body):
        a, b = int(m.group(1)), int(m.group(2))
        if a > b:
            a, b = b, a
        spans.append((a, b))
    for m in _CHAPTER_SINGLE_RE.finditer(body):
        n = int(m.group(1))
        if not any(a <= n <= b for a, b in spans):
            spans.append((n, n))
    return spans


def _scene_chapter_span(scene: dict) -> tuple[int, int] | None:
    lo: int | None = None
    hi: int | None = None
    for field in ("summary", "beat", "title"):
        for a, b in parse_chapter_spans(str(scene.get(field) or "")):
            lo = a if lo is None else min(lo, a)
            hi = b if hi is None else max(hi, b)
    if lo is None or hi is None:
        return None
    return lo, hi


def resolve_beat_for_prose_chapter(chapter_num: int) -> dict | None:
    """将正文章号映射到 plan 场景 Beat（支持「第1-2章」跨章 Beat）。"""
    if chapter_num < 1:
        return None
    plan = novel_data.load_plan()
    matches: list[tuple[int, int, dict]] = []
    for ch_data in plan.get("chapters", {}).values():
        for scene in ch_data.get("scenes") or []:
            span = _scene_chapter_span(scene)
            if not span:
                continue
            a, b = span
            if a <= chapter_num <= b:
                matches.append((a, b, scene))
    if not matches:
        key = str(chapter_num)
        ch = plan.get("chapters", {}).get(key) or {}
        scenes = ch.get("scenes") or []
        if scenes:
            scene = scenes[0]
            beat = (scene.get("beat") or "").strip()
            if beat:
                return {
                    "scene_id": scene.get("id") or "",
                    "scene_title": scene.get("title") or "",
                    "beat": beat,
                    "pace": scene.get("pace") or "",
                    "span_from": chapter_num,
                    "span_to": chapter_num,
                    "chapter_index_in_span": 1,
                    "span_chapters": 1,
                }
        return None
    matches.sort(key=lambda x: (x[1] - x[0], x[0]))
    span_from, span_to, scene = matches[0]
    beat = (scene.get("beat") or "").strip()
    if not beat:
        return None
    return {
        "scene_id": scene.get("id") or "",
        "scene_title": scene.get("title") or "",
        "beat": beat,
        "pace": scene.get("pace") or "",
        "span_from": span_from,
        "span_to": span_to,
        "chapter_index_in_span": chapter_num - span_from + 1,
        "span_chapters": span_to - span_from + 1,
    }
