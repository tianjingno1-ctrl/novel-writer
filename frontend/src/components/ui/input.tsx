import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'flex h-[30px] w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-primary)] px-3 text-[13px] transition-colors placeholder:text-[var(--color-text-tertiary)] focus-visible:outline-none focus-visible:border-[var(--color-primary)] disabled:opacity-40',
        className,
      )}
      {...props}
    />
  )
}

export function Textarea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        'flex min-h-24 w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-primary)] px-3 py-2 text-[13px] transition-colors placeholder:text-[var(--color-text-tertiary)] focus-visible:outline-none focus-visible:border-[var(--color-primary)] disabled:opacity-40',
        className,
      )}
      {...props}
    />
  )
}
