import { api } from '@/api/client'
import type {
  ActiveBookResponse,
  AppStatus,
  LibraryListResponse,
  ModelsConfigResponse,
  PromptCacheStatus,
  StatsResponse,
  WorkQueueResponse,
} from '@/types/api'

/** 书架：GET /api/library（非 /api/books） */
export function fetchLibrary() {
  return api<LibraryListResponse>('/api/library')
}

export function fetchActiveBook() {
  return api<ActiveBookResponse>('/api/library/active')
}

export function fetchStats() {
  return api<StatsResponse>('/api/stats')
}

export function createBook(body: {
  title?: string
  type?: string
  platform?: string
  world_label?: string
}) {
  return api<Record<string, unknown>>('/api/library/books', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function switchBook(bookId: string) {
  return api<Record<string, unknown>>('/api/library/switch', {
    method: 'POST',
    body: JSON.stringify({ book_id: bookId }),
  })
}

export function updateBook(
  bookId: string,
  body: {
    title?: string
    type?: string
    platform?: string
    world_label?: string
    tagline?: string
  },
) {
  return api<Record<string, unknown>>(`/api/library/books/${encodeURIComponent(bookId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function trashBook(bookId: string) {
  return api<Record<string, unknown>>(
    `/api/library/books/${encodeURIComponent(bookId)}/trash`,
    { method: 'POST' },
  )
}

export function trashBooks(bookIds: string[]) {
  return api<{
    ok?: boolean
    trashed?: Array<{ book_id?: string }>
    failed?: Array<{ book_id?: string; error?: string }>
    count?: number
    context_refreshed?: boolean
  }>('/api/library/batch/trash', {
    method: 'POST',
    body: JSON.stringify({ book_ids: bookIds }),
  })
}

export function fetchLibraryTrash() {
  return api<import('@/types/api').LibraryTrashResponse>('/api/library/trash')
}

export function restoreBook(bookId: string) {
  return api<Record<string, unknown>>(
    `/api/library/trash/${encodeURIComponent(bookId)}/restore`,
    { method: 'POST' },
  )
}

export function purgeBook(bookId: string) {
  return api<Record<string, unknown>>(
    `/api/library/trash/${encodeURIComponent(bookId)}`,
    { method: 'DELETE' },
  )
}

export function purgeBooks(bookIds: string[]) {
  return api<{
    ok?: boolean
    purged?: string[]
    failed?: Array<{ book_id?: string; error?: string }>
    count?: number
  }>('/api/library/batch/purge', {
    method: 'POST',
    body: JSON.stringify({ book_ids: bookIds }),
  })
}

export function purgeAllTrash() {
  return api<Record<string, unknown>>('/api/library/trash', { method: 'DELETE' })
}

export function fetchStatus() {
  return api<AppStatus>('/api/status')
}

export function fetchWorkQueue() {
  return api<WorkQueueResponse>('/api/flow/work-queue')
}

export function fetchFlowSteps() {
  return api<Record<string, unknown>>('/api/flow/steps')
}

export function fetchModelsConfig() {
  return api<ModelsConfigResponse>('/api/config/models')
}

export function updateModelsConfig(nodeModels: Record<string, unknown>) {
  return api<ModelsConfigResponse>('/api/config/models', {
    method: 'PUT',
    body: JSON.stringify({ node_models: nodeModels }),
  })
}

export function fetchPromptCacheStatus() {
  return api<PromptCacheStatus>('/api/tools/prompt-cache/status')
}

export function refreshPromptCache() {
  return api<PromptCacheStatus>('/api/tools/prompt-cache/refresh', {
    method: 'POST',
  })
}

export function updatePromptCacheSettings(body: {
  heartbeat_enabled?: boolean
  prompt_cache_auto_refresh?: boolean
}) {
  return api<PromptCacheStatus>('/api/tools/prompt-cache/settings', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function setWritingProvider(provider: string) {
  return api<AppStatus>('/api/config/provider', {
    method: 'PUT',
    body: JSON.stringify({ provider }),
  })
}

export function prefillDirection(body: {
  seed?: string
  reference_excerpt?: string
  chapter_count?: number
}) {
  return api<import('@/types/api').PrefillDirectionResponse>(
    '/api/prefill/direction',
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function applyDirection(option: Record<string, unknown>, logId?: string) {
  return api<Record<string, unknown>>('/api/prefill/direction/apply', {
    method: 'POST',
    body: JSON.stringify({ option, log_id: logId ?? null }),
  })
}

export function prefillPlan(body: {
  direction_option?: Record<string, unknown>
  chapter_count?: number
}) {
  return api<import('@/types/api').PrefillPlanResponse>('/api/prefill/plan', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function validatePlan(
  option: Record<string, unknown>,
  replace = true,
) {
  return api<import('@/lib/planValidation').PlanValidationResult>(
    '/api/prefill/plan/validate',
    {
      method: 'POST',
      body: JSON.stringify({ option, replace, log_id: null }),
    },
  )
}

export function semanticValidatePlan(
  option: Record<string, unknown>,
  replace = true,
) {
  return api<import('@/lib/planValidation').PlanSemanticValidationResult>(
    '/api/prefill/plan/semantic-validate',
    {
      method: 'POST',
      body: JSON.stringify({ option, replace, log_id: null }),
    },
  )
}

export function applyPlan(
  option: Record<string, unknown>,
  replace = true,
  logId?: string,
) {
  return api<Record<string, unknown>>('/api/prefill/plan/apply', {
    method: 'POST',
    body: JSON.stringify({ option, replace, log_id: logId ?? null }),
  })
}

export function fetchChatHistory() {
  return api<{
    messages: Array<{ role: string; content?: string }>
    appended_indices: number[]
  }>('/api/chat/history')
}

export function restoreChatSession() {
  return api<{
    ok: boolean
    saved_at?: string
    message_count?: number
    pending_writes?: number
    chapter_num?: number
    write_chapter_num?: number | null
    error?: string
  }>('/api/chat/restore', { method: 'POST' })
}

export function clearChatSession() {
  return api<{ ok: boolean }>('/api/chat/clear', { method: 'POST' })
}

export function setWriteChapter(chapterNum: number) {
  return api<{ ok: boolean; write_chapter_num?: number | null }>(
    '/api/chat/write-chapter',
    {
      method: 'PUT',
      body: JSON.stringify({ chapter_num: chapterNum }),
    },
  )
}

export function runDeconstruct(text: string, sourceLabel = '') {
  return api<{
    ok: boolean
    reply?: string
    log_id?: string
    deconstruct_id?: string
    patterns?: { hook_patterns?: string[]; structure_notes?: string[] }
    error?: string
  }>('/api/deconstruct', {
    method: 'POST',
    body: JSON.stringify({ text, source_label: sourceLabel }),
  })
}

export function importDeconstruct(
  qualityLogId: string,
  mergeGlobal = true,
  hookPatterns?: string[],
  structureNotes?: string[],
) {
  return api<Record<string, unknown>>('/api/taste/import-deconstruct', {
    method: 'POST',
    body: JSON.stringify({
      quality_log_id: qualityLogId,
      merge_global: mergeGlobal,
      hook_patterns: hookPatterns,
      structure_notes: structureNotes,
    }),
  })
}

export function initReviewCriteria(profileId = '') {
  const q = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ''
  return api<{
    ok: boolean
    profile_id?: string
    review_criteria?: Record<string, unknown>
  }>(`/api/plan/review-criteria/init${q}`, { method: 'POST' })
}

export function updateReviewCriteria(fields: Record<string, unknown>) {
  return api<Record<string, unknown>>('/api/plan/review-criteria', {
    method: 'PUT',
    body: JSON.stringify(fields),
  })
}

export function fetchCostSummary() {
  return api<import('@/types/api').CostSummaryResponse>('/api/cost/summary')
}
