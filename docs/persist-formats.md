# 磁盘持久化格式说明

> 文档契约（无可执行逻辑）。所有路径相对于单本书目录 `library/books/{book_id}/`（旧 `data/` 已迁移）。  
> **产品定稿 Schema（真相源、RuleRef、迁移）**：[data-schema.md](./data-schema.md)

---

## plan.json

章节规划与 Scene Beat。

顶层字段：

- `active_scene_id`: `str | null` — 当前选中场景 id
- `chapters`: `dict[str, ChapterPlan]`

**ChapterPlan**

- `title`: `str` — 卷/章标题（plan 层）
- `scenes`: `list[Scene]`

**Scene**

- `id`: `str` — 如 `ch1_opening01`
- `title`: `str`
- `beat`: `str` — Scene Beat 提纲
- `summary`: `str` — 可选
- `done`: `bool`
- `pace`: `str` — 快 | 中 | 慢
- `emotion_anchor`: `{ target, how }`
- `updated_at`: `str` — ISO 8601

读写：`novel_data.py`（`load_plan` / `save_plan` / `mutate_plan`）

---

## project.json

书籍元数据。

- `title`, `world_label`, `tagline`, `notes`
- `type`: `"novel" | "world" | "short"`
- `platform`: `"tomato" | "qimao" | "jjwxc"`
- `created_at`, `updated_at`

读写：`novel_data.py` / `book_context.py`

---

## chapters/chNNN.md

章节正文 — 纯 Markdown。

- 第一行可选：`# 第N章 标题`
- 正文：叙事 prose（无 JSON schema）

写入前经 `core/chapters.py` sanitize：

- 剥离 AI 元话语、HTML 实体
- 解析/应用 【章节标题】
- `format_chapter_file` 统一文件头

读写：`core.chapter_io` / `BookStore`（`read_chapter_content`、`write_text`）

---

## quality_log.jsonl

每行一条 JSON 审阅记录。

常见字段：

- `id`, `ts`, `kind`（summary | continuity | observe | …）
- `chapter_num`, `reply`, `summary`
- `persisted`, `persisted_detail`
- `extra` — 如 scope

读写：`quality_log.py`

---

## 档案 Markdown 文件

无 schema，约定段落结构：

| 文件 | 用途 |
|------|------|
| `world.md`, `style.md`, `characters.md` | 设定 |
| `char_static.md`, `char_dynamic.md` | 人物冷热分层 |
| `summaries_recent.md`, `summaries_archive.md` | 概述（近期 / 归档） |
| `plot_threads_locked.md` | 细节钉子 |
| `plot_threads_active.md` | `## 未回收` / `## 已回收` |
| `book_archive.md` | 合订本（`###` 小节对应上述文件） |

详见 [novel-writer-manual.md](./novel-writer-manual.md)、[canonical-status.md](./canonical-status.md) 与 [tech-intake.md](./tech-intake.md) §二
