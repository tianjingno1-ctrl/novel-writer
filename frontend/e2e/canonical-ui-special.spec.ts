import { expect, test } from '@playwright/test'

import { mockChapterBody, saveChapterContent, seedReadyBook } from './helpers/api'
import {
  REGENERATED_BODY_MARKER,
  setupChatStreamRegenerateMock,
  setupStandardModeGateMocks,
  setupStandardReviewReviseMocks,
} from './helpers/mocks'
import {
  acceptRevisePreview,
  adoptPreviewGate,
  expectBodyMarker,
  finishChapterGateAfterHighlights,
  openWritingFromShelf,
  passReviewGate,
  reachReviewGate,
  regenerateFromPreviewGate,
  reviseFromCriteriaOnReview,
  skipHighlightsGate,
  userNoteReviseFromReview,
} from './helpers/ui-flow'

test.describe('Canonical UI 专项（重新生成 / 改稿）', () => {
  test('整章重新生成：覆盖旧稿 → 新预览 → 采纳完成', async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000)

    const title = `E2E 重新生成 ${Date.now()}`
    const body = mockChapterBody('初遇')

    await seedReadyBook(request, title)
    await saveChapterContent(request, 1, body)
    await setupStandardModeGateMocks(page)
    await setupChatStreamRegenerateMock(page)

    await openWritingFromShelf(page, title)
    await expectBodyMarker(page, '池瑶推开门')

    await regenerateFromPreviewGate(page)
    await expectBodyMarker(page, REGENERATED_BODY_MARKER)
    await expect(page.getByRole('heading', { name: '预览，是否采纳？' })).toBeVisible({
      timeout: 30_000,
    })

    await adoptPreviewGate(page, REGENERATED_BODY_MARKER)
    await passReviewGate(page)
    await skipHighlightsGate(page)
    await finishChapterGateAfterHighlights(page)
  })

  test('按审阅标准改稿：审阅 Gate → 对比 → 回到审阅并通过', async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000)

    const title = `E2E 标准改稿 ${Date.now()}`
    const body = mockChapterBody('初遇')

    await seedReadyBook(request, title)
    await saveChapterContent(request, 1, body)
    await setupStandardReviewReviseMocks(page)

    await openWritingFromShelf(page, title)
    await reachReviewGate(page)

    await reviseFromCriteriaOnReview(page)
    await acceptRevisePreview(page)
    await passReviewGate(page)

    await expect(page.getByRole('heading', { name: '本章亮点' })).toBeVisible({
      timeout: 30_000,
    })
  })

  test('用户说明改稿：有问题 → 填写说明 → 对比 → 回到审阅', async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000)

    const title = `E2E 用户改稿 ${Date.now()}`
    const body = mockChapterBody('初遇')

    await seedReadyBook(request, title)
    await saveChapterContent(request, 1, body)
    await setupStandardReviewReviseMocks(page)

    await openWritingFromShelf(page, title)
    await reachReviewGate(page)

    await userNoteReviseFromReview(
      page,
      '情感节奏太快，苏瑶的犹豫要更深，对白再克制一点。',
    )
    await acceptRevisePreview(page)

    await expect(
      page.getByRole('button', { name: '按审阅标准改稿' }),
    ).toBeVisible()
    await expect(
      page.getByRole('button', { name: '通过，进入下一步 →' }),
    ).toBeVisible()
  })
})
