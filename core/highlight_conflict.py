"""L5a 正向案例入库前的口味库冲突检测。"""

from __future__ import annotations

from typing import Any

from core import taste


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def check_highlight_conflicts(
    *,
    book_id: str,
    text: str,
    annotation: str = "",
    book_dir=None,
) -> dict[str, Any]:
    """与 global rules / avoid_patterns / 本书 rules 做轻量比对。"""
    conflicts: list[dict[str, str]] = []
    snippet = _norm(text)
    note = _norm(annotation)
    if not snippet and not note:
        return {"ok": True, "conflicts": [], "has_conflict": False}

    global_doc = taste.load_global()
    for row in global_doc.get("rules") or []:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        weight = str(row.get("weight") or "soft").lower()
        c = _norm(content)
        if weight == "hard" and c and (c in snippet or c in note):
            conflicts.append({
                "kind": "rule_hard",
                "message": f"与硬性规则冲突：{content[:80]}",
                "ref": content[:120],
            })
        if "避免" in content or weight == "hard":
            for part in content.replace("避免", "").split("、"):
                p = _norm(part)
                if len(p) >= 4 and p in snippet:
                    conflicts.append({
                        "kind": "avoid",
                        "message": f"可能违反：{content[:80]}",
                        "ref": content[:120],
                    })

    prefs = global_doc.get("preferences") or {}
    if isinstance(prefs, dict):
        for pat in prefs.get("avoid_patterns") or []:
            p = _norm(str(pat))
            if len(p) >= 2 and p in snippet:
                conflicts.append({
                    "kind": "avoid_pattern",
                    "message": f"命中 avoid 模式：{pat}",
                    "ref": str(pat)[:120],
                })

    if book_dir is not None:
        book_taste = taste.load_book_taste(book_dir)
        for row in book_taste.get("rules") or []:
            if not isinstance(row, dict):
                continue
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            c = _norm(content)
            if len(c) >= 4 and c in snippet:
                conflicts.append({
                    "kind": "book_rule",
                    "message": f"与本书规则重复/矛盾：{content[:80]}",
                    "ref": content[:120],
                })

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in conflicts:
        key = item.get("ref") or item.get("message") or ""
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return {
        "ok": True,
        "conflicts": unique[:8],
        "has_conflict": len(unique) > 0,
    }
