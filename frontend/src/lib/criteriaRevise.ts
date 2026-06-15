import { filterOpenGaps } from '@/lib/gapFilter'

export type ReviewGap = {
  rule_ref?: string
  description?: string
  severity?: string
}

/** 将 L4 gaps / 审阅摘要拼成 revise_note（与 core/review_gaps.format_gaps_revise_note 对齐） */
export function buildCriteriaReviseNote(opts: {
  gaps?: ReviewGap[]
  reviewReply?: string
}): string {
  const gaps = filterOpenGaps(opts.gaps)
  const lines = ['请按以下审阅差距修改本章正文（输出完整改稿）：', '']
  if (gaps.length > 0) {
    for (const g of gaps) {
      const sev = g.severity === 'hard' ? '必须' : '建议'
      const ref = (g.rule_ref ?? '').trim()
      const desc = (g.description ?? (ref || '未说明')).trim()
      lines.push(`- [${sev}] ${ref}: ${desc}`)
    }
  } else {
    lines.push('- 请对照审阅报告中的 must-fix 项逐条改稿')
  }
  const excerpt = (opts.reviewReply ?? '').trim().slice(0, 2000)
  if (excerpt) {
    lines.push('', '## 审阅摘要', excerpt)
  }
  if (lines.length <= 2 && !excerpt) {
    lines.push('请对照已注入的审阅标准，修正本章未达标项。')
  }
  return lines.join('\n').trim()
}

export { filterOpenGaps, gapLooksPassing } from '@/lib/gapFilter'
