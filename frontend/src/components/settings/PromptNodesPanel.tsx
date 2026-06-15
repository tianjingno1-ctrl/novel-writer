import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import {
  fetchPromptNode,
  fetchPromptNodes,
  PROMPT_CATEGORY_LABEL,
  PROMPT_SOURCE_LABEL,
  updatePromptNodeOverride,
  type PromptNodeSummary,
} from '@/api/promptsApi'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { toast } from '@/stores/toastStore'

type Props = {
  initialNodeId?: string
}

function groupByCategory(nodes: PromptNodeSummary[]) {
  const map = new Map<string, PromptNodeSummary[]>()
  for (const node of nodes) {
    const cat = node.category || 'other'
    const list = map.get(cat) ?? []
    list.push(node)
    map.set(cat, list)
  }
  return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
}

export function PromptNodesPanel({ initialNodeId = '' }: Props) {
  const qc = useQueryClient()
  const { data: listData, isLoading: listLoading } = useQuery({
    queryKey: ['prompts', 'nodes'],
    queryFn: fetchPromptNodes,
  })
  const nodes = listData?.nodes ?? []
  const [selectedId, setSelectedId] = useState(initialNodeId || nodes[0]?.node_id || '')
  const [appendDraft, setAppendDraft] = useState('')

  useEffect(() => {
    if (initialNodeId) {
      setSelectedId(initialNodeId)
    } else if (!selectedId && nodes[0]?.node_id) {
      setSelectedId(nodes[0].node_id)
    }
  }, [initialNodeId, nodes, selectedId])

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['prompts', 'node', selectedId],
    queryFn: () => fetchPromptNode(selectedId),
    enabled: Boolean(selectedId),
  })

  useEffect(() => {
    setAppendDraft(String(detail?.override?.append ?? ''))
  }, [detail?.node_id, detail?.override?.append])

  const grouped = useMemo(() => groupByCategory(nodes), [nodes])

  const saveAppend = useMutation({
    mutationFn: () =>
      updatePromptNodeOverride(selectedId, {
        append: appendDraft.trim(),
      }),
    onSuccess: () => {
      toast('success', '本书 Prompt 覆盖已保存')
      void qc.invalidateQueries({ queryKey: ['prompts'] })
    },
  })

  const clearOverride = useMutation({
    mutationFn: () => updatePromptNodeOverride(selectedId, { clear: true }),
    onSuccess: () => {
      setAppendDraft('')
      toast('success', '已清除本书覆盖')
      void qc.invalidateQueries({ queryKey: ['prompts'] })
    },
  })

  const hasOverride = Boolean(
    detail?.override &&
      (detail.override.system || detail.override.append || detail.override.prepend),
  )

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-[var(--color-text-tertiary)]">
        查看各流程节点的生效 Prompt；「本书追加」写入{' '}
        <code className="text-[10px]">prompt_overrides.yaml</code>，不影响全局模板。
      </p>

      <div className="flex min-h-[420px] gap-4">
        <div className="w-[200px] shrink-0 space-y-3 overflow-auto">
          {listLoading ? (
            <p className="text-[11px] text-[var(--color-text-tertiary)]">加载节点…</p>
          ) : null}
          {grouped.map(([category, items]) => (
            <div key={category}>
              <p className="text-[10px] font-medium uppercase tracking-wide text-[var(--color-text-tertiary)]">
                {PROMPT_CATEGORY_LABEL[category] ?? category}
              </p>
              <ul className="mt-1 space-y-0.5">
                {items.map((node) => (
                  <li key={node.node_id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(node.node_id)}
                      className={cn(
                        'w-full rounded-[var(--border-radius-md)] px-2 py-1.5 text-left text-[12px]',
                        selectedId === node.node_id
                          ? 'bg-[var(--color-background-secondary)] font-medium'
                          : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-background-secondary)]/60',
                      )}
                    >
                      <span className="block truncate">{node.label}</span>
                      {node.has_override ? (
                        <span className="badge-soft mt-0.5 inline-block text-[9px]">
                          已覆盖
                        </span>
                      ) : null}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="min-w-0 flex-1 space-y-3">
          {!selectedId ? (
            <p className="text-[13px] text-[var(--color-text-tertiary)]">请选择节点</p>
          ) : detailLoading ? (
            <div className="flex items-center gap-2 text-[13px] text-[var(--color-text-tertiary)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              加载 Prompt…
            </div>
          ) : detail?.ok === false ? (
            <p className="text-[13px] text-[var(--color-danger)]">{detail.error}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-[13px] font-medium">{selectedId}</h3>
                {detail?.prompt_source ? (
                  <span className="badge-soft text-[10px]">
                    {PROMPT_SOURCE_LABEL[detail.prompt_source] ?? detail.prompt_source}
                  </span>
                ) : null}
                {detail?.profile_id ? (
                  <span className="text-[10px] text-[var(--color-text-tertiary)]">
                    profile: {detail.profile_id}
                  </span>
                ) : null}
                {detail?.prompt_hash ? (
                  <span className="text-[10px] text-[var(--color-text-tertiary)]">
                    #{detail.prompt_hash}
                  </span>
                ) : null}
              </div>

              <div>
                <p className="text-[11px] font-medium text-[var(--color-text-tertiary)]">
                  生效 Prompt（只读）
                </p>
                <pre className="mt-1 max-h-64 overflow-auto rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-secondary)] p-3 text-[11px] leading-relaxed whitespace-pre-wrap">
                  {detail?.system?.trim() || '（空）'}
                </pre>
              </div>

              {detail?.override?.prepend ? (
                <div className="text-[11px] text-[var(--color-text-tertiary)]">
                  <span className="font-medium">前置覆盖：</span>
                  {detail.override.prepend.slice(0, 200)}
                </div>
              ) : null}

              <div>
                <p className="text-[11px] font-medium text-[var(--color-text-tertiary)]">
                  本书追加（override.append）
                </p>
                <Textarea
                  className="mt-1 min-h-20 text-[12px]"
                  value={appendDraft}
                  onChange={(e) => setAppendDraft(e.target.value)}
                  placeholder="追加到全局 Prompt 末尾，例如：减少总结性旁白"
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    disabled={saveAppend.isPending || !selectedId}
                    onClick={() => saveAppend.mutate()}
                  >
                    {saveAppend.isPending ? '保存中…' : '保存追加'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!hasOverride || clearOverride.isPending}
                    onClick={() => clearOverride.mutate()}
                  >
                    清除本书覆盖
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
