import type { WizardStep } from '@/stores/wizardStore'
import { cn } from '@/lib/utils'

const STEPS: { id: WizardStep; label: string }[] = [
  { id: 'reference', label: '参考' },
  { id: 'direction', label: '方向' },
  { id: 'plan', label: '规划' },
  { id: 'criteria', label: '标准' },
]

type Props = {
  current: WizardStep
}

export function WizardProgress({ current }: Props) {
  const idx = STEPS.findIndex((s) => s.id === current)

  return (
    <div className="flex items-center justify-center gap-2 py-6">
      {STEPS.map((step, i) => (
        <div key={step.id} className="flex items-center gap-2">
          <div className="flex flex-col items-center gap-1">
            <div
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium transition-colors',
                i < idx && 'bg-primary text-primary-foreground',
                i === idx && 'bg-primary text-primary-foreground ring-4 ring-primary/20',
                i > idx && 'border border-border bg-surface text-muted',
              )}
            >
              {i < idx ? '✓' : i + 1}
            </div>
            <span
              className={cn(
                'text-xs',
                i === idx ? 'text-foreground font-medium' : 'text-muted',
              )}
            >
              {step.label}
            </span>
          </div>
          {i < STEPS.length - 1 ? (
            <div
              className={cn(
                'mb-5 h-px w-12 sm:w-20',
                i < idx ? 'bg-primary' : 'bg-border',
              )}
            />
          ) : null}
        </div>
      ))}
    </div>
  )
}
