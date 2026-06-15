# core/deps.py Callable 审计清单

> P2 步骤：逐个确认后再替换。**LlmHooks 已迁至 `core.llm`（P3-5a）**。

原则：Callable 应逐步消失，改为 **BookStore 方法** 或 **BookSnapshot 字段**。

---

## LlmHooks（3 个 Callable）✅ 已迁

| 字段 | 注入来源 | 功能 | 现状 |
|------|-----------|------|------|
| `build_cached_system` | `core.llm.build_cached_system` | 组装 Prompt Cache system 块 | `app/factories._llm_hooks()` |
| `call_api` | `core.llm.call_api` | 统一 LLM 调用 | 同上 |
| `get_last_call_info` | `core.llm.get_last_call_info` | 费用/错误元数据 | 同上 |

`main.call_api` 等经 PEP 562 `__getattr__` 转发（`app/main_forwards.py`），仅供测试 patch 兼容。

---

## ChapterHooks（GeneratorDeps，5 个 Callable）

| 字段 | 注入来源 | 功能 | 新架构归属 |
|------|-----------|------|------------|
| `read_content` | `read_chapter_content` | 读章节正文 | `BookStore.read_chapter(num)` |
| `get_path` | `get_chapter_path` | 章节文件 Path | `BookStore.chapter_path(num)` |
| `write_file` | `write_text` | 原子写 + history | `BookStore.write(path, ...)` |
| `invalidate_injection` | `_invalidate_chapter_injection` | 清会话注入标记 | 编排层 / app_state（非 core） |
| `apply_title` | `apply_chapter_title` | 解析并写标题 | `core.chapters` + BookStore |

---

## ArchiveHooks（ReviewerDeps / MaintainDeps）

| 字段 | 类型 | 新架构归属 |
|------|------|------------|
| `read_text` | Callable | `BookStore._read` 内部 |
| `*_file` Path 字段 | Path | `BookContext` 属性，BookStore 持有 ctx |

→ 整体由 **BookStore** 替代 `ArchiveHooks + read_text`。

---

## QualityHooks（3 个 Callable，均可选）

| 字段 | 注入来源 | 功能 | 新架构归属 |
|------|-----------|------|------------|
| `log_entry` | `_quality_log_entry` | 写 quality_log.jsonl | `BookStore.log_quality(...)` 或独立 QualityLog |
| `persist_summary` | `_persist_summary_text` | 概述 upsert + rotate | `BookStore.persist_summary(num, text)` |
| `short_story_skip` | `_short_story_archive_skip` | 短篇模式跳过 | 编排层检查 `project.json type` |

---

## ReviewerDeps 业务 Callable（10 个）

| 字段 | 注入来源 | 功能 | 新架构归属 |
|------|-----------|------|------------|
| `get_char_context_for_check` | `get_char_context_for_check` | 检查用人设块 | `BookSnapshot.char_context_for_check` |
| `get_summaries_combined` | `get_summaries_combined` | 合并概述 | `BookSnapshot.summaries_combined` |
| `summaries_for_scope` | `_summaries_for_scope` | 按 scope 取概述 | `BookStore.summaries_for_scope(num, scope)` |
| `scope_label` | `_scope_label` | scope 中文标签 | 纯函数留 `core/schemas` 或 reviewer 模块内 |
| `resolve_chapter` | `_resolve_chapter_num` | 解析章号+正文 | 编排层 → 构造 `ChapterWork` 传入服务 |
| `read_char_static` | `_read_char_static` | 读静态人设 | `BookSnapshot.char_static` |
| `get_chapters_text_for_scope` | `app.chapter_io` | 多章正文拼接 | `BookStore.chapters_text_for_scope(num, scope)` |
| `count_summaries` | `count_summaries` | 概述条数 | `BookStore.count_summaries()` |
| `latest_chapter_num` | `lambda: get_latest_chapter()[0]` | 最新章号 | `BookStore.latest_chapter_num()` |
| `write_append_locked` | lambda → `write_text(...)` | 追加钉子 | `BookStore.append_locked(num, text)` |
| `apply_observe` | `api_apply_observe` | 写入观察提案 | `BookStore.apply_observe(items, chapter_num)` |
| `observe_items_for_auto_apply` | `_observe_items_for_auto_apply` | 过滤可写提案 | 纯函数 → `core/schemas` 或 maintain |
| `observe_fallback_apply` | `_observe_fallback_apply` | 摘要回退写 dynamic | `BookStore.observe_fallback(num, text)` |

