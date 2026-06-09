"""组装 AppContext（由 main / web_app 在启动时注入工厂）。"""

from __future__ import annotations

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
