import { useMutation } from '@tanstack/react-query'
import { Paperclip } from 'lucide-react'
import { useState } from 'react'

import { importDeconstruct, runDeconstruct } from '@/api/endpoints'
import { Button } from '@/components/ui/button'
import { useWizardStore } from '@/stores/wizardStore'

type Props = {
  onNext: () => void
  deconstructMode?: boolean
}

export function StepReference({ onNext, deconstructMode = false }: Props) {
  const referenceExcerpt = useWizardStore((s) => s.referenceExcerpt)
  const setReference = useWizardStore((s) => s.setReference)
  const setDeconstruct = useWizardStore((s) => s.setDeconstruct)
  const [text, setText] = useState(referenceExcerpt)
  const [summary, setSummary] = useState('')

  const deconstruct = useMutation({
    mutationFn: async () => {
      const r = await runDeconstruct(text.trim(), '开书参考')
      if (!r.ok) {
        throw new Error(r.error ?? '拆文失败')
      }
      if (r.log_id) {
        await importDeconstruct(r.log_id, true)
      }
      return r
    },
    onSuccess: (data) => {
      const body = (data.reply ?? '').trim()
      setSummary(body.slice(0, 800))
      setDeconstruct(body, data.log_id ?? null)
    },
  })

  const saveAndNext = () => {
    setReference(text.trim())
    onNext()
  }

  const runDeconstructAndNext = async () => {
    if (!text.trim()) {
      setReference('')
      onNext()
      return
    }
    await deconstruct.mutateAsync()
    setReference(text.trim())
    onNext()
  }

  const skip = () => {
    setReference('')
    onNext()
  }

  return (
    <div className="mx-auto max-w-lg space-y-6 px-4">
      <div className="text-center">
        <h2 className="text-xl font-semibold text-foreground">开始一本新书</h2>
        <p className="mt-2 text-sm text-muted">每次只问一件事，慢慢来</p>
      </div>

      <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <p className="text-center text-base font-medium">你有参考的爆文吗？</p>
        <p className="mt-1 text-center text-sm text-muted">
          粘贴链接或正文，我们会用来找方向（可跳过）
        </p>

        <label className="mt-5 flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-accent/60 px-4 py-8 transition-colors hover:border-primary/40">
          <Paperclip className="h-6 w-6 text-muted" />
          <span className="text-sm text-muted">粘贴爆文链接或正文</span>
          <textarea
            className="mt-2 min-h-32 w-full resize-y rounded-md border border-border bg-surface p-3 text-sm leading-relaxed"
            placeholder="把参考文本贴在这里…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onClick={(e) => e.stopPropagation()}
          />
        </label>

        {summary ? (
          <div className="mt-4 rounded-lg bg-accent/40 p-3 text-left text-xs text-muted leading-relaxed">
            <p className="font-medium text-foreground">拆文摘要</p>
            <p className="mt-1 whitespace-pre-wrap">{summary}</p>
          </div>
        ) : null}

        <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-between">
          <Button variant="ghost" className="text-muted" onClick={skip}>
            没有，跳过 →
          </Button>
          {deconstructMode && text.trim() ? (
            <Button
              onClick={() => void runDeconstructAndNext()}
              disabled={deconstruct.isPending}
            >
              {deconstruct.isPending ? '拆文中…' : '拆文并继续 →'}
            </Button>
          ) : (
            <Button onClick={saveAndNext}>
              {text.trim() ? '下一步' : '跳过，下一步 →'}
            </Button>
          )}
        </div>
      </div>

      {deconstruct.error ? (
        <p className="text-center text-sm text-danger">
          {(deconstruct.error as Error).message}
        </p>
      ) : null}
    </div>
  )
}
