import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'

import {
  initReviewCriteria,
  updateReviewCriteria,
} from '@/api/endpoints'
import { fetchPlanProduct } from '@/api/productApi'
import { Button } from '@/components/ui/button'
import { useWizardStore } from '@/stores/wizardStore'

export function StepReviewCriteria() {
  const navigate = useNavigate()
  const reset = useWizardStore((s) => s.reset)

  const { data: plan, refetch } = useQuery({
    queryKey: ['plan', 'product'],
    queryFn: fetchPlanProduct,
  })

  const criteria = plan?.review_criteria ?? {}
  const hard = (criteria.hard_rules as string[] | undefined) ?? []
  const soft = (criteria.soft_rules as string[] | undefined) ?? []
  const custom = (criteria.custom_checks as string[] | undefined) ?? []

  const [customText, setCustomText] = useState(custom.join('\n'))

  const init = useMutation({
    mutationFn: () => initReviewCriteria(),
    onSuccess: () => void refetch(),
  })

  const save = useMutation({
    mutationFn: () =>
      updateReviewCriteria({
        custom_checks: customText
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
      }),
    onSuccess: () => {
      reset()
      navigate('/writing')
    },
  })

  const hasCriteria = hard.length > 0 || soft.length > 0 || custom.length > 0

  return (
    <div className="mx-auto max-w-lg space-y-6 px-4 pb-8">
      <div className="text-center">
        <h2 className="text-xl font-semibold">审阅标准</h2>
        <p className="mt-2 text-sm text-muted">
          写章时会按这些项做差距分析（可稍后改）
        </p>
      </div>

      {!hasCriteria ? (
        <div className="flex justify-center">
          <Button
            size="lg"
            onClick={() => init.mutate()}
            disabled={init.isPending}
          >
            {init.isPending ? '生成中…' : '从平台 profile 生成'}
          </Button>
        </div>
      ) : (
        <div className="space-y-4 rounded-xl border border-border bg-surface p-5 text-sm">
          {hard.length > 0 ? (
            <div>
              <p className="font-medium text-foreground">硬性规则</p>
              <ul className="mt-2 list-inside list-disc text-muted">
                {hard.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {soft.length > 0 ? (
            <div>
              <p className="font-medium text-foreground">软性规则</p>
              <ul className="mt-2 list-inside list-disc text-muted">
                {soft.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div>
            <p className="font-medium text-foreground">自定义检查（每行一条）</p>
            <textarea
              className="mt-2 min-h-24 w-full rounded-md border border-border bg-background p-3 text-sm"
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              placeholder="例如：章末钩子是否让人想点下一章"
            />
          </div>
        </div>
      )}

      {hasCriteria ? (
        <Button
          className="w-full"
          size="lg"
          disabled={save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? '保存中…' : '确认，开始写 →'}
        </Button>
      ) : null}

      {(init.error || save.error) && (
        <p className="text-center text-sm text-danger">
          {String(
            (init.error as Error | null)?.message ??
              (save.error as Error | null)?.message ??
              '操作失败',
          )}
        </p>
      )}
    </div>
  )
}
