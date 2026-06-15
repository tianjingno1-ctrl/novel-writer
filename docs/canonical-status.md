# Canonical 产品状态（新流程 vs 库存 vs 已废弃）

> **产品定义**以 [workflow.md](./workflow.md) + [chapter-roles.md](./chapter-roles.md) + `frontend/` 为准。  
> **排期唯一真相源**：本文 **§七**（Track S / F / Prompt / **E**）。勿在 `AGENTS.md` 或其他文件维护平行 backlog。  
> 后端 API / 盘格式是 **Substrate（能力库存）**，有 API ≠ 产品已有。  
> 旧四 Tab Web UI（`web/`）已删除，**不得**再作为需求或排期依据。  
> **长篇（`type=novel`）与短篇同一用户路径**（向导 → Gate → 稿件）；长篇仅多维护 `world.md` / `style.md` / Codex 等设定文件供上下文组装，**不**保留旧「先填 world 再批量生成」或 `batch_generate` 平行流程。

最后更新：2026-06-15（workflow 定稿节点 · 实现对照表；`writing_mode` 移除落地）

---

## 一、Canonical 用户路径（已实现）

```
/ 书架 → /library/new 向导 → /writing Gate 心流 → /manuscripts → /complete
/settings（书籍设定 · 模型 · 口味 · 费用 · 作者档案 · Prompt 节点）
```

| 节点 | 前端 | 后端 |
|------|------|------|
| A 开书 · 基本/偏好/方向/规划/标准 | `NewBookPage` + wizard 五步 | `POST /api/library/books`、`prefill/*`、`plan/meta`、`plan/review-criteria/init` |
| A 拆文 | `StepReference` | `POST /api/deconstruct`、`/api/taste/import-deconstruct` |
| L 续写 / 预览 / Gate | `FlowCanvas` + SSE | `POST /api/chat/stream` |
| L 会话恢复 | `SessionRecoveryBanner` | `POST /api/chat/restore` · `GET /api/status` |
| L1b 预检 | Gate（正文下方） | `POST /api/chapters/{n}/precheck` |
| L3 采纳 / 重写 | Gate `preview_cta`（正文下方） | `apply-turn` · 采纳后进 L4/L5a |
| L4 差距审阅 | Gate | `POST /api/review/female-fiction`（别名 `/api/review/chapter`） |
| L5a 亮点 | Gate | `POST /api/taste/highlights/{n}` |
| L5b 节奏 | Gate | `POST /api/chapters/{n}/rhythm-check` |
| L10/L11 概述 | Gate | `finalize` + `summary/confirm`（**现态**：整包定稿 + 150–300 字概述；**定稿图**见下表 L10 拆分） |
| P1 归因 | `AttributionRulesDrawer` | `POST /api/prompts/diagnose` |
| E 稿件/合规 | `ManuscriptsPage` / `CompletePage` | manuscripts + compliance API |
| 书籍档案（长篇） | `BookFilesPanel`（设定+章后档案）· 写作页「设定」 | `GET/PUT /api/book/files/*` |
| 口味库（全局） | `TastePanel`（设置） | `/api/taste/global`、rules delete/localize |
| 费用 | `CostSummaryPanel` | `GET /api/cost/summary` |

---

## 二、Substrate 有、Canonical 未接（库存）

| 能力 | API | 说明 |
|------|-----|------|
| L2 读者视角 | `POST /api/chapters/{n}/reader-preview` | 后端 + role overlay 已实现；**写作页无 Tab**（2026-06 移除 `PreviewPanel`） |
| L2 编辑视角 | `POST /api/chapters/{n}/editor-preview` | 同上 |

*当前无其他待接 Substrate 项；长篇设定见 **设置 → 书籍设定**（E8）。*

**已废弃（2026-06-10，勿恢复）**：Codex 写作页 UI、章后六项抽屉、自由聊及对应 HTTP。  
定稿 / 章后维护内部仍调用 `core/reviewer.py`；Codex 条目仍供写作上下文。

---

## 三、已做（后端 + 新前端对齐 workflow）

