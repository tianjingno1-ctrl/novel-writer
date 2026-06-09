/** 手写 API 类型（后续可用 openapi-typescript 生成到 api/generated/） */

export type LibraryBook = {
  id: string
  title?: string
  type?: string
  platform?: string
  world_label?: string
}

export type LibraryListResponse = {
  ok?: boolean
  books?: LibraryBook[]
  active_book_id?: string
}

export type AppStatus = {
  book_id?: string
  book_type?: string
  project_title?: string
  provider?: string
  provider_name?: string
  model?: string
  chapter_num?: number | null
  write_chapter_num?: number | null
  api_key_ok?: boolean
  total_cost?: number
}

export type FlowManualStep = {
  id: string
  label: string
  method: string
  path: string
  note?: string
  human_gate?: boolean
}

export type FlowRunResponse = {
  ok: boolean
  stop_reason?: string
  stopped_at?: string
  chapter_num?: number | null
  log_id?: string | null
  next_manual?: FlowManualStep
  manual_apis_note?: string
  error?: string | null
  executed?: Array<Record<string, unknown>>
}

export type WorkQueueResponse = {
  ok?: boolean
  chapter_statuses?: Record<string, string>
  pending_write?: number[]
  pending_review?: number[]
  pending_summary?: number[]
  locked?: number[]
  rhythm_warning?: {
    warning?: boolean
    message?: string
    chapters?: number[]
  }
}

export type ResolvedCriterion = {
  id?: string
  ref?: string
  label?: string
  content?: string
  description?: string
  weight?: string
}

export type ResolvedCriteria = {
  hard?: ResolvedCriterion[]
  soft?: ResolvedCriterion[]
}

/** POST /api/chat/stream SSE 事件（非 content 字段） */
export type SSEChunkEvent = { type: 'chunk'; text: string }
export type SSEDoneEvent = {
  type: 'done'
  chapter_num?: number
  chapter_saved?: boolean
  chapter_save_mode?: string
  chapter_title?: string
  cost?: number
  total_cost?: number
  model?: string
  provider?: string
}
export type SSEErrorEvent = { type: 'error'; message: string }
export type SSEEvent = SSEChunkEvent | SSEDoneEvent | SSEErrorEvent

export type ChatStreamRequest = {
  instruction: string
  scene_beat?: string
  scene_id?: string
  chapter_num?: number | null
}

export type NodeModelEntry = {
  provider: string
  model?: string
}

export type ModelsConfigResponse = {
  ok: boolean
  nodes: Array<{
    node_id: string
    label: string
    provider: string
    model: string
    overridden?: boolean
  }>
  providers: Array<{ id: string; name: string; model: string }>
  node_models: Record<string, NodeModelEntry>
}

export type DirectionOption = {
  id?: string
  logline?: string
  sell_point?: string
  tone?: string
  hook?: string
  title?: string
  chapter_count?: number
}

export type PrefillDirectionResponse = {
  ok: boolean
  options?: DirectionOption[]
  log_id?: string
  error?: string
}

export type PrefillPlanResponse = {
  ok: boolean
  option?: {
    title?: string
    chapters?: Array<{
      num?: number
      title?: string
      beat?: string
      hook?: string
    }>
  }
  log_id?: string
  error?: string
}

export type PromptCacheStatus = {
  ok: boolean
  writing_provider?: string
  writing_model?: string
  cache_supported?: boolean
  prompt_cache_auto_refresh?: boolean
  last_call?: Record<string, unknown>
}
