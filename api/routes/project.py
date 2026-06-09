"""当前书 project.json HTTP 路由。"""

from __future__ import annotations

from core.orchestration import project as orchestration_project
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["project"])


class ProjectUpdate(BaseModel):
    title: str | None = None
    world_label: str | None = None
    tagline: str | None = None
    notes: str | None = None
    type: str | None = None
    platform: str | None = None


@router.get("/api/project")
def get_project() -> dict:
    return orchestration_project.get_project_meta()


@router.put("/api/project")
def put_project(body: ProjectUpdate) -> dict:
    fields = body.model_dump(exclude_unset=True)
    return orchestration_project.save_project_meta(**fields)
