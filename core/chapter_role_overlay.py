"""章 role overlay：L1b / L2 / L4 / L5b（Track S3–S4）。"""

from __future__ import annotations

import json
import re
from typing import Any

from core import chapter_role_profiles
from core import chapter_roles
from core.plan_product import get_chapter_entry

_DIRECT_EMOTION_RE = re.compile(
    r"(她|他|我)(很|十分|特别|格外)?(愤怒|生气|难过|伤心|委屈|绝望|开心|高兴|激动)"
    r"|心中(一)?(紧|沉|酸|堵|颤)"
    r"|感到(了)?(愤怒|委屈|绝望|无力|心酸)",
)

_BRIDGE_HOOK_MARKERS = (
    "？",
    "…",
    "...",
    "却",
    "突然",
    "没想到",
    "谁知",
)

_CHANGE_MARKERS_RE = re.compile(
    r"(变了|不再|第一次|主动|开口|眼神|态度|关系|不同|松动|靠近|疏远|转折)",
)

_EXPLAIN_AFTER_TRIGGER_RE = re.compile(
    r"(原来|因为|这说明|她心里明白|她知道|这意味着|其实是因为)",
)

_CLOSURE_TONE_RE = re.compile(r"(从此|她终于明白|过上了|故事就此|全剧终)")

_VIEWPOINT_RE = re.compile(r"([她他]|我(?![们在]|是))")

ROLE_LABELS = chapter_roles.CHAPTER_ROLE_LABELS


def format_intent_final(intent: Any) -> str:
    if not isinstance(intent, dict):
        return ""
    final = intent.get("final")
    if isinstance(final, str):
        return final.strip()
    if isinstance(final, dict) and final:
        return json.dumps(final, ensure_ascii=False, indent=2)
    return str(intent.get("ai_suggest") or "").strip()


def _intent_final_dict(intent: Any) -> dict[str, Any]:
    if not isinstance(intent, dict):
        return {}
    final = intent.get("final")
    return final if isinstance(final, dict) else {}


def _text_appears_in_content(needle: str, content: str) -> bool:
    text = (needle or "").strip()
    if not text or not content:
        return False
    if text in content:
        return True
    for part in re.split(r"[，。；、\s]+", text):
        if len(part) >= 2 and part in content:
            return True
    return False


def _tail_has_hook(content: str, *, hook_plan: str = "") -> bool:
    tail = (content or "")[-400:]
    hook = (hook_plan or "").strip()
    if hook and hook in tail:
        return True
    if any(m in tail for m in _BRIDGE_HOOK_MARKERS):
        return True
    return bool(re.search(r"[？?…]\s*$", tail.strip()))


def _chapter_beat_tokens(ch: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    hook = str(ch.get("hook") or "").strip()
    if len(hook) >= 4:
        parts.append(hook)
    for scene in ch.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        beat = str(scene.get("beat") or "").strip()
        for token in re.split(r"[，。；、\n【】]", beat):
            t = token.strip()
            if len(t) >= 2:
                parts.append(t)
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:8]


def chapter_end_hook_issues(
    plan: dict,
    chapter_num: int,
    content: str,
    *,
    code: str,
    message: str,
) -> list[dict[str, Any]]:
    ch = get_chapter_entry(plan, chapter_num) or {}
    hook = str(ch.get("hook") or "").strip()
    if _tail_has_hook(content, hook_plan=hook):
        return []
    return [{
        "code": code,
        "severity": "hard",
        "message": message,
    }]


def hook_open_l1b_issues(plan: dict, chapter_num: int, content: str) -> list[dict[str, Any]]:
    ch = get_chapter_entry(plan, chapter_num) or {}
    issues: list[dict[str, Any]] = []
    issues.extend(chapter_end_hook_issues(
        plan, chapter_num, content,
        code="hook_open_no_end_hook",
        message="开篇钩子章须章末留下「想读下一章」的动力（填写 hook 或正文结尾悬念）",
    ))
    intent = ch.get("intent") if isinstance(ch.get("intent"), dict) else None
    if not format_intent_final(intent):
        issues.append({
            "code": "hook_open_intent_empty",
            "severity": "soft",
            "message": "建议在规划中确认 hook_open 梗×情绪配方（intent.final）",
        })
    head = (content or "")[:800]
    if head.strip() and not _VIEWPOINT_RE.search(head):
        issues.append({
            "code": "hook_open_no_viewpoint",
            "severity": "soft",
            "message": "开篇缺少清晰代入视角（建议出现可跟随的人物/立场）",
        })
    return issues


