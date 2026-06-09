#!/usr/bin/env python3
"""P4 one-shot migration (safe import rewriter)."""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"__pycache__", ".git", ".venv", "node_modules"}


def ensure_dirs() -> None:
    for d in ("infra/logs", "infra/billing", "infra/pipeline", "core/data"):
        (ROOT / d).mkdir(parents=True, exist_ok=True)
        init = ROOT / d / "__init__.py"
        if not init.exists():
            init.write_text('"""P4 package."""\n', encoding="utf-8")


def fix_root(content: str, depth: int) -> str:
    return content.replace(
        "Path(__file__).resolve().parent",
        f"Path(__file__).resolve().parents[{depth}]",
    )


def write_shim(path: Path, target: str) -> None:
    path.write_text(
        f'"""Shim → {target}."""\nfrom {target} import *  # noqa: F401,F403\n',
        encoding="utf-8",
    )


def move_files() -> None:
    ensure_dirs()
    moves = [
        ("config.py", "infra/config.py", 1),
        ("providers.py", "infra/providers.py", 1),
        ("app_state.py", "infra/state.py", 1),
        ("quality_log.py", "infra/logs/quality.py", 2),
        ("runtime_log.py", "infra/logs/runtime.py", 2),
        ("novel_data.py", "core/data/novel_data.py", 2),
        ("change_history.py", "core/data/change_history.py", 2),
        ("book_context.py", "core/data/book_context.py", 2),
    ]
    for src, dst, depth in moves:
        text = fix_root((ROOT / src).read_text(encoding="utf-8"), depth)
        out = ROOT / dst
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

    billing_src = ROOT / "app" / "cost.py"
    billing_body = billing_src.read_text(encoding="utf-8")
    if billing_body.count('"""') >= 2:
        billing_body = billing_body.split('"""', 2)[2]
        billing_body = billing_body.split("\n", 1)[1]
    (ROOT / "infra" / "billing" / "__init__.py").write_text(
        '"""费用与变更追踪。"""\nfrom __future__ import annotations\n' + billing_body,
        encoding="utf-8",
    )

    # infra/file_utils: atomic + book_io
    fu = (ROOT / "file_utils.py").read_text(encoding="utf-8")
    bio = (ROOT / "app" / "book_io.py").read_text(encoding="utf-8")
    bio_lines = bio.splitlines()
    start = 0
    for i, line in enumerate(bio_lines):
        if line.startswith("from app import paths"):
            start = i
            break
    bio_body = "\n".join(bio_lines[start:])
    merged = (
        '"""基础文件 IO。"""\nfrom __future__ import annotations\n\n'
        + fu.split("from __future__ import annotations", 1)[-1].lstrip()
        + "\n\n# book IO\n"
        + bio_body
    )
    (ROOT / "infra" / "file_utils.py").write_text(merged, encoding="utf-8")

    # core/llm merge
    api = (ROOT / "core" / "api.py").read_text(encoding="utf-8")
    llm = (ROOT / "app" / "llm.py").read_text(encoding="utf-8")
    api_body = api.split("from __future__ import annotations", 1)[1]
    llm_body = llm.split("from __future__ import annotations", 1)[1]
    # drop llm imports block until _request_lock
    llm_lines = llm_body.splitlines()
    body_start = 0
    for i, line in enumerate(llm_lines):
        if line.startswith("_request_lock"):
            body_start = i
            break
    llm_core = "\n".join(llm_lines[body_start:])
    llm_core = llm_core.replace('"app/llm.py:call_api"', '"core/llm.py:call_api"')
    header = textwrap.dedent(
        '''\
        """统一 LLM：transport + call_api。"""
        from __future__ import annotations

        import json
        import logging
        import threading
        import time
        from collections.abc import Iterator
        from dataclasses import dataclass
        from datetime import datetime

        import infra.config as config
        from core.data import novel_data
        from infra.logs import runtime as runtime_log
        from infra import billing as _cost
        from app import paths
        from app import writing_ctx as _wctx
        from infra.state import state
        from infra.providers import APIClient, APIError, TokenUsage, get_client, reset_client
        from core import context as writing_context

        __all__ = [
            "APIError", "CallOptions", "TokenUsage", "complete", "stream",
            "get_client", "reset_client", "call_api", "build_cached_system",
            "log_request_context", "prepare_messages_for_context", "trim_history",
            "get_last_call_info", "_request_lock", "_estimate_tokens",
            "_analyze_system", "_summarize_messages", "_build_context_report",
            "_is_stream_disconnect_error", "_record_call_usage", "_api_error_message",
        ]

        '''
    )
    transport = []
    for line in api_body.splitlines():
        if line.startswith("import config") or line.startswith("from providers"):
            continue
        if line.startswith('"""') or line.startswith("__all__"):
            continue
        transport.append(line)
    (ROOT / "core" / "llm.py").write_text(
        header + "\n".join(transport).strip() + "\n\n" + llm_core + "\n",
        encoding="utf-8",
    )

    (ROOT / "core" / "data" / "__init__.py").write_text(
        "from core.data import book_context, change_history, novel_data\n"
        "__all__ = ['novel_data', 'change_history', 'book_context']\n",
        encoding="utf-8",
    )
    (ROOT / "infra" / "logs" / "__init__.py").write_text(
        "from infra.logs import quality, runtime\n__all__ = ['quality', 'runtime']\n",
        encoding="utf-8",
    )

    write_shim(ROOT / "config.py", "infra.config")
    write_shim(ROOT / "providers.py", "infra.providers")
    write_shim(ROOT / "app_state.py", "infra.state")
    write_shim(ROOT / "file_utils.py", "infra.file_utils")
    write_shim(ROOT / "quality_log.py", "infra.logs.quality")
    write_shim(ROOT / "runtime_log.py", "infra.logs.runtime")
    write_shim(ROOT / "novel_data.py", "core.data.novel_data")
    write_shim(ROOT / "change_history.py", "core.data.change_history")
    write_shim(ROOT / "book_context.py", "core.data.book_context")
    write_shim(ROOT / "app" / "cost.py", "infra.billing")
    write_shim(ROOT / "app" / "book_io.py", "infra.file_utils")
    write_shim(ROOT / "core" / "api.py", "core.llm")
    write_shim(ROOT / "app" / "llm.py", "core.llm")


