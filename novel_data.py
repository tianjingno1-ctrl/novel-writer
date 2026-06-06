"""Plan 场景层 + Codex 条目化管理。"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

_BASE = Path(__file__).resolve().parent
DATA_DIR = _BASE / "data"
BACKUPS_DIR = DATA_DIR / "backups"
PLAN_FILE = DATA_DIR / "plan.json"
CODEX_DIR = DATA_DIR / "codex" / "entries"
CODEX_ACTIVE_FILE = DATA_DIR / "codex" / "active.json"


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def backup_file(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = BACKUPS_DIR / f"{path.stem}_{ts}{path.suffix}"
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_file(path)
    path.write_text(content, encoding="utf-8")

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


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_file(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_plan() -> dict:
    _ensure_dirs()
    if not PLAN_FILE.exists():
        _save_json(PLAN_FILE, DEFAULT_PLAN)
    return _load_json(PLAN_FILE, DEFAULT_PLAN)


def save_plan(plan: dict) -> None:
    _save_json(PLAN_FILE, plan)


def _new_scene_id(chapter_num: int) -> str:
    return f"ch{chapter_num}_{uuid.uuid4().hex[:8]}"


def ensure_chapter_plan(chapter_num: int, title: str = "") -> dict:
    plan = load_plan()
    key = str(chapter_num)
    if key not in plan["chapters"]:
        plan["chapters"][key] = {"title": title or f"第{chapter_num}章", "scenes": []}
    return plan


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


def get_chapter_plan(chapter_num: int) -> dict | None:
    plan = load_plan()
    ch = plan.get("chapters", {}).get(str(chapter_num))
    if ch is None:
        return None
    return {"num": chapter_num, **ch}


def add_scene(chapter_num: int, title: str = "新场景", beat: str = "") -> dict:
    plan = ensure_chapter_plan(chapter_num)
    key = str(chapter_num)
    scene = {
        "id": _new_scene_id(chapter_num),
        "title": title,
        "beat": beat,
        "summary": "",
        "done": False,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    plan["chapters"][key]["scenes"].append(scene)
    plan["active_scene_id"] = scene["id"]
    save_plan(plan)
    return scene


def update_scene(scene_id: str, **fields) -> dict | None:
    plan = load_plan()
    for ch in plan.get("chapters", {}).values():
        for scene in ch.get("scenes", []):
            if scene["id"] == scene_id:
                for k, v in fields.items():
                    if k in ("title", "beat", "summary", "done"):
                        scene[k] = v
                scene["updated_at"] = datetime.now().isoformat(timespec="seconds")
                save_plan(plan)
                return scene
    return None


def delete_scene(scene_id: str) -> bool:
    plan = load_plan()
    for key, ch in plan.get("chapters", {}).items():
        scenes = ch.get("scenes", [])
        for i, scene in enumerate(scenes):
            if scene["id"] == scene_id:
                scenes.pop(i)
                if plan.get("active_scene_id") == scene_id:
                    plan["active_scene_id"] = scenes[-1]["id"] if scenes else None
                save_plan(plan)
                return True
    return False


def get_scene(scene_id: str) -> dict | None:
    plan = load_plan()
    for key, ch in plan.get("chapters", {}).items():
        for scene in ch.get("scenes", []):
            if scene["id"] == scene_id:
                return {"chapter_num": int(key), **scene}
    return None


def set_active_scene(scene_id: str | None) -> dict:
    plan = load_plan()
    plan["active_scene_id"] = scene_id
    save_plan(plan)
    return {"active_scene_id": scene_id}


def get_active_scene() -> dict | None:
    plan = load_plan()
    sid = plan.get("active_scene_id")
    return get_scene(sid) if sid else None


def get_scene_context_text() -> str:
    scene = get_active_scene()
    if not scene:
        return ""
    parts = [f"【场景】{scene.get('title', '')}"]
    if scene.get("beat"):
        parts.append(f"【Scene Beat】\n{scene['beat']}")
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


def get_codex_entry(name: str) -> dict | None:
    path = CODEX_DIR / f"{name}.md"
    if not path.exists():
        return None
    return {"id": name, "name": name, "content": read_text(path)}


def save_codex_entry(name: str, content: str) -> dict:
    _ensure_dirs()
    safe = re.sub(r'[\\/:*?"<>|]', "_", name.strip())
    if not safe:
        return {"ok": False, "error": "名称无效"}
    path = CODEX_DIR / f"{safe}.md"
    write_text(path, content)
    return {"ok": True, "id": safe, "name": safe}


def create_codex_entry(name: str, content: str = "") -> dict:
    safe = re.sub(r'[\\/:*?"<>|]', "_", name.strip())
    path = CODEX_DIR / f"{safe}.md"
    if path.exists():
        return {"ok": False, "error": "条目已存在"}
    default = content or f"# {safe}\n\ntags: \n\n（人物/地点/物品设定）\n"
    return save_codex_entry(safe, default)


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
