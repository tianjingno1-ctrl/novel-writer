"""审阅规则引用（RuleRef）解析。

格式见 docs/data-schema.md §1.3。
"""

from __future__ import annotations

RULE_SOURCES = frozenset({"global", "local", "profile", "custom"})
RULE_REF_SEP = ":"


def format_rule_ref(source: str, rule_id: str) -> str:
    src = (source or "").strip().lower()
    rid = (rule_id or "").strip()
    if src not in RULE_SOURCES:
        raise ValueError(f"无效规则来源: {source!r}")
    if not rid:
        raise ValueError("rule_id 不能为空")
    return f"{src}{RULE_REF_SEP}{rid}"


def parse_rule_ref(ref: str) -> tuple[str, str]:
    """解析 ``global:rule_001`` → (source, rule_id)。"""
    text = (ref or "").strip()
    if RULE_REF_SEP not in text:
        raise ValueError(f"规则引用须含前缀 global:/local:/profile:/custom: —  got {ref!r}")
    source, rule_id = text.split(RULE_REF_SEP, 1)
    source = source.strip().lower()
    rule_id = rule_id.strip()
    if source not in RULE_SOURCES:
        raise ValueError(f"无效规则来源: {source!r}")
    if not rule_id:
        raise ValueError(f"规则 id 为空: {ref!r}")
    return source, rule_id


def is_rule_ref(ref: str) -> bool:
    try:
        parse_rule_ref(ref)
        return True
    except ValueError:
        return False


def resolve_rule_refs(refs: list[str] | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in refs or []:
        out.append(parse_rule_ref(str(item)))
    return out
