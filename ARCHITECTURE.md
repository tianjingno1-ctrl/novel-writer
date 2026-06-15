# 架构约定（重构期）

> **每次 PR 对照检查；违反即打回。**

## 架构红线

1. `core/` 内任何文件禁止 `import main` / `import web_app` / `import api`
2. 禁止三层同名转发：`A.run_X → B.run_X → C.run_X`
3. 禁止在 route / orchestration / reviewer 里直接 `Path.write_text`（统一走 `BookStore.write` / `file_utils.atomic_write_text`）
4. 新功能不得新建 `services/*.py`（统一进 `core/orchestration/`）
5. `main.py` 不得**新增**业务逻辑或 `api_run_*`；测试兼容符号经 `app/main_forwards.py` PEP 562 转发

## 目标分层

```
api/routes/          → HTTP only（请求解析、响应序列化；零 import main）
core/orchestration/  → 多步流程编排（finalize、review、archive_sync）
core/                → 单能力（reviewer、maintain、generator、book_store、schemas）
app/                 → bootstrap、paths、llm、writing_*、cli、runtime（业务实现层）
main.py              → 路径锚点（测试 patch）+ 显式 re-export + __getattr__ 转发
web_app.py           → FastAPI 装配 + lifespan
```

## 每步验收检查表

完成一步后确认：

- [ ] `grep -r "import main" core/` → 结果为空
- [ ] `grep -r "import main" api/` → 结果为空
- [ ] `grep -r "import main" app/` → 仅 `paths.py`（测试 mirror）
- [ ] 新函数签名不含 `app_state` / `request_dict` 等 HTTP 概念
- [ ] 至少有一个单测不需要启动 web server

## 执行原则

> **迁一块，同时删旧的，同时改所有调用方。**  
> 不留转发壳，不留注释掉的代码，不留「以后再删」的 TODO。

每步完成后项目应**可运行**，不是「先堆着，最后一起清」。

## 迁移进度

| Step | 内容 | 状态 |
|------|------|------|
| 0 | 目录骨架 `core/orchestration/`、`app/`、`api/routes/` | ✅ |
| 1 | `AppContext` + `app/bootstrap.py` | ✅ |
| 2 | `BookStore` 去掉 `import main` | ✅ |
| 3 | 删 `services/` | ✅ |
| 4 | `finalize` → `core/orchestration/finalize.py` | ✅ |
| 5 | `review` → `core/orchestration/review.py` | ✅ |
| 6 | `web_app.py` → `api/routes/*` | ✅ |
| 7 | 业务迁 `app/*`；`main.py` 瘦身至 ~148 行 | ✅ P3 完成 |
| 8 | 清理 `*Deps` Callable、收敛 `LlmHooks` → `core.llm` | 待做（低优先级） |

### P3 重构摘要（2026-06）

| 模块 | 职责 |
|------|------|
| `app/paths.py` | 路径 source of truth；`mirror_to_main` 兼容测试 |
| `app/bootstrap.py` | `bootstrap_library` / `init_data_dirs` / `init_context` |
| `app/bootstrap_data.py` | `INITIAL_FILE_TEMPLATES` / `DEFAULT_CHAT_PROMPTS` |
| `core/llm.py` | `call_api` / `build_cached_system` / `_request_lock` |
| `infra/file_utils.py` + `core/book_store.py` | `read_text` / `write_text` / archive 双写 |
| `infra/billing/` | 费用链 |
| `app/writing_ctx.py` | 写作上下文块 |
| `app/chapter_io.py` | 章节 IO |
| `app/writing_session.py` | 会话 IO |
| `app/writing_chat.py` | 写作主链 |
| `app/runtime.py` | `get_app_status` / heartbeat |
| `app/cli.py` | REPL + `do_*` |
| `app/main_forwards.py` | `main.*` PEP 562 转发表 |

- `main.py`：~2800 行 → **148 行**
- `app/*` lazy `import main`：**0**（`paths.py` mirror ×4 除外）
- `api/*` `import main`：**0**
- 测试：**117 passed**

详见 `docs/schemas.md`、`docs/deps-audit.md`。