def rewrite_line(line: str) -> str:
    if "infra.config" in line or "infra/file_utils" in line:
        pass
    # book_io first (specific)
    line = re.sub(
        r"^(\s*)from app import book_io as bio(\s*)$",
        r"\1from infra import file_utils as bio\2",
        line,
    )
    line = re.sub(
        r"^(\s*)from app import book_io(\s*)$",
        r"\1from infra import file_utils as book_io\2",
        line,
    )
    line = re.sub(r"^(\s*)import config(\s*)$", r"\1import infra.config as config\2", line)
    line = re.sub(r"^(\s*)from config import ", r"\1from infra.config import ", line)
    line = re.sub(r"^(\s*)import file_utils(\s*)$", r"\1from infra import file_utils\2", line)
    line = re.sub(r"^(\s*)from file_utils import ", r"\1from infra.file_utils import ", line)
    line = re.sub(r"^(\s*)import providers(\s*)$", r"\1from infra import providers\2", line)
    line = re.sub(r"^(\s*)from providers import ", r"\1from infra.providers import ", line)
    line = re.sub(
        r"^(\s*)import app_state(\s*)$",
        r"\1from infra import state as app_state\2",
        line,
    )
    line = re.sub(r"^(\s*)from app_state import ", r"\1from infra.state import ", line)
    line = re.sub(
        r"^(\s*)import quality_log(\s*)$",
        r"\1from infra.logs import quality as quality_log\2",
        line,
    )
    line = re.sub(
        r"^(\s*)from quality_log import ",
        r"\1from infra.logs.quality import ",
        line,
    )
    line = re.sub(
        r"^(\s*)import runtime_log(\s*)$",
        r"\1from infra.logs import runtime as runtime_log\2",
        line,
    )
    line = re.sub(
        r"^(\s*)from runtime_log import ",
        r"\1from infra.logs.runtime import ",
        line,
    )
    line = re.sub(
        r"^(\s*)import novel_data(\s*)$",
        r"\1from core.data import novel_data\2",
        line,
    )
    line = re.sub(
        r"^(\s*)from novel_data import ",
        r"\1from core.data.novel_data import ",
        line,
    )
    line = re.sub(
        r"^(\s*)import change_history(\s*)$",
        r"\1from core.data import change_history\2",
        line,
    )
    line = re.sub(
        r"^(\s*)from change_history import ",
        r"\1from core.data.change_history import ",
        line,
    )
    line = re.sub(
        r"^(\s*)import book_context(\s*)$",
        r"\1from core.data import book_context\2",
        line,
    )
    line = re.sub(
        r"^(\s*)from book_context import ",
        r"\1from core.data.book_context import ",
        line,
    )
    line = re.sub(r"^(\s*)from app\.cost import ", r"\1from infra.billing import ", line)
    line = re.sub(r"^(\s*)from app import cost as ", r"\1from infra import billing as ", line)
    line = re.sub(r"^(\s*)from app import cost(\s*)$", r"\1from infra import billing as cost\2", line)
    line = re.sub(r"^(\s*)from core\.api import ", r"\1from core.llm import ", line)
    line = re.sub(r"^(\s*)from app import llm as ", r"\1from core import llm as ", line)
    line = re.sub(r"^(\s*)from app import llm(\s*)$", r"\1from core import llm\2", line)
    line = re.sub(r"^(\s*)from app\.llm import ", r"\1from core.llm import ", line)
    return line


