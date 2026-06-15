#!/usr/bin/env python3
"""一次性：将短篇中「已有正文但仍 drafting」的章标为 approved。

默认 dry-run，仅打印；加 --apply 才写 plan.json。

用法：
  python scripts/migrate_short_drafting_approved.py
  python scripts/migrate_short_drafting_approved.py --book-id 新书-b4474569
  python scripts/migrate_short_drafting_approved.py --apply
  python scripts/migrate_short_drafting_approved.py --apply --min-chars 200
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import chapters as chapter_text  # noqa: E402
from core import chapter_io  # noqa: E402
from core.data import book_context  # noqa: E402


def _read_project_type(book_dir: Path) -> str:
    path = book_dir / "project.json"
    if not path.is_file():
        return "novel"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "novel"
    return str(raw.get("type") or "novel").strip().lower()


def _chapter_body_chars(book_dir: Path, chapter_num: int) -> int:
    path = book_dir / "chapters" / f"ch{chapter_num:03d}.md"
    if not path.is_file():
        return 0
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(chapter_text.strip_chapter_file_header(raw).strip())


def _load_plan_chapters(book_dir: Path) -> dict[int, dict]:
    plan_path = book_dir / "plan.json"
    if not plan_path.is_file():
        return {}
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    chapters = plan.get("chapters")
    if isinstance(chapters, dict):
        out: dict[int, dict] = {}
        for key, row in chapters.items():
            try:
                num = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(row, dict):
                out[num] = row
        return out
    if isinstance(chapters, list):
        out = {}
        for row in chapters:
            if not isinstance(row, dict):
                continue
            try:
                num = int(row.get("num") or 0)
            except (TypeError, ValueError):
                continue
            if num > 0:
                out[num] = row
        return out
    return {}


def _apply_approved(book_dir: Path, chapter_nums: list[int]) -> None:
    plan_path = book_dir / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    chapters = plan.setdefault("chapters", {})
    if not isinstance(chapters, dict):
        raise ValueError(f"{book_dir.name}: plan.chapters 不是 dict，请手动处理")
    for num in chapter_nums:
        key = str(num)
        row = chapters.setdefault(key, {"num": num})
        if not isinstance(row, dict):
            row = {"num": num}
            chapters[key] = row
        row["status"] = "approved"
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def scan_books(
    *,
    book_id: str = "",
    min_chars: int,
    apply: bool,
) -> int:
    books_dir = book_context.BOOKS_DIR
    if not books_dir.is_dir():
        print(f"书库不存在: {books_dir}", file=sys.stderr)
        return 1

    targets = sorted(books_dir.iterdir()) if not book_id else [books_dir / book_id]
    changed_total = 0

    for book_dir in targets:
        if not book_dir.is_dir():
            if book_id:
                print(f"书籍不存在: {book_dir}", file=sys.stderr)
                return 1
            continue
        if _read_project_type(book_dir) != "short":
            continue

        rows = _load_plan_chapters(book_dir)
        if not rows:
            continue

        to_fix: list[int] = []
        for num in sorted(rows):
            status = str(rows[num].get("status") or "pending").strip().lower()
            if status == "approved":
                continue
            if status != "drafting":
                continue
            chars = _chapter_body_chars(book_dir, num)
            if chars < min_chars:
                continue
            to_fix.append(num)

        if not to_fix:
            continue

        print(f"[{book_dir.name}] drafting → approved: 第 {', '.join(str(n) for n in to_fix)} 章")
        changed_total += len(to_fix)
        if apply:
            _apply_approved(book_dir, to_fix)
            print(f"  ✓ 已写入 plan.json")

    mode = "已应用" if apply else "dry-run（未写盘）"
    print(f"\n合计 {changed_total} 章 · {mode}")
    if not apply and changed_total:
        print("确认后请加 --apply 执行")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", default="", help="仅处理指定书 id")
    parser.add_argument(
        "--min-chars",
        type=int,
        default=chapter_io.MIN_CHAPTER_BODY_CHARS,
        help=f"正文最少字数（默认 {chapter_io.MIN_CHAPTER_BODY_CHARS}）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="写 plan.json（默认仅打印）",
    )
    args = parser.parse_args()
    raise SystemExit(
        scan_books(
            book_id=args.book_id.strip(),
            min_chars=max(1, args.min_chars),
            apply=args.apply,
        )
    )


if __name__ == "__main__":
    main()
