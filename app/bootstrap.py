"""组装 AppContext 与启动初始化（由 main / web_app / CLI 在启动时调用）。"""

from __future__ import annotations

import json

from app.context import AppContext

_ctx: AppContext | None = None


def configure(ctx: AppContext) -> None:
    global _ctx
    _ctx = ctx


def init_context() -> AppContext:
    """从工厂组装 AppContext 并注册（CLI / API 启动时调用）。"""
    from app import factories

    store = factories.book_store()
    ctx = AppContext(
        store=store,
        reviewer_deps=factories.reviewer_deps(store),
        maintain_deps=factories.maintain_deps(store),
        generator_deps=factories.generator_deps(store),
        resolve_chapter=factories.resolve_chapter_num,
        quality_log_entry=factories.quality_log_entry,
        short_story_skip=factories.short_story_archive_skip,
    )
    assert ctx.reviewer_deps.store is ctx.store, "store 引用不一致"
    assert ctx.maintain_deps.store is ctx.store, "store 引用不一致"
    configure(ctx)
    return ctx


def bootstrap_library() -> None:
    """初始化书库并绑定当前书路径（启动时调用一次）。"""
    from core.data import book_context
    from infra.logs import runtime as runtime_log
    from app import paths as _paths

    runtime_log.init_runtime_log(_paths.resolved("BASE_DIR"))
    from core import taste as taste_store

    taste_store.ensure_taste_dir()
    book_context.init_library()
    from infra import file_utils
    from core import context as writing_context
    from core import chapter_io as cio

    writing_context.install_path_resolver(_paths.resolved, file_utils.read_text)
    init_context()
    from app import factories

    cio.configure(
        store_provider=factories.book_store,
        path_resolver=_paths.resolved,
    )


def init_data_dirs() -> None:
    """首次运行：创建目录与空文件。"""
    from core.data import book_context
    from core.data import change_history
    from infra import file_utils
    from core.data import novel_data
    from infra.logs import quality as quality_log
    from app import paths as _paths
    from app.bootstrap_data import DEFAULT_CHAT_PROMPTS, INITIAL_FILE_TEMPLATES
    from infra.billing import _register_change_history

    _paths.resolved("CHAPTERS_DIR").mkdir(parents=True, exist_ok=True)
    _paths.resolved("BACKUPS_DIR").mkdir(parents=True, exist_ok=True)
    novel_data.CODEX_DIR.mkdir(parents=True, exist_ok=True)
    archive_exists = _paths.resolved("ARCHIVE_FILE").exists()
    archived_filenames = frozenset(book_context.ARCHIVE_SECTION_BY_FILENAME.keys())
    for key, path in _paths.resolved_codex_files().items():
        content = INITIAL_FILE_TEMPLATES.get(key)
        if not content or path.exists():
            continue
        if archive_exists and path.name in archived_filenames:
            continue
        path.write_text(content, encoding="utf-8")
    chat_prompts = _paths.resolved("CHAT_PROMPTS_FILE")
    if not chat_prompts.exists():
        file_utils.atomic_write_text(
            chat_prompts,
            json.dumps(DEFAULT_CHAT_PROMPTS, ensure_ascii=False, indent=2),
        )
    novel_data.load_plan()
    _register_change_history()
    quality_log.init_quality_log(_paths.resolved("DATA_DIR"))
    change_history.ensure_baseline_snapshot()
    from core.data import book_context

    from core import plan_product

    plan_product.migrate_legacy_brief(_paths.resolved("DATA_DIR"))


def rebuild_context() -> AppContext:
    """
    切书后调用（book_context.switch_book → apply_paths_to_modules 之后）。
    重新从 main 的全局路径变量组装所有实例。

    TODO: 单用户假设，多用户场景需改为 per-session context。
    """
    return init_context()


def get_app_context() -> AppContext:
    if _ctx is None:
        raise RuntimeError("AppContext 未初始化，请先调用 app.bootstrap.init_context()")
    return _ctx
