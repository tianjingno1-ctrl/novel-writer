import { expect, test } from '@playwright/test'

import { finishWizardViaApi, seedReadyBook } from './helpers/api'

test.describe('Canonical 路径', () => {
  test('书架 → 已就绪书籍 → Gate 写作页', async ({ page, request }) => {
    const title = `E2E Gate ${Date.now()}`
    await seedReadyBook(request, title)

    await page.goto('/')
    await expect(page.getByRole('heading', { name: '我的书架' })).toBeVisible()

    await page.locator('button').filter({ hasText: title }).first().click()
    await expect(page).toHaveURL(/\/writing/)

    await expect(page.locator('header').getByText('第 1 章')).toBeVisible()
    await expect(page.getByRole('button', { name: '继续写' })).toBeVisible()
  })

  test('向导（无 LLM）→ API 收尾 → Gate 写作页', async ({ page, request }) => {
    const title = `E2E 向导 ${Date.now()}`

    await page.goto('/library/new?mode=quick')
    await expect(page.getByRole('heading', { name: '基本信息' })).toBeVisible()

    await page.getByPlaceholder('必填').fill(title)
    await page.getByRole('button', { name: '下一步' }).click()

    await expect(page.getByRole('heading', { name: '写作偏好' })).toBeVisible()
    await page.getByRole('button', { name: '跳过', exact: true }).click()

    await expect(page.getByRole('heading', { name: 'AI 预填方向' })).toBeVisible()
    await page.getByRole('button', { name: '自己写方向' }).click()
    await page
      .getByPlaceholder('写下你的方向、logline 或大纲')
      .fill('都市甜宠，误会开局，章末强钩子')
    await page.getByRole('button', { name: '确认方向' }).click()

    await expect(page.getByRole('heading', { name: '章节规划' })).toBeVisible()

    await finishWizardViaApi(request)

    await page.goto('/writing')
    await expect(page.locator('header').getByText('第 1 章')).toBeVisible()
    await expect(page.getByRole('button', { name: '继续写' })).toBeVisible()
  })
})
