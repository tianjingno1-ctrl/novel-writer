import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { getToken, setToken } from '@/api/client'
import {
  fetchModelsConfig,
  fetchPromptCacheStatus,
  refreshPromptCache,
  setWritingProvider,
  updatePromptCacheSettings,
} from '@/api/endpoints'
import { fetchAuthorProfile } from '@/api/tasteApi'
import { PageHeader } from '@/components/layout/PageHeader'
import { TastePanel } from '@/components/taste/TastePanel'
import { PromptNodesPanel } from '@/components/settings/PromptNodesPanel'
import { CostSummaryPanel } from '@/components/settings/CostSummaryPanel'
import {
  AuthorProfileInherit,
  StyleExtractPanel,
} from '@/components/product/ComplianceGate'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { id: 'taste', label: '写作偏好' },
  { id: 'prompts', label: 'Prompt 节点' },
  { id: 'cost', label: '费用统计' },
  { id: 'models', label: '模型配置' },
  { id: 'profile', label: '作者档案' },
  { id: 'auth', label: '鉴权' },
] as const

export function SettingsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'models'
  const promptNode = params.get('node') ?? ''
  const setTab = (id: string) => setParams({ tab: id })
  const [tokenInput, setTokenInput] = useState(getToken())

  const { data: models } = useQuery({
    queryKey: ['config', 'models'],
    queryFn: fetchModelsConfig,
  })

  const { data: cacheStatus, refetch: refetchCache } = useQuery({
    queryKey: ['tools', 'prompt-cache'],
    queryFn: fetchPromptCacheStatus,
  })

  const { data: profileData } = useQuery({
    queryKey: ['author-profile'],
    queryFn: fetchAuthorProfile,
    enabled: tab === 'profile',
  })

  const refreshCache = useMutation({
    mutationFn: refreshPromptCache,
    onSuccess: () => void refetchCache(),
  })

  const toggleAutoRefresh = useMutation({
    mutationFn: (enabled: boolean) =>
      updatePromptCacheSettings({ prompt_cache_auto_refresh: enabled }),
    onSuccess: () => void refetchCache(),
  })

  const switchProvider = useMutation({
    mutationFn: (provider: string) => setWritingProvider(provider),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['status'] })
      void qc.invalidateQueries({ queryKey: ['config', 'models'] })
    },
  })

  useEffect(() => {
    if (params.get('tab') === 'book-files') {
      navigate('/writing?archives=1', { replace: true })
      return
    }
    if (!params.get('tab')) {
      setParams({ tab: 'models' }, { replace: true })
    }
  }, [params, setParams, navigate])

  return (
    <div className="flex max-w-4xl gap-8">
      <nav className="w-[140px] shrink-0 space-y-1">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={cn(
              'w-full rounded-[var(--border-radius-sm)] px-3 py-2 text-left text-[13px] transition-colors',
              tab === item.id
                ? 'border border-[var(--color-border)] bg-[var(--color-background-primary)] font-medium text-[var(--color-primary)]'
                : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-background-secondary)] hover:text-[var(--color-text-secondary)]',
            )}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="min-w-0 flex-1 space-y-4">
        <PageHeader title="设置" />

        {tab === 'taste' ? <TastePanel /> : null}

        {tab === 'prompts' ? <PromptNodesPanel initialNodeId={promptNode} /> : null}

        {tab === 'cost' ? <CostSummaryPanel /> : null}

        {tab === 'models' ? (
          <div className="space-y-4">
            <div className="card-ui space-y-2">
              <p className="text-[13px] font-medium">按节点模型</p>
              {models?.nodes?.map((node) => (
                <div
                  key={node.node_id}
                  className="flex items-center justify-between rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-3 py-2"
                >
                  <div>
                    <p className="text-[13px] font-medium">{node.label}</p>
                    <p className="text-[11px] text-[var(--color-text-tertiary)]">
                      {node.node_id}
                    </p>
                  </div>
                  <p className="text-[11px]">
                    {node.provider} / {node.model}
                  </p>
                </div>
              ))}
              {models?.providers?.length ? (
                <div className="flex flex-wrap gap-2 pt-2">
                  {models.providers.map((p) => (
                    <Button
                      key={p.id}
                      size="sm"
                      variant="outline"
                      onClick={() => switchProvider.mutate(p.id)}
                      disabled={switchProvider.isPending}
                    >
                      写作默认 → {p.name}
                    </Button>
                  ))}
                </div>
              ) : null}
            </div>
            <div className="card-ui space-y-3">
              <p className="text-[13px] font-medium">提示词缓存</p>
              <p className="text-[11px] text-[var(--color-text-tertiary)]">
                {cacheStatus?.writing_provider}/{cacheStatus?.writing_model}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  onClick={() => refreshCache.mutate()}
                  disabled={refreshCache.isPending}
                >
                  立即续命
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    toggleAutoRefresh.mutate(
                      !cacheStatus?.prompt_cache_auto_refresh,
                    )
                  }
                >
                  自动续命：
                  {cacheStatus?.prompt_cache_auto_refresh ? '开' : '关'}
                </Button>
              </div>
            </div>
          </div>
        ) : null}

        {tab === 'profile' ? (
          <div className="space-y-4">
            <StyleExtractPanel />
            <AuthorProfileInherit />
            {profileData?.profile ? (
              <pre className="card-ui max-h-64 overflow-auto text-[11px] text-[var(--color-text-tertiary)]">
                {JSON.stringify(profileData.profile, null, 2).slice(0, 1200)}
              </pre>
            ) : null}
          </div>
        ) : null}

        {tab === 'auth' ? (
          <div className="card-ui space-y-2">
            <p className="text-[13px] font-medium">API 鉴权</p>
            <input
              className="h-[30px] w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-primary)] px-3 text-[13px]"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="X-Novel-Token"
            />
            <Button size="sm" onClick={() => setToken(tokenInput)}>
              保存
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
