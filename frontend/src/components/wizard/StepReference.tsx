import { useMutation } from '@tanstack/react-query'
import { Paperclip } from 'lucide-react'
import { useMemo, useState } from 'react'

import { importDeconstruct, runDeconstruct } from '@/api/endpoints'
import { WizardStepActions } from '@/components/wizard/WizardStepActions'
import { Button } from '@/components/ui/button'
import { useWizardStore } from '@/stores/wizardStore'

type DeconstructPatterns = {
  hook_patterns?: string[]
  structure_notes?: string[]
}

type Props = {
  onNext: () => void
  onBack?: () => void
  deconstructMode?: boolean
}

function patternKey(prefix: string, text: string) {
  return `${prefix}:${text}`
}

export function StepReference({ onNext, onBack, deconstructMode = false }: Props) {
  const referenceExcerpt = useWizardStore((s) => s.referenceExcerpt)
  const setReference = useWizardStore((s) => s.setReference)
  const setDeconstruct = useWizardStore((s) => s.setDeconstruct)
  const [text, setText] = useState(referenceExcerpt)
  const [summary, setSummary] = useState('')
  const [patterns, setPatterns] = useState<DeconstructPatterns | null>(null)
  const [logId, setLogId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const allPatternItems = useMemo(() => {
    const items: Array<{ key: string; label: string; kind: 'hook' | 'structure' }> = []
    for (const row of patterns?.hook_patterns ?? []) {
      const s = String(row).trim()
      if (s) {
        items.push({ key: patternKey('hook', s), label: s, kind: 'hook' })
      }
    }
    for (const row of patterns?.structure_notes ?? []) {
      const s = String(row).trim()
      if (s) {
        items.push({ key: patternKey('structure', s), label: s, kind: 'structure' })
      }
    }
    return items
  }, [patterns])

  const deconstruct = useMutation({
    mutationFn: async () => {
      const r = await runDeconstruct(text.trim(), '开书参考')
      if (!r.ok) {
        throw new Error(r.error ?? '拆文失败')
      }
      return r
    },
    onSuccess: (data) => {
      const body = (data.reply ?? '').trim()
      setSummary(body.slice(0, 800))
      setDeconstruct(body, data.log_id ?? null)
      setLogId(data.log_id ?? null)
      const p = (data.patterns ?? {}) as DeconstructPatterns
      setPatterns(p)
      const keys = new Set<string>()
      for (const row of p.hook_patterns ?? []) {
        const s = String(row).trim()
        if (s) {
          keys.add(patternKey('hook', s))
        }
      }
      for (const row of p.structure_notes ?? []) {
        const s = String(row).trim()
        if (s) {
          keys.add(patternKey('structure', s))
        }
      }
      setSelected(keys)
    },
  })

  const importRules = useMutation({
    mutationFn: async () => {
      if (!logId || selected.size === 0) {
        return
      }
      const hooks: string[] = []
      const structures: string[] = []
      for (const item of allPatternItems) {
        if (!selected.has(item.key)) {
          continue
        }
        if (item.kind === 'hook') {
          hooks.push(item.label)
        } else {
          structures.push(item.label)
        }
      }
      await importDeconstruct(logId, true, hooks, structures)
    },
  })

  const togglePattern = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  const advance = async () => {
    if (logId && selected.size > 0) {
      await importRules.mutateAsync()
    }
    onNext()
  }

  const saveAndNext = () => {
    setReference(text.trim())
    void advance()
  }

  const runDeconstructAndNext = async () => {
    if (!text.trim()) {
      setReference('')
      await advance()
      return
    }
    if (!deconstruct.isSuccess) {
      await deconstruct.mutateAsync()
    }
    setReference(text.trim())
    await advance()
  }

  const skip = () => {
    setReference('')
    void advance()
  }

  const pending = deconstruct.isPending || importRules.isPending

  return (
    <div className="mx-auto max-w-lg space-y-5 px-4 pb-8">
      <div>
        <h2 className="text-[13px] font-medium">写作偏好</h2>
        <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
          上传爆文拆文或继承已有偏好（可跳过）
        </p>
      </div>

      <div className="card-ui">
        <p className="text-center text-[13px] font-medium">有参考爆文吗？</p>
        <p className="mt-1 text-center text-[11px] text-[var(--color-text-tertiary)]">
          粘贴链接或正文，用来提炼写作偏好
        </p>

        <label className="mt-4 flex cursor-pointer flex-col items-center gap-2 rounded-[var(--border-radius-md)] border border-dashed border-[var(--color-border-secondary)] bg-[var(--color-background-secondary)] px-4 py-6">
          <Paperclip className="h-5 w-5 text-[var(--color-text-tertiary)]" />
          <span className="text-[11px] text-[var(--color-text-tertiary)]">
            拖拽或粘贴爆文
          </span>
          <textarea
            className="mt-2 min-h-28 w-full resize-y rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-primary)] p-3 text-[13px] leading-relaxed outline-none"
            placeholder="把参考文本贴在这里…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onClick={(e) => e.stopPropagation()}
          />
        </label>

        {summary ? (
          <div className="ai-note mt-3 text-left">
            <p className="font-medium">拆文摘要</p>
            <p className="mt-1 whitespace-pre-wrap text-[11px]">{summary}</p>
          </div>
        ) : null}

        {allPatternItems.length > 0 ? (
          <div className="mt-3 space-y-2 text-left">
            <p className="text-[11px] font-medium text-[var(--color-text-secondary)]">
              确认要写入口味库的规律（默认全选）
            </p>
            <ul className="max-h-40 space-y-1 overflow-auto">
              {allPatternItems.map((item) => (
                <li key={item.key}>
                  <label className="flex cursor-pointer items-start gap-2 text-[11px]">
                    <input
                      type="checkbox"
                      className="mt-0.5"
                      checked={selected.has(item.key)}
                      onChange={() => togglePattern(item.key)}
                    />
                    <span>
                      <span className="text-[var(--color-text-tertiary)]">
                        {item.kind === 'hook' ? '钩子' : '结构'} ·
                      </span>{' '}
                      {item.label}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <WizardStepActions onBack={onBack}>
          <Button variant="ghost" onClick={skip} disabled={pending}>
            跳过
          </Button>
          {deconstructMode && text.trim() ? (
            <Button
              onClick={() => void runDeconstructAndNext()}
              disabled={pending}
            >
              {pending ? '处理中…' : deconstruct.isSuccess ? '确认并继续' : '拆文并继续'}
            </Button>
          ) : (
            <Button onClick={saveAndNext} disabled={pending}>
              {text.trim() ? '下一步' : '跳过，下一步'}
            </Button>
          )}
        </WizardStepActions>
      </div>

      {deconstruct.error ? (
        <p className="text-center text-[13px] text-[var(--color-danger)]">
          {(deconstruct.error as Error).message}
        </p>
      ) : null}
      {importRules.error ? (
        <p className="text-center text-[13px] text-[var(--color-danger)]">
          {(importRules.error as Error).message}
        </p>
      ) : null}
    </div>
  )
}