def paywall_l1b_issues(plan: dict, chapter_num: int, content: str) -> list[dict[str, Any]]:
    ch = get_chapter_entry(plan, chapter_num) or {}
    issues: list[dict[str, Any]] = []
    issues.extend(chapter_end_hook_issues(
        plan, chapter_num, content,
        code="paywall_no_suspense_hook",
        message="付费切割章须章末悬挂核心悬念（填写 hook 或正文结尾未决问题）",
    ))
    if not format_intent_final(ch.get("intent") if isinstance(ch.get("intent"), dict) else None):
        issues.append({
            "code": "paywall_intent_empty",
            "severity": "hard",
            "message": "请在规划中填写「付费切割」章的「付费前心理状态」",
        })
    return issues


def paid_open_continuity_issues(
    plan: dict,
    chapter_num: int,
    content: str,
) -> list[dict[str, Any]]:
    pw_num = chapter_roles.paywall_chapter_num(plan) or (chapter_num - 1)
    pw_ch = get_chapter_entry(plan, pw_num) or {}
    if chapter_roles.normalize_role(pw_ch.get("role")) != "paywall":
        return []
    head = (content or "")[:700]
    if not head.strip():
        return [{
            "code": "paid_open_empty",
            "severity": "hard",
            "message": "付费首章正文为空",
        }]
    pw_hook = str(pw_ch.get("hook") or "").strip()
    pw_intent = format_intent_final(
        pw_ch.get("intent") if isinstance(pw_ch.get("intent"), dict) else None,
    )
    connected = False
    if pw_hook and pw_hook[: min(20, len(pw_hook))] in head:
        connected = True
    if pw_intent and _text_appears_in_content(pw_intent[:40], head):
        connected = True
    for kw in _chapter_beat_tokens(pw_ch)[:5]:
        if kw in head:
            connected = True
            break
    if connected:
        return []
    return [{
        "code": "paid_open_no_continuity",
        "severity": "hard",
        "message": "「付费首章」开头须直接承接「付费切割」章的悬念或钩子",
    }]


def bridge_change_visibility_issues(
    plan: dict,
    chapter_num: int,
    content: str,
) -> list[dict[str, Any]]:
    ch = get_chapter_entry(plan, chapter_num) or {}
    from core import intent_final as intent_final_mod

    final_raw = ch.get("intent", {}).get("final") if isinstance(ch.get("intent"), dict) else None
    micro_changed = intent_final_mod.bridge_micro_changed(final_raw)
    micro_who = intent_final_mod.bridge_micro_who(final_raw)
    if micro_changed and not _text_appears_in_content(micro_changed, content):
        return [{
            "code": "bridge_micro_change_missing",
            "severity": "hard",
            "message": "过渡章正文未呈现规划中的人物/关系变化（micro_change）",
        }]
    if micro_who and not _text_appears_in_content(micro_who, content):
        return [{
            "code": "bridge_micro_who_missing",
            "severity": "soft",
            "message": f"正文未明显出现变化主体：{micro_who}",
        }]
    if not micro_changed and not _CHANGE_MARKERS_RE.search(content or ""):
        return [{
            "code": "bridge_no_visible_change",
            "severity": "hard",
            "message": "过渡章须至少一处可感知的人物/关系变化，避免等同注水",
        }]
    return []


def escalation_aftermath_issues(
    plan: dict,
    chapter_num: int,
    content: str,
) -> list[dict[str, Any]]:
    ch = get_chapter_entry(plan, chapter_num) or {}
    from core import intent_final as intent_final_mod

    final_raw = ch.get("intent", {}).get("final") if isinstance(ch.get("intent"), dict) else None
    trigger = intent_final_mod.escalation_trigger(final_raw)
    if not trigger or not content:
        return []
    idx = content.find(trigger[: min(12, len(trigger))])
    if idx < 0:
        return []
    after = content[idx + len(trigger): idx + len(trigger) + 350]
    if _EXPLAIN_AFTER_TRIGGER_RE.search(after):
        return [{
            "code": "escalation_over_explained",
            "severity": "soft",
            "message": "爆发点后出现解释性句子，可能把读者从情绪里拉出来",
        }]
    return []


