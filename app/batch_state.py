"""进程级 batch job 运行状态（单用户：全局唯一运行中 job）。"""

from __future__ import annotations

from infra import state as app_state


def is_batch_job_running() -> bool:
    return bool(app_state.state.batch_job_running)


def set_batch_job_running(running: bool, job_id: str = "") -> None:
    app_state.state.batch_job_running = running
    app_state.state.batch_job_id = job_id if running else ""


def get_running_job_id() -> str:
    return app_state.state.batch_job_id or ""
