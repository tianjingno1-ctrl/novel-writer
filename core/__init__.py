"""核心模块：API 调用、Prompt 加载、上下文（逐步从 main 迁入）。

新功能请优先放入 core/，勿在 main.py 新增大块业务逻辑。
LLM 调用请走 core.llm.call_api / stream，勿直接调 SDK。
章节正文解析请走 core.chapters，生成/改稿请走 core.generator，审阅请走 core.reviewer，章后维护请走 core.maintain。
"""

from __future__ import annotations

__all__ = ["book_store", "chapters", "context", "deps", "generator", "llm", "maintain", "prompts", "reviewer", "schemas"]
