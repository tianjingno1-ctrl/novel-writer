#!/usr/bin/env python3
"""一次性：从 summarizer.py 常量导出 prompts/*.yaml（开发用，勿在运行时调用）。"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 常量名 → YAML 文件名（不含扩展名）
_PROMPT_MAP: dict[str, str] = {
    "WRITING_INSTRUCTION": "writing",
    "SUMMARY_SYSTEM": "summary",
    "CHECK_SYSTEM": "check",
    "CROSS_CHAPTER_CONTINUITY_SYSTEM": "cross_chapter_continuity",
    "READER_REVIEW_SYSTEM": "reader_review",
    "EDITOR_REVIEW_SYSTEM": "editor_review",
    "DECONSTRUCT_SYSTEM": "deconstruct",
    "WORLD_BATCH_CHUNK_REVIEW_SYSTEM": "world_batch_chunk_review",
    "WORLD_BATCH_MERGE_SYSTEM": "world_batch_merge",
    "OUTLINE_SYSTEM": "outline",
    "CHARACTER_DRIFT_SYSTEM": "character_drift",
    "DETAIL_EXTRACT_SYSTEM": "detail_extract",
    "REPETITION_CHECK_SYSTEM": "repetition_check",
    "PACING_CHECK_SYSTEM": "pacing_check",
    "OBSERVE_SYSTEM": "observe",
    "POST_CHAPTER_MAINTAIN_SYSTEM": "post_chapter_maintain",
    "QUALITY_CHECK_BUNDLE_SYSTEM": "quality_check_bundle",
    "WORLD_REMEDIATE_DIAGNOSE_SYSTEM": "world_remediate_diagnose",
    "BULK_ARCHIVE_SUMMARIES_SYSTEM": "bulk_archive_summaries",
    "BULK_ARCHIVE_STATE_SYSTEM": "bulk_archive_state",
    "WORLD_REMEDIATE_BULK_CHANGE_LOG_SYSTEM": "world_remediate_bulk_change_log",
    "WORLD_REMEDIATE_CHANGE_LOG_SYSTEM": "world_remediate_change_log",
}


def _extract_constants(source_path: Path) -> dict[str, str]:
    text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            if name not in _PROMPT_MAP:
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                out[name] = node.value.value
    return out


def _yaml_escape_block(text: str) -> str:
    """YAML literal block scalar."""
    return "system: |\n" + "".join(f"  {line}\n" for line in text.splitlines())


def main() -> int:
    try:
        import yaml  # noqa: F401
    except ImportError:
        print("请先安装: pip install pyyaml", file=sys.stderr)
        return 1

    import yaml

    src = _ROOT / "summarizer.py"
    if not src.exists():
        print(f"找不到 {src}", file=sys.stderr)
        return 1

    constants = _extract_constants(src)
    prompts_dir = _ROOT / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    missing = set(_PROMPT_MAP) - set(constants)
    if missing:
        print(f"警告：未在 summarizer.py 中找到: {', '.join(sorted(missing))}", file=sys.stderr)

    for const_name, slug in _PROMPT_MAP.items():
        body = constants.get(const_name)
        if body is None:
            continue
        payload = {
            "id": slug,
            "description": f"从 summarizer.{const_name} 迁移",
            "system": body,
        }
        out_path = prompts_dir / f"{slug}.yaml"
        out_path.write_text(
            yaml.dump(
                payload,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
                width=120,
            ),
            encoding="utf-8",
        )
        print(f"  wrote {out_path.name}")

    print(f"完成：{len(constants)} 个 prompt → {prompts_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
