# 长篇小说辅助写作工具

基于大模型 API 的长篇小说写作助手，支持 **kie.ai Claude** 与 **DeepSeek**，帮助你在保持世界观一致性的同时高效续写、生成概述、检查连续性。

## 环境要求

- **Python 3.10+**（代码使用 `str | None` 等新语法）
- Windows / macOS / Linux 均可

## 安装

```bash
cd novel_writer
pip install -r requirements.txt
```

（Web 界面需 `fastapi` / `uvicorn`，CLI 至少需 `anthropic`；以 `requirements.txt` 为准。）

## 配置 API 提供商

推荐 **Claude 主力 + DeepSeek 辅助**（已内置）：

| 场景 | 默认提供商 | 配置项 |
|------|------------|--------|
| 正文续写、润色 | kie (Claude Sonnet) | `PROVIDER` 或 **设置 → 模型** |
| 更强推理写作 | kie-opus (Claude Opus) | 设置 / `/provider kie-opus` |
| `/summary` 概述 | DeepSeek | `SUMMARY_PROVIDER` |
| `/check` 检查 | DeepSeek | `CHECK_PROVIDER` |

运行时用 `/provider` 只切换**主力写作**；`/summary` 和 `/check` 走独立配置，不影响主对话。

### kie.ai Claude（默认，支持 Prompt Cache）

1. 在 [kie.ai](https://kie.ai/api-key) 获取 API Key
2. 配置方式（二选一）：

   ```powershell
   # Windows PowerShell（等号两侧不要空格）
   $env:KIE_API_KEY="你的_kie_密钥"
   ```

   或在 `config.py` → `PROVIDERS["kie"]["api_key_default"]` 填写。

3. 默认模型：`claude-sonnet-4-6`（`kie`）；Opus 可选 `kie-opus`（4.6）、`kie-opus-47`（4.7）、`kie-opus-48`（4.8），同一 Key

### DeepSeek

1. 在 [DeepSeek 开放平台](https://platform.deepseek.com/) 获取 API Key
2. 配置方式（二选一）：

   ```powershell
   $env:DEEPSEEK_API_KEY="你的_deepseek_密钥"
   ```

   或在 `config.py` → `PROVIDERS["deepseek"]["api_key_default"]` 填写。

3. 默认模型：`deepseek-chat`（可改为 `deepseek-reasoner` 等）

也可用环境变量 `NOVEL_PROVIDER=deepseek` 指定启动时的提供商。

其他可调参数见 `config.py`：缓存 TTL、心跳间隔、各提供商价格表等。

## 运行

### HTTP API（推荐）

```bash
cd novel_writer
copy .env.example .env    # 填入 API Key
启动API.bat               # 或: python web_app.py
```

浏览器打开 http://127.0.0.1:8765/docs 查看 OpenAPI 并调试 `/api/*`。根路径 `/` 会重定向到 `/docs`。

> **内置 Web 写作界面已移除**（原 `web/` 目录）。新客户端计划为 React PWA，对接同一套 API。
>
> **API 使用限制（必读）**：进程内共享**同一份**写作会话与费用统计，**仅限本地单人**使用；多客户端会互相干扰。建议在 `.env` 设置 `NOVEL_WEB_TOKEN`，API 请求须带 `X-Novel-Token`；默认仅监听 `127.0.0.1`，请勿对公网暴露。

### CLI

```bash
cd novel_writer
python main.py
```

## 用户手册

完整说明见 **[docs/novel-writer-manual.md](./docs/novel-writer-manual.md)**（系统设定、写作流程、注意事项合一）。技术架构与 API 见 [docs/tech-intake.md](./docs/tech-intake.md)。

## 给 AI / 协作者

- 仓库**不含 API Key**，本地复制 `.env.example` → `.env` 后自行配置。
- 项目结构与改 bug 注意点见 [AGENTS.md](./AGENTS.md)。

## 文件用途

| 文件 | 用途 |
|------|------|
| `data/world.md` | 世界观、五点骨架、章节节拍、爽点表（几乎不变，缓存块①） |
| `data/style.md` | 文风锚点：示范句、禁用词、节奏（写第一章前必做，与 world 同缓存块） |
| `data/characters.md` | 人物初始设定（只追加，用 `/patch`，缓存块②） |
| `data/char_static.md` | 人物锚点（性格/禁止写法，缓存②） |
| `data/char_dynamic.md` | 人物动态（当前状态，每章更新，④ 层） |
| `data/summaries_archive.md` | 概述归档（缓存③） |
| `data/summaries_recent.md` | 近期概述（`/summary` 追加，④ 层） |
| `data/plot_threads_locked.md` | 细节钉子（缓存③） |
| `data/plot_threads_active.md` | 活跃伏笔（④ 层） |
| `data/chapters/ch001.md` | 各章正文，命名 `ch001.md`、`ch002.md` … |
| `data/backups/` | 每次写入 `.md` 前自动备份（带时间戳） |
| `cost_log.jsonl` | API 费用记录（JSON Lines，运行后自动生成；旧版 `cost_log.txt` 仍可读） |

## 命令一览

| 命令 | 说明 |
|------|------|
| （直接输入文字） | 写作模式：根据指令协助创作 |
| `/summary` | 为最新章节生成 150–300 字概述并追加 |
| `/check` | 对照设定检查最新章节的矛盾 |
| `/outline [N]` | 基于概述与伏笔，预测后续 N 章剧情走向（默认 3 章） |
| `/patch 内容` | 在 characters.md 末尾追加设定补充 |
| `/heartbeat` | 开关智能心跳（续命 Prompt Cache，仅 kie） |
| `/provider` | 切换主力写作提供商（辅助任务见 config.py） |
| `/cost` | 显示累计 API 费用 |
| `/save` | 将未写入的 AI 正文补存到章节 + 保存会话 |
| `/undo` | 撤销上一次自动写入章节的正文 |
| `/new` | 清空对话历史（文档缓存保留） |
| `/restore` | 恢复上次自动保存的会话 |
| `/help` | 显示帮助 |
| `/quit` | 退出 |

## 缓存原理

System prompt 按「稳定 → 变化」分三层，均带 `cache_control`，利用 Claude Prompt Cache 前缀匹配：

1. `world.md` + `style.md`（文风锚点，合并为同一缓存块）
2. `characters.md`
3. `summaries.md`

第四层为本次任务指令（不缓存）。User message 携带当前章节正文。文件采用**只增不改**策略，缓存命中率可稳定在 80% 以上。

## 智能心跳

开启后，后台线程会在你**仍在写作**（6 分钟内有操作）且**距上次 API 请求超过 50 分钟**时，自动发送轻量心跳请求刷新 1 小时缓存，避免缓存过期。离开电脑超过 6 分钟会自动停止，不产生多余费用。

## 新手提示

- **CLI**：`python main.py`，使用 `/summary`、`/check`、`/outline`、`/patch` 等命令（见上表）。
- **API**：在 http://127.0.0.1:8765/docs 浏览 OpenAPI；产品主路径见 `docs/workflow.md`。
- 书库与设定文件位于 `library/books/{id}/`。产品流程见 [workflow.md](./docs/workflow.md)；做了/没做见 [canonical-status.md](./docs/canonical-status.md)；数据文件见 [novel-writer-manual.md](./docs/novel-writer-manual.md)。

## 费用说明

每次 API 请求后会打印 Token 统计与**预估**费用，并追加到 `cost_log.jsonl`（兼容读取旧版 `cost_log.txt`）。单价可在 `prices.json` 调整；实际账单以提供商后台为准。心跳请求标记为 `[心跳]`，普通请求标记为 `[请求]`。
