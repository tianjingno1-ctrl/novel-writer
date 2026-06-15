import { api } from '@/api/client'

export type PrecheckIssue = {
  code?: string
  severity?: string
  message?: string
  ai_tone?: { score?: number; threshold?: number; level?: string }
}

export type PrecheckResult = {
  ok: boolean
  chapter_num?: number
  chapter_role?: string
  word_count?: number
  word_count_target?: number | null
  platform?: string
  ai_tone?: {
    score?: number
    threshold?: number
    level?: string
    passed?: boolean
  }
  issues?: PrecheckIssue[]
  should_rewrite?: boolean
  error?: string
}

export type ReviewResult = {
  ok: boolean
  reply?: string
  log_id?: string
  review_log_id?: string
  chapter_num?: number
  revised_text?: string
  pending_accept?: boolean
  profile_id?: string
  profile_label?: string
  revise?: boolean
  error?: string
  precheck?: PrecheckResult
}

export type JudgmentResult = {
  ok: boolean
  error?: string
}

export type FinalizeResult = {
  ok: boolean
  chapter_num?: number
  skipped?: boolean
  summary_skipped?: boolean
  chapter_complete?: boolean
  reason?: string
  archive?: {
    summary?: {
      ok?: boolean
      text?: string
      full_text?: string
    }
  }
  error?: string
}

export type SummaryConfirmResult = {
  ok: boolean
  summary?: { content?: string }
  error?: string
}

export async function fetchChatHistory() {
  return api<{
    messages: Array<{ role: string; content?: string }>
    appended_indices: number[]
    conversation_chapter_num?: number | null
  }>('/api/chat/history')
}

export async function applyChapterTurn(chapterNum: number, msgIndex: number) {
  return api<{ ok: boolean; error?: string }>(
    `/api/chapters/${chapterNum}/apply-turn`,
    {
      method: 'POST',
      body: JSON.stringify({ msg_index: msgIndex, source: 'assistant' }),
    },
  )
}

export async function runChapterPrecheck(
  chapterNum: number,
  content = '',
  opts?: { skip_paywall_intent?: boolean },
) {
  return api<PrecheckResult>(`/api/chapters/${chapterNum}/precheck`, {
    method: 'POST',
    body: JSON.stringify({
      content,
      skip_paywall_intent: opts?.skip_paywall_intent ?? false,
    }),
  })
}

export async function runFemaleFictionReview(
  chapterNum: number,
  opts: {
    text?: string
    revise?: boolean
    skip_precheck?: boolean
    skip_paywall_intent?: boolean
    revise_note?: string
  } = {},
) {
  return api<ReviewResult>('/api/review/chapter', {
    method: 'POST',
    body: JSON.stringify({
      chapter_num: chapterNum,
      text: opts.text ?? '',
      revise: opts.revise ?? false,
      skip_precheck: opts.skip_precheck ?? true,
      skip_paywall_intent: opts.skip_paywall_intent ?? false,
      revise_note: opts.revise_note ?? '',
    }),
  })
}

export async function recordJudgment(
  logId: string,
  outcome: 'accepted' | 'rejected' | 'needs_revision',
  note = '',
  issueTags?: string[],
) {
  return api<JudgmentResult>(`/api/quality/log/${logId}/judgment`, {
    method: 'POST',
    body: JSON.stringify({
      outcome,
      note,
      issue_tags: issueTags ?? [],
    }),
  })
}

export async function finalizeChapter(chapterNum: number) {
  return api<FinalizeResult>('/api/post-chapter/finalize', {
    method: 'POST',
    body: JSON.stringify({ chapter_num: chapterNum }),
  })
}

export async function pushChapterHighlight(
  chapterNum: number,
  body: {
    text: string
    annotation?: string
    tags?: string[]
    skip_conflict_check?: boolean
  },
) {
  return api<{
    ok: boolean
    error?: string
    conflicts?: Array<{ kind?: string; message?: string; ref?: string }>
  }>(`/api/taste/highlights/${chapterNum}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function createAttributionLog(
  chapterNum: number,
  source: 'L4a' | 'L5b' = 'L5b',
  note = '',
) {
  return api<{ ok: boolean; log_id?: string; error?: string }>(
    `/api/chapters/${chapterNum}/attribution-log`,
    {
      method: 'POST',
      body: JSON.stringify({ source, note }),
    },
  )
}

export async function confirmChapterSummary(chapterNum: number) {
  return api<SummaryConfirmResult>(
    `/api/chapters/${chapterNum}/summary/confirm`,
    { method: 'POST' },
  )
}

export async function acceptFemaleFictionRewrite(logId: string) {
  return api<{ ok: boolean; error?: string }>(
    '/api/review/chapter/accept',
    {
      method: 'POST',
      body: JSON.stringify({ log_id: logId }),
    },
  )
}

/** 从审阅回复中提取最重要一条（不堆砌清单） */
const REVIEW_META_LINE =
  /^(profile\s*[:：]|本书类型|目标平台|mode\s*[:：]|>+\s*\*)/i

function isReviewMetadataLine(line: string): boolean {
  const t = line.trim()
  if (!t) return true
  if (REVIEW_META_LINE.test(t)) return true
  if (/^profile\s*[:：]/i.test(t)) return true
  return false
}

function isActionableReviewLine(line: string): boolean {
  return /改法|建议|问题|结论|⚠|偏弱|不足|钩子|差距|待改|must-fix/i.test(line)
}

/** 改稿预览正文：优先 revised_text */
export function extractReviseDraft(rev: ReviewResult): string {
  return (rev.revised_text ?? rev.reply ?? '').trim()
}

export function pickTopReviewNote(reply: string): string {
  const lines = (reply || '')
    .split('\n')
    .map((l) => l.replace(/^[\s\-*·✓✗•>]+/, '').trim())
    .filter((l) => l.length > 8 && !l.startsWith('#'))

  const actionable = lines.filter(
    (l) => !isReviewMetadataLine(l) && isActionableReviewLine(l),
  )
  if (actionable[0]) return actionable[0]

  const substantive = lines.filter((l) => !isReviewMetadataLine(l))
  return (substantive[0] ?? lines[0] ?? reply.slice(0, 120)).trim()
}

export function precheckPassLines(result: PrecheckResult): string[] {
  const lines: string[] = []
  if (result.word_count != null) {
    const target = result.word_count_target
    if (target) {
      lines.push(`字数 ${result.word_count}（目标约 ${target}）`)
    } else {
      lines.push(`字数 ${result.word_count}`)
    }
  }
  const hard = (result.issues ?? []).filter((i) => i.severity === 'hard')
  const soft = (result.issues ?? []).filter((i) => i.severity === 'soft')
  if (hard.length === 0 && result.ok) {
    lines.unshift('字数达标')
    const tone = result.ai_tone
    if (tone && (tone.passed === true || tone.level === 'low')) {
      lines.push('AI 腔风险可控')
    }
    if (soft.length > 0) {
      lines.push(`预检建议 ${soft.length} 项（审阅门可见）`)
    }
  }
  return lines
}

export { precheckFailMessage, splitPrecheckIssues } from '@/lib/precheckIssues'