SHIM_FILES = {
    "config.py",
    "providers.py",
    "app_state.py",
    "file_utils.py",
    "quality_log.py",
    "runtime_log.py",
    "novel_data.py",
    "change_history.py",
    "book_context.py",
    "app/cost.py",
    "app/book_io.py",
    "core/api.py",
    "app/llm.py",
}


def patch_internal_modules() -> None:
    patches = {
        ROOT / "infra/config.py": [("import file_utils", "from infra import file_utils")],
        ROOT / "infra/providers.py": [("import config", "import infra.config as config")],
        ROOT / "infra/logs/quality.py": [("import file_utils", "from infra import file_utils")],
        ROOT / "infra/logs/runtime.py": [("import file_utils", "from infra import file_utils")],
        ROOT / "core/data/novel_data.py": [("import file_utils", "from infra import file_utils")],
        ROOT / "core/data/change_history.py": [("import file_utils", "from infra import file_utils")],
        ROOT / "core/data/book_context.py": [("import file_utils", "from infra import file_utils")],
    }
    billing = ROOT / "infra/billing/__init__.py"
    text = billing.read_text(encoding="utf-8")
    text = text.replace("import change_history", "from core.data import change_history")
    text = text.replace("import config", "import infra.config as config")
    text = text.replace("import novel_data", "from core.data import novel_data")
    text = text.replace("from app_state import state", "from infra.state import state")
    text = text.replace("from core.api import TokenUsage", "from infra.providers import TokenUsage")
    if text.count("from __future__") > 1:
        parts = text.split("from __future__ import annotations\n", 2)
        text = parts[0] + "from __future__ import annotations\n" + parts[-1]
    billing.write_text(text, encoding="utf-8")

    fu = ROOT / "infra/file_utils.py"
    t = fu.read_text(encoding="utf-8")
    t = t.replace("import change_history", "from core.data import change_history")
    t = t.replace("import file_utils\n", "")
    t = t.replace("file_utils.backup_file", "backup_file")
    t = t.replace("file_utils.atomic_write_text", "atomic_write_text")
    fu.write_text(t, encoding="utf-8")

    for path, pairs in patches.items():
        if not path.exists():
            continue
        t = path.read_text(encoding="utf-8")
        for old, new in pairs:
            t = t.replace(old, new)
        path.write_text(t, encoding="utf-8")


def rewrite_all() -> None:
    for py in sorted(ROOT.rglob("*.py")):
        if any(s in py.parts for s in SKIP):
            continue
        rel = py.relative_to(ROOT).as_posix()
        if rel == "scripts/p4_migrate.py":
            continue
        if rel in SHIM_FILES:
            continue
        lines = py.read_text(encoding="utf-8").splitlines(keepends=True)
        new = [rewrite_line(ln) for ln in lines]
        out = "".join(new)
        if out != "".join(lines):
            py.write_text(out, encoding="utf-8")


def update_forwards() -> None:
    mf = ROOT / "app/main_forwards.py"
    t = mf.read_text(encoding="utf-8").replace('"app.llm"', '"core.llm"')
    mf.write_text(t, encoding="utf-8")
    main = ROOT / "main.py"
    m = main.read_text(encoding="utf-8")
    m = m.replace("import config", "import infra.config as config")
    m = m.replace("from app_state import state", "from infra.state import state")
    m = m.replace("from app.cost import", "from infra.billing import")
    m = m.replace("from app import llm as _llm_module", "from core import llm as _llm_module")
    main.write_text(m, encoding="utf-8")


def main() -> None:
    print("move...")
    move_files()
    print("patch internal...")
    patch_internal_modules()
    print("rewrite imports...")
    rewrite_all()
    print("forwards...")
    update_forwards()
    print("done")


if __name__ == "__main__":
    main()
