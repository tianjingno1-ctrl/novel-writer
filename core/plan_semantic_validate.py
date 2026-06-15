"""W5：章规划 intent 跨章语义校验（可选 LLM，不阻断启发式主流程）。"""

from __future__ import annotations

import json
import re
from typing import Any

from core import chapter_roles
from core import intent_final

HEURISTIC_OVERRIDE_BY_PAIR: dict[str, str] = {
    "bridge_seed_conditions": "bridge_next_seed_mismatch",
    "bridge_seed_missing_conditions": "bridge_next_buildup_no_conditions",
    "finale_hook_open_gap": "finale_opening_gap_mismatch",
    "escalation_debt_emotions": "escalation_debt_untraceable",
}


def collect_semantic_pairs(plan: dict) -> list[dict[str, Any]]:
    """提取需做语义比对的 intent 对（两侧均有文本）。"""
    nums = chapter_roles._chapter_nums(plan)
    if not nums:
        return []
    pairs: list[dict[str, Any]] = []
    first, last = nums[0], nums[-1]

    for num in nums:
        if chapter_roles.chapter_role(plan, num) != "bridge":
            continue
        bridge_ch = (plan.get("chapters") or {}).get(str(num))
        if not isinstance(bridge_ch, dict):
            continue
        seed = intent_final.bridge_next_seed(
            chapter_roles._intent_final_raw(bridge_ch),
        )
        if not seed:
            continue
        next_buildup: int | None = None
        for n in range(num + 1, last + 1):
            if chapter_roles.chapter_role(plan, n) == "buildup":
                next_buildup = n
                break
        if next_buildup is None:
            continue
        next_ch = (plan.get("chapters") or {}).get(str(next_buildup))
        if not isinstance(next_ch, dict):
            continue
        conditions = intent_final.buildup_conditions(
            chapter_roles._intent_final_raw(next_ch),
        )
        if not conditions:
            pairs.append({
                "id": f"bridge_{num}_buildup_{next_buildup}_seed",
                "kind": "bridge_seed_missing_conditions",
                "left_label": f"第{num}章 bridge.next_seed",
                "left": seed,
                "right_label": f"第{next_buildup}章 buildup.conditions",
                "right": "",
                "chapter_num": num,
            })
            continue
        pairs.append({
            "id": f"bridge_{num}_buildup_{next_buildup}_seed",
            "kind": "bridge_seed_conditions",
            "left_label": f"第{num}章 bridge.next_seed",
            "left": seed,
            "right_label": f"第{next_buildup}章 buildup.conditions",
            "right": conditions,
            "chapter_num": num,
        })

    if (
        chapter_roles.chapter_role(plan, first) == "hook_open"
        and chapter_roles.chapter_role(plan, last) == "finale"
    ):
        h1 = (plan.get("chapters") or {}).get(str(first))
        fin = (plan.get("chapters") or {}).get(str(last))
        if isinstance(h1, dict) and isinstance(fin, dict):
            hook_ref = intent_final.hook_open_ref(chapter_roles._intent_final_raw(h1))
            gap = intent_final.finale_opening_gap(chapter_roles._intent_final_raw(fin))
            if hook_ref and gap:
                pairs.append({
                    "id": "finale_hook_open_gap",
                    "kind": "finale_hook_open_gap",
                    "left_label": f"第{first}章 hook_open 缺口/配方",
                    "left": hook_ref,
                    "right_label": f"第{last}章 finale.opening_gap",
                    "right": gap,
                    "chapter_num": last,
                })

    for num in nums:
        if chapter_roles.chapter_role(plan, num) != "escalation":
            continue
        esc_ch = (plan.get("chapters") or {}).get(str(num))
        if not isinstance(esc_ch, dict):
            continue
        debt = intent_final.escalation_debt(chapter_roles._intent_final_raw(esc_ch))
        if not debt:
            continue
        emo_parts: list[str] = []
        emo_nums: list[int] = []
        for n in nums:
            if n >= num:
                break
            if chapter_roles.chapter_role(plan, n) != "buildup":
                continue
            prev = (plan.get("chapters") or {}).get(str(n))
            if not isinstance(prev, dict):
                continue
            emo = intent_final.buildup_emotions(chapter_roles._intent_final_raw(prev))
            if emo:
                emo_parts.append(f"第{n}章:{emo}")
                emo_nums.append(n)
        if not emo_parts:
            continue
        pairs.append({
            "id": f"escalation_{num}_debt_emotions",
            "kind": "escalation_debt_emotions",
            "left_label": f"第{num}章 escalation.debt",
            "left": debt,
            "right_label": "前文 buildup.emotions",
            "right": "；".join(emo_parts),
            "chapter_num": num,
        })

    return pairs


