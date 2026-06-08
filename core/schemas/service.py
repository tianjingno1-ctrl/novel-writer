"""服务层输入/输出契约：模块之间传递的结构化数据。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ChapterRef:
    num: int
    title: str = ""


@dataclass
class ChapterWork:
    """单次审阅/维护/生成的工作单元。"""

    ref: ChapterRef
    body: str


@dataclass
class BookSnapshot:
    """一次 LLM 调用所需的档案文本快照（不含 Path，纯内容）。"""

    world: str = ""
    style: str = ""
    characters: str = ""
    char_static: str = ""
    char_dynamic: str = ""
    char_context_for_check: str = ""
    summaries_combined: str = ""
    summaries_recent: str = ""
    plot_locked: str = ""
    plot_active: str = ""
    plot_unresolved: str = ""
    chapter_num: int = 0
    chapter_body: str = ""


SnapshotPurpose = Literal["writing", "check", "maintain"]


@dataclass
class ServiceResult:
    """统一 API / 服务返回包装。"""

    ok: bool
    error: str = ""
    data: Any = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class BundleCallResult:
    """maintain.call_bundle 返回值：仅 LLM，不写盘。"""

    ok: bool
    chapter_num: int
    reply: str | None = None
    payload: Any = None  # MaintainPayload | None
    error: str = ""
    parse_ok: bool = False
    llm_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SummaryPersistResult:
    ok: bool = False
    text: str = ""
    full_text: str = ""
    written_to: str = "summaries_recent"
    archived_count: int = 0
    archive_written_to: str | None = None


@dataclass
class ObservePersistResult:
    ok: bool = False
    applied_count: int = 0
    skipped_count: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    detail: str = ""


@dataclass
class DetailLockedPersistResult:
    ok: bool = False
    appended_count: int = 0
    written_to: str = "plot_threads_locked"
    text: str = ""


@dataclass
class PlotNewThreadsPersistResult:
    ok: bool = False
    appended_count: int = 0
    written_to: str = "plot_threads_active"
    items: list[Any] = field(default_factory=list)
    text: str = ""


@dataclass
class PersistOutcome:
    """maintain.persist 写盘结果。"""

    summary: SummaryPersistResult = field(default_factory=SummaryPersistResult)
    observe: ObservePersistResult = field(default_factory=ObservePersistResult)
    detail_locked: DetailLockedPersistResult = field(default_factory=DetailLockedPersistResult)
    plot_new_threads: PlotNewThreadsPersistResult = field(
        default_factory=PlotNewThreadsPersistResult
    )
    errors: list[str] = field(default_factory=list)
    structured_errors: list[dict[str, Any]] = field(default_factory=list)

    def to_archive_dict(self) -> dict[str, Any]:
        """兼容现有 Web/API 使用的 archive 块形状。"""
        return {
            "summary": {
                "ok": self.summary.ok,
                "text": self.summary.text,
                "full_text": self.summary.full_text,
                "written_to": self.summary.written_to,
                "archived_count": self.summary.archived_count,
                "archive_written_to": self.summary.archive_written_to,
            },
            "observe": {
                "ok": self.observe.ok,
                "applied_count": self.observe.applied_count,
                "skipped_count": self.observe.skipped_count,
                "items": self.observe.items,
                "summary": self.observe.summary,
                "detail": self.observe.detail,
            },
            "detail_locked": {
                "ok": self.detail_locked.ok,
                "appended_count": self.detail_locked.appended_count,
                "written_to": self.detail_locked.written_to,
                "text": self.detail_locked.text,
            },
            "plot_new_threads": {
                "ok": self.plot_new_threads.ok,
                "appended_count": self.plot_new_threads.appended_count,
                "written_to": self.plot_new_threads.written_to,
                "items": self.plot_new_threads.items,
                "text": self.plot_new_threads.text,
            },
        }
