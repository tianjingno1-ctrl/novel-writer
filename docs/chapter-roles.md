# 章级叙事语法（chapter.role）v1.0

<!-- NOVEL_WRITER_DESIGN_SNAPSHOT v1.0 -->
<!-- 粘贴本文件开头至新对话 +「继续」可续接实现 -->

> **定位**：短篇 MVP 的章级「挂钩」——所有 A9 规划与 L 段审阅/预检/读者视角都挂在此枚举上。  
> **用户路径**见 [workflow.md](./workflow.md)；**落盘字段**见 [data-schema.md](./data-schema.md) §五；**排期**见 [canonical-status.md](./canonical-status.md) §七。

---

## 已定稿决策（实现不得分叉）

1. **paywall_side**（计算字段，**不落盘**）：`num <= paywall_num → "pre"`；`num > paywall_num → "post"`。切割章（`role=paywall`）算 `pre`，转化语义由 `role` 承担。
2. **intent 落盘**：统一 `intent: { kind, ai_suggest, final }`；`kind` 与 `chapter.role` 同值。`paid_open` 无独立 intent，读上一章 `paywall` 的 `intent.final`。
3. **跨章闭环**：`bridge.intent.final.next_seed` 须与下一章 `buildup` 的 `intent.final.conditions` 语义对齐；`finale.intent.final.core_task.opening_gap` 须与第 1 章 `hook_open` 缺口呼应。

**命名**：`plan.meta.characters[].role` = **人物**角色（如 `female_lead`）；`plan.chapters[n].role` = **章节**叙事角色。二者不可混用。

---

## 核心架构

- 流程：**A（规划）→ L（逐章循环）→ P（归因）→ E（投递）**
- 铁律：**AI 预填 → 用户确认 → 才写盘**
- 用户在 **A9** 主要确认：`beat`、`hook`、`role`，以及各章 `intent.final`
- `review_criteria`：plan 级 **base**（平台 RuleRef）；章级 **overlay** 由 `role` + `intent.final` 动态加载，**不 per-chapter 持久化**

### 挂载链

```
A8 AI 预填 → title + beat + hook + role + intent.ai_suggest
      ↓
A9 确认 + 校验（paywall 唯一 + 拉弓 + 锚点章）
      ↓ 写入 plan.chapters
推导 paywall_side（运行时）
      ↓
├── L1b   role + paywall_side → 预检权重
├── L2    role + intent.final → 读者视角（不向用户暴露配方/internal 词）
├── L4    role + intent.final → 审阅维度（叠加 plan.review_criteria base）
├── L5b   role → 预警级别
└── E4b   meta.paywall_chapter → 平台切割位置验证
```

---

## chapter.role 枚举（8 值，封闭）

| role | 中文名 | 核心目标 |
|------|--------|----------|
| `hook_open` | 开篇钩子章 | 让读者读下去 |
| `buildup` | 铺垫章 | 制造情绪发生的条件，让读者自己产生情绪 |
| `escalation` | 爆发章 | 精准引爆 buildup 积累的情感债 |
| `paywall` | 付费切割点 | 让读者掏钱 |
| `paid_open` | 付费首章 | 让读者觉得值 |
| `climax` | 高潮章 | 最强爽点兑现 |
| `bridge` | 过渡章 | 节奏缓冲 + 埋下一根导火索 |
| `finale` | 完结章 | 情绪落地 + 留回味 |

### paywall 约束（`type=short` 时 error 级）

- 全书 **恰好 1 章** `role=paywall`
- **恰好 1 章** `role=paid_open`，且章号 = paywall + 1
- paywall **不能**是第 1 章或最后一章
- 建议位置：全书 **40%～55%**（超出 → **warn**，不阻断）
- 建议同步：`meta.paywall_chapter` 与 paywall 章号一致

`type=novel` 可跳过整套 paywall 校验。

### 锚点章（建议 error 或强 warn）

- 第 1 章：`hook_open`
- 最后一章：`finale`

---

## A9 拉弓结构校验（跨章）

```
buildup… → buildup → escalation（最后一箭）
```

| 校验项 | 检测内容 | 不达标症状 |
|--------|----------|------------|
| 压力梯度 | 多个 buildup 情感积累是否递进 | 每章 buildup 强度平铺 |
| 临界点 | escalation 前情感债是否「一触即发」 | 爆发显得突然 |
| 最后一根稻草 | escalation 引爆是否小而精准 | 大事件硬触发 |

原则：真正的爆发往往不是最大事件触发，而是长期积累后被一件「很小但很精准」的事压垮。

