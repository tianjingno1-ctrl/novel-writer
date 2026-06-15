"""概述生成与连续性检查的 prompt 模板。"""

import json
import re
from pathlib import Path

from core.prompts import load_system

WRITING_INSTRUCTION = load_system("writing")
SUMMARY_SYSTEM = load_system("summary")
CHECK_SYSTEM = load_system("check")
CROSS_CHAPTER_CONTINUITY_SYSTEM = load_system("cross_chapter_continuity")
READER_REVIEW_SYSTEM = load_system("reader_review")
EDITOR_REVIEW_SYSTEM = load_system("editor_review")
DECONSTRUCT_SYSTEM = load_system("deconstruct")
OUTLINE_SYSTEM = load_system("outline")
CHARACTER_DRIFT_SYSTEM = load_system("character_drift")
DETAIL_EXTRACT_SYSTEM = load_system("detail_extract")
REPETITION_CHECK_SYSTEM = load_system("repetition_check")
PACING_CHECK_SYSTEM = load_system("pacing_check")
OBSERVE_SYSTEM = load_system("observe")
POST_CHAPTER_MAINTAIN_SYSTEM = load_system("post_chapter_maintain")
QUALITY_CHECK_BUNDLE_SYSTEM = load_system("quality_check_bundle")
BULK_ARCHIVE_SUMMARIES_SYSTEM = load_system("bulk_archive_summaries")
BULK_ARCHIVE_STATE_SYSTEM = load_system("bulk_archive_state")

# LLM 结构化 JSON 解析：canonical 实现在 core.schemas.llm，此处 re-export 保持兼容。
from core.schemas.llm import (
    count_report_issues,
    parse_bulk_state,
    parse_bulk_summaries,
    parse_observe_proposals,
    parse_post_chapter_maintain,
    parse_quality_bundle,
)


def get_female_fiction_review_system(
    *,
    project: dict | None = None,
    profile_id: str | None = None,
    include_revise: bool = False,
) -> str:
    """女频核心审阅 system prompt（按书型×平台路由 docs/review-prompts/）。"""
    import review_prompts

    text, _pid = review_prompts.load_prompt_text(
        profile_id, project=project, include_revise=include_revise
    )
    return text

def build_summary_user_message(chapter_num: int, chapter_content: str) -> str:
    return f"请为以下第{chapter_num}章正文生成概述：\n\n{chapter_content}"


def build_check_user_message(
    world: str,
    characters: str,
    char_current: str,
    summaries: str,
    chapter_num: int,
    chapter_content: str,
) -> str:
    return f"""## 世界观设定
{world}

## 人物设定
{characters}

## 人物当前状态
{char_current or "（未维护）"}

## 章节概述（已写章节）
{summaries}

## 最新章节正文（第{chapter_num}章）
{chapter_content}

请对照以上资料，检查最新章节中的矛盾与不一致。"""


def build_cross_chapter_check_user_message(
    world: str,
    characters: str,
    char_current: str,
    summaries_slice: str,
    plot_locked: str,
    plot_active: str,
    scope_label: str,
    chapter_num: int,
    chapter_content: str = "",
) -> str:
    parts = [
        f"请对以下范围做跨章连续性检查：{scope_label}（锚点章：第{chapter_num}章）\n",
        f"## 世界观设定\n{world or '（未维护）'}\n",
        f"## 人物设定\n{characters or '（未维护）'}\n",
        f"## 人物当前状态\n{char_current or '（未维护）'}\n",
        f"## 范围内章节概述\n{summaries_slice or '（暂无概述，请先为本章定稿或生成概述）'}\n",
        f"## 细节钉子（plot_threads_locked）\n{truncate_context_tail(plot_locked) or '（暂无）'}\n",
        f"## 伏笔清单（plot_threads_active）\n{truncate_context_tail(plot_active) or '（暂无）'}\n",
    ]
    if chapter_content.strip():
        parts.append(f"## 锚点章正文（第{chapter_num}章，供对照）\n{chapter_content}\n")
    return "\n".join(parts)


