import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { createBook, fetchStatus, updateBook } from '@/api/endpoints'
import { fetchPlanProduct, updatePlanMeta } from '@/api/productApi'
import { StepBasicInfo } from '@/components/wizard/StepBasicInfo'
import { WizardProgress } from '@/components/wizard/WizardProgress'
import { StepDirection } from '@/components/wizard/StepDirection'
import { StepPlan } from '@/components/wizard/StepPlan'
import { StepReference } from '@/components/wizard/StepReference'
import { StepReviewCriteria } from '@/components/wizard/StepReviewCriteria'
import { isWizardStep, persistWizardStep, prevWizardStep, wizardStepIndex } from '@/components/wizard/wizardPersist'
import { AuthorProfileInherit } from '@/components/product/ComplianceGate'
import { isBookWritingReady } from '@/lib/bookReady'
import { normalizeBookFormat, normalizeGenre } from '@/lib/bookMeta'
import { resolveWizardChapterCount, resolveWordsPerChapter } from '@/lib/wordBudget'
import { useWizardStore, type WizardStep } from '@/stores/wizardStore'

export function NewBookPage() {
  const [params] = useSearchParams()
  const mode = params.get('mode') ?? 'quick'
  const isResume = params.get('resume') === '1'
  const minStep: WizardStep = mode === 'import' ? 'plan' : 'basic'
  const navigate = useNavigate()
  const qc = useQueryClient()
  const step = useWizardStore((s) => s.step)
  const setStep = useWizardStore((s) => s.setStep)
  const reset = useWizardStore((s) => s.reset)
  const setBasic = useWizardStore((s) => s.setBasic)
  const basicTitle = useWizardStore((s) => s.basicTitle)
  const basicPlatform = useWizardStore((s) => s.basicPlatform)
  const basicBookType = useWizardStore((s) => s.basicBookType)
  const basicGenre = useWizardStore((s) => s.basicGenre)
  const totalWords = useWizardStore((s) => s.totalWords)
  const shortChapterCount = useWizardStore((s) => s.shortChapterCount)
  const novelChapterCount = useWizardStore((s) => s.novelChapterCount)
  const wordsPerChapter = useWizardStore((s) => s.wordsPerChapter)
  const setTotalWords = useWizardStore((s) => s.setTotalWords)
  const setShortChapterCount = useWizardStore((s) => s.setShortChapterCount)
  const setNovelChapterCount = useWizardStore((s) => s.setNovelChapterCount)
  const setWordsPerChapter = useWizardStore((s) => s.setWordsPerChapter)

  const { data: planProduct } = useQuery({
    queryKey: ['plan', 'product'],
    queryFn: fetchPlanProduct,
    enabled: isResume,
  })

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    enabled: isResume,
  })

  const initBook = useMutation({
    mutationFn: () =>
      createBook({
        title: basicTitle.trim() || '新书',
        type: basicBookType,
        platform: basicPlatform,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['library'] })
      void qc.invalidateQueries({ queryKey: ['status'] })
    },
  })

  useEffect(() => {
    if (isResume) {
      return
    }
    reset()
    setBasic({
      title: '新书',
      bookType: mode === 'quick' ? 'short' : 'novel',
    })
    if (mode === 'import') {
      setStep('plan')
    } else {
      setStep('basic')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- init once per visit
  }, [mode, isResume])

  useEffect(() => {
    if (!isResume) {
      return
    }
    const meta = planProduct?.meta as {
      wizard_complete?: boolean
      wizard_step?: string
      title?: string
      platform?: string
      genre?: string
      chapter_count?: number
      word_count_per_chapter?: number
      total_word_target?: number
    } | undefined
    if (isBookWritingReady(planProduct)) {
      navigate('/writing', { replace: true })
      return
    }
    if (meta?.title) {
      setBasic({ title: String(meta.title) })
    }
    if (meta?.platform) {
      setBasic({ platform: String(meta.platform) })
    }
    if (meta?.genre) {
      setBasic({ genre: normalizeGenre(String(meta.genre)) })
    }
    if (status?.book_type) {
      setBasic({
        bookType: normalizeBookFormat(status.book_type, 'novel'),
      })
    }
    if (meta?.total_word_target && meta.total_word_target > 0) {
      setTotalWords(meta.total_word_target)
    }
    if (meta?.chapter_count && meta.chapter_count > 0) {
      if (status?.book_type === 'short') {
        setShortChapterCount(meta.chapter_count)
      } else {
        setNovelChapterCount(meta.chapter_count)
      }
    }
    if (meta?.word_count_per_chapter && meta.word_count_per_chapter > 0) {
      setWordsPerChapter(meta.word_count_per_chapter)
    }
    const saved = meta?.wizard_step
    if (planProduct?.meta) {
      if (isWizardStep(saved)) {
        setStep(saved)
      } else {
        setStep('basic')
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isResume, planProduct, status?.book_type])

  const canPersist = isResume || initBook.isSuccess

  const goStep = (next: WizardStep) => {
    setStep(next)
    if (canPersist) {
      void persistWizardStep(next)
    }
  }

  const goBack = () => {
    const prev = prevWizardStep(step)
    if (!prev) return
    if (wizardStepIndex(prev) < wizardStepIndex(minStep)) return
    goStep(prev)
  }

  const goToStep = (target: WizardStep) => {
    if (wizardStepIndex(target) > wizardStepIndex(step)) return
    if (wizardStepIndex(target) < wizardStepIndex(minStep)) return
    goStep(target)
  }

  const showBack = wizardStepIndex(step) > wizardStepIndex(minStep)

  const afterBasic = useMutation({
    mutationFn: async () => {
      const title = basicTitle.trim() || '新书'
      const chapterCount = resolveWizardChapterCount(
        basicBookType,
        totalWords,
        novelChapterCount,
        basicPlatform,
        shortChapterCount,
      )
      const wpc = resolveWordsPerChapter(
        basicBookType,
        totalWords,
        chapterCount,
        wordsPerChapter,
      )
      if (!isResume && !initBook.isSuccess) {
        await initBook.mutateAsync()
      }
      await updatePlanMeta({
        title,
        platform: basicPlatform,
        genre: basicGenre || undefined,
        wizard_step: 'reference',
        chapter_count: chapterCount,
        word_count_per_chapter: wpc,
        total_word_target: basicBookType === 'short' ? totalWords : undefined,
      })
      const bookStatus = await fetchStatus()
      if (bookStatus.book_id) {
        await updateBook(bookStatus.book_id, {
          title,
          type: basicBookType,
          platform: basicPlatform,
        })
      }
    },
    onSuccess: () => goStep('reference'),
  })

  return (
    <div className="wizard-shell">
      <button
        type="button"
        className="mb-2 self-start text-[13px] text-[var(--color-text-tertiary)] hover:text-[var(--color-primary)]"
        onClick={() => navigate('/')}
      >
        ← 返回书架
      </button>
      <WizardProgress
        current={step}
        minStep={minStep}
        onStepClick={goToStep}
      />
      {step === 'basic' ? (
        <StepBasicInfo
          onNext={() => afterBasic.mutate()}
          pending={afterBasic.isPending}
        />
      ) : null}
      {step === 'reference' ? (
        <div className="space-y-4">
          <StepReference
            onNext={() => goStep('direction')}
            onBack={showBack ? goBack : undefined}
            deconstructMode={mode === 'deconstruct'}
          />
          <div className="mx-auto max-w-lg px-4">
            <AuthorProfileInherit />
          </div>
        </div>
      ) : null}
      {step === 'direction' ? (
        <StepDirection
          onNext={() => goStep('plan')}
          onBack={showBack ? goBack : undefined}
        />
      ) : null}
      {step === 'plan' ? (
        <StepPlan
          onNext={() => goStep('criteria')}
          onBack={showBack ? goBack : undefined}
        />
      ) : null}
      {step === 'criteria' ? (
        <StepReviewCriteria onBack={showBack ? goBack : undefined} />
      ) : null}
      {(initBook.error || afterBasic.error) ? (
        <p className="mt-4 text-center text-[13px] text-[var(--color-danger)]">
          {((afterBasic.error ?? initBook.error) as Error).message}
        </p>
      ) : null}
    </div>
  )
}