**escalation** 约束：`trigger` 不能比 `debt` 大；`intent.final.debt` 须能回溯前面 buildup 的 `intent.final.emotions`。

---

## intent 落盘形状

```json
{
  "title": "第九章",
  "hook": "结尾钩子",
  "role": "paywall",
  "word_count_target": 2200,
  "intent": {
    "kind": "paywall",
    "ai_suggest": "AI 根据 beat 推导的配方草稿",
    "final": {}
  },
  "scenes": [{ "beat": "…" }]
}
```

各 `kind` 的 `final` 形状见下表；`ai_suggest` → 用户确认 → 下游只读 `final`。

| kind | final 要点 |
|------|------------|
| `hook_open` | 梗×情绪组合配方（字符串或结构化，作者可自由格式） |
| `buildup` | `{ conditions, emotions }` — 条件载体 + 情感叠加方向 |
| `escalation` | `{ debt, trigger }` — 情感债 + 小而精准的引爆载体 |
| `paywall` | 读者付费前心理状态（一句话，驱动 L2） |
| `paid_open` | （无）读 paywall 的 final |
| `climax` | `{ mechanism, contrast, peak_carrier, ripple, ending_tone }` |
| `bridge` | 见 bridge 小节（含 `next_seed`） |
| `finale` | `{ core_task, freeze_frame, open_ending, … }` |

---

## 各 role 审阅要点（封版摘要）

实现时展开为 `library/profiles/chapter_roles/*.yaml` 的 L4/L1b/L2/L5b 权重；此处为产品真相源摘要。

### hook_open

- **定义**：卖「值不值得花时间」，不是卖类型/人设。
- **L4**：配方落地、顺序节奏、合力效果、代入点；禁止大段世界观铺垫。
- **L1b**：钩子 ↑↑、代入 ↑；字数放宽。
- **L5b**：高，不可跳过。

### buildup

- **定义**：搭条件让读者**自己**产生情绪；与 hook_open「触发」相对，是「积累」。
- **情感叠加**（可多选）：带入自己 / 爱上人物 / 带入场景 / 认可价值。
- **L4**：条件落地、情绪自发、情感叠加、节奏密度；禁止直接描述情绪。
- **L5b**：中，建议不跳过。

### escalation

- **定义**：精准引爆情感债；拉弓最后一箭。
- **L4**：引爆精准度、细节代替情绪、节奏收紧、视角锁定、爆发后克制。
- **L1b**：引爆对齐 ↑↑（阻断）；情绪词/爆发后解释 ↑ 警告。
- **L5b**：高，不可跳过。

### paywall

- **定义**：让读者掏钱；审转化力非「质量分」。
- **L4**：悬念强度、情感锚点、代价感、节奏收口；禁止大量新铺垫。
- **L5b**：最高，不可跳过。

### paid_open

- **定义**：付费后不后悔；顺序任务：**还债 → 续航 → 基调转换**（悬→燃/稳）。
- **无独立 intent**；L4 以 paywall `intent.final` 为基准。
- **续航**：次级钩子强度须 **低于** paywall 钩子。
- **L5b**：高，不可跳过。

### climax

- **定义**：完成读者心理代偿；爽感机制：债务清算 / 能力展示 / 关系确认（可叠加，主次分明）。
- **节奏**：收紧 → 静止感 → 引爆点 → 爆发波（三圈连锁）→ 余韵。
- **L5b**：高，不可跳过。

### bridge

- **定义**：情绪重置 + 埋下一 buildup 种子；三层：降压 / 信息补偿 / 新悬念（缺一不可）。
- **子类型**：依承接的 climax 类型选情绪缓冲 / 铺垫蓄势 / 关系沉淀。
- **篇幅**：1～2 章内完成；`next_seed` 对齐下一 `buildup`。
- **L5b**：中，建议不跳过。

### finale

- **定义**：情感交割非交代结局；三层顺序：情感交割 → 关系定格 → 余韵留白。
- **首尾**：`opening_gap` 对应 hook_open 缺口。
- **L5b**：最高，不可跳过。

---

## 与 plan.review_criteria 的关系

| 层 | 来源 | 用途 |
|----|------|------|
| base | `plan.review_criteria`（RuleRef + custom_checks） | 平台硬规则、全书检查项 |
| overlay | `chapter.role` + `intent.final` + `paywall_side` | L4/L1b/L2 动态维度 |

**不是二选一**；L4 prompt = base 注入 + role overlay。

---

实现进度见 **[canonical-status.md §七 Track R](./canonical-status.md)**（`library/profiles/chapter_roles/*.yaml` + `core/chapter_role_profiles.py`）。