def build_reader_review_user_message(
    chapter_num: int,
    scope_label: str,
    content: str,
    summaries_slice: str = "",
) -> str:
    body = content.strip() or summaries_slice.strip() or "（无内容）"
    kind = "正文" if content.strip() else "概述"
    return (
        f"请从读者视角审阅：{scope_label}（锚点第{chapter_num}章，主要依据{kind}）\n\n"
        f"{body}"
    )


def build_editor_review_user_message(
    chapter_num: int,
    scope_label: str,
    content: str,
    summaries_slice: str = "",
    world: str = "",
) -> str:
    body = content.strip() or summaries_slice.strip() or "（无内容）"
    kind = "正文" if content.strip() else "概述"
    return (
        f"请从编辑视角审阅：{scope_label}（锚点第{chapter_num}章，主要依据{kind}）\n\n"
        f"## 故事背景参考\n{world or '（未维护）'}\n\n"
        f"## 审阅材料（{kind}）\n{body}"
    )


def build_deconstruct_user_message(
    source_text: str,
    *,
    source_label: str = "",
    book_title: str = "",
    world_excerpt: str = "",
    style_excerpt: str = "",
    taste_excerpt: str = "",
) -> str:
    label = source_label.strip() or "外部参考文"
    parts = [f"请拆解以下「{label}」：\n"]
    if taste_excerpt.strip():
        parts.append(taste_excerpt.strip())
        parts.append("")
    if book_title or world_excerpt.strip() or style_excerpt.strip():
        parts.append("## 用户正在写的书（供「你的书可以怎么用」对照）\n")
        if book_title:
            parts.append(f"书名：{book_title}\n")
        if world_excerpt.strip():
            parts.append(f"### world.md 摘要\n{world_excerpt.strip()[:4000]}\n")
        if style_excerpt.strip():
            parts.append(f"### style.md 摘要\n{style_excerpt.strip()[:2500]}\n")
        parts.append("")
    parts.append("## 待拆解正文\n")
    parts.append(source_text.strip())
    return "\n".join(parts)


_FEMALE_REVIEW_MODE_HINTS = {
    "chapter": (
        "【审阅模式：章节正文】\n"
        "重点：钩子、爽点密度、章节结尾；逐段标注读者情绪。\n"
        "输出开头用 `# 女频审阅 · 第N章`。"
    ),
    "outline": (
        "【审阅模式：大纲/规划】\n"
        "六个维度各给判断：成立 / 有风险 / 需要重写，并说明原因。\n"
        "输出开头用 `# 女频审阅 · 大纲`。"
    ),
    "characters": (
        "【审阅模式：人物设定】\n"
        "重点：「被看见」张力——男主看见了女主什么？女主身上什么被忽视？\n"
        "输出开头用 `# 女频审阅 · 人物设定`。"
    ),
}


_FEMALE_REVIEW_REVISE_HINT = (
    "【任务：审阅 + 改稿】\n"
    "在同一条回复中：先按 system 中的输出格式完成审阅报告；"
    "然后 `---` 分隔，输出 `# 改稿正文` 及完整重写内容（见 system 改稿阶段说明）。\n"
)


_FEMALE_REVIEW_REWRITE_ONLY_HINT = (
    "【任务：直改稿】\n"
    "以下是需要你改写的素材。按 system 要求：内部完成上头点判断后，"
    "只输出改完的完整全文（不要诊断、不要建议、不要对照表）。\n"
)


