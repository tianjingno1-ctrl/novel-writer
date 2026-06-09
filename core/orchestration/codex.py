"""Codex 编排。"""
from __future__ import annotations

from core.data import novel_data
from app import codex as codex_svc


def list_codex_files() -> dict:
    return {"files": codex_svc.codex_file_names()}


def get_codex_file(name: str) -> dict | None:
    if name not in codex_svc.valid_codex_names():
        return None
    return codex_svc.get_codex(name)


def save_codex_file(name: str, content: str, *, chapter_num: int | None = None) -> dict:
    if name not in codex_svc.valid_codex_names():
        return {"ok": False, "error": "非法设定文件名"}
    return codex_svc.save_codex(name, content, chapter_num=chapter_num)


def list_entries() -> dict:
    return {
        "entries": novel_data.list_codex_entries(),
        "active": novel_data.get_active_codex_ids(),
    }


def create_entry(name: str, content: str) -> dict:
    return novel_data.create_codex_entry(name, content)


def set_active_ids(active: list[str]) -> dict:
    return novel_data.set_active_codex_ids(active)


def get_entry(entry_id: str) -> dict | None:
    return novel_data.get_codex_entry(entry_id)


def save_entry(entry_id: str, content: str) -> dict:
    return novel_data.save_codex_entry(entry_id, content)


def delete_entry(entry_id: str) -> dict:
    return novel_data.delete_codex_entry(entry_id)
