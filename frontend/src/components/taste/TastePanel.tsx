import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookMarked, Trash2 } from 'lucide-react'
import { useState } from 'react'

import {
  deleteTasteRule,
  fetchTasteBook,
  fetchTasteEvents,
  fetchTasteGlobal,
  localizeTasteRule,
  updateTasteGlobal,
  type TasteRule,
} from '@/api/tasteApi'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export function TastePanel() {
  const qc = useQueryClient()
  const { data: globalData } = useQuery({
    queryKey: ['taste', 'global'],
    queryFn: fetchTasteGlobal,
  })
  const { data: bookData } = useQuery({
    queryKey: ['taste', 'book'],
    queryFn: fetchTasteBook,
  })
  const { data: events } = useQuery({
    queryKey: ['taste', 'events'],
    queryFn: () => fetchTasteEvents(30),
  })

  const tasteDoc = globalData?.global
  const rules = tasteDoc?.rules ?? []
  const examples = tasteDoc?.examples ?? []
  const activeBookId = bookData?.book_id ?? ''
  const bookOverrides = (bookData?.taste as { overrides?: { append_rules?: TasteRule[] } } | undefined)
    ?.overrides
  const bookRules = bookOverrides?.append_rules ?? []
  const [newRule, setNewRule] = useState('')
  const [pendingRuleId, setPendingRuleId] = useState<string | null>(null)

  const invalidateTaste = () => {
    void qc.invalidateQueries({ queryKey: ['taste'] })
  }

  const addRule = useMutation({
    mutationFn: async () => {
      const prefs = {
        ...(tasteDoc?.preferences ?? {}),
        hook_patterns: [
          ...(((tasteDoc?.preferences as { hook_patterns?: string[] })
            ?.hook_patterns) ?? []),
          newRule.trim(),
        ].filter(Boolean),
      }
      return updateTasteGlobal(prefs)
    },
    onSuccess: () => {
      setNewRule('')
      invalidateTaste()
    },
  })

  const removeRule = useMutation({
    mutationFn: (ruleId: string) => deleteTasteRule(ruleId),
    onMutate: (ruleId) => setPendingRuleId(ruleId),
    onSettled: () => setPendingRuleId(null),
    onSuccess: invalidateTaste,
  })

  const localizeRule = useMutation({
    mutationFn: (ruleId: string) => localizeTasteRule(ruleId),
    onMutate: (ruleId) => setPendingRuleId(ruleId),
    onSettled: () => setPendingRuleId(null),
    onSuccess: invalidateTaste,
  })

  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-[13px] font-medium">写作规则</h3>
        {!activeBookId ? (
          <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
            未选中书籍时无法使用「仅本书」
          </p>
        ) : null}
        <ul className="mt-2 space-y-2">
          {rules.map((r) => {
            const ruleId = r.id ?? r.content ?? ''
            const busy = pendingRuleId === ruleId
            const isHard = (r.weight ?? 'soft') === 'hard'
            return (
              <li
                key={ruleId}
                className="flex items-center gap-2 rounded-[var(--border-radius-md)] py-1"
              >
                <span className="min-w-0 flex-1 text-[13px]">{r.content}</span>
                <span className={cn('shrink-0', isHard ? 'badge-hard' : 'badge-soft')}>
                  {isHard ? '必须' : '建议'}
                </span>
                <button
                  type="button"
                  className="rounded p-1 text-[var(--color-text-tertiary)] hover:bg-[var(--color-background-secondary)] disabled:opacity-40"
                  title="↓ 仅本书"
                  disabled={!ruleId || !activeBookId || busy}
                  onClick={() => ruleId && localizeRule.mutate(ruleId)}
                >
                  <BookMarked className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  className="rounded p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] disabled:opacity-40"
                  title="删除"
                  disabled={!ruleId || busy}
                  onClick={() => ruleId && removeRule.mutate(ruleId)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            )
          })}
          {rules.length === 0 ? (
            <li className="text-[13px] text-[var(--color-text-tertiary)]">
              暂无规则
            </li>
          ) : null}
        </ul>
        <Textarea
          className="mt-3 min-h-16 text-[13px]"
          placeholder="添加一条偏好（如：章末必须有钩子）"
          value={newRule}
          onChange={(e) => setNewRule(e.target.value)}
        />
        <Button
          size="sm"
          className="mt-2"
          disabled={!newRule.trim() || addRule.isPending}
          onClick={() => addRule.mutate()}
        >
          添加
        </Button>
      </section>

      {activeBookId ? (
        <section>
          <h3 className="text-[13px] font-medium">本书规则</h3>
          <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
            从全局「仅本书」下沉或 L5a 等写入；优先于全局规则
          </p>
          <ul className="mt-2 space-y-2">
            {bookRules.map((r) => {
              const ruleId = r.id ?? r.content ?? ''
              const isHard = (r.weight ?? 'soft') === 'hard'
              return (
                <li
                  key={`book-${ruleId}`}
                  className="flex items-center gap-2 rounded-[var(--border-radius-md)] py-1"
                >
                  <span className="min-w-0 flex-1 text-[13px]">{r.content}</span>
                  <span className="badge-soft shrink-0">本书</span>
                  <span className={cn('shrink-0', isHard ? 'badge-hard' : 'badge-soft')}>
                    {isHard ? '必须' : '建议'}
                  </span>
                </li>
              )
            })}
            {bookRules.length === 0 ? (
              <li className="text-[13px] text-[var(--color-text-tertiary)]">
                暂无本书专属规则
              </li>
            ) : null}
          </ul>
        </section>
      ) : null}

      <section>
        <h3 className="text-[13px] font-medium">正向案例</h3>
        <ul className="mt-2 space-y-2">
          {examples.map((ex) => (
            <li
              key={ex.id}
              className="card-ui font-serif text-[13px] text-[var(--color-text-secondary)]"
            >
              {(ex as { text?: string }).text ?? ex.content}
              {ex.annotation ? (
                <p className="mt-1 font-sans text-[11px] text-[var(--color-text-tertiary)]">
                  来自：{ex.annotation}
                </p>
              ) : null}
            </li>
          ))}
          {examples.length === 0 ? (
            <li className="text-[11px] text-[var(--color-text-tertiary)]">
              审阅通过后会自动沉淀
            </li>
          ) : null}
        </ul>
      </section>

      <section>
        <h3 className="text-[13px] font-medium">最近事件</h3>
        <ul className="mt-2 max-h-48 overflow-auto text-[11px] text-[var(--color-text-tertiary)]">
          {(events?.events ?? []).map((ev) => (
            <li
              key={ev.id}
              className="border-b border-[var(--color-border-tertiary)] py-1"
            >
              {ev.source} · {ev.outcome || '—'}
              {ev.note ? ` · ${ev.note.slice(0, 40)}` : ''}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
