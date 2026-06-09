"""章节正文纯文本处理（无路径、无 API，可单测）。"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

ApplyTitleFn: TypeAlias = Callable[[int, str | None], str | None]

DISCUSSION_PREFIXES = ("[讨论]", "[问答]", "[建议]", "[说明]", "[分析]")
META_LINE_PREFIXES = ("以下是", "我建议", "可以考虑", "总结：", "分析：", "注意：", "说明：")
APPEND_INSTRUCTION_KEYWORDS = (
    "续写",
    "接着写",
    "继续写",
    "接下去",
    "往后写",
    "续上一段",
    "往下写",
)

_CHAPTER_MD_HEADER_RE = re.compile(
    r"^#\s*第(?:\d+|[一二三四五六七八九十百零]+)章"
    r"(?:\s*[·•\-—]\s*|\s+)(.+?)\s*$"
)


def list_chapter_files(chapters_dir: Path) -> list[tuple[int, Path]]:
    chapters: list[tuple[int, Path]] = []
    for p in chapters_dir.glob("ch*.md"):
        m = re.match(r"ch(\d+)\.md$", p.name, re.IGNORECASE)
        if m:
            chapters.append((int(m.group(1)), p))
    chapters.sort(key=lambda x: x[0])
    return chapters


def apply_chapter_title(chapter_num: int, title: str | None) -> str | None:
    """将标题同步到 plan.json（并确保章节规划存在）。"""
    from core.data import novel_data

    if not title:
        return None
    clean = title.strip().strip("《》「」\"' ")
    if not clean or clean in {f"第{chapter_num}章", f"第{chapter_cn(chapter_num)}章"}:
        return None
    if len(clean) > 48:
        clean = clean[:48].rstrip()
    novel_data.ensure_chapter_plan(chapter_num, title=clean)
    novel_data.update_chapter_title(chapter_num, clean)
    return clean


def chapter_cn(n: int) -> str:
    """1–99 章中文序数（用于正文文件标题行）。"""
    if n <= 0:
        return str(n)
    if n < 10:
        return "一二三四五六七八九"[n - 1]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + chapter_cn(n - 10)
    if n % 10 == 0:
        return chapter_cn(n // 10) + "十"
    return chapter_cn(n // 10) + "十" + chapter_cn(n % 10)


def sanitize_chapter_text(text: str) -> str:
    if not text:
        return text
    return html.unescape(text)


def should_append_to_chapter(reply: str) -> bool:
    stripped = reply.strip()
    if not stripped or len(stripped) < 30:
        return False
    if any(stripped.startswith(p) for p in DISCUSSION_PREFIXES):
        return False
    if any(stripped.startswith(p) for p in META_LINE_PREFIXES):
        return False
    if stripped.startswith("✅"):
        return False
    first_line = stripped.split("\n", 1)[0].strip()
    if first_line.endswith("：") and len(first_line) < 24:
        return False
    return True


def instruction_save_mode(instruction: str) -> str:
    text = (instruction or "").strip()
    if any(k in text for k in APPEND_INSTRUCTION_KEYWORDS):
        return "append"
    return "replace"


def parse_chapter_header_line(line: str) -> str | None:
    m = _CHAPTER_MD_HEADER_RE.match((line or "").strip())
    if not m:
        return None
    title = m.group(1).strip().strip("《》「」\"' ")
    return title or None


def split_chapter_markdown_header(text: str) -> tuple[str | None, str]:
    stripped = (text or "").strip()
    if not stripped:
        return None, ""
    lines = stripped.splitlines()
    if not lines[0].startswith("#"):
        return None, stripped
    title = parse_chapter_header_line(lines[0])
    i = 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    body = "\n".join(lines[i:]).strip()
    return title, body


def extract_chapter_title_from_reply(text: str) -> tuple[str | None, str]:
    stripped = (text or "").strip()
    if not stripped:
        return None, ""
    m = re.match(r"^【章节标题】\s*(.+?)(?:\n\n|\n|$)", stripped, re.DOTALL)
    if m:
        title = m.group(1).strip().split("\n", 1)[0].strip()
        title = title.strip("《》「」\"' ")
        body = stripped[m.end() :].strip()
        return (title or None), body
    title, body = split_chapter_markdown_header(stripped)
    if title:
        return title, body
    return None, stripped


def strip_chapter_file_header(text: str) -> str:
    _, body = split_chapter_markdown_header(text or "")
    return body


def format_chapter_file(
    chapter_num: int, body: str, *, title: str | None = None
) -> str:
    body = body.strip()
    if not body:
        return ""
    parsed_title, body = extract_chapter_title_from_reply(body)
    md_title, body = split_chapter_markdown_header(body)
    use_title = (title or parsed_title or md_title or "").strip()
    header = f"# 第{chapter_num}章"
    if use_title and use_title not in {
        f"第{chapter_num}章",
        f"第{chapter_cn(chapter_num)}章",
    }:
        header = f"{header} · {use_title}"
    return f"{header}\n\n{body}\n"


def prepare_chapter_body_from_reply(
    reply: str,
    chapter_num: int,
    apply_title: ApplyTitleFn,
) -> tuple[str | None, str]:
    reply = sanitize_chapter_text(reply)
    title, body = extract_chapter_title_from_reply(reply)
    applied = apply_title(chapter_num, title)
    if not applied:
        md_title, body = split_chapter_markdown_header(body)
        applied = apply_title(chapter_num, md_title)
    return applied, body


def write_chapter_from_review_text(
    store: object,
    chapter_num: int,
    body: str,
    *,
    apply_title: ApplyTitleFn,
    after_write: Callable[[int], None] | None = None,
) -> dict:
    """将审阅/改稿正文解析后写入章节文件。"""
    parsed = sanitize_chapter_text((body or "").strip())
    if not parsed:
        return {"ok": False, "error": "改稿正文为空"}
    if not parsed.strip().startswith("【章节标题】"):
        parsed = f"【章节标题】\n{parsed}"
    title, chapter_body = prepare_chapter_body_from_reply(
        parsed, chapter_num, apply_title
    )
    chapter_file = format_chapter_file(chapter_num, chapter_body, title=title)
    store.write_chapter(chapter_num, chapter_file, append=False)
    if after_write:
        after_write(chapter_num)
    return {
        "ok": True,
        "chapter_num": chapter_num,
        "chapter_title": title,
        "chars": len(chapter_file),
    }
