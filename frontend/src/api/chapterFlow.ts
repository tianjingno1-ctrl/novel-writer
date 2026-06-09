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
  chapter_num?: number
  revised_text?: string
  pending_accept?: boolean
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

export async function runChapterPrecheck(chapterNum: number, content = '') {
  return api<PrecheckResult>(`/api/chapters/${chapterNum}/precheck`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

export async function runFemaleFictionReview(
  chapterNum: number,
  opts: { text?: string; revise?: boolean; skip_precheck?: boolean } = {},
) {
  return api<ReviewResult>('/api/review/female-fiction', {
    method: 'POST',
    body: JSON.stringify({
      mode: 'chapter',
      chapter_num: chapterNum,
      text: opts.text ?? '',
      revise: opts.revise ?? false,
      skip_precheck: opts.skip_precheck ?? true,
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
  body: { text: string; annotation?: string; tags?: string[] },
) {
  return api<{ ok: boolean; error?: string }>(
    `/api/taste/highlights/${chapterNum}`,
    { method: 'POST', body: JSON.stringify(body) },
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
    '/api/review/female-fiction/accept',
    {
      method: 'POST',
      body: JSON.stringify({ log_id: logId }),
    },
  )
}

export async function fetchChapter(num: number) {
  return api<{ num?: number; content?: string; title?: string }>(
    `/api/chapters/${num}`,
  )
}

/** 从审阅回复中提取最重要一条（不堆砌清单） */
export function pickTopReviewNote(reply: string): string {
  const lines = (reply || '')
    .split('\n')
    .map((l) => l.replace(/^[\s\-*·✓✗•]+/, '').trim())
    .filter((l) => l.length > 8 && !l.startsWith('#'))
  return (lines[0] ?? reply.slice(0, 120)).trim()
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
  if (hard.length === 0 && result.ok) {
    lines.unshift('字数达标')
    const tone = result.ai_tone
    if (tone && (tone.passed === true || tone.level === 'low')) {
      lines.push('AI 腔风险可控')
    }
  }
  return lines
}

export function precheckFailMessage(result: PrecheckResult): string {
  const hard = (result.issues ?? []).filter((i) => i.severity === 'hard')
  return hard[0]?.message ?? result.error ?? '预检未通过'
}