def finale_l1b_issues(plan: dict, chapter_num: int, content: str) -> list[dict[str, Any]]:
    ch = get_chapter_entry(plan, chapter_num) or {}
    from core import intent_final as intent_final_mod

    final_raw = ch.get("intent", {}).get("final") if isinstance(ch.get("intent"), dict) else None
    issues: list[dict[str, Any]] = []

    gap = intent_final_mod.finale_opening_gap(final_raw)
    if not gap:
        ch1 = get_chapter_entry(plan, 1) or {}
        if chapter_roles.normalize_role(ch1.get("role")) == "hook_open":
            gap = format_intent_final(ch1.get("intent"))
    if gap and not _text_appears_in_content(gap[:40], content):
        issues.append({
            "code": "finale_opening_gap_weak",
            "severity": "hard",
            "message": "完结章须回扣开篇 hook_open 缺口/配方（首尾呼应）",
        })

    freeze = intent_final_mod.finale_freeze_what(final_raw)
    if not freeze:
        issues.append({
            "code": "finale_freeze_missing",
            "severity": "hard",
            "message": "完结章须在规划中填写关系定格画面（freeze_frame）",
        })
    elif not _text_appears_in_content(freeze[:40], content):
        issues.append({
            "code": "finale_freeze_weak",
            "severity": "hard",
            "message": "正文未明显呈现规划中的定格画面",
        })

    tail = (content or "")[-250:]
    if _CLOSURE_TONE_RE.search(tail):
        issues.append({
            "code": "finale_over_closed",
            "severity": "soft",
            "message": "结尾收束句式偏多，建议留白余韵",
        })
    return issues


def escalation_intent_issues(
    plan: dict,
    chapter_num: int,
    content: str,
) -> list[dict[str, Any]]:
    """escalation L1b：debt/trigger 与正文对齐（hard 阻断）。"""
    ch = get_chapter_entry(plan, chapter_num) or {}
    if chapter_roles.normalize_role(ch.get("role")) != "escalation":
        return []
    from core import intent_final as intent_final_mod

    final_raw = ch.get("intent", {}).get("final") if isinstance(ch.get("intent"), dict) else None
    debt = intent_final_mod.escalation_debt(final_raw)
    trigger = intent_final_mod.escalation_trigger(final_raw)
    issues: list[dict[str, Any]] = []
    if not debt and not trigger:
        issues.append({
            "code": "escalation_intent_empty",
            "severity": "hard",
            "message": "escalation 须在规划中填写 intent.final.debt 与 trigger",
        })
        return issues
    if debt and not _text_appears_in_content(debt, content):
        issues.append({
            "code": "escalation_debt_weak",
            "severity": "hard",
            "message": "正文未明显承接 intent.final.debt（情感债）",
        })
    if trigger and not _text_appears_in_content(trigger, content):
        issues.append({
            "code": "escalation_trigger_weak",
            "severity": "hard",
            "message": "正文未明显呈现 intent.final.trigger（小而精准的引爆载体）",
        })
    if trigger and chapter_roles._trigger_too_big(trigger, debt):
        issues.append({
            "code": "escalation_trigger_too_big",
            "severity": "soft",
            "message": "trigger 疑似过大事件，建议比 debt 更小更精准",
        })
    return issues


def buildup_emotion_word_issues(content: str) -> list[dict[str, Any]]:
    hits = _DIRECT_EMOTION_RE.findall(content or "")
    if len(hits) >= 4:
        return [{
            "code": "buildup_emotion_words",
            "severity": "soft",
            "message": f"铺垫章直接情绪描写偏多（约 {len(hits)} 处），建议用条件载体代替",
        }]
    return []


