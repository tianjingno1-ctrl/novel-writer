"""写作引导 HTTP 路由。"""

from __future__ import annotations

from app.guide import get_guide_status
from fastapi import APIRouter

router = APIRouter(tags=["guide"])


@router.get("/api/guide/status")
def guide_status() -> dict:
    return get_guide_status()
