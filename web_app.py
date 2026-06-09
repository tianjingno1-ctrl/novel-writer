"""HTTP API — FastAPI 后端（无内置前端，见 /docs）。"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

import infra.config as config
from infra.logs import runtime as runtime_log
from app.bootstrap import bootstrap_library, init_data_dirs, init_context
from infra.billing import load_total_cost, set_total_cost
from app import writing_session as ws
from app.free_chat import load_free_chat
from api.routes import batch as batch_routes
from api.routes import chapters as chapters_routes
from api.routes import codex as codex_routes
from api.routes import config as config_routes
from api.routes import female_fiction as female_fiction_routes
from api.routes import finalize as finalize_routes
from api.routes import free_chat as free_chat_routes
from api.routes import guide as guide_routes
from api.routes import history as history_routes
from api.routes import library as library_routes
from api.routes import logs as logs_routes
from api.routes import maintain as maintain_routes
from api.routes import meta as meta_routes
from api.routes import outline as outline_routes
from api.routes import plan as plan_routes
from api.routes import project as project_routes
from api.routes import review as review_routes
from api.routes import stats as stats_routes
from api.routes import workshop as workshop_routes
from api.routes import writing as writing_routes
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

_LOCAL_CLIENTS = frozenset({
    "127.0.0.1",
    "::1",
    "localhost",
    "::ffff:127.0.0.1",
})


def _is_local_client(host: str) -> bool:
    h = (host or "").strip().lower()
    if not h:
        return True
    if h in _LOCAL_CLIENTS:
        return True
    if h.startswith("::ffff:127.0.0.1"):
        return True
    return False


def _safe_print(msg: str) -> None:
    """Windows GBK 控制台可能无法输出 emoji，降级为可打印字符。"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        ))


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_library()
    init_data_dirs()
    config.load_runtime_settings()
    set_total_cost(load_total_cost())
    load_free_chat()
    if ws.auto_restore_session_if_needed():
        _safe_print("[OK] 已从磁盘恢复写书对话（session_autosave.json）")
    if config.WEB_TOKEN:
        _safe_print("[AUTH] Web API 已启用令牌鉴权（请求头 X-Novel-Token）")
    if config.CONTEXT_LOG_ENABLED:
        _safe_print(
            "[LOG] 上下文体积日志：data/context_log.jsonl（NOVEL_CONTEXT_LOG=0 可关闭）"
        )
    rs = runtime_log.get_status()
    _safe_print(
        f"[DEBUG] 运行时日志 [{rs['runtime_env_label']}]：{rs['log_path']}"
        f"（NOVEL_RUNTIME_LOG=0 可关闭）"
    )
    app.state.ctx = init_context()
    yield


app = FastAPI(title="小说写作助手", lifespan=lifespan)
app.include_router(finalize_routes.router)
app.include_router(review_routes.router)
app.include_router(maintain_routes.router)
app.include_router(library_routes.router)
app.include_router(outline_routes.router)
app.include_router(workshop_routes.router)
app.include_router(female_fiction_routes.router)
app.include_router(batch_routes.router)
app.include_router(guide_routes.router)
app.include_router(codex_routes.router)
app.include_router(chapters_routes.router)
app.include_router(plan_routes.router)
app.include_router(free_chat_routes.router)
app.include_router(writing_routes.router)
app.include_router(stats_routes.router)
app.include_router(history_routes.router)
app.include_router(config_routes.router)
app.include_router(meta_routes.router)
app.include_router(project_routes.router)
app.include_router(logs_routes.router)


@app.middleware("http")
async def web_auth_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)

    client_host = request.client.host if request.client else ""
    if config.WEB_TOKEN:
        token = request.headers.get("X-Novel-Token", "")
        if token != config.WEB_TOKEN:
            return JSONResponse(
                status_code=401,
                content={"detail": "需要有效的 X-Novel-Token（与 .env 中 NOVEL_WEB_TOKEN 一致）"},
            )
    elif client_host and not _is_local_client(client_host):
        return JSONResponse(
            status_code=403,
            content={
                "detail": "非本地访问被拒绝。请设置 NOVEL_WEB_TOKEN 并通过 X-Novel-Token 鉴权，"
                "或仅在 127.0.0.1 上使用。"
            },
        )

    return await call_next(request)


@app.middleware("http")
async def runtime_error_middleware(request: Request, call_next):
    path = request.url.path
    try:
        response = await call_next(request)
        if path.startswith("/api/") and response.status_code >= 500:
            runtime_log.log_error(
                "web",
                f"{request.method} {path}",
                f"HTTP {response.status_code}",
                data={"status_code": response.status_code},
            )
        return response
    except HTTPException as exc:
        if exc.status_code >= 500:
            runtime_log.log_error(
                "web",
                f"{request.method} {path}",
                exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                data={"status_code": exc.status_code},
            )
        raise
    except Exception as exc:
        runtime_log.log_error(
            "web",
            f"{request.method} {path}",
            str(exc),
            exc=exc,
        )
        raise


def run(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    import threading
    import time
    import webbrowser

    import uvicorn

    safe_hosts = ("127.0.0.1", "localhost", "::1")
    if host not in safe_hosts:
        if not config.WEB_TOKEN:
            _safe_print(
                "[WARN] 非本地监听必须设置 NOVEL_WEB_TOKEN；"
                "已强制回退到 127.0.0.1"
            )
            host = "127.0.0.1"
        else:
            _safe_print(
                "[WARN] Web 服务正在非本地地址监听。"
                "已启用 NOVEL_WEB_TOKEN 鉴权，仍请勿对不可信网络暴露。"
            )

    if open_browser:
        def _open() -> None:
            time.sleep(1.2)
            webbrowser.open(f"http://{host}:{port}/docs")

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import os

    _port = 8765
    try:
        _port = int(os.environ.get("NOVEL_WEB_PORT", "8765"))
    except ValueError:
        pass
    run(port=_port)