def bridge_hook_issues(plan: dict, chapter_num: int, content: str) -> list[dict[str, Any]]:
    issues = chapter_end_hook_issues(
        plan, chapter_num, content,
        code="bridge_no_hook",
        message="过渡章须章末新悬念：请填写 hook 或在正文结尾留下悬念",
    )
    issues.extend(bridge_change_visibility_issues(plan, chapter_num, content))
    return issues


def finale_opening_gap_issues(plan: dict, chapter_num: int, content: str) -> list[dict[str, Any]]:
    return finale_l1b_issues(plan, chapter_num, content)


def _cross_chapter_hints(plan: dict, chapter_num: int, role: str) -> list[str]:
    hints: list[str] = []
    if role == "finale":
        ch1 = get_chapter_entry(plan, 1) or {}
        if chapter_roles.normalize_role(ch1.get("role")) == "hook_open":
            gap = format_intent_final(ch1.get("intent"))
            if gap:
                hints.append(f"- **首尾呼应**：开篇 hook_open 缺口/配方 → {gap}")
    if role == "bridge":
        next_ch = get_chapter_entry(plan, chapter_num + 1) or {}
        if chapter_roles.normalize_role(next_ch.get("role")) == "buildup":
            seed = format_intent_final(next_ch.get("intent"))
            if seed:
                hints.append(f"- **next_seed 对齐**：下一章 buildup 条件 → {seed}")
    if role == "escalation":
        hints.append("- **拉弓**：本章为 paywall 前最后一箭，trigger 须小而精准")
    return hints


def chapter_review_context(plan: dict, chapter_num: int) -> dict[str, Any]:
    """运行时上下文：role、paywall_side、intent（paid_open 读 paywall）。"""
    role = chapter_roles.chapter_role(plan, chapter_num)
    pw_num = chapter_roles.paywall_chapter_num(plan)
    side = chapter_roles.paywall_side(chapter_num, pw_num)
    ch = get_chapter_entry(plan, chapter_num) or {}
    intent = ch.get("intent") if isinstance(ch.get("intent"), dict) else None
    final_text = format_intent_final(intent)

    paywall_intent_text = ""
    if pw_num and pw_num > 0:
        pw_ch = get_chapter_entry(plan, pw_num) or {}
        paywall_intent_text = format_intent_final(
            pw_ch.get("intent") if isinstance(pw_ch.get("intent"), dict) else None,
        )

    if role == "paid_open" and paywall_intent_text:
        final_text = paywall_intent_text

    return {
        "chapter_num": chapter_num,
        "role": role,
        "role_label": ROLE_LABELS.get(role or "", role or ""),
        "paywall_side": side,
        "paywall_chapter": pw_num,
        "intent": intent,
        "intent_final": final_text,
        "paywall_intent_final": paywall_intent_text,
        "l5b_priority": chapter_role_profiles.role_l5b_priority(role or ""),
    }


def l4_overlay_block(plan: dict, chapter_num: int) -> str:
    ctx = chapter_review_context(plan, chapter_num)
    role = ctx.get("role")
    overlay_text = chapter_role_profiles.role_l4(role or "") if role else ""
    if not role or not overlay_text:
        return ""
    lines = [
        "## 章级叙事角色 overlay（叠加 plan.review_criteria，非替代）",
        "",
        f"- **角色**：`{role}`（{ctx.get('role_label') or role}）",
    ]
    side = ctx.get("paywall_side")
    if side:
        lines.append(f"- **付费侧**：{side}（paywall 章 = {ctx.get('paywall_chapter')}）")
    final_text = str(ctx.get("intent_final") or "").strip()
    if final_text and role != "paid_open":
        lines.append(f"- **作者确认意图**：{final_text}")
    elif role == "paid_open" and ctx.get("paywall_intent_final"):
        lines.append(f"- **对照 paywall 意图**：{ctx['paywall_intent_final']}")
    cross = _cross_chapter_hints(plan, chapter_num, role)
    if cross:
        lines.append("")
        lines.extend(cross)
    lines.append("")
    lines.append(overlay_text)
    return "\n".join(lines).strip()


def l1b_params(plan: dict, chapter_num: int) -> dict[str, Any]:
    ctx = chapter_review_context(plan, chapter_num)
    role = ctx.get("role")
    base = dict(chapter_role_profiles.role_l1b(role or ""))
    base["role"] = role
    base["paywall_side"] = ctx.get("paywall_side")
    return base


