# novel_writer 产品方案

> **定位**：我是读者，不是作者。AI 负责生产，我负责审阅和判断。  
> **流程**：[workflow.md §一](./workflow.md) · **章叙事语法**：[chapter-roles.md](./chapter-roles.md) · **Schema**：[data-schema.md](./data-schema.md)  
> **排期**：见 [canonical-status.md §七](./canonical-status.md)（勿在本文件维护 backlog）

## 核心原则

1. AI 预填 → 人确认；预览 → 采纳才写盘  
2. 判断留痕 → 口味库（负向 + **正向案例 L5a**）  
3. 拒稿 / 改规则 → **内容类**走 **Prompt 归因（P1）**；**投递策略类拒稿**回 **E4b**；重跑前选范围（**P3b**）  
4. 写完后 **机器预检（L1b）** 再给人预览；章后 **极简回顾** 可确认或跳过  

## 五处流程补丁（已定稿）

| # | 节点 | 要点 |
|---|------|------|
| 1 | L5a | 审阅通过 → 亮点进口味库正向案例 |
| 2 | E4b | 投递前选类型（文字/漫剧/短剧）→ 审阅标准+模板 |
| 3 | L1b | 字数+大纲关键词预检，不过不给人看 |
| 4 | P3b | 重跑：仅本章 / 从第N章 / 仅规划 |
| 5 | E7 | 拒稿分叉：内容→P1；投递策略→E4b |

## 四条流程优化（2026-06，已定稿）

| # | 节点 | 要点 |
|---|------|------|
| 1 | L4a | 差距分析后可主动进 P1 |
| 2 | L5a | 正向案例入库含冲突检测 |
| 3 | P3c/d | 重跑前可选注入 author_profile（本书/他书） |
| — | ~~A10c~~ | **已移除**：无标准/快速写作模式；全书统一 Gate |

## 数据模型（定稿）

完整字段、真相源、迁移见 **[data-schema.md](./data-schema.md)**。要点：

- **无** `books/{id}/index.json`；书元数据 + lifecycle → `project.json`
- 拆文 → `library/deconstruct/`（与 taste 平级）
- 口味 v2 → `global.rules` + `global.examples`；规则引用 `global:` / `local:` / `profile:`
- 标准层 → `library/profiles/`；执行层 → `prompts/review/`
- 归因 → `books/{id}/diagnosis/`；patch 对齐 `prompt_overrides` 的 `node_id`

实现状态与排期见 **[canonical-status.md](./canonical-status.md)**（§三 已做 · §七 Track S/F/Prompt），不在本文件重复列表。
