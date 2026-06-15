import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type Props = {
  open: boolean
  title: string
  message: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  pending?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = '确认',
  cancelLabel = '取消',
  danger = false,
  pending = false,
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-50 bg-[var(--color-overlay)]"
        aria-label="关闭"
        onClick={pending ? undefined : onCancel}
      />
      <div
        role="dialog"
        aria-modal="true"
        className="fixed left-1/2 top-1/2 z-50 w-[min(400px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-[var(--border-radius-lg)] border border-[var(--color-border)] bg-[var(--color-background-primary)] p-5 shadow-xl"
      >
        <h3 className="text-[15px] font-semibold">{title}</h3>
        <div className="mt-2 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {message}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" size="sm" disabled={pending} onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            size="sm"
            disabled={pending}
            className={cn(danger && 'bg-[var(--color-danger)] hover:opacity-90')}
            onClick={onConfirm}
          >
            {pending ? '处理中…' : confirmLabel}
          </Button>
        </div>
      </div>
    </>
  )
}
