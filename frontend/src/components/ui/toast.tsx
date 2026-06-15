import { X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { useToastStore, type ToastKind } from '@/stores/toastStore'

const kindStyles: Record<ToastKind, string> = {
  success:
    'border-[var(--primary)]/25 bg-[var(--surface)] text-[var(--color-text-secondary)]',
  warning:
    'border-[var(--warning)]/30 bg-[var(--surface)] text-[var(--color-warning-text)]',
  info: 'border-[var(--primary)]/25 bg-[var(--surface)] text-[var(--color-text-secondary)]',
}

export function ToastHost() {
  const toasts = useToastStore((s) => s.toasts)
  const dismiss = useToastStore((s) => s.dismiss)

  if (toasts.length === 0) {
    return null
  }

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            'pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2.5 text-[13px] shadow-lg',
            kindStyles[t.kind],
          )}
          role="status"
        >
          <span className="min-w-0 flex-1 leading-snug">{t.message}</span>
          <button
            type="button"
            className="shrink-0 rounded p-0.5 opacity-60 hover:opacity-100"
            onClick={() => dismiss(t.id)}
            aria-label="关闭"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}
