# 口味库 CRUD：global.json + 本书 taste.json、规则 merge、拆文导入、L5a 亮点与写作上下文 taste 块；不管 L4 RuleRef 解析。
"""口味库：全局偏好 + 本书覆盖 + 事件流 + LLM 上下文块。"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from infra import file_utils

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parents[1]
TASTE_DIR = _BASE / "library" / "taste"
GLOBAL_FILE = TASTE_DIR / "global.json"
EVENTS_FILE = TASTE_DIR / "events.jsonl"
BOOK_TASTE_FILENAME = "taste.json"

_MAX_EVENTS = 2000
_MAX_EVENT_BODY = 4000

_lock = threading.Lock()

# 标准问题标签（可扩展；自由文本 tag 也接受）
ISSUE_TAG_LABELS: dict[str, str] = {
    "hook_weak": "钩子弱/开头慢",
    "hook_strong": "钩子强",
    "ai_tone": "AI味重",
    "pacing_slow": "节奏拖",
    "pacing_fast": "节奏合适",
    "character_off": "人设不对",
    "emotion_flat": "情绪 flat/不落地",
    "dialogue_stiff": "对话假",
    "structure_good": "结构好",
    "payoff_good": "爽点到位",
    "platform_mismatch": "不符合平台",
    "deconstruct_pattern": "拆文规律",
    "submission_reject": "投递被拒",
    "submission_pass": "投递通过",
}

DEFAULT_PREFERENCES: dict[str, Any] = {
    "likes": [],
    "dislikes": [],
    "hook_patterns": [],
    "avoid_patterns": [],
    "platform_notes": "",
    "style_notes": "",
    "review_notes": "",
}

DEFAULT_GLOBAL: dict[str, Any] = {
    "version": 1,
    "updated_at": "",
    "preferences": DEFAULT_PREFERENCES.copy(),
    "tag_stats": {},
    "rules": [],
    "examples": [],
}


def _rule_id() -> str:
    return f"rule-{uuid.uuid4().hex[:8]}"


def _example_id() -> str:
    return f"ex-{uuid.uuid4().hex[:8]}"


def migrate_global_v1_to_v2(doc: dict[str, Any]) -> dict[str, Any]:
    if int(doc.get("version") or 1) >= 2:
        doc.setdefault("rules", [])
        doc.setdefault("examples", [])
        return doc
    prefs = doc.get("preferences") or {}
    rules: list[dict[str, Any]] = list(doc.get("rules") or [])
    seen = {str(r.get("content", "")).strip() for r in rules if isinstance(r, dict)}
    for item in prefs.get("hook_patterns") or []:
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        rules.append({
            "id": _rule_id(),
            "content": s,
            "weight": "soft",
            "source": "deconstruct",
            "tags": ["hook"],
            "created_at": _now(),
            "linked_examples": [],
        })
    for item in prefs.get("avoid_patterns") or []:
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        rules.append({
            "id": _rule_id(),
            "content": s,
            "weight": "soft",
            "source": "manual",
            "tags": ["avoid"],
            "created_at": _now(),
            "linked_examples": [],
        })
    doc["version"] = 2
    doc["rules"] = rules[:80]
    doc.setdefault("examples", [])
    return doc


def _sync_preferences_to_rules(doc: dict[str, Any]) -> None:
    prefs = doc.get("preferences") or {}
    rules: list[dict[str, Any]] = list(doc.get("rules") or [])
    seen = {str(r.get("content", "")).strip() for r in rules if isinstance(r, dict)}
    for item in list(prefs.get("hook_patterns") or []) + list(prefs.get("avoid_patterns") or []):
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        rules.append({
            "id": _rule_id(),
            "content": s,
            "weight": "soft",
            "source": "manual",
            "tags": ["hook"] if item in (prefs.get("hook_patterns") or []) else ["avoid"],
            "created_at": _now(),
            "linked_examples": [],
        })
    doc["rules"] = rules[:120]


def _normalize_global(doc: dict[str, Any]) -> dict[str, Any]:
    doc = migrate_global_v1_to_v2(doc)
    prefs = doc.get("preferences")
    if not isinstance(prefs, dict):
        doc["preferences"] = dict(DEFAULT_PREFERENCES)
    else:
        for key, default in DEFAULT_PREFERENCES.items():
            prefs.setdefault(key, default if not isinstance(default, list) else [])
    doc.setdefault("tag_stats", {})
    if not isinstance(doc.get("rules"), list):
        doc["rules"] = []
    if not isinstance(doc.get("examples"), list):
        doc["examples"] = []
    _sync_preferences_to_rules(doc)
    return doc


def _save_global_doc(doc: dict[str, Any]) -> dict[str, Any]:
    doc["updated_at"] = _now()
    ensure_taste_dir()
    file_utils.atomic_write_text(
        GLOBAL_FILE,
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    return doc


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _evt_id() -> str:
    return f"evt-{uuid.uuid4().hex[:10]}"


def ensure_taste_dir() -> Path:
    TASTE_DIR.mkdir(parents=True, exist_ok=True)
    if not GLOBAL_FILE.is_file():
        doc = {**DEFAULT_GLOBAL, "version": 2, "updated_at": _now()}
        doc["rules"] = []
        doc["examples"] = []
        file_utils.atomic_write_text(
            GLOBAL_FILE,
            json.dumps(doc, ensure_ascii=False, indent=2),
        )
    return TASTE_DIR


def tag_label(tag: str) -> str:
    t = (tag or "").strip()
    return ISSUE_TAG_LABELS.get(t, t)


def load_global() -> dict[str, Any]:
    ensure_taste_dir()
    if not GLOBAL_FILE.is_file():
        return {**DEFAULT_GLOBAL, "updated_at": _now()}
    try:
        raw = json.loads(GLOBAL_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    raw = _normalize_global(raw)
    return raw


def save_global(fields: dict[str, Any]) -> dict[str, Any]:
    doc = load_global()
    if "preferences" in fields and isinstance(fields["preferences"], dict):
        prefs = doc.setdefault("preferences", {})
        for key in DEFAULT_PREFERENCES:
            if key in fields["preferences"]:
                prefs[key] = fields["preferences"][key]
    if "rules" in fields and isinstance(fields["rules"], list):
        doc["rules"] = fields["rules"]
    if "examples" in fields and isinstance(fields["examples"], list):
        doc["examples"] = fields["examples"]
    _sync_preferences_to_rules(doc)
    return _save_global_doc(doc)


def add_rule(
    *,
    content: str,
    weight: str = "soft",
    source: str = "manual",
    tags: list[str] | None = None,
    linked_examples: list[str] | None = None,
) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise ValueError("规则 content 不能为空")
    w = (weight or "soft").strip().lower()
    if w not in ("hard", "soft"):
        w = "soft"
    doc = load_global()
    rules: list[dict] = list(doc.get("rules") or [])
    rule = {
        "id": _rule_id(),
        "content": text[:500],
        "weight": w,
        "source": (source or "manual").strip(),
        "tags": [str(t).strip() for t in (tags or []) if str(t).strip()][:8],
        "created_at": _now(),
        "linked_examples": list(linked_examples or [])[:8],
    }
    rules.append(rule)
    doc["rules"] = rules[-120:]
    _save_global_doc(doc)
    return rule


def _remove_rule_content_from_preferences(doc: dict[str, Any], content: str) -> None:
    text = (content or "").strip()
    if not text:
        return
    prefs = doc.setdefault("preferences", {})
    for key in ("hook_patterns", "avoid_patterns"):
        items = prefs.get(key)
        if isinstance(items, list):
            prefs[key] = [x for x in items if str(x).strip() != text]


def delete_rule(rule_id: str) -> dict[str, Any] | None:
    """从 global.json rules 移除指定 id。"""
    rid = (rule_id or "").strip()
    if not rid:
        raise ValueError("rule_id 不能为空")
    doc = load_global()
    rules: list[dict] = list(doc.get("rules") or [])
    target: dict[str, Any] | None = None
    kept: list[dict] = []
    for row in rules:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        if row.get("id") == rid:
            target = row
        else:
            kept.append(row)
    if target is None:
        return None
    doc["rules"] = kept
    _remove_rule_content_from_preferences(doc, str(target.get("content") or ""))
    _save_global_doc(doc)
    return target


def localize_rule_to_book(rule_id: str, book_dir: Path) -> dict[str, Any]:
    """从 global 移除规则并写入本书 overrides.append_rules。"""
    rid = (rule_id or "").strip()
    if not rid:
        raise ValueError("rule_id 不能为空")
    if not book_dir:
        raise ValueError("book_dir 不能为空")

    doc = load_global()
    rules: list[dict] = list(doc.get("rules") or [])
    target: dict[str, Any] | None = None
    kept: list[dict] = []
    for row in rules:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        if row.get("id") == rid:
            target = dict(row)
        else:
            kept.append(row)
    if target is None:
        raise ValueError("规则不存在")

    doc["rules"] = kept
    _remove_rule_content_from_preferences(doc, str(target.get("content") or ""))
    _save_global_doc(doc)

    book_doc = _ensure_book_overrides(load_book_taste(book_dir))
    overrides = book_doc["overrides"]
    append_rules: list[dict] = [
        r for r in (overrides.get("append_rules") or [])
        if not (isinstance(r, dict) and r.get("id") == rid)
    ]
    append_rules.append({
        "id": rid,
        "content": str(target.get("content") or "").strip()[:500],
        "weight": target.get("weight") or "soft",
        "source": "localized",
        "tags": list(target.get("tags") or [])[:8],
        "created_at": target.get("created_at") or _now(),
        "linked_examples": list(target.get("linked_examples") or [])[:8],
    })
    overrides["append_rules"] = append_rules[-80:]
    book_doc["overrides"] = overrides
    book_dir.mkdir(parents=True, exist_ok=True)
    file_utils.atomic_write_text(
        book_taste_path(book_dir),
        json.dumps(book_doc, ensure_ascii=False, indent=2),
    )
    return {"rule": target, "book_taste": book_doc}


def add_example(
    *,
    example_type: str,
    text: str,
    annotation: str = "",
    source: str = "highlight",
    tags: list[str] | None = None,
    linked_rule: str = "",
    book_id: str = "",
    chapter_num: int = 0,
) -> dict[str, Any]:
    body = (text or "").strip()
    if not body:
        raise ValueError("example text 不能为空")
    typ = (example_type or "good").strip().lower()
    if typ not in ("good", "bad"):
        typ = "good"
    doc = load_global()
    examples: list[dict] = list(doc.get("examples") or [])
    ex = {
        "id": _example_id(),
        "type": typ,
        "text": body[:2000],
        "annotation": (annotation or "").strip()[:500],
        "tags": [str(t).strip() for t in (tags or []) if str(t).strip()][:8],
        "source": (source or "manual").strip(),
        "linked_rule": (linked_rule or "").strip(),
        "book_id": (book_id or "").strip(),
        "chapter_num": int(chapter_num) if chapter_num else 0,
        "created_at": _now(),
    }
    examples.append(ex)
    doc["examples"] = examples[-200:]
    _save_global_doc(doc)
    return ex


_MAX_BOOK_APPEND_EXAMPLES = 80
_CONTEXT_EXAMPLE_LIMIT = 5


def _ensure_book_overrides(doc: dict[str, Any]) -> dict[str, Any]:
    doc["version"] = max(int(doc.get("version") or 1), 2)
    overrides = doc.get("overrides")
    if not isinstance(overrides, dict):
        overrides = {}
    overrides.setdefault("rules", list(overrides.get("rules") or []))
    overrides.setdefault("append_rules", list(overrides.get("append_rules") or []))
    overrides.setdefault("append_examples", list(overrides.get("append_examples") or []))
    doc["overrides"] = overrides
    return doc


def _resolve_book_dir(book_id: str) -> Path | None:
    bid = (book_id or "").strip()
    if not bid:
        return None
    existing = _book_dir_for_id(bid)
    if existing is not None:
        return existing
    from core.data.book_context import BOOKS_DIR

    return BOOKS_DIR / bid


def _append_book_example(
    book_dir: Path,
    *,
    text: str,
    annotation: str = "",
    source: str = "highlight",
    tags: list[str] | None = None,
    chapter_num: int = 0,
) -> dict[str, Any]:
    body = (text or "").strip()
    if not body:
        raise ValueError("example text 不能为空")
    doc = _ensure_book_overrides(load_book_taste(book_dir))
    overrides = doc["overrides"]
    examples: list[dict] = list(overrides.get("append_examples") or [])
    ex = {
        "id": _example_id(),
        "type": "good",
        "text": body[:2000],
        "annotation": (annotation or "").strip()[:500],
        "tags": [str(t).strip() for t in (tags or []) if str(t).strip()][:8],
        "source": (source or "highlight").strip(),
        "chapter_num": int(chapter_num) if chapter_num else 0,
        "created_at": _now(),
    }
    examples.append(ex)
    overrides["append_examples"] = examples[-_MAX_BOOK_APPEND_EXAMPLES:]
    doc["overrides"] = overrides
    book_dir.mkdir(parents=True, exist_ok=True)
    file_utils.atomic_write_text(
        book_taste_path(book_dir),
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    return ex


def push_highlight_to_taste(
    *,
    book_id: str,
    chapter_num: int,
    text: str,
    annotation: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """L5a：有 book_id 时写入本书 taste.json overrides.append_examples，否则写 global.examples。"""
    tag_list = tags or ["hook_strong"]
    bid = (book_id or "").strip()
    book_dir = _resolve_book_dir(bid) if bid else None
    if book_dir is not None:
        ex = _append_book_example(
            book_dir,
            text=text,
            annotation=annotation,
            source="highlight",
            tags=tag_list,
            chapter_num=chapter_num,
        )
        scope = "book"
    else:
        ex = add_example(
            example_type="good",
            text=text,
            annotation=annotation,
            source="highlight",
            tags=tag_list,
            book_id=book_id,
            chapter_num=chapter_num,
        )
        scope = "global"
    eid = append_event(
        source="highlight",
        outcome="accepted",
        issue_tags=tag_list,
        note=(annotation or "审阅通过亮点")[:200],
        book_id=book_id,
        chapter_num=chapter_num,
        extra={"example_id": ex["id"], "scope": scope},
    )
    return {"example": ex, "event_id": eid, "scope": scope}


def book_taste_path(book_dir: Path) -> Path:
    return book_dir / BOOK_TASTE_FILENAME


def load_book_taste(book_dir: Path | None) -> dict[str, Any]:
    if not book_dir:
        return {"version": 1, "inherit_global": True, "preferences": {}, "notes": ""}
    path = book_taste_path(book_dir)
    if not path.is_file():
        return {"version": 1, "inherit_global": True, "preferences": {}, "notes": ""}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("version", 1)
    raw.setdefault("inherit_global", True)
    raw.setdefault("preferences", {})
    raw.setdefault("notes", "")
    if int(raw.get("version") or 1) >= 2:
        _ensure_book_overrides(raw)
    return raw


def save_book_taste(book_dir: Path, fields: dict[str, Any]) -> dict[str, Any]:
    doc = load_book_taste(book_dir)
    if "inherit_global" in fields:
        doc["inherit_global"] = bool(fields["inherit_global"])
    if "notes" in fields and fields["notes"] is not None:
        doc["notes"] = str(fields["notes"]).strip()[:2000]
    if "preferences" in fields and isinstance(fields["preferences"], dict):
        prefs = doc.setdefault("preferences", {})
        for key in DEFAULT_PREFERENCES:
            if key in fields["preferences"]:
                prefs[key] = fields["preferences"][key]
    book_dir.mkdir(parents=True, exist_ok=True)
    file_utils.atomic_write_text(
        book_taste_path(book_dir),
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    return doc


def merge_preferences(
    *,
    book_dir: Path | None = None,
) -> dict[str, Any]:
    """合并全局 + 本书偏好（列表去重合并，字符串本书优先）。"""
    global_doc = load_global()
    g_prefs = global_doc.get("preferences") or {}
    merged: dict[str, Any] = {
        key: (list(g_prefs.get(key) or []) if isinstance(DEFAULT_PREFERENCES.get(key), list) else str(g_prefs.get(key) or ""))
        for key in DEFAULT_PREFERENCES
    }
    book_doc = load_book_taste(book_dir)
    if book_doc.get("inherit_global", True) is False:
        merged = {key: ([] if isinstance(DEFAULT_PREFERENCES.get(key), list) else "") for key in DEFAULT_PREFERENCES}
    b_prefs = book_doc.get("preferences") or {}
    for key in DEFAULT_PREFERENCES:
        val = b_prefs.get(key)
        if val is None:
            continue
        if isinstance(merged[key], list) and isinstance(val, list):
            seen: set[str] = set()
            out: list[str] = []
            for item in list(val) + list(merged[key]):
                s = str(item).strip()
                if s and s not in seen:
                    seen.add(s)
                    out.append(s)
            merged[key] = out
        elif isinstance(val, str) and val.strip():
            merged[key] = val.strip()
    merged["_book_notes"] = str(book_doc.get("notes") or "").strip()
    return merged


def _bump_tag_stats(tags: list[str], outcome: str = "") -> None:
    if not tags:
        return
    doc = load_global()
    stats: dict[str, Any] = doc.setdefault("tag_stats", {})
    for tag in tags:
        t = str(tag).strip()
        if not t:
            continue
        row = stats.setdefault(t, {"count": 0, "last_at": "", "outcomes": {}})
        row["count"] = int(row.get("count") or 0) + 1
        row["last_at"] = _now()
        if outcome:
            oc = row.setdefault("outcomes", {})
            oc[outcome] = int(oc.get(outcome) or 0) + 1
    doc["updated_at"] = _now()
    file_utils.atomic_write_text(
        GLOBAL_FILE,
        json.dumps(doc, ensure_ascii=False, indent=2),
    )


def append_event(
    *,
    source: str,
    outcome: str = "",
    issue_tags: list[str] | None = None,
    note: str = "",
    book_id: str = "",
    manuscript_id: str = "",
    quality_log_id: str = "",
    chapter_num: int = 0,
    prompt_node: str = "",
    patterns: dict[str, Any] | None = None,
    extra: dict | None = None,
) -> str:
    """追加口味事件，更新 tag_stats，返回 event id。"""
    ensure_taste_dir()
    tags = [str(t).strip() for t in (issue_tags or []) if str(t).strip()]
    event = {
        "id": _evt_id(),
        "created_at": _now(),
        "source": (source or "manual").strip(),
        "outcome": (outcome or "").strip(),
        "issue_tags": tags,
        "note": (note or "").strip()[:500],
        "book_id": (book_id or "").strip(),
        "manuscript_id": (manuscript_id or "").strip(),
        "quality_log_id": (quality_log_id or "").strip(),
        "chapter_num": int(chapter_num) if chapter_num else 0,
        "prompt_node": (prompt_node or "").strip(),
    }
    if patterns:
        event["patterns"] = patterns
    if extra:
        event["extra"] = extra

    line = json.dumps(event, ensure_ascii=False) + "\n"
    with _lock:
        existing = ""
        if EVENTS_FILE.is_file():
            try:
                existing = EVENTS_FILE.read_text(encoding="utf-8")
            except OSError:
                existing = ""
        file_utils.atomic_write_text(EVENTS_FILE, existing + line)
        _trim_events_if_needed()

    _bump_tag_stats(tags, outcome)
    return event["id"]


def _trim_events_if_needed() -> None:
    if not EVENTS_FILE.is_file():
        return
    try:
        lines = [ln for ln in EVENTS_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return
    if len(lines) <= _MAX_EVENTS:
        return
    file_utils.atomic_write_text(EVENTS_FILE, "\n".join(lines[-_MAX_EVENTS:]) + "\n")


def list_events(
    *,
    book_id: str | None = None,
    source: str | None = None,
    limit: int = 80,
) -> list[dict]:
    ensure_taste_dir()
    if not EVENTS_FILE.is_file():
        return []
    lim = max(1, min(200, limit))
    try:
        lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if book_id and row.get("book_id") != book_id:
            continue
        if source and row.get("source") != source:
            continue
        out.append(row)
        if len(out) >= lim:
            break
    return out


def get_summary(*, book_id: str | None = None) -> dict[str, Any]:
    global_doc = load_global()
    stats = global_doc.get("tag_stats") or {}
    top_tags = sorted(
        (
            {
                "tag": tag,
                "label": tag_label(tag),
                "count": int((row or {}).get("count") or 0),
                "last_at": (row or {}).get("last_at", ""),
            }
            for tag, row in stats.items()
        ),
        key=lambda x: x["count"],
        reverse=True,
    )[:15]
    recent = list_events(book_id=book_id, limit=20)
    return {
        "global_updated_at": global_doc.get("updated_at", ""),
        "top_issue_tags": top_tags,
        "recent_events": recent,
        "preferences": merge_preferences(
            book_dir=_book_dir_for_id(book_id) if book_id else None,
        ),
    }


def _book_dir_for_id(book_id: str) -> Path | None:
    if not book_id:
        return None
    from core.data.book_context import BOOKS_DIR

    path = BOOKS_DIR / book_id
    return path if path.is_dir() else None


def _good_examples_from_list(items: list) -> list[dict[str, Any]]:
    return [
        ex for ex in items
        if isinstance(ex, dict) and (ex.get("type") or "good") == "good"
    ]


def _collect_context_good_examples(
    *,
    book_dir: Path | None,
    global_doc: dict[str, Any],
    limit: int = _CONTEXT_EXAMPLE_LIMIT,
) -> list[dict[str, Any]]:
    """本书 append_examples 全部优先；不足 limit 时用 global.examples 最近条目补齐。"""
    book_good: list[dict[str, Any]] = []
    if book_dir is not None:
        book_doc = load_book_taste(book_dir)
        if int(book_doc.get("version") or 1) >= 2:
            overrides = book_doc.get("overrides") or {}
            book_good = _good_examples_from_list(overrides.get("append_examples") or [])

    if len(book_good) >= limit:
        return book_good

    need = limit - len(book_good)
    global_good = _good_examples_from_list(global_doc.get("examples") or [])
    return book_good + (global_good[-need:] if need > 0 else [])


def _normalize_rule_text(text: str) -> str:
    return (text or "").strip().lower()


def _rule_content(row: dict[str, Any]) -> str:
    return str(row.get("content") or "").strip()


def _rules_texts_similar(a: str, b: str) -> bool:
    """简单包含检测：较短内容为较长内容子串且长度比 ≥ 0.8。"""
    na = _normalize_rule_text(a)
    nb = _normalize_rule_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
    if short not in long:
        return False
    return len(short) / len(long) >= 0.8


def _conflicts_with_accepted(content: str, accepted: list[str]) -> bool:
    return any(_rules_texts_similar(content, prev) for prev in accepted)


def _book_type_from_dir(book_dir: Path | None) -> str:
    import review_prompts

    project: dict[str, Any] = {}
    if book_dir is not None:
        proj_path = book_dir / "project.json"
        if proj_path.is_file():
            try:
                raw = json.loads(proj_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    project = raw
            except (OSError, json.JSONDecodeError):
                project = {}
    if not project:
        try:
            from core.data import novel_data

            meta = novel_data.get_project_meta()
            if isinstance(meta, dict):
                project = meta
        except Exception:
            project = {}
    bt = review_prompts.normalize_book_type(project.get("type"))
    return "novel" if bt == "world" else bt


def rule_applies_to_book_type(rule: dict[str, Any], book_type: str) -> bool:
    """无 book_types 字段的规则对全部书型生效。"""
    raw = rule.get("book_types")
    if not raw:
        return True
    if isinstance(raw, str):
        raw = [raw]
    allowed = {str(t).strip().lower() for t in raw if str(t).strip()}
    if not allowed:
        return True
    bt = (book_type or "novel").strip().lower()
    if bt == "world":
        bt = "novel"
    if bt in allowed:
        return True
    return bt == "novel" and "world" in allowed


def _load_profile_rules_for_book(book_dir: Path | None) -> list[dict[str, Any]]:
    from core import plan_product
    from core import profiles

    plan: dict[str, Any] = {}
    if book_dir is not None:
        plan_path = book_dir / "plan.json"
        if plan_path.is_file():
            try:
                raw = json.loads(plan_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    plan = raw
            except (OSError, json.JSONDecodeError):
                plan = {}
    if not plan:
        try:
            from core.data import novel_data

            loaded = novel_data.load_plan()
            plan = loaded if isinstance(loaded, dict) else {}
        except Exception:
            plan = {}

    criteria = plan_product.get_review_criteria(plan)
    profile_id = str(criteria.get("platform_profile") or "").strip()
    if not profile_id:
        return []
    profile = profiles.load_profile(profile_id)
    if not profile:
        return []
    out: list[dict[str, Any]] = []
    checks = profile.get("checks") or {}
    for bucket in ("hard", "soft"):
        for row in checks.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            content = _rule_content(row)
            if content:
                out.append({"content": content, "weight": bucket, "source": "profile"})
    return out


def _merge_context_rules(
    *,
    book_dir: Path | None,
    global_doc: dict[str, Any],
    book_type: str | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """按优先级合并规则；返回 (merged, 本书条数, 全局条数)。"""
    bt = book_type or _book_type_from_dir(book_dir)
    tier_rules: list[tuple[str, list[dict[str, Any]]]] = []

    book_rows: list[dict[str, Any]] = []
    if book_dir is not None:
        book_doc = load_book_taste(book_dir)
        if int(book_doc.get("version") or 1) >= 2:
            overrides = book_doc.get("overrides") or {}
            for row in overrides.get("append_rules") or []:
                if (
                    isinstance(row, dict)
                    and _rule_content(row)
                    and rule_applies_to_book_type(row, bt)
                ):
                    book_rows.append(row)
    tier_rules.append(("book", book_rows))

    global_rules = [
        r
        for r in (global_doc.get("rules") or [])
        if isinstance(r, dict) and rule_applies_to_book_type(r, bt)
    ]
    tier_rules.append((
        "global_hard",
        [r for r in global_rules if str(r.get("weight") or "").lower() == "hard" and _rule_content(r)],
    ))
    tier_rules.append((
        "global_soft",
        [
            r for r in global_rules
            if str(r.get("weight") or "soft").lower() != "hard" and _rule_content(r)
        ],
    ))
    tier_rules.append(("profile", _load_profile_rules_for_book(book_dir)))

    accepted: list[str] = []
    merged: list[dict[str, Any]] = []
    book_count = 0
    global_count = 0

    for tier, rows in tier_rules:
        for row in rows:
            content = _rule_content(row)
            if not content or _conflicts_with_accepted(content, accepted):
                continue
            accepted.append(content)
            merged.append({
                "content": content,
                "tier": tier,
                "weight": str(row.get("weight") or "soft").lower(),
            })
            if tier == "book":
                book_count += 1
            elif tier in ("global_hard", "global_soft"):
                global_count += 1

    return merged, book_count, global_count


def _format_merged_rule_line(rule: dict[str, Any]) -> str:
    content = rule["content"]
    tier = rule.get("tier") or ""
    if tier == "book":
        return f"- [本书] {content}"
    if tier == "global_hard":
        return f"- {content}（硬性）"
    if tier == "global_soft":
        return f"- {content}（软性）"
    if tier == "profile":
        weight = rule.get("weight") or "soft"
        label = "硬性" if weight == "hard" else "软性"
        return f"- {content}（平台·{label}）"
    return f"- {content}"


def build_context_block(
    *,
    book_id: str | None = None,
    book_dir: Path | None = None,
    max_chars: int = 3500,
    book_type: str | None = None,
) -> str:
    """供预填/审阅/拆文注入的口味上下文（Markdown）。"""
    if book_dir is None and book_id:
        book_dir = _book_dir_for_id(book_id)
    bt = book_type or _book_type_from_dir(book_dir)
    prefs = merge_preferences(book_dir=book_dir)
    global_doc = load_global()
    stats = global_doc.get("tag_stats") or {}
    merged_rules, book_rule_count, global_rule_count = _merge_context_rules(
        book_dir=book_dir,
        global_doc=global_doc,
        book_type=bt,
    )

    lines = ["## 用户口味库（审阅与生成须参考）", ""]
    if book_rule_count or global_rule_count:
        lines.append(f"# 规则来源：本书{book_rule_count}条 / 全局{global_rule_count}条")
        lines.append("")

    def _list_section(title: str, items: list) -> None:
        if not items:
            return
        lines.append(f"**{title}**")
        for item in items[:12]:
            lines.append(f"- {item}")
        lines.append("")

    _list_section("偏好（喜欢）", prefs.get("likes") or [])
    _list_section("忌讳（不喜欢）", prefs.get("dislikes") or [])
    _list_section("钩子/开头套路（可参考）", prefs.get("hook_patterns") or [])
    _list_section("须规避的模式", prefs.get("avoid_patterns") or [])

    for key, label in (
        ("platform_notes", "平台取向"),
        ("style_notes", "文风取向"),
        ("review_notes", "审阅补充"),
    ):
        text = str(prefs.get(key) or "").strip()
        if text:
            lines.append(f"**{label}**：{text}")
            lines.append("")

    book_notes = str(prefs.get("_book_notes") or "").strip()
    if book_notes:
        lines.append(f"**本书补充**：{book_notes}")
        lines.append("")

    hot = sorted(
        stats.items(),
        key=lambda kv: int((kv[1] or {}).get("count") or 0),
        reverse=True,
    )[:8]
    if hot:
        lines.append("**历史问题标签（出现次数高，生成时主动规避）**")
        for tag, row in hot:
            cnt = int((row or {}).get("count") or 0)
            if cnt < 1:
                continue
            lines.append(f"- {tag_label(tag)}（×{cnt}）")
        lines.append("")

    good_examples = _collect_context_good_examples(
        book_dir=book_dir,
        global_doc=global_doc,
    )
    if good_examples:
        lines.append("**正向案例（可参考写法）**")
        for ex in good_examples:
            ann = str(ex.get("annotation") or "").strip()
            snippet = str(ex.get("text") or "").strip()[:120]
            if ann:
                lines.append(f"- {ann}：「{snippet}…」" if len(snippet) >= 120 else f"- {ann}：「{snippet}」")
            elif snippet:
                lines.append(f"- 「{snippet}…」" if len(str(ex.get("text") or "")) > 120 else f"- 「{snippet}」")
        lines.append("")

    if merged_rules:
        lines.append("**写作规则（按优先级）**")
        for rule in merged_rules[:18]:
            lines.append(_format_merged_rule_line(rule))
        lines.append("")

    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n\n…（口味库已截断）"
    return text


def record_judgment_event(
    *,
    book_id: str,
    quality_log_id: str,
    outcome: str,
    issue_tags: list[str] | None = None,
    note: str = "",
    chapter_num: int = 0,
    prompt_node: str = "",
    kind: str = "",
) -> str:
    return append_event(
        source="judgment",
        outcome=outcome,
        issue_tags=issue_tags,
        note=note,
        book_id=book_id,
        quality_log_id=quality_log_id,
        chapter_num=chapter_num,
        prompt_node=prompt_node,
        extra={"quality_kind": kind} if kind else None,
    )


def record_submission_event(
    *,
    book_id: str,
    manuscript_id: str,
    result: str,
    reject_tags: list[str] | None = None,
    reject_reason: str = "",
) -> str:
    outcome = "accepted" if result in ("pass", "passed", "通过") else "rejected"
    tags = list(reject_tags or [])
    if outcome == "rejected" and "submission_reject" not in tags:
        tags.append("submission_reject")
    if outcome == "accepted" and "submission_pass" not in tags:
        tags.append("submission_pass")
    return append_event(
        source="submission",
        outcome=outcome,
        issue_tags=tags,
        note=reject_reason,
        book_id=book_id,
        manuscript_id=manuscript_id,
    )


def _extract_deconstruct_patterns(reply: str) -> dict[str, Any]:
    """从拆文报告轻量提取可沉淀规律。"""
    text = (reply or "").strip()
    hooks: list[str] = []
    structures: list[str] = []
    for line in text.splitlines():
        s = line.strip().lstrip("-*·").strip()
        if not s or len(s) < 4:
            continue
        low = s.lower()
        if any(k in s for k in ("钩子", "开头", "黄金", "前三")):
            hooks.append(s[:120])
        elif any(k in s for k in ("结构", "节奏", "节拍", "爽点", "转折")):
            structures.append(s[:120])
    return {
        "hook_patterns": hooks[:8],
        "structure_notes": structures[:8],
    }


def extract_deconstruct_patterns(reply: str) -> dict[str, Any]:
    """从拆文报告轻量提取可沉淀规律（供 API / 前端确认）。"""
    return _extract_deconstruct_patterns(reply)


def record_deconstruct_event(
    *,
    book_id: str,
    quality_log_id: str,
    reply: str,
    source_label: str = "",
) -> str:
    patterns = _extract_deconstruct_patterns(reply)
    tags = ["deconstruct_pattern"]
    return append_event(
        source="deconstruct",
        outcome="accepted",
        issue_tags=tags,
        note=(source_label or "参考拆文")[:200],
        book_id=book_id,
        quality_log_id=quality_log_id,
        patterns=patterns,
        extra={"reply_excerpt": reply[:_MAX_EVENT_BODY]},
    )


def import_deconstruct_patterns(
    quality_log_id: str,
    *,
    book_dir: Path | None = None,
    merge_global: bool = True,
    hook_patterns: list[str] | None = None,
    structure_notes: list[str] | None = None,
) -> dict[str, Any]:
    """将某次拆文事件中的 patterns 合并进 global/book hook_patterns。"""
    events = list_events(limit=500)
    target = None
    for row in events:
        if row.get("quality_log_id") == quality_log_id or row.get("id") == quality_log_id:
            target = row
            break
    if not target:
        return {"ok": False, "error": "未找到对应拆文事件或 quality_log 记录"}

    patterns = target.get("patterns") or {}
    hooks = list(hook_patterns) if hook_patterns is not None else list(patterns.get("hook_patterns") or [])
    structures = (
        list(structure_notes)
        if structure_notes is not None
        else list(patterns.get("structure_notes") or [])
    )
    if not hooks and not structures:
        return {"ok": False, "error": "该记录没有可导入的规律"}

    imported = {"hook_patterns": hooks, "structure_notes": structures}
    if merge_global:
        doc = load_global()
        prefs = doc.setdefault("preferences", {})
        existing = list(prefs.get("hook_patterns") or [])
        seen = set(existing)
        for item in hooks + structures:
            s = str(item).strip()
            if s and s not in seen:
                seen.add(s)
                existing.append(s)
        prefs["hook_patterns"] = existing[:40]
        save_global({"preferences": prefs})
        for item in hooks + structures:
            s = str(item).strip()
            if s:
                try:
                    add_rule(content=s, weight="soft", source="deconstruct", tags=["hook"])
                except ValueError:
                    pass

    if book_dir:
        bdoc = load_book_taste(book_dir)
        bprefs = bdoc.setdefault("preferences", {})
        existing_b = list(bprefs.get("hook_patterns") or [])
        seen_b = set(existing_b)
        for item in hooks:
            s = str(item).strip()
            if s and s not in seen_b:
                seen_b.add(s)
                existing_b.append(s)
        bprefs["hook_patterns"] = existing_b[:30]
        save_book_taste(book_dir, {"preferences": bprefs})

    return {"ok": True, "imported": imported}
