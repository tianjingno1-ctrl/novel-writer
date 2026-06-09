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

export type ReaderPreviewResult = {
  chapter_num?: number
  payoff_density?: string
  payoff_score?: number
  drop_off_risk?: string
  drop_off_score?: number
  drop_off_reason?: string
  matched_emotions?: string[]
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

export function fetchReaderPreview(chapterNum: number, content = '') {
  return api<{ ok: boolean; reader_preview?: ReaderPreviewResult }>(
    `/api/chapters/${chapterNum}/reader-preview`,
    { method: 'POST', body: JSON.stringify({ content }) },
  )
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

export function fetchChaptersList() {
  return api<{ chapters?: Array<{ num: number; title?: string; chars?: number }> }>(
    '/api/chapters',
  )
}

export function fetchChapter(num: number) {
  return api<{ num?: number; content?: string; title?: string }>(
    `/api/chapters/${num}`,
  )
}

export function saveChapter(num: number, content: string) {
  return api<Record<string, unknown>>(`/api/chapters/${num}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
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
  return api<Record<string, unknown>>(`/api/manuscripts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(fields),
  })
}

export type ManuscriptRow = {
  id: string
  title?: string
  state?: string
  book_id?: string
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
