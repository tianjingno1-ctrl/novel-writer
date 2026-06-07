"""核心纯函数与工具的最小单测。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import file_utils  # noqa: E402
import main  # noqa: E402
from providers import TokenUsage  # noqa: E402


class FileUtilsTests(unittest.TestCase):
    def test_atomic_write_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            file_utils.atomic_write_text(path, "hello")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello")
            file_utils.atomic_write_text(path, "world")
            self.assertEqual(path.read_text(encoding="utf-8"), "world")


class CostTests(unittest.TestCase):
    def test_calc_cost_no_cache(self) -> None:
        usage = main.TokenUsage(
            cache_read_input_tokens=1_000_000,
            cache_creation_input_tokens=0,
            input_tokens=100_000,
            output_tokens=500_000,
        )
        with_cache = main.calc_cost(usage, "kie")
        no_cache = main.calc_cost_no_cache(usage, "kie")
        self.assertGreater(no_cache, with_cache)

    def test_build_cached_system_records_context_debug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "world.md").write_text("# 世界", encoding="utf-8")
            (data / "style.md").write_text("# 文风", encoding="utf-8")
            (data / "characters.md").write_text("# 人", encoding="utf-8")
            (data / "char_static.md").write_text("锚点", encoding="utf-8")
            orig = {
                "WORLD": main.WORLD_FILE,
                "STYLE": main.STYLE_FILE,
                "CHARACTERS": main.CHARACTERS_FILE,
                "STATIC": main.CHAR_STATIC_FILE,
            }
            try:
                main.WORLD_FILE = data / "world.md"
                main.STYLE_FILE = data / "style.md"
                main.CHARACTERS_FILE = data / "characters.md"
                main.CHAR_STATIC_FILE = data / "char_static.md"
                main.build_cached_system("续写指令", provider="kie")
                debug = main.get_last_context_debug()
                self.assertTrue(debug["ok"])
                self.assertGreaterEqual(len(debug["layers"]), 3)
                labels = [layer["label"] for layer in debug["layers"]]
                self.assertTrue(any("world" in label for label in labels))
            finally:
                main.WORLD_FILE = orig["WORLD"]
                main.STYLE_FILE = orig["STYLE"]
                main.CHARACTERS_FILE = orig["CHARACTERS"]
                main.CHAR_STATIC_FILE = orig["STATIC"]

    def test_log_request_context_free_chat_no_stale_layers(self) -> None:
        main.build_cached_system("续写", provider="kie")
        main.log_request_context(
            None,
            [{"role": "user", "content": "你好"}],
            tag="自由聊",
            provider="deepseek",
        )
        debug = main.get_last_context_debug()
        self.assertTrue(debug["ok"])
        self.assertEqual(debug["tag"], "自由聊")
        self.assertEqual(len(debug["layers"]), 1)
        self.assertIn("无 system", debug["layers"][0]["label"])

    def test_calc_cost_kie(self) -> None:
        usage = TokenUsage(
            cache_read_input_tokens=1_000_000,
            cache_creation_input_tokens=0,
            input_tokens=0,
            output_tokens=0,
        )
        cost = main.calc_cost(usage, provider="kie")
        self.assertAlmostEqual(cost, 0.30, places=4)

    def test_load_total_cost_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "cost_log.jsonl"
            log.write_text(
                "\n".join(
                    [
                        json.dumps({"cost": 0.1, "total_cost": 0.1}),
                        json.dumps({"cost": 0.2, "total_cost": 0.3}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            total = main.load_total_cost_from_jsonl(log)
            self.assertAlmostEqual(total, 0.3)


class SanitizeChapterTextTests(unittest.TestCase):
    def test_unescape_quot(self) -> None:
        raw = '&quot;二姐，什么事。&quot;'
        self.assertEqual(main.sanitize_chapter_text(raw), '"二姐，什么事。"')

    def test_unescape_mixed_entities(self) -> None:
        raw = "&lt;tag&gt; &amp; &apos;x&apos;"
        self.assertEqual(main.sanitize_chapter_text(raw), "<tag> & 'x'")

    def test_prepare_chapter_body_strips_entities(self) -> None:
        reply = "【章节标题】测试\n\n&quot;你好。&quot;"
        title, body = main.prepare_chapter_body_from_reply(reply, 2)
        self.assertIn('"你好。"', body)
        self.assertNotIn("&quot;", body)


class ShouldAppendTests(unittest.TestCase):
    def test_discussion_prefix(self) -> None:
        self.assertFalse(main.should_append_to_chapter("[讨论] 这是一段很长的说明文字" * 3))

    def test_meta_prefix(self) -> None:
        self.assertFalse(main.should_append_to_chapter("我建议你可以这样写下一章的内容" * 2))

    def test_prose(self) -> None:
        text = "夜风从窗缝里渗进来，带着潮气。他握紧剑柄，听见廊下脚步声渐近。"
        self.assertTrue(main.should_append_to_chapter(text))


class TrimHistoryTests(unittest.TestCase):
    def test_trim_history(self) -> None:
        history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}] * 5
        trimmed = main.trim_history(history, max_turns=2)
        self.assertEqual(len(trimmed), 4)


class ConfigTests(unittest.TestCase):
    def test_get_price_has_cache_write(self) -> None:
        price = config.get_price("kie")
        self.assertIn("cache_write", price)
        self.assertGreater(price["input"], 0)


class HistoryTests(unittest.TestCase):
    def test_baseline_and_save_with_history(self) -> None:
        import change_history

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            backups = data / "backups"
            dynamic = data / "char_dynamic.md"
            dynamic.write_text("状态A\n", encoding="utf-8")
            change_history.init_history(
                data,
                {"char_dynamic": dynamic},
                backups_dir=backups,
            )
            manifest = change_history.ensure_baseline_snapshot()
            self.assertTrue(manifest.get("files"))
            self.assertEqual(
                (data / "history" / "baseline" / "char_dynamic.md").read_text(
                    encoding="utf-8"
                ),
                "状态A\n",
            )
            eid = change_history.save_with_history(
                dynamic,
                "\n状态B\n",
                append=True,
                source="test",
                chapter_num=2,
            )
            self.assertIsNotNone(eid)
            self.assertIn("状态B", dynamic.read_text(encoding="utf-8"))
            hist = change_history.list_history()
            self.assertEqual(hist["summary"]["char_dynamic"]["change_count"], 1)
            rev = change_history.revert_entry(eid)
            self.assertTrue(rev["ok"])
            self.assertEqual(dynamic.read_text(encoding="utf-8"), "状态A\n")


class MaintainTests(unittest.TestCase):
    def test_parse_post_chapter_maintain(self) -> None:
        from summarizer import parse_post_chapter_maintain

        reply = (
            "```post-chapter-json\n"
            "{"
            '"summary": "【第1章：试】\\n核心事件：甲\\n人物变化：乙\\n伏笔/关键信息：丙",'
            '"observe": {"summary": "女主更警觉", "items": ['
            '{"id": "char_dynamic", "has_change": true, "target_file": "char_dynamic", '
            '"proposed_text": "### 状态\\n- 警觉"}'
            "]},"
            '"detail_locked": "## 第1章\\n- 【年龄】17岁"'
            "}\n```"
        )
        parsed, _ = parse_post_chapter_maintain(reply)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIn("核心事件", parsed["summary"])
        self.assertEqual(len(parsed["observe"]["items"]), 1)
        self.assertIn("年龄", parsed["detail_locked"])

    def test_parse_post_chapter_maintain_fail(self) -> None:
        from summarizer import parse_post_chapter_maintain

        parsed, raw = parse_post_chapter_maintain("只有纯文本，没有 JSON")
        self.assertIsNone(parsed)
        self.assertIn("纯文本", raw)

    def test_parse_post_chapter_maintain_plot_fields(self) -> None:
        from summarizer import parse_post_chapter_maintain

        reply = (
            "```post-chapter-json\n"
            '{"summary": "【第2章：试】\\n核心事件：甲",'
            '"observe": {"summary": "", "items": []},'
            '"detail_locked": "",'
            '"plot_new_threads": "- 【新坑】描述",'
            '"plot_advanced": "- 【旧坑】推进",'
            '"plot_resolved": ""}\n```"'
        )
        parsed, _ = parse_post_chapter_maintain(reply)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIn("新坑", parsed["plot_new_threads"])
        self.assertIn("旧坑", parsed["plot_advanced"])

    def test_parse_quality_bundle(self) -> None:
        from summarizer import parse_quality_bundle

        reply = (
            "```quality-bundle-json\n"
            '{"continuity": "- [道具] 矛盾",'
            '"character_drift": "无漂移",'
            '"repetition": "## 重复"}\n```"'
        )
        parsed, _ = parse_quality_bundle(reply)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIn("矛盾", parsed["continuity"])

    def test_persist_archive_writes_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            summaries_recent = data / "summaries_recent.md"
            summaries = data / "summaries.md"
            locked = data / "plot_threads_locked.md"
            active = data / "plot_threads_active.md"
            dynamic = data / "char_dynamic.md"
            static = data / "char_static.md"
            for p in (summaries_recent, summaries, locked, active, dynamic, static):
                p.write_text("# 占位\n", encoding="utf-8")
            active.write_text(
                "# 活跃伏笔\n\n## 未回收\n\n（暂无）\n\n## 已回收\n",
                encoding="utf-8",
            )
            orig = {
                "RECENT": main.SUMMARIES_RECENT_FILE,
                "SUM": main.SUMMARIES_FILE,
                "LOCKED": main.PLOT_THREADS_LOCKED_FILE,
                "ACTIVE": main.PLOT_THREADS_ACTIVE_FILE,
                "DYN": main.CHAR_DYNAMIC_FILE,
                "STA": main.CHAR_STATIC_FILE,
                "DATA": main.DATA_DIR,
            }
            import change_history

            try:
                main.DATA_DIR = data
                main.SUMMARIES_RECENT_FILE = summaries_recent
                main.SUMMARIES_FILE = summaries
                main.PLOT_THREADS_LOCKED_FILE = locked
                main.PLOT_THREADS_ACTIVE_FILE = active
                main.CHAR_DYNAMIC_FILE = dynamic
                main.CHAR_STATIC_FILE = static
                change_history.init_history(
                    data,
                    {
                        "summaries_recent": summaries_recent,
                        "plot_threads_locked": locked,
                        "plot_threads_active": active,
                        "char_dynamic": dynamic,
                        "char_static": static,
                    },
                    backups_dir=data / "backups",
                )
                parsed = {
                    "summary": "【第3章：测】\n核心事件：事件A\n人物变化：无\n伏笔/关键信息：无",
                    "observe": {
                        "summary": "有变化",
                        "items": [
                            {
                                "id": "char_dynamic",
                                "has_change": True,
                                "target_file": "char_dynamic",
                                "proposed_text": "### 状态\n- 警觉",
                            }
                        ],
                    },
                    "detail_locked": "## 第3章\n- 【年龄】18岁",
                    "plot_new_threads": "- 【测试伏笔】埋设于本章",
                    "plot_advanced": "",
                    "plot_resolved": "",
                }
                archive, errors, _ = main._persist_archive_payload(
                    3,
                    parsed,
                    auto_apply_observe=True,
                    auto_append_locked=True,
                    auto_append_plot_new=True,
                )
                self.assertFalse(errors, errors)
                self.assertTrue(archive["summary"]["ok"])
                self.assertIn("第3章", summaries_recent.read_text(encoding="utf-8"))
                self.assertIn("警觉", dynamic.read_text(encoding="utf-8"))
                self.assertIn("18岁", locked.read_text(encoding="utf-8"))
                self.assertIn("测试伏笔", active.read_text(encoding="utf-8"))
            finally:
                main.DATA_DIR = orig["DATA"]
                main.SUMMARIES_RECENT_FILE = orig["RECENT"]
                main.SUMMARIES_FILE = orig["SUM"]
                main.PLOT_THREADS_LOCKED_FILE = orig["LOCKED"]
                main.PLOT_THREADS_ACTIVE_FILE = orig["ACTIVE"]
                main.CHAR_DYNAMIC_FILE = orig["DYN"]
                main.CHAR_STATIC_FILE = orig["STA"]

    def test_summary_rotate_to_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            recent = data / "summaries_recent.md"
            archive = data / "summaries_archive.md"
            summaries = data / "summaries.md"
            recent.write_text(
                "# 近期概述\n\n"
                + "\n\n".join(
                    f"【第{i}章：章{i}】\n核心事件：事件{i}" for i in range(1, 6)
                )
                + "\n",
                encoding="utf-8",
            )
            archive.write_text("# 归档\n\n", encoding="utf-8")
            summaries.write_text("# 兼容\n\n", encoding="utf-8")
            orig_r, orig_a, orig_s, orig_d = (
                main.SUMMARIES_RECENT_FILE,
                main.SUMMARIES_ARCHIVE_FILE,
                main.SUMMARIES_FILE,
                main.DATA_DIR,
            )
            import change_history

            try:
                main.DATA_DIR = data
                main.SUMMARIES_RECENT_FILE = recent
                main.SUMMARIES_ARCHIVE_FILE = archive
                main.SUMMARIES_FILE = summaries
                change_history.init_history(
                    data,
                    {
                        "summaries_recent": recent,
                        "summaries_archive": archive,
                    },
                    backups_dir=data / "backups",
                )
                ok, rot = main._persist_summary_text(
                    6,
                    "【第6章：新】\n核心事件：新章\n人物变化：无\n伏笔/关键信息：无",
                )
                self.assertTrue(ok)
                self.assertEqual(rot["rotated"], 2)
                arch_text = archive.read_text(encoding="utf-8")
                self.assertIn("第1章", arch_text)
                self.assertIn("第2章", arch_text)
                recent_text = recent.read_text(encoding="utf-8")
                self.assertIn("第6章", recent_text)
                self.assertNotIn("第1章", recent_text)
            finally:
                main.DATA_DIR = orig_d
                main.SUMMARIES_RECENT_FILE = orig_r
                main.SUMMARIES_ARCHIVE_FILE = orig_a
                main.SUMMARIES_FILE = orig_s

    def test_finalize_mock_api(self) -> None:
        archive_json = (
            "```post-chapter-json\n"
            "{"
            '"summary": "【第1章：终】\\n核心事件：完\\n人物变化：无\\n伏笔/关键信息：无",'
            '"observe": {"summary": "", "items": []},'
            '"detail_locked": "## 第1章\\n- 【专名】测试城",'
            '"plot_new_threads": "- 【线A】新开",'
            '"plot_advanced": "",'
            '"plot_resolved": ""'
            "}\n```"
        )
        quality_json = (
            "```quality-bundle-json\n"
            '{"continuity": "✅ 未发现明显矛盾",'
            '"character_drift": "无漂移",'
            '"repetition": "无重复"}\n```"'
        )

        def fake_call(system, messages, *, tag="请求", **kwargs):
            main.state.last_call_info = {
                "ok": True,
                "cost": 0.001,
                "usage": {"input": 10, "output": 5, "cache_read": 0},
            }
            if tag == "档案bundle":
                return archive_json
            if tag == "质检bundle":
                return quality_json
            return None

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            ch_dir = data / "chapters"
            ch_dir.mkdir()
            (ch_dir / "ch001.md").write_text("# 第1章\n\n正文足够长。" * 5, encoding="utf-8")
            summaries_recent = data / "summaries_recent.md"
            summaries = data / "summaries.md"
            locked = data / "plot_threads_locked.md"
            active = data / "plot_threads_active.md"
            world = data / "world.md"
            characters = data / "characters.md"
            dynamic = data / "char_dynamic.md"
            static = data / "char_static.md"
            for p in (
                summaries_recent,
                summaries,
                locked,
                active,
                world,
                characters,
                dynamic,
                static,
            ):
                p.write_text("# 占位\n", encoding="utf-8")
            active.write_text("# 活跃\n\n## 未回收\n\n## 已回收\n", encoding="utf-8")
            orig_ch = main.CHAPTERS_DIR
            orig = {
                "RECENT": main.SUMMARIES_RECENT_FILE,
                "SUM": main.SUMMARIES_FILE,
                "LOCKED": main.PLOT_THREADS_LOCKED_FILE,
                "ACTIVE": main.PLOT_THREADS_ACTIVE_FILE,
                "WORLD": main.WORLD_FILE,
                "CHARS": main.CHARACTERS_FILE,
                "DYN": main.CHAR_DYNAMIC_FILE,
                "STA": main.CHAR_STATIC_FILE,
                "DATA": main.DATA_DIR,
            }
            import change_history

            try:
                main.CHAPTERS_DIR = ch_dir
                main.DATA_DIR = data
                main.SUMMARIES_RECENT_FILE = summaries_recent
                main.SUMMARIES_FILE = summaries
                main.PLOT_THREADS_LOCKED_FILE = locked
                main.PLOT_THREADS_ACTIVE_FILE = active
                main.WORLD_FILE = world
                main.CHARACTERS_FILE = characters
                main.CHAR_DYNAMIC_FILE = dynamic
                main.CHAR_STATIC_FILE = static
                change_history.init_history(
                    data,
                    {
                        "summaries_recent": summaries_recent,
                        "plot_threads_locked": locked,
                        "plot_threads_active": active,
                    },
                    backups_dir=data / "backups",
                )
                import quality_log

                quality_log.init_quality_log(data)
                with mock.patch.object(main, "call_api", side_effect=fake_call):
                    r = main.api_run_post_chapter_finalize(
                        1,
                        run_pacing=False,
                        run_outline=False,
                    )
                self.assertTrue(r["ok"], r)
                self.assertTrue(r["archive"]["summary"]["ok"])
                self.assertIn("测试城", locked.read_text(encoding="utf-8"))
                self.assertIn("线A", active.read_text(encoding="utf-8"))
                self.assertTrue(r["quality"]["continuity"]["ok"])
                self.assertEqual(len(r["calls"]), 2)
            finally:
                main.CHAPTERS_DIR = orig_ch
                main.DATA_DIR = orig["DATA"]
                main.SUMMARIES_RECENT_FILE = orig["RECENT"]
                main.SUMMARIES_FILE = orig["SUM"]
                main.PLOT_THREADS_LOCKED_FILE = orig["LOCKED"]
                main.PLOT_THREADS_ACTIVE_FILE = orig["ACTIVE"]
                main.WORLD_FILE = orig["WORLD"]
                main.CHARACTERS_FILE = orig["CHARS"]
                main.CHAR_DYNAMIC_FILE = orig["DYN"]
                main.CHAR_STATIC_FILE = orig["STA"]


class ObserveTests(unittest.TestCase):
    def test_parse_observe_proposals(self) -> None:
        from summarizer import parse_observe_proposals

        reply = (
            "本章出现新习惯。\n\n"
            "```observe-json\n"
            '{"items": [{"id": "private_frequency", "has_change": true, '
            '"target_file": "char_static", "proposed_text": "- 试"}]}\n'
            "```"
        )
        items, summary = parse_observe_proposals(reply)
        self.assertEqual(len(items), 1)
        self.assertIn("习惯", summary)

    def test_api_apply_observe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            static = data / "char_static.md"
            dynamic = data / "char_dynamic.md"
            static.write_text("# 锚点\n", encoding="utf-8")
            dynamic.write_text("# 动态\n", encoding="utf-8")
            orig_s = main.CHAR_STATIC_FILE
            orig_d = main.CHAR_DYNAMIC_FILE
            try:
                main.CHAR_STATIC_FILE = static
                main.CHAR_DYNAMIC_FILE = dynamic
                r = main.api_apply_observe(
                    [
                        {
                            "id": "private_frequency",
                            "target_file": "char_static",
                            "accepted": True,
                            "proposed_text": "### 新习惯\n- 试",
                        }
                    ]
                )
                self.assertTrue(r["ok"])
                self.assertIn("新习惯", static.read_text(encoding="utf-8"))
            finally:
                main.CHAR_STATIC_FILE = orig_s
                main.CHAR_DYNAMIC_FILE = orig_d

    def test_save_codex_unchanged_reports_false(self) -> None:
        import change_history

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            dynamic = data / "char_dynamic.md"
            dynamic.write_text("# 动态\n- 状态：旧\n", encoding="utf-8")
            orig = main.CHAR_DYNAMIC_FILE
            orig_data = main.DATA_DIR
            orig_codex = dict(main.CODEX_FILES)
            try:
                main.DATA_DIR = data
                main.CHAR_DYNAMIC_FILE = dynamic
                main.CODEX_FILES["char_dynamic"] = dynamic
                change_history.init_history(
                    data, {"char_dynamic": dynamic}, backups_dir=data / "backups"
                )
                text = dynamic.read_text(encoding="utf-8")
                r = main.save_codex("char_dynamic", text, chapter_num=1)
                self.assertTrue(r["ok"])
                self.assertFalse(r["changed"])
                r2 = main.save_codex(
                    "char_dynamic", text.replace("旧", "新"), chapter_num=1
                )
                self.assertTrue(r2["changed"])
            finally:
                main.CHAR_DYNAMIC_FILE = orig
                main.DATA_DIR = orig_data
                main.CODEX_FILES.clear()
                main.CODEX_FILES.update(orig_codex)


class QualityLogTests(unittest.TestCase):
    def test_append_and_list(self) -> None:
        import quality_log

        with tempfile.TemporaryDirectory() as tmp:
            quality_log.init_quality_log(Path(tmp))
            eid = quality_log.append_entry(
                "detail_extract",
                1,
                "钉子：编号 7-3",
                persisted=True,
                persisted_detail="已追加",
            )
            rows = quality_log.list_entries(limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], eid)
            self.assertTrue(rows[0]["persisted"])
            full = quality_log.get_entry(eid)
            self.assertIsNotNone(full)
            self.assertIn("7-3", full["body"])


class PaceTests(unittest.TestCase):
    def test_resolve_scene_pace_from_field(self) -> None:
        import novel_data

        self.assertEqual(
            novel_data.resolve_scene_pace({"pace": "快", "beat": ""}),
            "快",
        )

    def test_resolve_scene_pace_from_beat(self) -> None:
        import novel_data

        beat = "【场景目的】打脸\n【节奏档位】慢\n【结尾钩子】…"
        self.assertEqual(novel_data.resolve_scene_pace({"beat": beat}), "慢")

    def test_format_emotion_anchor_from_field(self) -> None:
        import novel_data

        scene = {
            "emotion_anchor": {
                "target": "读者感到暗爽",
                "how": "全场安静三秒后有人鼓掌",
            }
        }
        text = novel_data.format_emotion_anchor_instruction(scene)
        self.assertIn("暗爽", text)
        self.assertIn("鼓掌", text)

    def test_get_scene_context_includes_emotion(self) -> None:
        import novel_data

        def fake_active():
            return {
                "title": "测试场",
                "beat": "目的：反击",
                "pace": "快",
                "emotion_anchor": {"target": "爽", "how": "围观反应"},
            }

        orig = novel_data.get_active_scene
        try:
            novel_data.get_active_scene = fake_active
            ctx = novel_data.get_scene_context_text()
            self.assertIn("情绪锚点", ctx)
            self.assertIn("围观反应", ctx)
        finally:
            novel_data.get_active_scene = orig

    def test_get_chapters_text_recent3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapters = Path(tmp)
            orig = main.CHAPTERS_DIR
            try:
                main.CHAPTERS_DIR = chapters
                (chapters / "ch001.md").write_text("第一章", encoding="utf-8")
                (chapters / "ch002.md").write_text("第二章", encoding="utf-8")
                text = main.get_chapters_text_for_scope(2, "recent3")
                self.assertIn("第一章", text or "")
                self.assertIn("第二章", text or "")
            finally:
                main.CHAPTERS_DIR = orig


class StyleInjectionTests(unittest.TestCase):
    def test_writing_instruction_era_language(self) -> None:
        from summarizer import WRITING_INSTRUCTION

        self.assertIn("语言时代约束", WRITING_INSTRUCTION)
        self.assertIn("窗口", WRITING_INSTRUCTION)
        self.assertIn("白话章回体", WRITING_INSTRUCTION)

    def test_get_world_block_includes_style(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            world = data / "world.md"
            style = data / "style.md"
            world.write_text("# 世界观\n快穿框架", encoding="utf-8")
            style.write_text("# 文风\n禁用：不禁", encoding="utf-8")
            orig_world = main.WORLD_FILE
            orig_style = main.STYLE_FILE
            try:
                main.WORLD_FILE = world
                main.STYLE_FILE = style
                block = main.get_world_block()
                self.assertIn("快穿框架", block)
                self.assertIn("文风锚点", block)
                self.assertIn("不禁", block)
            finally:
                main.WORLD_FILE = orig_world
                main.STYLE_FILE = orig_style

    def test_load_chat_prompts_fallback_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat_prompts.json"
            path.write_text('{"prompts": []}', encoding="utf-8")
            orig = main.CHAT_PROMPTS_FILE
            try:
                main.CHAT_PROMPTS_FILE = path
                data = main.load_chat_prompts()
                self.assertGreaterEqual(len(data["prompts"]), 5)
                self.assertTrue(
                    any("style.md" in p.get("content", "") for p in data["prompts"])
                )
            finally:
                main.CHAT_PROMPTS_FILE = orig

    def test_characters_block_includes_char_static(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            chars = data / "characters.md"
            static = data / "char_static.md"
            chars.write_text("# 人物\n甲", encoding="utf-8")
            static.write_text("## 锚点\n冷静", encoding="utf-8")
            orig_chars = main.CHARACTERS_FILE
            orig_static = main.CHAR_STATIC_FILE
            orig_current = main.CHAR_CURRENT_FILE
            try:
                main.CHARACTERS_FILE = chars
                main.CHAR_STATIC_FILE = static
                main.CHAR_CURRENT_FILE = data / "char_current.md"
                block = main.get_characters_block()
                self.assertIn("锚点", block)
                self.assertIn("char_static", block)
            finally:
                main.CHARACTERS_FILE = orig_chars
                main.CHAR_STATIC_FILE = orig_static
                main.CHAR_CURRENT_FILE = orig_current

    def test_build_cached_system_splits_hot_cold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            locked = data / "plot_threads_locked.md"
            active = data / "plot_threads_active.md"
            dynamic = data / "char_dynamic.md"
            locked.write_text("## 已钉死的细节\n- 年龄：23", encoding="utf-8")
            active.write_text("## 未回收\n- 伏笔A", encoding="utf-8")
            dynamic.write_text("## 当前\n试探期", encoding="utf-8")
            orig_locked = main.PLOT_THREADS_LOCKED_FILE
            orig_active = main.PLOT_THREADS_ACTIVE_FILE
            orig_dynamic = main.CHAR_DYNAMIC_FILE
            orig_plot = main.PLOT_THREADS_FILE
            try:
                main.PLOT_THREADS_LOCKED_FILE = locked
                main.PLOT_THREADS_ACTIVE_FILE = active
                main.CHAR_DYNAMIC_FILE = dynamic
                main.PLOT_THREADS_FILE = data / "plot_threads.md"
                system = main.build_cached_system("续写", provider="deepseek")
                text = str(system)
                self.assertIn("已钉死的细节", text)
                self.assertIn("未回收", text)
                self.assertIn("char_dynamic", text)
                self.assertIn("归档与细节钉子", text)
            finally:
                main.PLOT_THREADS_LOCKED_FILE = orig_locked
                main.PLOT_THREADS_ACTIVE_FILE = orig_active
                main.CHAR_DYNAMIC_FILE = orig_dynamic
                main.PLOT_THREADS_FILE = orig_plot


class PlanLockTests(unittest.TestCase):
    def test_mutate_plan_serializes(self) -> None:
        import novel_data

        novel_data._mutate_plan(lambda p: p.setdefault("chapters", {}))
        plan = novel_data.load_plan()
        self.assertIn("chapters", plan)


class CodexTests(unittest.TestCase):
    def test_sanitize_codex_name(self) -> None:
        import novel_data

        self.assertEqual(novel_data._sanitize_codex_name("a/b"), "a_b")
        self.assertEqual(novel_data._sanitize_codex_name('x:y'), "x_y")


class ApplyTurnTests(unittest.TestCase):
    def test_extract_chapter_body_from_user_message(self) -> None:
        text = (
            "【当前章节：第1章】\n\n# 第一章\n\n开头段落。\n\n"
            "【写作指令】\n续写 500 字"
        )
        body = main.extract_chapter_body_from_user_message(text)
        self.assertIn("开头段落", body or "")
        self.assertNotIn("写作指令", body or "")

    def test_extract_returns_none_without_block(self) -> None:
        self.assertIsNone(main.extract_chapter_body_from_user_message("续写吧"))

    def test_format_chapter_file_adds_header(self) -> None:
        out = main.format_chapter_file(2, "正文一段。")
        self.assertTrue(out.startswith("# 第2章"))

    def test_format_chapter_file_with_ai_title(self) -> None:
        raw = "【章节标题】暗流试探\n\n正文一段。"
        out = main.format_chapter_file(2, raw)
        self.assertIn("暗流试探", out)
        self.assertIn("正文一段", out)
        self.assertNotIn("【章节标题】", out)

    def test_append_to_empty_chapter_writes_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ch_dir = Path(tmp) / "chapters"
            ch_dir.mkdir()
            main.CHAPTERS_DIR = ch_dir
            path = ch_dir / "ch002.md"
            path.write_text("", encoding="utf-8")
            chars, title = main.append_to_chapter(
                "【章节标题】测试标题\n\n第一段正文。",
                path,
                chapter_num=2,
            )
            text = path.read_text(encoding="utf-8")
            self.assertGreater(chars, 0)
            self.assertEqual(title, "测试标题")
            self.assertIn("# 第2章 · 测试标题", text)
            self.assertIn("第一段正文", text)

    def test_extract_chapter_title_from_reply(self) -> None:
        title, body = main.extract_chapter_title_from_reply(
            "【章节标题】化妆间里的手册\n\n她翻开攻略手册。"
        )
        self.assertEqual(title, "化妆间里的手册")
        self.assertIn("攻略手册", body)

    def test_extract_title_from_markdown_header(self) -> None:
        title, body = main.extract_chapter_title_from_reply(
            "# 第2章 双向面试\n\n申请发出去的第三天晚上。"
        )
        self.assertEqual(title, "双向面试")
        self.assertIn("第三天晚上", body)

    def test_sync_chapter_title_from_file(self) -> None:
        import novel_data

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ch_dir = base / "chapters"
            ch_dir.mkdir()
            main.CHAPTERS_DIR = ch_dir
            plan_path = base / "plan.json"
            novel_data.PLAN_FILE = plan_path
            novel_data._plan_lock = novel_data.threading.Lock()
            novel_data._mutate_plan(
                lambda p: p.setdefault("chapters", {}).setdefault(
                    "2", {"title": "旧标题", "scenes": []}
                )
            )
            (ch_dir / "ch002.md").write_text(
                "# 第2章 双向面试\n\n正文。",
                encoding="utf-8",
            )
            synced = main.sync_chapter_title_from_file(2)
            self.assertEqual(synced, "双向面试")
            plan = novel_data.load_plan()
            self.assertEqual(plan["chapters"]["2"]["title"], "双向面试")

    def test_derive_chapter_title(self) -> None:
        import novel_data

        title = novel_data.derive_chapter_title_from_suggestion({
            "定位": "试探升级，关系进入拉锯",
            "核心事件": "女主换打法",
        })
        self.assertIn("试探升级", title)

    def test_ensure_chapter_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ch_dir = base / "chapters"
            ch_dir.mkdir()
            main.CHAPTERS_DIR = ch_dir
            r = main.ensure_chapter_file(2, "换一套打法")
            self.assertTrue(r["created"])
            text = (ch_dir / "ch002.md").read_text(encoding="utf-8")
            self.assertIn("第2章", text)
            self.assertIn("换一套打法", text)
            r2 = main.ensure_chapter_file(2, "x")
            self.assertFalse(r2["created"])

    def test_parse_outline_suggestions(self) -> None:
        import novel_data

        text = """【后续第1章（建议）】