def build_female_fiction_review_user_message(
    mode: str,
    body: str,
    *,
    book_title: str = "",
    chapter_num: int = 0,
    world_excerpt: str = "",
    revise: bool = False,
    rewrite_only: bool = False,
    taste_excerpt: str = "",
    revise_note: str = "",
) -> str:
    if rewrite_only and mode == "chapter":
        parts = [_FEMALE_REVIEW_REWRITE_ONLY_HINT, ""]
    else:
        hint = _FEMALE_REVIEW_MODE_HINTS.get(mode, _FEMALE_REVIEW_MODE_HINTS["chapter"])
        parts = [hint, ""]
        if revise:
            parts.insert(0, _FEMALE_REVIEW_REVISE_HINT)
    note = (revise_note or "").strip()
    if note and (revise or rewrite_only):
        parts.insert(1 if rewrite_only and mode == "chapter" else 0, f"【改稿说明】\n{note}\n")
    if book_title:
        parts.append(f"书名：{book_title}")
    if chapter_num > 0:
        parts.append(f"章节：第{chapter_num}章")
    if world_excerpt.strip():
        parts.append(f"\n## 世界观参考（节选）\n{world_excerpt.strip()[:3000]}\n")
    if taste_excerpt.strip():
        parts.append(taste_excerpt.strip())
        parts.append("")
    parts.append("## 待审阅材料\n" if not rewrite_only else "## 待改稿正文\n")
    parts.append(body.strip())
    return "\n".join(parts)


_FEMALE_REVISE_MARKERS = (
    re.compile(r"\n---+\s*\n\s*#\s*改稿正文", re.IGNORECASE),
    re.compile(r"\n#\s*改稿正文\s*\n", re.IGNORECASE),
)


def split_female_review_revise_reply(reply: str) -> tuple[str, str]:
    """拆分「审阅报告 + 改稿正文」同条回复。返回 (review, revised_body)。"""
    text = (reply or "").strip()
    if not text:
        return "", ""
    for pattern in _FEMALE_REVISE_MARKERS:
        match = pattern.search(text)
        if not match:
            continue
        review = text[: match.start()].strip()
        revised = text[match.end() :].strip()
        return review, revised
    return text, ""


def build_outline_user_message(
    world: str,
    char_current: str,
    summaries: str,
    plot_threads: str,
    next_count: int = 3,
) -> str:
    return (
        f"请基于以下资料，为接下来的 {next_count} 章设计剧情走向：\n\n"
        f"## 世界观\n{world or '（未维护）'}\n\n"
        f"## 人物当前状态\n{char_current or '（未维护）'}\n\n"
        f"## 已有章节概述\n{summaries or '（暂无概述，请先 /summary）'}\n\n"
        f"## 未回收伏笔\n{plot_threads or '（未维护）'}\n"
    )


CHARACTER_DRIFT_SYSTEM = """你是专业的小说编辑，负责检查人物性格一致性。
请对照【人物状态锁】中的性格锚点与禁止写法，分析【最新章节正文】中人物的行为、对话、反应是否出现漂移。

输出格式：

## 人物一致性报告
### ✅ 一致的部分
### ⚠️ 疑似漂移
- 人物：XXX
- 原设定：XXX
- 本章表现：XXX（引用原文）
- 建议：XXX
### 📌 建议更新 char_dynamic.md 的内容（如有合理成长）
"""

DETAIL_EXTRACT_SYSTEM = """你是专业的小说编辑，负责追踪细节一致性。
请从【章节正文】中提取所有需要在后续章节保持一致的具体细节。

提取范围：
- 具体数字（年龄、金额、时间、距离等）
- 外貌特征（身高、发色、标志特征等）
- 专有名词（地名、公司名、物品名等）
- 已发生的关键事件（不可逆的）
- 人物关系的新变化

输出格式（直接输出可追加到 plot_threads_locked.md「已钉死的细节」的 Markdown 列表）：

## 第X章新增细节钉子
- 【类别】描述（出处：原文简短引用）
"""

REPETITION_CHECK_SYSTEM = """你是专业的文字编辑，负责检查套话与重复表达。
请分析【正文】中出现频率过高的词语、句式、段落结构。

输出格式：

## 套话检查报告
### 高频词语（出现3次以上）
| 词语/句式 | 出现次数 | 建议替换 |
|---------|---------|---------|

### 重复句式模式
- 模式：XXX（举例说明）
- 出现次数：X
- 替换建议：XXX

### 建议加入 style.md 禁用词
（直接列出可复制的禁用词条目，格式：- XXX（已出现N次））
"""

