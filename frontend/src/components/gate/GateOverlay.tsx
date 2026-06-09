import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Props = {
  open: boolean
  children: ReactNode
  className?: string
}

/** 决策状态：正文变暗，中央聚焦判断卡 */
export function GateOverlay({ open, children, className }: Props) {
  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4">
      <div
        className={cn(
          'w-full max-w-md rounded-2xl border border-border bg-surface p-6 shadow-xl',
          className,
        )}
      >
        {children}
      </div>
    </div>
  )
}
