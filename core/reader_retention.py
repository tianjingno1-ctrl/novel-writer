"""读者留存模拟：爽点密度 + 章尾弃文风险（L2 读者视角 / L11 节奏预警）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from infra import file_utils

# 默认情绪/爽点信号词（可被 taste.reader_pattern 覆盖加权）
DEFAULT_PAYOFF_MARKERS: tuple[str, ...] = (
    "竟然",
    "居然",
    "愣",
    "惊",
    "全场",
    "安静",
    "倒吸",
    "屏息",
    "心跳",
    "脸红",
    "扬眉",
    "冷笑",
    "握紧",
    "转身",
    "停住",
)

HOOK_END_MARKERS: tuple[str, ...] = (
    "？",
    "…",
    "...",
    "却",
    "突然",
    "没想到",
    "谁知",
    "门",
    "电话",
    "消息",
)


def retention_path(book_dir: Path, chapter_num: int) -> Path:
    return book_dir / "chapters" / f"ch{chapter_num:03d}" / "retention.json"


def load_retention(book_dir: Path, chapter_num: int) -> dict[str, Any] | None:
    path = retention_path(book_dir, chapter_num)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def save_retention(book_dir: Path, chapter_num: int, doc: dict[str, Any]) -> dict[str, Any]:
    path = retention_path(book_dir, chapter_num)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_utils.atomic_write_text(
        path,
        json.dumps(doc, ensure_ascii=False, indent=2),
    )
    return doc


def _level_from_score(score: float, *, high: float, medium: float) -> str:
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def analyze_reader_perspective(
    content: str,
    *,
    chapter_num: int,
    reader_pattern: dict[str, Any] | None = None,
    drop_risk_thresholds: dict[str, float] | None = None,
    chapter_role: str | None = None,
) -> dict[str, Any]:
    """读者视角：爽点密度 + 章尾弃文风险（启发式）。"""
    text = (content or "").strip()
    plain_len = max(len(re.sub(r"\s+", "", text)), 1)
    pattern = reader_pattern if isinstance(reader_pattern, dict) else {}
    preferred = pattern.get("good_emotions") or pattern.get("emotion_nodes") or []
    markers = [str(m).strip() for m in preferred if str(m).strip()] or list(DEFAULT_PAYOFF_MARKERS)

    payoff_hits = 0
    matched: list[str] = []
    for m in markers:
        c = text.count(m)
        if c > 0:
            payoff_hits += c
            matched.append(m)
    # 每 1000 字至少 2 个信号 → 高密度
    density_score = payoff_hits * 1000 / plain_len
    payoff_level = _level_from_score(density_score, high=3.5, medium=1.8)

    tail = text[-600:] if len(text) > 600 else text
    hook_score = 0.0
    for hm in HOOK_END_MARKERS:
        if hm in tail:
            hook_score += 0.15
    if re.search(r"[？?…]\s*$", tail.strip()):
        hook_score += 0.35
    if len(tail.strip()) < 80:
        hook_score += 0.2
    if chapter_role in ("paywall", "hook_open"):
        hook_score -= 0.05
    drop_score = max(0.0, min(1.0, 0.65 - hook_score + (0.15 if payoff_level == "low" else 0)))
    th = drop_risk_thresholds if isinstance(drop_risk_thresholds, dict) else {}
    high_th = float(th.get("high", 0.55))
    medium_th = float(th.get("medium", 0.35))
    drop_level = _level_from_score(drop_score, high=high_th, medium=medium_th)

    reason_parts: list[str] = []
    if payoff_level == "low":
        reason_parts.append("本章爽点/情绪落点偏少")
    if drop_level == "high":
        reason_parts.append("章尾缺少悬念或钩子")
    elif drop_level == "medium":
        reason_parts.append("章尾张力一般")

    return {
        "chapter_num": chapter_num,
        "chapter_role": chapter_role,
        "payoff_density": payoff_level,
        "payoff_score": round(density_score, 2),
        "matched_emotions": matched[:6],
        "drop_off_risk": drop_level,
        "drop_off_score": round(drop_score, 3),
        "drop_off_reason": "；".join(reason_parts) or "节奏正常",
        "source": "heuristic",
    }


def _normalize_level(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in ("high", "medium", "low"):
        return raw
    if raw in ("高", "偏高"):
        return "high"
    if raw in ("中", "一般"):
        return "medium"
    if raw in ("低", "偏低"):
        return "low"
    return None


def _parse_reader_json_line(text: str) -> dict[str, str] | None:
    for line in reversed((text or "").splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{") or "}" not in candidate:
            continue
        start = candidate.find("{")
        end = candidate.rfind("}") + 1
        blob = candidate[start:end]
        try:
            raw = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        out: dict[str, str] = {}
        risk = _normalize_level(raw.get("risk"))
        payoff = _normalize_level(raw.get("payoff"))
        notes = str(raw.get("notes") or raw.get("summary") or "").strip()
        if risk:
            out["drop_off_risk"] = risk
        if payoff:
            out["payoff_density"] = payoff
        if notes:
            out["reader_review_summary"] = notes
        if out:
            return out
    return None


def _parse_drop_level_from_llm(text: str) -> str | None:
    parsed = _parse_reader_json_line(text)
    if parsed and parsed.get("drop_off_risk"):
        return parsed["drop_off_risk"]
    match = re.search(r"RISK:\s*(high|medium|low)\b", text or "", re.IGNORECASE)
    if match:
        return match.group(1).lower()
    for line in (text or "").splitlines():
        if "弃读" in line or "弃文" in line:
            if "高" in line:
                return "high"
            if "中" in line:
                return "medium"
            if "低" in line:
                return "low"
    return None


def _parse_payoff_level_from_llm(text: str) -> str | None:
    parsed = _parse_reader_json_line(text)
    if parsed and parsed.get("payoff_density"):
        return parsed["payoff_density"]
    match = re.search(r"PAYOFF:\s*(high|medium|low)\b", text or "", re.IGNORECASE)
    if match:
        return match.group(1).lower()
    for line in (text or "").splitlines():
        if "爽点" in line or "情绪落点" in line:
            if "高" in line:
                return "high"
            if "中" in line:
                return "medium"
            if "低" in line:
                return "low"
    return None


def parse_llm_reader_metrics(text: str) -> dict[str, str]:
    parsed = _parse_reader_json_line(text)
    if parsed:
        return parsed
    out: dict[str, str] = {}
    risk = _parse_drop_level_from_llm(text)
    payoff = _parse_payoff_level_from_llm(text)
    if risk:
        out["drop_off_risk"] = risk
    if payoff:
        out["payoff_density"] = payoff
    return out


def try_llm_reader_review(
    content: str,
    *,
    plan: dict,
    chapter_num: int,
    base: dict[str, Any],
) -> dict[str, Any] | None:
    """L2：按 role + intent 调用 reader_review prompt；失败时返回 None。"""
    import infra.config as config
    from core import chapter_role_overlay
    from core import llm
    from core import prompts
    from core.llm import CallOptions

    pid = config.CHECK_PROVIDER
    if not config.is_api_key_configured(pid):
        return None
    user = chapter_role_overlay.l2_reader_user_prompt(plan, chapter_num, content)
    if not user.strip():
        return None
    try:
        system = prompts.load_system("reader_review")
        reply, _usage = llm.complete(
            system,
            [{"role": "user", "content": user}],
            options=CallOptions(provider=pid, max_tokens=1200, temperature=0.3),
        )
    except Exception:
        return None
    metrics = parse_llm_reader_metrics(reply)
    out = dict(base)
    out["source"] = "llm+heuristic"
    out["reader_review_text"] = reply.strip()
    if metrics.get("drop_off_risk"):
        out["drop_off_risk"] = metrics["drop_off_risk"]
        out["drop_off_reason"] = f"读者模拟：{metrics['drop_off_risk']} 风险（LLM）"
    if metrics.get("payoff_density"):
        out["payoff_density"] = metrics["payoff_density"]
    if metrics.get("reader_review_summary"):
        out["reader_review_summary"] = metrics["reader_review_summary"]
        if not metrics.get("drop_off_risk"):
            out["drop_off_reason"] = metrics["reader_review_summary"]
    return out


def check_rhythm_warning(
    book_dir: Path,
    chapter_nums: list[int],
    *,
    window: int = 3,
) -> dict[str, Any]:
    """L11：近 N 章连续高弃文风险 → 节奏预警。"""
    nums = sorted(chapter_nums)[-window:]
    if len(nums) < window:
        return {"ok": True, "warning": False, "window": window}
    rows: list[dict[str, Any]] = []
    for num in nums:
        doc = load_retention(book_dir, num)
        if doc:
            rows.append(doc)
        else:
            rows.append({"chapter_num": num, "drop_off_risk": "unknown"})
    high_streak = all(r.get("drop_off_risk") == "high" for r in rows)
    medium_plus = sum(
        1 for r in rows if r.get("drop_off_risk") in ("high", "medium")
    )
    warning = high_streak or medium_plus >= window
    return {
        "ok": True,
        "warning": warning,
        "window": window,
        "chapters": nums,
        "recent": rows,
        "message": (
            f"节奏预警：第 {nums[0]}–{nums[-1]} 章弃文风险偏高，建议检查节拍"
            if warning
            else ""
        ),
    }
