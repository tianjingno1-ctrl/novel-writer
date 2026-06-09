import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { createBook } from '@/api/endpoints'
import { WizardProgress } from '@/components/wizard/WizardProgress'
import { StepDirection } from '@/components/wizard/StepDirection'
import { StepPlan } from '@/components/wizard/StepPlan'
import { StepReference } from '@/components/wizard/StepReference'
import { StepReviewCriteria } from '@/components/wizard/StepReviewCriteria'
import { AuthorProfileInherit } from '@/components/product/ComplianceGate'
import { useWizardStore } from '@/stores/wizardStore'

export function NewBookPage() {
  const [params] = useSearchParams()
  const mode = params.get('mode') ?? 'quick'
  const navigate = useNavigate()
  const qc = useQueryClient()
  const step = useWizardStore((s) => s.step)
  const setStep = useWizardStore((s) => s.setStep)
  const reset = useWizardStore((s) => s.reset)

  const initBook = useMutation({
    mutationFn: () =>
      createBook({
        title: '新书',
        type: mode === 'quick' ? 'short' : 'novel',
        platform: 'tomato',
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['library'] })
      void qc.invalidateQueries({ queryKey: ['status'] })
    },
  })

  useEffect(() => {
    reset()
    if (mode === 'import') {
      setStep('plan')
    } else if (mode === 'deconstruct') {
      setStep('reference')
    } else {
      setStep('reference')
    }
    void initBook.mutateAsync().catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- init once per visit
  }, [mode])

  const goDirection = () => setStep('direction')

  return (
    <div className="pb-24 pt-4">
      <button
        type="button"
        className="mb-2 px-4 text-sm text-muted hover:text-foreground"
        onClick={() => navigate('/')}
      >
        ← 返回书架
      </button>
      <WizardProgress current={step} />
      {step === 'reference' ? (
        <div className="space-y-4">
          <StepReference
            onNext={goDirection}
            deconstructMode={mode === 'deconstruct'}
          />
          <div className="mx-auto max-w-lg px-4">
            <AuthorProfileInherit />
          </div>
        </div>
      ) : null}
      {step === 'direction' ? (
        <StepDirection onNext={() => setStep('plan')} />
      ) : null}
      {step === 'plan' ? <StepPlan /> : null}
      {step === 'criteria' ? <StepReviewCriteria /> : null}
      {initBook.error ? (
        <p className="mt-4 text-center text-sm text-danger">
          {(initBook.error as Error).message}
        </p>
      ) : null}
    </div>
  )
}
