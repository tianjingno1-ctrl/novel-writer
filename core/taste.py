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


def push_highlight_to_taste(
    *,
    book_id: str,
    chapter_num: int,
    text: str,
    annotation: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """L5a：亮点写入 global.examples 并记 event。"""
    ex = add_example(
        example_type="good",
        text=text,
        annotation=annotation,
        source="highlight",
        tags=tags or ["hook_strong"],
        book_id=book_id,
        chapter_num=chapter_num,
    )
    eid = append_event(
        source="highlight",
        outcome="accepted",
        issue_tags=tags or ["hook_strong"],
        note=(annotation or "审阅通过亮点")[:200],
        book_id=book_id,
        chapter_num=chapter_num,
        extra={"example_id": ex["id"]},
    )
    return {"example": ex, "event_id": eid}


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
        overrides = raw.get("overrides")
        if not isinstance(overrides, dict):
            raw["overrides"] = {
                "rules": [],
                "append_rules": [],
                "append_examples": [],
            }
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


def build_context_block(
    *,
    book_id: str | None = None,
    book_dir: Path | None = None,
    max_chars: int = 3500,
) -> str:
    """供预填/审阅/拆文注入的口味上下文（Markdown）。"""
    if book_dir is None and book_id:
        book_dir = _book_dir_for_id(book_id)
    prefs = merge_preferences(book_dir=book_dir)
    global_doc = load_global()
    stats = global_doc.get("tag_stats") or {}

    lines = ["## 用户口味库（审阅与生成须参考）", ""]

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

    good_examples = [
        ex for ex in (global_doc.get("examples") or [])
        if isinstance(ex, dict) and ex.get("type") == "good"
    ][-5:]
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

    hard_rules = [
        r for r in (global_doc.get("rules") or [])
        if isinstance(r, dict) and r.get("weight") == "hard"
    ][:6]
    if hard_rules:
        lines.append("**硬性规则**")
        for rule in hard_rules:
            lines.append(f"- {rule.get('content', '')}")
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
    hooks = patterns.get("hook_patterns") or []
    structures = patterns.get("structure_notes") or []
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