- 向导五 step + `wizard_step` 持久化 + 草稿续写
- Gate 全链（无写作模式分叉）+ Track S role 全 overlay
- Track F（书型/题材/拆文规则/本书 append_rules）
- Prompt P0（设置页节点 + 归因抽屉查看指令）
- review.json Phase 2（L4 侧车 + judgment 回写 + Gate 审阅记录）
- **E1 会话恢复 UI**（写作页 Banner + restore/clear）
- **E2 审阅 API 别名**（`/api/review/chapter`）
- **E3 API 冒烟**（`tests/test_api_smoke.py`）
- **E4 review.json gaps**（`core/review_gaps.py` + Gate 差距展示）
- **E5 Playwright E2E**（`frontend/e2e/`：`canonical-ui-flow` 全流程 UI + `canonical-path`，`npm run e2e` / `npm run e2e:flow`）
- **E6 前端审阅路径**（`/api/review/chapter`）
- **E7 会话隔离**（`infra/session_book.py` · 切书保留对话 · API 按 token/host 分桶）
- **E8 书籍档案编辑器**（设定 + 伏笔/概述 · 设置「书籍档案」· 写作页「设定」）
- **长短篇分叉**（主流程不变）：口味 `book_types` 过滤 · `prefill_*`/`writing_*` 按 type 路由 · `tomato_*_v1` profile 拆分
- B 线清扫（除 Prompt 外 HTTP/UI 已删）
- **`writing_mode` 移除**（无 A10c；`GET /api/plan/product` 无该字段；`plan.meta` 读/写 strip）

---

## 三·一、workflow 定稿 vs 实现

> **[workflow.md](./workflow.md)** = 产品定稿流程图；**本表** = 代码/前端是否已落地。  
> 目标态未实现时，以 **现态**（§一 API/Gate）为准开发；勿把定稿图节点当作已实现。

| 功能 | workflow 节点 | 状态 | 现态摘要 |
|------|---------------|------|----------|
| `writing_mode` 移除（无标准/快速分叉） | ~~A10c~~ | ✅ 已落地 | `plan_product` strip；API 无 `writing_mode`；workflow 图无 A10c |
| 规划面板（常驻 + L10c 触发） | PLANPANEL / L10d | 🔲 目标态，未实现 | 向导 `StepPlan` 只读规划；`prefill/plan apply(replace=false)` 后端有，写作页无 UI |
| L10 拆分（档案 vs 极简回顾 vs 规划检查） | L10a / L10 / L10c | 🔲 目标态，未实现 | 现：`finalize` 单次 `post_chapter_maintain` bundle，无 L10a/L10 独立步 |
| L10b skip（空回顾 auto confirmed） | L10b | 🔲 目标态，未实现 | 现：`summary_gate` 必确认；短篇 `type=short` 整段跳过概述 Gate |
| A8 轻量章规划 prompt | A8 | 🔲 目标态，未实现 | 现：prefill plan prompt 仍偏详（beat + intent 结构） |

**排期**：上表 🔲 项未入 §七 Track 编号；立项时在此表增行或开新 Track，并改 workflow §六「实现差距」避免双源。

---

## 四、未做（工程/体验）

| 项 | 说明 |
|----|------|
| **Track N — 长篇上下文加厚** | 见 **§七 Track N**（用户明确：**暂不做**） |

---

## 五、多做 / 易误导（已清理或须排除）

| 项 | 处理 |
|----|------|
| 旧 `web/` 四 Tab UI | 已删 |
| 写作页 `PreviewPanel`（右侧正文 + L2 Tab） | **已删**（2026-06）；正文仅在 `FlowCanvas` 中间栏 |
| B 线（Codex 侧栏/六项/自由聊） | 已删 |
| `batch_generate` 平行流程 | 已删 |
| AGENTS 平行 backlog | 已收敛至 §七 |

---

## 六、文档 Canonical 链（只读顺序）

```
workflow.md（定稿图） → chapter-roles.md → canonical-status.md（§三·一 定稿 vs 实现） → data-schema.md → product-plan.md → tech-intake.md
```

