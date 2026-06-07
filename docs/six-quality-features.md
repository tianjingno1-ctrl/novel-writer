# 六项质量功能（已并入用户手册）

> 用户向说明已合并至 **[novel-writer-manual.md](./novel-writer-manual.md)**：
> - **[五、质量工具](./novel-writer-manual.md#五质量工具)** — 六项对照、章后清单、节奏/情感
> - **[四、写书对话按钮](./novel-writer-manual.md#44-写书对话)** — 面板操作路径
>
> 下文仅保留**开发者 API 索引**。

## Web 按钮 → API

| 按钮 | API | 提供商 | 说明 |
|------|-----|--------|------|
| 人物检查 | `POST /api/check/character-drift` | CHECK_PROVIDER | 对照 char_static + char_dynamic |
| 角色观察 | `POST /api/observe` · `POST /api/observe/apply` | CHECK_PROVIDER | 结构化提案；确认后写入档案 |
| 提取细节 | `POST /api/extract/details` | SUMMARY_PROVIDER | `auto_append` → plot_threads_locked |
| 重复检查 | `POST /api/check/repetition` | CHECK_PROVIDER | body: `{ scope: current\|recent3\|all }` |
| 爽点检查 | `POST /api/check/pacing` | CHECK_PROVIDER | 需先有 summaries |

## 代码索引

| 模块 | 路径 |
|------|------|
| Prompt | `summarizer.py` |
| API 逻辑 | `main.py` |
| 路由 | `web_app.py` |
| 前端 | `web/app.js`, `web/index.html` |
