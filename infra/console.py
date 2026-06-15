"""控制台输出（Windows GBK 下 emoji 等字符需降级）。"""

from __future__ import annotations

import sys


def safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


def ensure_utf8_stdio() -> None:
    """API/CLI 启动时尽量用 UTF-8，减少 Windows 控制台编码问题。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
