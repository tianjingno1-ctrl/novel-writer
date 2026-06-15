import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'

import {
  initReviewCriteria,
  updateReviewCriteria,
} from '@/api/endpoints'
import { fetchPlanProduct, updatePlanMeta } from '@/api/productApi'
import { WizardStepActions } from '@/components/wizard/WizardStepActions'
import { persistWizardStep } from '@/components/wizard/wizardPersist'
import { Button } from '@/components/ui/button'
import {
  criterionKey,
  criterionLabel,
  profileHardRules,
} from '@/lib/reviewCriteria'
import { useWizardStore } from '@/stores/wizardStore'

type Props = {
  onBack?: () => void
}

export function StepReviewCriteria({ onBack }: Props) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const reset = useWizardStore((s) => s.reset)

  const { data: plan, refetch } = useQuery({
    queryKey: ['plan', 'product'],
    queryFn: fetchPlanProduct,
  })

  const criteria = plan?.review_criteria ?? {}
  const hardRefs = (criteria.hard_rules as string[] | undefined) ?? []
  const softRefs = (criteria.soft_rules as string[] | undefined) ?? []
  const custom = (criteria.custom_checks as string[] | undefined) ?? []

  const hard = profileHardRules(plan?.resolved_criteria?.hard)
  const soft = plan?.resolved_criteria?.soft ?? []

  const [customText, setCustomText] = useState(custom.join('\n'))

  const init = useMutation({
    mutationFn: () => initReviewCriteria(),
    onSuccess: () => void refetch(),
  })

  const save = useMutation({
    mutationFn: async () => {
      const meta = {
        ...((plan?.meta as Record<string, unknown>) ?? {}),
      }
      await updatePlanMeta(meta)
      await updateReviewCriteria({
        custom_checks: customText
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
      })
      await persistWizardStep('criteria')
      await updatePlanMeta({ wizard_complete: true, wizard_step: null })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['library'] })
      void qc.invalidateQueries({ queryKey: ['status'] })
      reset()
      navigate('/writing')
    },
  })

  const hasCriteria =
    hardRefs.length > 0 || softRefs.length > 0 || custom.length > 0

  const profileId = String(criteria.platform_profile ?? '').trim()

  return (
    <div className="mx-auto max-w-lg space-y-5 px-4 pb-8">
      <div>
        <h2 className="text-[13px] font-medium">审阅标准</h2>
        <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
          写章时按这些项做质量检查
          {profileId ? ` · 预设 ${profileId}` : ''}
        </p>
      </div>

      {!hasCriteria ? (
        <div className="flex justify-center">
          <Button onClick={() => init.mutate()} disabled={init.isPending}>
            {init.isPending ? '生成中…' : '从平台预设生成'}
          </Button>
        </div>
      ) : (
        <div className="card-ui space-y-4 text-[13px]">
          {hard.length > 0 ? (
            <div>
              <p className="text-[11px] font-medium text-[var(--color-danger)]">
                必须
              </p>
              <ul className="mt-2 space-y-1.5">
                {hard.map((c, i) => (
                  <li key={criterionKey(c, 'hard', i)}>
                    {criterionLabel(c)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {soft.length > 0 ? (
            <div>
              <p className="text-[11px] font-medium text-[var(--color-text-secondary)]">
                建议
              </p>
              <ul className="mt-2 space-y-1.5">
                {soft.map((c, i) => (
                  <li key={criterionKey(c, 'soft', i)}>
                    {criterionLabel(c)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div>
            <p className="font-medium">自定义检查（每行一条）</p>
            <textarea
              className="mt-2 min-h-24 w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] p-3 text-[13px] outline-none"
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              placeholder="例如：章末钩子是否让人想点下一章"
            />
          </div>
        </div>
      )}

      {hasCriteria ? (
        <WizardStepActions onBack={onBack}>
          <Button
            disabled={save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? '保存中…' : '完成，开始写作'}
          </Button>
        </WizardStepActions>
      ) : onBack ? (
        <WizardStepActions onBack={onBack} />
      ) : null}

      {(init.error || save.error) && (
        <p className="text-center text-[13px] text-[var(--color-danger)]">
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
