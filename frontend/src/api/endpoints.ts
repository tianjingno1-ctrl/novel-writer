import { api } from '@/api/client'
import type {
  AppStatus,
  FlowRunResponse,
  LibraryListResponse,
  ModelsConfigResponse,
  PromptCacheStatus,
  WorkQueueResponse,
} from '@/types/api'

/** 书架：GET /api/library（非 /api/books） */
export function fetchLibrary() {
  return api<LibraryListResponse>('/api/library')
}

export function fetchActiveBook() {
  return api<Record<string, unknown>>('/api/library/active')
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

export function fetchStatus() {
  return api<AppStatus>('/api/status')
}

export function fetchWorkQueue() {
  return api<WorkQueueResponse>('/api/flow/work-queue')
}

export function fetchFlowSteps() {
  return api<Record<string, unknown>>('/api/flow/steps')
}

export function runFlow(body: Record<string, unknown>) {
  return api<FlowRunResponse>('/api/flow/run', {
    method: 'POST',
    body: JSON.stringify(body),
  })
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

export function runDeconstruct(text: string, sourceLabel = '') {
  return api<{
    ok: boolean
    reply?: string
    log_id?: string
    deconstruct_id?: string
    error?: string
  }>('/api/deconstruct', {
    method: 'POST',
    body: JSON.stringify({ text, source_label: sourceLabel }),
  })
}

export function importDeconstruct(qualityLogId: string, mergeGlobal = true) {
  return api<Record<string, unknown>>('/api/taste/import-deconstruct', {
    method: 'POST',
    body: JSON.stringify({
      quality_log_id: qualityLogId,
      merge_global: mergeGlobal,
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
