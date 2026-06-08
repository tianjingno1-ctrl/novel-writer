# 架构约定（重构期）

> **每次 PR 对照检查；违反即打回。**

## 架构红线

1. `core/` 内任何文件禁止 `import main` / `import web_app` / `import api`
2. 禁止三层同名转发：`A.run_X → B.run_X → C.run_X`
3. 禁止在 route / orchestration / reviewer 里直接 `Path.write_text`（统一走 `BookStore.write` / `file_utils.atomic_write_text`）
4. 新功能不得新建 `services/*.py`（统一进 `core/orchestration/`）
5. `main.py` 不得**新增**任何 `api_run_*` 函数；已有转发须随迁移**物理删除**

## 目标分层

```
api/routes/          → HTTP only（请求解析、响应序列化）
core/orchestration/  → 多步流程编排（finalize、review、archive_sync）
core/                → 单能力（reviewer、maintain、generator、book_store、schemas）
infra/               → llm、config、file_utils、logs（逐步从根目录迁入）
app/                 → bootstrap、AppContext、CLI（不含业务编排）
```

## 每步验收检查表

完成一步后确认：

- [ ] `grep -r "import main" core/` → 结果为空
- [ ] `grep -r "services\.maintain" .` → 为空
- [ ] 新函数签名不含 `app_state` / `request_dict` 等 HTTP 概念
- [ ] 对应的旧转发函数已**物理删除**（不是注释）
- [ ] 至少有一个单测不需要启动 web server

## 执行原则

> **迁一块，同时删旧的，同时改所有调用方。**  
> 不留转发，不留注释掉的代码，不留「以后再删」的 TODO。

每步完成后项目应**可运行**，不是「先堆着，最后一起清」。

## 迁移进度

| Step | 内容 | 状态 |
|------|------|------|
| 0 | 目录骨架 `core/orchestration/`、`app/`、`api/routes/` | 完成 |
| 1 | `AppContext` + `app/bootstrap.py` | 完成（实例化 + `rebuild_context()`） |
| 2 | `BookStore` 去掉 `import main` | 完成 |
| 3 | 删 `services/` | 完成 |
| 4 | `finalize` → `core/orchestration/finalize.py` | 完成 |
| 5 | `review` → `core/orchestration/review.py` | 完成 |
| 6 | `web_app.py` → `api/routes/*` | 进行中（`finalize` + `review` + `maintain` + `library` 已迁） |
| 7 | `main.py` → `app/cli.py` | 待做 |
| 8 | 清理 `*Deps`、`summarizer` re-export | 待做 |

详见 `docs/schemas.md`、`docs/deps-audit.md`。
