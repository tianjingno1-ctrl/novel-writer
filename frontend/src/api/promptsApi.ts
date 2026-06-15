import { api } from '@/api/client'

export type PromptNodeSummary = {
  node_id: string
  label: string
  category: string
  prompt_id?: string | null
  review_profile?: boolean
  description?: string
  has_override?: boolean
}

export type PromptNodeDetail = {
  ok?: boolean
  node_id?: string
  system?: string
  prompt_source?: string
  prompt_hash?: string
  prompt_id?: string | null
  profile_id?: string | null
  override?: {
    system?: string
    append?: string
    prepend?: string
  } | null
  error?: string
}

export type PromptFlowStep = {
  node_id?: string
  label?: string
  stage?: string
}

export function fetchPromptNodes() {
  return api<{
    ok?: boolean
    nodes?: PromptNodeSummary[]
    overrides_path?: string
  }>('/api/prompts/nodes')
}

export function fetchPromptNode(nodeId: string) {
  return api<PromptNodeDetail>(`/api/prompts/nodes/${encodeURIComponent(nodeId)}`)
}

export function updatePromptNodeOverride(
  nodeId: string,
  body: {
    system?: string
    append?: string
    prepend?: string
    clear?: boolean
  },
) {
  return api<PromptNodeDetail>(`/api/prompts/nodes/${encodeURIComponent(nodeId)}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function fetchPromptFlow() {
  return api<{ ok?: boolean; steps?: PromptFlowStep[]; nodes?: PromptNodeSummary[] }>(
    '/api/prompts/flow',
  )
}

export const PROMPT_SOURCE_LABEL: Record<string, string> = {
  global: '全局默认',
  book_override: '本书覆盖',
  review_profile: '审阅标准',
}

export const PROMPT_CATEGORY_LABEL: Record<string, string> = {
  writing: '写作',
  review: '审阅',
  prefill: '开书预填',
  maintain: '章后维护',
  check: '检查',
  diagnose: '归因',
}
