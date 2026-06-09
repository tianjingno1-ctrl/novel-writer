import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getToken, setToken } from '@/api/client'
import {
  fetchModelsConfig,
  fetchPromptCacheStatus,
  refreshPromptCache,
  setWritingProvider,
  updatePromptCacheSettings,
} from '@/api/endpoints'
import { TastePanel } from '@/components/taste/TastePanel'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs } from '@/components/ui/tabs'

const TAB_ITEMS = [
  { id: 'models', label: '模型' },
  { id: 'taste', label: '口味库' },
  { id: 'auth', label: '鉴权' },
] as const

export function SettingsPage() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<string>('models')
  const [tokenInput, setTokenInput] = useState(getToken())

  const { data: models } = useQuery({
    queryKey: ['config', 'models'],
    queryFn: fetchModelsConfig,
  })

  const { data: cacheStatus, refetch: refetchCache } = useQuery({
    queryKey: ['tools', 'prompt-cache'],
    queryFn: fetchPromptCacheStatus,
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

  return (
    <div className="mx-auto max-w-3xl space-y-4 px-4 pb-24">
      <h1 className="pt-2 text-xl font-semibold">设置</h1>
      <Tabs tabs={[...TAB_ITEMS]} active={tab} onChange={setTab} />

      {tab === 'models' ? (
        <div className="space-y-4 pt-2">
          <Card>
            <CardHeader>
              <CardTitle>按节点模型</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {models?.nodes?.map((node) => (
                <div
                  key={node.node_id}
                  className="flex items-center justify-between rounded-md border border-border px-3 py-2"
                >
                  <div>
                    <p className="font-medium">{node.label}</p>
                    <p className="text-xs text-muted">{node.node_id}</p>
                  </div>
                  <p className="text-xs">
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
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Prompt Cache</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <p className="text-muted">
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
            </CardContent>
          </Card>
        </div>
      ) : null}

      {tab === 'taste' ? (
        <div className="pt-2">
          <TastePanel />
        </div>
      ) : null}

      {tab === 'auth' ? (
        <Card className="mt-2">
          <CardHeader>
            <CardTitle>API 鉴权</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="X-Novel-Token"
            />
            <Button size="sm" onClick={() => setToken(tokenInput)}>
              保存
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
