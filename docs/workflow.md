# 全流程手册

> **角色**：读者 + 审核者。AI 生产，你判断。  
> **交互**：AI 预填 → 你确认；预览 → 采纳才写盘。  
> API 实操见 `http://127.0.0.1:8765/docs`；机器可读流程见 `GET /api/prompts/flow`。

---

## 一、总流程图（定稿）

以下为产品定稿流程（含 2026-06 补丁 + 三方向新增）。图中 **不写 API 文件名**，实现映射见 §五。  
**★** = 2026-06 三方向新增节点；**虚线** = 可选 / 反馈路径（非主循环）。

### 1.1 四阶段布局（绘图用）

| 泳道 | 阶段 | 主色建议（对齐 `frontend/src/index.css`） |
|------|------|---------------------------------------------|
| 左 1 | **A · 开书** | `--color-primary` 墨绿 `#2d6a4f` |
| 左 2 | **L · 每章循环** | `--color-foreground` 正文色；决策菱形用 `--color-success` |
| 左 3 | **P · Prompt 归因** | `--color-warning` `#b45309`（反馈环，虚线汇入） |
| 左 4 | **E · 完结与投递** | `--color-muted` 边框 + `--color-accent` 底 |

**新增三点（★）在图中的锚位：**

| ★ | 节点 | 锚位 | 线型 |
|---|------|------|------|
| 1 | **AI 腔风险分** | 嵌在 `L1b` 机器预检内（并行项，最早拦截） | 实线；不过 → 回 `L1` |
| 2 | **读者视角** | 并列挂在 `L2` 预览（Tab：编辑 / 读者） | 实线 |
| 2b | **节奏预警** | `L5a` 之后**独立节点** `L5b`（非「还有章?」内嵌） | 连续高风险 → **虚线** → `P1` |
| 3 | **合规预检** | `E4b` 与 `E5` 之间 `E4c` | 高风险回改 → **虚线** → `L7` |
| — | **风格提炼** | `E8` 复盘内可选 `E8b` | 资产 → `author_profile.json` → 回流 **A4** |

**E7 拒稿分叉（相对旧版修正）：** 拒稿标签写入口味库后，用户选归因路径——**内容问题** → `P1`（章节写作归因）；**投递策略** → `E4b`（重选平台/类型），避免用 P1 硬套规格类拒稿。

```mermaid
flowchart TD
    START([灵感 / 爆文 / 平台取向]) --> OPEN

    subgraph OPEN [阶段 A · 开书]
        A1[新建书] --> A2{有爆文?}
        A2 -- 是 --> A3[拆文]
        A3 --> A3b[规律写入口味库]
        A2 -- 否 --> A4
        A3b --> A4
        A4["可选: 配置口味库 ★\n或继承 author_profile"] --> A5[AI预填方向 · 2~3方案]
        A5 --> A6{选一个 / 微调}
        A6 -- 换方案 --> A5
        A6 -- 确认 --> A7[写入 plan.meta]
        A7 --> A8[AI预填章规划 · 含钩子/Beat]
        A8 --> A9{确认规划?}
        A9 -- 再生成 --> A8
        A9 -- 确认 --> A10[(plan.json · meta+chapters)]
        A10 --> A10b[生成/确认审阅标准]
    end

    A10b --> LOOP

    subgraph LOOP [阶段 B · 每章循环]
        L1[AI写正文\n读 plan + 口味库 + 审阅标准] --> L1b{"机器预检 ★\n字数? 大纲?\nAI腔风险?"}
        L1b -- 不达标 --> L1
        L1b -- 达标 --> L2["用户预览 ★\n编辑视角 | 读者视角"]
        L2 --> L3{采纳?}
        L3 -- 否 --> L1
        L3 -- 是 --> L4[按审阅标准做差距分析]
        L4 --> L5{用户判断}
        L5 -- 通过 --> L5a[AI提取本章亮点\n正向案例写入口味库]
        L5a --> L5b{"节奏预警 ★\n近3章弃文风险?"}
        L5b -. 连续高风险 .-> P1
        L5b --> L10[AI自动生成概述]
        L10 --> L10b{用户确认概述?}
        L10b -- 再生成 --> L10
        L10b -- 确认 --> L11{还有章?}
        L11 -- 是 --> L1
        L5 -- 不通过 --> L6{改什么?}
        L6 -- 改本章 --> L7[打标签\n输入修改意见]
        L7 --> L8[AI改稿预览]
        L8 --> L9{采纳?}
        L9 -- 否 --> L8
        L9 -- 是 --> L4
        L6 -- 改规则 --> P1
    end

    subgraph PROMPT [阶段 C · Prompt归因]
        P1[归因分析] --> P2[预览patch]
        P2 --> P3{写入override?}
        P3 -- 是 --> P3b[选择重跑范围\n仅本章 / 从第N章 / 仅规划]
        P3b --> P4[确认后执行重跑]
        P4 --> LOOP
        P3 -- 否 --> LOOP
    end

    L11 -- 写完 --> ENDFLOW

    subgraph ENDFLOW [阶段 D · 完结与稿件]
        E1{确认全书完结?} -- 否 --> LOOP
        E1 -- 是 --> E1b{有未确认概述?}
        E1b -- 有 --> E1c[软提示: X章待确认\n是否现在处理?]
        E1c -- 是 --> E1d[处理待确认概述]
        E1d --> E2
        E1c -- 否 --> E2
        E1b -- 没有 --> E2
        E2[创建稿件 manuscript] --> E3[状态 → complete]
        E3 --> E4{要投递?}
        E4 -- 否 --> E8([复盘 / 留库])
        E4 -- 是 --> E4b[选择投递类型\n文字编辑 / 漫剧 / 短剧]
        E4b --> E4c{"合规预检 ★\nAI腔全书扫描"}
        E4c -- 风险低 --> E5[投递\n加载对应审阅标准+记录模板]
        E4c -- 风险高 --> E4d{用户决策}
        E4d -- 忽略继续 --> E5
        E4d -. 回改 .-> L7
        E5 --> E6{结果?}
        E6 -- 通过 --> E8
        E6 -- 拒稿 --> E7[拒稿标签写入口味库]
        E7 --> E7a{拒稿原因?}
        E7a -- 内容问题 --> P1
        E7a -- 投递策略 --> E4b
        E8 --> E8b[可选: 风格提炼 ★\n→ author_profile.json]
        E8b -. 下本书 .-> A4
    end
```

