import { expect, test } from '@playwright/test'

const USER_BOOK_ID = '新书-b4474569'
const API_BASE = `http://127.0.0.1:${process.env.NOVEL_WEB_PORT ?? '18765'}`

test('用户原书：书架点击进入写作页', async ({ page, request }) => {
  const switchRes = await request.post(`${API_BASE}/api/library/switch`, {
    headers: { 'Content-Type': 'application/json' },
    data: { book_id: USER_BOOK_ID },
  })
  expect(switchRes.ok()).toBeTruthy()

  await page.goto('/')
  await expect(page.getByRole('heading', { name: '我的书架' })).toBeVisible()

  const card = page
    .locator('button')
    .filter({ hasText: '穿成恶毒女配自救' })
    .first()
  await expect(card).toBeVisible({ timeout: 15_000 })
  await card.click()

  await expect(page).toHaveURL(/\/writing/, { timeout: 15_000 })
  await expect(page.locator('header').getByText('第 1 章')).toBeVisible()
  await expect(
    page.getByRole('button', { name: /继续写|采纳/ }),
  ).toBeVisible()
})