---

## 七、排期（唯一真相源）

### Track S / F / Prompt — ✅ 已完成

见 git 历史；S0–S4、F1–F3、P0 均已落地。

### Track E — 工程收尾（当前主刀）

> **原则**：先补 **L 段体验断点** → **API 卫生** → **自动化** → **架构债** → **库存能力**。

| 序 | 项 | 说明 | 状态 |
|----|-----|------|------|
| E1 | 会话恢复 UI | `session_autosave.json` → 写作页 Banner | ✅ |
| E2 | 审阅 API 别名 | `POST /api/review/chapter`（保留 female-fiction 兼容） | ✅ |
| E3 | API 冒烟测试 | TestClient 覆盖 status / plan / review / session | ✅ |
| E4 | review.json 结构化 gaps | L4 LLM 输出解析 → gaps[] | ✅ |
| E5 | Playwright E2E | 书架→向导→Gate；**`canonical-ui-flow` + `canonical-ui-special`（全流程 + 重新生成/改稿）** | ✅ |
| E6 | 前端切 `/api/review/chapter` | chapterFlow 逐步弃用旧路径 | ✅ |
| E7 | 多用户 / session 隔离 | 按 book + client scope 隔离进程态 | ✅ |
| E8 | 全局 md 编辑器 | 设置 → 书籍设定 · `/api/book/files/*` | ✅ |

**Track E 工程收尾：✅ 已全部完成。**

### Track R — 章 role v1.0 深度（当前）

| 序 | 项 | 说明 | 状态 |
|----|-----|------|------|
| R1 | A9 拉弓压力梯度 | buildup 递进 / escalation debt+trigger / trigger 过大 warn | ✅ |
| R2 | L1b 阻断对齐 | escalation hard、buildup 情绪词、bridge hook、finale 首尾 | ✅ |
| R3 | 向导结构化 intent | `IntentFields` + `chapterForApply` 传 object final | ✅ |
| R4 | L2 读者模拟 | `try_llm_reader_review` + heuristic fallback | ✅ |
| R5 | role YAML 外置 | `library/profiles/chapter_roles/*.yaml` + loader | ✅ |
| R6 | bridge 跨章闭环 | `next_seed` ↔ 下一 buildup `conditions` A9 warn | ✅ |
| R7 | L2 结构化解析 | `RISK`/`PAYOFF` 行 + `parse_llm_reader_metrics` | ✅ |
| R8 | climax 五字段 | mechanism / contrast / peak_carrier / ripple / ending_tone | ✅ |

### Track U — 校验 UX 闭环（当前）

| 序 | 项 | 说明 | 状态 |
|----|-----|------|------|
| U1 | 校验可视化 | StepPlan 实时 A9 + Gate precheck 详情 + 读者 Tab 摘要 | ✅ |
| U2 | finale ↔ hook_open | `finale_opening_gap_mismatch` A9 warn | ✅ |
| U3 | debt ↔ buildup.emotions | `escalation_debt_untraceable` A9 warn | ✅ |
| U4 | L2 JSON schema | `{"risk","payoff","notes"}` 单行 JSON 解析 | ✅ |

### Track V — schema 与 L2 深化（当前）

| 序 | 项 | 说明 | 状态 |
|----|-----|------|------|
| V1 | intent.final 归一 | `core/intent_final.py` · finale `core_task` 嵌套读写 | ✅ |
| V2 | 校验读嵌套 | A9/L1b 跨章校验统一走 intent_final 助手 | ✅ |
| V3 | L2 role 问题集 | YAML `l2_questions` → 读者模拟 prompt | ✅ |
| V4 | 向导 finale 嵌套提交 | `nestIntentFinalForApply` / `flattenIntentFinalForEdit` | ✅ |

### Track W — 体验加固（当前）

