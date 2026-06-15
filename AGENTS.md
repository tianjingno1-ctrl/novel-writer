# AI 协作者指南

本仓库是**长篇小说辅助写作工具**（Python），含 CLI、**HTTP API** 与 **React 前端**（`frontend/`）。接手改 bug 时请先读本文。

## 快速启动

```bash
cd novel_writer
cp .env.example .env   # Windows: copy .env.example .env
# 在 .env 填入 KIE_API_KEY、DEEPSEEK_API_KEY（仓库内不含真实 Key）
pip install -r requirements.txt
python web_app.py      # API: http://127.0.0.1:8765/docs
# 或
python main.py         # CLI
# 前端（另开终端）
cd frontend && npm install && npm run dev   # http://127.0.0.1:5173 ，/api 代理到 8765
```

## 目录结构

| 路径 | 说明 |
|------|------|
| `main.py` | **路径锚点** + 测试契约 re-export（`__getattr__` → `app/main_forwards.py`）；CLI 入口 `python main.py` |
| `app/` | 启动绑定 + 业务：`bootstrap`、`llm`、`writing_*`、`cli`、`runtime` 等（见 `ARCHITECTURE.md`） |
| `app_state.py` | 进程内单例状态（CLI/API 共享；多用户需按 session 隔离） |
| `web_app.py` | FastAPI **纯 API**（`/api/*` + OpenAPI `/docs`），lifespan 调 `app.bootstrap` |
| `config.py` | 提供商、上下文策略、从 `.env` 读 Key |
| `prices.json` | 可选：覆盖各模型 token 单价（费用为预估） |
| `providers.py` | kie(Anthropic) + DeepSeek(OpenAI 兼容) 统一调用 |
| `summarizer.py` | 概述/检查的系统提示词 |
| `novel_data.py` | Plan 场景、Codex 设定条目 |
| `book_context.py` | 书库 `library/books/{id}/`、切换书、路径注入 |
| `core/chapter_roles.py` | 章 `role` / `intent` 契约与 A9 序列校验 |
| `core/chapter_role_overlay.py` | L1b/L2/L4 overlay 与 L5b 按 role 路由 |
| `core/orchestration/` | 多步流程编排（定稿、审阅、档案同步） |
| `core/book_store.py` | 书籍读写入口（概述、观察写盘） |
| `core/schemas/` | 跨模块数据契约（LLM JSON、服务 IO） |
| `review_prompts.py` | 女频审阅 Prompt 路由（`docs/review-prompts/`） |
| `library/` | 书库 index + `books/{id}/`（world、chapters、plan 等） |

## 文档（协作者只读顺序）

| 顺序 | 文件 | 用途 |
|------|------|------|
| 1 | `docs/workflow.md` | 用户路径 **A→L→P→E**（交互真相源） |
| 2 | `docs/chapter-roles.md` | 章 **role / intent / A9 校验**（叙事语法 v1.0） |
| 3 | `docs/canonical-status.md` | **唯一排期**（Track S/F/Prompt/**E**）+ 做了/没做/库存 |
| 4 | `docs/data-schema.md` | 落盘字段、RuleRef、迁移 |
| 5 | `docs/product-plan.md` | 原则与补丁摘要（不背 backlog） |
| 6 | `docs/tech-intake.md` | 开发者 API/栈 |

**排期与 backlog 只改 `canonical-status.md` §七**，勿在本文件维护平行列表。

## API 与产品模块（前端）

旧 `web/` 静态页已删除。业务能力通过 `web_app.py` 的 `/api/*` 暴露；交互见 **http://127.0.0.1:8765/docs**。

**已删旧 Web 专用路由（勿恢复）**：`/api/guide/*`、`/api/workshop/*`、`/api/outline/*`（独立 HTTP）、`/api/overview`、`/api/chat/prompts`、**`/api/batch/*`**。续章灵感仍可通过 `finalize` 内部调用；开书规划用 `prefill/*`。

### 前端布局（2026-06 UI）

- **52px 左侧栏**：书架 / 稿件 / 写作偏好 / 设置（无独立「写作」Tab；从书架进 `/writing`）
- **设计令牌**：`frontend/src/index.css`（13px 正文、语义色蓝/绿/红/橙）
- **写作页两栏**：章节列表 | **中间栏**（正文全文 + 字数条 + Gate 卡片；流式/只读/可编辑）
- **已移除**：右侧 `PreviewPanel`（正文 Tab + 编辑/读者 L2 Tab）
- **Gate 组件**：`ChapterGates` + `GatePanel` + `GateStepIndicator`（已移除全屏 `GateOverlay`）
- **诊断**：`AttributionRulesDrawer`（用户向文案，非「Prompt 归因」）

### 已实现页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 书架 | 网格书卡、筛选、`bookshelf_stats` 进度 |
| `/library/new` | 开书向导 | 5 步，草稿可 `?resume=1` 续写 |
| `/writing` | 写作 | 一章 Gate 循环 |
| `/manuscripts` | 稿件 | 投递中心（预检 / 结果录入 / 拒稿诊断） |
| `/complete` | 完结 | 庆祝弹窗 → 跳转投递 |
| `/settings` | 设置 | 左栏：写作偏好 / 费用 / 模型 / 作者档案 / 鉴权 |

## 改 bug 时注意

1. **不要提交 `.env`**，只改 `.env.example` 占位说明。系统环境变量优先于 `.env`。
2. **API 默认单进程**：写作对话按 **client scope（token/host）+ book_id** 隔离（`infra/session_book.py`）；切书保留各书内存会话。默认仅 `127.0.0.1`；可设 `NOVEL_WEB_TOKEN` 启用最小鉴权。Provider/上下文变更写入 `data/runtime.json` 持久化。
3. `providers.py`：system 为空时不传 Anthropic `system` 参数。
5. DeepSeek 不支持 Prompt Cache；kie 写作走 `build_cached_system()`。
6. kie.ai Claude 须 `auth_token`（Bearer）+ 自定义 `User-Agent`（见 `providers._get_anthropic`），勿改回纯 `api_key`。
6. 章节/会话写入用 `file_utils.atomic_write_text`；费用日志为 `cost_log.jsonl`。
7. 新 UI 在 `frontend/`（Vite + React + 侧栏布局）；勿恢复已删除的 `web/app.js` 单页，勿恢复已删的 `GateOverlay` / `StreamWriter` / `ManualGatePanel`。

## 架构红线（重构期）

**完整规则见 [ARCHITECTURE.md](./ARCHITECTURE.md)**。每次 PR 对照，违反即打回：

1. `core/` 禁止 `import main` / `web_app` / `api`
2. 禁止三层同名转发；禁止新建 `services/*.py`
3. 禁止 route / orchestration / reviewer 里直接 `Path.write_text`
4. `main.py` 不得**新增**业务逻辑或 `api_run_*`；新代码进 `app/*` 或 `core/*`
5. 档案写盘走 `BookStore`；LLM 解析类型放 `core/schemas/llm.py`

详见 `docs/schemas.md`、`docs/deps-audit.md`。

## 测试

```bash
cd novel_writer
python -m unittest discover -s tests -v
```

## 常见排查

- API 报错：检查 `.env` 与 `config.is_api_key_configured()`
- API 起不来：`pip install fastapi uvicorn`
- 清华源 403：用 `pip install -i https://pypi.org/simple -r requirements.txt`
