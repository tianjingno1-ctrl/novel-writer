import json
import logging
import os
from pathlib import Path

import file_utils

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent
_ENV_CANDIDATES = (_CONFIG_DIR / ".env", _CONFIG_DIR / ".evn")
RUNTIME_FILE = _CONFIG_DIR / "data" / "runtime.json"


def _load_env_file() -> None:
    """从 novel_writer/.env 读取 Key，无需配置系统环境变量。"""
    env_path = next((p for p in _ENV_CANDIDATES if p.exists()), None)
    if env_path is None:
        return
    if env_path.name == ".evn":
        logger.warning(
            "检测到 .evn 文件名，建议重命名为 .env（启动.bat 可自动处理）"
        )
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and value:
            os.environ.setdefault(name, value)


_load_env_file()

# 主力提供商（正文续写、润色、多轮对话）：建议 kie (Claude)
PROVIDER = os.environ.get("NOVEL_PROVIDER", "kie")

# 辅助任务专用提供商（不影响主对话，自动走便宜模型）
SUMMARY_PROVIDER = os.environ.get("NOVEL_SUMMARY_PROVIDER", "deepseek")
CHECK_PROVIDER = os.environ.get("NOVEL_CHECK_PROVIDER", "deepseek")
OUTLINE_PROVIDER = os.environ.get("NOVEL_OUTLINE_PROVIDER", "deepseek")

MAX_TOKENS = 4096

USE_1H_CACHE = True
CACHE_TTL = "1h" if USE_1H_CACHE else "5m"

HEARTBEAT_ENABLED = True
HEARTBEAT_INTERVAL = 240
HEARTBEAT_REFRESH_AFTER = 50 * 60
HEARTBEAT_IDLE_STOP = 6 * 60

AUTO_APPEND_CHAPTER = True

# 写作对话保留最近 N 轮（1 轮 = 用户 + 助手各 1 条）；0 表示不限制
CHAT_CONTEXT_TURNS = int(os.environ.get("NOVEL_CONTEXT_TURNS", "10"))

# 上下文策略: turns | summaries | beats | codex
CONTEXT_MODE = os.environ.get("NOVEL_CONTEXT_MODE", "beats")

# 自由聊天（与写作分离，默认 DeepSeek 省钱）
FREE_CHAT_PROVIDER = os.environ.get("NOVEL_FREE_CHAT_PROVIDER", "deepseek")
FREE_CHAT_CONTEXT_TURNS = int(os.environ.get("NOVEL_FREE_CHAT_TURNS", "20"))

# Web 最小鉴权：设置后所有 /api/* 须带请求头 X-Novel-Token
WEB_TOKEN = os.environ.get("NOVEL_WEB_TOKEN", "").strip()

PLACEHOLDER_PREFIX = "在这里填"

PROVIDERS = {
    "kie": {
        "name": "kie.ai Claude Sonnet",
        "api_key_env": "KIE_API_KEY",
        "api_key_default": "在这里填你的_KIE_API_KEY",
        "base_url": "https://api.kie.ai/claude",
        "model": "claude-sonnet-4-6",
        "supports_cache": True,
        "client": "anthropic",
        # 价格参考：2025-06 预估，单位 USD / 1M tokens
        "price": {
            "cache_read": 0.30,
            "cache_write_5m": 3.75,
            "cache_write_1h": 6.00,
            "input": 3.00,
            "output": 15.00,
        },
    },
    "kie-opus": {
        "name": "kie.ai Claude Opus 4.6",
        "api_key_env": "KIE_API_KEY",
        "api_key_default": "在这里填你的_KIE_API_KEY",
        "base_url": "https://api.kie.ai/claude",
        "model": "claude-opus-4-6",
        "supports_cache": True,
        "client": "anthropic",
        "price": {
            "cache_read": 0.50,
            "cache_write_5m": 6.25,
            "cache_write_1h": 10.00,
            "input": 5.00,
            "output": 25.00,
        },
    },
    "kie-opus-47": {
        "name": "kie.ai Claude Opus 4.7",
        "api_key_env": "KIE_API_KEY",
        "api_key_default": "在这里填你的_KIE_API_KEY",
        "base_url": "https://api.kie.ai/claude",
        "model": "claude-opus-4-7",
        "supports_cache": True,
        "client": "anthropic",
        "price": {
            "cache_read": 0.50,
            "cache_write_5m": 6.25,
            "cache_write_1h": 10.00,
            "input": 5.00,
            "output": 25.00,
        },
    },
    "kie-opus-48": {
        "name": "kie.ai Claude Opus 4.8",
        "api_key_env": "KIE_API_KEY",
        "api_key_default": "在这里填你的_KIE_API_KEY",
        "base_url": "https://api.kie.ai/claude",
        "model": "claude-opus-4-8",
        "supports_cache": True,
        "client": "anthropic",
        "price": {
            "cache_read": 0.50,
            "cache_write_5m": 6.25,
            "cache_write_1h": 10.00,
            "input": 5.00,
            "output": 25.00,
        },
    },
    "deepseek": {
        "name": "DeepSeek V4 Pro",
        "api_key_env": "DEEPSEEK_API_KEY",
        "api_key_default": "在这里填你的_DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        "supports_cache": False,
        "client": "openai",
        # 价格参考：V4-Pro 预估，单位 USD / 1M tokens（可在 prices.json 覆盖）
        "price": {
            "cache_read": 0.014,
            "cache_write_5m": 0.0,
            "cache_write_1h": 0.0,
            "input": 1.74,
            "output": 3.48,
        },
    },
}

