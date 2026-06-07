# 技术信息收集清单（已填答）

> 供 AI / 新协作者快速了解本项目。基于当前代码整理。  
> **用户操作、数据文件机制、写作必填**见 **[novel-writer-manual.md](./novel-writer-manual.md)**（§二 系统设定、§三 写作流程、§六 注意事项）。
>
> **维护**：功能或上下文策略变更时，请同步更新本文「三、上下文组装」「四、已有功能」与「九、规划功能」章节。

---

## 一、技术栈基本信息

| # | 问题 | 答案 |
|---|------|------|
| 1 | 前端用什么框架？版本号？ | **无 React/Vue**。原生 **HTML + CSS + 原生 JavaScript**（`web/index.html`、`web/app.js`、`web/style.css`），无 package.json 锁版本 |
| 2 | 后端用什么语言/框架？版本号？ | **Python 3** + **FastAPI**（`requirements.txt`: `fastapi>=0.110.0`, `uvicorn>=0.27.0`） |
| 3 | 数据库用什么？ | **无**。纯 **文件系统**（`data/` 下 `.md` + `.json`） |
| 4 | 部署在哪里？ | **本地单机**：`python web_app.py`，默认 `http://127.0.0.1:8765`；可选 `NOVEL_WEB_TOKEN` 鉴权；非本地访问默认 403 |
| 5 | 调用的 AI 接口？ | **kie.ai**（Anthropic 兼容，Claude Sonnet/Opus）+ **DeepSeek**（OpenAI 兼容 API） |
| 6 | AI 调用是流式还是普通请求？ | **写书对话**：SSE 流式（`/api/chat/stream`）；概述 / 检查 / 续章灵感 / 自由聊：**普通请求** |

---

## 二、数据结构

### 7. 项目目录结构（核心）

