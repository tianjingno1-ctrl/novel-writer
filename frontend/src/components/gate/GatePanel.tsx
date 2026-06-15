import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Props = {
  children: ReactNode
  className?: string
}

/** 中间栏 Gate 卡片（非模态） */
export function GatePanel({ children, className }: Props) {
  return (
    <div className={cn('card-ui mx-auto w-full max-w-lg', className)}>{children}</div>
  )
}
