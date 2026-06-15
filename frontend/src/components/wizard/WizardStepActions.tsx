import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type Props = {
  onBack?: () => void
  className?: string
  children?: ReactNode
}

export function WizardStepActions({ onBack, className, children }: Props) {
  return (
    <div
      className={cn(
        'flex flex-col gap-2 sm:flex-row sm:items-center',
        onBack ? 'sm:justify-between' : 'sm:justify-end',
        className,
      )}
    >
      {onBack ? (
        <Button variant="ghost" type="button" onClick={onBack}>
          上一步
        </Button>
      ) : null}
      {children ? (
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-end">
          {children}
        </div>
      ) : null}
    </div>
  )
}