| 序 | 项 | 说明 | 状态 |
|----|-----|------|------|
| W1 | review_gate L1b soft | 审阅门展示机器预检建议（不阻断） | ✅ |
| W2 | 其余 role schema | climax/bridge 保持扁平（v1.0 已够用） | ⏭ 跳过 |
| W3 | E2E 校验 | `plan-validation.spec.ts` + 采纳后刷新 precheck | ✅ |
| W5 | LLM 语义校验 | 向导「深度语义检查」· `plan_semantic_validate` | ✅ |

### Track X — v1.0 设计稿对齐（2026-06-11）

| 序 | 项 | 说明 | 状态 |
|----|-----|------|------|
| X1 | L1b hard 全 role | hook_open 章末/paywall 悬念/paid_open 衔接/bridge 变化/finale 定格+首尾 | ✅ |
| X2 | L5b 高风险禁跳 | `l5b_mandatory` + Gate 预警时仅改章/归因 | ✅ |
| X3 | bridge/finale schema | 嵌套 micro_change / next_seed / freeze_frame / open_ending | ✅ |
| X4 | prefill role intent | 短篇/长篇 plan 预填按 role 结构化说明 | ✅ |
| X5 | L4 维度补全 | hook_open 等 profile 注入设计稿维度表 | ✅（逐 role 可续补） |

**仍不在 v1.0 范围**：Track N 长篇上下文加厚（用户暂缓）。

### Track N — 长篇上下文加厚（待定 · 未开始）

> **用户决定（2026-06-11）**：暂时不做；下文为立项规划，实施时以此为准。  
> **原则**：主流程不变（向导 → Gate → 稿件）；只加强 `type=novel` 时 LLM **实际收到** 的上下文，不恢复 `batch_generate` / 旧 world 平行流程。  
> **现状**：E8 可编辑档案 + `writing_novel.yaml` + `build_cached_system()` 骨架已有；**缺**按书型裁剪、超长书 token 治理、按章筛选注入。

**已有 vs 缺口**

| 已有 | 缺口（加厚要补） |
|------|------------------|
| `BookFilesPanel` / `/api/book/files/*` | `novel` 专用注入策略（层权重、长度上限） |
| `core/context.py` 拼 world/style/人物/archive/recent/active | archive 过大时 sliding window，不全文灌入 |
| `writing_novel` 系统 Prompt 连载原则 | 按当前章 `plan` Beat / 出场人物筛选档案片段 |
| `GET /api/debug/last_context` 调试 | 写作页可读的「本章注入摘要」（产品化 debug） |
| Codex 条目可读 | 按章自动激活相关 Codex（非手选） |

**建议实施顺序（立项后）**

| 序 | 项 | 说明 | 依赖 |
|----|-----|------|------|
| N1 | novel 上下文策略开关 | `project.type=novel` 走 `build_cached_system` 分支；短篇行为不变 | `core/context.py` |
| N2 | archive 滑动窗口 | `summaries_archive` 超阈值只注入「卷摘要 + summaries_recent」；阈值可配置 | N1 |
| N3 | 按章筛选 dynamic | 从 plan 本章 beat/角色名匹配 `plot_threads_active`、char_dynamic 段落 | N1 |
| N4 | 审阅/连续性加厚 | L4、`cross_chapter_continuity` 默认带 locked + recent（与写作侧一致） | N1 |
| N5 | 本章上下文预览 UI | 设置或写作页展示 `last_context` 各层字数/摘要 | 已有 debug API |
| N6 | Codex 按章挂载（可选） | 根据 plan 场景/人物 id 自动 `format_active_codex_text` | Codex 数据质量 |

**验收标准（草案）**

- 开 `type=novel` 书写第 30+ 章时，system 上下文 token 不超配置上限，且仍含 recent + locked + 本章 Beat。
- `type=short` 回归：注入层与加厚前一致（或更短）。
- `GET /api/debug/last_context` 可对照 N1–N3 各层 `id` 与裁剪原因。

**主要改动面（预估）**：`core/context.py`、`app/writing_ctx`（若有）、`config` 上下文上限、`docs/tech-intake.md` §上下文组装。

不以复刻旧四 Tab、写书对话面板、世界批量生成、B 线为验收标准。