```
novel_writer/
├── main.py              # 核心业务（CLI + 被 web 引用）
├── web_app.py           # FastAPI + REST/SSE
├── config.py            # 提供商、上下文策略、.env
├── providers.py         # 统一 LLM 调用
├── novel_data.py        # plan.json、Codex
├── summarizer.py        # system prompt 模板
├── app_state.py         # 进程内单例状态
├── file_utils.py        # 原子写、备份
├── web/                 # 静态前端
├── data/                # 一本书的全部数据
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

- **单书模式**：一个 `data/` = 一本书（`data/project.json` 存书名 / 世界标签）
- 多书：复制整个 `novel_writer` 文件夹，或 Git 分支隔离各自的 `data/`（Web 内无多书下拉）

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

- 读取：`main.read_text()`、`main.CODEX_FILES` 映射；组装见 `get_characters_block()` / `get_stable_archive_block()` / `get_dynamic_context_block()`
- Web：`GET/PUT /api/codex/{name}`（`name` 含 `char_static`、`char_dynamic`、`summaries_archive`、`summaries_recent`、`plot_threads_locked`、`plot_threads_active` 及兼容项）
- 首次运行：`main.init_data_dirs()` + `INITIAL_FILES` 模板
- **章后维护习惯**：改 `char_dynamic` + `plot_threads_active` → 生成概述 → 旧概述剪切进 `summaries_archive`

### 12. 对话历史存在哪里？格式是什么？

| 类型 | 路径 | 格式 |
|------|------|------|
| 写书对话 | `data/session_autosave.json` | JSON：`conversation_history`（`{role, content}` 数组）+ `appended_indices`、章号等 |
| 写书可读备份 | `data/session_autosave.md` | Markdown 摘要 |
| 自由聊 | `data/free_chat.json` | JSON（gitignore）；**多话题** `threads[]`，`active_thread_id`；旧版单条 `messages` 启动时自动迁移 |
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
| 输出上限 | `MAX_TOKENS` 默认 8192（`NOVEL_MAX_TOKENS`）；自由聊 `FREE_CHAT_MAX_TOKENS` 默认 16384（`NOVEL_FREE_CHAT_MAX_TOKENS`） |
| 对话截断 | 写书 `CHAT_CONTEXT_TURNS`（默认 10）；自由聊 `FREE_CHAT_CONTEXT_TURNS`（默认 20）；Web ⚙️ 可改并持久化到 `runtime.json`；**0 = 不截断**；**非**按 token 切 system |
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
- `main.cache_block()` → Anthropic `cache_control: {type: ephemeral, ttl: 1h}`
- DeepSeek：system 合并为纯文本，无 cache
- 可选心跳：50 分钟无 API 且仍在写作时刷新 cache（`HEARTBEAT_*`）

**冷热分层与命中率**（2025 优化）

| 块 | 内容 | 典型刷新频率 |
|----|------|--------------|
| ① | world + style | 几乎不刷 |
| ② | characters + **char_static** | 人物本质不变则不刷 |
| ③ | **summaries_archive** + **plot_threads_locked** | 只追加归档/钉子时不刷前缀 |
| ④ | instruction + **char_dynamic** + **summaries_recent** + **plot_threads_active** + Beat | 每章必变 |

**调试：缓存命中验证（已实现）**

- 顶栏 **cache pill** 点击展开：`cache_read` / `cache_write` / `input` / `output` 明细、本次费用 vs 无缓存费用、TTL 剩余
- 数据：`state.last_call_info`（含 `cost_no_cache`、`cache_savings_pct`、`cache_write_at`、`cache_ttl_remaining`）
- 仅 kie 写书对话有 Prompt Cache 统计；DeepSeek 显示「无 Prompt Cache」

**调试：上下文内容验证（已实现）**

- 顶栏 **🔍 上下文** → 侧边抽屉，展示上次请求各层实际文本 + messages 摘要
- 接口：`GET /api/debug/last_context`
- 来源：`build_cached_system()` → `state.last_context_debug`；`log_request_context()` 追加 messages
- ④ 层可展开子项：`WRITING_INSTRUCTION`、Beat、char_dynamic、summaries_recent、plot_threads_active

---

## 四、已有功能清单

### 19. 写作模式

| Web 顶栏 | 功能 |
|----------|------|
| 概览 | 书架、world 摘要、大纲、点章只读 |
| 规划 | 建章、场景、Beat、排序、done |
| 写作 | 章节编辑、Codex、全局文件 |
| 写书对话 | SSE 续写、概述、检查、续章灵感、质量工具栏、**🔍 上下文调试**、撤销写入 |
| 自由聊 | 无设定注入 |
| 统计 | 字数、费用 |

CLI：`python main.py`（`/summary` `/check` `/outline` 等）。

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

### 26. 质量工具栏（写书对话）

| 按钮 | API | 说明 |
|------|-----|------|
| **一键章后维护** | `POST /api/post-chapter/maintain` | **1 次 LLM** → `post-chapter-json` 拆分写入 summaries / char_* / plot_threads_locked |
| 人物检查 | `POST /api/check/character-drift` | 对照 char_static + char_dynamic |
| **角色观察** | `POST /api/observe` · `POST /api/observe/apply` | 章后 AI 提案；用户确认后追加 char_static / char_dynamic |
| 提取细节 | `POST /api/extract/details` | 可选 `auto_append` → plot_threads_locked |
| 重复检查 | `POST /api/check/repetition` | scope: current / recent3 / all |
| 爽点检查 | `POST /api/check/pacing` | 需先有概述 |

---

## 五、现有问题与痛点

| # | 说明 |
|---|------|
| 27 | **已知限制**：Web 单进程单会话；自由聊等非流式；`chat_prompts.json` 非空时不自动合并新默认模板；无多书 / 多用户 |
| 28 | 质量风险：文风偏移、人设漂移、细节吃书、重复套话、节奏单一、爽点散乱——已通过 style / world / char 冷热分层 / plot_threads 拆分 / Beat 档位与指令库、六项检查按钮缓解；**章后 char_dynamic 仍须人工维护** |
| 29 | 上下文：长章正文首轮全量注入 user message；无硬 token 预算器；cache ②③ 已冷热分层，④ 层每章变动属预期 |
| 30 | **未实现**：单 Web 多书、多用户 session 隔离、Free 流式、细粒度 token 截断 |

---

## 六、代码细节

### 31. 调用 AI 的核心

- `providers.APIClient.create_message()` / `iter_message()`
- 封装：`main.call_api()`、`main.writing_chat_stream()`
- kie：Anthropic SDK + 自定义 UA/Bearer；DeepSeek：OpenAI SDK

### 32. 上下文组装的核心

- `build_cached_system()`、`get_world_block()`、`get_characters_block()`、`get_stable_archive_block()`、`get_dynamic_context_block()`
- `_prepare_writing_turn()`、`prepare_messages_for_context()`、`trim_history()`
- `get_last_context_debug()`、`calc_cost_no_cache()`、`_build_last_call_info()`、`_record_context_debug()`

### 33. 数据读写的核心

- `main.read_text()` / `write_text()`（带 backup）
- `file_utils.atomic_write_text()`
- `novel_data.load_plan()` / `_mutate_plan()`
- `read_chapter_content()` → `data/chapters/ch{num:03d}.md`

### 34. 中间件

- `web_app.web_auth_middleware`：本地 IP 或 `X-Novel-Token`
- `main._request_lock`：LLM 请求串行化

### 35. 错误处理

- `providers.APIError`（auth / rate_limit / timeout / network）
- `main._api_error_message()` 中文提示
- SSE `{type: "error"}`；流式断连可 fallback 非流式

---

## 七、扩展性相关

| # | 答案 |
|---|------|
| 35 | 模块：`main`、`web_app`、`novel_data`、`providers`、`config`、`summarizer`、`app_state` |
| 36 | 配置：`.env`、`config.py`、`data/runtime.json`、`prices.json` |
| 37 | 日志：`cost_log.jsonl`、`data/context_log.jsonl`（`NOVEL_CONTEXT_LOG=0` 可关） |
| 38 | FastAPI REST + SSE；静态 `web/`；业务在 `main.py` 可被 CLI 直接调用 |
| 39 | **不支持多用户**；`app_state` 单例（含 `last_call_info`、`last_context_debug`）；多用户需按 session 隔离（未实现） |

---

## 八、补充（重要设计决策）

1. **单书单会话**：一个 `data/` + 一份内存状态，不适合公网多用户。
2. **设定只增不改**：为 Prompt Cache 服务；全局 md 须手动保存 + 确认。
3. **章节写入**：显式「续写」类指令 **append**；定稿用 Web「替换本章」或 `apply-turn`。
4. **kie 网关**：须 Bearer + 自定义 User-Agent。
5. **地基文件**：`style.md`、`char_static`/`char_dynamic`、`summaries_archive`/`summaries_recent`、`plot_threads_locked`/`plot_threads_active` 已按冷热分层接入续写上下文。
6. **测试**：`python -m unittest discover -s tests -v`（45 项）。
7. **导演拍板原则**：AI 生成正文 / 检查 / 提案，**全局 md 与 char_dynamic 写入须用户确认**（全局文件保存有确认框）；自动写入仅限章节 append 与用户点选的「提取细节追加」。

---

## 九、角色观察（已实现）

> **产品原则**：你是导演，AI 提案，你拍板。章写入后可触发；**不自动写文件**，须用户在弹窗确认。

### 40. 机制

```
POST /api/observe（或章 append 成功后 confirm 触发）
     ↓
