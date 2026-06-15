import { cva, type VariantProps } from 'class-variance-authority'
import type { ButtonHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-[var(--border-radius-md)] text-[13px] font-medium transition-colors disabled:pointer-events-none disabled:opacity-40',
  {
    variants: {
      variant: {
        default:
          'h-[34px] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-text-primary)] px-4 text-[var(--color-background-primary)] hover:opacity-90',
        outline:
          'h-[34px] border border-[var(--color-border)] bg-[var(--color-background-primary)] px-4 hover:bg-[var(--color-background-secondary)]',
        ghost:
          'h-[34px] border border-transparent px-4 hover:bg-[var(--color-background-secondary)]',
        danger:
          'h-[30px] border-[0.5px] border-[#f09595] bg-transparent px-3 text-[var(--color-danger)] hover:bg-[var(--color-danger-bg)]',
        dangerOutline:
          'h-[30px] border-[0.5px] border-[#f09595] bg-transparent px-3 text-[var(--color-danger)] hover:bg-[var(--color-danger-bg)]',
      },
      size: {
        default: 'h-[30px] px-3',
        sm: 'h-[26px] px-2.5 text-[11px]',
        lg: 'h-[36px] px-4',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants>

export function Button({
  className,
  variant,
  size,
  type = 'button',
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
}
