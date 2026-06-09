# novel_writer 前端

React 19 + TypeScript + Vite + TanStack Query + Zustand + Tailwind + PWA。

## 开发

```bash
# 终端 1
cd novel_writer && python web_app.py

# 终端 2
cd frontend && npm run dev
```

http://127.0.0.1:5173 · `/api/*` 代理到 `:8765`

## 功能概览

| 模块 | 路由 | 说明 |
|------|------|------|
| 书架 / 新手引导 | `/` | 空库三路径；开书向导 `/library/new` |
| 写作（心流 + Gate） | `/writing` | 加载磁盘正文、流式续写、L1b–L10b 一章循环 |
| 阶段 C 归因 | 写作内抽屉 | diagnose → patch 预览 → P3b 重跑 |
| 稿件 | `/manuscripts` | 章列表 + plan 状态 + 待办队列 |
| 完结 / 投递 | `/complete` | 标记完结、E4b 投递类型 |
| 设置 | `/settings` | 模型、Prompt Cache、**口味库**、鉴权 |

## 开书向导

`参考爆文 → 方向卡片（可填 seed）→ 可编辑章规划 → 开始写`

API：`/api/prefill/direction` · `/api/prefill/plan` · apply

## 每章循环 API

`apply-turn` → `precheck` → `female-fiction` → `judgment` → `finalize` → `summary/confirm`

## OpenAPI 类型

```bash
npm run gen:api   # 需 backend 运行；输出 src/api/generated/schema.ts
```

手写类型在 `src/types/api.ts`；生成后可逐步迁移 import。

## PWA

`vite-plugin-pwa` 已启用；`npm run build` 产出 `sw.js`，本地可安装为独立窗口（API 仍依赖本机 backend）。

## 构建

```bash
npm run build
npm run preview
```

## 目录

```
src/
  api/           client, endpoints, productApi, tasteApi, chapterFlow, generated/
  components/    wizard, gate, writing, taste, layout, ui
  hooks/         useChapterFlow, useSSEStream, useWorkQueue
  pages/         Library, Writing, Manuscripts, Complete, Settings, NewBook
  stores/        book, wizard, ui
```
