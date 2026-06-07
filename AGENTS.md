# AI 协作者指南

本仓库是**长篇小说辅助写作工具**（Python），含 CLI 与 Web UI。接手改 bug 时请先读本文。

## 快速启动

```bash
cd novel_writer
cp .env.example .env   # Windows: copy .env.example .env
# 在 .env 填入 KIE_API_KEY、DEEPSEEK_API_KEY（仓库内不含真实 Key）
pip install -r requirements.txt
python web_app.py      # Web: http://127.0.0.1:8765
# 或
python main.py         # CLI
```

## 目录结构

| 路径 | 说明 |
|------|------|
| `main.py` | 核心业务：写作对话、/summary、/check、自由聊、会话持久化 |
| `app_state.py` | 进程内单例状态（CLI/Web 共享；多用户需按 session 隔离） |
| `web_app.py` | FastAPI 后端，挂载 `web/` 静态前端 |
| `config.py` | 提供商、上下文策略、从 `.env` 读 Key |
| `prices.json` | 可选：覆盖各模型 token 单价（费用为预估） |
| `providers.py` | kie(Anthropic) + DeepSeek(OpenAI 兼容) 统一调用 |
| `summarizer.py` | 概述/检查的系统提示词 |
| `novel_data.py` | Plan 场景、Codex 设定条目 |
| `book_context.py` | 书库 `library/books/{id}/`、切换书、路径注入 |
| `review_prompts.py` | 女频审阅 Prompt 路由（`docs/review-prompts/`） |
| `batch_generate.py` | 按 plan Beat 批量生成世界章节 |
| `web/` | `index.html` `app.js` `style.css` |
| `library/` | 书库 index + `books/{id}/`（world、chapters、plan 等） |

## 文档

| 文件 | 用途 |
|------|------|
| `docs/novel-writer-manual.md` | **完整使用指南**（系统设定、写作流程、注意事项合一） |
| `docs/tech-intake.md` | 技术信息清单：栈、数据结构、上下文组装、API 索引 |
| `docs/six-quality-features.md` | 六项质量功能 API 索引（用户说明已并入手册 §五） |

## 模式说明（Web 顶栏）

- **规划**：Scene Beat + Plan 看板
- **写作**：章节编辑
- **写书对话**：带三层 Prompt Cache 的写作 AI（kie Claude）
- **质量**：女频直改稿、批量生成世界、世界闭环、单章检查
- **自由聊**：无 system prompt，用户自选模型，不写章节
- **统计**：字数与 API 费用

## 改 bug 时注意

1. **不要提交 `.env`**，只改 `.env.example` 占位说明。系统环境变量优先于 `.env`。
2. **Web 无鉴权、单进程单会话**：默认仅 `127.0.0.1`；可设 `NOVEL_WEB_TOKEN` 启用最小鉴权。Provider/上下文变更写入 `data/runtime.json` 持久化。
3. 写书与自由聊**模型选择独立**；自由聊 provider 存在 `data/free_chat.json`（已 gitignore）。
4. `providers.py`：system 为空时不传 Anthropic `system` 参数。
5. DeepSeek 不支持 Prompt Cache；kie 写作走 `build_cached_system()`。
6. kie.ai Claude 须 `auth_token`（Bearer）+ 自定义 `User-Agent`（见 `providers._get_anthropic`），勿改回纯 `api_key`。
6. 章节/会话写入用 `file_utils.atomic_write_text`；费用日志为 `cost_log.jsonl`。
7. 保持中文 UI 文案与现有浅色主题风格。

## 测试

```bash
cd novel_writer
python -m unittest discover -s tests -v
```

## 常见排查

- API 报错：检查 `.env` 与 `config.is_api_key_configured()`
- Web 起不来：`pip install fastapi uvicorn`
- 清华源 403：用 `pip install -i https://pypi.org/simple -r requirements.txt`
