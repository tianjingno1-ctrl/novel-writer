"""章审阅侧车 review.json（L4 轮次 + judgment 留痕）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from infra import file_utils

JUDGMENT_PASS = frozenset({"pass", "passed", "accepted", "accept", "通过"})
JUDGMENT_FAIL = frozenset({"fail", "failed", "rejected", "reject", "needs_revision", "不通过", "拒稿"})


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def review_path(book_dir: Path, chapter_num: int) -> Path:
    return book_dir / "chapters" / f"ch{chapter_num:03d}" / "review.json"


def _sanitize_gaps(gaps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    from core import review_gaps

    return review_gaps.filter_open_gaps(gaps)


def _sanitize_review_doc(doc: dict[str, Any]) -> dict[str, Any]:
    rounds = doc.get("rounds")
    if not isinstance(rounds, list):
        return doc
    for row in rounds:
        if not isinstance(row, dict):
            continue
        row["gaps"] = _sanitize_gaps(row.get("gaps"))
    return doc


def load_review(book_dir: Path, chapter_num: int) -> dict[str, Any] | None:
    path = review_path(book_dir, chapter_num)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    return _sanitize_review_doc(raw)


def _save_review(book_dir: Path, doc: dict[str, Any]) -> dict[str, Any]:
    num = int(doc.get("chapter_num") or 0)
    if num < 1:
        raise ValueError("chapter_num 须 ≥ 1")
    path = review_path(book_dir, num)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_utils.atomic_write_text(
        path,
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    return doc


def normalize_judgment(outcome: str | None) -> str:
    raw = (outcome or "").strip().lower()
    if raw in JUDGMENT_PASS:
        return "pass"
    if raw in JUDGMENT_FAIL:
        return "fail"
    if raw in ("pending", ""):
        return "pending"
    return raw or "pending"


def append_round(
    book_dir: Path,
    chapter_num: int,
    *,
    quality_log_id: str,
    profile_id: str = "",
    revise: bool = False,
    rewrite_only: bool = False,
    review_excerpt: str = "",
    gaps: list[dict[str, Any]] | None = None,
    judgment: str = "pending",
    issue_tags: list[str] | None = None,
    user_note: str = "",
) -> dict[str, Any]:
    """追加一轮 L4 审阅记录。"""
    log_id = (quality_log_id or "").strip()
    if not log_id:
        raise ValueError("quality_log_id 不能为空")

    doc = load_review(book_dir, chapter_num) or {
        "chapter_num": chapter_num,
        "rounds": [],
    }
    rounds: list[dict[str, Any]] = list(doc.get("rounds") or [])
    round_no = len(rounds) + 1
    rounds.append({
        "round": round_no,
        "version": f"v{round_no}",
        "gaps": _sanitize_gaps(gaps),
        "judgment": normalize_judgment(judgment),
        "issue_tags": [str(t).strip() for t in (issue_tags or []) if str(t).strip()],
        "quality_log_id": log_id,
        "user_note": (user_note or "").strip()[:500],
        "profile_id": (profile_id or "").strip(),
        "revise": bool(revise),
        "rewrite_only": bool(rewrite_only),
        "review_excerpt": (review_excerpt or "").strip()[:2000],
        "ts": _now(),
    })
    doc["rounds"] = rounds[-20:]
    doc["chapter_num"] = chapter_num
    return _save_review(book_dir, doc)


def update_round_by_log_id(
    book_dir: Path,
    chapter_num: int,
    quality_log_id: str,
    *,
    judgment: str,
    issue_tags: list[str] | None = None,
    user_note: str = "",
) -> dict[str, Any] | None:
    """judgment 录入时回写对应轮次。"""
    log_id = (quality_log_id or "").strip()
    if not log_id or chapter_num < 1:
        return None
    doc = load_review(book_dir, chapter_num)
    if not doc:
        return None
    rounds: list[dict[str, Any]] = list(doc.get("rounds") or [])
    updated = False
    for row in reversed(rounds):
        if not isinstance(row, dict):
            continue
        if str(row.get("quality_log_id") or "") != log_id:
            continue
        row["judgment"] = normalize_judgment(judgment)
        if issue_tags is not None:
            row["issue_tags"] = [
                str(t).strip() for t in issue_tags if str(t).strip()
            ]
        if user_note:
            row["user_note"] = user_note.strip()[:500]
        row["judged_at"] = _now()
        updated = True
        break
    if not updated:
        return None
    doc["rounds"] = rounds
    return _save_review(book_dir, doc)


def list_rounds(book_dir: Path, chapter_num: int) -> list[dict[str, Any]]:
    doc = load_review(book_dir, chapter_num)
    if not doc:
        return []
    return list(doc.get("rounds") or [])
