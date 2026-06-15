"""章级叙事角色（chapter.role）契约与 A9 序列校验。"""

from __future__ import annotations

import re
from typing import Any, Literal

CHAPTER_ROLES = frozenset({
    "hook_open",
    "buildup",
    "escalation",
    "paywall",
    "paid_open",
    "climax",
    "bridge",
    "finale",
})

PaywallSide = Literal["pre", "post"]
Severity = Literal["error", "warn"]

CHAPTER_ROLE_LABELS: dict[str, str] = {
    "hook_open": "开篇钩子",
    "buildup": "铺垫",
    "escalation": "爆发",
    "paywall": "付费切割",
    "paid_open": "付费首章",
    "climax": "高潮",
    "bridge": "过渡",
    "finale": "完结",
}

CHAPTER_ROLE_ORDER: tuple[str, ...] = tuple(CHAPTER_ROLE_LABELS)

PAYWALL_POSITION_MIN = 0.40
PAYWALL_POSITION_MAX = 0.55


def normalize_prefill_chapter(ch: dict[str, Any]) -> dict[str, Any]:
    """A8 预填章：归一 role + intent 形状供前端 A9 确认。"""
    if not isinstance(ch, dict):
        return ch
    out = dict(ch)
    role = normalize_role(out.get("role"))
    if not role:
        return out
    out["role"] = role
    if role == "paid_open":
        out.pop("intent", None)
        return out
    intent_raw = out.get("intent")
    if not isinstance(intent_raw, dict):
        suggest = str(
            out.pop("intent_ai_suggest", None)
            or out.get("ai_suggest")
            or ""
        ).strip()
        intent_raw = {"ai_suggest": suggest}
    out["intent"] = normalize_intent(role, intent_raw)
    return out


def normalize_prefill_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    options = payload.get("options")
    if not isinstance(options, list):
        return payload
    out = dict(payload)
    normalized_options: list[dict[str, Any]] = []
    for opt in options:
        if not isinstance(opt, dict):
            continue
        opt_copy = dict(opt)
        chapters = opt_copy.get("chapters")
        if isinstance(chapters, list):
            opt_copy["chapters"] = [
                normalize_prefill_chapter(ch)
                for ch in chapters
                if isinstance(ch, dict)
            ]
        normalized_options.append(opt_copy)
    out["options"] = normalized_options
    return out


def normalize_role(role: Any) -> str | None:
    if role is None:
        return None
    raw = str(role).strip().lower()
    return raw if raw in CHAPTER_ROLES else None


def normalize_intent(role: str, intent: Any) -> dict[str, Any] | None:
    from core import intent_final as intent_final_mod

    if role == "paid_open":
        return None
    if not isinstance(intent, dict):
        return {"kind": role, "ai_suggest": "", "final": {}}
    kind = normalize_role(intent.get("kind")) or role
    final = intent.get("final")
    if final is None:
        final = {}
    return {
        "kind": kind,
        "ai_suggest": str(intent.get("ai_suggest") or "").strip(),
        "final": intent_final_mod.normalize_intent_final(kind, final),
    }


def chapter_role(plan: dict, chapter_num: int) -> str | None:
    ch = (plan.get("chapters") or {}).get(str(chapter_num))
    if not isinstance(ch, dict):
        return None
    return normalize_role(ch.get("role"))


def paywall_chapter_num(plan: dict) -> int | None:
    meta_pw = (plan.get("meta") or {}).get("paywall_chapter")
    if meta_pw is not None:
        try:
            n = int(meta_pw)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    nums: list[int] = []
    for key, ch in (plan.get("chapters") or {}).items():
        if not isinstance(ch, dict):
            continue
        if normalize_role(ch.get("role")) != "paywall":
            continue
        try:
            nums.append(int(key))
        except (TypeError, ValueError):
            continue
    if len(nums) == 1:
        return nums[0]
    return None


def paywall_side(chapter_num: int, paywall_num: int | None) -> PaywallSide | None:
    if paywall_num is None or chapter_num < 1:
        return None
    return "pre" if chapter_num <= paywall_num else "post"


