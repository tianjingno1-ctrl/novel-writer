"""Web UI — FastAPI 后端。"""

from __future__ import annotations

import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import config
import main as core
import novel_data
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

WEB_DIR = Path(__file__).resolve().parent / "web"
MAX_CONTENT_BYTES = 2 * 1024 * 1024  # 2MB，章节/Codex 文件
MAX_API_TEXT_CHARS = 50_000  # 对话/指令等 API 文本
VALID_CODEX_NAMES = frozenset(core.CODEX_FILES.keys())
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    core.init_data_dirs()
    config.load_runtime_settings()
    core.set_total_cost(core.load_total_cost())
    core.load_free_chat()
    if core.auto_restore_session_if_needed():
        print("✅ 已从磁盘恢复写书对话（session_autosave.json）")
    if config.WEB_TOKEN:
        print("🔐 Web API 已启用令牌鉴权（请求头 X-Novel-Token）")
    yield


app = FastAPI(title="小说写作助手", lifespan=lifespan)


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

_stats_cache: dict | None = None
_stats_sig: tuple | None = None
_stats_lock = threading.Lock()


def _require_ok(result: dict, default_msg: str = "操作失败") -> dict:
    """将 core 层 {ok: false, error} 统一转为 HTTPException。"""
    if not result.get("ok", True):
        raise HTTPException(400, result.get("error", default_msg))
    return result


def _build_stats_sig(chapters: list[tuple[int, object]]) -> tuple:
    sig_parts: list[tuple] = []
    for num, path in chapters:
        st = path.stat()
        sig_parts.append((num, st.st_mtime_ns, st.st_size))
    if novel_data.PLAN_FILE.exists():
        st = novel_data.PLAN_FILE.stat()
        sig_parts.append(("plan", st.st_mtime_ns, st.st_size))
    codex_dir = novel_data.CODEX_DIR
    if codex_dir.exists():
        for p in sorted(codex_dir.glob("*.md")):
            st = p.stat()
            sig_parts.append((p.name, st.st_mtime_ns, st.st_size))
    for extra in (core.SUMMARIES_FILE, core.COST_LOG, core.COST_LOG_JSONL):
        if extra.exists():
            st = extra.stat()
            sig_parts.append((extra.name, st.st_mtime_ns, st.st_size))
    return tuple(sig_parts)


def _compute_stats(chapters: list[tuple[int, object]]) -> dict:
    chapter_stats = []
    total_chars = 0
    for num, path in chapters:
        text = core.read_text(path)
        chars = len(re.sub(r"\s", "", text))
        total_chars += chars
        chapter_stats.append({"num": num, "chars": chars, "file": path.name})

    plan = novel_data.load_plan()
    scene_count = sum(
        len(ch.get("scenes", [])) for ch in plan.get("chapters", {}).values()
    )
    codex_count = len(novel_data.list_codex_entries())

    return {
        "total_chars": total_chars,
        "chapter_count": len(chapters),
        "scene_count": scene_count,
        "codex_count": codex_count,
        "summary_count": core.count_summaries(),
        "total_cost": core.get_total_cost(),
        "chapters": chapter_stats,
    }


def _check_file_content(v: str) -> str:
    if len(v.encode("utf-8")) > MAX_CONTENT_BYTES:
        mb = MAX_CONTENT_BYTES // 1024 // 1024
        raise ValueError(f"内容过大（上限 {mb}MB）")
    return v


def _check_api_text(v: str) -> str:
    if len(v) > MAX_API_TEXT_CHARS:
        raise ValueError(f"文本过长（上限 {MAX_API_TEXT_CHARS} 字符）")
    return v


class ChatRequest(BaseModel):
    instruction: str = ""
    scene_beat: str = ""
    scene_id: str = ""

    _validate_instruction = field_validator("instruction")(_check_api_text)
    _validate_scene_beat = field_validator("scene_beat")(_check_api_text)


