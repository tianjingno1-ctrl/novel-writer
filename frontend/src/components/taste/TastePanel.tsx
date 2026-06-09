import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  fetchTasteEvents,
  fetchTasteGlobal,
  fetchTasteSummary,
  updateTasteGlobal,
} from '@/api/tasteApi'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'

export function TastePanel() {
  const qc = useQueryClient()
  const { data: global } = useQuery({
    queryKey: ['taste', 'global'],
    queryFn: fetchTasteGlobal,
  })
  const { data: summary } = useQuery({
    queryKey: ['taste', 'summary'],
    queryFn: fetchTasteSummary,
  })
  const { data: events } = useQuery({
    queryKey: ['taste', 'events'],
    queryFn: () => fetchTasteEvents(30),
  })

  const rules = global?.doc?.rules ?? []
  const examples = global?.doc?.examples ?? []
  const [newRule, setNewRule] = useState('')

  const addRule = useMutation({
    mutationFn: async () => {
      const prefs = {
        ...(global?.doc?.preferences ?? {}),
        hook_patterns: [
          ...(((global?.doc?.preferences as { hook_patterns?: string[] })
            ?.hook_patterns) ?? []),
          newRule.trim(),
        ].filter(Boolean),
      }
      return updateTasteGlobal(prefs)
    },
    onSuccess: () => {
      setNewRule('')
      void qc.invalidateQueries({ queryKey: ['taste'] })
    },
  })

  return (
    <div className="space-y-6">
      {summary ? (
        <div className="rounded-lg border border-border p-3 text-xs text-muted">
          <pre>{JSON.stringify(summary, null, 2).slice(0, 600)}</pre>
        </div>
      ) : null}

      <section>
        <h3 className="text-sm font-medium">写作规则</h3>
        <ul className="mt-2 space-y-1 text-sm">
          {rules.map((r) => (
            <li key={r.id ?? r.content} className="text-muted">
              · {r.content}
            </li>
          ))}
          {rules.length === 0 ? (
            <li className="text-muted">暂无规则</li>
          ) : null}
        </ul>
        <div className="mt-3 flex gap-2">
          <Textarea
            className="min-h-16 text-sm"
            placeholder="添加一条偏好（如：章末必须有钩子）"
            value={newRule}
            onChange={(e) => setNewRule(e.target.value)}
          />
        </div>
        <Button
          size="sm"
          className="mt-2"
          disabled={!newRule.trim() || addRule.isPending}
          onClick={() => addRule.mutate()}
        >
          添加
        </Button>
      </section>

      <section>
        <h3 className="text-sm font-medium">正向案例</h3>
        <ul className="mt-2 space-y-2 text-sm">
          {examples.map((ex) => (
            <li
              key={ex.id}
              className="rounded-md border border-border p-2 font-serif text-muted"
            >
              {ex.content}
              {ex.annotation ? (
                <p className="mt-1 font-sans text-xs">{ex.annotation}</p>
              ) : null}
            </li>
          ))}
          {examples.length === 0 ? (
            <li className="text-muted text-xs">审阅通过后会自动沉淀</li>
          ) : null}
        </ul>
      </section>

      <section>
        <h3 className="text-sm font-medium">最近事件</h3>
        <ul className="mt-2 max-h-48 overflow-auto text-xs text-muted">
          {(events?.events ?? []).map((ev) => (
            <li key={ev.id} className="border-b border-border/50 py-1">
              {ev.source} · {ev.outcome || '—'}
              {ev.note ? ` · ${ev.note.slice(0, 40)}` : ''}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
