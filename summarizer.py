"""概述生成与连续性检查的 prompt 模板。"""

import json
import re

WRITING_INSTRUCTION = """你是一位专业的小说写作助手。用户会提供当前章节的正文和你的写作指令。
请根据指令协助创作：续写、修改、润色、扩写或回答写作相关问题。
保持与已有世界观、人物设定和前文概述的一致性。

文风与节奏（重要）：
- 系统提示中已附带 style.md 文风锚点：必须遵守禁用词、示范句风格与节奏表。
- char_static.md 含「性格锚点」与「禁止写法」：人物本质不得漂移；char_dynamic.md 含当前状态与表层软肋。
- plot_threads_locked.md 含「已钉死的细节」：数字、日期、专名、外貌必须与清单一致，不得擅自改动。
- 快穿题材对照 world.md 中当前世界的「五点骨架」「章节节拍」「爽点设计」，一章只推进一件核心事件。
- Scene Beat 若标注【节奏档位】快/中/慢，须匹配对应段落长度与句式密度。
- Scene Beat 若标注【情绪锚点】，本场必须让读者感受到该情绪，用指定的画面/动作落地，不得用心理描写替代。
- 续写时优先：动作与对话 > 心理描写；爽点场景用短句 + 留白 + 围观反应。

【语言时代约束】（重要）
- 须对照 world.md 当前世界的时代背景；角色处于古代/历史背景时：
  - 禁止使用现代网络用语、互联网隐喻、职场黑话（如「窗口」「格局」「上线」「赛道」「复盘」「内卷」「刚需」等）
  - 禁止现代口语俚语穿越到古代角色对话与内心（如「OK」「无语」「整个人都不好了」「社死」等）
  - 叙述与对话须符合该朝代语言习惯，以白话章回体为基准：短白描、半文半白均可，不写晦涩骈文堆砌，也不写现代都市语感
- 当代/娱乐圈等现代世界：沿用 style.md 都市爽文语感，仍须遵守禁用词表

【反「文学腔」规则】
爽文的情绪冲击 ≠ 文学性的优美描写。以下是硬性要求：

1. 禁止「景物烘托情绪」套路
   ❌ 夕阳的余晖洒在她肩头，像是某种无声的告别
   ✅ 她把手机屏幕朝下扣在桌上。没有说话。

2. 禁止「内心独白式感慨」
   ❌ 她忽然明白，有些东西失去了就是失去了
   ✅ 她笑了一下，转身走了。步子很稳。

3. 爽点场景：用「外部反应」代替「内心感受」
   ❌ 她感到一阵扬眉吐气，多年的委屈在这一刻得到了释放
   ✅ 全场安静了三秒。然后有人开始鼓掌。
      林晚没有看任何人，只是低头整理了一下话筒。

4. 张力场景：用「动作的细节」制造情绪密度
   ❌ 两人之间的气氛变得微妙而紧张
   ✅ 他没有后退。她也没有。
      两个人都在等对方先开口。

5. 「留白」优于「解释」
   - 写完动作，停。不要解释这个动作意味着什么。
   - 读者自己会感受到。你解释了，情绪就泄了。

【情感表达规则】
- 禁止直接陈述角色情绪（如「她很难过」「他很感动」「她心疼」）
- 必须用动作、细节、环境、对话来传递情绪
- 示例：
  ❌ 她心里很难过
  ✅ 她站了很久，直到走廊的灯自动熄灭，才发现自己忘记动了

【爽文情绪节拍】
都市爽文的情绪冲击有固定节拍，必须遵守：

- 「蓄力」：对手轻视/施压，用对话或动作展示，不要告诉读者"对手很嚣张"
- 「引爆」：反击动作要干脆，一句话或一个动作，不要铺垫太多
- 「余震」：围观者的反应 > 主角的内心感受，让读者通过别人的眼睛感受爽点
- 「收」：主角不解释、不炫耀，做完就走或转移话题，留白制造强者感

输出规则（重要）：
- 当用户要求续写、扩写、润色、修改正文时：
  1. 第一行必须是：【章节标题】简短标题（6-12 字，概括本章或本段核心，不要书名号）
  2. 空一行后，只输出可直接写入章节的正文
  3. 不要其他解释或元评论；标题行不会进入正文段落
- 当用户只是提问、讨论设定、征求意见时：第一行必须以 [讨论]、[问答] 或 [建议] 开头，然后正常回答。"""