class ContentBody(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def check_size(cls, v: str) -> str:
        return _check_file_content(v)


class FreeChatRequest(BaseModel):
    content: str
    provider: str | None = None

    _validate_content = field_validator("content")(_check_api_text)


class ContextConfig(BaseModel):
    turns: int | None = None
    mode: str | None = None


class ProviderSwitch(BaseModel):
    provider: str


class SceneCreate(BaseModel):
    chapter_num: int
    title: str = "新场景"
    beat: str = ""

    _validate_title = field_validator("title")(_check_api_text)
    _validate_beat = field_validator("beat")(_check_api_text)


class SceneUpdate(BaseModel):
    title: str | None = None
    beat: str | None = None
    summary: str | None = None
    done: bool | None = None

    @field_validator("title", "beat", "summary")
    @classmethod
    def check_optional_text(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _check_api_text(v)


class ChapterTitleUpdate(BaseModel):
    title: str

    _validate_title = field_validator("title")(_check_api_text)


class SceneReorder(BaseModel):
    scene_ids: list[str]


class CodexCreate(BaseModel):
    name: str
    content: str = ""

    _validate_name = field_validator("name")(_check_api_text)

    @field_validator("content")
    @classmethod
    def check_content(cls, v: str) -> str:
        return _check_file_content(v)


class CodexActive(BaseModel):
    active: list[str]


class OutlineRequest(BaseModel):
    next_count: int = 3

    @field_validator("next_count")
    @classmethod
    def validate_next_count(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("章节数须在 1-10 之间")
        return v


class OutlineApplyRequest(BaseModel):
    offset: int = 1
    replace: bool = False
    reply: str | None = None

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("offset 须在 1-10 之间")
        return v


# ── 路由 ──────────────────────────────────────────
@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/status")
def status() -> dict:
    status_data = core.get_app_status()
    last = core.get_last_call_info()
    if last:
        status_data["last_call"] = last
    return status_data


class ProjectUpdate(BaseModel):
    title: str | None = None
    world_label: str | None = None
    tagline: str | None = None
    notes: str | None = None


@app.get("/api/project")
def get_project() -> dict:
    return novel_data.get_project_meta()


@app.put("/api/project")
def put_project(body: ProjectUpdate) -> dict:
    fields = body.model_dump(exclude_unset=True)
    return novel_data.save_project_meta(**fields)


@app.get("/api/overview")
def bookshelf_overview() -> dict:
    chapters = core.list_chapters()
    stats = _compute_stats(chapters)
    latest = core.get_latest_chapter()
    current = latest[0] if latest else None
    return novel_data.build_bookshelf_overview(
        chapters=chapters,
        chapter_stats=stats.get("chapters", []),
        summaries_text=core.read_text(core.SUMMARIES_FILE),
        world_text=core.read_text(core.WORLD_FILE),
        current_chapter=current,
    )


@app.get("/api/stats")
def stats() -> dict:
    global _stats_cache, _stats_sig

    # 单人工具章节数有限；锁内完成 list + sig + 读取，保证签名与内容一致
    with _stats_lock:
        chapters = core.list_chapters()
        sig = _build_stats_sig(chapters)
        if _stats_cache is not None and _stats_sig == sig:
            return _stats_cache
        result = _compute_stats(chapters)
        _stats_cache = result
        _stats_sig = sig
        return result


# ── 章节 ──────────────────────────────────────────
@app.get("/api/chapters")
def chapters() -> dict:
    items = [{"num": n, "file": p.name} for n, p in core.list_chapters()]
    return {"chapters": items}


@app.get("/api/chapters/{num}")
def get_chapter(num: int) -> dict:
    ch = core.get_chapter_by_num(num)
    if ch is None:
        raise HTTPException(404, f"章节 ch{num:03d} 不存在")
    plan = novel_data.get_chapter_plan(num)
    return {**ch, "plan": plan}


@app.put("/api/chapters/{num}")
def put_chapter(num: int, body: ContentBody) -> dict:
    return core.save_chapter_by_num(num, body.content)


@app.post("/api/chapters/new")
def new_chapter() -> dict:
    r = core.create_next_chapter()
    novel_data.ensure_chapter_plan(r["num"])
    return r


# ── Plan 场景 ─────────────────────────────────────
@app.get("/api/plan")
def plan_all() -> dict:
    return {"chapters": novel_data.list_plan_chapters()}


@app.get("/api/plan/full")
def plan_full() -> dict:
    return {"chapters": novel_data.list_plan_details()}


@app.put("/api/plan/{chapter_num}/title")
def plan_update_chapter_title(chapter_num: int, body: ChapterTitleUpdate) -> dict:
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "标题不能为空")
    if novel_data.update_chapter_title(chapter_num, title) is None:
        raise HTTPException(404, "章节不存在")
    return {"ok": True, "title": title}


@app.put("/api/plan/{chapter_num}/reorder")
def plan_reorder_scenes(chapter_num: int, body: SceneReorder) -> dict:
    if not novel_data.reorder_scenes(chapter_num, body.scene_ids):
        raise HTTPException(404, "章节不存在")
    return {"ok": True}


@app.get("/api/plan/{chapter_num}")
def plan_chapter(chapter_num: int) -> dict:
    ch = novel_data.get_chapter_plan(chapter_num)
    if ch is None:
        ch = novel_data.ensure_chapter_plan(chapter_num)["chapters"][str(chapter_num)]
        ch = {"num": chapter_num, **ch}
    return ch


@app.post("/api/plan/scenes")
def plan_add_scene(body: SceneCreate) -> dict:
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "场景标题不能为空")
    scene = novel_data.add_scene(body.chapter_num, title, body.beat)
    return {"ok": True, "scene": scene}


@app.put("/api/plan/scenes/{scene_id}")
def plan_update_scene(scene_id: str, body: SceneUpdate) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if "title" in fields and not str(fields["title"]).strip():
        raise HTTPException(400, "场景标题不能为空")
    scene = novel_data.update_scene(scene_id, **fields)
    if scene is None:
        raise HTTPException(404, "场景不存在")
    return {"ok": True, "scene": scene}


@app.delete("/api/plan/scenes/{scene_id}")
def plan_delete_scene(scene_id: str) -> dict:
    if not novel_data.delete_scene(scene_id):
        raise HTTPException(404, "场景不存在")
    return {"ok": True}


@app.put("/api/plan/active/{scene_id}")
def plan_set_active(scene_id: str) -> dict:
    if novel_data.get_scene(scene_id) is None:
        raise HTTPException(404, "场景不存在")
    return novel_data.set_active_scene(scene_id)


# ── Codex 全局文件 ────────────────────────────────
@app.get("/api/codex")
def codex_list() -> dict:
    return {"files": list(core.CODEX_FILES.keys())}


@app.get("/api/codex/{name}")
def get_codex(name: str) -> dict:
    if name not in VALID_CODEX_NAMES:
        raise HTTPException(400, "非法设定文件名")
    data = core.get_codex(name)
    if data is None:
        raise HTTPException(404, f"未知设定: {name}")
    return data


@app.put("/api/codex/{name}")
def put_codex(name: str, body: ContentBody) -> dict:
    if name not in VALID_CODEX_NAMES:
        raise HTTPException(400, "非法设定文件名")
    return _require_ok(core.save_codex(name, body.content), "保存失败")


# ── Codex 条目 ────────────────────────────────────
@app.get("/api/codex-entries")
def codex_entries() -> dict:
    return {
        "entries": novel_data.list_codex_entries(),
        "active": novel_data.get_active_codex_ids(),
    }


@app.post("/api/codex-entries")
def codex_entry_create(body: CodexCreate) -> dict:
    return _require_ok(novel_data.create_codex_entry(body.name, body.content), "创建失败")


@app.put("/api/codex-entries/active")
def codex_set_active(body: CodexActive) -> dict:
    return novel_data.set_active_codex_ids(body.active)


@app.get("/api/codex-entries/{entry_id}")
def codex_entry_get(entry_id: str) -> dict:
    entry = novel_data.get_codex_entry(entry_id)
    if entry is None:
        raise HTTPException(404, "条目不存在")
    return entry


@app.put("/api/codex-entries/{entry_id}")
def codex_entry_save(entry_id: str, body: ContentBody) -> dict:
    return _require_ok(novel_data.save_codex_entry(entry_id, body.content), "保存失败")


@app.delete("/api/codex-entries/{entry_id}")
def codex_entry_delete(entry_id: str) -> dict:
    return _require_ok(novel_data.delete_codex_entry(entry_id), "删除失败")


# ── 对话 ──────────────────────────────────────────
@app.get("/api/chat/history")
def chat_history() -> dict:
    return {
        "messages": core.get_chat_history(),
        "appended_indices": core.get_appended_indices(),
        "context_turns": config.CHAT_CONTEXT_TURNS,
        "context_mode": config.CONTEXT_MODE,
    }


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    core.touch_user_active()
    return _require_ok(
        core.writing_chat(req.instruction, req.scene_beat, req.scene_id),
        "写书对话失败",
    )


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    core.touch_user_active()

    def generate():
        for event in core.writing_chat_stream(
            req.instruction, req.scene_beat, req.scene_id
        ):
            yield f"data: {event}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat/clear")
