import type { HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

const variants = {
  default: 'bg-[var(--color-background-secondary)] text-[var(--color-text-secondary)]',
  hard: 'badge-hard',
  soft: 'badge-soft',
  done: 'badge-done',
  warn: 'badge-warn',
  success: 'badge-done',
  warning: 'badge-warn',
  muted: 'bg-[var(--color-background-secondary)] text-[var(--color-text-tertiary)]',
} as const

type Props = HTMLAttributes<HTMLSpanElement> & {
  variant?: keyof typeof variants
}

export function Badge({ className, variant = 'default', ...props }: Props) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium',
        variants[variant],
        className,
      )}
      {...props}
    />
  )
}
