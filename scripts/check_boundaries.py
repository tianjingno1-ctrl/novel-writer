"""P4 架构边界检测。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RULES = [
    ("infra", ["core.", "app.", "api."], "infra 不能依赖业务层"),
    ("core", ["app.", "api.", "main", "web_app"], "core 不能依赖适配层"),
    (
        "api/routes",
        ["novel_data", "change_history", "quality_log", "runtime_log", "app_state"],
        "路由层不能穿透根模块",
    ),
]


def get_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


def main() -> int:
    violations: list[str] = []
    for prefix, forbidden, reason in RULES:
        for py in sorted(ROOT.rglob("*.py")):
            if "__pycache__" in str(py):
                continue
            rel = py.relative_to(ROOT).as_posix()
            if not rel.startswith(prefix):
                continue
            if prefix == "core" and rel.startswith("core/orchestration/"):
                continue
            for imp in get_imports(py):
                for f in forbidden:
                    if imp == f or imp.startswith(f + "."):
                        violations.append(f"[{prefix}] {rel}: import '{imp}' ← {reason}")
    if violations:
        print(f"\nFAIL: {len(violations)} boundary violations:\n")
        for v in violations:
            print(" ", v)
        return 1
        print("\nOK: no boundary violations\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
