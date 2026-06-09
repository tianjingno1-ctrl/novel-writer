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
| `app/` | 业务实现：`bootstrap`、`llm`、`writing_*`、`cli`、`runtime`、`paths`、`book_io`、`cost` 等 |
| `app_state.py` | 进程内单例状态（CLI/API 共享；多用户需按 session 隔离） |
| `web_app.py` | FastAPI **纯 API**（`/api/*` + OpenAPI `/docs`），lifespan 调 `app.bootstrap` |
| `config.py` | 提供商、上下文策略、从 `.env` 读 Key |
| `prices.json` | 可选：覆盖各模型 token 单价（费用为预估） |
| `providers.py` | kie(Anthropic) + DeepSeek(OpenAI 兼容) 统一调用 |
| `summarizer.py` | 概述/检查的系统提示词 |
| `novel_data.py` | Plan 场景、Codex 设定条目 |
| `book_context.py` | 书库 `library/books/{id}/`、切换书、路径注入 |
| `core/orchestration/` | 多步流程编排（定稿、审阅、档案同步） |
| `app/` | 启动绑定 + 业务实现（见 `ARCHITECTURE.md` P3 模块表） |
| `core/book_store.py` | 书籍读写入口（概述、观察写盘） |
| `core/schemas/` | 跨模块数据契约（LLM JSON、服务 IO） |
| `review_prompts.py` | 女频审阅 Prompt 路由（`docs/review-prompts/`） |
| `batch_generate.py` | 按 plan Beat 批量生成世界章节 |
| `library/` | 书库 index + `books/{id}/`（world、chapters、plan 等） |

## 文档

| 文件 | 用途 |
|------|------|
| `docs/workflow.md` | **产品流程图**（定稿 + 五补丁） |
| `docs/data-schema.md` | **产品数据 Schema**（真相源、RuleRef、迁移） |
| `docs/product-plan.md` | 产品索引与 backlog |
| `docs/novel-writer-manual.md` | **完整使用指南**（系统设定、写作流程；旧 Web 顶栏 UI 已移除） |
| `docs/tech-intake.md` | 技术信息清单：栈、数据结构、上下文组装、API 索引 |
| `docs/six-quality-features.md` | 六项质量功能 API 索引（用户说明已并入手册 §五） |

## API 与产品模块（新前端规划）

旧 `web/` 静态页已删除。业务能力通过 `web_app.py` 的 `/api/*` 暴露；交互见 **http://127.0.0.1:8765/docs**。

前端已实现 MVP：书架、开书向导（含拆文/审阅标准）、心流写作 + Gate 一章循环、归因抽屉、稿件/完结、口味库、设置（模型/Prompt Cache）。待接：自由聊、批量生成、Codex、六项质量、Prompt 节点编辑。

## 改 bug 时注意

1. **不要提交 `.env`**，只改 `.env.example` 占位说明。系统环境变量优先于 `.env`。
2. **API 无鉴权、单进程单会话**：默认仅 `127.0.0.1`；可设 `NOVEL_WEB_TOKEN` 启用最小鉴权。Provider/上下文变更写入 `data/runtime.json` 持久化。
3. 写书与自由聊**模型选择独立**；自由聊 provider 存在 `data/free_chat.json`（已 gitignore）。
4. `providers.py`：system 为空时不传 Anthropic `system` 参数。
5. DeepSeek 不支持 Prompt Cache；kie 写作走 `build_cached_system()`。
6. kie.ai Claude 须 `auth_token`（Bearer）+ 自定义 `User-Agent`（见 `providers._get_anthropic`），勿改回纯 `api_key`。
6. 章节/会话写入用 `file_utils.atomic_write_text`；费用日志为 `cost_log.jsonl`。
7. 新 UI 在 `frontend/`（Vite + React）；勿恢复已删除的 `web/app.js` 单页。

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
