# 技术信息收集清单（已填答）

> 供 AI / 新协作者快速了解本项目。基于当前代码整理。  
> **产品流程与 UI** → **[workflow.md](./workflow.md)** · **做了/没做** → **[canonical-status.md](./canonical-status.md)**  
> **数据文件机制** → **[novel-writer-manual.md](./novel-writer-manual.md)**（仅数据层，无旧 UI 导航）
>
> **维护**：功能或上下文策略变更时，请同步更新 [canonical-status.md](./canonical-status.md) §七、[workflow.md](./workflow.md) §五，以及本文「三、上下文组装」「四、API 能力（Substrate）」。

---

## 一、技术栈基本信息

| # | 问题 | 答案 |
|---|------|------|
| 1 | 前端用什么框架？版本号？ | **React 19 + Vite + TypeScript**（`frontend/package.json`）。开发 `npm run dev`（5173），`/api` 代理到 8765。**旧 `web/` 静态页已删除** |
| 2 | 后端用什么语言/框架？版本号？ | **Python 3** + **FastAPI**（`requirements.txt`: `fastapi>=0.110.0`, `uvicorn>=0.27.0`） |
| 3 | 数据库用什么？ | **无**。纯 **文件系统**（`library/books/{id}/` 下 `.md` + `.json`；旧 `data/` 可迁移） |
| 4 | 部署在哪里？ | **本地单机**：`python web_app.py`，默认 `http://127.0.0.1:8765`；可选 `NOVEL_WEB_TOKEN` 鉴权；非本地访问默认 403 |
| 5 | 调用的 AI 接口？ | **kie.ai**（Anthropic 兼容，Claude Sonnet/Opus）+ **DeepSeek**（OpenAI 兼容 API） |
| 6 | AI 调用是流式还是普通请求？ | **写书对话**：SSE 流式（`/api/chat/stream`）；概述 / 检查 / 定稿 / Gate 步骤：**普通请求** |

---

## 二、数据结构

### 7. 项目目录结构（核心）

```
novel_writer/
├── main.py              # 路径锚点 + CLI 入口（业务在 app/）
├── web_app.py           # FastAPI + REST/SSE（零 import main）
├── app/                 # bootstrap、llm、writing_*、cli、runtime、paths …
├── api/routes/          # HTTP 路由（零 import main）
├── config.py            # 提供商、上下文策略、.env
├── providers.py         # 统一 LLM 调用
├── novel_data.py        # plan.json、Codex
├── summarizer.py        # system prompt 模板
├── app_state.py         # 进程内单例状态
├── file_utils.py        # 原子写、备份
├── frontend/            # React 新 UI（Canonical 产品界面）
├── library/             # 书库 + taste + profiles
├── data/                # 旧版单书目录（可迁移到 library/books/default/）
│   ├── world.md, style.md, characters.md
│   ├── char_static.md, char_dynamic.md（人物冷热分层）
│   ├── summaries_archive.md, summaries_recent.md, summaries.md（兼容）
│   ├── plot_threads_locked.md, plot_threads_active.md, plot_threads.md（兼容）
│   ├── char_current.md（已拆分占位，续写不读）
│   ├── plan.json, project.json, chat_prompts.json, runtime.json, outline_latest.md
│   ├── chapters/ch001.md …
│   ├── codex/entries/*.md, codex/active.json
│   ├── backups/
│   ├── history/                 # 档案变更留痕（baseline + change_history.jsonl）
│   └── session_autosave.json（运行时）
├── cost_log.jsonl
└── tests/
```

### 8. 一本书的数据怎么存？

- **书库**：`library/index.json` + `library/books/{book_id}/`（`book_context.py`）
- **`project.json`**：`title`, `type`（`novel`|`world`|`short`）, `platform`（`tomato`|`qimao`|`jjwxc`）, `world_label`
- **全局**：`library/runtime.json`（提供商/上下文）；根目录 `cost_log.jsonl`（带 `book_id`）
- 旧 `data/` 首次启动迁移 → `library/books/default/`
- 切换书：`POST /api/library/switch`；进程内写书会话随书重置

### 9. 章节数据结构

- **正文**：`data/chapters/ch{NNN}.md`，纯 Markdown，无 JSON schema
- **规划元数据**：`data/plan.json` → `chapters["N"]`：

```json
{
  "title": "世界一·xxx",
  "scenes": [ ... ]
}
```

