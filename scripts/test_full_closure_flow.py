#!/usr/bin/env python3
"""全流程：大纲 → 章节检查 → 仅诊断审阅 → 世界闭环（审阅+修改+档案）。

写入 data/closure_flow_log.jsonl 与 debug-d92d85.log（闭环阶段）。
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows 控制台 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("NOVEL_CHECK_PROVIDER", "deepseek")
os.environ.setdefault("NOVEL_QUALITY_PROVIDER", "deepseek")
os.environ.setdefault("NOVEL_MAINTAIN_PROVIDER", "deepseek")
os.environ.setdefault("NOVEL_OUTLINE_PROVIDER", "deepseek")

import config
import main
import quality_log

FLOW_LOG = main.DATA_DIR / "closure_flow_log.jsonl"
DEBUG_LOG = ROOT / "debug-d92d85.log"


def _sep(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def _flow_log(step: str, ok: bool, detail: dict | None = None) -> None:
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "step": step,
        "ok": ok,
        "detail": detail or {},
    }
    FLOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(FLOW_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # #region agent log
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "d92d85",
                        "hypothesisId": "E2E",
                        "location": "test_full_closure_flow",
                        "message": step,
                        "data": {"ok": ok, **(detail or {})},
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        pass
    # #endregion


def main_flow() -> int:
    quality_log.init_quality_log(main.DATA_DIR)
    _sep("0. 配置检查")
    for pid in (
        config.OUTLINE_PROVIDER,
        config.CHECK_PROVIDER,
        config.PROVIDER,
        config.MAINTAIN_PROVIDER,
    ):
        name = config.get_provider_config(pid)["name"]
        ok = config.is_api_key_configured(pid)
        print(f"  {pid} ({name}): {'OK' if ok else 'MISSING'}")
        if not ok and pid in (config.CHECK_PROVIDER, config.PROVIDER):
            print(f"ERROR: 必需 Key 未配置: {pid}")
            return 1

    chapters = main.list_chapters()
    _sep(f"1. 写作前提 · 已有 {len(chapters)} 章")
    if not chapters:
        print("ERROR: data/chapters/ 无正文，请先在 Web 写作模式或写书对话生成章节")
        _flow_log("chapters_check", False, {"count": 0})
        return 1
    nums = [n for n, _ in chapters]
    print(f"章节: {nums}")
    _flow_log("chapters_check", True, {"count": len(chapters), "nums": nums})

    _sep("2. 续章灵感 / 大纲 outline")
    t0 = time.time()
    outline_r = main.api_run_outline(next_count=1)
    elapsed = time.time() - t0
    if not outline_r.get("ok"):
        print("WARN:", outline_r.get("error", "大纲失败（可继续，若已有 plan）"))
        _flow_log("outline", False, {"error": outline_r.get("error"), "elapsed_s": elapsed})
    else:
        preview = (outline_r.get("reply") or "")[:400]
        print(f"耗时 {elapsed:.1f}s · 预览:")
        try:
            print(f"{preview}…")
        except UnicodeEncodeError:
            print(preview.encode("utf-8", errors="replace").decode("utf-8") + "…")
        _flow_log(
            "outline",
            True,
            {"elapsed_s": round(elapsed, 1), "reply_len": len(outline_r.get("reply") or "")},
        )

    _sep("3. 世界批次 status")
    status = main.api_get_world_batch_status()
    print(
        f"{status.get('label')} · 正文 {status.get('written_count')} 章 "
        f"（第{status.get('written_from')}–{status.get('written_to')}）"
    )
    _flow_log("world_status", True, {k: status.get(k) for k in ("written_count", "written_from", "written_to")})

    if not status.get("written_count"):
        print("ERROR: 无正文可审阅")
        return 1

    _sep("4. 仅诊断 · 世界审阅 review")
    print("开始调用…")
    t1 = time.time()
    review_r = main.api_run_world_batch_review()
    elapsed = time.time() - t1
    if not review_r.get("ok") and not review_r.get("partial"):
        print("ERROR:", review_r.get("error"))
        _flow_log("review", False, {"error": review_r.get("error"), "elapsed_s": elapsed})
        return 1
    print(
        f"耗时 {elapsed:.1f}s · ok={review_r.get('ok')} partial={review_r.get('partial')} "
        f"log_id={review_r.get('log_id')}"
    )
    _flow_log(
        "review",
        True,
        {
            "elapsed_s": round(elapsed, 1),
            "partial": review_r.get("partial"),
            "log_id": review_r.get("log_id"),
            "report_chars": review_r.get("report_chars"),
        },
    )

    _sep("5. 世界闭环 remediate（诊断→改稿→档案→报告）")
    print("开始调用（耗时较长）…")
    t2 = time.time()
    remediate_r = main.api_run_world_remediate()
    elapsed = time.time() - t2
    if not remediate_r.get("ok") and not remediate_r.get("partial"):
        print("ERROR:", remediate_r.get("error"))
        _flow_log("remediate", False, {"error": remediate_r.get("error"), "elapsed_s": elapsed})
        return 1
    print(
        f"耗时 {elapsed:.1f}s · status={remediate_r.get('status')} "
        f"ok_count={remediate_r.get('ok_count')}/{remediate_r.get('target_count')} "
        f"job_id={remediate_r.get('job_id')}"
    )
    if remediate_r.get("warnings"):
        for w in remediate_r["warnings"]:
            print(f"  WARN: {w}")
    if remediate_r.get("errors"):
        for e in remediate_r["errors"]:
            print(f"  ERR: {e}")
    report = remediate_r.get("report") or ""
    preview = report[:1500]
    print("\n--- 闭环报告（前 1500 字）---")
    try:
        print(preview)
    except UnicodeEncodeError:
        print(preview.encode("utf-8", errors="replace").decode("utf-8"))
    out = main.DATA_DIR / "test_closure_report.md"
    out.write_text(report, encoding="utf-8")
    print(f"\n完整报告: {out}")
    _flow_log(
        "remediate",
        remediate_r.get("status") == "completed",
        {
            "elapsed_s": round(elapsed, 1),
            "job_id": remediate_r.get("job_id"),
            "status": remediate_r.get("status"),
            "ok_count": remediate_r.get("ok_count"),
            "target_count": remediate_r.get("target_count"),
            "partial": remediate_r.get("partial"),
            "total_cost_usd": remediate_r.get("total_cost_usd"),
        },
    )

    _sep("6. 善后 · accept job")
    job_id = remediate_r.get("job_id")
    if job_id:
        acc = main.api_accept_batch_job(job_id)
        print(f"accept: {acc}")
        _flow_log("accept", acc.get("ok", False), {"job_id": job_id})

    _sep("7. 结果")
    if remediate_r.get("partial"):
        print("⚠️ 部分完成，见 warnings/errors 与 debug-d92d85.log")
        return 2
    print("✅ 全流程完成")
    print(f"流程日志: {FLOW_LOG}")
    print(f"调试日志: {DEBUG_LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_flow())