PACING_CHECK_SYSTEM = """你是专业的爽文编辑，负责检查剧情节奏与爽点分布。
请对照【世界大纲（world.md）】中的章节节拍表与爽点设计，
分析【已完成章节概述（summaries_archive + summaries_recent）】中爽点的实际分布情况。

输出格式：

## 爽点节拍报告
### 已出现的爽点
| 章节 | 爽点类型 | 效果评估 |
|------|---------|---------|

### ⚠️ 节奏问题
- 连续X章无爽点（第X-X章）
- 爽点过于密集（第X-X章）
- 高潮前缺少低谷铺垫

### 📋 建议
- 下一个爽点建议在第X章出现
- 建议类型：XXX
"""


def build_character_drift_user_message(char_current: str, chapter_content: str) -> str:
    return (
        f"【人物状态锁】\n{char_current or '（未维护）'}\n\n"
        f"【最新章节正文】\n{chapter_content}"
    )


def build_detail_extract_user_message(
    chapter_num: int,
    chapter_content: str,
    plot_threads_locked: str = "",
) -> str:
    locked = truncate_context_tail(plot_threads_locked) if plot_threads_locked else ""
    extra = (
        f"\n\n## 已有细节钉子（勿重复）\n{locked}"
        if locked
        else ""
    )
    return f"请从第{chapter_num}章提取细节钉子：\n\n{chapter_content}{extra}"


def build_pacing_check_user_message(world: str, summaries: str) -> str:
    return (
        f"【世界大纲】\n{world or '（未维护）'}\n\n"
        f"【已完成章节概述】\n{summaries or '（暂无概述）'}"
    )


OBSERVE_SYSTEM = """你是专业的小说编辑，负责从刚写完的章节中提取「可写入角色档案」的更新提案。
你只提案，不擅自修改任何文件；用户确认后才会写入 char_static.md 或 char_dynamic.md。

分析三件事：
1. **私人频率**：本章是否出现新的、值得长期记录的角色细节/习惯/小动作？若有，建议写入 char_static。
2. **隐藏软肋**：本章软肋是否被触碰？暴露程度是否应从「隐约可感」→「读者基本确认」等升级？
3. **char_dynamic**：关系、情绪、处境、策略等当前状态有无变化？

输出要求：
- 先用 2–5 句 Markdown 给用户阅读（说明本章观察结论）
- 然后输出**唯一一个** JSON 代码块，_fence 标记必须是 observe-json：

```observe-json
{
  "items": [
    {
      "id": "private_frequency",
      "title": "私人频率",
      "has_change": false,
      "target_file": "char_static",
      "scene": "",
      "suggestion": "",
      "proposed_text": ""
    },
    {
      "id": "soft_spot",
      "title": "隐藏软肋",
      "has_change": false,
      "target_file": "char_dynamic",
      "scene": "",
      "suggestion": "",
      "exposure_level": "",
      "proposed_text": ""
    },
    {
      "id": "char_dynamic",
      "title": "char_dynamic 状态变化",
      "has_change": false,
      "target_file": "char_dynamic",
      "changes": [],
      "proposed_text": ""
    }
  ]
}
```

规则：
- has_change=false 时其余字段可留空；无变化必须写 false
- has_change=true 时 proposed_text 必须是可直接**追加**到 target_file 的 Markdown（建议含 `###` 小标题）
- 私人频率 → target_file 固定 char_static；软肋与 dynamic → char_dynamic
- changes 数组：`{"field":"...", "from":"...", "to":"..."}`，可多条
- suggestion 每条不超过两行；语言简洁
"""