正文文件本身无结构化字段；AI 续写可能带 `【章节标题】` 行，写入章节前会剥离。

### 10. 场景 / Beat 数据结构

`plan.json` 中每个 scene：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 如 `ch1_opening01` |
| `title` | string | 场景名 |
| `beat` | string | Scene Beat 提纲 |
| `summary` | string | 场景概述（可选） |
| `done` | bool | 规划完成标记 |
| `pace` | string | 节奏档位：`快` / `中` / `慢` |
| `emotion_anchor` | object | `{ target, how }` 情绪锚点，注入续写 |
| `updated_at` | string | ISO 时间 |

顶层还有 `active_scene_id` 表示当前选中场景。

### 11. 全局文件存在哪里？怎么读取？

**冷热分层（续写 Prompt Cache 用）**

| 层 | 文件 | 维护频率 |
|----|------|----------|
| ② 缓存 | `char_static.md` | 极少改（性格锚点、禁止写法、深层软肋） |
| ④ 动态 | `char_dynamic.md` | 每章改（当前状态、表层软肋、关系） |
| ③ 缓存 | `summaries_archive.md` | 只增不改（旧章概述归档） |
| ④ 动态 | `summaries_recent.md` | 每章追加（最近 3–5 章；`/summary` 写入） |
| ③ 缓存 | `plot_threads_locked.md` | 只增不改（已钉死细节；提取细节可追加） |
| ④ 动态 | `plot_threads_active.md` | 每章改（未回收 / 已回收伏笔） |

**其他全局文件**

| 文件 | 路径 |
|------|------|
| 世界观 | `data/world.md` |
| 文风锚点 | `data/style.md` |
| 人物总表 | `data/characters.md` |
| 兼容占位 | `char_current.md`、`plot_threads.md`、`summaries.md`（续写不直接读；见拆分文件） |

- 读取：`app.book_io.read_text()`、`app.paths.resolved_codex_files()`；组装见 `app.writing_ctx`（`get_characters_block` / `get_stable_archive_block` / `get_dynamic_context_block`）
- 档案读写：`app.codex.get_codex` / `save_codex`（CLI）；**无** `/api/codex*` HTTP（2026-06-10 已删）
- 首次运行：`app.bootstrap.init_data_dirs()` + `app.bootstrap_data.INITIAL_FILE_TEMPLATES`
- **章后维护习惯**：改 `char_dynamic` + `plot_threads_active` → 生成概述 → 旧概述剪切进 `summaries_archive`

### 12. 对话历史存在哪里？格式是什么？

| 类型 | 路径 | 格式 |
|------|------|------|
| 写书对话 | `data/session_autosave.json` | JSON：`conversation_history`（`{role, content}` 数组）+ `appended_indices`、章号等 |
| 写书可读备份 | `data/session_autosave.md` | Markdown 摘要 |
| 指令模板 | `data/chat_prompts.json` | `{ "prompts": [{id, title, content}] }` |

---

## 三、上下文组装逻辑

### 13. 每次发送给 AI 之前，上下文怎么组装？

核心调用链：

```
_prepare_writing_turn()
  → build_cached_system(WRITING_INSTRUCTION)
  → prepare_messages_for_context(conversation_history)
  → providers.APIClient.create_message() / iter_message()
```

### 14. 现在注入了哪些内容？

**System（kie/Claude 为 3–4 块，前 2–3 块 Prompt Cache）**

| 块 | 内容 | 来源函数 |
|----|------|----------|
| ① | world + style | `get_world_block()` |
| ② | 人物 + 锚点 | `get_characters_block()`（Codex 或 characters.md + **char_static.md**） |
| ③ | 归档 + 钉子 | `get_stable_archive_block()`（**summaries_archive** + **plot_threads_locked**） |
| ④ | 写作指令 + 动态 | `WRITING_INSTRUCTION` + `get_dynamic_context_block()` |

**User messages**

- 首轮：`【当前章节：第N章】` + 章节正文 + `【写作指令】`（含 Scene Beat）
- 后续轮：仅指令（换章前不重复注入正文）
- 历史：`trim_history()` 按 `CHAT_CONTEXT_TURNS` 截断

**④ 层动态（不缓存，每章变动）**