_PRICES_FILE = _CONFIG_DIR / "prices.json"


def _load_prices_from_file() -> None:
    if not _PRICES_FILE.exists():
        return
    try:
        data = json.loads(_PRICES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("无法读取 prices.json，使用内置价格: %s", e)
        return
    for key, prices in data.items():
        if key.startswith("_") or not isinstance(prices, dict) or key not in PROVIDERS:
            continue
        PROVIDERS[key]["price"].update(prices)


_load_prices_from_file()


def load_runtime_settings() -> None:
    """从 data/runtime.json 恢复 Web 端修改过的 provider / 上下文配置。"""
    global PROVIDER, CONTEXT_MODE, CHAT_CONTEXT_TURNS
    if not RUNTIME_FILE.exists():
        return
    try:
        data = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("无法读取 runtime.json: %s", e)
        return
    provider = data.get("provider")
    if isinstance(provider, str) and provider in PROVIDERS:
        PROVIDER = provider
    mode = data.get("context_mode")
    if isinstance(mode, str) and mode in ("turns", "summaries", "beats", "codex"):
        CONTEXT_MODE = mode
    turns = data.get("context_turns")
    if isinstance(turns, int) and 0 <= turns <= 100:
        CHAT_CONTEXT_TURNS = turns


def save_runtime_settings() -> None:
    payload = {
        "provider": PROVIDER,
        "context_mode": CONTEXT_MODE,
        "context_turns": CHAT_CONTEXT_TURNS,
    }
    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_utils.atomic_write_text(
        RUNTIME_FILE,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )


def resolve_provider(provider: str | None = None) -> str:
    return provider or PROVIDER


def get_provider_config(provider: str | None = None) -> dict:
    key = resolve_provider(provider)
    if key not in PROVIDERS:
        raise ValueError(f"未知提供商: {key}，可选: {', '.join(PROVIDERS)}")
    return PROVIDERS[key]


def get_api_key(provider: str | None = None) -> str:
    cfg = get_provider_config(provider)
    return os.environ.get(cfg["api_key_env"], cfg["api_key_default"])


def get_model(provider: str | None = None) -> str:
    return get_provider_config(provider)["model"]


def is_api_key_configured(provider: str | None = None) -> bool:
    key = get_api_key(provider)
    return bool(key) and not key.startswith(PLACEHOLDER_PREFIX)


def supports_prompt_cache(provider: str | None = None) -> bool:
    return get_provider_config(provider)["supports_cache"]


def cache_enabled(provider: str | None = None) -> bool:
    return supports_prompt_cache(provider) and USE_1H_CACHE


def get_price(provider: str | None = None) -> dict:
    cfg = get_provider_config(provider)
    price = dict(cfg["price"])
    if supports_prompt_cache(provider):
        price["cache_write"] = (
            price["cache_write_1h"] if USE_1H_CACHE else price["cache_write_5m"]
        )
    else:
        price["cache_write"] = 0.0
    return price


def list_providers() -> str:
    lines = []
    for key, cfg in PROVIDERS.items():
        marks = []
        if key == PROVIDER:
            marks.append("主力")
        if key == SUMMARY_PROVIDER:
            marks.append("/summary")
        if key == CHECK_PROVIDER:
            marks.append("/check")
        if key == OUTLINE_PROVIDER:
            marks.append("/outline")
        mark = f" ← {', '.join(marks)}" if marks else ""
        cache = "支持缓存" if cfg["supports_cache"] else "无 Prompt Cache"
        lines.append(f"  {key}: {cfg['name']} ({cfg['model']}, {cache}){mark}")
    lines.append(
        f"\n  主力写作: {PROVIDER}  |  "
        f"/summary: {SUMMARY_PROVIDER}  |  "
        f"/check: {CHECK_PROVIDER}  |  /outline: {OUTLINE_PROVIDER}"
    )
    lines.append("  （辅助任务提供商在 config.py 修改，/provider 只切换主力）")
    return "\n".join(lines)


load_runtime_settings()