SUMMARY_SYSTEM = """你是一位专业的小说编辑。请阅读用户提供的章节正文，生成 150-300 字的章节概述。

严格使用以下格式（不要添加额外说明）：

【第X章：标题】
核心事件：...
人物变化：...
伏笔/关键信息：...

如果正文中没有明确标题，可根据内容概括一个简短标题。"""

CHECK_SYSTEM = """你是一位严谨的小说 continuity editor（连续性编辑）。
对照用户提供的「世界观设定」「人物设定」「章节概述」三份参考资料，扫描「最新章节正文」中的矛盾与不一致。

重点检查：
1. 人物能力、物品、外貌与设定/前文矛盾
2. char_static「性格锚点」是否被违反（人设漂移、主动示弱、过度解释等）
3. plot_threads_locked「已钉死的细节」中的数字、日期、专名是否与正文一致
4. 时间线冲突（事件顺序、年龄、季节等）
5. 人名、称谓不一致
6. 世界观规则违反（魔法体系、地理、社会规则等）
7. 与章节概述已记录事实的冲突
8. 语言时代错位：古代/历史背景下出现现代网络用语、互联网隐喻、职场黑话（如「窗口」「格局」「上线」「赛道」「复盘」「内卷」）或现代口语俚语（如「OK」「无语」「社死」）；对照 world.md 当前世界时代定位

只输出问题清单，每条一行，格式：「- [类型] 具体问题描述」
不要改写正文，不要输出无关内容。
若未发现明显矛盾，仅回复：✅ 未发现明显矛盾"""

CROSS_CHAPTER_CONTINUITY_SYSTEM = """你是一位严谨的小说 continuity editor（连续性编辑）。
对照用户提供的设定、章节概述（非全文）、细节钉子与伏笔清单，
检查指定章节范围内的逻辑是否自洽。

重点检查：
1. 时间线是否自洽（事件顺序、时间跨度、季节等）
2. 伏笔是否有头无尾（plot_threads_active 未回收与概述是否矛盾）
3. 人物位置/状态/关系是否连贯
4. 世界规则、专名、数字是否与 plot_threads_locked 及概述一致
5. 各章概述之间是否互相矛盾

只输出问题清单，每条一行，格式：「- [类型] 具体问题描述」
不要改写正文。若未发现明显矛盾，仅回复：✅ 未发现明显矛盾"""

READER_REVIEW_SYSTEM = """你是一位资深网文读者，从追读体验角度审阅给定内容。
关注：开篇是否抓人、钩子是否有效、节奏是否拖、情绪是否代入、有无出戏点、是否想继续读。

输出格式：

## 读者审阅
### ✅ 读得顺的部分
### ⚠️ 可能弃读/出戏点
- （引用或概括具体位置 + 原因）
### 📌 建议（不改设定，只谈阅读感受）
"""

EDITOR_REVIEW_SYSTEM = """你是一位商业网文编辑，从可刊稿与连载运营角度审阅。
关注：主线是否清晰、冲突是否升级、人物动机、章末钩子、爽点是否落地、是否有注水段。

输出格式：

## 编辑审阅
### ✅ 可保留的亮点
### ⚠️ 需改稿的问题
- （问题 + 建议方向，不直接改写正文）
### 📌 下一章建议（可选）
"""

OUTLINE_SYSTEM = """你是一位资深小说主编，擅长快穿/爽文叙事节奏与剧情规划。
用户会提供「世界观设定（含各世界五点骨架、章节节拍、爽点表）」「人物当前状态」「已有章节概述」「未回收伏笔清单」。
请基于这些已确立的事实，为接下来的 N 章设计剧情走向建议。

要求：
1. 必须承接已有伏笔与人物动机，不得引入与设定矛盾的新元素。
2. 对照 world.md 当前世界的章节节拍表：明确本章在 10–15 章弧线中的位置，不跳步、不塞多事件。
3. 每一章给出：章节定位、核心事件（仅一件）、情绪目标、爽点类型、冲突升级点、章末悬念钩子。
4. 快穿爽点：每章至少标注一个爽点落点（打脸/逆袭/博弈/情感/能力等），高潮章与前章铺垫呼应。
5. 至少推进或回收 1 条已有伏笔，并可埋设 1 条新伏笔。
6. 节奏张弛交替：爽点章节奏快、铺垫章须有钩子；避免连续三章同情绪。
7. 伏笔动向须引用 plot_threads 或概述中的具体条目原文或编号描述，不得凭空编造伏笔。

严格使用以下格式输出（可输出多条，按顺序排列）：

【后续第X章（建议）】
定位：本章在主线/本世界节拍中的作用
核心事件：...（仅一件）
情绪目标：...（爽/甜/揪心/燃/好奇等）
爽点类型：...（打脸/逆袭/博弈/情感/能力等）
冲突/转折：...
章末钩子：...
伏笔动向：回收【...】 / 埋设【...】

编号规则（重要）：
- X 从 1 开始，表示「紧接用户当前章节之后的第 X 条建议」，不是全书绝对章号。
- 用户当前为第 N 章、只建议下一章时，必须写【后续第1章（建议）】，禁止写【后续第2章】。
- 建议连续 3 章时依次写【后续第1章】【后续第2章】【后续第3章】。

最后附一行：
【整体节奏提示】：对这 N 章整体走向的一句话点评。"""


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
        f"## 世界观节拍参考\n{world or '（未维护）'}\n\n"
        f"## 审阅材料（{kind}）\n{body}"
    )


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


