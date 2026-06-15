import { expect, test } from '@playwright/test'

test('空书架欢迎页可进入开书向导', async ({ page }) => {
  const status = await page.request.get('/api/status')
  expect(status.ok()).toBeTruthy()

  const library = await page.request.get('/api/library')
  const libBody = (await library.json()) as { books?: unknown[] }
  const hasBooks = (libBody.books?.length ?? 0) > 0

  test.skip(hasBooks, '仅在有书书架时跳过空态用例')

  await page.goto('/')
  await expect(page.getByText('欢迎使用 Novel Writer')).toBeVisible()
  await page.getByRole('button', { name: '我有想法，直接开始写' }).click()
  await expect(page).toHaveURL(/\/library\/new/)
  await expect(page.getByRole('heading', { name: '基本信息' })).toBeVisible()
})