def build_observe_user_message(
    chapter_num: int,
    chapter_content: str,
    char_static: str,
    char_dynamic: str,
) -> str:
    return (
        f"请分析第{chapter_num}章，生成角色观察更新提案。\n\n"
        f"## 本章正文\n{chapter_content}\n\n"
        f"## char_static（人物锚点）\n{char_static or '（未维护）'}\n\n"
        f"## char_dynamic（当前动态）\n{char_dynamic or '（未维护）'}"
    )


POST_CHAPTER_MAINTAIN_SYSTEM = """你是章节维护助手。阅读用户提供的章节正文、角色档案与已有细节/伏笔清单后，一次性完成档案分析。

任务彼此独立、可同时完成：
1. **summary**：150–300 字章节概述
2. **observe**：角色观察提案（可写入 char_static / char_dynamic）
3. **detail_locked**：细节钉子（追加 plot_threads_locked；勿重复已有钉子）
4. **plot_new_threads**：本章新埋设的伏笔（Markdown 列表，将追加到 plot_threads_active「未回收」）
5. **plot_advanced**：本章有推进但未回收的已有伏笔（只供作者参考，Markdown 列表）
6. **plot_resolved**：本章疑似已回收的伏笔（只供作者确认，Markdown 列表）

严格只输出一个 JSON 代码块，fence 标记必须是 post-chapter-json：

```post-chapter-json
{
  "summary": "【第N章：标题】\\n核心事件：...\\n人物变化：...\\n伏笔/关键信息：...",
  "observe": {
    "summary": "2-5句角色观察说明",
    "items": [
      {
        "id": "private_frequency",
        "has_change": false,
        "target_file": "char_static",
        "proposed_text": ""
      },
      {
        "id": "soft_spot",
        "has_change": false,
        "target_file": "char_dynamic",
        "proposed_text": ""
      },
      {
        "id": "char_dynamic",
        "has_change": false,
        "target_file": "char_dynamic",
        "proposed_text": ""
      }
    ]
  },
  "detail_locked": "## 第N章新增细节钉子\\n- 【类别】描述（出处：原文简短引用）",
  "plot_new_threads": "- 【伏笔名】描述：... 埋设位置：第N章",
  "plot_advanced": "",
  "plot_resolved": ""
}
```

规则：
- summary 格式与章节概述一致；无标题时根据内容概括
- observe.items：has_change=false 时 proposed_text 留空；true 时必须为可直接追加的 Markdown（建议含 ### 小标题）
- 私人频率 → char_static；软肋与 dynamic → char_dynamic
- detail_locked：仅具体数字、专名、外貌、不可逆事件；勿与已有钉子重复
- plot_new_threads：仅本章新埋设、值得长期追踪的叙事伏笔；每条一行，无则留空字符串
- plot_advanced / plot_resolved：无则留空字符串
- 不要输出 JSON 外的任何文字
"""

QUALITY_CHECK_BUNDLE_SYSTEM = """你是严谨的小说质检编辑。对照用户提供的设定与正文，一次性完成三项检查。

1. **continuity**：连续性检查（对照世界观、人物、概述、细节钉子）
2. **character_drift**：人物一致性（对照 char_static/char_dynamic 性格锚点）
3. **repetition**：套话/重复表达（分析给定范围内的正文）

严格只输出一个 JSON 代码块，fence 标记必须是 quality-bundle-json：

```quality-bundle-json
{
  "continuity": "- [类型] 具体问题描述\\n（无问题则仅写：✅ 未发现明显矛盾）",
  "character_drift": "## 人物一致性报告\\n### ✅ 一致的部分\\n...\\n### ⚠️ 疑似漂移\\n...",
  "repetition": "## 套话检查报告\\n..."
}
```

规则：
- 各字段为完整 Markdown 报告正文，沿用单项检查的输出风格
- 不要输出 JSON 外的任何文字
"""

_CONTEXT_TAIL_CHARS = 8000


def truncate_context_tail(text: str, max_chars: int = _CONTEXT_TAIL_CHARS) -> str:
    """长上下文取尾部，避免超长输入。"""
    body = (text or "").strip()
    if len(body) <= max_chars:
        return body
    return "…（前文已截断）\n" + body[-max_chars:]


