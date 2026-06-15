import type { PrecheckResult } from '@/api/chapterFlow'
import {
  precheckIssueLabel,
  splitPrecheckIssues,
} from '@/lib/precheckIssues'

type Props = {
  result: PrecheckResult
  /** hard：预检失败；soft：审阅门建议；all：全部 */
  mode?: 'all' | 'hard' | 'soft'
}

export function PrecheckIssuesPanel({
  result,
  mode = 'all',
}: Props) {
  const { hard, soft } = splitPrecheckIssues(result)
  const showHard = mode !== 'soft' && hard.length > 0
  const showSoft = mode !== 'hard' && soft.length > 0
  if (!showHard && !showSoft) {
    return null
  }
  return (
    <div className="mt-3 space-y-2">
      {showHard ? (
        <ul className="space-y-1.5 text-[12px]">
          {hard.map((issue, i) => (
            <li
              key={`${issue.code ?? 'hard'}-${i}`}
              className="text-[var(--color-danger)]"
            >
              <span className="font-medium">
                {precheckIssueLabel(issue)}
              </span>
              {issue.message ? (
                <span className="text-[var(--color-text-secondary)]">
                  {' '}
                  — {issue.message}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {showSoft ? (
        <ul className="space-y-1 text-[11px] text-[var(--color-warning-text)]">
          {soft.map((issue, i) => (
            <li key={`${issue.code ?? 'soft'}-${i}`}>
              {precheckIssueLabel(issue)}：{issue.message}
            </li>
          ))}
        </ul>
      ) : null}
      {result.chapter_role ? (
        <p className="text-[10px] text-[var(--color-text-tertiary)]">
          叙事角色：{result.chapter_role}
        </p>
      ) : null}
    </div>
  )
}