**补丁说明（相对上一版）**

| # | 节点 | 行为 |
|---|------|------|
| 1 | `L5a` | 审阅通过后，AI 提取有效钩子/节奏等 → 口味库 **正向案例** |
| 2 | `E4b` | 投递前选类型 → 加载不同 **审阅标准** 与 **投递记录模板** |
| 3 | `L1b` | 写完后机器预检（字数、大纲关键词）；不达标自动打回 `L1`，不进预览 |
| 4 | `P3b` | 写入 override 前选 **重跑范围**（仅本章 / 从第 N 章 / 仅规划），确认后 `P4` |
| 5 | `E7` | 拒稿标签后 **分叉**：内容 → `P1`；投递策略 → `E4b`（旧版一律 P1 已废弃） |
| 6 | `L1b` | 并行 **AI 腔检测**；阈值按 `plan.meta.platform` 动态取 |
| 7 | `L2` | 预览 **双视角**：编辑（钩子/节拍）+ 读者（爽点密度、弃文风险） |
| 8 | `L5b` | `L5a` 后 **节奏预警**（近 3 章弃文风险）；虚线可选 → `P1` |
| 9 | `E4c` | 投递前 **合规预检**；高风险虚线回改 → `L7` 或忽略继续 |
| 10 | `E8b` / `A4` | 完结 **风格提炼** → `author_profile.json`；开书可 **继承** |

**已与代码对齐**：`E3` 稿件状态为 **`complete`**（非 `completed`）。

---

## 二、四条铁律

1. **AI 预填 → 你确认**（方向、规划、概述、改稿）
2. **预览 → 采纳才写盘**（正文、规划、概述、prompt override）
3. **判断留痕**（`outcome` + `issue_tags`）→ 口味库；**通过时**沉淀正向案例（`L5a`）
4. **拒稿 / 改规则** → 改规则与**内容类拒稿**走 **Prompt 归因环**（`P1`）；**投递策略类拒稿**回 `E4b` 重选

---

## 三、核心概念（不写死文件名）

### 3.1 `plan.json`（规划真相源）

短篇优先：**方向与章规划合并在一个文件**，不再单独维护 `brief.md`（目标态；见 §六实现差距）。

| 字段 | 含义 | 何时写入 |
|------|------|----------|
| `meta` | 已确认方向：logline、卖点、基调、目标章数等 | 阶段 A，方向确认后 |
| `chapters` | 章标题、场景、Beat、钩子 | 阶段 A，规划确认后 |
| `review_criteria` | **审阅标准**（检查项清单，见下） | 开书末或拆文后，你确认后 |

