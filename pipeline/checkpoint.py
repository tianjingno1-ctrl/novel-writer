"""批量任务检查点：统一 job.json 读写与续跑查询。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

JOB_KIND_WORLD_GENERATE = "world_generate"
JOB_KIND_WORLD_REMEDIATE = "world_remediate"

STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

RESUMABLE_STATUSES = frozenset({STATUS_RUNNING, STATUS_PAUSED, STATUS_FAILED})


def jobs_dir(data_dir: Path) -> Path:
    return data_dir / "batch_jobs"


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def job_path(data_dir: Path, job_id: str) -> Path:
    return jobs_dir(data_dir) / job_id


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_job(data_dir: Path, job_id: str) -> dict | None:
    path = job_path(data_dir, job_id) / "job.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_job(data_dir: Path, job: dict) -> None:
    jid = job.get("id")
    if not jid:
        raise ValueError("job 缺少 id")
    job["updated_at"] = _now_iso()
    root = job_path(data_dir, jid)
    root.mkdir(parents=True, exist_ok=True)
    (root / "job.json").write_text(
        json.dumps(job, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_jobs(
    data_dir: Path,
    *,
    kind: str | None = None,
    limit: int = 20,
) -> list[dict]:
    root = jobs_dir(data_dir)
    if not root.is_dir():
        return []
    rows: list[dict] = []
    for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not child.is_dir():
            continue
        job = load_job(data_dir, child.name)
        if not job:
            continue
        if kind and job.get("kind") != kind:
            continue
        rows.append(job)
        if len(rows) >= limit:
            break
    return rows


def find_resumable_job(data_dir: Path, kind: str) -> dict | None:
    for job in list_jobs(data_dir, kind=kind, limit=50):
        if job.get("status") in RESUMABLE_STATUSES:
            return job
    return None


def create_job(
    kind: str,
    *,
    label: str = "",
    chapter_from: int = 0,
    chapter_to: int = 0,
    targets: list[int] | None = None,
    extra: dict | None = None,
) -> dict:
    jid = new_job_id()
    job: dict = {
        "id": jid,
        "kind": kind,
        "status": STATUS_RUNNING,
        "label": label,
        "chapter_from": chapter_from,
        "chapter_to": chapter_to,
        "targets": list(targets or []),
        "completed": [],
        "generated": [],
        "skipped": [],
        "errors": [],
        "warnings": [],
        "total_cost_usd": 0.0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "accepted": False,
    }
    if extra:
        job.update(extra)
    return job


def mark_job_done(job: dict, *, partial: bool = False) -> None:
    if job.get("errors") and partial:
        job["status"] = STATUS_PAUSED
    elif job.get("errors"):
        job["status"] = STATUS_FAILED
    else:
        job["status"] = STATUS_DONE


def remaining_targets(job: dict) -> list[int]:
    done = {int(x) for x in job.get("completed") or []}
    return [int(n) for n in job.get("targets") or [] if int(n) not in done]
