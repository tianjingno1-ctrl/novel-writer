import type { WizardStep } from '@/stores/wizardStore'
import { cn } from '@/lib/utils'
import { WIZARD_STEP_ORDER, wizardStepIndex } from '@/components/wizard/wizardPersist'

const STEP_LABELS: Record<WizardStep, string> = {
  basic: '基本',
  reference: '偏好',
  direction: '方向',
  plan: '规划',
  criteria: '标准',
}

type Props = {
  current: WizardStep
  minStep?: WizardStep
  onStepClick?: (step: WizardStep) => void
}

export function WizardProgress({ current, minStep = 'basic', onStepClick }: Props) {
  const idx = wizardStepIndex(current)
  const minIdx = wizardStepIndex(minStep)

  return (
    <div className="flex items-center justify-center gap-1 py-6">
      {WIZARD_STEP_ORDER.map((stepId, i) => {
        const step = { id: stepId, label: STEP_LABELS[stepId] }
        const clickable =
          Boolean(onStepClick) && i <= idx && i >= minIdx && i !== idx
        const dot = (
          <>
            <div
              className={cn(
                'h-3 w-3 rounded-full border transition-colors',
                i < idx &&
                  'border-[var(--color-primary)] bg-[var(--color-primary)]',
                i === idx &&
                  'border-[var(--color-primary)] bg-[var(--color-primary)] ring-4 ring-[var(--color-border)]',
                i > idx &&
                  'border-[var(--color-border-secondary)] bg-transparent',
              )}
            />
            <span
              className={cn(
                'text-[10px]',
                i === idx
                  ? 'font-medium text-[var(--color-text-primary)]'
                  : 'text-[var(--color-text-tertiary)]',
                clickable && 'group-hover:text-[var(--color-text-secondary)]',
              )}
            >
              {step.label}
            </span>
          </>
        )

        return (
          <div key={step.id} className="flex items-center gap-1">
            <div className="flex flex-col items-center gap-1">
              {clickable ? (
                <button
                  type="button"
                  className="group flex flex-col items-center gap-1 rounded-[var(--border-radius-sm)] px-1 py-0.5 transition-colors hover:bg-[var(--color-background-secondary)]"
                  onClick={() => onStepClick?.(step.id)}
                  title={`返回：${step.label}`}
                >
                  {dot}
                </button>
              ) : (
                dot
              )}
            </div>
            {i < WIZARD_STEP_ORDER.length - 1 ? (
              <div
                className={cn(
                  'mb-4 h-px w-8 sm:w-12',
                  i < idx
                    ? 'bg-[var(--color-primary)]'
                    : 'bg-[var(--color-border)]',
                )}
              />
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