CHECK_PROVIDER 读本章 + char_static + char_dynamic
     ↓
返回结构化 items（observe-json）+ Markdown 摘要
     ↓
Web 弹窗：每条 ✅接受 / ✏️改一下 / ❌拒绝
     ↓
POST /api/observe/apply → 追加写入 char_static / char_dynamic
```

### 41. API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/observe` | body 可选 `{ chapter_num }`；默认最新章 |
| POST | `/api/observe/apply` | body `{ items: [{ id, target_file, accepted, proposed_text, edited_text }] }` |

### 42. 代码

| 项 | 位置 |
|----|------|
| Prompt | `summarizer.OBSERVE_SYSTEM`, `build_observe_user_message`, `parse_observe_proposals` |
| 业务 | `main.api_run_observe`, `main.api_apply_observe` |
| UI | 写书对话 **「角色观察」** 按钮；`observeModal` 弹窗 |

章 **append 写入成功** 后会 confirm 是否立即生成提案（不自动写档案）。

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

- 所有 `main.write_text()` 对追踪文件 → `change_history.save_with_history()`
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

`change_history.py` · `main._register_change_history()` · `init_data_dirs()` 内 `ensure_baseline_snapshot()`

---

## 十一、写作引导（已实现）

> 按阶段提示「先填什么、再规划、章后维护什么」，降低新手漏步骤概率。

