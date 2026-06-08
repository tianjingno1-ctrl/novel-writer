#!/usr/bin/env python3
"""Rewrite summarizer.py to load system prompts from YAML."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.prompts import LEGACY_NAME_TO_ID, load_system

path = _ROOT / "summarizer.py"
text = path.read_text(encoding="utf-8")

marker = "def build_summary_user_message"
idx = text.index(marker)

header = '''"""概述生成与连续性检查的 prompt 模板。"""

import json
import re
from pathlib import Path

from core.prompts import load_system

'''

assignments = [f'{const} = load_system("{pid}")' for const, pid in LEGACY_NAME_TO_ID.items()]

gf_match = re.search(
    r"(def get_female_fiction_review_system\([\s\S]*?return text\n)",
    text,
)
gf_block = gf_match.group(1) if gf_match else ""

const_block = header + "\n".join(assignments) + "\n\n\n" + gf_block + "\n"
new_text = const_block + text[idx:]
path.write_text(new_text, encoding="utf-8")
print(f"summarizer.py rewritten, {len(new_text.splitlines())} lines")

# verify all load
for const, pid in LEGACY_NAME_TO_ID.items():
    load_system(pid)
print("all prompts load OK")