def _chapter_nums(plan: dict) -> list[int]:
    nums: list[int] = []
    for key in (plan.get("chapters") or {}):
        try:
            nums.append(int(key))
        except (TypeError, ValueError):
            continue
    return sorted(nums)


def roles_engaged(plan: dict) -> bool:
    meta = plan.get("meta") if isinstance(plan.get("meta"), dict) else {}
    if meta.get("paywall_chapter") is not None:
        return True
    for ch in (plan.get("chapters") or {}).values():
        if isinstance(ch, dict) and normalize_role(ch.get("role")):
            return True
    return False


def _intent_final_raw(ch: dict[str, Any]) -> Any:
    intent = ch.get("intent")
    if not isinstance(intent, dict):
        return None
    return intent.get("final")


def _intent_final_dict(ch: dict[str, Any]) -> dict[str, Any]:
    final = _intent_final_raw(ch)
    return final if isinstance(final, dict) else {}


def _buildup_fingerprint(final: Any) -> str:
    if isinstance(final, dict):
        cond = str(final.get("conditions") or "").strip().lower()
        emo = str(final.get("emotions") or "").strip().lower()
        if cond or emo:
            return f"{cond}|{emo}"
    if isinstance(final, str):
        return final.strip().lower()
    return ""


_BIG_TRIGGER_MARKERS = (
    "大战", "爆炸", "车祸", "死亡", "战争", "破产", "火灾", "谋杀",
    "枪杀", "收购", "婚礼", "离婚", "绑架", "地震", "海啸",
)


def _trigger_too_big(trigger: str, debt: str) -> bool:
    trig = (trigger or "").strip()
    if not trig:
        return False
    if any(k in trig for k in _BIG_TRIGGER_MARKERS):
        return True
    debt_len = len((debt or "").strip())
    return len(trig) > max(24, debt_len * 2 + 12) and debt_len < 10


def _semantic_overlap(a: str, b: str) -> bool:
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    tokens_a = {t for t in re.split(r"[，。；、\s→]+", left) if len(t) >= 2}
    tokens_b = {t for t in re.split(r"[，。；、\s→]+", right) if len(t) >= 2}
    return bool(tokens_a & tokens_b)