- `char_dynamic.md`（当前状态、表层软肋）
- `summaries_recent.md`（近期 3–5 章概述）
- `plot_threads_active.md`（未回收 / 已回收伏笔）
- 当前场景 Beat（`beats` / `summaries` 模式）

### 15. 注入顺序

1. System ① world+style → ② 人物+char_static → ③ archive+locked → ④ instruction+动态  
2. User：按时间序的对话历史（可能截断最近 N 轮）

### 16. 有没有 token 限制或截断？

| 机制 | 说明 |
|------|------|
| 输出上限 | `MAX_TOKENS` 默认 8192（`NOVEL_MAX_TOKENS`） |
| 对话截断 | 写书 `CHAT_CONTEXT_TURNS`（默认 10）；Web ⚙️ 可改并持久化到 `runtime.json`；**0 = 不截断**；**非**按 token 切 system |
| 监控 | `_estimate_tokens()` 粗估；`data/context_log.jsonl` 记录体积 |
| Web 限制 | 指令等 `MAX_API_TEXT_CHARS = 50_000`；章节 `MAX_CONTENT_BYTES = 2MB |
| 无 | 对 world / summaries 按 token 自动截断 |

**CONTEXT_MODE 对历史轮数的影响**

| 模式 | 人物来源 | 历史轮数 |
|------|----------|----------|
| `beats`（默认） | Codex 优先 + char_static | `CHAT_CONTEXT_TURNS`（⚙️ 可配，0=不截断） |
| `summaries` | 同上 | 同上 |
| `codex` | 强制 Codex | 同上 |
| `turns` | characters.md + char_static | 同上 |

### 17. system prompt 写什么？

| 用途 | 常量 | 文件 |
|------|------|------|
| 写书续写 | `WRITING_INSTRUCTION` | `summarizer.py` |
| 生成概述 | `SUMMARY_SYSTEM` | `summarizer.py` |
| 连续性检查 | `CHECK_SYSTEM` | `summarizer.py` |
| 续章灵感 | `OUTLINE_SYSTEM` | `summarizer.py` |

`WRITING_INSTRUCTION` 要点：遵守 `style.md` 文风；`char_static` 性格锚点 + `char_dynamic` 当前状态；`plot_threads_locked` 细节钉子；`world.md` 节拍与爽点；Beat 节奏档位与情绪锚点；续写输出格式（`【章节标题】` + 纯正文，或 `[讨论]` 前缀）。

其他 system 模板（均在 `summarizer.py`）：`CHARACTER_DRIFT_SYSTEM`、`DETAIL_EXTRACT_SYSTEM`、`REPETITION_CHECK_SYSTEM`、`PACING_CHECK_SYSTEM`。

### 18. Prompt Cache 怎么实现？

- **仅 kie/Claude**（`config.supports_prompt_cache()`）
- `core.llm.build_cached_system()` → Anthropic `cache_control: {type: ephemeral, ttl: 1h}`
- DeepSeek：system 合并为纯文本，无 cache
- 可选心跳：50 分钟无 API 且仍在写作时刷新 cache（`HEARTBEAT_*`）

**冷热分层与命中率**（2025 优化）

| 块 | 内容 | 典型刷新频率 |
|----|------|--------------|
| ① | world + style | 几乎不刷 |
| ② | characters + **char_static** | 人物本质不变则不刷 |
| ③ | **summaries_archive** + **plot_threads_locked** | 只追加归档/钉子时不刷前缀 |
| ④ | instruction + **char_dynamic** + **summaries_recent** + **plot_threads_active** + Beat | 每章必变 |

**调试：缓存命中验证（API 仍有；新 UI 在设置 → Prompt Cache）**

- 接口数据：`state.last_call_info`（含 `cost_no_cache`、`cache_savings_pct` 等）
- 设置页：`GET /api/tools/prompt-cache/status`、手动 refresh
- 仅 kie 写作 SSE 有 Prompt Cache 统计；DeepSeek 无

**调试：上下文内容验证（API）**

- `GET /api/debug/last_context`：上次请求各层文本 + messages 摘要
- 来源：`build_cached_system()` → `state.last_context_debug`
- ④ 层可展开子项：`WRITING_INSTRUCTION`、Beat、char_dynamic、summaries_recent、plot_threads_active

---

## 四、API 能力（Substrate）

> **Canonical 前端已接哪些** → [canonical-status.md §一–§二](./canonical-status.md)。  
> 下列为后端仍存在的 API；**有 API 不表示新 UI 已有入口**。

### 19. 写作与续写

| 能力 | API / 入口 |
|------|------------|
| 新 UI 写作 Gate | `frontend/` → `/writing`；SSE `POST /api/chat/stream` |
| 布局 | 左：章节列表；**中：正文 + Gate**（无右侧 `PreviewPanel`） |
| 章节编辑 | 中间栏 `ChapterEditor`（磁盘稿可手动改） |
| L2 预览（库存） | `POST .../reader-preview` · `.../editor-preview`（**无写作页 UI**） |
| 概述确认 | `POST /api/post-chapter/finalize` + summary confirm（Gate） |
| 上下文调试 | `GET /api/debug/last_context`（设置 Prompt Cache；无旧顶栏 🔍） |
| CLI | `python main.py`（`/summary` `/check` `/outline` 等） |

**已移除**：旧 Web 四 Tab（构想/写作/审阅/设定）、写书对话面板、写书记录对照、顶栏 cache pill UI。

### 20. 生成概述

- 触发：写书对话「生成概述」或 `/summary`
- 提供商：`SUMMARY_PROVIDER`（默认 DeepSeek）
- 存储：**追加** `summaries_recent.md`（同时镜像 `summaries.md`）；**不自动**改 `char_dynamic` / `plot_threads_active`
- 维护：近期条满 3–5 章时，手动剪切旧条到 `summaries_archive.md` 以稳定 cache ③

### 21. 连续性检查

- 触发：「连续性检查」或 `/check`
- 对照：world、characters、`char_static`+`char_dynamic`（合并）、summaries（archive+recent）、最新章正文
- 含：性格锚点、细节钉子、时间线、专名、世界观规则

### 22. 伏笔追踪

- 手动维护 **`plot_threads_active.md`**（未回收 / 已回收）；钉子进 **`plot_threads_locked.md`**
- 续写：locked 在 cache ③，active 在 ④；续章灵感引用 active
- 「提取细节」可追加 locked；无自动伏笔状态机

### 23. 自动备份

- 写入前 → `data/backups/{stem}_{timestamp}{suffix}`
- 每文件最多 **10 份**，超出删最旧
- 覆盖：章节、plan、全局 md、Codex

### 24. 章节 / 场景状态

- 场景：`done: bool`
- 章节：无草稿/审阅枚举；正文即 `ch00x.md`
- 写书记录标记「✓已写入」

### 25. 写书对话核心流程

```
用户指令 (+ scene_id / beat)
  → _prepare_writing_turn()
  → build_cached_system() + prepare_messages_for_context()
  → writing_chat_stream() / call_api()
  → _finalize_writing_turn()
      → save_chapter_after_reply()（续写类 append）
      → save_session()
  → SSE chunk + done(费用 + cache 明细)
