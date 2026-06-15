import { api } from '@/api/client'

import type { ResolvedCriteria } from '@/types/api'

export function fetchPlanProduct() {
  return api<{
    ok: boolean
    meta?: Record<string, unknown>
    chapter_statuses?: Record<string, string>
    review_criteria?: Record<string, unknown>
    resolved_criteria?: ResolvedCriteria
  }>('/api/plan/product')
}

export function updatePlanMeta(meta: Record<string, unknown>) {
  return api<{ ok: boolean; meta?: Record<string, unknown> }>(
    '/api/plan/meta',
    { method: 'PUT', body: JSON.stringify({ meta }) },
  )
}

export function fetchRhythmCheck(chapterNum: number) {
  return api<{
    ok: boolean
    l5b_mandatory?: boolean
    l5b_priority?: string
    chapter_role?: string
    rhythm_warning?: {
      warning?: boolean
      message?: string
      chapters?: number[]
    }
  }>(`/api/chapters/${chapterNum}/rhythm-check`, { method: 'POST' })
}

export type CompliancePreviewResult = {
  ok?: boolean
  platform?: string
  threshold?: number
  risk_score?: number
  risk_level?: string
  high_risk_chapters?: Array<{
    chapter_num?: number
    ai_tone_score?: number
    snippets?: string[]
  }>
  can_submit?: boolean
}

export function fetchCompliancePreview(submissionTarget: string) {
  return api<CompliancePreviewResult>('/api/compliance/preview', {
    method: 'POST',
    body: JSON.stringify({ submission_target: submissionTarget }),
  })
}

export function fetchChapterSummary(num: number) {
  return api<{
    ok: boolean
    summary?: {
      content?: string
      status?: string
      highlights_draft?: Array<{ text?: string; annotation?: string }>
    }
  }>(`/api/chapters/${num}/summary`)
}

export type ChapterReviewGap = {
  rule_ref?: string
  description?: string
  severity?: 'hard' | 'soft' | string
}

export type ChapterReviewRound = {
  round?: number
  judgment?: string
  issue_tags?: string[]
  gaps?: ChapterReviewGap[]
  quality_log_id?: string
  review_excerpt?: string
  profile_id?: string
  ts?: string
  judged_at?: string
}

export function fetchChapterReview(num: number) {
  return api<{
    ok: boolean
    chapter_num?: number
    round_count?: number
    review?: { rounds?: ChapterReviewRound[] }
  }>(`/api/chapters/${num}/review`)
}

export function fetchChaptersList() {
  return api<{
    chapters?: Array<{
      num: number
      title?: string
      chars?: number
      word_count_target?: number | null
    }>
  }>('/api/chapters')
}

export function fetchChapter(num: number) {
  return api<{
    num?: number
    content?: string
    title?: string
    plan?: {
      title?: string
      hook?: string
      role?: string
      intent?: import('@/lib/chapterRoles').ChapterIntent
      word_count_target?: number | null
      scenes?: Array<{ title?: string; beat?: string; summary?: string }>
    }
  }>(`/api/chapters/${num}`)
}

export function saveChapter(num: number, content: string) {
  return api<Record<string, unknown>>(`/api/chapters/${num}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

export function fetchDiagnosis(diagnosisId: string) {
  return api<{
    ok: boolean
    diagnosis?: {
      id?: string
      analysis?: string
      issue_tags?: string[]
      patch?: {
        target_node?: string
        override?: { append?: string }
      }
    }
  }>(`/api/diagnosis/${diagnosisId}`)
}

export function runPromptDiagnose(qualityLogId: string) {
  return api<DiagnoseResponse>('/api/prompts/diagnose', {
    method: 'POST',
    body: JSON.stringify({ quality_log_id: qualityLogId }),
  })
}

export function previewPromptPatch(body: {
  node_id: string
  suggested_patch: string
  patch_mode?: string
  save?: boolean
}) {
  return api<Record<string, unknown>>('/api/prompts/diagnose/preview', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function rerunPreview(body: {
  scope: string
  from_chapter_num?: number
  current_chapter_num?: number
}) {
  return api<{ ok: boolean; impact_preview?: string; locked_chapters?: number[] }>(
    '/api/rerun/preview',
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function decideDiagnosis(
  diagnosisId: string,
  body: {
    accepted: boolean
    rerun_scope?: string
    from_chapter_num?: number
    apply_override?: boolean
    execute_rerun?: boolean
    apply_author_profile?: boolean
    author_profile_book_id?: string
  },
) {
  return api<Record<string, unknown>>(`/api/diagnosis/${diagnosisId}/decide`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function fetchLifecycle() {
  return api<{ ok: boolean; lifecycle?: Record<string, unknown> }>(
    '/api/project/lifecycle',
  )
}

export function updateLifecycle(fields: Record<string, unknown>) {
  return api<Record<string, unknown>>('/api/project/lifecycle', {
    method: 'PUT',
    body: JSON.stringify(fields),
  })
}

export function listManuscripts(bookId?: string) {
  const q = bookId ? `?book_id=${encodeURIComponent(bookId)}` : ''
  return api<{ manuscripts?: ManuscriptRow[] }>(`/api/manuscripts${q}`)
}

export function createManuscript(title = '') {
  return api<Record<string, unknown>>('/api/manuscripts', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export function patchManuscript(
  id: string,
  fields: Record<string, unknown>,
) {
  return api<ManuscriptPatchResponse>(`/api/manuscripts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(fields),
  })
}

export type ManuscriptSubmission = {
  id?: string
  target?: string
  target_name?: string
  submitted_at?: string
  result?: string
  reject_tags?: string[]
  reject_reason?: string
  reject_kind?: string
  diagnosis_id?: string
  compliance_checked?: boolean
}

export type ManuscriptRow = {
  id: string
  title?: string
  state?: string
  book_id?: string
  submission?: ManuscriptSubmission
  last_submission?: ManuscriptSubmission
}

export type ManuscriptPatchResponse = {
  ok?: boolean
  diagnosis_id?: string
  rejection_fork?: 'content' | 'strategy'
  next_action?: string
  manuscript?: Record<string, unknown>
}

export type DiagnoseSuspect = {
  node_id?: string
  reason?: string
  suggested_patch?: string
  confidence?: number
}

export type DiagnoseResponse = {
  ok: boolean
  diagnosis_id?: string
  diagnosis?: {
    summary?: string
    suspects?: DiagnoseSuspect[]
  }
  error?: string
}
