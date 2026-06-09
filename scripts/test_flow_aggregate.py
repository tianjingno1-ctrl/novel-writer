#!/usr/bin/env python3
"""聚合 flow smoke test（不调用 LLM，请求本地 web_app）。"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("NOVEL_API_BASE", "http://127.0.0.1:8765").rstrip("/")
TOKEN = os.environ.get("NOVEL_WEB_TOKEN", "").strip()


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["X-Novel-Token"] = TOKEN
    return h


def _request(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload


def _ok(status: int, data: dict, label: str, *, allow_ok_false: bool = False) -> dict:
    if status >= 400:
        print(f"[FAIL] {label} HTTP {status}: {data}")
        sys.exit(1)
    if data.get("ok") is False and not allow_ok_false:
        print(f"[FAIL] {label}: {data.get('error') or data}")
        sys.exit(1)
    print(f"[OK] {label}")
    return data


def _ping() -> None:
    status, _ = _request("GET", "/api/flow/steps")
    if status == 403:
        print("[FAIL] API 拒绝访问。请确认 web_app 在 127.0.0.1 上运行。")
        print("       python web_app.py")
        sys.exit(1)
    if status >= 400:
        print(f"[FAIL] 无法连接 {BASE}（HTTP {status}）")
        print("       先启动：python web_app.py")
        sys.exit(1)


def main() -> int:
    print(f"=== 聚合 flow smoke test @ {BASE}（无 LLM）===\n")
    _ping()

    status, steps = _request("GET", "/api/flow/steps")
    steps = _ok(status, steps, "GET /api/flow/steps")
    step_ids = {s["id"] for s in steps.get("steps") or []}
    for need in ("precheck", "judgment", "rerun_prepare"):
        if need not in step_ids:
            print(f"[FAIL] 缺少步骤 id: {need}")
            return 1

    status, book = _request(
        "POST",
        "/api/library/books",
        {
            "title": "flow聚合测试",
            "type": "short",
            "platform": "tomato",
        },
    )
    book = _ok(status, book, "POST /api/library/books")
    print(f"     book_id={book.get('book_id') or book.get('id')}")

    status, _ = _request(
        "POST",
        "/api/prefill/plan/apply",
        {
            "option": {
                "id": "manual-test",
                "chapters": [
                    {
                        "num": 1,
                        "title": "初遇",
                        "beat": "男女主误会",
                        "hook": "结尾反转",
                        "word_count_target": 2000,
                    },
                    {
                        "num": 2,
                        "title": "再遇",
                        "beat": "误会加深",
                        "hook": "新悬念",
                    },
                ],
            },
            "replace": True,
        },
    )
    _ok(status, _, "POST /api/prefill/plan/apply")

    status, _ = _request("POST", "/api/plan/review-criteria/init", {})
    _ok(status, _, "POST /api/plan/review-criteria/init")

    body = "男女主误会" + ("内容" * 900)
    status, _ = _request(
        "PUT",
        "/api/chapters/1",
        {"content": f"# 第1章 · 初遇\n\n{body}"},
    )
    _ok(status, _, "PUT /api/chapters/1")

    status, wq = _request("GET", "/api/flow/work-queue")
    wq = _ok(status, wq, "GET /api/flow/work-queue")
    print(f"     pending_write={wq.get('pending_write')} pending_review={wq.get('pending_review')}")

    status, pre = _request(
        "POST",
        "/api/flow/run",
        {
            "mode": "chapter",
            "chapter_num": 1,
            "from_step": "precheck",
            "stop_after": "precheck",
        },
    )
    pre = _ok(status, pre, "POST /api/flow/run stop_after=precheck")
    print(f"     stop_reason={pre.get('stop_reason')} stopped_at={pre.get('stopped_at')}")
    if pre.get("stop_reason") != "stop_after" or pre.get("stopped_at") != "precheck":
        print("[FAIL] precheck 停点不符合预期")
        return 1

    status, _ = _request(
        "PATCH",
        "/api/plan/chapters/1/status",
        {"status": "approved"},
    )
    _ok(status, _, "PATCH ch1 approved")

    status, rerun = _request(
        "POST",
        "/api/flow/run",
        {
            "mode": "rerun",
            "scope": "from_chapter_n",
            "from_chapter_num": 2,
            "stop_after": "rerun_prepare",
        },
    )
    rerun = _ok(status, rerun, "POST /api/flow/run rerun stop_after=rerun_prepare")
    executed = rerun.get("executed") or []
    if executed:
        print(f"     affected={executed[0].get('affected_chapters')}")

    status, plan = _request("GET", "/api/plan/product")
    plan = _ok(status, plan, "GET /api/plan/product")
    statuses = plan.get("chapter_statuses") or {}
    print(f"     ch2 status={statuses.get('2') or statuses.get(2)}")

    print("\n=== 全部通过 ===")
    print("带 LLM 的下一步（Swagger http://127.0.0.1:8765/docs）：")
    print('  POST /api/flow/run  {"mode":"continue"}')
    print("  或在人工门按响应里的 next_manual 调单步 API")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
