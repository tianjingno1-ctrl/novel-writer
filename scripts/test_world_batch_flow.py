#!/usr/bin/env python3
"""世界批次审阅全流程：status → preview → review（DeepSeek）。"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("NOVEL_CHECK_PROVIDER", "deepseek")
os.environ.setdefault("NOVEL_QUALITY_PROVIDER", "deepseek")

import config
import quality_log
from app import llm
from app import paths as _paths
from app.bootstrap import bootstrap_library, init_context, init_data_dirs
from core.orchestration import batch as orchestration_batch


def _sep(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main_flow() -> int:
    bootstrap_library()
    init_data_dirs()
    quality_log.init_quality_log(_paths.resolved("DATA_DIR"))
    pid = config.CHECK_PROVIDER
    _sep(f"1. 配置 · provider={pid} ({config.get_provider_config(pid)['model']})")
    if not config.is_api_key_configured(pid):
        print(f"ERROR: {pid} API Key 未配置")
        return 1
    print("API Key: OK")

    ctx = init_context()
    _sep("2. 世界批次 status")
    status = orchestration_batch.get_world_batch_status(ctx)
    print(json.dumps(status, ensure_ascii=False, indent=2))

    _sep("3. 发送预览 preview")
    t0 = time.time()
    preview = orchestration_batch.preview_world_batch_review(ctx)
    if not preview.get("ok"):
        print("ERROR:", preview.get("error"))
        return 1
    print(f"正文 {preview['total_prose_chars']:,} 字 · user {preview['total_user_chars']:,} 字")
    print(
        f"估算 input ≈{preview['total_est_input_tokens']:,} tokens · "
        f"典型 output ≈{preview['total_typical_output_tokens']:,} · "
        f"API {preview['api_call_count']} 次"
    )
    for i, c in enumerate(preview.get("calls") or [], 1):
        print(
            f"  [{i}] {c['label']}: user {c['user_chars']:,} 字 · "
            f"≈{c['est_input_tokens']:,} in · 典型 out {c['est_output_tokens_typical']:,}"
        )
    print(f"\n预览耗时 {time.time() - t0:.1f}s（无 API）")
    print("\n--- 预览正文（前 1200 字）---\n")
    body = preview.get("preview") or ""
    print(body[:1200])
    if len(body) > 1200:
        print("\n…（预览已截断显示，完整见 quality 面板）")

    _sep("4. 执行世界审阅 review（DeepSeek，串行 API）")
    print("开始调用，请稍候…")
    t1 = time.time()
    result = orchestration_batch.run_world_batch_review(ctx)
    elapsed = time.time() - t1
    print(f"耗时 {elapsed:.1f}s")

    if not result.get("ok") and not result.get("partial"):
        print("ERROR:", result.get("error"))
        if result.get("errors"):
            print("errors:", result["errors"])
        return 1

    print(f"ok={result.get('ok')} partial={result.get('partial')}")
    print(f"log_id={result.get('log_id')}")
    print(f"report_chars={result.get('report_chars')}")
    print(f"input_truncated={result.get('input_truncated')}")
    print(f"output_truncated={result.get('output_truncated')}")
    print(f"total_cost_usd={result.get('total_cost_usd')}")
    if result.get("warnings"):
        print("warnings:")
        for w in result["warnings"]:
            print(f"  - {w}")
    if result.get("errors"):
        print("errors:")
        for e in result["errors"]:
            print(f"  - {e}")

    last = llm.get_last_call_info()
    print(f"last_call: provider={last.get('provider')} cost={last.get('cost')}")

    _sep("5. 审阅报告（前 2000 字）")
    reply = result.get("reply") or ""
    try:
        print(reply[:2000])
    except UnicodeEncodeError:
        print(reply[:2000].encode("utf-8", errors="replace").decode("utf-8"))
    if len(reply) > 2000:
        print(f"\n…（报告共 {len(reply):,} 字，已截断显示）")

    out_path = ROOT / "data" / "test_world_batch_report.md"
    out_path.write_text(reply, encoding="utf-8")
    print(f"\n完整报告已写入: {out_path}")

    _sep("6. 结果")
    if result.get("output_truncated"):
        print("⚠️  存在 output 截断，建议提高 NOVEL_BATCH_REVIEW_*_MAX_TOKENS")
        return 2
    if result.get("partial"):
        print("⚠️  部分步骤失败，见 errors")
        return 2
    print("✅ 全流程通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_flow())