def extract_plot_active_unresolved(plot_active: str) -> str:
    """提取 plot_threads_active 中「未回收」段落。"""
    lines = (plot_active or "").splitlines()
    in_section = False
    parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## 未回收"):
            in_section = True
            continue
        if in_section and stripped.startswith("##"):
            break
        if in_section and stripped:
            parts.append(line)
    return "\n".join(parts).strip()


def build_post_chapter_maintain_user_message(
    chapter_num: int,
    chapter_content: str,
    char_static: str,
    char_dynamic: str,
    plot_threads_locked: str = "",
    plot_active_unresolved: str = "",
) -> str:
    return (
        f"请对第{chapter_num}章完成章后档案维护（概述 + 角色观察 + 细节钉子 + 新伏笔）。\n\n"
        f"## 本章正文\n{chapter_content}\n\n"
        f"## char_static（人物锚点）\n{char_static or '（未维护）'}\n\n"
        f"## char_dynamic（当前动态）\n{char_dynamic or '（未维护）'}\n\n"
        f"## 已有细节钉子（plot_threads_locked，勿重复）\n"
        f"{truncate_context_tail(plot_threads_locked) or '（暂无）'}\n\n"
        f"## 未回收伏笔（plot_threads_active）\n"
        f"{plot_active_unresolved or '（暂无）'}"
    )


def build_quality_bundle_user_message(
    world: str,
    characters: str,
    char_current: str,
    summaries: str,
    chapter_num: int,
    chapter_content: str,
    repetition_text: str,
    repetition_scope: str,
) -> str:
    return (
        f"请对第{chapter_num}章完成质检 bundle（连续性 + 人物 + 套话）。\n\n"
        f"## 套话检查范围（scope={repetition_scope}）\n{repetition_text}\n\n"
        f"## 世界观设定\n{world or '（未维护）'}\n\n"
        f"## 人物设定\n{characters or '（未维护）'}\n\n"
        f"## 人物当前状态\n{char_current or '（未维护）'}\n\n"
        f"## 章节概述（已写章节）\n{truncate_context_tail(summaries) or '（暂无）'}\n\n"
        f"## 最新章节正文（第{chapter_num}章）\n{chapter_content}"
    )


def build_bulk_summaries_user_message(
    chapter_nums: list[int],
    chapters_text: str,
    summaries_recent: str = "",
    char_static: str = "",
) -> str:
    nums = ", ".join(str(n) for n in chapter_nums)
    return (
        f"请为第 {nums} 章生成概述 bulk-summaries-json。\n\n"
        f"## char_static（参考，勿改写进概述）\n{char_static or '（未维护）'}\n\n"
        f"## 现有 summaries_recent（避免重复表述，可更新覆盖）\n"
        f"{truncate_context_tail(summaries_recent) or '（暂无）'}\n\n"
        f"## 改后正文\n{chapters_text}"
    )


def build_bulk_state_user_message(
    chapter_nums: list[int],
    chapters_text: str,
    summaries_text: str,
    char_static: str,
    char_dynamic: str,
    plot_locked: str,
    plot_active_unresolved: str,
) -> str:
    nums = ", ".join(str(n) for n in chapter_nums)
    return (
        f"请根据第 {nums} 章改后正文与概述，输出 bulk-state-json。\n\n"
        f"## 本章概述（刚生成）\n{summaries_text}\n\n"
        f"## 改后正文\n{chapters_text}\n\n"
        f"## char_static\n{char_static or '（未维护）'}\n\n"
        f"## char_dynamic（当前，请输出合并后的整份）\n{char_dynamic or '（未维护）'}\n\n"
        f"## plot_threads_locked（勿重复）\n{truncate_context_tail(plot_locked) or '（暂无）'}\n\n"
        f"## 未回收伏笔（当前）\n{plot_active_unresolved or '（暂无）'}"
    )
