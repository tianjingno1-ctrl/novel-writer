"""L1b 机器预检：字数 + 大纲关键词。"""

from __future__ import annotations

import re
from typing import Any

from core.plan_product import get_chapter_entry, get_meta


def _resolve_platform(plan: dict, project: dict | None = None) -> str:
    from core import compliance

    return compliance.resolve_platform_slug(
        plan_meta=get_meta(plan),
        project=project or {},
    )


def _count_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _beat_keywords(plan: dict, chapter_num: int) -> list[str]:
    ch = get_chapter_entry(plan, chapter_num)
    if not ch:
        return []
    parts: list[str] = []
    hook = str(ch.get("hook") or "").strip()
    if len(hook) >= 4:
        parts.append(hook)
    for scene in ch.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        beat = str(scene.get("beat") or "").strip()
        if not beat:
            continue
        for token in re.split(r"[，。；、\n【】]", beat):
            t = token.strip()
            if len(t) >= 2:
                parts.append(t)
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:12]


def run_precheck(
    *,
    chapter_num: int,
    content: str,
    plan: dict,
    min_ratio: float = 0.85,
    max_ratio: float = 1.25,
    platform: str = "",
    project: dict | None = None,
    check_ai_tone: bool = True,
) -> dict[str, Any]:
    """返回 ok + issues；不达标时不应进入用户预览。"""
    issues: list[dict[str, Any]] = []
    ch = get_chapter_entry(plan, chapter_num)
    target = int((ch or {}).get("word_count_target") or 0)
    count = _count_chars(content)

    if target > 0:
        low = int(target * min_ratio)
        high = int(target * max_ratio)
        if count < low:
            issues.append({
                "code": "word_count_low",
                "severity": "hard",
                "message": f"字数 {count} 低于目标 {target} 的 {int(min_ratio*100)}%（至少 {low}）",
            })
        elif count > high:
            issues.append({
                "code": "word_count_high",
                "severity": "soft",
                "message": f"字数 {count} 超过目标 {target} 的 {int(max_ratio*100)}%（建议 ≤ {high}）",
            })
    elif count < 200:
        issues.append({
            "code": "word_count_too_short",
            "severity": "hard",
            "message": f"正文字数过少（{count}），疑似未写完",
        })

    keywords = _beat_keywords(plan, chapter_num)
    if keywords:
        missing = [kw for kw in keywords[:6] if kw not in content]
        if len(missing) >= max(2, len(keywords[:6]) // 2 + 1):
            issues.append({
                "code": "outline_keywords_missing",
                "severity": "hard",
                "message": f"正文未覆盖大纲关键词：{', '.join(missing[:5])}",
                "missing": missing[:8],
            })

    ai_tone: dict[str, Any] | None = None
    if check_ai_tone and content.strip():
        from core import compliance

        pf = platform.strip() or _resolve_platform(plan, project)
        ai_tone = compliance.check_ai_tone_for_platform(content, platform=pf)
        if not ai_tone.get("passed"):
            top = (ai_tone.get("hits") or [{}])[0]
            snippet = str(top.get("snippet") or top.get("phrase") or "")
            issues.append({
                "code": "ai_tone_high",
                "severity": "hard",
                "message": (
                    f"AI 腔风险 {ai_tone['score']:.2f} 超过平台 {pf} 阈值 "
                    f"{ai_tone['threshold']:.2f}"
                    + (f"（如：{snippet[:40]}…）" if snippet else "")
                ),
                "ai_tone": ai_tone,
            })

    hard = [i for i in issues if i.get("severity") == "hard"]
    return {
        "ok": len(hard) == 0,
        "chapter_num": chapter_num,
        "word_count": count,
        "word_count_target": target or None,
        "platform": platform.strip() or _resolve_platform(plan, project),
        "ai_tone": ai_tone,
        "issues": issues,
        "should_rewrite": len(hard) > 0,
    }
