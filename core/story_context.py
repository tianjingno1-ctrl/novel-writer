"""写作/审阅用故事背景：跳过未填写的 world 占位模板，改用 plan.meta。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import plan_product
from core import project_lifecycle

# 与 app/bootstrap_data.py 旧版 world 模板对齐；≥2 命中视为占位
WORLD_PLACEHOLDER_MARKERS = (
    "绑定系统",
    "穿越各个世界完成任务",
    "【女主名】",
    "**类型**：快穿",
    "世界一：【世界名】",
)


def is_unfilled_world_template(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 80:
        return True
    return sum(1 for m in WORLD_PLACEHOLDER_MARKERS if m in t) >= 2


def build_story_context_block(
    plan: dict[str, Any],
    world_text: str,
    *,
    chapter_num: int = 0,
    book_dir: Path | None = None,
) -> str:
    """审阅/预览用背景：已维护 world 用原文，否则用开书确认的 meta + 本章 plan。"""
    if not is_unfilled_world_template(world_text):
        return world_text.strip()

    meta = plan.get("meta") if isinstance(plan.get("meta"), dict) else {}
    lines = ["## 本书方向（开书确认 · 非 world 占位模板）"]
    for key, label in (
        ("title", "书名"),
        ("logline", "一句话"),
        ("sell_point", "卖点"),
        ("genre", "题材"),
        ("tone", "基调"),
    ):
        val = str(meta.get(key) or "").strip()
        if val:
            lines.append(f"- **{label}**：{val}")

    if chapter_num > 0:
        ch = plan_product.get_chapter_entry(plan, chapter_num) or {}
        title = str(ch.get("title") or "").strip()
        if title:
            lines.append(f"- **本章**：第{chapter_num}章《{title}》")
        hook = str(ch.get("hook") or "").strip()
        if hook:
            lines.append(f"- **章钩子**：{hook}")
        for scene in ch.get("scenes") or []:
            if isinstance(scene, dict) and scene.get("beat"):
                lines.append(f"- **Scene Beat**：{str(scene['beat'])[:800]}")
                break

    if book_dir is not None:
        try:
            proj = project_lifecycle.load_project(book_dir)
            bt = str(proj.get("type") or "").strip()
            pf = str(proj.get("platform") or "").strip()
            if bt or pf:
                lines.append(f"- **书型/平台**：{bt or '—'} / {pf or '—'}")
        except (OSError, TypeError, ValueError):
            pass

    if len(lines) <= 1:
        return (
            "（world.md 仍为占位模板，且 plan.meta 无方向；"
            "请在开书向导或书籍档案填写设定后再审阅）"
        )
    return "\n".join(lines)
