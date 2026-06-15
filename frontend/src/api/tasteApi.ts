import { api } from '@/api/client'

export function fetchTasteGlobal() {
  return api<{ ok?: boolean; global?: TasteDoc }>('/api/taste/global')
}

export function updateTasteGlobal(preferences: Record<string, unknown>) {
  return api<Record<string, unknown>>('/api/taste/global', {
    method: 'PUT',
    body: JSON.stringify({ preferences }),
  })
}

export function fetchTasteBook() {
  return api<{
    ok?: boolean
    book_id?: string
    taste?: TasteDoc
    merged_preferences?: Record<string, unknown>
  }>('/api/taste/book')
}

export function deleteTasteRule(ruleId: string) {
  return api<{ ok?: boolean; rule?: { id?: string; content?: string } }>(
    `/api/taste/rules/${encodeURIComponent(ruleId)}`,
    { method: 'DELETE' },
  )
}

export function localizeTasteRule(ruleId: string) {
  return api<{ ok?: boolean; book_id?: string; rule?: { id?: string } }>(
    `/api/taste/rules/${encodeURIComponent(ruleId)}/localize`,
    { method: 'POST' },
  )
}

export function fetchTasteSummary() {
  return api<Record<string, unknown>>('/api/taste/summary')
}

export function fetchTasteEvents(limit = 40) {
  return api<{ events?: TasteEvent[] }>(`/api/taste/events?limit=${limit}`)
}

export function fetchAuthorProfile() {
  return api<{ ok?: boolean; profile?: AuthorProfileDoc }>(
    '/api/taste/author-profile',
  )
}

export function extractAuthorProfile() {
  return api<{ ok?: boolean; profile?: AuthorProfileDoc }>(
    '/api/taste/author-profile/extract',
    { method: 'POST' },
  )
}

export function applyAuthorProfile(body: {
  inherit_all?: boolean
  rule_ids?: string[]
}) {
  return api<Record<string, unknown>>('/api/taste/author-profile/apply', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export type AuthorProfileDoc = {
  version?: number
  rules?: Array<{ content?: string; weight?: string; source_book_id?: string }>
  reader_patterns?: Array<{ good_emotions?: string[]; book_title?: string }>
  books?: Array<{ book_id?: string; book_title?: string }>
}

export type TasteRule = {
  id?: string
  content?: string
  ref?: string
  weight?: 'hard' | 'soft'
}

export type TasteDoc = {
  version?: number
  rules?: TasteRule[]
  examples?: Array<{ id?: string; content?: string; text?: string; annotation?: string }>
  preferences?: Record<string, unknown>
}

export type TasteEvent = {
  id?: string
  source?: string
  outcome?: string
  issue_tags?: string[]
  note?: string
  created_at?: string
}
