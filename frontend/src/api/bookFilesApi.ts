import { api } from '@/api/client'

export type BookFileMeta = {
  key: string
  label: string
  group?: string
  group_label?: string
  hint?: string
  filename?: string
  chars?: number
  exists?: boolean
}

export function fetchBookFiles() {
  return api<{
    ok: boolean
    book_type?: string
    scope?: 'setting_only' | 'full'
    files?: BookFileMeta[]
  }>('/api/book/files')
}

export function fetchBookFile(key: string) {
  return api<{
    ok: boolean
    key?: string
    label?: string
    hint?: string
    content?: string
    chars?: number
    error?: string
  }>(`/api/book/files/${encodeURIComponent(key)}`)
}

export function saveBookFile(key: string, content: string) {
  return api<{ ok: boolean; key?: string; chars?: number; error?: string }>(
    `/api/book/files/${encodeURIComponent(key)}`,
    {
      method: 'PUT',
      body: JSON.stringify({ content }),
    },
  )
}
