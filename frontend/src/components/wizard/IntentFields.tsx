import {
  flattenIntentFinalForEdit,
  getStructuredIntentFields,
  intentFinalText,
  type PlanChapterRow,
} from '@/lib/chapterRoles'

type Props = {
  ch: PlanChapterRow
  onChange: (final: string | Record<string, string>) => void
}

function objectFinal(ch: PlanChapterRow): Record<string, string> {
  return flattenIntentFinalForEdit(ch.role, ch.intent?.final)
}

export function IntentFields({ ch, onChange }: Props) {
  const role = ch.role ?? ''
  const fields = getStructuredIntentFields(role)
  if (!fields) {
    return (
      <textarea
        className="min-h-[56px] w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-2 py-1 text-[11px] outline-none"
        value={intentFinalText(ch)}
        placeholder="叙事意图（确认）"
        onChange={(e) => onChange(e.target.value)}
      />
    )
  }

  const values = objectFinal(ch)
  return (
    <div className="space-y-2">
      {fields.map((field) => (
        <label key={field.key} className="block space-y-0.5">
          <span className="text-[10px] text-[var(--color-text-tertiary)]">
            {field.label}
          </span>
          <input
            className="w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-2 py-1 text-[11px] outline-none"
            value={values[field.key] ?? ''}
            placeholder={field.placeholder}
            onChange={(e) =>
              onChange({ ...values, [field.key]: e.target.value })
            }
          />
        </label>
      ))}
    </div>
  )
}
