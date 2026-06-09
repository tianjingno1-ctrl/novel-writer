import type { HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

const variants = {
  default: 'bg-accent text-foreground',
  success: 'bg-primary/15 text-primary',
  warning: 'bg-warning/15 text-warning',
  muted: 'bg-accent text-muted',
} as const

type Props = HTMLAttributes<HTMLSpanElement> & {
  variant?: keyof typeof variants
}

export function Badge({ className, variant = 'default', ...props }: Props) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        variants[variant],
        className,
      )}
      {...props}
    />
  )
}
