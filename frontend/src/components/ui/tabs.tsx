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
    <div className={cn('flex gap-1 border-b border-border', className)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={cn(
            'px-4 py-2 text-sm transition-colors -mb-px border-b-2',
            active === tab.id
              ? 'border-primary text-primary font-medium'
              : 'border-transparent text-muted hover:text-foreground',
          )}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
