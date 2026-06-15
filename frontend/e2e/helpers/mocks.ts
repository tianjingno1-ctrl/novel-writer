import type { Page } from '@playwright/test'

import {
  mockChapterBody,
  mockRegeneratedChapterBody,
  mockRevisedChapterBody,
} from './api'

export const E2E_QUALITY_LOG_ID = 'e2e-quality-log-1'
export const E2E_REVISED_LOG_ID = 'e2e-quality-log-revise'

export const ORIGINAL_BODY_MARKER = '池瑶推开门'
export const REGENERATED_BODY_MARKER = '陆景琛重新抬头'
export const REVISED_BODY_MARKER = '改稿后苏瑶放慢了脚步'

const precheckOk = {
  ok: true,
  chapter_num: 1,
  word_count: 1200,
  word_count_target: 400,
  issues: [],
  ai_tone: { passed: true, level: 'low' },
}

/** 采纳 Gate：会话有未采纳 assistant → apply-turn */
export async function setupAdoptMocks(page: Page, chapterTitle = '初遇') {
  const body = mockChapterBody(chapterTitle)

  await page.route('**/api/chat/history', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        messages: [{ role: 'assistant', content: body }],
        appended_indices: [],
        context_turns: 8,
      }),
    })
  })

  await page.route('**/api/chapters/*/apply-turn', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    })
  })
}

/** AUTO_APPEND：正文已在磁盘，无未采纳 turn */
export async function setupDiskSavedAdoptMocks(page: Page, chapterTitle = '初遇') {
  const body = mockChapterBody(chapterTitle)

  await page.route('**/api/chat/history', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        messages: [{ role: 'assistant', content: body }],
        appended_indices: [0],
        context_turns: 8,
      }),
    })
  })

  await page.route('**/api/chapters/*/apply-turn', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: false,
        error: 'E2E: apply-turn 不应被调用（正文已在磁盘）',
      }),
    })
  })
}

async function mockPostChapterPipeline(page: Page) {
  await page.route('**/api/chapters/*/precheck', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(precheckOk),
    })
  })

  await page.route('**/api/chapters/*/rhythm-check', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        rhythm_warning: { warning: false },
        l5b_mandatory: false,
      }),
    })
  })

  await page.route('**/api/post-chapter/finalize', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        chapter_num: 1,
        archive: {
          summary: {
            ok: true,
            text: 'E2E 本章概述：误会加深，章末留钩。',
            full_text: 'E2E 本章概述：误会加深，章末留钩。',
          },
        },
      }),
    })
  })

  await page.route('**/api/chapters/*/summary/confirm', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    })
  })
}

/** Gate mock：采纳 → L4 审阅 → 亮点 → 概述 */
export async function setupStandardModeGateMocks(page: Page, chapterTitle = '初遇') {
  await setupDiskSavedAdoptMocks(page)
  await mockPostChapterPipeline(page)

  await page.route('**/api/review/chapter', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        log_id: E2E_QUALITY_LOG_ID,
        reply: '开篇钩子明确，情感张力足够，节奏紧凑，整体通过。',
        chapter_num: 1,
      }),
    })
  })

  await page.route(`**/api/quality/log/${E2E_QUALITY_LOG_ID}/judgment`, async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    })
  })
}

/** 整章重新生成：mock SSE `/api/chat/stream`（仅 regenerate: true） */
export async function setupChatStreamRegenerateMock(
  page: Page,
  chapterTitle = '初遇',
) {
  await page.route('**/api/chat/stream', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    const req = JSON.parse(route.request().postData() ?? '{}') as {
      regenerate?: boolean
    }
    if (!req.regenerate) {
      await route.continue()
      return
    }
    const text = mockRegeneratedChapterBody(chapterTitle)
    const sse = [
      `data: ${JSON.stringify({ type: 'chapter_cleared', chapter_num: 1 })}\n\n`,
      `data: ${JSON.stringify({ type: 'chunk', text })}\n\n`,
      `data: ${JSON.stringify({
        type: 'done',
        chapter_num: 1,
        chapter_saved: true,
      })}\n\n`,
    ].join('')
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache',
      },
      body: sse,
    })
  })
}

/** 标准模式 + 审阅改稿链（用户说明 / 按审阅标准） */
export async function setupStandardReviewReviseMocks(
  page: Page,
  chapterTitle = '初遇',
) {
  await setupDiskSavedAdoptMocks(page, chapterTitle)
  await mockPostChapterPipeline(page)

  await page.route('**/api/chapters/*/review', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        chapter_num: 1,
        review: {
          rounds: [
            {
              round: 1,
              quality_log_id: E2E_QUALITY_LOG_ID,
              gaps: [
                {
                  rule_ref: 'opening_hook',
                  description: '开篇钩子不够强',
                  severity: 'hard',
                },
              ],
              review_excerpt: '情感节奏偏快，需加强犹豫层次。',
            },
          ],
        },
      }),
    })
  })

  await page.route('**/api/review/chapter', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    const body = JSON.parse(route.request().postData() ?? '{}') as {
      revise?: boolean
    }
    if (body.revise) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          log_id: E2E_REVISED_LOG_ID,
          revised_text: mockRevisedChapterBody(chapterTitle),
          reply: '已按改稿说明重写，情感节奏放缓。',
          chapter_num: 1,
          pending_accept: true,
        }),
      })
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        log_id: E2E_QUALITY_LOG_ID,
        reply: '开篇有张力，但节奏略快，建议加强人物内心戏。',
        chapter_num: 1,
      }),
    })
  })

  await page.route('**/api/review/chapter/accept', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    })
  })

  await page.route('**/api/quality/log/*/judgment', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    })
  })
}
