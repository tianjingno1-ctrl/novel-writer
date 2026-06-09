"""CLI 入口（P3-5b）：REPL 循环 + do_* 命令。LLM/章节 helper 仍 lazy import main。"""

from __future__ import annotations

import atexit
import re
import signal
from datetime import datetime

import config
from app import paths as _paths
from app import writing_session as ws
from app import writing_turns as wt
from app_state import state


def do_undo() -> None:
    result = wt.undo_last_chapter_append()
    if result.get("ok"):
        print(f"↩️  已撤销上次章节写入（{result['file']}）")
    else:
        print(result.get("error", "撤销失败"))


def do_restore() -> None:
    result = ws.restore_chat_session()
    if not result.get("ok"):
        print(result.get("error", "没有可恢复的会话备份"))
        return
    print(
        f"✅ 已恢复会话（{result.get('saved_at', '')}，"
        f"{result.get('message_count', 0)} 条消息）"
    )
    print(f"   详细内容见：{_paths.resolved('SESSION_MD_FILE')}")
    pending = result.get("pending_writes", 0)
    if pending:
        print(f"💡 仍有 {pending} 条正文可能未写入章节，建议输入 /save 补存")


def do_save() -> None:
    import main as m

    chapter_count = m.flush_chapter_writes()
    session_saved = ws.save_session("manual", silent=True)
    if chapter_count or session_saved:
        if session_saved:
            print(f"💾 会话已保存 → {_paths.resolved('SESSION_MD_FILE')}")
        return
    print("当前没有需要保存的内容")


def do_writing(instruction: str) -> None:
    import main as m
    from summarizer import WRITING_INSTRUCTION

    latest = m.get_latest_chapter()
    if latest is None:
        print("提示：data/chapters/ 中尚无章节文件，将仅根据指令回复。")
        chapter_num, chapter_content = 0, "（尚无章节正文）"
    else:
        chapter_num, _, chapter_content = latest

    if chapter_num > 0:
        state.write_chapter_num = chapter_num
    if not state.session_includes_chapter:
        user_content = (
            f"【当前章节：第{chapter_num}章】\n\n"
            f"{chapter_content}\n\n"
            f"【写作指令】\n{instruction}"
        )
        state.session_includes_chapter = True
        state.last_injected_chapter_num = chapter_num
    else:
        user_content = instruction

    state.conversation_history.append({"role": "user", "content": user_content})

    system = m.build_cached_system(WRITING_INSTRUCTION)
    reply = m.call_api(system, m.prepare_messages_for_context(state.conversation_history))
    if reply is None:
        state.conversation_history.pop()
        return

    reply = m.sanitize_chapter_text(reply)
    print(f"\n{reply}\n")
    state.conversation_history.append({"role": "assistant", "content": reply})
    m.save_chapter_after_reply(
        reply,
        len(state.conversation_history) - 1,
        write_chapter_num=chapter_num if chapter_num > 0 else None,
        instruction=instruction,
    )
    ws.save_session("auto", silent=True)


def do_summary() -> None:
    import main as m
    from summarizer import SUMMARY_SYSTEM, build_summary_user_message

    latest = m.get_latest_chapter()
    if latest is None:
        print("错误：没有找到章节文件（data/chapters/ch001.md 等）")
        return

    chapter_num, _, content = latest
    if not content.strip():
        print(f"错误：第{chapter_num}章内容为空")
        return

    pid = config.SUMMARY_PROVIDER
    cfg = config.get_provider_config(pid)
    system = m.build_cached_system(SUMMARY_SYSTEM, provider=pid)
    messages = [{"role": "user", "content": build_summary_user_message(chapter_num, content)}]
    reply = m.call_api(system, messages, provider=pid, tag="概述")
    if reply is None:
        return

    append_text = f"\n{reply.strip()}\n"
    m.write_text(
        _paths.resolved("SUMMARIES_RECENT_FILE"),
        append_text,
        append=True,
        history_source="summary",
        chapter_num=chapter_num,
    )
    m.write_text(
        _paths.resolved("SUMMARIES_FILE"),
        append_text,
        append=True,
        history_source="summary",
        chapter_num=chapter_num,
    )
    print(f"\n概述已追加至 summaries_recent.md（{cfg['name']}）；仅④层变动，③层归档缓存可保持命中")
    print(reply)


def do_check() -> None:
    import main as m
    from summarizer import CHECK_SYSTEM, build_check_user_message

    latest = m.get_latest_chapter()
    if latest is None:
        print("错误：没有找到章节文件")
        return

    chapter_num, _, chapter_content = latest
    world = m.read_text(_paths.resolved("WORLD_FILE"))
    characters = m.read_text(_paths.resolved("CHARACTERS_FILE"))
    pid = config.CHECK_PROVIDER
    system = m.build_cached_system(CHECK_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_check_user_message(
                world,
                characters,
                m.get_char_context_for_check(),
                m.get_summaries_combined(),
                chapter_num,
                chapter_content,
            ),
        }
    ]
    reply = m.call_api(system, messages, provider=pid, tag="检查")
    if reply is not None:
        print(f"\n{reply}\n")


