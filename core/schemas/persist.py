"""磁盘持久化格式说明（文档契约，无可执行逻辑）。

所有路径相对于单本书目录 library/books/{book_id}/（旧 data/ 已迁移）。

**产品定稿 Schema（真相源、RuleRef、迁移）**：docs/data-schema.md
"""

# ---------------------------------------------------------------------------
# plan.json
# ---------------------------------------------------------------------------
"""
plan.json — 章节规划与 Scene Beat

顶层字段：
  active_scene_id: str | null   — 当前选中场景 id
  chapters: dict[str, ChapterPlan]

ChapterPlan:
  title: str                    — 卷/章标题（plan 层）
  scenes: list[Scene]

Scene:
  id: str                       — 如 ch1_opening01
  title: str
  beat: str                     — Scene Beat 提纲
  summary: str                  — 可选
  done: bool
  pace: str                     — 快 | 中 | 慢
  emotion_anchor: { target, how }
  updated_at: str               — ISO 8601

读写：novel_data.py（load_plan / save_plan / mutate_plan）
"""

# ---------------------------------------------------------------------------
# project.json
# ---------------------------------------------------------------------------
"""
project.json — 书籍元数据

  title: str
  world_label: str
  tagline: str
  notes: str
  type: "novel" | "world" | "short"
  platform: "tomato" | "qimao" | "jjwxc"
  created_at: str
  updated_at: str

读写：novel_data.py / book_context.py
"""

# ---------------------------------------------------------------------------
# chapters/chNNN.md
# ---------------------------------------------------------------------------
"""
章节正文 — 纯 Markdown

  第一行可选：# 第N章 标题
  正文：叙事 prose（无 JSON schema）

  写入前经 core/chapters.py sanitize：
  - 剥离 AI 元话语、HTML 实体
  - 解析/应用 【章节标题】
  - format_chapter_file 统一文件头

读写：main.read_chapter_content / write_text
"""

# ---------------------------------------------------------------------------
# job.json（批量任务检查点）
# ---------------------------------------------------------------------------
"""
batch_jobs/{job_id}/job.json — pipeline/checkpoint.py

  id: str
  kind: "world_generate" | "world_remediate"
  status: "running" | "paused" | "done" | "failed"
  label: str
  chapter_from: int
  chapter_to: int
  targets: list[int]          — 待处理章号
  completed: list[int]
  generated: list[int]
  skipped: list[int]
  errors: list
  warnings: list
  total_cost_usd: float
  created_at: str
  updated_at: str
  accepted: bool
  ...extra 字段按 kind 扩展

读写：pipeline/checkpoint.py
"""

# ---------------------------------------------------------------------------
# quality_log.jsonl
# ---------------------------------------------------------------------------
"""
quality_log.jsonl — 每行一条 JSON 审阅记录

常见字段：
  id: str
  ts: str
  kind: str                   — summary | continuity | observe | ...
  chapter_num: int
  reply: str                  — LLM 原文或摘要
  summary: str                — 短摘要
  persisted: bool
  persisted_detail: str
  extra: dict                 — 如 scope

读写：quality_log.py
"""

# ---------------------------------------------------------------------------
# 档案 Markdown 文件（无 schema，约定段落结构）
# ---------------------------------------------------------------------------
"""
world.md, style.md, characters.md     — 设定
char_static.md, char_dynamic.md       — 人物冷热分层
summaries_recent.md, summaries_archive.md — 概述（近期 / 归档）
plot_threads_locked.md                — 细节钉子
plot_threads_active.md                — ## 未回收 / ## 已回收
book_archive.md                       — 合订本（### 小节对应上述文件）

详见 docs/novel-writer-manual.md 与 docs/tech-intake.md §二
"""
