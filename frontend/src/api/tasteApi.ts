import { api } from '@/api/client'

export function fetchTasteGlobal() {
  return api<{ ok?: boolean; doc?: TasteDoc }>('/api/taste/global')
}

export function updateTasteGlobal(preferences: Record<string, unknown>) {
  return api<Record<string, unknown>>('/api/taste/global', {
    method: 'PUT',
    body: JSON.stringify({ preferences }),
  })
}

export function fetchTasteBook() {
  return api<{ ok?: boolean; doc?: TasteDoc }>('/api/taste/book')
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

export type TasteDoc = {
  version?: number
  rules?: Array<{ id?: string; content?: string; ref?: string }>
  examples?: Array<{ id?: string; content?: string; annotation?: string }>
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
