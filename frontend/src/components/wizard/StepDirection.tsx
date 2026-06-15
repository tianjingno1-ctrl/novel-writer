import { useMutation } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { applyDirection, prefillDirection } from '@/api/endpoints'
import { updatePlanMeta } from '@/api/productApi'
import { WizardStepActions } from '@/components/wizard/WizardStepActions'
import { useWizardWordBudget } from '@/hooks/useWizardWordBudget'
import { Button } from '@/components/ui/button'
import { useWizardStore } from '@/stores/wizardStore'
import { cn } from '@/lib/utils'
import type { DirectionOption } from '@/types/api'

type Props = {
  onNext: () => void
  onBack?: () => void
}

function optionTitle(opt: DirectionOption) {
  return (
    opt.title ||
    opt.tone ||
    opt.logline?.slice(0, 12) ||
    `方案 ${opt.id ?? ''}`
  )
}

function loglineFromText(text: string): string {
  const trimmed = text.trim()
  if (!trimmed) return ''
  const firstLine = trimmed.split('\n').find((line) => line.trim())?.trim()
  return (firstLine ?? trimmed).slice(0, 4000)
}

export function StepDirection({ onNext, onBack }: Props) {
  const referenceExcerpt = useWizardStore((s) => s.referenceExcerpt)
  const seed = useWizardStore((s) => s.seed)
  const setSeed = useWizardStore((s) => s.setSeed)
  const { chapterCount } = useWizardWordBudget()
  const options = useWizardStore((s) => s.directionOptions)
  const logId = useWizardStore((s) => s.directionLogId)
  const setDirectionOptions = useWizardStore((s) => s.setDirectionOptions)
  const selectDirection = useWizardStore((s) => s.selectDirection)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const [manualMode, setManualMode] = useState(false)
  const [manualDirection, setManualDirection] = useState('')

  const load = useMutation({
    mutationFn: () =>
      prefillDirection({
        reference_excerpt: referenceExcerpt,
        seed: seed.trim(),
        chapter_count: chapterCount,
      }),
    onSuccess: (data) => {
      setDirectionOptions(data.options ?? [], data.log_id ?? null)
    },
  })

  const pick = useMutation({
    mutationFn: (opt: DirectionOption) =>
      applyDirection(opt as Record<string, unknown>, logId ?? undefined),
    onSuccess: (_data, opt) => {
      selectDirection(opt)
      onNext()
    },
  })

  const confirmManual = useMutation({
    mutationFn: async () => {
      const text = manualDirection.trim()
      if (!text) {
        throw new Error('请写下你的方向')
      }
      const logline = loglineFromText(text)
      return updatePlanMeta({ logline, direction_note: text })
    },
    onSuccess: () => {
      const text = manualDirection.trim()
      const logline = loglineFromText(text)
      selectDirection({
        logline,
        title: logline.slice(0, 12) || '我的方向',
      })
      onNext()
    },
  })

  const hasOptions = options.length > 0

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-4 pb-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-[13px] font-medium">
            {manualMode ? '自己写方向' : 'AI 预填方向'}
          </h2>
          <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
            {manualMode
              ? '直接填写 logline 或大纲，跳过方案选择'
              : '选一个感觉对的方向，或换一批'}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setManualMode((v) => !v)}>
          {manualMode ? 'AI 生成方案' : '自己写方向'}
        </Button>
      </div>

      {manualMode ? (
        <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
          <textarea
            className="min-h-40 w-full rounded-[var(--border-radius-lg)] border-[0.5px] border-[var(--color-border-secondary)] p-3 text-[13px] outline-none"
            placeholder="写下你的方向、logline 或大纲"
            value={manualDirection}
            onChange={(e) => setManualDirection(e.target.value)}
          />
          <div className="flex items-end">
            <Button
              className="w-full"
              onClick={() => confirmManual.mutate()}
              disabled={confirmManual.isPending || !manualDirection.trim()}
            >
              {confirmManual.isPending ? '保存中…' : '确认方向'}
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
          <div className="space-y-3">
            {!hasOptions ? (
              <div className="flex justify-center py-8">
                <Button onClick={() => load.mutate()} disabled={load.isPending}>
                  {load.isPending ? '正在想方向…' : '生成 3 个方向'}
                </Button>
              </div>
            ) : (
              <>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
                  {options.map((opt, i) => (
                    <button
                      key={opt.id ?? i}
                      type="button"
                      className={cn(
                        'card-ui text-left transition-colors hover:border-[var(--color-primary)]',
                        selectedId === i &&
                          'border-[var(--color-primary)] ring-1 ring-[var(--color-primary)]/30',
                      )}
                      onClick={() => setSelectedId(i)}
                      disabled={pick.isPending}
                    >
                      <p className="text-[13px] font-medium">{optionTitle(opt)}</p>
                      {opt.logline ? (
                        <p className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-tertiary)]">
                          {opt.logline}
                        </p>
                      ) : null}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => load.mutate()}
                    disabled={load.isPending}
                  >
                    <RefreshCw className="mr-1 h-3.5 w-3.5" />
                    换一批
                  </Button>
                  {selectedId != null && options[selectedId] ? (
                    <Button
                      size="sm"
                      onClick={() => pick.mutate(options[selectedId]!)}
                      disabled={pick.isPending}
                    >
                      选中并继续
                    </Button>
                  ) : null}
                </div>
              </>
            )}
          </div>
          <div className="card-ui">
            <label className="text-[11px] text-[var(--color-text-tertiary)]">
              补充想法（可选）
            </label>
            <textarea
              className="mt-2 min-h-32 w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] p-3 text-[13px] outline-none"
              placeholder="例如：都市甜宠、女主独立、章末强钩子"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
            />
          </div>
        </div>
      )}

      {load.error ? (
        <p className="text-center text-[13px] text-[var(--color-danger)]">
          {(load.error as Error).message}
        </p>
      ) : null}
      {pick.error || confirmManual.error ? (
        <p className="text-center text-[13px] text-[var(--color-danger)]">
          {((pick.error ?? confirmManual.error) as Error).message}
        </p>
      ) : null}

      {onBack ? (
        <WizardStepActions onBack={onBack} className="pt-2" />
      ) : null}
    </div>
  )
}