定位：试探升级
核心事件：女主换非示弱打法
冲突/转折：林珩反将一军
章末钩子：发布会预告
伏笔动向：回收【三次接触】

【整体节奏提示】：张弛有度。"""
        items = novel_data.parse_outline_suggestions(text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["offset"], 1)
        self.assertIn("示弱", items[0]["核心事件"])

    def test_parse_outline_ignores_book_chapter_label(self) -> None:
        import novel_data

        text = """【后续第2章】
定位：换打法后的第一次实战
核心事件：旁观排练
冲突/转折：沉默对峙
章末钩子：进度条跳动
伏笔动向：推进【空椅子】"""
        items = novel_data.parse_outline_suggestions(text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["offset"], 1)

    def test_apply_outline_wrong_label_targets_next_chapter(self) -> None:
        import novel_data

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_path = base / "plan.json"
            plan_path.write_text(
                json.dumps({"active_scene_id": None, "chapters": {"1": {"title": "第一章", "scenes": []}}}),
                encoding="utf-8",
            )
            novel_data.PLAN_FILE = plan_path

            suggestion = novel_data.parse_outline_suggestions(
                """【后续第2章】
定位：换打法实战
核心事件：旁观排练
冲突/转折：对峙
章末钩子：系统跳动"""
            )[0]
            result = novel_data.apply_outline_suggestion_to_chapter(
                1,
                suggestion,
                target_offset=1,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["chapter_num"], 2)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertIn("2", plan["chapters"])
            self.assertNotIn("3", plan["chapters"])

    def test_restore_chat_session(self) -> None:
        from app_state import state

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            main.SESSION_FILE = base / "session_autosave.json"
            main.SESSION_MD_FILE = base / "session_autosave.md"
            main.SESSION_FILE.write_text(
                json.dumps(
                    {
                        "saved_at": "2026-01-01 12:00:00",
                        "conversation_history": [
                            {"role": "user", "content": "写一段"},
                            {"role": "assistant", "content": "夜风从窗缝里渗进来，带着潮气。" * 3},
                        ],
                        "appended_indices": [1],
                    }
                ),
                encoding="utf-8",
            )
            state.conversation_history.clear()
            state.appended_indices.clear()
            r = main.restore_chat_session()
            self.assertTrue(r["ok"])
            self.assertEqual(len(state.conversation_history), 2)
            self.assertIn(1, state.appended_indices)

    def test_delete_codex_entry(self) -> None:
        import novel_data

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            entries = base / "codex" / "entries"
            entries.mkdir(parents=True)
            active = base / "codex" / "active.json"
            active.write_text('{"active": ["测试条目"]}', encoding="utf-8")
            novel_data.CODEX_DIR = entries
            novel_data.CODEX_ACTIVE_FILE = active
            novel_data.BACKUPS_DIR = base / "backups"
            novel_data.create_codex_entry("测试条目", "# 测试\n")
            r = novel_data.delete_codex_entry("测试条目")
            self.assertTrue(r["ok"])
            self.assertFalse((entries / "测试条目.md").exists())
            self.assertEqual(novel_data.get_active_codex_ids(), [])


class APIErrorTests(unittest.TestCase):
    def test_classify_auth(self) -> None:
        from providers import APIError, _classify_api_error

        err = _classify_api_error(Exception("401 Unauthorized"))
        self.assertEqual(err.kind, "auth")
        self.assertIsInstance(err, APIError)

    def test_classify_server_error(self) -> None:
        from providers import APIError, _classify_api_error

        raw = (
            "Error code: 500 - {'type': 'error', 'error': "
            "{'type': 'api_error', 'message': 'Server exception, please try again later'}}"
        )
        err = _classify_api_error(Exception(raw))
        self.assertEqual(err.kind, "server_error")
        self.assertIsInstance(err, APIError)

    def test_classify_stream_disconnect(self) -> None:
        from main import _is_stream_disconnect_error
        from providers import APIError, _classify_api_error

        peer = (
            "peer closed connection without sending complete message body "
            "(incomplete chunked read)"
        )
        self.assertTrue(_is_stream_disconnect_error(_classify_api_error(Exception(peer))))
        self.assertTrue(_is_stream_disconnect_error(APIError(peer, kind="network")))
        self.assertFalse(_is_stream_disconnect_error(Exception("400 bad request")))


class ChapterSaveTests(unittest.TestCase):
    def test_instruction_save_mode(self) -> None:
        self.assertEqual(main.instruction_save_mode("续写 1500 字"), "append")
        self.assertEqual(main.instruction_save_mode("接着写一场戏"), "append")
        self.assertEqual(
            main.instruction_save_mode("字数控制在2000-3000，减ai腔调"), "replace"
        )
        beat_instruction = "【场景指令 Scene Beat】\n续写下一场\n\n继续写"
        self.assertEqual(main.instruction_save_mode(beat_instruction), "append")

    def test_resolve_write_chapter_from_scene(self) -> None:
        import novel_data

        novel_data._mutate_plan(
            lambda p: p.setdefault("chapters", {}).setdefault(
                "2",
                {
                    "title": "第二章",
                    "scenes": [
                        {
                            "id": "ch2_test_scene",
                            "title": "测试场景",
                            "beat": "",
                            "summary": "",
                            "done": False,
                        }
                    ],
                },
            )
        )
        num = main.resolve_write_chapter_num(None, "ch2_test_scene")
        self.assertEqual(num, 2)


class ContextLogTests(unittest.TestCase):
    def test_estimate_tokens_chinese(self) -> None:
        from main import _estimate_tokens

        self.assertGreater(_estimate_tokens("你好世界测试"), 2)

    def test_analyze_cached_system(self) -> None:
        from main import _analyze_system

        system = [
            {"type": "text", "text": "a" * 100},
            {"type": "text", "text": "b" * 200},
            {"type": "text", "text": "c" * 50},
            {"type": "text", "text": "d" * 10},
        ]
        parts = _analyze_system(system)
        self.assertEqual(parts["world"], 100)
        self.assertEqual(parts["characters"], 200)

    def test_build_context_report_warns_large_chapter(self) -> None:
        from main import _build_context_report

        report = _build_context_report(
            "# 世界观设定\n短",
            [
                {
                    "role": "user",
                    "content": "【当前章节：第1章】\n\n" + ("正" * 70_000),
                }
            ],
            tag="写书对话",
            provider="deepseek",
        )
        self.assertGreater(report["total_chars"], 60_000)
        self.assertTrue(any("章节正文" in w for w in report["warnings"]))


class ChapterInjectionTests(unittest.TestCase):
    def test_trim_clears_injection_when_chapter_block_removed(self) -> None:
        prev_inc = main.state.session_includes_chapter
        prev_last = main.state.last_injected_chapter_num
        try:
            main.state.session_includes_chapter = True
            main.state.last_injected_chapter_num = 3
            tail = []
            for i in range(20):
                tail.append({"role": "user", "content": f"指令{i}"})
                tail.append({"role": "assistant", "content": f"回复{i}" * 20})
            history = [
                {"role": "user", "content": "【当前章节：第3章】\n\n正文\n\n【写作指令】\n写"},
                {"role": "assistant", "content": "续写内容" * 20},
            ] + tail
            main.prepare_messages_for_context(history)
            self.assertFalse(main.state.session_includes_chapter)
        finally:
            main.state.session_includes_chapter = prev_inc
            main.state.last_injected_chapter_num = prev_last

    def test_resolve_chapter_prefers_write_chapter_num(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ch_dir = Path(tmp) / "chapters"
            ch_dir.mkdir()
            orig = main.CHAPTERS_DIR
            prev_w = main.state.write_chapter_num
            try:
                main.CHAPTERS_DIR = ch_dir
                (ch_dir / "ch002.md").write_text("# 第2章\n\n二章正文", encoding="utf-8")
                (ch_dir / "ch005.md").write_text("# 第5章\n\n五章正文", encoding="utf-8")
                main.state.write_chapter_num = 2
                resolved = main._resolve_chapter_num(None)
                self.assertEqual(resolved, (2, "# 第2章\n\n二章正文"))
            finally:
                main.CHAPTERS_DIR = orig
                main.state.write_chapter_num = prev_w


class SessionChapterCacheTests(unittest.TestCase):
    def test_save_chapter_by_num_clears_injection_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ch_dir = Path(tmp) / "chapters"
            ch_dir.mkdir()
            orig = main.CHAPTERS_DIR
            try:
                main.CHAPTERS_DIR = ch_dir
                (ch_dir / "ch003.md").write_text("# 第三章\n旧", encoding="utf-8")
                main.state.last_injected_chapter_num = 3
                main.state.session_includes_chapter = True
                main.save_chapter_by_num(3, "# 第三章\n新")
                self.assertFalse(main.state.session_includes_chapter)
            finally:
                main.CHAPTERS_DIR = orig

    def test_get_app_status_write_chapter_num(self) -> None:
        prev = main.state.write_chapter_num
        try:
            main.state.write_chapter_num = 7
            st = main.get_app_status()
            self.assertEqual(st["write_chapter_num"], 7)
        finally:
            main.state.write_chapter_num = prev


class GuideStatusTests(unittest.TestCase):
    def test_get_guide_status_shape(self) -> None:
        status = main.get_guide_status()
        self.assertTrue(status["ok"])
        self.assertIn(status["stage"], ("setup", "planning", "first_chapter", "writing"))
        for key in ("world", "char_static", "style", "char_dynamic", "plot_threads_active"):
            self.assertIn(key, status["files"])
        todos = status["post_chapter_todos"]
        for key in (
            "summary",
            "char_dynamic",
            "plot_threads",
            "char_dynamic_never",
            "plot_threads_never",
            "archive",
        ):
            self.assertIn(key, todos)
            self.assertIsInstance(todos[key], bool)

    def test_latest_chapter_summary_requires_exact_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            ch_dir = data / "chapters"
            ch_dir.mkdir()
            orig = {
                "CHAPTERS": main.CHAPTERS_DIR,
                "RECENT": main.SUMMARIES_RECENT_FILE,
                "ARCHIVE": main.SUMMARIES_ARCHIVE_FILE,
            }
            try:
                main.CHAPTERS_DIR = ch_dir
                (ch_dir / "ch002.md").write_text("# 第二章\n正文", encoding="utf-8")
                main.SUMMARIES_RECENT_FILE = data / "summaries_recent.md"
                main.SUMMARIES_ARCHIVE_FILE = data / "summaries_archive.md"
                main.SUMMARIES_RECENT_FILE.write_text(
                    "【第5章】旧书残留概述\n", encoding="utf-8"
                )
                main.SUMMARIES_ARCHIVE_FILE.write_text("", encoding="utf-8")
                status = main.get_guide_status()
                self.assertEqual(status["latest_chapter_num"], 2)
                self.assertFalse(status["latest_chapter_has_summary"])
                self.assertTrue(status["post_chapter_todos"]["summary"])
            finally:
                main.CHAPTERS_DIR = orig["CHAPTERS"]
                main.SUMMARIES_RECENT_FILE = orig["RECENT"]
                main.SUMMARIES_ARCHIVE_FILE = orig["ARCHIVE"]

    def test_maint_file_content_clears_never_todos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            ch_dir = data / "chapters"
            ch_dir.mkdir()
            dynamic = data / "char_dynamic.md"
            active = data / "plot_threads_active.md"
            orig = {
                "CHAPTERS": main.CHAPTERS_DIR,
                "DYNAMIC": main.CHAR_DYNAMIC_FILE,
                "ACTIVE": main.PLOT_THREADS_ACTIVE_FILE,
            }
            try:
                tpl_dynamic = main.INITIAL_FILE_TEMPLATES["char_dynamic"]
                tpl_active = main.INITIAL_FILE_TEMPLATES["plot_threads_active"]
                main.CHAPTERS_DIR = ch_dir
                (ch_dir / "ch001.md").write_text("# 第一章\n正文", encoding="utf-8")
                main.CHAR_DYNAMIC_FILE = dynamic
                main.PLOT_THREADS_ACTIVE_FILE = active
                main.CODEX_FILES["char_dynamic"] = dynamic
                main.CODEX_FILES["plot_threads_active"] = active
                dynamic.write_text(tpl_dynamic, encoding="utf-8")
                active.write_text(tpl_active, encoding="utf-8")
                status = main.get_guide_status()
                self.assertTrue(status["post_chapter_todos"]["char_dynamic_never"])
                dynamic.write_text(
                    dynamic.read_text(encoding="utf-8").replace(
                        "- 当前状态：\n", "- 当前状态：刚穿入，正在摸底\n"
                    ),
                    encoding="utf-8",
                )
                status = main.get_guide_status()
                self.assertFalse(status["post_chapter_todos"]["char_dynamic_never"])
            finally:
                main.CHAPTERS_DIR = orig["CHAPTERS"]
                main.CHAR_DYNAMIC_FILE = orig["DYNAMIC"]
                main.PLOT_THREADS_ACTIVE_FILE = orig["ACTIVE"]
                main.CODEX_FILES["char_dynamic"] = orig["DYNAMIC"]
                main.CODEX_FILES["plot_threads_active"] = orig["ACTIVE"]


class FreeChatThreadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_threads = list(main.state.free_chat_threads)
        self._orig_active = main.state.free_chat_active_thread_id
        self._orig_history = list(main.state.free_chat_history)
        self._orig_file = main.FREE_CHAT_FILE
        main.state.free_chat_threads = []
        main.state.free_chat_active_thread_id = ""
        main.state.free_chat_history = []

    def tearDown(self) -> None:
        main.state.free_chat_threads = self._orig_threads
        main.state.free_chat_active_thread_id = self._orig_active
        main.state.free_chat_history = self._orig_history
        main.FREE_CHAT_FILE = self._orig_file

    def test_legacy_free_chat_migrates_to_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "free_chat.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": "deepseek",
                        "messages": [
                            {"role": "user", "content": "讨论世界观"},
                            {"role": "assistant", "content": "好的"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            main.FREE_CHAT_FILE = path
            main.load_free_chat()
            self.assertEqual(len(main.state.free_chat_threads), 1)
            self.assertEqual(main.state.free_chat_threads[0]["title"], "讨论世界观")
            self.assertEqual(len(main.state.free_chat_history), 2)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("threads", saved)
            self.assertEqual(len(saved["threads"]), 1)

    def test_create_and_switch_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main.FREE_CHAT_FILE = Path(tmp) / "free_chat.json"
            main._ensure_free_chat_threads()
            first_id = main.state.free_chat_active_thread_id
            main.state.free_chat_history.append(
                {"role": "user", "content": "第一条"},
            )
            main.save_free_chat()

            created = main.create_free_chat_thread(title="人物设定")
            self.assertTrue(created["ok"])
            second_id = created["thread"]["id"]
            self.assertNotEqual(second_id, first_id)
            self.assertEqual(main.state.free_chat_history, [])

            switched = main.switch_free_chat_thread(first_id)
            self.assertTrue(switched["ok"])
            self.assertEqual(len(switched["messages"]), 1)
            self.assertEqual(switched["messages"][0]["content"], "第一条")

    def test_delete_free_chat_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main.FREE_CHAT_FILE = Path(tmp) / "free_chat.json"
            main._ensure_free_chat_threads()
            main.state.free_chat_history = [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"},
                {"role": "user", "content": "c"},
            ]
            main._persist_active_thread_messages()
            main.save_free_chat()

            bad = main.delete_free_chat_message(9)
            self.assertFalse(bad["ok"])

            ok = main.delete_free_chat_message(1)
            self.assertTrue(ok["ok"])
            self.assertEqual(len(ok["messages"]), 2)
            self.assertEqual(ok["messages"][0]["content"], "a")
            self.assertEqual(ok["messages"][1]["content"], "c")

            saved = json.loads(main.FREE_CHAT_FILE.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["threads"][0]["messages"]), 2)


class BatchWorldTests(unittest.TestCase):
    def test_parse_chapter_spans(self) -> None:
        import batch_world

        spans = batch_world.parse_chapter_spans("第1-2章 · 初见 · 第15章")
        self.assertIn((1, 2), spans)
        self.assertIn((15, 15), spans)

    def test_iter_chapter_chunks(self) -> None:
        import batch_world

        chunks = batch_world.iter_chapter_chunks(1, 15, chunk_size=5)
        self.assertEqual(chunks, [(1, 5), (6, 10), (11, 15)])

    def test_build_chapters_text_block_truncates(self) -> None:
        import batch_world

        def read_ch(n: int) -> str:
            return f"第{n}章" + ("正文" * 5000)

        text, truncated, used = batch_world.build_chapters_text_block(
            [1, 2],
            read_ch,
            max_total_chars=8000,
            max_chapter_chars=3000,
        )
        self.assertTrue(truncated)
        self.assertGreater(len(text), 0)
        self.assertGreaterEqual(len(used), 1)

    def test_infer_world_range_from_plan(self) -> None:
        import batch_world
        import novel_data

        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "chapters": {
                            "1": {
                                "scenes": [
                                    {"summary": "第1-2章"},
                                    {"summary": "第15章"},
                                ]
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            orig = novel_data.PLAN_FILE
            novel_data.PLAN_FILE = plan_path
            try:
                cf, ct = batch_world.infer_world_chapter_range()
                self.assertEqual(cf, 1)
                self.assertEqual(ct, 15)
            finally:
                novel_data.PLAN_FILE = orig

    def test_world_batch_status_written(self) -> None:
        import batch_world

        def read_ch(n: int) -> str:
            return "有正文" if n <= 3 else ""

        status = batch_world.get_world_batch_status(read_chapter=read_ch)
        self.assertGreaterEqual(status["written_count"], 0)

    def test_review_plan_token_estimate(self) -> None:
        import batch_world
        import novel_data

        prose = "正文" * 1600  # 3200 字/章

        def read_ch(n: int) -> str:
            return f"# 第{n}章\n\n{prose}" if n <= 5 else ""

        def read_text(_path) -> str:
            return "设定" * 200

        def get_char() -> str:
            return "人物" * 100

        def build_sys(prompt, **kwargs):
            return [{"type": "text", "content": prompt[:500]}]

        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "chapters": {
                            "1": {"scenes": [{"summary": "第1-15章"}]},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            orig = novel_data.PLAN_FILE
            novel_data.PLAN_FILE = plan_path
            try:
                plan = batch_world.build_world_batch_review_plan(
                    read_chapter=read_ch,
                    read_text=read_text,
                    get_char_context_for_check=get_char,
                    build_cached_system=build_sys,
                    summaries_for_scope_fn=lambda _n, _s: "概述" * 50,
                    cross_chapter_user_message_fn=lambda *a, **k: "跨章" * 80,
                    world_file=Path("w.md"),
                    characters_file=Path("c.md"),
                    plot_locked_file=Path("l.md"),
                    plot_active_file=Path("a.md"),
                )
            finally:
                novel_data.PLAN_FILE = orig

        self.assertTrue(plan.get("ok"))
        self.assertGreater(plan["total_prose_chars"], 10000)
        self.assertGreater(plan["total_est_input_tokens"], 5000)
        md = batch_world.format_review_plan_markdown(plan)
        self.assertIn("发送预览", md)
        self.assertIn("tokens", md)


class TestWorldRemediate(unittest.TestCase):
    def test_parse_remediate_diagnose(self) -> None:
        from summarizer import parse_remediate_diagnose

        reply = (
            '说明\n```remediate-diagnose-json\n'
            '{"num":2,"action":"patch","issues":[{"severity":"must_fix",'
            '"summary":"钩子弱","location":"开篇"}],"skip_reason":""}\n```'
        )
        data, err = parse_remediate_diagnose(reply)
        self.assertIsNone(err or None)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data["action"], "patch")
        self.assertEqual(len(data["issues"]), 1)

    def test_format_closure_report(self) -> None:
        from summarizer import format_remediate_closure_report

        md = format_remediate_closure_report(
            "测试世界",
            1,
            2,
            [
                {
                    "num": 1,
                    "action": "patch",
                    "changes": [
                        {
                            "issue": "钩子弱",
                            "done": "加入冲突",
                            "location": "第2段",
                        }
                    ],
                    "skipped": [],
                },
                {"num": 2, "action": "skip", "skip_reason": "节奏可保留"},
            ],
        )
        self.assertIn("世界闭环", md)
        self.assertIn("已改", md)
        self.assertIn("未改动", md)

    def test_snapshot_and_revert(self) -> None:
        import batch_remediate

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            job_id = "testjob01"
            root = batch_remediate.job_path(data, job_id)
            root.mkdir(parents=True)
            ch_path = root / "before" / "ch001.md"
            ch_path.parent.mkdir(parents=True, exist_ok=True)
            ch_path.write_text("# 第1章\n\n旧正文\n", encoding="utf-8")

            written: dict[int, str] = {}

            def write_ch(n: int, t: str) -> None:
                written[n] = t

            batch_remediate.save_job(
                data,
                {"id": job_id, "status": "completed", "targets": [1]},
            )
            r = batch_remediate.revert_chapter_from_job(
                data,
                job_id,
                1,
                write_chapter=write_ch,
                sync_title=lambda _n: None,
            )
            self.assertTrue(r.get("ok"))
            self.assertIn("旧正文", written.get(1, ""))
            self.assertIn("正文", r.get("reverted", []))
            self.assertIn("档案", r.get("warning", ""))

    def test_parse_bulk_summaries_and_state(self) -> None:
        from summarizer import parse_bulk_state, parse_bulk_summaries

        sum_reply = (
            '```bulk-summaries-json\n'
            '{"summaries":[{"num":1,"text":"【第1章：测】\\n核心事件：a"}]}\n```'
        )
        data, err = parse_bulk_summaries(sum_reply)
        self.assertIsNone(err or None)
        assert data is not None
        self.assertEqual(len(data["summaries"]), 1)

        state_reply = (
            '```bulk-state-json\n'
            '{"char_dynamic":"# 动态","plot_threads_active":"# 伏笔"}\n```'
        )
        sdata, serr = parse_bulk_state(state_reply)
        self.assertIsNone(serr or None)
        assert sdata is not None
        self.assertIn("动态", sdata["char_dynamic"])

    def test_persist_bulk_summaries(self) -> None:
        import main

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            recent = data / "summaries_recent.md"
            compat = data / "summaries.md"
            recent.write_text("# 近期\n\n", encoding="utf-8")
            compat.write_text("# 兼容\n\n", encoding="utf-8")
            orig_r = main.SUMMARIES_RECENT_FILE
            orig_s = main.SUMMARIES_FILE
            try:
                main.SUMMARIES_RECENT_FILE = recent
                main.SUMMARIES_FILE = compat
                ok, errors, count = main._persist_bulk_summaries(
                    {
                        "summaries": [
                            {"num": 1, "text": "【第1章：测】\n核心事件：x"},
                            {"num": 2, "text": "【第2章：测】\n核心事件：y"},
                        ]
                    }
                )
                self.assertTrue(ok)
                self.assertEqual(count, 2)
                self.assertFalse(errors)
                text = recent.read_text(encoding="utf-8")
                self.assertIn("【第1章", text)
                self.assertIn("【第2章", text)
            finally:
                main.SUMMARIES_RECENT_FILE = orig_r
                main.SUMMARIES_FILE = orig_s

    def test_remediate_chapter_standalone_mock(self) -> None:
        import main

        with tempfile.TemporaryDirectory() as tmp:
            ch_dir = Path(tmp) / "chapters"
            ch_dir.mkdir()
            ch_file = ch_dir / "ch001.md"
            ch_file.write_text("# 第1章 · 旧\n\n旧内容。\n", encoding="utf-8")

            orig_chapters = main.CHAPTERS_DIR
            orig_call = main.call_api
            orig_info = main.get_last_call_info
            orig_build = main.build_cached_system
            main.CHAPTERS_DIR = ch_dir
            try:

                def fake_api(_sys, _msgs, **kwargs):
                    return "【章节标题】新标题\n\n新正文段落。\n"

                main.call_api = fake_api
                main.get_last_call_info = lambda: {"cost": 0.01}
                main.build_cached_system = lambda p, **k: p

                r = main.remediate_chapter_standalone(
                    1,
                    "【文风参考】重写本章",
                )
                self.assertTrue(r.get("ok"))
                text = ch_file.read_text(encoding="utf-8")
                self.assertIn("新正文", text)
                self.assertIn("新标题", text)
            finally:
                main.CHAPTERS_DIR = orig_chapters
                main.call_api = orig_call
                main.get_last_call_info = orig_info
                main.build_cached_system = orig_build


class DeconstructPromptTests(unittest.TestCase):
    def test_build_deconstruct_user_message(self) -> None:
        from summarizer import build_deconstruct_user_message

        msg = build_deconstruct_user_message(
            "她推开门，全场安静了。",
            source_label="测试章",
            book_title="我的书",
            world_excerpt="古代乱世",
        )
        self.assertIn("测试章", msg)
        self.assertIn("我的书", msg)
        self.assertIn("推开门", msg)


class BookContextTests(unittest.TestCase):
    def test_create_and_switch_book(self) -> None:
        import book_context

        with tempfile.TemporaryDirectory() as tmp:
            lib = Path(tmp) / "library"
            books = lib / "books"
            books.mkdir(parents=True)
            index = {
                "version": 1,
                "active_book_id": "a",
                "books": [{"id": "a", "title": "书A", "type": "novel"}],
            }
            (lib / "index.json").write_text(
                json.dumps(index, ensure_ascii=False), encoding="utf-8"
            )
            book_a = books / "a"
            book_a.mkdir()
            (book_a / "project.json").write_text(
                json.dumps(
                    {"title": "书A", "type": "novel", "world_label": "", "tagline": ""},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            orig_lib = book_context.LIBRARY_DIR
            orig_books = book_context.BOOKS_DIR
            orig_index = book_context.INDEX_FILE
            orig_ctx = book_context._context
            try:
                book_context.LIBRARY_DIR = lib
                book_context.BOOKS_DIR = books
                book_context.INDEX_FILE = lib / "index.json"
                book_context._context = None
                book_context.init_library(book_id="a")

                r = book_context.create_book(title="短篇测试", book_type="short")
                self.assertTrue(r.get("ok"))
                self.assertEqual(r["book"]["type"], "short")
                self.assertTrue(book_context.is_short_book(r["book_id"]))

                sw = book_context.switch_book("a")
                self.assertTrue(sw.get("ok"))
                self.assertFalse(book_context.is_short_book())
            finally:
                book_context.LIBRARY_DIR = orig_lib
                book_context.BOOKS_DIR = orig_books
                book_context.INDEX_FILE = orig_index
                book_context._context = orig_ctx


class ReviewPromptTests(unittest.TestCase):
    def test_resolve_profile_by_type_platform(self) -> None:
        import review_prompts

        self.assertEqual(
            review_prompts.resolve_profile_id("world", "tomato"), "world-tomato"
        )
        self.assertEqual(
            review_prompts.resolve_profile_id("short", "jjwxc"), "short-jjwxc"
        )
        self.assertEqual(
            review_prompts.resolve_profile_id("short", "qimao"), "short-general"
        )

    def test_resolve_beat_for_prose_chapter(self) -> None:
        import batch_world
        import novel_data

        plan = {
            "active_scene_id": None,
            "chapters": {
                "1": {
                    "title": "世界一",
                    "scenes": [
                        {
                            "id": "s1",
                            "title": "穿入",
                            "summary": "第1-2章",
                            "beat": "【场景目的】穿入立人设（第1-2章）",
                        },
                        {
                            "id": "s2",
                            "title": "初见",
                            "summary": "第3-4章",
                            "beat": "【场景目的】遇见男主",
                        },
                    ],
                }
            },
        }
        orig_load = novel_data.load_plan
        try:
            novel_data.load_plan = lambda: plan  # type: ignore[method-assign]
            m1 = batch_world.resolve_beat_for_prose_chapter(1)
            self.assertIsNotNone(m1)
            assert m1 is not None
            self.assertEqual(m1["scene_id"], "s1")
            self.assertEqual(m1["span_from"], 1)
            self.assertEqual(m1["span_to"], 2)
            self.assertEqual(m1["chapter_index_in_span"], 1)
            m2 = batch_world.resolve_beat_for_prose_chapter(2)
            assert m2 is not None
            self.assertEqual(m2["chapter_index_in_span"], 2)
            m4 = batch_world.resolve_beat_for_prose_chapter(4)
            assert m4 is not None
            self.assertEqual(m4["scene_id"], "s2")
        finally:
            novel_data.load_plan = orig_load  # type: ignore[method-assign]

    def test_build_chapter_generate_instruction(self) -> None:
        import batch_generate

        meta = {
            "scene_title": "穿入",
            "span_from": 1,
            "span_to": 2,
            "chapter_index_in_span": 2,
            "pace": "快",
        }
        text = batch_generate.build_chapter_generate_instruction(2, meta, prev_tail="上一章尾巴")
        self.assertIn("第 2 章", text)
        self.assertIn("上一章尾巴", text)

    def test_load_world_tomato_prompt(self) -> None:
        import review_prompts

        text, pid = review_prompts.load_prompt_text("world-tomato")
        self.assertEqual(pid, "world-tomato")
        self.assertTrue(review_prompts.is_rewrite_only_profile(pid))
        self.assertIn("唯一交付物", text)
        self.assertIn("番茄/七猫", text)

    def test_active_profile_for_project(self) -> None:
        import review_prompts

        meta = review_prompts.active_profile_for_project(
            {"type": "world", "platform": "tomato"}
        )
        self.assertEqual(meta["profile_id"], "world-tomato")
        self.assertEqual(meta["book_type_label"], "快穿")
        self.assertTrue(meta.get("rewrite_only"))

    def test_world_qimao_includes_tomato_prompt(self) -> None:
        import review_prompts

        text, pid = review_prompts.load_prompt_text("world-qimao")
        self.assertEqual(pid, "world-qimao")
        self.assertIn("唯一交付物", text)

    def test_rewrite_only_skips_revise_appendix(self) -> None:
        import review_prompts

        text, _pid = review_prompts.load_prompt_text(
            "world-tomato", include_revise=True
        )
        self.assertNotIn("改稿阶段", text)

    def test_load_prompt_with_revise_appendix(self) -> None:
        import review_prompts

        text, _pid = review_prompts.load_prompt_text(
            "novel-tomato", include_revise=True
        )
        self.assertIn("改稿阶段", text)

    def test_split_female_review_revise_reply(self) -> None:
        from summarizer import split_female_review_revise_reply

        raw = (
            "【这个世界值不值得写】\n值得\n\n"
            "---\n\n"
            "# 改稿正文\n\n"
            "【章节标题】测试章\n\n"
            "正文第一段。"
        )
        review, revised = split_female_review_revise_reply(raw)
        self.assertIn("值得", review)
        self.assertIn("【章节标题】", revised)
        self.assertIn("正文第一段", revised)


class TestRuntimeLog(unittest.TestCase):
    def test_env_detection_and_entries(self) -> None:
        import os
        import tempfile
        import runtime_log
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            dev_root = Path(tmp) / "novel_writer"
            write_root = Path(tmp) / "novel_writer_write"
            dev_root.mkdir()
            write_root.mkdir()

            os.environ["NOVEL_RUNTIME_LOG"] = "1"
            os.environ["NOVEL_RUNTIME_LOG_DEBUG"] = "1"
            try:
                runtime_log.init_runtime_log(dev_root)
                self.assertEqual(runtime_log.runtime_env(), "dev")
                eid = runtime_log.log_error("test", "t", "dev error")
                self.assertIsNotNone(eid)
                rows = runtime_log.list_entries(limit=5)
                self.assertEqual(len(rows), 1)
                full = runtime_log.get_entry(eid or "")
                self.assertIsNotNone(full)
                assert full is not None
                self.assertIn("dev error", full["message"])

                runtime_log.init_runtime_log(write_root)
                self.assertEqual(runtime_log.runtime_env(), "write")
                runtime_log.log_warn("test", "t", "write warn")
                wrows = runtime_log.list_entries(limit=5)
                self.assertEqual(len(wrows), 1)
                self.assertNotEqual(
                    dev_root / "logs/dev/runtime.jsonl",
                    write_root / "logs/write/runtime.jsonl",
                )
            finally:
                os.environ.pop("NOVEL_RUNTIME_LOG", None)
                os.environ.pop("NOVEL_RUNTIME_LOG_DEBUG", None)


if __name__ == "__main__":
    unittest.main()
