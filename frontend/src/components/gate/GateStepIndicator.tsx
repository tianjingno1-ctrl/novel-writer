import type { ChapterFlowPhase } from '@/hooks/useChapterFlow'
import { cn } from '@/lib/utils'

const STEPS = ['写作', '预检', '预览', '质量审阅', '亮点', '完成'] as const

function phaseStepIndex(phase: ChapterFlowPhase): number {
  switch (phase) {
    case 'writing':
    case 'regenerating':
      return 0
    case 'running':
    case 'precheck_fail':
      return 1
    case 'preview_cta':
      return 2
    case 'review_gate':
    case 'judgment_fork':
    case 'revise_input':
    case 'revise_preview':
    case 'rules_drawer':
      return 3
    case 'highlights_gate':
    case 'rhythm_gate':
      return 4
    case 'summary_gate':
    case 'chapter_done':
      return 5
    default:
      return 0
  }
}

type Props = {
  phase: ChapterFlowPhase
  className?: string
}

export function GateStepIndicator({ phase, className }: Props) {
  const current = phaseStepIndex(phase)
  const hidden = (phase === 'writing' || phase === 'regenerating') && current === 0

  if (hidden) {
    return null
  }

  return (
    <div
      className={cn(
        'flex h-8 items-center gap-1 border-b border-[var(--color-border-tertiary)] px-3 text-[11px]',
        className,
      )}
    >
      {STEPS.map((label, i) => {
        const done = i < current
        const active = i === current
        return (
          <span key={label} className="flex items-center gap-1">
            {i > 0 ? (
              <span className="text-[var(--color-text-tertiary)]">›</span>
            ) : null}
            <span
              className={cn(
                done && 'text-[var(--color-success)]',
                active && 'font-medium text-[var(--color-text-primary)]',
                !done && !active && 'text-[var(--color-text-tertiary)]',
              )}
            >
              {done ? '✓ ' : active ? '→ ' : ''}
              {label}
            </span>
          </span>
        )
      })}
    </div>
  )
}
