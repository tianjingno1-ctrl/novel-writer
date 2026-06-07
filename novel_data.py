"""Plan 场景层 + Codex 条目化管理。"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

import file_utils

_BASE = Path(__file__).resolve().parent
DATA_DIR = _BASE / "data"
BACKUPS_DIR = DATA_DIR / "backups"
PLAN_FILE = DATA_DIR / "plan.json"
PROJECT_FILE = DATA_DIR / "project.json"
CODEX_DIR = DATA_DIR / "codex" / "entries"
CODEX_ACTIVE_FILE = DATA_DIR / "codex" / "active.json"

DEFAULT_PROJECT = {
    "title": "未命名小说",
    "world_label": "",
    "tagline": "",
    "notes": "",
}

_plan_lock = threading.RLock()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def backup_file(path: Path) -> None:
    file_utils.backup_file(path, BACKUPS_DIR)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_file(path)
    file_utils.atomic_write_text(path, content)

DEFAULT_PLAN = {"active_scene_id": None, "chapters": {}}


def _ensure_dirs() -> None:
    CODEX_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(default)


def _active_chapter_from_plan(plan: dict) -> int:
    sid = plan.get("active_scene_id") or ""
    if not sid:
        return 0
    for key, ch in plan.get("chapters", {}).items():
        for scene in ch.get("scenes", []):
            if scene.get("id") == sid:
                try:
                    return int(key)
                except (TypeError, ValueError):
                    return 0
    return 0


def _save_json(
    path: Path,
    data: dict,
    *,
    history_source: str = "plan",
    chapter_num: int | None = None,
) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2)
    import change_history

    if change_history.resolve_key(path) == "plan":
        ch = chapter_num if chapter_num is not None else _active_chapter_from_plan(data)
        change_history.save_with_history(
            path,
            content,
            source=history_source,
            chapter_num=ch,
        )
        return
    backup_file(path)
    file_utils.atomic_write_text(path, content, encoding="utf-8")


def _read_plan_unlocked() -> dict:
    _ensure_dirs()
    if not PLAN_FILE.exists():
        _save_json(PLAN_FILE, DEFAULT_PLAN)
    return _load_json(PLAN_FILE, DEFAULT_PLAN)


def load_plan() -> dict:
    with _plan_lock:
        return _read_plan_unlocked()


def save_plan(plan: dict) -> None:
    with _plan_lock:
        _save_json(PLAN_FILE, plan)


def _mutate_plan(editor):
    """在锁内 load → 改 → save，避免 plan.json 并发 lost update。"""
    with _plan_lock:
        plan = _read_plan_unlocked()
        result = editor(plan)
        _save_json(PLAN_FILE, plan, chapter_num=_active_chapter_from_plan(plan))
        return result


def restore_plan_json_text(content: str) -> None:
    """从 JSON 文本恢复 plan（用于档案撤销，走 plan 锁，不再二次留痕）。"""
    with _plan_lock:
        backup_file(PLAN_FILE)
        file_utils.atomic_write_text(PLAN_FILE, content, encoding="utf-8")


def _new_scene_id(chapter_num: int) -> str:
    return f"ch{chapter_num}_{uuid.uuid4().hex[:8]}"


def ensure_chapter_plan(chapter_num: int, title: str = "") -> dict:
    def edit(plan: dict) -> None:
        key = str(chapter_num)
        if key not in plan["chapters"]:
            plan["chapters"][key] = {"title": title or f"第{chapter_num}章", "scenes": []}

    _mutate_plan(edit)
    return load_plan()


def list_plan_chapters() -> list[dict]:
    plan = load_plan()
    items = []
    for key in sorted(plan.get("chapters", {}), key=lambda x: int(x)):
        ch = plan["chapters"][key]
        items.append({
            "num": int(key),
            "title": ch.get("title", ""),
            "scene_count": len(ch.get("scenes", [])),
        })
    return items


def list_plan_details() -> list[dict]:
    plan = load_plan()
    items = []
    for key in sorted(plan.get("chapters", {}), key=lambda x: int(x)):
        ch = plan["chapters"][key]
        items.append({
            "num": int(key),
            "title": ch.get("title", ""),
            "scenes": ch.get("scenes", []),
        })
    return items


def get_chapter_plan(chapter_num: int) -> dict | None:
    plan = load_plan()
    ch = plan.get("chapters", {}).get(str(chapter_num))
    if ch is None:
        return None
    return {"num": chapter_num, **ch}


def add_scene(chapter_num: int, title: str = "新场景", beat: str = "") -> dict:
    ensure_chapter_plan(chapter_num)

    def edit(plan: dict) -> dict:
        key = str(chapter_num)
        scene = {
            "id": _new_scene_id(chapter_num),
            "title": title.strip() or "新场景",
            "beat": beat,
            "pace": "中",
            "summary": "",
            "done": False,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        plan["chapters"][key]["scenes"].append(scene)
        plan["active_scene_id"] = scene["id"]
        return scene

    return _mutate_plan(edit)


def update_scene(scene_id: str, **fields) -> dict | None:
    def edit(plan: dict) -> dict | None:
        for ch in plan.get("chapters", {}).values():
            for scene in ch.get("scenes", []):
                if scene["id"] == scene_id:
                    for k, v in fields.items():
                        if k in ("title", "beat", "pace", "summary", "done", "emotion_anchor"):
                            if k == "emotion_anchor":
                                scene[k] = _normalize_emotion_anchor(v)
                            else:
                                scene[k] = v
                    scene["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    return scene
        return None

    return _mutate_plan(edit)


def delete_scene(scene_id: str) -> bool:
    def edit(plan: dict) -> bool:
        for key, ch in plan.get("chapters", {}).items():
            scenes = ch.get("scenes", [])
            for i, scene in enumerate(scenes):
                if scene["id"] == scene_id:
                    scenes.pop(i)
                    if plan.get("active_scene_id") == scene_id:
                        if scenes:
                            plan["active_scene_id"] = scenes[-1]["id"]
                        else:
                            fallback = None
                            for k in sorted(plan.get("chapters", {}), key=lambda x: int(x)):
                                ch2 = plan["chapters"][k]
                                if ch2.get("scenes"):
                                    fallback = ch2["scenes"][0]["id"]
                                    break
                            plan["active_scene_id"] = fallback
                    return True
        return False

    return _mutate_plan(edit)


def get_scene(scene_id: str) -> dict | None:
    plan = load_plan()
    for key, ch in plan.get("chapters", {}).items():
        for scene in ch.get("scenes", []):
            if scene["id"] == scene_id:
                return {"chapter_num": int(key), **scene}
    return None


def set_active_scene(scene_id: str | None) -> dict:
    def edit(plan: dict) -> dict:
        plan["active_scene_id"] = scene_id
        return {"active_scene_id": scene_id}

    return _mutate_plan(edit)


def update_chapter_title(chapter_num: int, title: str) -> dict | None:
    def edit(plan: dict) -> dict | None:
        key = str(chapter_num)
        if key not in plan["chapters"]:
            return None
        plan["chapters"][key]["title"] = title.strip()
        return plan["chapters"][key]

    return _mutate_plan(edit)


def reorder_scenes(chapter_num: int, scene_ids: list[str]) -> bool:
    def edit(plan: dict) -> bool:
        key = str(chapter_num)
        if key not in plan["chapters"]:
            return False
        scenes = plan["chapters"][key]["scenes"]
        id_map = {s["id"]: s for s in scenes}
        ordered = [id_map[sid] for sid in scene_ids if sid in id_map]
        seen = {s["id"] for s in ordered}
        ordered.extend(s for s in scenes if s["id"] not in seen)
        plan["chapters"][key]["scenes"] = ordered
        return True

    return _mutate_plan(edit)


def get_active_scene() -> dict | None:
    plan = load_plan()
    sid = plan.get("active_scene_id")
    return get_scene(sid) if sid else None


PACE_INSTRUCTIONS = {
    "快": "【节奏档位：快】短句为主，每段1-2行，动词密集，少修饰，适合冲突/打脸场景。",
    "中": "【节奏档位：中】正常叙述节奏，对话与动作均衡。",
    "慢": "【节奏档位：慢】细节丰富，感官描写，适合感情场景或高潮后余韵。",
}

_PACE_BEAT_RE = re.compile(r"【节奏档位】\s*(快|中|慢)")


def resolve_scene_pace(scene: dict) -> str:
    """场景节奏档位：显式 pace 字段优先，否则从 Beat 文本解析。"""
    pace = (scene.get("pace") or "").strip()
    if pace in PACE_INSTRUCTIONS:
        return pace
    beat = scene.get("beat") or ""
    m = _PACE_BEAT_RE.search(beat)
    if m:
        return m.group(1)
    return "中"


def _normalize_emotion_anchor(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    target = str(value.get("target", "")).strip()
    how = str(value.get("how", "")).strip()
    if not target and not how:
        return {}
    return {"target": target, "how": how}


def format_emotion_anchor_instruction(scene: dict) -> str:
    anchor = _normalize_emotion_anchor(scene.get("emotion_anchor"))
    if anchor:
        return f"【情绪锚点】目标：{anchor['target']}；落地方式：{anchor['how']}"
    beat = scene.get("beat") or ""
    m = re.search(
        r"【情绪锚点】\s*目标[：:]\s*(.+?)[；;]\s*落地(?:方式)?[：:]\s*(.+?)(?:\n|$)",
        beat,
    )
    if m:
        return f"【情绪锚点】目标：{m.group(1).strip()}；落地方式：{m.group(2).strip()}"
    return ""


def get_scene_context_text() -> str:
    scene = get_active_scene()
    if not scene:
        return ""
    parts = [f"【场景】{scene.get('title', '')}"]
    if scene.get("beat"):
        parts.append(f"【Scene Beat】\n{scene['beat']}")
    parts.append(PACE_INSTRUCTIONS[resolve_scene_pace(scene)])
    emotion = format_emotion_anchor_instruction(scene)
    if emotion:
        parts.append(emotion)
    if scene.get("summary"):
        parts.append(f"【场景概述】\n{scene['summary']}")
    return "\n\n".join(parts)


def list_codex_entries() -> list[dict]:
    _ensure_dirs()
    items = []
    for p in sorted(CODEX_DIR.glob("*.md")):
        name = p.stem
        text = read_text(p)
        tag_m = re.search(r"tags?:\s*(.+)", text, re.I)
        items.append({
            "id": name,
            "name": name,
            "tags": tag_m.group(1).strip() if tag_m else "",
            "preview": text[:80].replace("\n", " "),
        })
    return items


def _sanitize_codex_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name.strip())


def get_codex_entry(name: str) -> dict | None:
    safe = _sanitize_codex_name(name)
    if not safe:
        return None
    path = CODEX_DIR / f"{safe}.md"
    if not path.exists():
        return None
    return {"id": safe, "name": safe, "content": read_text(path)}


def save_codex_entry(name: str, content: str) -> dict:
    _ensure_dirs()
    safe = _sanitize_codex_name(name)
    if not safe:
        return {"ok": False, "error": "名称无效"}
    path = CODEX_DIR / f"{safe}.md"
    write_text(path, content)
    return {"ok": True, "id": safe, "name": safe}


def create_codex_entry(name: str, content: str = "") -> dict:
    safe = _sanitize_codex_name(name)
    if not safe:
        return {"ok": False, "error": "名称无效"}
    path = CODEX_DIR / f"{safe}.md"
    if path.exists():
        return {"ok": False, "error": "条目已存在"}
    default = content or f"# {safe}\n\ntags: \n\n（人物/地点/物品设定）\n"
    return save_codex_entry(safe, default)


def delete_codex_entry(name: str) -> dict:
    _ensure_dirs()
    safe = _sanitize_codex_name(name)
    if not safe:
        return {"ok": False, "error": "名称无效"}
    path = CODEX_DIR / f"{safe}.md"
    if not path.exists():
        return {"ok": False, "error": "条目不存在"}
    backup_file(path)
    path.unlink()
    ids = [x for x in get_active_codex_ids() if x != safe]
    set_active_codex_ids(ids)
    return {"ok": True, "id": safe}


def get_active_codex_ids() -> list[str]:
    _ensure_dirs()
    data = _load_json(CODEX_ACTIVE_FILE, {"active": []})
    return list(data.get("active", []))


def set_active_codex_ids(ids: list[str]) -> dict:
    _ensure_dirs()
    _save_json(CODEX_ACTIVE_FILE, {"active": ids})
    return {"active": ids}


def format_active_codex_text() -> str:
    ids = get_active_codex_ids()
    if not ids:
        return ""
    parts = []
    for entry_id in ids:
        entry = get_codex_entry(entry_id)
        if entry:
            parts.append(f"## {entry['name']}\n{entry['content']}")
    return "\n\n".join(parts)


def get_project_meta() -> dict:
    _ensure_dirs()
    if not PROJECT_FILE.exists():
        _save_json(PROJECT_FILE, DEFAULT_PROJECT)
    meta = _load_json(PROJECT_FILE, DEFAULT_PROJECT)
    for key, default in DEFAULT_PROJECT.items():
        meta.setdefault(key, default)
    return meta


def save_project_meta(**fields: str) -> dict:
    meta = get_project_meta()
    for key, value in fields.items():
        if key in DEFAULT_PROJECT and value is not None:
            meta[key] = str(value).strip()
    _save_json(PROJECT_FILE, meta)
    return meta


def _excerpt(text: str, limit: int = 480) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[:limit].rstrip() + "…"


def build_bookshelf_overview(
    *,
    chapters: list[tuple[int, object]],
    chapter_stats: list[dict],
    summaries_text: str,
    world_text: str,
    current_chapter: int | None,
) -> dict:
    """书架概览：书名、世界、大纲、章节目录。"""
    project = get_project_meta()
    plan = load_plan()
    stats_by_num = {c["num"]: c for c in chapter_stats}
    active_ids = get_active_codex_ids()

    file_nums = {n for n, _ in chapters}
    plan_nums = {int(k) for k in plan.get("chapters", {})}
    all_nums = sorted(file_nums | plan_nums)

    outline = []
    for num in all_nums:
        key = str(num)
        ch = plan.get("chapters", {}).get(key, {})
        scenes = []
        for s in ch.get("scenes", []):
            scenes.append({
                "id": s.get("id"),
                "title": s.get("title", ""),
                "beat": _excerpt(s.get("beat", ""), 200),
                "done": bool(s.get("done")),
            })
        outline.append({
            "num": num,
            "title": ch.get("title") or f"第{num}章",
            "chars": stats_by_num.get(num, {}).get("chars", 0),
            "has_body": num in file_nums,
            "scenes": scenes,
        })

    active_worlds = []
    for entry_id in active_ids:
        entry = get_codex_entry(entry_id)
        if not entry:
            continue
        active_worlds.append({
            "id": entry["id"],
            "name": entry["name"],
            "preview": _excerpt(entry["content"], 600),
        })

    current_title = None
    if current_chapter is not None:
        ch = plan.get("chapters", {}).get(str(current_chapter), {})
        current_title = ch.get("title") or f"第{current_chapter}章"

    return {
        "project": project,
        "single_book_mode": True,
        "multi_book_hint": (
            "当前为单书模式（一个 data/ 目录 = 一本书）。"
            "同时写多本：复制整个 novel_writer 文件夹，或 Git 分支隔离各自的 data/。"
        ),
        "current_chapter": current_chapter,
        "current_chapter_title": current_title,
        "world_excerpt": _excerpt(world_text, 800),
        "active_worlds": active_worlds,
        "outline": outline,
        "summaries_excerpt": _excerpt(summaries_text, 1200),
        "chapter_count": len(all_nums),
    }


_OUTLINE_BLOCK_RE = re.compile(
    r"【后续第(\d+)章[^】]*】\s*\n(.*?)(?=【后续第|\【整体节奏提示】|\Z)",
    re.DOTALL,
)


def _outline_field(block: str, field_name: str) -> str:
    pattern = rf"{re.escape(field_name)}[：:]\s*(.+?)(?=\n[^\s]{{1,12}}[：:]|$)"
    m = re.search(pattern, block, re.DOTALL)
    return m.group(1).strip() if m else ""


def parse_outline_suggestions(text: str) -> list[dict]:
    """解析续章灵感输出为结构化建议列表。

    offset 按块出现顺序从 1 编号（紧接当前章后的第 1、2…条建议），
    不采用标题里的全书章号，避免 AI 写「后续第2章」时错位到第 3 章。
    """
    results: list[dict] = []
    for seq, (_label_num, body) in enumerate(_OUTLINE_BLOCK_RE.findall(text or ""), start=1):
        body = body.strip()
        if not body:
            continue
        results.append({
            "offset": seq,
            "定位": _outline_field(body, "定位"),
            "核心事件": _outline_field(body, "核心事件"),
            "冲突转折": _outline_field(body, "冲突/转折") or _outline_field(body, "冲突"),
            "章末钩子": _outline_field(body, "章末钩子"),
            "伏笔动向": _outline_field(body, "伏笔动向"),
            "raw": body,
        })
    return results


def _scene_title_from_text(text: str, fallback: str, max_len: int = 14) -> str:
    one_line = re.sub(r"\s+", " ", (text or "").strip())
    if not one_line:
        return fallback
    return one_line[:max_len] + ("…" if len(one_line) > max_len else "")


def derive_chapter_title_from_suggestion(suggestion: dict, *, max_len: int = 48) -> str:
    """从续章建议提炼 Plan 章节标题（用户可事后在规划里改）。"""
    for key in ("定位", "核心事件", "章末钩子"):
        text = (suggestion.get(key) or "").strip()
        if not text:
            continue
        one_line = re.sub(r"\s+", " ", text)
        for sep in ("。", "；", ";", "，", ",", "、"):
            if sep in one_line:
                one_line = one_line.split(sep, 1)[0].strip()
                break
        if len(one_line) > max_len:
            one_line = one_line[: max_len - 1] + "…"
        return one_line
    return ""


def apply_outline_suggestion_to_chapter(
    latest_chapter: int,
    suggestion: dict,
    *,
    target_offset: int | None = None,
    replace: bool = False,
) -> dict:
    """将一条续章建议写入 Plan 对应章节的场景 Beat。"""
    offset = int(target_offset if target_offset is not None else suggestion.get("offset", 1))
    chapter_num = latest_chapter + offset
    chapter_title = derive_chapter_title_from_suggestion(suggestion) or f"第{chapter_num}章"
    ensure_chapter_plan(chapter_num, title=chapter_title)

    scenes_spec: list[tuple[str, str]] = []
    core = suggestion.get("核心事件", "").strip()
    dingwei = suggestion.get("定位", "").strip()
    if dingwei or core:
        beat = dingwei
        if dingwei and core:
            beat = f"{dingwei}\n\n{core}"
        elif core:
            beat = core
        scenes_spec.append((_scene_title_from_text(core or dingwei, "核心推进"), beat))

    conflict = suggestion.get("冲突转折", "").strip()
    if conflict:
        scenes_spec.append(("冲突升级", conflict))

    hook = suggestion.get("章末钩子", "").strip()
    foreshadow = suggestion.get("伏笔动向", "").strip()
    if hook or foreshadow:
        beat = hook
        if hook and foreshadow:
            beat = f"{hook}\n\n伏笔动向：{foreshadow}"
        elif foreshadow:
            beat = f"伏笔动向：{foreshadow}"
        scenes_spec.append((_scene_title_from_text(hook or foreshadow, "章末钩子"), beat))

    if not scenes_spec:
        return {"ok": False, "error": "该条建议没有可写入的 Beat 内容"}

    plan = load_plan()
    key = str(chapter_num)
    existing = plan.get("chapters", {}).get(key, {}).get("scenes", [])
    has_content = any((s.get("beat") or "").strip() for s in existing)
    if existing and has_content and not replace:
        return {
            "ok": False,
            "error": f"第{chapter_num}章已有 {len(existing)} 个场景且含 Beat，需确认覆盖",
            "need_replace": True,
            "chapter_num": chapter_num,
        }

    update_chapter_title(chapter_num, chapter_title)

    def edit(plan: dict) -> list[dict]:
        ch = plan["chapters"][key]
        if replace or not ch.get("scenes"):
            ch["scenes"] = []
        created: list[dict] = []
        for title, beat in scenes_spec:
            scene = {
                "id": _new_scene_id(chapter_num),
                "title": title,
                "beat": beat,
                "pace": "中",
                "summary": "",
                "done": False,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            ch["scenes"].append(scene)
            created.append(scene)
        if created:
            plan["active_scene_id"] = created[0]["id"]
        return created

    created = _mutate_plan(edit)
    return {
        "ok": True,
        "chapter_num": chapter_num,
        "chapter_title": chapter_title,
        "scene_count": len(created),
        "scenes": created,
        "offset": offset,
    }
