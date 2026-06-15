import { expect, type APIRequestContext, type Page } from '@playwright/test'

import { approveChapterForE2E, createAndSubmitManuscript } from './api'

/** 从书架进入指定书名写作页 */
export async function openWritingFromShelf(page: Page, bookTitle: string) {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '我的书架' })).toBeVisible()
  await page.locator('button').filter({ hasText: bookTitle }).first().click()
  await expect(page).toHaveURL(/\/writing/)
  await expect(page.locator('header').getByText('第 1 章')).toBeVisible()
}

/** 预览 Gate：采纳（期望进入下一 Gate 标题） */
export async function adoptPreviewGate(
  page: Page,
  bodyMarker = '池瑶推开门',
) {
  await expect(page.getByText(bodyMarker)).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('heading', { name: '预览，是否采纳？' })).toBeVisible({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: '采纳' }).click()
}

/** 预览 Gate：整章重新生成 */
export async function regenerateFromPreviewGate(page: Page) {
  await expect(page.getByRole('heading', { name: '预览，是否采纳？' })).toBeVisible({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: '整章重新生成' }).click()
}

/** 等待正文区出现指定片段（流式或磁盘） */
export async function expectBodyMarker(page: Page, marker: string) {
  await expect(page.getByText(marker)).toBeVisible({ timeout: 30_000 })
}

/** 标准模式：进入审阅 Gate（仅采纳，不通过） */
export async function reachReviewGate(page: Page) {
  await adoptPreviewGate(page)
  await expect(page.getByRole('heading', { name: '质量审阅' })).toBeVisible({
    timeout: 30_000,
  })
}

/** 审阅 Gate：按审阅标准改稿 → 对比预览 */
export async function reviseFromCriteriaOnReview(page: Page) {
  await page.getByRole('button', { name: '按审阅标准改稿' }).click()
  await expect(page.getByText('对比修改')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('改稿后苏瑶放慢了脚步')).toBeVisible({
    timeout: 15_000,
  })
}

/** 审阅 Gate：有问题 → 用户说明改稿 → 对比预览 */
export async function userNoteReviseFromReview(page: Page, note: string) {
  await page.getByRole('button', { name: '有问题，改稿' }).click()
  await expect(page.getByRole('heading', { name: '通过还是修改？' })).toBeVisible()
  await page.getByRole('button', { name: '改本章' }).click()
  await expect(page.getByRole('heading', { name: '说明改哪里' })).toBeVisible()
  await page
    .getByPlaceholder('例如：情感节奏太快，苏瑶的犹豫要更深')
    .fill(note)
  await page.getByRole('button', { name: '生成修改版' }).click()
  await expect(page.getByText('对比修改')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('改稿后苏瑶放慢了脚步')).toBeVisible({
    timeout: 15_000,
  })
}

/** 改稿对比页：采纳修改版，回到审阅 Gate */
export async function acceptRevisePreview(page: Page) {
  await page.getByRole('button', { name: '用这个版本' }).click()
  await expect(page.getByRole('heading', { name: '质量审阅' })).toBeVisible({
    timeout: 30_000,
  })
}

/** 标准模式：质量审阅 Gate — 勾选全部「必须」后通过 */
export async function passReviewGate(page: Page) {
  await expect(page.getByRole('heading', { name: '质量审阅' })).toBeVisible({
    timeout: 30_000,
  })
  const hardChecks = page.locator('p:has-text("必须")').locator('..').locator('input[type="checkbox"]')
  const count = await hardChecks.count()
  for (let i = 0; i < count; i += 1) {
    const box = hardChecks.nth(i)
    if (!(await box.isChecked())) {
      await box.check()
    }
  }
  await page.getByRole('button', { name: '通过，进入下一步 →' }).click()
}

/** 亮点 Gate：跳过 */
export async function skipHighlightsGate(page: Page) {
  await expect(page.getByRole('heading', { name: '本章亮点' })).toBeVisible({
    timeout: 30_000,
  })
  await page.getByRole('button', { name: '跳过' }).click()
}

/** 节奏 Gate：若有则点继续 */
export async function dismissRhythmGateIfShown(page: Page) {
  const rhythmContinue = page.getByRole('button', { name: '继续' })
  if (await rhythmContinue.isVisible({ timeout: 4_000 }).catch(() => false)) {
    await rhythmContinue.click()
  }
}

/** 亮点/节奏之后：短篇跳过概述直达完成，长篇走概述 Gate */
export async function finishChapterGateAfterHighlights(page: Page, chapterNum = 1) {
  await dismissRhythmGateIfShown(page)

  const summaryHeading = page.getByRole('heading', { name: '确认本章摘要' })
  const doneHeading = page.getByRole('heading', {
    name: `第 ${chapterNum} 章完成！`,
  })

  const next = await Promise.race([
    summaryHeading
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => 'summary' as const),
    doneHeading
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => 'done' as const),
  ]).catch(() => null)

  if (next === 'summary') {
    await page.getByRole('button', { name: '确认' }).click()
    await expectChapterDoneGate(page, chapterNum)
    return
  }
  if (next === 'done') {
    return
  }
  throw new Error('亮点/节奏之后未进入概述或章完成')
}

/** 概述 Gate：确认（仅长篇；短篇请用 finishChapterGateAfterHighlights） */
export async function confirmSummaryGate(page: Page) {
  await expect(page.getByRole('heading', { name: '确认本章摘要' })).toBeVisible({
    timeout: 30_000,
  })
  await page.getByRole('button', { name: '确认' }).click()
}

/** 章 Gate 完成态 */
export async function expectChapterDoneGate(page: Page, chapterNum = 1) {
  await expect(
    page.getByRole('heading', { name: `第 ${chapterNum} 章完成！` }),
  ).toBeVisible({ timeout: 30_000 })
}

/** 标准模式：采纳 → 审阅 → 亮点 → （概述或章完成） */
export async function runStandardModeChapterGateUI(page: Page) {
  await adoptPreviewGate(page)
  await passReviewGate(page)
  await skipHighlightsGate(page)
  await finishChapterGateAfterHighlights(page)
}

/** 完结页 + 稿件投递 UI（创建稿件走 API 避免弹窗视口问题） */
export async function runCompleteAndSubmitUI(
  page: Page,
  request: APIRequestContext,
  bookTitle: string,
) {
  await page.goto('/complete')
  await expect(page.getByRole('heading', { name: '完结！' })).toBeVisible()
  await page.getByRole('button', { name: '标记全书完结' }).click()
  await page.getByRole('button', { name: '去投递稿件 →' }).click()
  await expect(page).toHaveURL(/\/manuscripts/)

  await page.getByRole('button', { name: '新建稿件' }).click()
  await expect(page.getByRole('heading', { name: '新建稿件' })).toBeVisible()

  await createAndSubmitManuscript(request, bookTitle)
  await page.reload()

  const recordBtn = page.getByRole('button', { name: '录入投递结果' })
  await expect(recordBtn).toBeVisible({ timeout: 20_000 })
  await recordBtn.click()

  const passBtn = page.getByRole('button', { name: '编辑通过' })
  await expect(passBtn).toBeVisible()
  await passBtn.click()

  await expect(page.getByText('通过', { exact: true }).first()).toBeVisible({
    timeout: 10_000,
  })
}

/** 章 Gate UI 走完后用 API 标记 approved（与 mock 定稿链配合，用于完结前置） */
export async function markChapterApprovedForComplete(
  request: APIRequestContext,
  chapterNum = 1,
) {
  await approveChapterForE2E(request, chapterNum)
}
