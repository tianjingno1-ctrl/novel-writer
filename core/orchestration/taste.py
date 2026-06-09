"""口味库编排。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from core import taste

if TYPE_CHECKING:
    from app.context import AppContext


def _book_id(ctx: AppContext) -> str:
    from core.data import book_context

    return book_context.get_context().book_id


def _book_dir(ctx: AppContext) -> Path:
    return ctx.store.paths.data_dir


def get_global() -> dict:
    doc = taste.load_global()
    return {"ok": True, "global": doc, "tag_labels": taste.ISSUE_TAG_LABELS}


def put_global(fields: dict[str, Any]) -> dict:
    doc = taste.save_global(fields)
    return {"ok": True, "global": doc}


def get_book(ctx: AppContext) -> dict:
    book_dir = _book_dir(ctx)
    doc = taste.load_book_taste(book_dir)
    merged = taste.merge_preferences(book_dir=book_dir)
    return {
        "ok": True,
        "book_id": _book_id(ctx),
        "taste": doc,
        "merged_preferences": merged,
    }


def put_book(ctx: AppContext, fields: dict[str, Any]) -> dict:
    doc = taste.save_book_taste(_book_dir(ctx), fields)
    merged = taste.merge_preferences(book_dir=_book_dir(ctx))
    return {
        "ok": True,
        "taste": doc,
        "merged_preferences": merged,
    }


def list_events(
    *,
    book_id: str | None = None,
    source: str | None = None,
    limit: int = 80,
) -> dict:
    return {
        "ok": True,
        "events": taste.list_events(book_id=book_id, source=source, limit=limit),
    }


def post_event(
    ctx: AppContext,
    *,
    source: str = "manual",
    outcome: str = "",
    issue_tags: list[str] | None = None,
    note: str = "",
    patterns: dict | None = None,
) -> dict:
    eid = taste.append_event(
        source=source,
        outcome=outcome,
        issue_tags=issue_tags,
        note=note,
        book_id=_book_id(ctx),
        patterns=patterns,
    )
    return {"ok": True, "event_id": eid}


def get_summary(ctx: AppContext) -> dict:
    summary = taste.get_summary(book_id=_book_id(ctx))
    return {"ok": True, **summary}


def context_block(ctx: AppContext, *, max_chars: int = 3500) -> str:
    return taste.build_context_block(
        book_id=_book_id(ctx),
        book_dir=_book_dir(ctx),
        max_chars=max_chars,
    )


def import_deconstruct(ctx: AppContext, quality_log_id: str, *, merge_global: bool = True) -> dict:
    return taste.import_deconstruct_patterns(
        quality_log_id,
        book_dir=_book_dir(ctx),
        merge_global=merge_global,
    )


def get_author_profile() -> dict:
    from core import author_profile

    return {"ok": True, "profile": author_profile.load_author_profile()}


def extract_author_profile(ctx: AppContext) -> dict:
    from core import author_profile
    from core.data import novel_data

    book_dir = _book_dir(ctx)
    taste_doc = taste.load_book_taste(book_dir)
    reader_pattern = taste_doc.get("reader_pattern") if isinstance(taste_doc, dict) else {}
    project = novel_data.get_project_meta()
    saved = author_profile.extract_from_book(
        book_id=_book_id(ctx),
        book_title=str(project.get("title") or ""),
        taste_doc=taste_doc,
        reader_pattern=reader_pattern if isinstance(reader_pattern, dict) else None,
    )
    return {"ok": True, "profile": saved}


def apply_author_profile(
    ctx: AppContext,
    *,
    inherit_all: bool = True,
    rule_ids: list[str] | None = None,
) -> dict:
    from core import author_profile

    book_dir = _book_dir(ctx)
    cur = taste.load_book_taste(book_dir)
    merged = author_profile.apply_to_book_taste(
        cur,
        inherit_all=inherit_all,
        rule_ids=rule_ids,
    )
    saved = taste.save_book_taste(book_dir, merged)
    return {"ok": True, "taste": saved}


def put_reader_pattern(ctx: AppContext, reader_pattern: dict[str, Any]) -> dict:
    book_dir = _book_dir(ctx)
    cur = taste.load_book_taste(book_dir)
    cur["reader_pattern"] = reader_pattern
    saved = taste.save_book_taste(book_dir, cur)
    return {"ok": True, "taste": saved}


def on_quality_judgment(
    ctx: AppContext,
    entry: dict,
    *,
    outcome: str,
    issue_tags: list[str] | None = None,
    note: str = "",
) -> str | None:
    extra = entry.get("extra") if isinstance(entry.get("extra"), dict) else {}
    return taste.record_judgment_event(
        book_id=_book_id(ctx),
        quality_log_id=str(entry.get("id") or ""),
        outcome=outcome,
        issue_tags=issue_tags or extra.get("issue_tags"),
        note=note,
        chapter_num=int(entry.get("chapter_num") or 0),
        prompt_node=str(extra.get("prompt_node") or ""),
        kind=str(entry.get("kind") or ""),
    )