`chapters` 结构与现有 `plan.json` 兼容；`meta` / `review_criteria` 已实现（见 `GET /api/plan/product`）。

### 3.2 审阅标准（Review Criteria）

**概念**：本章/本书「过不过」的对照清单（钩子、节奏、平台项等），供 `L4 差距分析` 使用。

| 维度 | 说明 |
|------|------|
| 来源 | 拆文规律、口味库、平台取向、你确认的补充项 |
| 行为 | AI 可建议条目；**你确认后才生效** |
| 与口味库 | 口味 = 长期偏好；审阅标准 = 检查项清单（可重叠，职责不同） |
| 与 prompt | 标准 = **查什么**；`review.platform` 等节点 = **怎么查、怎么写** |
| 落盘 | 由实现决定（`plan.review_criteria` 或等价配置）；**需求只定字段与行为** |

### 3.3 口味库

跨书 `global` + 本书 `taste` + 事件流 `events`：拆文、judgment、投递拒稿自动沉淀；预填/审阅/拆文时注入上下文。

### 3.4 Prompt 节点与 override

每个 pipeline 步骤对应 `node_id`（写作、预填、审阅、诊断等）。本书可在 `prompt_overrides` 覆盖；归因环 **preview → 确认写入**。

---

## 四、阶段说明

### 阶段 A · 开书

| 步骤 | 你的动作 | 说明 |
|------|----------|------|
| 新建书 | 选 type/platform | 短篇优先 `type=short` |
| 拆文（可选） | 粘贴爆文 | 规律进口味库；可提炼审阅标准候选 |
| 口味库（可选） | 配置 likes/dislikes | 一次配置，长期复用 |
| 预填方向 | 从 2～3 方案中选 | 确认 → **`plan.meta`** |
| 预填规划 | 确认章/Beat/钩子 | 确认 → **`plan.chapters`** |
| 审阅标准 | 确认检查项清单 | → **`plan.review_criteria`**（或等价存储） |

### 阶段 B · 每章循环

| 步骤 | 你的动作 | 说明 |
|------|----------|------|
| 写正文 | — | AI 读 plan + 口味 + 审阅标准 |
| 机器预检 | 无（自动） | 字数 + 大纲关键词 + **AI 腔**；不过 → 自动重写 |
| 预览正文 | 采纳? | 双 Tab：编辑 / **读者视角**；否 → 重写 |
| 差距分析 | 读报告 | **按审阅标准** |
| 不通过 | 改本章 / 改规则 | 改本章：标签 → 改稿 → 再审阅；改规则 → **阶段 C** |
| 审阅通过 | 无（自动） | **L5a** 正向案例；**L5b** 节奏预警（虚线可进 P1） |
| 确认概述 | 采纳? | 概述 AI 生成 → 你确认 → `L11` 下一章 |

### 阶段 C · Prompt 归因

**统一入口 `P1`**：章审阅改规则（`L6`）、**内容类拒稿（`E7a`）**、**节奏预警（`L5b` 虚线）** 进入此环。  
**不进 P1**：投递策略类拒稿 → `E4b`；合规回改 → `L7`（改稿环，非 prompt 归因）。

流程：归因 → 预览 patch → 是否写入 override → **选重跑范围（P3b）** → 确认执行 → 回阶段 B。

### 阶段 D · 完结与稿件

| 步骤 | 说明 |
|------|------|
| 未确认概述 | 完结前软提示；`GET /api/flow/work-queue` → `pending_summary` |
| 创建稿件 | `manuscript`，`draft` |
| complete | 确认可交付 |
| 选择投递类型 | 文字编辑 / 漫剧 / 短剧 → 审阅标准 + 记录模板 |
| 投递 / 结果 | 拒稿 → 口味库 → **`E7a` 分叉**（内容→P1 / 策略→E4b） |

稿件状态：`draft → complete → submitting → result → revising → …`（详见 `core/manuscript.py`）。

---

## 五、当前 API 映射（实现对照）

