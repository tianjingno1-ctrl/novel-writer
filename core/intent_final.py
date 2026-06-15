"""intent.final 读写：兼容 v1.0 扁平字段与嵌套 schema（finale.core_task 等）。"""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def get_field(final: Any, key: str, *, nested: str | None = None) -> str:
    """读 final 字段：优先 flat[key]，其次 nested 子对象内的 key。"""
    if isinstance(final, str):
        return final.strip() if key == "text" else ""
    doc = _as_dict(final)
    direct = str(doc.get(key) or "").strip()
    if direct:
        return direct
    if nested:
        sub = _as_dict(doc.get(nested))
        return str(sub.get(key) or "").strip()
    return ""


def finale_opening_gap(final: Any) -> str:
    return get_field(final, "opening_gap", nested="core_task")


def finale_closing_payoff(final: Any) -> str:
    return get_field(final, "closing_payoff", nested="core_task")


def bridge_next_seed(final: Any) -> str:
    doc = _as_dict(final)
    ns = doc.get("next_seed")
    if isinstance(ns, str):
        return ns.strip()
    if isinstance(ns, dict):
        parts = [
            str(ns.get("hook_type") or "").strip(),
            str(ns.get("clarity") or "").strip(),
            str(ns.get("text") or "").strip(),
        ]
        joined = " ".join(p for p in parts if p)
        if joined:
            return joined
    return ""


def bridge_micro_changed(final: Any) -> str:
    doc = _as_dict(final)
    mc = _as_dict(doc.get("micro_change"))
    return str(mc.get("what_changed") or doc.get("micro_what_changed") or "").strip()


def bridge_micro_who(final: Any) -> str:
    doc = _as_dict(final)
    mc = _as_dict(doc.get("micro_change"))
    return str(mc.get("who") or doc.get("micro_who") or "").strip()


def finale_freeze_what(final: Any) -> str:
    doc = _as_dict(final)
    ff = doc.get("freeze_frame")
    if isinstance(ff, str):
        return ff.strip()
    sub = _as_dict(ff)
    parts = [str(sub.get("who") or "").strip(), str(sub.get("what") or "").strip()]
    joined = " · ".join(p for p in parts if p)
    if joined:
        return joined
    return str(doc.get("freeze_what") or "").strip()


def buildup_conditions(final: Any) -> str:
    return get_field(final, "conditions")


def buildup_emotions(final: Any) -> str:
    return get_field(final, "emotions")


def escalation_debt(final: Any) -> str:
    return get_field(final, "debt")


def escalation_trigger(final: Any) -> str:
    return get_field(final, "trigger")


def hook_open_ref(final: Any) -> str:
    if isinstance(final, str):
        return final.strip()
    doc = _as_dict(final)
    for key in ("opening_gap", "recipe", "gap"):
        val = str(doc.get(key) or "").strip()
        if val:
            return val
    core = _as_dict(doc.get("core_task"))
    return str(core.get("opening_gap") or "").strip()


def normalize_intent_final(role: str, final: Any) -> Any:
    """采纳/预填时归一 final 形状（finale → 嵌套 core_task）。"""
    if final is None:
        return {}
    if role in ("hook_open", "paywall") and isinstance(final, str):
        return final.strip()
    if not isinstance(final, dict):
        return final
    if role == "bridge":
        return _normalize_bridge_final(final)

    if role != "finale":
        return dict(final)

    out: dict[str, Any] = {}
    core = _as_dict(final.get("core_task"))
    opening = str(final.get("opening_gap") or core.get("opening_gap") or "").strip()
    closing = str(final.get("closing_payoff") or core.get("closing_payoff") or "").strip()
    if opening or closing:
        out["core_task"] = {
            "opening_gap": opening,
            "closing_payoff": closing,
        }
    freeze_who = str(final.get("freeze_who") or "").strip()
    freeze_what = str(final.get("freeze_what") or "").strip()
    ff_raw = final.get("freeze_frame")
    if isinstance(ff_raw, dict):
        freeze_who = freeze_who or str(ff_raw.get("who") or "").strip()
        freeze_what = freeze_what or str(ff_raw.get("what") or "").strip()
    elif isinstance(ff_raw, str) and ff_raw.strip():
        freeze_what = freeze_what or ff_raw.strip()
    if freeze_who or freeze_what:
        out["freeze_frame"] = {"who": freeze_who, "what": freeze_what}

    open_what = str(final.get("open_ending_what") or "").strip()
    open_feel = str(final.get("reader_feeling") or "").strip()
    oe_raw = final.get("open_ending")
    if isinstance(oe_raw, dict):
        open_what = open_what or str(oe_raw.get("what_is_left_unsaid") or "").strip()
        open_feel = open_feel or str(oe_raw.get("reader_feeling") or "").strip()
    elif isinstance(oe_raw, str) and oe_raw.strip():
        open_what = open_what or oe_raw.strip()
    if open_what or open_feel:
        out["open_ending"] = {
            "what_is_left_unsaid": open_what,
            "reader_feeling": open_feel,
        }

    for arc_key in ("entry_emotion", "exit_emotion", "landing_method"):
        val = str(final.get(arc_key) or "").strip()
        if val:
            out.setdefault("emotional_arc", {})[arc_key] = val
    ea = _as_dict(final.get("emotional_arc"))
    if ea:
        out["emotional_arc"] = {**_as_dict(out.get("emotional_arc")), **ea}
    subtype = str(final.get("finale_subtype") or "").strip()
    if subtype:
        out["finale_subtype"] = subtype

    for key, val in final.items():
        skip = {
            "opening_gap", "closing_payoff", "core_task",
            "freeze_frame", "freeze_who", "freeze_what",
            "open_ending", "open_ending_what", "reader_feeling",
            "entry_emotion", "exit_emotion", "landing_method",
            "emotional_arc", "finale_subtype",
        }
        if key in skip:
            continue
        if val not in (None, "", {}):
            out[key] = val
    return out


