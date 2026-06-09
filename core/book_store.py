"""书籍存储层：统一快照加载与写盘（逐步替换 main 全局 Path + *Deps Callable）。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.schemas.service import BookSnapshot, PersistOutcome, SnapshotPurpose

if TYPE_CHECKING:
    from core.data.book_context import BookContext

SUMMARIES_RECENT_KEEP = 4

ReadTextFn = Callable[[Path], str]
WriteTextFn = Callable[..., bool]
SessionChapterFn = Callable[[], int]


@dataclass
class BookPathsView:
    """单本书路径视图（由 BookContext 或 app/bootstrap 从外部注入）。"""

    data_dir: Path
    chapters_dir: Path
    summaries_recent_file: Path
    summaries_archive_file: Path
    summaries_file: Path
    char_static_file: Path
    char_dynamic_file: Path
    plot_threads_locked_file: Path
    plot_threads_active_file: Path
    plot_threads_file: Path
    world_file: Path
    style_file: Path
    characters_file: Path
    char_current_file: Path
    outline_latest_file: Path

    @classmethod
    def from_book_context(cls, ctx: BookContext) -> BookPathsView:
        return cls(
            data_dir=ctx.data_dir,
            chapters_dir=ctx.chapters_dir,
            summaries_recent_file=ctx.summaries_recent_file,
            summaries_archive_file=ctx.summaries_archive_file,
            summaries_file=ctx.summaries_file,
            char_static_file=ctx.char_static_file,
            char_dynamic_file=ctx.char_dynamic_file,
            plot_threads_locked_file=ctx.plot_threads_locked_file,
            plot_threads_active_file=ctx.plot_threads_active_file,
            plot_threads_file=ctx.plot_threads_file,
            world_file=ctx.world_file,
            style_file=ctx.style_file,
            characters_file=ctx.characters_file,
            char_current_file=ctx.char_current_file,
            outline_latest_file=ctx.outline_latest_file,
        )

    def to_writing_paths(self) -> object:
        """转为 core.context.BookPaths（快照加载时绑定写作上下文）。"""
        from core.context import BookPaths

        return BookPaths(
            world_file=self.world_file,
            style_file=self.style_file,
            characters_file=self.characters_file,
            char_static_file=self.char_static_file,
            char_dynamic_file=self.char_dynamic_file,
            char_current_file=self.char_current_file,
            summaries_archive_file=self.summaries_archive_file,
            summaries_recent_file=self.summaries_recent_file,
            summaries_file=self.summaries_file,
            plot_threads_locked_file=self.plot_threads_locked_file,
            plot_threads_active_file=self.plot_threads_active_file,
            plot_threads_file=self.plot_threads_file,
        )


def parse_markdown_list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("- "):
            items.append(s)
    return items


def split_summary_entries(content: str) -> tuple[str, list[str]]:
    """按「【第N章」拆分为文件头 + 各章概述块。"""
    text = content or ""
    parts = re.split(r"(?=^【第\d+章)", text, flags=re.MULTILINE)
    if len(parts) <= 1:
        return text, []
    header = parts[0]
    entries = [p.strip() for p in parts[1:] if p.strip()]
    return header, entries


class BookStore:
    """单本书的读快照 / 写持久化入口。"""

    def __init__(
        self,
        paths: BookPathsView,
        *,
        read_text: ReadTextFn,
        write_text: WriteTextFn,
        session_chapter_num: SessionChapterFn | None = None,
        book_context: BookContext | None = None,
    ) -> None:
        self._paths = paths
        self._read = read_text
        self._write = write_text
        self._session_chapter_num = session_chapter_num or (lambda: 0)
        self._ctx = book_context

    @classmethod
    def from_context(
        cls,
        ctx: BookContext,
        *,
        read_text: ReadTextFn,
        write_text: WriteTextFn,
        session_chapter_num: SessionChapterFn | None = None,
    ) -> BookStore:
        return cls(
            BookPathsView.from_book_context(ctx),
            read_text=read_text,
            write_text=write_text,
            session_chapter_num=session_chapter_num,
            book_context=ctx,
        )

    @property
    def paths(self) -> BookPathsView:
        return self._paths

    def read(self, path: Path) -> str:
        return self._read(path)

    def write(
        self,
        path: Path,
        content: str,
        *,
        append: bool = False,
        history_source: str = "write",
        chapter_num: int | None = None,
    ) -> bool:
        """统一写盘（委托 main.write_text，路径由调用方从 self._paths 传入）。"""
        ch = chapter_num if chapter_num is not None else self._session_chapter_num()
        return self._write(
            path,
            content,
            append=append,
            history_source=history_source,
            chapter_num=ch,
        )

    def chapter_path(self, chapter_num: int) -> Path:
        return self._paths.chapters_dir / f"ch{chapter_num:03d}.md"

    def list_chapter_nums(self) -> list[int]:
        chapters_dir = self._paths.chapters_dir
        if not chapters_dir.is_dir():
            return []
        nums: list[int] = []
        for path in chapters_dir.glob("ch*.md"):
            m = re.match(r"ch(\d+)\.md$", path.name)
            if m:
                nums.append(int(m.group(1)))
        return sorted(nums)

    def read_chapter(self, chapter_num: int) -> str:
        return self._read(self.chapter_path(chapter_num))

    def write_chapter(
        self,
        chapter_num: int,
        content: str,
        *,
        append: bool = False,
        history_source: str = "write",
    ) -> bool:
        return self.write(
            self.chapter_path(chapter_num),
            content,
            append=append,
            history_source=history_source,
            chapter_num=chapter_num,
        )

    def latest_chapter_num(self) -> int:
        nums = self.list_chapter_nums()
        return nums[-1] if nums else 0

    def count_summaries(self) -> int:
        _, entries = split_summary_entries(self._read(self._paths.summaries_recent_file))
        return len(entries)

    def summaries_for_scope(self, chapter_num: int, scope: str) -> str:
        combined = self._summaries_combined()
        _header, entries = split_summary_entries(combined)
        if scope == "all":
            return "\n\n".join(entries) if entries else "（暂无概述）"
        if scope == "current":
            start = end = chapter_num
        elif scope == "recent3":
            start = max(1, chapter_num - 2)
            end = chapter_num
        else:
            return "（未知范围）"
        filtered: list[str] = []
        for entry in entries:
            m = re.match(r"【第(\d+)章", entry)
            if m and start <= int(m.group(1)) <= end:
                filtered.append(entry)
        return "\n\n".join(filtered) if filtered else "（该范围内无概述）"

    def chapters_text_for_scope(self, chapter_num: int, scope: str) -> str | None:
        if scope == "current":
            text = self.read_chapter(chapter_num)
            return text if text.strip() else None
        if scope == "recent3":
            start = max(1, chapter_num - 2)
            parts: list[str] = []
            for n in range(start, chapter_num + 1):
                content = self.read_chapter(n)
                if content.strip():
                    parts.append(f"## 第{n}章\n{content}")
            return "\n\n".join(parts) if parts else None
        if scope == "all":
            parts: list[str] = []
            for n in self.list_chapter_nums():
                content = self.read_chapter(n)
                if content.strip():
                    parts.append(f"## 第{n}章\n{content}")
            return "\n\n".join(parts) if parts else None
        return None

    def _upsert_summary_in_file(
        self, path: Path, chapter_num: int, summary_text: str
    ) -> bool:
        raw = self._read(path)
        header, entries = split_summary_entries(raw)
        chapter_prefix = f"【第{chapter_num}章"
        new_entries: list[str] = []
        replaced = False
        for entry in entries:
            if entry.startswith(chapter_prefix):
                if not replaced:
                    new_entries.append(summary_text)
                    replaced = True
            else:
                new_entries.append(entry)
        if not replaced:
            new_entries.append(summary_text)
        body = header.rstrip() + "\n\n" + "\n\n".join(new_entries) + "\n"
        return self.write(
            path,
            body,
            append=False,
            history_source="summary",
            chapter_num=chapter_num,
        )

    def maybe_rotate_summaries_to_archive(
        self,
        *,
        keep_recent: int = SUMMARIES_RECENT_KEEP,
        chapter_num: int = 0,
    ) -> dict[str, Any]:
        """近期概述超过 keep_recent 条时，将最旧条目追加到 summaries_archive。"""
        p = self._paths
        recent_raw = self._read(p.summaries_recent_file)
        header, entries = split_summary_entries(recent_raw)
        if len(entries) <= keep_recent:
            return {"rotated": 0, "ok": True, "recent_count": len(entries)}

        to_archive = entries[: len(entries) - keep_recent]
        kept = entries[len(entries) - keep_recent :]
        archive_body = "\n\n".join(to_archive).strip() + "\n"
        archived = self.write(
            p.summaries_archive_file,
            f"\n\n{archive_body}",
            append=True,
            history_source="summary",
            chapter_num=chapter_num,
        )
        new_recent = header.rstrip() + "\n\n" + "\n\n".join(kept) + "\n"
        trimmed = self.write(
            p.summaries_recent_file,
            new_recent,
            append=False,
            history_source="summary",
            chapter_num=chapter_num,
        )
        return {
            "rotated": len(to_archive),
            "ok": archived and trimmed,
            "recent_count": len(kept),
            "archived": archived,
        }

    def persist_summary(
        self, chapter_num: int, summary_text: str
    ) -> tuple[bool, dict[str, Any]]:
        """写入/更新章节概述（recent + 兼容 summaries.md），必要时 rotate 到 archive。"""
        text = (summary_text or "").strip()
        if not text:
            return False, {"rotated": 0, "ok": True, "recent_count": 0}
        p = self._paths
        w1 = self._upsert_summary_in_file(p.summaries_recent_file, chapter_num, text)
        w2 = self._upsert_summary_in_file(p.summaries_file, chapter_num, text)
        rotate = self.maybe_rotate_summaries_to_archive(chapter_num=chapter_num)
        return (w1 or w2), rotate

    def apply_observe(
        self,
        items: list[dict],
        *,
        chapter_num: int | None = None,
    ) -> dict[str, Any]:
        """将角色观察提案写入 char_static / char_dynamic（路径来自 self._paths）。"""
        if not items:
            return {"ok": False, "error": "没有可应用的提案"}
        ch = chapter_num if chapter_num and chapter_num > 0 else self._session_chapter_num()
        pending: list[dict] = []
        skipped: list[str] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            if not raw.get("accepted"):
                item_id = str(raw.get("id", ""))
                if item_id:
                    skipped.append(item_id)
                continue
            target = str(raw.get("target_file", "")).strip()
            if target not in ("char_static", "char_dynamic"):
                return {"ok": False, "error": f"非法 target_file: {target}"}
            text = str(raw.get("edited_text") or raw.get("proposed_text") or "").strip()
            if not text:
                skipped.append(str(raw.get("id", "?")))
                continue
            pending.append(
                {
                    "id": raw.get("id"),
                    "target": target,
                    "text": text,
                    "chapter_num": int(raw.get("chapter_num") or 0) or ch,
                }
            )
        if not pending:
            return {"ok": False, "error": "没有选中任何提案", "skipped": skipped}

        p = self._paths
        applied: list[dict] = []
        stamp = datetime.now().strftime("%Y-%m-%d")
        for item in pending:
            path = (
                p.char_static_file
                if item["target"] == "char_static"
                else p.char_dynamic_file
            )
            block = f"\n\n<!-- 角色观察 {stamp} -->\n{item['text']}\n"
            wrote = self.write(
                path,
                block,
                append=True,
                history_source="observe",
                chapter_num=item["chapter_num"],
            )
            if wrote:
                applied.append({"id": item["id"], "target_file": item["target"]})
        if not applied:
            return {
                "ok": False,
                "error": "写入未生效（内容与磁盘相同或为空）",
                "skipped": skipped,
            }
        return {"ok": True, "applied": applied, "skipped": skipped}

    def observe_fallback_apply(self, chapter_num: int, text: str) -> list[dict]:
        """无结构化提案时，将摘要追加到 char_dynamic。"""
        body = (text or "").strip()
        if len(body) < 20:
            return []
        stamp = datetime.now().strftime("%Y-%m-%d")
        block = f"\n\n<!-- 角色观察 {stamp} -->\n{body[:4000]}\n"
        if self.write(
            self._paths.char_dynamic_file,
            block,
            append=True,
            history_source="observe",
            chapter_num=chapter_num,
        ):
            return [{"id": "fallback_summary", "target_file": "char_dynamic"}]
        return []

    def append_plot_locked(self, chapter_num: int, detail_text: str) -> bool:
        """追加细节钉子到 plot_threads_locked。"""
        text = (detail_text or "").strip()
        if not text:
            return False
        return self.write(
            self._paths.plot_threads_locked_file,
            f"\n\n{text}\n",
            append=True,
            history_source="detail_extract",
            chapter_num=chapter_num,
        )

    def append_plot_new_threads(
        self,
        chapter_num: int,
        plot_text: str,
        *,
        auto_append: bool = True,
    ) -> tuple[bool, list[str]]:
        """追加新伏笔到 plot_threads_active「未回收」段。"""
        items = parse_markdown_list_items(plot_text)
        if not items or not auto_append:
            return False, items
        block = "\n\n" + "\n".join(items) + "\n"
        wrote = self.write(
            self._paths.plot_threads_active_file,
            block,
            append=True,
            history_source="plot_threads",
            chapter_num=chapter_num,
        )
        return wrote, items

    def _read_char_static(self) -> str:
        text = self._read(self._paths.char_static_file).strip()
        if text:
            return text
        return self._read(self._paths.char_current_file).strip()

    def _extract_plot_unresolved(self, plot_active: str) -> str:
        from summarizer import extract_plot_active_unresolved

        return extract_plot_active_unresolved(plot_active)

    def _bind_writing_context(self) -> None:
        from core import context as writing_context

        writing_context.bind(self._paths.to_writing_paths(), read_text=self._read)

    def _char_context_for_check(self) -> str:
        self._bind_writing_context()
        from core import context as writing_context

        return writing_context.get_char_context_for_check()

    def _summaries_combined(self) -> str:
        self._bind_writing_context()
        from core import context as writing_context

        return writing_context.get_summaries_combined()

    def load_snapshot(
        self,
        chapter_num: int = 0,
        *,
        for_purpose: SnapshotPurpose = "maintain",
        chapter_body: str = "",
    ) -> BookSnapshot:
        p = self._paths
        plot_active = self._read(p.plot_threads_active_file).strip()

        snap = BookSnapshot(
            world=self._read(p.world_file),
            style=self._read(p.style_file),
            characters=self._read(p.characters_file),
            char_static=self._read_char_static(),
            char_dynamic=self._read(p.char_dynamic_file),
            plot_locked=self._read(p.plot_threads_locked_file),
            plot_active=plot_active,
            plot_unresolved=self._extract_plot_unresolved(plot_active),
            summaries_recent=self._read(p.summaries_recent_file),
            chapter_num=chapter_num,
            chapter_body=chapter_body,
        )

        if for_purpose in ("check", "writing"):
            snap.summaries_combined = self._summaries_combined()
        if for_purpose == "check":
            snap.char_context_for_check = self._char_context_for_check()

        return snap

    def apply(self, outcome: PersistOutcome) -> dict[str, bool]:
        """占位：将来由 persist 直接写盘后，编排层可统一调此方法校验。"""
        return {
            "summary": outcome.summary.ok,
            "observe": outcome.observe.applied_count > 0,
            "detail_locked": outcome.detail_locked.ok,
            "plot_new_threads": outcome.plot_new_threads.ok,
        }
