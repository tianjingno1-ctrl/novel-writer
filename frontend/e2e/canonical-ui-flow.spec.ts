import { expect, test } from '@playwright/test'

import {
  finishWizardViaApi,
  mockChapterBody,
  saveChapterContent,
  seedReadyBook,
} from './helpers/api'
import { setupStandardModeGateMocks } from './helpers/mocks'
import {
  markChapterApprovedForComplete,
  openWritingFromShelf,
  runCompleteAndSubmitUI,
  runStandardModeChapterGateUI,
} from './helpers/ui-flow'

test.describe('Canonical UI 全流程（Mock LLM / 定稿链）', () => {
  test('标准模式：采纳 → 审阅 → 亮点 → 概述 → 章完成', async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000)

    const title = `E2E 标准Gate ${Date.now()}`
    const body = mockChapterBody('初遇')

    await seedReadyBook(request, title)
    await saveChapterContent(request, 1, body)
    await setupStandardModeGateMocks(page)

    await openWritingFromShelf(page, title)
    await runStandardModeChapterGateUI(page)
    await expect(
      page.getByRole('heading', { name: '第 1 章完成！' }),
    ).toBeVisible({ timeout: 15_000 })
  })

  test('向导 UI → Gate → 完结 → 投递', async ({ page, request }) => {
    test.setTimeout(180_000)

    const title = `E2E 向导全路径 ${Date.now()}`
    const body = mockChapterBody('初遇')

    await page.goto('/library/new?mode=quick')
    await expect(page.getByRole('heading', { name: '基本信息' })).toBeVisible()

    await page.getByPlaceholder('必填').fill(title)
    await page.getByRole('button', { name: '下一步' }).click()

    await expect(page.getByRole('heading', { name: '写作偏好' })).toBeVisible({
      timeout: 15_000,
    })
    await page.getByRole('button', { name: '跳过', exact: true }).click()

    await expect(page.getByRole('heading', { name: 'AI 预填方向' })).toBeVisible()
    await page.getByRole('button', { name: '自己写方向' }).click()
    await page
      .getByPlaceholder('写下你的方向、logline 或大纲')
      .fill('都市甜宠，误会开局，章末强钩子')
    await page.getByRole('button', { name: '确认方向' }).click()

    await expect(page.getByRole('heading', { name: '章节规划' })).toBeVisible()
    await finishWizardViaApi(request, {
      wordCountTarget: 400,
      chapterTitle: '初遇',
    })

    await saveChapterContent(request, 1, body)
    await setupStandardModeGateMocks(page)

    await page.goto('/')
    await openWritingFromShelf(page, title)
    await runStandardModeChapterGateUI(page)

    await markChapterApprovedForComplete(request, 1)
    await runCompleteAndSubmitUI(page, request, title)
  })

  test('API 开书 → Gate → 完结 → 投递', async ({ page, request }) => {
    test.setTimeout(180_000)

    const title = `E2E API全路径 ${Date.now()}`
    const body = mockChapterBody('初遇')

    await seedReadyBook(request, title)
    await saveChapterContent(request, 1, body)
    await setupStandardModeGateMocks(page)

    await openWritingFromShelf(page, title)
    await runStandardModeChapterGateUI(page)

    await markChapterApprovedForComplete(request, 1)
    await runCompleteAndSubmitUI(page, request, title)
  })
})