```

### 26. 章后档案与内部质检

| 入口 | API / 模块 | 说明 |
|------|------------|------|
| **章后维护** | `POST /api/post-chapter/maintain` | **1 次 LLM** → 拆分写入 summaries / char_* / plot_threads_locked |
| 定稿 bundle | `finalize` → `core/reviewer.py` | 人物漂移、重复句式等；**无**独立 `/api/check/*` 按钮向路由 |
| 质量留痕 | `GET/POST /api/quality/log*` | P1 归因、`judgment_fork` 用；非 B2 抽屉 |

### 27. 审阅 / 拆文

| 按钮 | API | 新 UI |
|------|-----|-------|
| 女频审阅 | `POST /api/review/female-fiction` | ✅ Writing Gate |
| 采纳改稿 | `POST /api/review/female-fiction/accept` | ✅ Gate |
| Profile 列表 | `GET /api/review/profiles` | 间接（init criteria） |
| 参考拆文 | `POST /api/deconstruct` | ✅ 向导偏好步 |

> 旧 `/api/batch/world/*` 世界批量链已删除（2026-06-09）；长篇与短篇同 Canonical Gate 流程。

Prompt 目录：`docs/review-prompts/`（如 `world-tomato.md`，`mode: rewrite-only`）。

---

## 五、现有问题与痛点

| # | 说明 |
|---|------|
| 27 | **已知限制**：Web 单进程单会话；`chat_prompts.json` 非空时不自动合并新默认模板；无多书 / 多用户 |
| 28 | 质量风险：文风偏移、人设漂移、细节吃书、重复套话、节奏单一、爽点散乱——通过 style / world / char 分层 / plot_threads / Beat 与 Gate 审阅缓解；定稿内部仍跑 reviewer bundle |
| 29 | 上下文：长章正文首轮全量注入 user message；无硬 token 预算器；cache ②③ 已冷热分层，④ 层每章变动属预期 |
| 30 | **未实现**：多用户 session 隔离、Free 流式、细粒度 token 截断（书库 v0.7 已支持） |

---

## 六、代码细节

### 31. 调用 AI 的核心

- `providers.APIClient.create_message()` / `iter_message()`
- 封装：`core.llm.call_api()`、`app.writing_chat.writing_chat_stream()`
- kie：Anthropic SDK + 自定义 UA/Bearer；DeepSeek：OpenAI SDK

### 32. 上下文组装的核心

- `build_cached_system()`、`get_world_block()`、`get_characters_block()`、`get_stable_archive_block()`、`get_dynamic_context_block()`
- `_prepare_writing_turn()`、`prepare_messages_for_context()`、`trim_history()`
- `get_last_context_debug()`、`calc_cost_no_cache()`、`_build_last_call_info()`、`_record_context_debug()`

### 33. 数据读写的核心

- `app.book_io.read_text()` / `write_text()`（带 backup）
- `file_utils.atomic_write_text()`
- `novel_data.load_plan()` / `_mutate_plan()`
- `read_chapter_content()` → `data/chapters/ch{num:03d}.md`

### 34. 中间件

- `web_app.web_auth_middleware`：本地 IP 或 `X-Novel-Token`
- `core.llm._request_lock`：LLM 请求串行化

### 35. 错误处理

- `providers.APIError`（auth / rate_limit / timeout / network）
- `core.llm._api_error_message()` 中文提示
- SSE `{type: "error"}`；流式断连可 fallback 非流式

---

## 七、扩展性相关

| # | 答案 |
|---|------|
| 35 | 模块：`main`、`web_app`、`novel_data`、`providers`、`config`、`summarizer`、`app_state` |
| 36 | 配置：`.env`、`config.py`、`data/runtime.json`、`prices.json` |
| 37 | 日志：`cost_log.jsonl`、`data/context_log.jsonl`（`NOVEL_CONTEXT_LOG=0` 可关） |
| 38 | FastAPI REST + SSE；业务在 `app/*` + `core/orchestration/`；`main.py` 仅路径锚点与测试契约 |
| 39 | **不支持多用户**；`app_state` 单例（含 `last_call_info`、`last_context_debug`）；多用户需按 session 隔离（未实现） |

---

## 八、补充（重要设计决策）

1. **单书单会话**：一个 `data/` + 一份内存状态，不适合公网多用户。
2. **设定只增不改**：为 Prompt Cache 服务；全局 md 须手动保存 + 确认。
3. **章节写入**：SSE 续写 **append**；新 UI 定稿走 Gate「采纳预览」；CLI/旧 API 仍可用 `apply-turn`。
4. **kie 网关**：须 Bearer + 自定义 User-Agent。
5. **地基文件**：`style.md`、`char_static`/`char_dynamic`、`summaries_archive`/`summaries_recent`、`plot_threads_locked`/`plot_threads_active` 已按冷热分层接入续写上下文。
6. **测试**：`python -m unittest discover -s tests -v`（45 项）。
7. **导演拍板原则**：AI 生成正文 / 检查 / 提案，**全局 md 与 char_dynamic 写入须用户确认**（全局文件保存有确认框）；自动写入仅限章节 append 与用户点选的「提取细节追加」。

---

## 九、角色观察（内部 · HTTP 已删）

定稿 / 章后维护（`finalize`、`maintain`）可调用 `core/reviewer.run_observe`，经 `BookStore.apply_observe` 写 char_*。  
**无** `/api/observe*` 路由与旧 Web 弹窗（2026-06-10 自 B 线移除）。Prompt 仍在 `summarizer.OBSERVE_SYSTEM`。

---

## 十、档案变更留痕（已实现 · 页面待做）

> 解决「系统在悄悄进化，我不知道变成什么样」——每次追踪文件写入前留 `before/after`，可回溯、可撤销。

### 43. 追踪范围

| tier | 文件 | 说明 |
|------|------|------|
| dynamic | char_dynamic, summaries_*, plot_threads_* | 每章可能变 |
| stable | world, style, char_static, characters | 不应常变；若变了会记一条 |
| plan | plan.json | 规划变更 |

章节正文 `chapters/` **不在此追踪**（沿用 `data/backups/`）。

### 44. 存储

```
data/history/
├── baseline/              # 第 0 章基准快照（首次启动或 POST baseline 刷新）
│   ├── manifest.json
│   └── {file_key}.md …
└── change_history.jsonl   # 每条：id, ts, chapter_num, file_key, source, before, after, op
```

### 45. 写入路径

- 所有 `app.book_io.write_text()` 对追踪文件 → `change_history.save_with_history()`
- `novel_data._save_json(plan.json)` 同理
- `source` 标记：`codex` | `summary` | `observe` | `detail_extract` | `plan` | `revert` | `write`

### 46. API（前端档案室页面可对接）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/history` | 按文件汇总 + 最近条目（`?file_key=char_dynamic`） |
| GET | `/api/history/baseline` | 基准 manifest |
| POST | `/api/history/baseline` | 强制刷新基准（慎用） |
| GET | `/api/history/{entry_id}` | 完整 before/after |
| POST | `/api/history/revert` | body `{ entry_id }` 一键撤销 |

### 47. 代码

`change_history.py` · `app.cost._register_change_history()` · `init_data_dirs()` 内 `ensure_baseline_snapshot()`

---

## 十一、写作章与会话

> 旧 `GET /api/guide/status` 已删除；新流程用向导 + Gate。

### 写作目标章

| 概念 | 来源 | 用途 |
|------|------|------|
| `write_chapter_num` | 会话 / `/api/status` | AI 写入与质量检查默认章 |
| Gate 当前章 | 前端 `FlowCanvas` | 编辑与审阅上下文 |

章节正文注入在以下情况会失效并下轮重新从磁盘注入：手动/AI 保存、apply-turn、undo、历史 trim 裁掉首轮、API 失败回滚。API 仍支持 `PUT /api/chat/write-chapter`（新 UI 以 Gate 章为准）。

---

## 关键代码索引

| 主题 | 文件 | 符号 |
|------|------|------|
| 上下文组装 | `core/llm.py`, `app/writing_ctx.py` | `build_cached_system`, `_prepare_writing_turn` |
| 调试 | `core/context.py` / `api/routes/meta.py` | `get_last_context_debug`, `GET /api/debug/last_context` |
| Plan / Codex | `core/data/novel_data.py` | `add_scene`, `get_scene_context_text` |
| LLM 调用 | `infra/providers.py` | `APIClient.create_message`, `iter_message` |
| Prompt 模板 | `summarizer.py` | `WRITING_INSTRUCTION`, `CHECK_SYSTEM`, `CHARACTER_DRIFT_SYSTEM` |
| Web API | `web_app.py` | `/api/chat/stream`, `/api/prompts/*` |
| 内部质检 | `core/reviewer.py` | `run_character_drift`, `run_repetition_check`（定稿/maintain 调用） |
| 质量记录 | `infra/logs/quality.py` | `GET /api/quality/log`, `POST .../judgment`（P1） |
| 档案留痕 | `change_history.py` | `GET /api/history`, `POST /api/history/revert` |
| 配置 | `infra/config.py` | `CONTEXT_MODE`, `PROVIDERS`, `CHAT_CONTEXT_TURNS` |

---

## 一张总表（写作质量 ↔ 数据文件）

| 问题 | 解决工具 | 维护文件 | 平台行为 |
|------|---------|---------|---------|
| 人物漂移 | 性格锚点 + 定稿 reviewer | `char_static` + `char_dynamic` | maintain / finalize 内部 |
| 细节矛盾 | 细节钉子 + maintain | `plot_threads_locked` + `plot_threads_active` | 章后维护 LLM 拆分 |
| 重复句式 | 禁用词 + reviewer | `style.md` | 定稿 bundle |
| 节奏单一 | Beat + pace 档位 | 规划场景 | 下拉保存；`get_scene_context_text()` 注入 |
| 情感太直 | 情感具象化规则 | `WRITING_INSTRUCTION` | 续写全局生效 |
| 爽点散乱 | Beat + L5b 节奏 | `world.md` / plan | Gate `rhythm-check` |

详见 [novel-writer-manual.md §三](./novel-writer-manual.md#三质量与档案内部能力)。
