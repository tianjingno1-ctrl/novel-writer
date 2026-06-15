import { cn } from '@/lib/utils'

type Tab = { id: string; label: string }

type Props = {
  tabs: Tab[]
  active: string
  onChange: (id: string) => void
  className?: string
}

export function Tabs({ tabs, active, onChange, className }: Props) {
  return (
    <div
      className={cn(
        'flex gap-1 border-b border-[var(--color-border-tertiary)]',
        className,
      )}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={cn(
            'px-3 py-2 text-[13px] transition-colors -mb-px border-b-2',
            active === tab.id
              ? 'border-[var(--color-primary)] font-medium text-[var(--color-primary)]'
              : 'border-transparent text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]',
          )}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
