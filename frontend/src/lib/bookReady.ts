/** 与后端 bookshelf_stats 一致：是否可进入 Gate 写作（非开书向导）。 */

export type PlanProductLike = {
  meta?: Record<string, unknown>
  chapter_statuses?: Record<string, string>
  review_criteria?: {
    hard_rules?: unknown[]
    soft_rules?: unknown[]
    custom_checks?: unknown[]
  }
}

export function isBookWritingReady(plan: PlanProductLike | null | undefined): boolean {
  if (!plan) return false
  const meta = plan.meta ?? {}
  if (meta.wizard_complete === true) return true

  const logline = String(meta.logline ?? '').trim()
  const chapterCount = Object.keys(plan.chapter_statuses ?? {}).length
  const review = plan.review_criteria ?? {}
  const hasCriteria = Boolean(
    (review.hard_rules?.length ?? 0) > 0 ||
      (review.soft_rules?.length ?? 0) > 0 ||
      (review.custom_checks?.length ?? 0) > 0,
  )
  return Boolean(logline) && chapterCount > 0 && hasCriteria
}
