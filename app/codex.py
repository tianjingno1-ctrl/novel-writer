"""文件型 Codex（world/style 等 md）读写。"""

from __future__ import annotations

from app import paths as _paths


def _codex_files() -> dict:
    return _paths.resolved_codex_files()


def valid_codex_names() -> frozenset[str]:
    return frozenset(_codex_files().keys())


def codex_file_names() -> list[str]:
    return list(_codex_files().keys())


def get_codex(name: str) -> dict | None:
    import main

    path = _codex_files().get(name)
    if path is None:
        return None
    return {"name": name, "content": main.read_text(path)}


def save_codex(name: str, content: str, chapter_num: int | None = None) -> dict:
    import main

    path = _codex_files().get(name)
    if path is None:
        return {"ok": False, "error": f"未知设定文件: {name}"}
    ch = (
        chapter_num
        if chapter_num and chapter_num > 0
        else main._session_chapter_num()
    )
    changed = main.write_text(
        path, content, append=False, history_source="codex", chapter_num=ch
    )
    return {"ok": True, "name": name, "changed": changed}