| 流程节点 | 现有 API | 备注 |
|----------|----------|------|
| 新建书 | `POST /api/library/books` | |
| 拆文 | `POST /api/deconstruct` | |
| 规律进口味库 | `POST /api/taste/import-deconstruct` | |
| 配置口味库 | `PUT /api/taste/global` · `PUT /api/taste/book` | |
| 预填方向 | `POST /api/prefill/direction` → `apply` | ✅ 写 `plan.meta`；legacy `brief.md` 只读迁移 |
| 预填规划 | `POST /api/prefill/plan` → `apply` | 写 `plan.chapters`；可 `init_review_criteria` |
| 审阅标准 | `GET/PUT /api/plan/review-criteria` · `POST .../init` | |
| 写正文 | `POST /api/chat/stream` | |
| 机器预检 L1b | `POST /api/chapters/{n}/precheck` | 含 AI 腔；阈值见 `plan.meta.platform` |
| 读者视角 L2 | `POST /api/chapters/{n}/reader-preview` | 爽点密度 + 弃文风险；读 `taste.reader_pattern` |
| 合规预检 E4c | `POST /api/compliance/preview` | body: `submission_target`；高风险虚线 → L7 |
| 节奏预警 L5b | `GET /api/flow/work-queue` | 字段 `rhythm_warning`（实现暂挂在章末队列检查） |
| 作者风格 E8b/A4 | `GET/POST /api/taste/author-profile` · `.../extract` · `.../apply` | `library/author_profile.json` |
| 读者口味 | `PUT /api/taste/book/reader-pattern` | 写入 `taste.reader_pattern` |
| 差距分析 | `POST /api/review/female-fiction` | 按 `resolved_criteria` |
| 正向案例 L5a | `POST /api/taste/highlights/{n}` | 概述确认时亦可 `push_highlights` |
| 打标签 | `POST /api/quality/log/{id}/judgment` | 同步口味库 |
| 改稿采纳 | `POST /api/review/female-fiction/accept` | |
| 概述 | `POST /api/post-chapter/finalize` → `GET/POST .../summary/confirm` | 侧车 `chapters/chNNN/summary.json` |
| Prompt 归因 P1 | `POST /api/prompts/diagnose` · `diagnose/preview` | L6、E7 内容类、L5b 可选 |
| 重跑范围 P3b | `POST /api/rerun/preview` · `execute` · `pipeline` | `chapter_only` / `from_chapter_n` / `plan_only` |
| 聚合流程 | `POST /api/flow/run` · `GET /api/flow/work-queue` | 含 `pending_summary` |
| 稿件 | `POST /api/manuscripts` · `PATCH` | `state: complete` |
| 投递类型 E4b | `PATCH` `submission.target` | `text_editor` / `comic_drama` / `short_drama` |

---

## 六、实现差距（开发 backlog）

| 目标态（本流程图） | 当前代码 |
|--------------------|----------|
| 前端全覆盖 | MVP 已接主路径；自由聊/批量/Codex/质量六项等待 UI |
| `brief.md` 彻底废弃 | apply 已写 `plan.meta`；启动时 M2 迁移；不再新建 brief |
| chapters Phase 2 全量侧车 | `summary.json` 已有；`review.json` 待做 |
| API 改名 `female-fiction` | 路径未改，行为已泛化 |
| E4b 投递记录模板 | `submission.target` 有；完整模板 UI 待加强 |
| E7 拒稿分叉 UI | 文档已定 `E7a`；前端 Complete 页待「内容 / 策略」二选一 |
| 多用户 / 会话隔离 | 单进程单会话 |
| 前端 E2E | 无自动化联调 |

---

## 七、Prompt 节点索引

| node_id | 阶段 |
|---------|------|
| `prefill.direction` | A |
| `prefill.plan` | A |
| `writing.main` | B |
| `review.platform` | B（执行审阅标准） |
| `maintain.summary` | B |
| `diagnose.prompt` | C |
| `check.deconstruct` | A（拆文） |

---

## 八、核对记录

| 决议 | 流程节点 |
|------|----------|
| 口味库（负向） | judgment、E7 拒稿标签 |
| 口味库（正向） | **L5a** 审阅通过亮点 |
| 投递/拒稿 | 阶段 D；**E4b** 类型 |
| Prompt 归因 | **L6→P1**、**E7a 内容→P1**、**L5b 虚线→P1**；**E7a 策略→E4b**；**P3b** 重跑范围 |
| brief 并入 plan | A7 `plan.meta` |
| 审阅标准 | A10b、L4；按投递类型可覆盖 |
| 概述必确认 | L10 → L10b |
| 机器预检 | **L1b** 先于用户预览 |
| 完结前待确认概述 | E1b–E1d · `pending_summary` |
| 合规 / 读者模拟 | **L1b** AI 腔 · **E4c** 全书扫描 · **L2** 读者视角 |
| 节奏预警 | **L5b** · `retention.json` 侧车 |
| 跨书风格资产 | **E8b** 提炼 · **A4** 继承 · `author_profile.json` |

---

相关：[product-plan.md](./product-plan.md)