def do_outline(next_count: int = 3) -> None:
    import main as m
    from summarizer import OUTLINE_SYSTEM, build_outline_user_message

    err = m._outline_context_ready()
    if err:
        print(f"错误：{err}")
        return

    n = max(1, min(10, next_count))
    pid = config.OUTLINE_PROVIDER
    cfg = config.get_provider_config(pid)
    system = m.build_cached_system(OUTLINE_SYSTEM, provider=pid)
    messages = [
        {
            "role": "user",
            "content": build_outline_user_message(
                m.read_text(_paths.resolved("WORLD_FILE")),
                m.get_char_context_for_check(),
                m.get_summaries_combined(),
                m._read_plot_active(),
                n,
            ),
        }
    ]
    reply = m.call_api(system, messages, provider=pid, tag="续章灵感")
    if reply is not None:
        print(f"\n（{cfg['name']} · 后续 {n} 章建议）\n{reply}\n")


def do_patch(content: str) -> None:
    import main as m

    if not content.strip():
        print("用法：/patch 补充内容...")
        return

    chars_file = _paths.resolved("CHARACTERS_FILE")
    draft_num = len(re.findall(r"【设定补充-第\d+稿", m.read_text(chars_file))) + 1
    date_str = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n【设定补充-第{draft_num}稿-{date_str}】：{content.strip()}\n"
    m.write_text(chars_file, entry, append=True)
    print(f"已追加到 characters.md（第{draft_num}稿）")


def do_heartbeat_toggle() -> None:
    if not config.supports_prompt_cache():
        print("当前提供商不支持 Prompt Cache，心跳无意义")
        return
    config.HEARTBEAT_ENABLED = not config.HEARTBEAT_ENABLED
    status = "已开启" if config.HEARTBEAT_ENABLED else "已关闭"
    print(f"智能心跳{status}")


def do_provider(arg: str) -> None:
    from providers import reset_client

    arg = arg.strip().lower()
    if not arg:
        print("可用提供商：")
        print(config.list_providers())
        print("\n用法：/provider kie | kie-opus | kie-opus-47 | kie-opus-48 | deepseek")
        print("（只切换主力写作；/summary、/check、/outline 见 config.py）")
        return

    if arg not in config.PROVIDERS:
        print(f"未知提供商：{arg}")
        print(config.list_providers())
        return

    config.PROVIDER = arg
    config.save_runtime_settings()
    reset_client(arg)
    cfg = config.get_provider_config()
    print(f"✅ 主力写作已切换至 {cfg['name']}（模型: {cfg['model']}）")
    print(
        f"   /summary → {config.SUMMARY_PROVIDER}  |  "
        f"/check → {config.CHECK_PROVIDER}  |  /outline → {config.OUTLINE_PROVIDER}（不变）"
    )
    if not config.supports_prompt_cache():
        print("   该提供商不支持 Prompt Cache，心跳已自动跳过")
    elif not config.is_api_key_configured():
        print(f"   ⚠️  请配置 {cfg['api_key_env']}")


def do_cost() -> None:
    cost_log = _paths.resolved("COST_LOG")
    cost_jsonl = _paths.resolved("COST_LOG_JSONL")
    print(f"累计总费用（预估）：${state.total_cost:.6f}")
    if cost_jsonl.exists():
        print(f"详细记录见：{cost_jsonl}")
    elif cost_log.exists():
        print(f"详细记录见：{cost_log}（旧格式）")


def do_new() -> None:
    import main as m

    pending = m.count_unsaved_chapter_turns()
    if pending:
        print(f"⚠️  还有 {pending} 条正文未写入章节，正在补存…")
        m.flush_chapter_writes()
    ws.backup_session_before_clear()
    state.conversation_history.clear()
    state.session_includes_chapter = False
    state.write_chapter_num = 0
    state.last_injected_chapter_num = 0
    state.appended_indices.clear()
    ws.clear_session_files()
    print("对话历史已清空（文档缓存保留）")


def print_help() -> None:
    print("""
可用命令：
  /summary   — 生成概述（默认 DeepSeek，config.SUMMARY_PROVIDER）
  /check     — 连续性检查（默认 DeepSeek，config.CHECK_PROVIDER）
  /outline [N] — 续章剧情灵感，默认后续 3 章（config.OUTLINE_PROVIDER）
  /patch     — 在 characters.md 末尾追加设定补充
  /heartbeat — 开关智能心跳（续命缓存，仅 kie）
  /provider  — 切换主力写作提供商（/summary /check 独立配置）
  /cost      — 显示累计 API 费用
  /new       — 清空对话历史（保留文档缓存）
  /save      — 将未写入的 AI 正文补存到章节 + 保存会话
  /undo      — 撤销上一次自动写入章节的正文
  /restore   — 恢复上次自动保存的会话
  /help      — 显示此帮助
  /quit      — 退出程序

直接输入文字即为写作指令（默认模式）。
""")