def chat_clear() -> dict:
    core.clear_chat_session()
    return {"ok": True}


@app.post("/api/chat/restore")
def chat_restore() -> dict:
    return _require_ok(core.restore_chat_session(), "恢复失败")


class ChatPromptItem(BaseModel):
    id: str
    title: str
    content: str = ""


class ChatPromptsBody(BaseModel):
    prompts: list[ChatPromptItem]


@app.get("/api/chat/prompts")
def get_chat_prompts() -> dict:
    return core.load_chat_prompts()


@app.put("/api/chat/prompts")
def put_chat_prompts(body: ChatPromptsBody) -> dict:
    prompts = [p.model_dump() for p in body.prompts]
    return core.save_chat_prompts(prompts)


@app.get("/api/free-chat/history")
def free_chat_history() -> dict:
    return {
        "messages": core.get_free_chat_history(),
        "provider": core.get_free_chat_provider(),
    }


@app.put("/api/free-chat/provider")
def set_free_chat_provider(body: ProviderSwitch) -> dict:
    _require_ok(core.set_free_chat_provider(body.provider), "切换失败")
    from providers import reset_client

    reset_client(body.provider)
    return {"ok": True, **core.get_app_status()}


@app.post("/api/free-chat")
def free_chat_send(body: FreeChatRequest) -> dict:
    core.touch_user_active()
    return _require_ok(core.free_chat(body.content, provider=body.provider), "自由聊失败")


