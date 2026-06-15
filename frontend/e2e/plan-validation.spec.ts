import { expect, test } from '@playwright/test'

import { API_BASE } from './helpers/api'

const jsonHeaders = { 'Content-Type': 'application/json' }

test.describe('章规划校验 API', () => {
  test('validate 返回跨章 warn', async ({ request }) => {
    const title = `E2E Validate ${Date.now()}`
    const bookRes = await request.post(`${API_BASE}/api/library/books`, {
      headers: jsonHeaders,
      data: { title, type: 'short', platform: 'tomato' },
    })
    expect(bookRes.ok()).toBeTruthy()

    const res = await request.post(`${API_BASE}/api/prefill/plan/validate`, {
      headers: jsonHeaders,
      data: {
        option: {
          title,
          chapters: [
            {
              num: 1,
              role: 'hook_open',
              title: '开篇',
              intent: { kind: 'hook_open', final: '身份误会' },
            },
            {
              num: 2,
              role: 'bridge',
              title: '过渡',
              intent: {
                kind: 'bridge',
                final: { next_seed: '宫廷宴会' },
              },
            },
            {
              num: 3,
              role: 'buildup',
              title: '铺垫',
              intent: {
                kind: 'buildup',
                final: { conditions: '加班熬夜', emotions: '疲惫' },
              },
            },
            { num: 4, role: 'finale', title: '完结' },
          ],
        },
        replace: true,
      },
    })
    expect(res.ok()).toBeTruthy()
    const body = (await res.json()) as {
      ok?: boolean
      warnings?: Array<{ code?: string }>
    }
    const codes = (body.warnings ?? []).map((w) => w.code)
    expect(codes).toContain('bridge_next_seed_mismatch')
  })
})
