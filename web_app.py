"""Web UI — FastAPI 后端。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import config
import main as core
import novel_data
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

WEB_DIR = Path(__file__).resolve().parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    core.init_data_dirs()
    core.total_cost = core.load_total_cost()
    core.load_free_chat()
    yield


app = FastAPI(title="小说写作助手", lifespan=lifespan)


class ChatRequest(BaseModel):
    instruction: str = ""
    scene_beat: str = ""
    scene_id: str = ""


class ContentBody(BaseModel):
    content: str


class FreeChatRequest(BaseModel):
    content: str
    provider: str | None = None


class ContextConfig(BaseModel):
    turns: int | None = None
    mode: str | None = None


class ProviderSwitch(BaseModel):
    provider: str


class SceneCreate(BaseModel):
    chapter_num: int
    title: str = "新场景"
    beat: str = ""


class SceneUpdate(BaseModel):
    title: str | None = None
    beat: str | None = None
    summary: str | None = None
    done: bool | None = None


class ChapterTitleUpdate(BaseModel):
    title: str


class SceneReorder(BaseModel):
    scene_ids: list[str]


class CodexCreate(BaseModel):
    name: str
    content: str = ""


class CodexActive(BaseModel):
    active: list[str]


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


@app.get("/api/stats")
def stats() -> dict:
    import re

    chapters = core.list_chapters()
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
        "total_cost": core.total_cost,
        "chapters": chapter_stats,
    }


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
    scene = novel_data.add_scene(body.chapter_num, body.title, body.beat)
    return {"ok": True, "scene": scene}


@app.put("/api/plan/scenes/{scene_id}")
def plan_update_scene(scene_id: str, body: SceneUpdate) -> dict:
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
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
    return novel_data.set_active_scene(scene_id)


# ── Codex 全局文件 ────────────────────────────────
@app.get("/api/codex")
def codex_list() -> dict:
    return {"files": list(core.CODEX_FILES.keys())}


@app.get("/api/codex/{name}")
def get_codex(name: str) -> dict:
    data = core.get_codex(name)
    if data is None:
        raise HTTPException(404, f"未知设定: {name}")
    return data


@app.put("/api/codex/{name}")
def put_codex(name: str, body: ContentBody) -> dict:
    result = core.save_codex(name, body.content)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "保存失败"))
    return result


# ── Codex 条目 ────────────────────────────────────
@app.get("/api/codex-entries")
def codex_entries() -> dict:
    return {
        "entries": novel_data.list_codex_entries(),
        "active": novel_data.get_active_codex_ids(),
    }


@app.post("/api/codex-entries")
def codex_entry_create(body: CodexCreate) -> dict:
    result = novel_data.create_codex_entry(body.name, body.content)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "创建失败"))
    return result


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
    return novel_data.save_codex_entry(entry_id, body.content)


# ── 对话 ──────────────────────────────────────────
@app.get("/api/chat/history")
def chat_history() -> dict:
    return {
        "messages": core.get_chat_history(),
        "context_turns": config.CHAT_CONTEXT_TURNS,
        "context_mode": config.CONTEXT_MODE,
    }


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    core.touch_user_active()
    return core.writing_chat(req.instruction, req.scene_beat, req.scene_id)


@app.post("/api/chat/clear")
def chat_clear() -> dict:
    core.clear_chat_session()
    return {"ok": True}


@app.get("/api/free-chat/history")
def free_chat_history() -> dict:
    return {
        "messages": core.get_free_chat_history(),
        "provider": core.get_free_chat_provider(),
    }


@app.put("/api/free-chat/provider")
def set_free_chat_provider(body: ProviderSwitch) -> dict:
    result = core.set_free_chat_provider(body.provider)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "切换失败"))
    from providers import reset_client

    reset_client(body.provider)
    return {"ok": True, **core.get_app_status()}


@app.post("/api/free-chat")
def free_chat_send(body: FreeChatRequest) -> dict:
    core.touch_user_active()
    return core.free_chat(body.content, provider=body.provider)


@app.post("/api/free-chat/clear")
def free_chat_clear() -> dict:
    core.clear_free_chat()
    return {"ok": True}


@app.post("/api/summary")
def run_summary() -> dict:
    return core.api_run_summary()


@app.post("/api/check")
def run_check() -> dict:
    return core.api_run_check()


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
    from providers import reset_client

    reset_client(body.provider)
    return {"ok": True, **core.get_app_status()}


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def run(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    import threading
    import time
    import webbrowser

    import uvicorn

    if open_browser:
        def _open() -> None:
            time.sleep(1.2)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
