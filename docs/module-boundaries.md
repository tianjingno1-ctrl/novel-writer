# 模块边界：口味 / 审阅标准 / Profile

> 改 `core/taste.py`、`criteria_resolver.py`、`profiles.py`、`chapter_role_profiles.py` 前先读本文。  
> 写作链五文件见各模块顶部 `#` 注释与 `.cursorrules`。

最后更新：2026-06-11

---

## 总览

| 文件 | 管什么 | 什么时候用到 |
|------|--------|--------------|
| **`core/taste.py`** | **作者口味数据层**：`library/taste/global.json`、本书 `taste.json`、规则 merge（global → 本书 append）、事件流、拆文导入、L5a 亮点、写作侧 taste 上下文块 | 设置页口味库、向导偏好步、Gate L5a、写作上下文注入口味 |
| **`core/criteria_resolver.py`** | **L4 审阅标准的解析器**：读 `plan.review_criteria` 里的 `RuleRef`，展开成 hard/soft 可执行条目 | Gate L4、`female_fiction` 审阅、product 页展示「已解析标准」 |
| **`core/profiles.py`** | **平台/投递 profile 层**：`library/profiles/*.yaml`（书型×平台×投递类型），审阅模板、`review_prompt_id`、profile 内嵌 rules | 向导标准步 init criteria、prefill 路由、L4 的 `profile:` RuleRef、书型/平台匹配 |
| **`core/chapter_role_profiles.py`** | **章叙事 role 配置层**：`library/profiles/chapter_roles/*.yaml`（buildup / hook_open / paywall…） | L1b 预检 overlay、L2 读者模拟、L4/L5b 按 role 路由 |

---

## 各自不管什么

| 文件 | 不负责 |
|------|--------|
| **taste** | 不解析 `review_criteria` 的 RuleRef；不加载章 role YAML |
| **criteria_resolver** | 不读写口味文件（只查 taste）；无 CRUD；不碰章 role |
| **profiles** | 不管作者个人偏好 CRUD；不管单章 role；目录是 `profiles/` 不是 `chapter_roles/` |
| **chapter_role_profiles** | 不管作者偏好、不管 L4 checklist RuleRef；只管 plan 里章的 **role** 与 Gate overlay |

---

## 调用关系（有交界、无重复实现）

```
plan.review_criteria (RuleRef[])
        │
        ▼
criteria_resolver ──global:/local:──► taste.load_global / load_book_taste
        │
        └──profile:──────────────────► profiles.resolve_profile_rule_ref
        │
        └──custom:───────────────────► plan 内 custom_checks

plan.chapters[].role
        │
        ▼
chapter_role_profiles ──► chapter_role_overlay（L1b / L2 / L4 / L5b）

taste ──（写作/L5a）──► LLM 上下文块、亮点库
profiles ──（书型路由）──► prefill、platform_profile 选择（criteria 引用 profile 时经 resolver）
```

- **taste ↔ criteria_resolver**：taste **存**规则；resolver 在审阅时 **解析** `global:` / `local:` 引用。有调用，职责不重叠。
- **criteria_resolver ↔ profiles**：resolver 的 `profile:` 来源是 `profiles.py`；profiles 提供平台标准模板，resolver 负责把 ref 变成 L4 用的条目。
- **criteria_resolver ↔ chapter_role_profiles**：**正交**。同一次 Gate 可能两处都用，但数据轴不同（审阅标准 vs 章叙事角色）。

---

## 常见混淆

### `chapter_role_profiles.py` vs `profiles.py`

两者都在 `library/profiles/` 树下，名字都带 profile，**不是同一个东西**：

| | **`core/profiles.py`** | **`core/chapter_role_profiles.py`** |
|--|------------------------|-------------------------------------|
| **目录** | `library/profiles/*.yaml`（如 `tomato_short_v1.yaml`） | `library/profiles/chapter_roles/*.yaml`（如 `hook_open.yaml`） |
| **粒度** | 一本书的 **平台/投递/书型** 默认审阅标准 | 单章的 **叙事角色**（buildup、paywall、finale…） |
| **谁写入 plan** | 向导「标准」步 → `review_criteria.platform_profile` | 向导「规划」步 → 每章 `role` / `intent` |
| **主要消费者** | L4 审阅 prompt、criteria_resolver 的 `profile:` ref | L1b 预检、L2 读者 Tab、L4/L5b role overlay |
| **典型问题** | 「番茄短篇审阅维度有哪些？」 | 「paywall 章 L1b 要检什么？L2 问读者什么问题？」 |

**记法**：`profiles` = **平台标准**（投递给谁、什么书型）；`chapter_role_profiles` = **章语法**（这一章在叙事结构里扮演什么角色）。

改错文件的信号：动 L4 维度表却改了 `chapter_roles/`；或改 paywall 预检却去改 `tomato_novel_v1.yaml`。

---

## 相关文档

- 口味 merge 与 RuleRef 格式：`docs/data-schema.md`
- 章 role / intent：`docs/chapter-roles.md`
- 产品排期：`docs/canonical-status.md`