def _normalize_bridge_final(final: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("bridge_subtype", "climax_type", "decompression", "compensation"):
        val = str(final.get(key) or "").strip()
        if val:
            out[key] = val

    arc: dict[str, str] = {}
    for k in ("entry_emotion", "exit_emotion", "reset_method"):
        v = str(final.get(k) or "").strip()
        if v:
            arc[k] = v
    ea = _as_dict(final.get("emotional_arc"))
    arc.update({k: str(v).strip() for k, v in ea.items() if str(v).strip()})
    if arc:
        out["emotional_arc"] = arc

    info_what = str(final.get("info_what") or "").strip()
    info_linked = final.get("info_linked_to_next")
    if info_what or info_linked is not None:
        out["info_payoff"] = {
            "what": info_what,
            "linked_to_next": bool(info_linked) if info_linked is not None else True,
        }
    ip = _as_dict(final.get("info_payoff"))
    if ip:
        out["info_payoff"] = {**_as_dict(out.get("info_payoff")), **ip}

    micro_who = str(final.get("micro_who") or "").strip()
    micro_changed = str(final.get("micro_what_changed") or "").strip()
    mc = _as_dict(final.get("micro_change"))
    micro_who = micro_who or str(mc.get("who") or "").strip()
    micro_changed = micro_changed or str(mc.get("what_changed") or "").strip()
    if micro_who or micro_changed:
        out["micro_change"] = {"who": micro_who, "what_changed": micro_changed}

    sp_type = str(final.get("small_payoff_type") or "").strip()
    if sp_type:
        out["small_payoff"] = {"type": sp_type}

    seed_text = str(final.get("next_seed") or "").strip()
    seed_hook = str(final.get("next_seed_hook_type") or "").strip()
    seed_intensity = str(final.get("next_seed_intensity") or "").strip()
    ns = _as_dict(final.get("next_seed"))
    if isinstance(final.get("next_seed"), str) and final.get("next_seed"):
        seed_text = seed_text or str(final.get("next_seed")).strip()
    if ns:
        seed_text = seed_text or str(ns.get("text") or "").strip()
        seed_hook = seed_hook or str(ns.get("hook_type") or "").strip()
        seed_intensity = seed_intensity or str(ns.get("intensity") or "").strip()
    if seed_text or seed_hook or seed_intensity:
        out["next_seed"] = {
            "text": seed_text,
            "hook_type": seed_hook,
            "intensity": seed_intensity or "低",
        }

    for key, val in final.items():
        skip = {
            "bridge_subtype", "climax_type", "decompression", "compensation",
            "entry_emotion", "exit_emotion", "reset_method", "emotional_arc",
            "info_what", "info_linked_to_next", "info_payoff",
            "micro_who", "micro_what_changed", "micro_change",
            "small_payoff_type", "small_payoff",
            "next_seed", "next_seed_hook_type", "next_seed_intensity",
        }
        if key in skip:
            continue
        if val not in (None, "", {}):
            out[key] = val
    return out