### 48. 后端

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/guide/status` | `main.get_guide_status()`：stage、files 就绪、plan 场景数、章后 todos |

`stage`：`setup` → `planning` → `first_chapter` → `writing`。  
`post_chapter_todos`：`summary` / `char_dynamic` / `plot_threads` / `*_never` / `archive`（近期概述 ≥5 条）。

### 49. 前端

| 页面 | 容器 | 行为 |
|------|------|------|
| 总览 | `#overview-guide-bar` | 阶段条 + 维护告警 |
| 规划 | `#plan-guide-panel` | Beat 写法提示 |
| 写作 | `#write-guide-bar` | char_dynamic / 伏笔 / 概述滞后 |
| 写书对话 | `#chat-guide-bar` | 章后待办计数；**章保存成功**弹出 `postChapterModal` |

章后清单弹窗含 **角色观察** 入口；观察生成后 **auto_apply** 自动写入 char_*，完整报告进侧栏「质量记录」。

### 50. 写作目标章 vs 浏览章

| 概念 | 来源 | 用途 |
|------|------|------|
| `write_chapter_num` | 会话 / `/api/status` | AI 写入与质量检查默认章 |
| `state.currentChapter`（前端） | 侧栏/写作页选中 | 仅浏览编辑，**不再**随 `sendChat` 上传 |

章节正文注入在以下情况会失效并下轮重新从磁盘注入：手动/AI 保存、apply-turn、undo、历史 trim 裁掉首轮、API 失败回滚。Web 写书对话顶栏可选 **写作目标** 章（`PUT /api/chat/write-chapter`）。

### 51. 档案留痕 UI

设置抽屉 → **档案留痕**：按 `file_key` 筛选、`POST /api/history/revert` 撤销。

---

## 关键代码索引

| 主题 | 文件 | 符号 |
|------|------|------|
| 上下文组装 | `main.py` | `build_cached_system`, `_prepare_writing_turn`, `_record_context_debug` |
| 调试 | `main.py` / `web_app.py` | `get_last_context_debug`, `GET /api/debug/last_context`, `_build_last_call_info` |
| Plan / Codex | `novel_data.py` | `add_scene`, `get_scene_context_text` |
| LLM 调用 | `providers.py` | `APIClient.create_message`, `iter_message` |
| Prompt 模板 | `summarizer.py` | `WRITING_INSTRUCTION`, `CHECK_SYSTEM`, `CHARACTER_DRIFT_SYSTEM` |
| Web API | `web_app.py` | `/api/chat/stream`, `/api/codex/{name}` |
| 质量检查 | `web_app.py` | `/api/check/character-drift`, `/api/extract/details`, `/api/check/repetition`, `/api/check/pacing` |
| 角色观察 | `main.api_run_observe`, `POST /api/observe`（`auto_apply` 默认 true） | 自动追加 char_*；日志 `quality_log` |
| 质量记录 | `quality_log.py` | `GET /api/quality/log`, `GET /api/quality/log/{id}` |
| 档案留痕 | `change_history.py` | `GET /api/history`, `POST /api/history/revert` |
| 写作引导 | `main.get_guide_status` | `GET /api/guide/status` |
| 配置 | `config.py` | `CONTEXT_MODE`, `PROVIDERS`, `CHAT_CONTEXT_TURNS` |

---

## 一张总表（写作质量 ↔ 数据文件）

| 问题 | 解决工具 | 维护文件 | 平台行为 |
|------|---------|---------|---------|
| 人物漂移 | 性格锚点 + 人物检查 + **角色观察** | `char_static` + `char_dynamic` | 观察弹窗确认后追加写入 |
| 细节矛盾 | 细节钉子 + 提取细节 | `plot_threads_locked` + `plot_threads_active` | 锁定③ / 活跃④；按钮 `/api/extract/details`（追加 locked） |
| 重复句式 | 禁用词 + 重复检查 | `style.md` | 文风层；按钮 `/api/check/repetition` |
| 节奏单一 | Beat + pace 档位 | 规划场景 | 下拉保存；`get_scene_context_text()` 注入 |
| 情感太直 | 情感具象化规则 | `WRITING_INSTRUCTION` | 续写全局生效 |
| 爽点散乱 | 节拍表 + 爽点检查 | `world.md` | 续章灵感；按钮 `/api/check/pacing` |

详见手册 [§五 质量工具](./novel-writer-manual.md#五质量工具)。
