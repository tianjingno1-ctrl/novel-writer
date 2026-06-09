import { useMutation } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'

import { applyDirection, prefillDirection } from '@/api/endpoints'
import { Button } from '@/components/ui/button'
import { useWizardStore } from '@/stores/wizardStore'
import type { DirectionOption } from '@/types/api'

type Props = {
  onNext: () => void
}

function optionTitle(opt: DirectionOption) {
  return (
    opt.title ||
    opt.tone ||
    opt.logline?.slice(0, 12) ||
    `方案 ${opt.id ?? ''}`
  )
}

export function StepDirection({ onNext }: Props) {
  const referenceExcerpt = useWizardStore((s) => s.referenceExcerpt)
  const seed = useWizardStore((s) => s.seed)
  const setSeed = useWizardStore((s) => s.setSeed)
  const chapterCount = useWizardStore((s) => s.chapterCount)
  const options = useWizardStore((s) => s.directionOptions)
  const logId = useWizardStore((s) => s.directionLogId)
  const setDirectionOptions = useWizardStore((s) => s.setDirectionOptions)
  const selectDirection = useWizardStore((s) => s.selectDirection)
  const setStep = useWizardStore((s) => s.setStep)

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
      setStep('plan')
      onNext()
    },
  })

  const hasOptions = options.length > 0

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4">
      <div className="text-center">
        <h2 className="text-xl font-semibold">为你生成几个方向</h2>
        <p className="mt-2 text-sm text-muted">选一个感觉对的，不用想太多</p>
      </div>

      <div className="mx-auto max-w-md">
        <label className="text-xs text-muted">补充想法（可选）</label>
        <textarea
          className="mt-1 min-h-20 w-full rounded-md border border-border bg-surface p-3 text-sm"
          placeholder="例如：都市甜宠、女主独立、章末强钩子"
          value={seed}
          onChange={(e) => setSeed(e.target.value)}
        />
      </div>

      {!hasOptions ? (
        <div className="flex justify-center">
          <Button
            size="lg"
            onClick={() => load.mutate()}
            disabled={load.isPending}
          >
            {load.isPending ? '正在想方向…' : '生成方向'}
          </Button>
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {options.map((opt, i) => (
              <button
                key={opt.id ?? i}
                type="button"
                className="group rounded-xl border border-border bg-surface p-5 text-left shadow-sm transition-all hover:border-primary/50 hover:shadow-md"
                onClick={() => pick.mutate(opt)}
                disabled={pick.isPending}
              >
                <p className="text-lg font-medium text-foreground">
                  {optionTitle(opt)}
                </p>
                {opt.logline ? (
                  <p className="mt-2 text-sm text-muted leading-relaxed">
                    {opt.logline}
                  </p>
                ) : null}
                {opt.hook || opt.sell_point ? (
                  <p className="mt-3 text-xs text-muted">
                    {[opt.sell_point, opt.hook].filter(Boolean).join(' · ')}
                  </p>
                ) : null}
                <span className="mt-4 inline-block text-sm font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
                  选这个 →
                </span>
              </button>
            ))}
          </div>
          <div className="flex justify-center">
            <Button
              variant="outline"
              onClick={() => load.mutate()}
              disabled={load.isPending}
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              换一批方向
            </Button>
          </div>
        </>
      )}

      {load.error ? (
        <p className="text-center text-sm text-danger">
          {(load.error as Error).message}
        </p>
      ) : null}
      {pick.error ? (
        <p className="text-center text-sm text-danger">
          {(pick.error as Error).message}
        </p>
      ) : null}
    </div>
  )
}
