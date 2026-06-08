"""写作引导 HTTP 路由。"""

from __future__ import annotations

import main as core
from fastapi import APIRouter

router = APIRouter(tags=["guide"])


@router.get("/api/guide/status")
def guide_status() -> dict:
    return core.get_guide_status()
