"""项目元信息编排。"""
from __future__ import annotations

from core.data import novel_data


def get_project_meta() -> dict:
    return novel_data.get_project_meta()


def save_project_meta(**fields) -> dict:
    return novel_data.save_project_meta(**fields)