def _issue(
    code: str,
    severity: Severity,
    message: str,
    *,
    chapter_num: int | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if chapter_num is not None:
        out["chapter_num"] = chapter_num
    return out


def validate_plan_sequence(
    plan: dict,
    *,
    book_type: str = "short",
) -> list[dict[str, Any]]:
    """A9 章序列校验：error 阻断采纳，warn 仅提示。"""
    issues: list[dict[str, Any]] = []
    nums = _chapter_nums(plan)
    if not nums:
        return issues

    bt = str(book_type or "short").strip().lower()
    engaged = roles_engaged(plan)

    for num in nums:
        ch = (plan.get("chapters") or {}).get(str(num))
        if not isinstance(ch, dict):
            continue
        raw_role = ch.get("role")
        if raw_role is None or str(raw_role).strip() == "":
            continue
        role = normalize_role(raw_role)
        if not role:
            issues.append(_issue(
                "invalid_role",
                "error",
                f"第 {num} 章 role 无效：{raw_role}",
                chapter_num=num,
            ))

    if not engaged:
        return issues

    first, last = nums[0], nums[-1]
    anchor_severity: Severity = "error" if bt == "short" else "warn"

    if chapter_role(plan, first) != "hook_open":
        issues.append(_issue(
            "anchor_ch1_not_hook_open",
            anchor_severity,
            f"第 1 章应为 hook_open（当前：{chapter_role(plan, first) or '未设'}）",
            chapter_num=first,
        ))
    if chapter_role(plan, last) != "finale":
        issues.append(_issue(
            "anchor_last_not_finale",
            anchor_severity,
            f"最后一章（第 {last} 章）应为 finale（当前：{chapter_role(plan, last) or '未设'}）",
            chapter_num=last,
        ))

    if bt != "short":
        return issues

    paywall_nums = [
        n for n in nums if chapter_role(plan, n) == "paywall"
    ]
    paid_open_nums = [
        n for n in nums if chapter_role(plan, n) == "paid_open"
    ]

    if len(paywall_nums) != 1:
        issues.append(_issue(
            "paywall_count",
            "error",
            f"短篇须恰好 1 章「付费切割」（当前 {len(paywall_nums)} 章）",
        ))
    if len(paid_open_nums) != 1:
        issues.append(_issue(
            "paid_open_count",
            "error",
            f"短篇须恰好 1 章「付费首章」（当前 {len(paid_open_nums)} 章）",
        ))

    pw = paywall_nums[0] if len(paywall_nums) == 1 else None
    po = paid_open_nums[0] if len(paid_open_nums) == 1 else None

    if pw is not None:
        if pw == first or pw == last:
            issues.append(_issue(
                "paywall_position_edge",
                "error",
                f"「付费切割」不能是第 1 章或最后一章（当前第 {pw} 章）",
                chapter_num=pw,
            ))
        total = last
        ratio = pw / total if total else 0
        if ratio < PAYWALL_POSITION_MIN or ratio > PAYWALL_POSITION_MAX:
            pct = int(round(ratio * 100))
            issues.append(_issue(
                "paywall_position_range",
                "warn",
                f"「付费切割」建议位于全书 40%～55%（当前约 {pct}%，第 {pw}/{total} 章）",
                chapter_num=pw,
            ))
        meta_pw = paywall_chapter_num(plan)
        if meta_pw is not None and meta_pw != pw:
            issues.append(_issue(
                "meta_paywall_mismatch",
                "warn",
                f"规划的付费章号（{meta_pw}）与「付费切割」章号（{pw}）不一致",
                chapter_num=pw,
            ))

    if pw is not None and po is not None and po != pw + 1:
        issues.append(_issue(
            "paid_open_not_after_paywall",
            "error",
            f"「付费首章」须紧接「付费切割」下一章（付费切割=第 {pw} 章，付费首章=第 {po} 章）",
            chapter_num=po,
        ))

    if pw is not None and pw > 1:
        pre_nums = [n for n in nums if n < pw]
        buildup_nums = [n for n in pre_nums if chapter_role(plan, n) == "buildup"]
        escalation_nums = [n for n in pre_nums if chapter_role(plan, n) == "escalation"]

        if len(buildup_nums) < 2 and pw >= 4:
            issues.append(_issue(
                "bow_too_few_buildup",
                "warn",
                f"拉弓：paywall 前建议至少 2 章 buildup（当前 {len(buildup_nums)} 章）",
                chapter_num=pw,
            ))
        if not escalation_nums:
            issues.append(_issue(
                "bow_no_escalation",
                "warn",
                "拉弓：paywall 前建议至少 1 章 escalation",
                chapter_num=pw,
            ))
        elif pw - 1 in pre_nums and chapter_role(plan, pw - 1) != "escalation":
            issues.append(_issue(
                "bow_last_pre_not_escalation",
                "warn",
                f"拉弓：paywall 前一章（第 {pw - 1} 章）建议为 escalation",
                chapter_num=pw - 1,
            ))

        if len(buildup_nums) >= 2:
            fps = [
                _buildup_fingerprint(_intent_final_raw(
                    (plan.get("chapters") or {}).get(str(n)) or {},
                ))
                for n in buildup_nums
            ]
            nonempty = [fp for fp in fps if fp]
            if not nonempty:
                issues.append(_issue(
                    "bow_buildup_no_intent",
                    "warn",
                    "拉弓·压力梯度：paywall 前 buildup 章均未填写 conditions/emotions 意图",
                    chapter_num=buildup_nums[0],
                ))
            elif len(set(nonempty)) == 1:
                issues.append(_issue(
                    "bow_flat_buildup",
                    "warn",
                    "拉弓·压力梯度：多个 buildup 意图相同，情感积累可能平铺",
                    chapter_num=buildup_nums[-1],
                ))

        esc_num: int | None = None
        if pw - 1 in pre_nums and chapter_role(plan, pw - 1) == "escalation":
            esc_num = pw - 1
        elif escalation_nums:
            esc_num = escalation_nums[-1]

        if esc_num is not None:
            esc_ch = (plan.get("chapters") or {}).get(str(esc_num))
            if isinstance(esc_ch, dict):
                from core import intent_final as intent_final_mod

                debt = intent_final_mod.escalation_debt(_intent_final_raw(esc_ch))
                trigger = intent_final_mod.escalation_trigger(_intent_final_raw(esc_ch))
                if not debt:
                    issues.append(_issue(
                        "bow_escalation_no_debt",
                        "warn",
                        "拉弓·临界点：escalation 建议填写 intent.final.debt（一触即发的情感债）",
                        chapter_num=esc_num,
                    ))
                if not trigger:
                    issues.append(_issue(
                        "bow_escalation_no_trigger",
                        "warn",
                        "拉弓·临界点：escalation 建议填写 intent.final.trigger（小而精准的引爆载体）",
                        chapter_num=esc_num,
                    ))
                elif _trigger_too_big(trigger, debt):
                    issues.append(_issue(
                        "bow_trigger_too_big",
                        "warn",
                        "拉弓·最后一根稻草：trigger 疑似过大事件，建议比 debt 更小更精准",
                        chapter_num=esc_num,
                    ))

    for num in nums:
        if chapter_role(plan, num) != "bridge":
            continue
        next_buildup: int | None = None
        for n in range(num + 1, last + 1):
            if chapter_role(plan, n) == "buildup":
                next_buildup = n
                break
        if next_buildup is None:
            continue
        bridge_ch = (plan.get("chapters") or {}).get(str(num))
        next_ch = (plan.get("chapters") or {}).get(str(next_buildup))
        if not isinstance(bridge_ch, dict) or not isinstance(next_ch, dict):
            continue
        from core import intent_final as intent_final_mod

        seed = intent_final_mod.bridge_next_seed(_intent_final_raw(bridge_ch))
        conditions = intent_final_mod.buildup_conditions(_intent_final_raw(next_ch))
        if seed and not conditions:
            issues.append(_issue(
                "bridge_next_buildup_no_conditions",
                "warn",
                f"bridge（第 {num} 章）已填 next_seed，但下一 buildup（第 {next_buildup} 章）缺 conditions",
                chapter_num=next_buildup,
            ))
        elif seed and conditions and not _semantic_overlap(seed, conditions):
            issues.append(_issue(
                "bridge_next_seed_mismatch",
                "warn",
                f"bridge.next_seed 与第 {next_buildup} 章 buildup.conditions 语义未对齐",
                chapter_num=num,
            ))

    if chapter_role(plan, first) == "hook_open" and chapter_role(plan, last) == "finale":
        h1_ch = (plan.get("chapters") or {}).get(str(first))
        fin_ch = (plan.get("chapters") or {}).get(str(last))
        if isinstance(h1_ch, dict) and isinstance(fin_ch, dict):
            from core import intent_final as intent_final_mod

            hook_ref = intent_final_mod.hook_open_ref(_intent_final_raw(h1_ch))
            gap = intent_final_mod.finale_opening_gap(_intent_final_raw(fin_ch))
            if gap and hook_ref and not _semantic_overlap(gap, hook_ref):
                issues.append(_issue(
                    "finale_opening_gap_mismatch",
                    "warn",
                    "finale.opening_gap 与第 1 章 hook_open 缺口/配方语义未呼应",
                    chapter_num=last,
                ))
            elif gap and not hook_ref:
                issues.append(_issue(
                    "hook_open_gap_empty",
                    "warn",
                    "finale 已填 opening_gap，但第 1 章 hook_open 意图为空，首尾难以闭环",
                    chapter_num=first,
                ))

    for num in nums:
        if chapter_role(plan, num) != "escalation":
            continue
        esc_ch = (plan.get("chapters") or {}).get(str(num))
        if not isinstance(esc_ch, dict):
            continue
        from core import intent_final as intent_final_mod

        debt = intent_final_mod.escalation_debt(_intent_final_raw(esc_ch))
        if not debt:
            continue
        buildup_emotions: list[str] = []
        for n in nums:
            if n >= num:
                break
            if chapter_role(plan, n) != "buildup":
                continue
            prev = (plan.get("chapters") or {}).get(str(n))
            if not isinstance(prev, dict):
                continue
            emo = intent_final_mod.buildup_emotions(_intent_final_raw(prev))
            if emo:
                buildup_emotions.append(emo)
        if not buildup_emotions:
            issues.append(_issue(
                "escalation_debt_no_buildup",
                "warn",
                f"第 {num} 章 escalation 有 debt，但此前无 buildup.emotions 可回溯",
                chapter_num=num,
            ))
        elif not any(_semantic_overlap(debt, emo) for emo in buildup_emotions):
            issues.append(_issue(
                "escalation_debt_untraceable",
                "warn",
                f"第 {num} 章 escalation.debt 与前面 buildup.emotions 语义未对齐",
                chapter_num=num,
            ))

    if chapter_role(plan, last) == "finale":
        fin_ch = (plan.get("chapters") or {}).get(str(last))
        if isinstance(fin_ch, dict):
            from core import intent_final as intent_final_mod

            final_raw = _intent_final_raw(fin_ch)
            if not intent_final_mod.finale_freeze_what(final_raw):
                issues.append(_issue(
                    "finale_freeze_plan_missing",
                    "warn",
                    "完结章建议在规划中填写关系定格画面（freeze_frame）",
                    chapter_num=last,
                ))
            if not intent_final_mod.finale_opening_gap(final_raw):
                issues.append(_issue(
                    "finale_gap_plan_missing",
                    "warn",
                    "完结章建议填写 core_task.opening_gap 以形成首尾呼应",
                    chapter_num=last,
                ))

    return issues


def validation_errors(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in issues if i.get("severity") == "error"]


def validation_warnings(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in issues if i.get("severity") == "warn"]


def format_validation_error(issues: list[dict[str, Any]]) -> str:
    errors = validation_errors(issues)
    if not errors:
        return ""
    return "；".join(str(e.get("message") or e.get("code")) for e in errors)


def build_plan_preview(
    existing: dict,
    option: dict[str, Any],
    *,
    replace: bool,
) -> dict:
    """根据预填 option 构造内存 plan，供采纳前校验。"""
    meta = dict(existing.get("meta") or {}) if isinstance(existing.get("meta"), dict) else {}
    if option.get("paywall_chapter") is not None:
        try:
            meta["paywall_chapter"] = int(option["paywall_chapter"])
        except (TypeError, ValueError):
            pass

    chapters: dict[str, Any] = {}
    if not replace:
        for key, ch in (existing.get("chapters") or {}).items():
            if isinstance(ch, dict):
                chapters[key] = dict(ch)

    for ch in option.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        num = int(ch.get("num") or ch.get("chapter_num") or 0)
        if num < 1:
            continue
        key = str(num)
        entry = dict(chapters.get(key) or {})
        entry["title"] = str(ch.get("title") or entry.get("title") or f"第{num}章").strip()
        role = normalize_role(ch.get("role"))
        if role:
            entry["role"] = role
            intent = normalize_intent(role, ch.get("intent"))
            if intent is not None:
                entry["intent"] = intent
            elif "intent" in entry and role == "paid_open":
                entry.pop("intent", None)
        hook = str(ch.get("hook") or entry.get("hook") or "").strip()
        if hook:
            entry["hook"] = hook
        chapters[key] = entry

    paywall_nums = [
        int(k) for k, v in chapters.items()
        if isinstance(v, dict) and normalize_role(v.get("role")) == "paywall"
    ]
    if len(paywall_nums) == 1:
        meta["paywall_chapter"] = paywall_nums[0]

    return {
        "version": int(existing.get("version") or 2),
        "meta": meta,
        "chapters": chapters,
    }
