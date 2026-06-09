# novel_writer 产品方案

> **定位**：我是读者，不是作者。AI 负责生产，我负责审阅和判断。  
> **流程**：[workflow.md §一](./workflow.md) · **数据 Schema**：[data-schema.md](./data-schema.md)（定稿）

## 核心原则

1. AI 预填 → 人确认；预览 → 采纳才写盘  
2. 判断留痕 → 口味库（负向 + **正向案例 L5a**）  
3. 拒稿 / 改规则 → **内容类**走 **Prompt 归因（P1）**；**投递策略类拒稿**回 **E4b**；重跑前选范围（**P3b**）  
4. 写完后 **机器预检（L1b）** 再给人预览；概述每章必确认  

## 五处流程补丁（已定稿）

| # | 节点 | 要点 |
|---|------|------|
| 1 | L5a | 审阅通过 → 亮点进口味库正向案例 |
| 2 | E4b | 投递前选类型（文字/漫剧/短剧）→ 审阅标准+模板 |
| 3 | L1b | 字数+大纲关键词预检，不过不给人看 |
| 4 | P3b | 重跑：仅本章 / 从第N章 / 仅规划 |
| 5 | E7 | 拒稿分叉：内容→P1；投递策略→E4b |

## 数据模型（定稿）

完整字段、真相源、迁移见 **[data-schema.md](./data-schema.md)**。要点：

- **无** `books/{id}/index.json`；书元数据 + lifecycle → `project.json`
- 拆文 → `library/deconstruct/`（与 taste 平级）
- 口味 v2 → `global.rules` + `global.examples`；规则引用 `global:` / `local:` / `profile:`
- 标准层 → `library/profiles/`；执行层 → `prompts/review/`
- 归因 → `books/{id}/diagnosis/`；patch 对齐 `prompt_overrides` 的 `node_id`

## 模块状态

| 模块 | 状态 |
|------|------|
| 流程 + 数据 Schema 定稿 | ✅ |
| RuleRef 解析 + 产品 Schema 逻辑 | ✅ |
| 口味库 v2 + 正向 L5a API | ✅ |
| plan.meta / review_criteria / chapter.status | ✅ |
| 审阅链路 L1b/L5a/标准注入 | ✅ |
| P3b 重跑 preview + **P4 pipeline execute** | ✅ |
| **聚合 flow runner**（`/api/flow/run`，与单步 API 并存） | ✅ |
| E4b 投递类型校验 + 拒稿 diagnosis | ✅ |
| 概述 confirm → approved | ✅ API |
| 前端 | ✅ 开书（拆文+A10b）+ Gate（L5a/标签/标准）+ 完结 pending_summary + E4b |
| E1b pending_summary | ✅ `GET /api/flow/work-queue` |
| brief→plan.meta M2 | ✅ apply 写 meta；启动迁移 legacy brief |

详见 [workflow.md §五–§六](./workflow.md) · [data-schema.md §十–§十一](./data-schema.md)。