def remind_unsaved_on_exit() -> None:
    import main as m

    if not state.conversation_history:
        return

    pending = m.count_unsaved_chapter_turns()
    chapter_num = ws._session_chapter_num()
    session_md = _paths.resolved("SESSION_MD_FILE")

    print()
    if pending > 0:
        print(f"⚠️  提醒：还有 {pending} 条 AI 正文未写入章节！")
        print("   正在尝试补存…")
        m.flush_chapter_writes()
        pending = m.count_unsaved_chapter_turns()
        if pending > 0:
            print(f"   仍有 {pending} 条未保存，请手动执行 /save 或查看 {session_md}")
    elif config.AUTO_APPEND_CHAPTER and chapter_num:
        print(f"✅ 本章正文已全部自动保存到 data/chapters/ch{chapter_num:03d}.md")
    print(f"   会话备份：{session_md}")
    print("   下次启动输入 /restore 可继续对话")


def graceful_exit(message: str = "再见！") -> None:
    import main as m

    if m._exiting:
        return
    m._exiting = True
    m._heartbeat_stop.set()
    ws.save_session("exit", silent=True)
    remind_unsaved_on_exit()
    print(message)
    raise SystemExit(0)


def _handle_exit_signal(signum, frame) -> None:
    sig_name = "Ctrl+C" if signum == signal.SIGINT else f"信号{signum}"
    print(f"\n⚠️  检测到异常关闭（{sig_name}），正在保存会话…")
    graceful_exit("已保存，安全退出。")


def _atexit_save() -> None:
    import main as m

    if m._exiting:
        return
    m._heartbeat_stop.set()
    ws.save_session("atexit", silent=True)
    if state.conversation_history:
        remind_unsaved_on_exit()


def setup_exit_handlers() -> None:
    atexit.register(_atexit_save)
    signal.signal(signal.SIGINT, _handle_exit_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_exit_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle_exit_signal)


def print_startup_banner() -> None:
    import main as m

    latest = m.get_latest_chapter()
    chapter_str = f"第{latest[0]}章" if latest else "（尚无章节）"
    summary_count = m.count_summaries()

    cfg = config.get_provider_config()
    sum_cfg = config.get_provider_config(config.SUMMARY_PROVIDER)
    chk_cfg = config.get_provider_config(config.CHECK_PROVIDER)
    out_cfg = config.get_provider_config(config.OUTLINE_PROVIDER)
    print("=== 小说写作助手 ===")
    print(f"🔌 主力写作：{cfg['name']}（{cfg['model']}）")
    print(
        f"📋 /summary → {sum_cfg['name']}  |  /check → {chk_cfg['name']}  |  "
        f"/outline → {out_cfg['name']}"
    )

    if config.supports_prompt_cache():
        if config.HEARTBEAT_ENABLED:
            cache_ttl = "1h" if config.USE_1H_CACHE else "5m"
            idle_min = config.HEARTBEAT_IDLE_STOP // 60
            print(f"💓 智能心跳已开启（缓存:{cache_ttl}，离开{idle_min}分钟自动停）")
        else:
            print("💓 智能心跳已关闭")
    else:
        print("💓 Prompt Cache 不可用（DeepSeek 模式，心跳已跳过）")
    print(f"当前章节：{chapter_str}（自动检测最新章节）")
    print(f"已加载概述：{summary_count}章")
    if config.AUTO_APPEND_CHAPTER:
        print("💾 续写正文将自动保存到最新章节（写入前自动备份）")
    else:
        print("💡 续写正文需手动 /save 才会写入章节")
    print("输入你的写作指令，或输入 /help 查看命令")
    ws.remind_pending_session_on_startup()


def main() -> None:
    import main as m

    m.bootstrap_library()
    m.init_data_dirs()
    config.load_runtime_settings()
    state.total_cost = m.load_total_cost()
    setup_exit_handlers()

    print_startup_banner()
    m.start_heartbeat_thread()

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            graceful_exit()
            break

        if not user_input:
            continue

        ws.touch_user_active()

        if user_input.startswith("/"):
            cmd_parts = user_input.split(maxsplit=1)
            cmd = cmd_parts[0].lower()
            arg = cmd_parts[1] if len(cmd_parts) > 1 else ""

            if cmd in ("/quit", "/exit", "/q"):
                graceful_exit()
            elif cmd == "/help":
                print_help()
            elif cmd == "/summary":
                do_summary()
            elif cmd == "/check":
                do_check()
            elif cmd == "/outline":
                n = 3
                if arg.strip().isdigit():
                    n = int(arg.strip())
                do_outline(n)
            elif cmd == "/patch":
                do_patch(arg)
            elif cmd == "/heartbeat":
                do_heartbeat_toggle()
            elif cmd == "/provider":
                do_provider(arg)
            elif cmd == "/cost":
                do_cost()
            elif cmd == "/new":
                do_new()
            elif cmd == "/save":
                do_save()
            elif cmd == "/undo":
                do_undo()
            elif cmd == "/restore":
                do_restore()
            else:
                print(f"未知命令：{cmd}，输入 /help 查看帮助")
        else:
            do_writing(user_input)
