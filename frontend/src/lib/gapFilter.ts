import type { ReviewGap } from '@/lib/criteriaRevise'

const FAIL_HINTS = [
  '不通过',
  '未通过',
  '没过',
  '未能通过',
  '尚未通过',
  '未达标',
  '有风险',
  '需要重写',
  '需改',
  '偏弱',
  '不足',
  '缺失',
  '问题',
  '红线',
]

/** 与 core/review_gaps.gap_looks_passing 对齐 */
export function gapLooksPassing(description: string): boolean {
  const text = description.trim()
  if (!text) return false
  if (/✅|☑|✔/.test(text)) return true
  if (FAIL_HINTS.some((h) => text.includes(h))) return false
  if (/⚠|❌/.test(text)) return false
  if (/(?<![未不])通过|(?<![未不])达标|成立|无问题|\bok\b/i.test(text)) {
    return true
  }
  if (/合格(?!但)|已满足|无差距|全部达标/i.test(text)) return true
  return false
}

export function filterOpenGaps(gaps: ReviewGap[] | undefined): ReviewGap[] {
  return (gaps ?? []).filter((g) => !gapLooksPassing(g.description ?? ''))
}
