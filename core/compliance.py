"""平台合规预检：AI 腔启发式 + 全书投递前扫描（E4c）。"""

from __future__ import annotations

import re
from typing import Any

# 常见 AI 腔 / 文学腔短语（出现密度越高风险越大）
AI_TONE_PHRASES: tuple[str, ...] = (
    "仿佛",
    "不禁",
    "微微",
    "缓缓",
    "竟然",
    "内心深处",
    "宛如",
    "犹如",
    "涌上心头",
    "说不清",
    "某种",
    "莫名",
    "悄然",
    "映入眼帘",
    "嘴角微微",
    "眼眸",
    "空气仿佛",
    "时间仿佛",
    "心中一紧",
    "心头一震",
)

# 平台 AI 腔风险阈值（score ≥ 阈值则 L1b 硬拦截）
PLATFORM_AI_THRESHOLDS: dict[str, float] = {
    "tomato": 0.38,
    "qimao": 0.42,
    "jjwxc": 0.48,
    "general": 0.55,
}

DEFAULT_THRESHOLD = 0.45


def resolve_platform_slug(
    *,
    plan_meta: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
) -> str:
    meta = plan_meta if isinstance(plan_meta, dict) else {}
    proj = project if isinstance(project, dict) else {}
    raw = str(meta.get("platform") or proj.get("platform") or "tomato").strip().lower()
    if raw in PLATFORM_AI_THRESHOLDS:
        return raw
    return "general"


def ai_tone_threshold(platform: str) -> float:
    return PLATFORM_AI_THRESHOLDS.get((platform or "").strip().lower(), DEFAULT_THRESHOLD)


def score_ai_tone(content: str) -> dict[str, Any]:
    """返回 0~1 风险分 + 命中片段。"""
    text = content or ""
    length = max(len(re.sub(r"\s+", "", text)), 1)
    hits: list[dict[str, Any]] = []
    total = 0
    for phrase in AI_TONE_PHRASES:
        count = text.count(phrase)
        if count <= 0:
            continue
        total += count
        idx = text.find(phrase)
        start = max(0, idx - 12)
        end = min(len(text), idx + len(phrase) + 24)
        hits.append({
            "phrase": phrase,
            "count": count,
            "snippet": text[start:end].replace("\n", " ").strip(),
        })
    hits.sort(key=lambda h: h["count"], reverse=True)
    # 每 800 字出现 1 次 AI 短语 ≈ 0.25 分，上限 1
    score = min(1.0, round(total * 800 / length * 0.25, 3))
    level = "low"
    if score >= 0.55:
        level = "high"
    elif score >= 0.32:
        level = "medium"
    return {
        "score": score,
        "level": level,
        "hit_count": total,
        "hits": hits[:8],
    }


def check_ai_tone_for_platform(
    content: str,
    *,
    platform: str,
) -> dict[str, Any]:
    """L1b 并行项：AI 腔是否超过平台阈值。"""
    tone = score_ai_tone(content)
    threshold = ai_tone_threshold(platform)
    passed = tone["score"] < threshold
    return {
        **tone,
        "platform": platform,
        "threshold": threshold,
        "passed": passed,
    }


def scan_chapters_compliance(
    chapters: list[tuple[int, str]],
    *,
    platform: str,
) -> dict[str, Any]:
    """E4c：全书合规预检（启发式，无需 LLM）。"""
    threshold = ai_tone_threshold(platform)
    chapter_rows: list[dict[str, Any]] = []
    high_risk: list[dict[str, Any]] = []
    scores: list[float] = []
    for num, body in chapters:
        tone = score_ai_tone(body)
        scores.append(tone["score"])
        row = {
            "chapter_num": num,
            "ai_tone_score": tone["score"],
            "ai_tone_level": tone["level"],
            "top_hits": tone["hits"][:3],
        }
        chapter_rows.append(row)
        if tone["score"] >= threshold:
            high_risk.append({
                **row,
                "snippets": [h.get("snippet") for h in tone["hits"][:2]],
            })
    avg = round(sum(scores) / len(scores), 3) if scores else 0.0
    book_level = "low"
    if avg >= threshold or len(high_risk) >= max(1, len(chapters) // 3):
        book_level = "high"
    elif avg >= threshold * 0.75:
        book_level = "medium"
    return {
        "ok": True,
        "platform": platform,
        "threshold": threshold,
        "risk_score": avg,
        "risk_level": book_level,
        "chapter_count": len(chapters),
        "high_risk_chapters": high_risk,
        "chapters": chapter_rows,
        "can_submit": book_level != "high",
    }
