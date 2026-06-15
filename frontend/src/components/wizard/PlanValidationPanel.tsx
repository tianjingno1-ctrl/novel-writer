import {
  formatPlanIssueLine,
  type PlanValidationIssue,
} from '@/lib/planValidation'

type Props = {
  errors?: PlanValidationIssue[]
  warnings?: PlanValidationIssue[]
}

export function PlanValidationPanel({ errors = [], warnings = [] }: Props) {
  if (!errors.length && !warnings.length) {
    return null
  }
  return (
    <div className="space-y-3">
      {errors.length > 0 ? (
        <div className="rounded-[var(--border-radius-md)] border border-[var(--color-danger)]/30 bg-[var(--color-danger-bg)] px-3 py-2">
          <p className="text-[11px] font-medium text-[var(--color-danger)]">
            须修正后才能保存（{errors.length}）
          </p>
          <ul className="mt-1 space-y-1 text-[11px] text-[var(--color-danger)]">
            {errors.map((issue, i) => (
              <li key={`${issue.code ?? 'err'}-${issue.chapter_num ?? i}`}>
                {formatPlanIssueLine(issue)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {warnings.length > 0 ? (
        <div className="rounded-[var(--border-radius-md)] border border-[var(--color-warning)]/30 bg-[var(--color-warning-bg)] px-3 py-2">
          <p className="text-[11px] font-medium text-[var(--color-warning-text)]">
            规划建议（可继续，{warnings.length}）
          </p>
          <ul className="mt-1 space-y-1 text-[11px] text-[var(--color-warning-text)]">
            {warnings.map((issue, i) => (
              <li key={`${issue.code ?? 'warn'}-${issue.chapter_num ?? i}`}>
                {formatPlanIssueLine(issue)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
