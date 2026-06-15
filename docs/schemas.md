# LLM JSON Fence 索引

> 机器可读的类型定义见 `core/schemas/llm.py`；磁盘格式见 [persist-formats.md](./persist-formats.md)；**产品数据 Schema** 见 [data-schema.md](./data-schema.md)。

本文档列出项目中所有 **LLM 回复里用 fence 标记包裹的 JSON 块**，便于新功能对齐格式、避免重复造 parser。

---

## 总表

| Fence 标记 | Prompt 来源 | 解析函数 | 规范化函数 | 业务功能 | 是否写盘 |
|------------|-------------|----------|------------|----------|----------|
| `post-chapter-json` | `prompts/post_chapter_maintain.yaml` / `summarizer.POST_CHAPTER_MAINTAIN_SYSTEM` | `parse_post_chapter_maintain` | `normalize_maintain_payload` | 章后维护 bundle（概述+观察+钉子+伏笔） | 是 |
| `observe-json` | `prompts/observe.yaml` | `parse_observe_proposals` | — | 角色观察（单项） | 可选自动写入 char_* |
| `quality-bundle-json` | `prompts/quality_check_bundle.yaml` | `parse_quality_bundle` | `normalize_quality_payload` | 定稿质检 bundle（连续性+人物+套话） | 否（仅 quality_log） |
| `remediate-diagnose-json` | `prompts/world_remediate_diagnose.yaml` | `parse_remediate_diagnose` | 内联 action/issues 校验 | 世界改稿 · 单章诊断 | 否 |
| `remediate-change-json` | `prompts/world_remediate_change_log.yaml` | `parse_remediate_change_log` | 内联 changes/skipped 校验 | 世界改稿 · 单章变更记录 | 否 |
| `remediate-bulk-change-json` | `prompts/world_remediate_bulk_change_log.yaml` | `parse_remediate_bulk_change_log` | chapters 列表过滤 | 世界改稿 · 批量变更记录 | 否 |
| `bulk-summaries-json` | `prompts/bulk_archive_summaries.yaml` | `parse_bulk_summaries` | summaries 列表过滤 | 批量档案 · 多章概述 | 是 |
| `bulk-state-json` | `prompts/bulk_archive_state.yaml` | `parse_bulk_state` | — | 批量档案 · char_dynamic + plot_active 整份更新 | 是 |

**解析函数位置（canonical）**：`core/schemas/llm.py`（自 summarizer 迁移副本）。  
**兼容副本**：`summarizer.py` 仍保留同名函数，尚未改 import 路径。

---

## 各 Fence 字段摘要

### post-chapter-json → `MaintainPayload`

```json
{
  "summary": "【第N章：标题】\\n核心事件：…",
  "observe": {
    "summary": "2-5句说明",
    "items": [
      {
        "id": "char_dynamic",
        "has_change": true,
        "target_file": "char_static | char_dynamic",
        "proposed_text": "Markdown 块"
      }
    ]
  },
  "detail_locked": "## 第N章…\\n- 【类别】…",
  "plot_new_threads": "- 【伏笔名】…",
  "plot_advanced": "",
  "plot_resolved": ""
}
```

- `plot_advanced` / `plot_resolved`：定稿时供作者参考，默认不写盘
- 写盘逻辑：`core/maintain.persist()`

### observe-json

```json
{
  "items": [ /* 同 MaintainPayload.observe.items */ ]
}
```

- 回复正文 fence 前可有 Markdown 摘要
- 写盘：`BookStore.apply_observe`（`core/orchestration` + `app/hooks`）

### quality-bundle-json → `QualityPayload`

```json
{
  "continuity": "Markdown 报告",
  "character_drift": "Markdown 报告",
  "repetition": "Markdown 报告"
}
```

- 用于 `api_run_post_chapter_finalize` 第二步

### remediate-diagnose-json

```json
{
  "num": 1,
  "action": "patch | full_rewrite | skip",
  "issues": [{ "severity": "must_fix|should_fix", "summary": "", "location": "" }],
  "skip_reason": ""
}
```

### remediate-change-json / remediate-bulk-change-json

单章：`changes[]`, `skipped[]`  
批量：`chapters[]` 每项含 num、action、changes、skipped

### bulk-summaries-json

```json
{ "summaries": [{ "num": 1, "text": "【第1章：…】" }] }
```

### bulk-state-json

```json
{
  "char_dynamic": "整份 Markdown",
  "plot_threads_active": "整份 Markdown",
  "detail_locked_append": "",
  "plot_new_threads": ""
}
```

---

## 非 JSON Fence（分隔符，非 schema）

| 标记 | 位置 | 用途 |
|------|------|------|
| ` ```json `（通用回退） | 多数 parser | 所有 parse_* 在专用 fence 失败时会尝试 |

> 旧 Web「规划工坊」(`---DRAFT---` / `---EXTRACT---` 等) 已移除（2026-06-09）；开书规划走 `prefill/*` API。

---

## 其他结构化解析（非 LLM fence）

| 函数 | 文件 | 输入 | 用途 |
|------|------|------|------|
| `parse_outline_suggestions` | `novel_data.py` | Markdown | 续章灵感（finalize 内部；无独立 HTTP） |
| `parse_chapter_spans` | `core/plan_chapters.py` | 场景 summary/beat | Plan 章号区间 |

---

## 架构迁移（schemas 层）

| 项 | 状态 |
|----|------|
| `core/schemas/` 类型 + parse 副本 | ✅ |
| `maintain.call_bundle` / `persist` 两阶段 | ✅ |
| `BookStore.load_snapshot` / `persist_summary` / `apply_observe` | ✅ |
| summarizer → schemas 单源；Deps Callable 清理 | 待做（非产品排期） |

---

## 新功能检查清单

加 LLM 结构化输出前：

1. 在 `core/schemas/llm.py` 增加 TypedDict + `parse_*` + `normalize_*`
2. 在 `prompts/*.yaml` 写明 fence 名与示例 JSON
3. 更新本文档表格一行
4. 服务输入用 `ChapterWork` / `BookSnapshot`，输出用 `ServiceResult` / `PersistOutcome`
5. **不要**往 `core/deps.py` 加新 Callable——先讨论是否应走 `BookStore`