@app.post("/api/free-chat/clear")
def free_chat_clear() -> dict:
    core.clear_free_chat()
    return {"ok": True}


@app.post("/api/summary")
def run_summary() -> dict:
    return _require_ok(core.api_run_summary(), "生成概述失败")


@app.post("/api/check")
def run_check() -> dict:
    return _require_ok(core.api_run_check(), "连续性检查失败")


@app.post("/api/outline")
def run_outline(body: OutlineRequest) -> dict:
    return _require_ok(core.api_run_outline(body.next_count), "续章灵感生成失败")


@app.get("/api/outline/latest")
def outline_latest() -> dict:
    return core.get_outline_latest()


@app.post("/api/outline/apply")
def outline_apply(body: OutlineApplyRequest) -> dict:
    result = core.api_apply_outline(
        body.offset,
        replace=body.replace,
        reply=body.reply,
    )
    if result.get("need_replace"):
        raise HTTPException(409, result.get("error", "需要确认覆盖"))
    return _require_ok(result, "写入 Plan 失败")


@app.put("/api/config/context")
def set_context(cfg: ContextConfig) -> dict:
    if cfg.turns is not None:
        if cfg.turns < 0 or cfg.turns > 100:
            raise HTTPException(400, "轮数范围 0-100")
        config.CHAT_CONTEXT_TURNS = cfg.turns
    if cfg.mode is not None:
        if cfg.mode not in ("turns", "summaries", "beats", "codex"):
            raise HTTPException(400, "mode 必须是 turns/summaries/beats/codex")
        config.CONTEXT_MODE = cfg.mode
    config.save_runtime_settings()
    return {
        "ok": True,
        "context_turns": config.CHAT_CONTEXT_TURNS,
        "context_mode": config.CONTEXT_MODE,
    }


@app.put("/api/config/provider")
def set_provider(body: ProviderSwitch) -> dict:
    if body.provider not in config.PROVIDERS:
        raise HTTPException(400, f"未知提供商: {body.provider}")
    config.PROVIDER = body.provider
    config.save_runtime_settings()
    from providers import reset_client

    reset_client(body.provider)
    return {"ok": True, **core.get_app_status()}


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.post("/api/chapters/undo-last")
def undo_last_chapter_write() -> dict:
    return _require_ok(core.undo_last_chapter_append(), "撤销失败")


class ApplyTurnBody(BaseModel):
    msg_index: int
    source: str = "assistant"  # assistant | user_draft

    @field_validator("msg_index")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("msg_index 不能为负")
        return v


@app.post("/api/chapters/{num}/apply-turn")
def apply_chapter_turn(num: int, body: ApplyTurnBody) -> dict:
    if body.source == "user_draft":
        result = core.apply_user_draft_turn_to_chapter(num, body.msg_index)
    elif body.source == "assistant":
        result = core.apply_assistant_turn_to_chapter(num, body.msg_index)
    else:
        raise HTTPException(400, "source 必须是 assistant 或 user_draft")
    return _require_ok(result, "替换章节失败")


def run(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    import threading
    import time
    import webbrowser

    import uvicorn

    safe_hosts = ("127.0.0.1", "localhost", "::1")
    if host not in safe_hosts:
        if not config.WEB_TOKEN:
            print(
                "⚠️  非本地监听必须设置 NOVEL_WEB_TOKEN；"
                "已强制回退到 127.0.0.1"
            )
            host = "127.0.0.1"
        else:
            print(
                "⚠️  警告：Web 服务正在非本地地址监听。"
                "已启用 NOVEL_WEB_TOKEN 鉴权，仍请勿对不可信网络暴露。"
            )

    if open_browser:
        def _open() -> None:
            time.sleep(1.2)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
