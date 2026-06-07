# 六项质量功能（已并入用户手册）

> 用户向说明已合并至 **[novel-writer-manual.md](./novel-writer-manual.md)**：
> - **[五、质量工具](./novel-writer-manual.md#五质量工具)** — 六项对照、章后清单、节奏/情感
> - **[§3.7 快穿批量流程](./novel-writer-manual.md#37-快穿单世界批量--直改稿typeworld)** — 批量生成、直改稿、采纳
> - **[§4.6 质量页](./novel-writer-manual.md#46-质量审阅中心)** — 面板操作路径
>
> 下文为**开发者 API 索引**。

## Web 按钮 → API

| 按钮 | API | 提供商 | 说明 |
|------|-----|--------|------|
| 人物检查 | `POST /api/check/character-drift` | CHECK | 对照 char_static + char_dynamic |
| 角色观察 | `POST /api/observe` · `POST /api/observe/apply` | CHECK | 结构化提案；确认后写入档案 |
| 提取细节 | `POST /api/extract/details` | SUMMARY | `auto_append` → plot_threads_locked |
| 重复检查 | `POST /api/check/repetition` | CHECK | `{ scope: current\|recent3\|all }` |
| 爽点检查 | `POST /api/check/pacing` | CHECK | 需先有 summaries |
| 女频审阅 | `POST /api/review/female-fiction` | PROVIDER（直改稿）/ CHECK（诊断） | body: `mode`, `profile_id`, `revise`, `write_back` |
| 采纳改稿 | `POST /api/review/female-fiction/accept` | MAINTAIN（档案） | body: `{ log_id, sync_archive }` |
| 审阅 profile 列表 | `GET /api/review/profiles` | — | 当前书默认 + 可选列表 |
| 批量生成世界 | `POST /api/batch/world/generate` | PROVIDER | `{ overwrite, skip_existing }` |
| 世界闭环 | `POST /api/batch/world/remediate` | CHECK+PROVIDER | 诊断→改稿→档案 |
| 参考拆文 | `POST /api/deconstruct` | CHECK | 外部参考文 |

## Prompt 文件

| 路径 | 说明 |
|------|------|
| `docs/review-prompts/{type}-{platform}.md` | 女频审阅路由 |
| `mode: rewrite-only` | 直改稿 profile，不拼接 `_revise-appendix.md` |
| `review_prompts.py` | 解析与 `load_prompt_text()` |

## 代码索引

| 模块 | 路径 |
|------|------|
| Prompt | `summarizer.py`, `docs/review-prompts/` |
| 审阅/采纳 | `main.py` → `api_run_female_fiction_review`, `api_accept_female_fiction_rewrite` |
| 批量生成 | `batch_generate.py` |
| 世界批次 | `batch_world.py`, `batch_remediate.py` |
| 路由 | `web_app.py` |
| 前端 | `web/app.js`, `web/index.html` |
