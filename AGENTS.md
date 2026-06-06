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
| `web_app.py` | FastAPI 后端，挂载 `web/` 静态前端 |
| `config.py` | 提供商、上下文策略、从 `.env` 读 Key |
| `providers.py` | kie(Anthropic) + DeepSeek(OpenAI 兼容) 统一调用 |
| `summarizer.py` | 概述/检查的系统提示词 |
| `novel_data.py` | Plan 场景、Codex 设定条目 |
| `web/` | `index.html` `app.js` `style.css` |
| `data/` | 小说数据（world、characters、chapters、plan.json） |

## 模式说明（Web 顶栏）

- **规划**：Scene Beat + Plan 看板
- **写作**：章节编辑
- **写书对话**：带三层 Prompt Cache 的写作 AI（kie Claude）
- **自由聊**：无 system prompt，用户自选模型，不写章节
- **统计**：字数与 API 费用

## 改 bug 时注意

1. **不要提交 `.env`**，只改 `.env.example` 占位说明。
2. 写书与自由聊**模型选择独立**；自由聊 provider 存在 `data/free_chat.json`（已 gitignore）。
3. `providers.py`：system 为空时不传 Anthropic `system` 参数。
4. DeepSeek 不支持 Prompt Cache；kie 写作走 `build_cached_system()`。
5. 保持中文 UI 文案与现有浅色主题风格。

## 常见排查

- API 报错：检查 `.env` 与 `config.is_api_key_configured()`
- Web 起不来：`pip install fastapi uvicorn`
- 清华源 403：用 `pip install -i https://pypi.org/simple -r requirements.txt`
