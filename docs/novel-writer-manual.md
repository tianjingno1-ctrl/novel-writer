# 数据层与质量参考（非 UI 手册）

> **版本**：2026-06-10（旧 Web 四 Tab 已移除；排期见 [canonical-status.md](./canonical-status.md)）  
> **产品流程与界面** → **[workflow.md](./workflow.md)**  
> **做了/没做/库存** → **[canonical-status.md](./canonical-status.md)**  
> **API 索引** → **[tech-intake.md](./tech-intake.md)** · OpenAPI `/docs`

---

## 一、快速启动

```bash
cd novel_writer
copy .env.example .env
pip install -r requirements.txt
python web_app.py          # API http://127.0.0.1:8765/docs

cd frontend && npm install && npm run dev   # UI http://127.0.0.1:5173
```

新 UI 路由：`/` 书架 · `/library/new` 向导 · `/writing` 写作（**左章列表 + 中间栏正文与 Gate**）· `/manuscripts` · `/settings`。

---

## 二、书库与数据文件

### 2.1 目录

| 概念 | 路径 |
|------|------|
| 书库索引 | `library/index.json` |
| 运行时配置 | `library/runtime.json`（换书不重置） |
| 单书 | `library/books/{id}/` |
| 全局口味 | `library/taste/global.json` |
| 平台审阅模板 | `library/profiles/*.yaml` |

```
library/books/{book_id}/
├── project.json      # type, platform, lifecycle
├── plan.json         # meta, chapters, review_criteria（规划真相源）
├── taste.json        # 本书口味覆盖（append_rules 等）
├── prompt_overrides.yaml
├── chapters/ch001.md …
└── quality_log.jsonl
```

**`project.json` 关键字段**

| 字段 | 取值 | 用途 |
|------|------|------|
| `type` | `novel` / `short` | 审阅 Prompt 路由；长篇与短篇同 Canonical 路径（`world` 旧类型已废弃） |
| `platform` | `tomato` / `qimao` / … | 审阅 profile |

短篇向导开书写 `plan.meta`，**不**再维护 `brief.md`（仅 legacy 迁移）。

### 2.2 全局 md 档案（Substrate，长篇/beats 模式仍读）

| 文件 | 用途 | 缓存层 |
|------|------|--------|
| `world.md` | 世界观、节拍 | ① |
| `style.md` | 文风锚点 | ① |
| `characters.md` / `char_static.md` | 人物 | ② |
| `char_dynamic.md` | 章后人物状态 | ④ |
| `summaries_recent.md` / `summaries_archive.md` | 概述 | ③④ |
| `plot_threads_locked.md` / `plot_threads_active.md` | 钉子/伏笔 | ③④ |
| Codex 条目 | 勾选注入 | 替代 characters 块 |

**Canonical 路径（短篇与长篇相同）**：向导 → Gate → 稿件；确认 `plan.meta` + `plan.chapters` + `review_criteria` + 口味库。**不强制**开书前填 world/style。长篇在写作期维护上表设定文件即可，不走旧批量生成流程。

**长短篇分叉（流程不变）**：`project.type` 驱动 — 口味 global 规则可选 `book_types`；`prefill.*` / `writing.main` / 审阅 profile（`short-tomato` vs `novel-tomato`）按书型路由。逐章 Beat 以 **plan** 为准，world 只写宏观规则。

### 2.3 上下文策略（`runtime.json` / 设置）

| 模式 | 注入 |
|------|------|
| `beats`（默认） | 场景 Beat + Codex |
| `summaries` | 章节概述 |
| `turns` | 最近 N 轮对话 |
| `codex` | 仅勾选 Codex |

### 2.4 提供商

| 变量 | 默认 | 用途 |
|------|------|------|
| `NOVEL_PROVIDER` | deepseek | 写作 SSE（Gate 续写） |
| `NOVEL_CHECK_PROVIDER` | deepseek | 检查类 |
| `NOVEL_MAINTAIN_PROVIDER` | deepseek | 档案同步 |
| `NOVEL_SUMMARY_PROVIDER` | deepseek | 概述 |

费用日志：`cost_log.jsonl`（全局，带 `book_id`）。

---

## 三、质量与档案（内部能力）

定稿（`finalize`）与章后维护（`POST /api/post-chapter/maintain`）内部会调用人物漂移、重复句式等检查（`core/reviewer.py`），结果写入 `quality_log` 供 P1 归因使用。  
**已无**独立「六项质量」按钮向 HTTP（2026-06-10 自 B 线移除）。

**新 UI 已接入 Gate 的**：预检、差距审阅（L4）、节奏预警、亮点入库、概述确认。  
**L2 编辑/读者视角**：后端 API 仍可用（`reader-preview` / `editor-preview`），**写作页已无 Tab**（2026-06）。

女频审阅 Prompt：`docs/review-prompts/{type}-{platform}.md`（`review_prompts.py` 路由）。

---

## 四、数据安全与 FAQ

- 写入前自动备份：`library/books/{id}/backups/`，每文件最多 10 份  
- 单进程单会话：勿多标签同时写  
- API Key：`.env` 中 `KIE_API_KEY` / `DEEPSEEK_API_KEY`  
- 切换书：`POST /api/library/switch`（会重置进程内写作状态）  
- 女频直改稿：预览不写盘；采纳走 `POST /api/review/female-fiction/accept`  

**Q：Codex 条目怎么生效？**  
A：上下文模式须为 `beats` 或 `codex`，且 `codex/active.json` 中勾选条目；写作页 Codex 侧栏 UI 已废弃，改文件或 CLI `save_codex`。

**Q：审阅 Prompt 在哪改？**  
A：`docs/review-prompts/` 下对应 md 文件。

---

## 五、CLI

`python main.py` 仍可用：`/summary`、`/check`、`/outline` 等。  
交互式写作以 **frontend + `/api/chat/stream`** 为主。
