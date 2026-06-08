#!/usr/bin/env python3
"""一次性：docs/review-prompts/*.md → prompts/review/*.yaml"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SRC = _ROOT / "docs" / "review-prompts"
DST = _ROOT / "prompts" / "review"


def _parse_mode(text: str) -> str | None:
    m = re.search(r"^>\s*mode:\s*(\S+)", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    if "mode: rewrite-only" in text:
        return "rewrite-only"
    return None


def main() -> int:
    try:
        import yaml
    except ImportError:
        print("pip install pyyaml", file=sys.stderr)
        return 1

    if not SRC.is_dir():
        print(f"源目录不存在: {SRC}", file=sys.stderr)
        return 1

    DST.mkdir(parents=True, exist_ok=True)
    count = 0
    for md in sorted(SRC.glob("*.md")):
        text = md.read_text(encoding="utf-8").strip()
        payload: dict = {
            "id": md.stem,
            "description": f"从 docs/review-prompts/{md.name} 迁移",
            "system": text,
        }
        mode = _parse_mode(text)
        if mode:
            payload["mode"] = mode
        out = DST / f"{md.stem}.yaml"
        out.write_text(
            yaml.dump(payload, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )
        print(f"  wrote {out.name}")
        count += 1
    print(f"完成：{count} 个审阅 prompt → {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