def parse_observe_proposals(reply: str) -> tuple[list[dict], str]:
    """解析 AI 回复中的 observe-json 块，返回 (items, 给用户看的 Markdown 摘要)。"""
    text = reply.strip()
    for pattern in (r"```observe-json\s*([\s\S]*?)```", r"```json\s*([\s\S]*?)```"):
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            items = data.get("items", [])
            if isinstance(items, list):
                summary = text[: match.start()].strip()
                return items, summary
        except json.JSONDecodeError:
            continue
    return [], text


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


def _normalize_maintain_payload(data: dict) -> dict:
    observe = data.get("observe")
    if isinstance(observe, list):
        observe = {"summary": "", "items": observe}
    elif not isinstance(observe, dict):
        observe = {"summary": "", "items": []}
    items = observe.get("items", [])
    if not isinstance(items, list):
        items = []
    return {
        "summary": str(data.get("summary") or "").strip(),
        "observe": {
            "summary": str(observe.get("summary") or "").strip(),
            "items": items,
        },
        "detail_locked": str(data.get("detail_locked") or "").strip(),
        "plot_new_threads": str(data.get("plot_new_threads") or "").strip(),
        "plot_advanced": str(data.get("plot_advanced") or "").strip(),
        "plot_resolved": str(data.get("plot_resolved") or "").strip(),
    }


def _normalize_quality_payload(data: dict) -> dict:
    return {
        "continuity": str(data.get("continuity") or "").strip(),
        "character_drift": str(data.get("character_drift") or "").strip(),
        "repetition": str(data.get("repetition") or "").strip(),
    }


def count_report_issues(text: str) -> int:
    """粗估报告中的问题条数（供前端展示）。"""
    body = (text or "").strip()
    if not body or "未发现明显矛盾" in body or "无明显漂移" in body:
        return 0
    count = 0
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("- [") or s.startswith("- 【") or "⚠️" in s:
            count += 1
    return count


def parse_post_chapter_maintain(reply: str) -> tuple[dict | None, str]:
    """解析章后维护 JSON。返回 (payload, 解析失败时的原文/备注)。"""
    text = (reply or "").strip()
    if not text:
        return None, ""

    for fence in ("post-chapter-json", "json"):
        match = re.search(rf"```{re.escape(fence)}\s*([\s\S]*?)```", text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict) and (
                data.get("summary")
                or data.get("observe")
                or data.get("detail_locked")
                or data.get("plot_new_threads")
            ):
                return _normalize_maintain_payload(data), ""
        except json.JSONDecodeError:
            continue

    brace = re.search(r"\{[\s\S]*\"summary\"[\s\S]*\}", text)
    if brace:
        try:
            data = json.loads(brace.group(0))
            if isinstance(data, dict):
                return _normalize_maintain_payload(data), ""
        except json.JSONDecodeError:
            pass

    return None, text


def parse_quality_bundle(reply: str) -> tuple[dict | None, str]:
    """解析质检 bundle JSON。"""
    text = (reply or "").strip()
    if not text:
        return None, ""

    for fence in ("quality-bundle-json", "json"):
        match = re.search(rf"```{re.escape(fence)}\s*([\s\S]*?)```", text, re.IGNORECASE)
        if not match:
            continue
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict) and (
                data.get("continuity")
                or data.get("character_drift")
                or data.get("repetition")
            ):
                return _normalize_quality_payload(data), ""
        except json.JSONDecodeError:
            continue

    brace = re.search(
        r"\{[\s\S]*\"continuity\"[\s\S]*\"character_drift\"[\s\S]*\}", text
    )
    if brace:
        try:
            data = json.loads(brace.group(0))
            if isinstance(data, dict):
                return _normalize_quality_payload(data), ""
        except json.JSONDecodeError:
            pass

    return None, text