def l1b_extra_issues(plan: dict, chapter_num: int, content: str) -> list[dict[str, Any]]:
    params = l1b_params(plan, chapter_num)
    role = params.get("role")
    issues: list[dict[str, Any]] = []
    if params.get("check_escalation_intent"):
        issues.extend(escalation_intent_issues(plan, chapter_num, content))
        issues.extend(escalation_aftermath_issues(plan, chapter_num, content))
    if role == "hook_open":
        issues.extend(hook_open_l1b_issues(plan, chapter_num, content))
    elif role == "buildup":
        issues.extend(buildup_emotion_word_issues(content))
    elif role == "paywall":
        issues.extend(paywall_l1b_issues(plan, chapter_num, content))
    elif role == "paid_open":
        issues.extend(paid_open_continuity_issues(plan, chapter_num, content))
    elif role == "bridge":
        issues.extend(bridge_hook_issues(plan, chapter_num, content))
    elif role == "finale":
        issues.extend(finale_l1b_issues(plan, chapter_num, content))
    return issues


def l2_reader_user_prompt(plan: dict, chapter_num: int, content: str) -> str:
    ctx = chapter_review_context(plan, chapter_num)
    role = str(ctx.get("role") or "")
    focus = chapter_role_profiles.role_l2_focus(role) or "节奏、代入感与章尾钩子"
    final_text = str(ctx.get("intent_final") or "").strip()
    lines = [
        f"请从资深网文读者视角审阅第 {chapter_num} 章。",
        f"- **叙事角色**：{role}（{ctx.get('role_label') or role}）",
        f"- **本章关注点**：{focus}",
    ]
    if final_text:
        lines.append(f"- **作者确认意图**：{final_text}")
    side = ctx.get("paywall_side")
    if side:
        lines.append(f"- **付费侧**：{side}")
    questions = chapter_role_profiles.role_l2_questions(role)
    if questions:
        lines.append("- **读者模拟问题**：")
        lines.extend(f"  - {q}" for q in questions)
    lines.extend([
        "",
        "请评估：读者是否想继续读？章尾弃读风险（高/中/低）？",
        "",
        "--- 正文 ---",
        (content or "").strip()[:12000],
    ])
    return "\n".join(lines)


def l2_reader_thresholds(plan: dict, chapter_num: int) -> dict[str, float]:
    ctx = chapter_review_context(plan, chapter_num)
    role = ctx.get("role")
    return chapter_role_profiles.role_l2_thresholds(role or "")


def l5b_rhythm_priority(plan: dict, chapter_num: int) -> str:
    ctx = chapter_review_context(plan, chapter_num)
    return str(ctx.get("l5b_priority") or "medium")


def l5b_mandatory(plan: dict, chapter_num: int) -> bool:
    """high / highest 角色：L5b 预警不可一键跳过（v1.0）。"""
    return l5b_rhythm_priority(plan, chapter_num) in ("high", "highest")


def review_context_meta(plan: dict, chapter_num: int) -> dict[str, Any]:
    """API 响应附带的 role 上下文（不含长 overlay 文本）。"""
    ctx = chapter_review_context(plan, chapter_num)
    out: dict[str, Any] = {"chapter_num": chapter_num}
    if ctx.get("role"):
        out["chapter_role"] = ctx["role"]
    if ctx.get("role_label"):
        out["role_label"] = ctx["role_label"]
    if ctx.get("paywall_side"):
        out["paywall_side"] = ctx["paywall_side"]
    if ctx.get("paywall_chapter") is not None:
        out["paywall_chapter"] = ctx["paywall_chapter"]
    if ctx.get("l5b_priority"):
        out["l5b_priority"] = ctx["l5b_priority"]
    out["l5b_mandatory"] = l5b_mandatory(plan, chapter_num)
    return out


def all_role_profiles() -> dict[str, dict[str, Any]]:
    """8 role 完整 profile 摘要（供测试/文档对齐）。"""
    return {
        role: chapter_role_profiles.profile_summary(role)
        for role in chapter_roles.CHAPTER_ROLE_ORDER
    }
