"""从 cost_log.jsonl 按书 / 步骤聚合费用。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def summarize_cost_by_book(path: Path) -> dict[str, Any]:
    """读取 JSONL，按 book_id 与 tag 求和 cost，书按 total_cost 降序。"""
    tag_totals: dict[str, dict[str, float]] = {}

    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            try:
                cost = float(record.get("cost", 0))
            except (TypeError, ValueError):
                continue
            book_id = str(record.get("book_id") or "").strip()
            tag = str(record.get("tag") or "unknown").strip() or "unknown"
            book_tags = tag_totals.setdefault(book_id, {})
            book_tags[tag] = book_tags.get(tag, 0.0) + cost

    by_book: list[dict[str, Any]] = []
    for book_id, tags in tag_totals.items():
        steps = [
            {"tag": tag, "cost": round(amount, 6)}
            for tag, amount in tags.items()
        ]
        steps.sort(key=lambda row: row["cost"], reverse=True)
        total_cost = round(sum(row["cost"] for row in steps), 6)
        by_book.append({
            "book_id": book_id,
            "total_cost": total_cost,
            "steps": steps,
        })

    by_book.sort(key=lambda row: row["total_cost"], reverse=True)
    return {"ok": True, "by_book": by_book}