def _parse_llm_checks(text: str) -> list[dict[str, Any]]:
    for line in reversed((text or "").splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{") or "}" not in candidate:
            continue
        start = candidate.find("{")
        end = candidate.rfind("}") + 1
        try:
            raw = json.loads(candidate[start:end])
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        checks = raw.get("checks")
        if isinstance(checks, list):
            return [c for c in checks if isinstance(c, dict)]
    match = re.search(r"\{[\s\S]*\"checks\"[\s\S]*\}", text or "")
    if match:
        try:
            raw = json.loads(match.group(0))
            checks = raw.get("checks")
            if isinstance(checks, list):
                return [c for c in checks if isinstance(c, dict)]
        except json.JSONDecodeError:
            pass
    return []


def _checks_to_issues(
    pairs: list[dict[str, Any]],
    checks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """返回 semantic warnings + heuristic codes to override (LLM 认为对齐)."""
    by_id = {str(c.get("id") or ""): c for c in checks if c.get("id")}
    warnings: list[dict[str, Any]] = []
    overrides: list[str] = []

    for pair in pairs:
        pid = str(pair.get("id") or "")
        kind = str(pair.get("kind") or "")
        row = by_id.get(pid)
        if not row:
            continue
        aligned = row.get("aligned")
        if aligned is True:
            code = HEURISTIC_OVERRIDE_BY_PAIR.get(kind)
            if code:
                overrides.append(code)
            continue
        if aligned is False:
            msg = str(row.get("message") or "").strip()
            if not msg:
                msg = (
                    f"{pair.get('left_label')} 与 {pair.get('right_label')} "
                    "语义未对齐"
                )
            warnings.append({
                "code": f"semantic_{kind}",
                "severity": "warn",
                "message": f"[语义] {msg}",
                "chapter_num": pair.get("chapter_num"),
                "source": "llm_semantic",
                "pair_id": pid,
            })

    return warnings, overrides


def run_semantic_validation(plan: dict) -> dict[str, Any]:
    """LLM 语义校验；无 Key 或失败时 skipped=True，不抛错。"""
    import infra.config as config
    from core import llm
    from core import prompts
    from core.llm import CallOptions

    pairs = collect_semantic_pairs(plan)
    if not pairs:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_pairs",
            "warnings": [],
            "overrides": [],
            "pairs_checked": 0,
        }

    pid = config.CHECK_PROVIDER
    if not config.is_api_key_configured(pid):
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_api_key",
            "warnings": [],
            "overrides": [],
            "pairs_checked": len(pairs),
        }

    payload = [
        {
            "id": p["id"],
            "task": p.get("kind"),
            "left": {"label": p["left_label"], "text": p["left"]},
            "right": {"label": p["right_label"], "text": p["right"]},
        }
        for p in pairs
    ]
    user = (
        "请判断以下 intent 对是否语义对齐：\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    try:
        system = prompts.load_system("plan_intent_semantic")
        reply, _usage = llm.complete(
            system,
            [{"role": "user", "content": user}],
            options=CallOptions(provider=pid, max_tokens=1200, temperature=0.2),
        )
    except Exception as exc:
        return {
            "ok": True,
            "skipped": True,
            "reason": "llm_error",
            "error": str(exc),
            "warnings": [],
            "overrides": [],
            "pairs_checked": len(pairs),
        }

    checks = _parse_llm_checks(reply)
    if not checks:
        return {
            "ok": True,
            "skipped": True,
            "reason": "parse_failed",
            "warnings": [],
            "overrides": [],
            "pairs_checked": len(pairs),
        }

    warnings, overrides = _checks_to_issues(pairs, checks)
    return {
        "ok": True,
        "skipped": False,
        "warnings": warnings,
        "overrides": overrides,
        "pairs_checked": len(pairs),
    }