**ReviewerDeps 目标形态**：仅 `llm: LlmClient` + 输入 `ChapterWork` + `BookSnapshot`，无 Callable。

---

## MaintainDeps 业务 Callable（9 个）

| 字段 | 注入来源 | 功能 | 新架构归属 |
|------|-----------|------|------------|
| `resolve_chapter` | `_resolve_chapter_num` | 同 Reviewer | 编排层 → `ChapterWork` |
| `read_char_static` | `_read_char_static` | 同 Reviewer | `BookSnapshot.char_static` |
| `extract_plot_unresolved` | `extract_plot_active_unresolved` | 提取未回收伏笔段 | `BookSnapshot.plot_unresolved` |
| `persist_summary` | `_persist_summary_text` | 同 QualityHooks | `BookStore.persist_summary` |
| `apply_observe` | `api_apply_observe` | 同 Reviewer | `BookStore.apply_observe` |
| `observe_items_for_auto_apply` | `_observe_items_for_auto_apply` | 同 Reviewer | 纯函数 |
| `observe_fallback_apply` | `_observe_fallback_apply` | 同 Reviewer | `BookStore.observe_fallback` |
| `append_plot_new_threads` | `_append_plot_new_threads` | 追加新伏笔到 active | `BookStore.append_plot_new(num, text)` |
| `parse_markdown_list_items` | `_parse_markdown_list_items` | 统计列表条数 | 纯函数 → `core/chapters` 或 schemas |
| `write_text` | `write_text` | 通用写盘 | `BookStore.write` |

**MaintainDeps 目标形态**：`persist(payload, store: BookStore, options)` — store 替代全部 Callable。

---

## 已迁移到 BookStore（✅）

| Callable | 状态 |
|----------|------|
| `persist_summary` | ✅ `MaintainDeps.store` + `store.persist_summary` |
| `apply_observe` | ✅ `store.apply_observe` |
| `observe_fallback_apply` | ✅ `store.observe_fallback_apply` |
| `write_text`（detail_locked） | ✅ `store.append_plot_locked` |
| `append_plot_new_threads` | ✅ `store.append_plot_new_threads` |
| `parse_markdown_list_items` | ✅ `core.book_store.parse_markdown_list_items` |
| `observe_items_for_auto_apply` | ✅ `core.maintain.observe_items_for_auto_apply` |
| `write_append_locked`（Reviewer） | ✅ `store.append_plot_locked` |

`MaintainDeps` 现以 **`store: BookStore`** 为主；上表 Callable 字段已改为可选，`_maintain_deps()` 不再注入。

## 建议替换顺序

1. `resolve_chapter` → 编排层构造 `ChapterWork`（影响面最广，放后）
2. `read_*` / `get_summaries_*` / `extract_plot_unresolved` → `BookStore.load_snapshot`
3. 删除 `MaintainDeps` 中已可选的 Callable 字段定义
4. `ReviewerDeps` 其余 Callable → `BookSnapshot` + `BookStore`
5. `LlmHooks` 收敛到 `core.llm`（可选，低优先级）

---

## 不应新增的 Callable

加新功能前检查：若需要往 Deps 加 Callable，应改为：

- 读数据 → 扩展 `BookSnapshot` 或 `load_snapshot(for_purpose=...)`
- 写数据 → 扩展 `BookStore` 方法或 `PersistOutcome` 字段
- 纯逻辑 → `core/schemas` 或对应 service 模块内函数

---

## P3 重构后 `import main` 分布（2026-06）

| 层 | `import main` | 说明 |
|----|---------------|------|
| `core/` | **0** | 红线 |
| `app/*`（业务） | **0** | 仅 `paths.py` ×4 测试 mirror |
| `api/*` | **0** | 路由直引 `app.*` |
| `web_app.py` | **0** | |
| `main.py` | 148 行 | 路径锚点 + re-export + `__getattr__` |
| `tests/` | 若干 | 测试契约（patch `main.*` 路径） |
| `scripts/` | **0** | `app.bootstrap` + `app.paths` |

