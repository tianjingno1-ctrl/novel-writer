"""创作工坊：回复解析与常量（无路径、无 API）。"""

from __future__ import annotations

import json

from core.data import novel_data

WORKSHOP_DRAFT_SEP = "---DRAFT---"
WORKSHOP_REPLY_SEP = "---REPLY---"
WORKSHOP_EXTRACT_SEP = "---EXTRACT---"
WORKSHOP_END_SEP = "---END---"

WORKSHOP_SYSTEM_PROMPTS: dict[str, str] = {
    "world": (
        "你是一个故事创作助手，当前侧重世界观设计。用户会描述他们的故事世界，你需要：\n"
        "1. 用自然语言回应，鼓励用户继续描述\n"
        "2. 在 EXTRACT 中全量整理世界观、人物与章节计划（每轮输出完整内容）"
    ),
    "characters": (
        "你是一个故事创作助手，当前侧重人物设计。用户会描述故事人物，你需要：\n"
        "1. 用自然语言回应，帮用户深化人物设计\n"
        "2. 在 EXTRACT 中全量整理世界观、人物与章节计划（每轮输出完整内容）"
    ),
    "style": (
        "你是一个故事创作助手，当前侧重写作风格。用户会描述目标风格，你需要：\n"
        "1. 用自然语言回应，帮用户明确风格定位\n"
        "2. 在 EXTRACT 中全量整理世界观、人物与章节计划（每轮输出完整内容）"
    ),
}

WORKSHOP_FORMAT_SUFFIX = (
    "\n\n每次回复必须严格按以下格式输出，不得省略任何分隔符：\n\n"
    f"{WORKSHOP_REPLY_SEP}\n"
    "（你对用户说的话，自然对话语气）\n"
    f"{WORKSHOP_EXTRACT_SEP}\n"
    '{"world": "当前整理的世界观设定（没有则空字符串）", '
    '"characters": "当前整理的人物设定（没有则空字符串）", '
    '"beats": [{"chapter": 1, "title": "章节标题", "beat": "这章要写什么"}]}\n'
    f"{WORKSHOP_END_SEP}\n\n"
    "注意：\n"
    "- EXTRACT 是你对整个对话内容的全量整理，每轮都要输出完整内容\n"
    "- beats 没有则输出空数组 []\n"
    "- beats 每项用 chapter（章号），勿用 chapter_index；写入 plan 时每条 beat 对应 scenes[] 一项：\n"
    "  title←beat.title, beat←beat.beat, pace=\"中\", emotion_anchor={}, done=false；"
    "beat.chapter 决定归入 plan.chapters[章号]\n"
    "- 严格输出合法JSON，不加注释"
)

WORKSHOP_MODULE_FILES: dict[str, str] = {
    "world": "world",
    "characters": "characters",
    "style": "style",
}

WORKSHOP_WRITE_KEY_MAP: dict[str, str] = {
    "世界观设定": "world",
    "人物设定": "characters",
    "写作风格": "style",
    "world": "world",
    "characters": "characters",
    "style": "style",
}


def normalize_workshop_beats(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ch = novel_data._workshop_beat_chapter_num(item)
        if ch is None:
            continue
        out.append({
            "chapter": ch,
            "title": str(item.get("title") or "").strip(),
            "beat": str(item.get("beat") or "").strip(),
        })
    return out


def _empty_workshop_extract() -> dict:
    return {"world": "", "characters": "", "beats": []}


def parse_workshop_response(text: str) -> tuple[str, dict]:
    """分离对话回复与结构化 extract（world/characters/beats）。"""
    raw = (text or "").strip()
    empty = _empty_workshop_extract()

    if WORKSHOP_REPLY_SEP in raw and WORKSHOP_EXTRACT_SEP in raw:
        try:
            after_reply = raw.split(WORKSHOP_REPLY_SEP, 1)[1]
            reply_part, extract_part = after_reply.split(WORKSHOP_EXTRACT_SEP, 1)
            reply = reply_part.strip()
            json_part = extract_part.split(WORKSHOP_END_SEP, 1)[0].strip()
            data = json.loads(json_part)
            if not isinstance(data, dict):
                data = {}
            extract = {
                "world": str(data.get("world") or ""),
                "characters": str(data.get("characters") or ""),
                "beats": normalize_workshop_beats(data.get("beats")),
            }
            return reply, extract
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    if WORKSHOP_DRAFT_SEP in raw:
        reply, draft = raw.split(WORKSHOP_DRAFT_SEP, 1)
        return reply.strip(), {"world": draft.strip(), "characters": "", "beats": []}

    return raw, empty
