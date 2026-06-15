# novel_writer 前端

React 19 + TypeScript + Vite + TanStack Query + Zustand + Tailwind + PWA。

产品范围与**唯一排期**见 [`docs/canonical-status.md`](../docs/canonical-status.md) §七（Track S/F/Prompt）。  
章 `role` / `intent` 见 [`docs/chapter-roles.md`](../docs/chapter-roles.md)。

## 开发

```bash
# 终端 1
cd novel_writer && python web_app.py

# 终端 2
cd frontend && npm run dev
```

http://127.0.0.1:5173 · `/api/*` 代理到 `:8765`

## E2E（Playwright · Track E5）

自动拉起 API（`:18765`）+ Vite（`:5175`），无需 LLM Key：

```bash
cd frontend
npm run e2e          # 首次可选：npm run e2e:install（下载 Chromium）
```

用例：

| 文件 | 覆盖 |
|------|------|
| `e2e/canonical-ui-flow.spec.ts` | **全流程 UI**：标准 Gate、向导开书、完结投递 |
| `e2e/canonical-ui-special.spec.ts` | **专项 UI**：整章重新生成、按审阅标准改稿、用户说明改稿 |
| `e2e/canonical-path.spec.ts` | 书架 → Gate、向导（无 LLM）→ Gate |
| `e2e/plan-validation.spec.ts` | 章规划 validate API |

只跑主流程：`npm run e2e:flow`

## 功能概览

| 模块 | 路由 | 说明 |
|------|------|------|
| 书架 / 新手引导 | `/` | 空库三路径；开书向导 `/library/new` |
| 写作（心流 + Gate） | `/writing` | **中间栏**正文 + 流式续写 + L1b–L10b Gate（无右侧预览栏） |
| 阶段 C 归因 | 写作内抽屉 | diagnose → patch 预览 → P3b 重跑 |
| 稿件 | `/manuscripts` | 投递记录、预检、结果录入 |
| 完结 / 投递 | `/complete` | 标记完结、E4b 投递类型 |
| 设置 | `/settings` | 模型、Prompt Cache、**口味库**、鉴权 |

## 开书向导

五步：`基本 → 偏好 → 方向 → 规划 → 标准`（`/library/new`；`mode=import` 可跳过前几步）

API：`/api/library/books` · `/api/prefill/*` · `/api/plan/meta` · `/api/plan/review-criteria/init`

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
