import type { APIRequestContext } from '@playwright/test'

const apiPort = process.env.NOVEL_WEB_PORT ?? '18765'
export const API_BASE = `http://127.0.0.1:${apiPort}`

const jsonHeaders = { 'Content-Type': 'application/json' }

async function expectOk(res: { ok(): boolean; status(): number; json(): Promise<unknown> }, label: string) {
  if (!res.ok()) {
    const body = await res.json().catch(() => ({}))
    throw new Error(`${label} HTTP ${res.status()}: ${JSON.stringify(body)}`)
  }
  const body = (await res.json()) as { ok?: boolean; error?: string }
  if (body.ok === false) {
    throw new Error(`${label}: ${body.error ?? JSON.stringify(body)}`)
  }
  return body
}

export async function seedReadyBook(
  request: APIRequestContext,
  title: string,
  opts: SeedPlanOptions = {},
) {
  const { wordCountTarget = 400, chapterTitle = '初遇' } = opts

  const bookRes = await request.post(`${API_BASE}/api/library/books`, {
    headers: jsonHeaders,
    data: { title, type: 'short', platform: 'tomato' },
  })
  const book = await expectOk(bookRes, 'POST /api/library/books')

  const planRes = await request.post(`${API_BASE}/api/prefill/plan/apply`, {
    headers: jsonHeaders,
    data: {
      option: {
        id: 'e2e-manual',
        chapters: [
          {
            num: 1,
            title: chapterTitle,
            beat: '男女主误会',
            hook: '结尾反转',
            word_count_target: wordCountTarget,
          },
        ],
      },
      replace: true,
    },
  })
  await expectOk(planRes, 'POST /api/prefill/plan/apply')

  const criteriaRes = await request.post(`${API_BASE}/api/plan/review-criteria/init`, {
    headers: jsonHeaders,
    data: {},
  })
  await expectOk(criteriaRes, 'POST /api/plan/review-criteria/init')

  const metaRes = await request.put(`${API_BASE}/api/plan/meta`, {
    headers: jsonHeaders,
    data: {
      meta: {
        wizard_complete: true,
        wizard_step: null,
      },
    },
  })
  await expectOk(metaRes, 'PUT /api/plan/meta')

  return book as { book_id?: string; id?: string }
}

export type SeedPlanOptions = {
  wordCountTarget?: number
  chapterTitle?: string
}

export async function finishWizardViaApi(
  request: APIRequestContext,
  opts: SeedPlanOptions = {},
) {
  const { wordCountTarget = 400, chapterTitle = '开篇' } = opts

  const planRes = await request.post(`${API_BASE}/api/prefill/plan/apply`, {
    headers: jsonHeaders,
    data: {
      option: {
        id: 'e2e-wizard',
        chapters: [
          {
            num: 1,
            title: chapterTitle,
            beat: '强钩子开局',
            hook: '悬念',
            word_count_target: wordCountTarget,
          },
        ],
      },
      replace: true,
    },
  })
  await expectOk(planRes, 'POST /api/prefill/plan/apply')

  const criteriaRes = await request.post(`${API_BASE}/api/plan/review-criteria/init`, {
    headers: jsonHeaders,
    data: {},
  })
  await expectOk(criteriaRes, 'POST /api/plan/review-criteria/init')

  const metaRes = await request.put(`${API_BASE}/api/plan/meta`, {
    headers: jsonHeaders,
    data: {
      meta: {
        wizard_complete: true,
        wizard_step: null,
      },
    },
  })
  await expectOk(metaRes, 'PUT /api/plan/meta')
}

export function mockChapterBody(chapterTitle = '初遇'): string {
  const para =
    '池瑶推开门，陆景琛坐在沙发上看手机，气氛微妙，两人对视片刻。'
  return `# 第1章 · ${chapterTitle}\n\n${para.repeat(28)}`
}

/** 整章重新生成后的 mock 正文（与原文区分） */
export function mockRegeneratedChapterBody(chapterTitle = '初遇'): string {
  const para =
    '陆景琛重新抬头，目光与苏瑶相撞，这一版节奏更紧，章末悬念上扬。'
  return `# 第1章 · ${chapterTitle}\n\n${para.repeat(28)}`
}

/** 审阅改稿后的 mock 正文 */
export function mockRevisedChapterBody(chapterTitle = '初遇'): string {
  const para = '改稿后苏瑶放慢了脚步，情绪层次更细腻，对白更有张力。'
  return `# 第1章 · ${chapterTitle}\n\n${para.repeat(28)}`
}

export async function saveChapterContent(
  request: APIRequestContext,
  chapterNum: number,
  content: string,
) {
  const res = await request.put(`${API_BASE}/api/chapters/${chapterNum}`, {
    headers: jsonHeaders,
    data: { content },
  })
  await expectOk(res, `PUT /api/chapters/${chapterNum}`)
}

export async function switchToBook(request: APIRequestContext, bookId: string) {
  const res = await request.post(`${API_BASE}/api/library/switch`, {
    headers: jsonHeaders,
    data: { book_id: bookId },
  })
  await expectOk(res, 'POST /api/library/switch')
}

export async function waitChapterApproved(
  request: APIRequestContext,
  chapterNum: number,
  timeoutMs = 90_000,
) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    const res = await request.get(`${API_BASE}/api/plan/product`)
    const data = (await res.json()) as {
      chapter_statuses?: Record<string, string>
    }
    if (data.chapter_statuses?.[String(chapterNum)] === 'approved') {
      return
    }
    await new Promise((r) => setTimeout(r, 1000))
  }
  throw new Error(`chapter ${chapterNum} not approved within ${timeoutMs}ms`)
}

export async function approveChapterForE2E(
  request: APIRequestContext,
  chapterNum: number,
) {
  const res = await request.patch(
    `${API_BASE}/api/plan/chapters/${chapterNum}/status`,
    {
      headers: jsonHeaders,
      data: { status: 'approved' },
    },
  )
  await expectOk(res, `PATCH /api/plan/chapters/${chapterNum}/status`)
}

/** 完结后创建稿件并标记为 submitting（绕过弹窗内 click 视口问题） */
export async function createAndSubmitManuscript(
  request: APIRequestContext,
  title: string,
) {
  const msRes = await request.post(`${API_BASE}/api/manuscripts`, {
    headers: jsonHeaders,
    data: { title },
  })
  const msBody = (await msRes.json()) as {
    ok?: boolean
    manuscript?: { id?: string }
  }
  if (!msRes.ok() || !msBody.manuscript?.id) {
    throw new Error(`POST /api/manuscripts failed: ${JSON.stringify(msBody)}`)
  }
  const msId = msBody.manuscript.id

  const lcRes = await request.put(`${API_BASE}/api/project/lifecycle`, {
    headers: jsonHeaders,
    data: { status: 'complete', manuscript_id: msId },
  })
  await expectOk(lcRes, 'PUT /api/project/lifecycle')

  const completeRes = await request.patch(`${API_BASE}/api/manuscripts/${msId}`, {
    headers: jsonHeaders,
    data: { state: 'complete' },
  })
  await expectOk(completeRes, `PATCH /api/manuscripts/${msId} complete`)

  const patchRes = await request.patch(`${API_BASE}/api/manuscripts/${msId}`, {
    headers: jsonHeaders,
    data: {
      state: 'submitting',
      submission: {
        target: 'text_editor',
        submitted_at: new Date().toISOString().slice(0, 10),
        compliance_checked: true,
      },
    },
  })
  await expectOk(patchRes, `PATCH /api/manuscripts/${msId}`)
  return msId
}
