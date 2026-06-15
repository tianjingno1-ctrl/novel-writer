import { useMutation } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'

import { applyPlan, prefillPlan, semanticValidatePlan, validatePlan } from '@/api/endpoints'
import { PlanValidationPanel } from '@/components/wizard/PlanValidationPanel'
import { IntentFields } from '@/components/wizard/IntentFields'
import { WizardStepActions } from '@/components/wizard/WizardStepActions'
import type { PlanValidationIssue } from '@/lib/planValidation'
import { SHORT_PAYWALL_HELP } from '@/lib/planValidation'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  CHAPTER_ROLE_LABELS,
  CHAPTER_ROLES,
  chapterForApply,
  emptyStructuredFinal,
  getStructuredIntentFields,
  intentFieldLabel,
  intentFinalText,
  isChapterRole,
  type PlanChapterRow,
} from '@/lib/chapterRoles'
import { stampChapterWordTargets } from '@/lib/wordBudget'
import { useWizardWordBudget } from '@/hooks/useWizardWordBudget'
import { useWizardStore } from '@/stores/wizardStore'

function updateChapter(
  chapters: PlanChapterRow[],
  index: number,
  patch: Partial<PlanChapterRow>,
) {
  return chapters.map((ch, i) => (i === index ? { ...ch, ...patch } : ch))
}

function updateIntent(
  chapters: PlanChapterRow[],
  index: number,
  patch: { ai_suggest?: string; final?: string | Record<string, string> },
) {
  const ch = chapters[index]
  if (!ch) return chapters
  return updateChapter(chapters, index, {
    intent: { ...ch.intent, ...patch },
  })
}

function pickPlanOption(data: {
  option?: { title?: string; chapters?: PlanChapterRow[] }
  options?: Array<{ title?: string; chapters?: PlanChapterRow[] }>
}) {
  return data.option ?? data.options?.[0] ?? {}
}

type Props = {
  onNext: () => void
  onBack?: () => void
}

export function StepPlan({ onNext, onBack }: Props) {
  const selectedDirection = useWizardStore((s) => s.selectedDirection)
  const { chapterCount, wordsPerChapterResolved } = useWizardWordBudget()
  const planTitle = useWizardStore((s) => s.planTitle)
  const planChapters = useWizardStore((s) => s.planChapters)
  const planLogId = useWizardStore((s) => s.planLogId)
  const bookType = useWizardStore((s) => s.basicBookType)
  const setPlan = useWizardStore((s) => s.setPlan)
  const [expanded, setExpanded] = useState(true)
  const [localChapters, setLocalChapters] = useState<PlanChapterRow[]>([])
  const [validationErrors, setValidationErrors] = useState<PlanValidationIssue[]>(
    [],
  )
  const [validationWarnings, setValidationWarnings] = useState<
    PlanValidationIssue[]
  >([])
  const [validating, setValidating] = useState(false)
  const [semanticNote, setSemanticNote] = useState<string | null>(null)

  const chapters = localChapters.length ? localChapters : planChapters

  const planOption = () => ({
    title: planTitle,
    chapters: stampChapterWordTargets(chapters, wordsPerChapterResolved).map((ch) =>
      chapterForApply(ch),
    ),
  })

  const syncChapters = (next: PlanChapterRow[]) => {
    setLocalChapters(next)
    setPlan(planTitle, next, planLogId)
  }

  const load = useMutation({
    mutationFn: () =>
      prefillPlan({
        direction_option: selectedDirection ?? undefined,
        chapter_count: chapterCount,
      }),
    onSuccess: (data) => {
      const opt = pickPlanOption(data)
      const rows = stampChapterWordTargets(
        (opt.chapters ?? []) as PlanChapterRow[],
        wordsPerChapterResolved,
      )
      setLocalChapters(rows)
      setPlan(
        String(opt.title ?? selectedDirection?.logline ?? '未命名'),
        rows,
        data.log_id ?? null,
      )
    },
  })

  const semanticCheck = useMutation({
    mutationFn: () => semanticValidatePlan(planOption(), true),
    onSuccess: (data) => {
      if (data.skipped) {
        const reason =
          data.reason === 'no_api_key'
            ? '未配置审阅 API Key，已跳过语义检查'
            : data.reason === 'no_pairs'
              ? '无可检查的跨章 intent 对'
              : data.reason === 'parse_failed'
                ? '语义检查结果解析失败'
                : '语义检查暂不可用'
        setSemanticNote(reason)
        return
      }
      setSemanticNote(
        data.pairs_checked
          ? `已检查 ${data.pairs_checked} 组跨章 intent（LLM）`
          : null,
      )
      const overrides = new Set(data.overrides ?? [])
      setValidationWarnings((prev) => {
        const kept = prev.filter((w) => !overrides.has(w.code ?? ''))
        const merged = [...kept, ...(data.warnings ?? [])]
        const seen = new Set<string>()
        return merged.filter((w) => {
          const key = `${w.code ?? ''}-${w.chapter_num ?? ''}-${w.message ?? ''}`
          if (seen.has(key)) return false
          seen.add(key)
          return true
        })
      })
    },
  })

  const confirm = useMutation({
    mutationFn: async () => {
      const option = planOption()
      const check = await validatePlan(option, true)
      setValidationErrors(check.errors ?? [])
      setValidationWarnings(check.warnings ?? [])
      if (!check.ok) {
        throw new Error(check.error || '章规划校验未通过')
      }
      return applyPlan(option, true, planLogId ?? undefined)
    },
    onSuccess: (data) => {
      const warns = (data?.validation_warnings ?? []) as PlanValidationIssue[]
      if (warns.length) {
        setValidationWarnings(warns)
      }
      onNext()
    },
  })

  const hasPlan = chapters.length > 0
  const hasBlockingErrors = validationErrors.length > 0

  useEffect(() => {
    if (!hasPlan) {
      setValidationErrors([])
      setValidationWarnings([])
      setSemanticNote(null)
      return undefined
    }
    setSemanticNote(null)
    const option = planOption()
    setValidating(true)
    const timer = window.setTimeout(() => {
      void validatePlan(option, true)
        .then((check) => {
          setValidationErrors(check.errors ?? [])
          setValidationWarnings(check.warnings ?? [])
        })
        .catch(() => {
          setValidationErrors([])
        })
        .finally(() => setValidating(false))
    }, 600)
    return () => window.clearTimeout(timer)
  }, [hasPlan, planTitle, chapters])

  return (
    <div className="mx-auto max-w-xl space-y-5 px-4 pb-8">
      <div>
        <h2 className="text-[13px] font-medium">章节规划</h2>
        <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
          {planTitle || '章规划'}
          {hasPlan ? ` · 共 ${chapters.length} 章 · 章均约 ${wordsPerChapterResolved} 字` : ''}
        </p>
        <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
          确认每章 <strong className="font-medium">叙事角色</strong> 与{' '}
          <strong className="font-medium">本章意图</strong>。
          {bookType === 'short' ? (
            <span className="mt-1 block">{SHORT_PAYWALL_HELP}</span>
          ) : null}
        </p>
      </div>

      {!hasPlan ? (
        <div className="space-y-4">
          <div className="flex justify-center">
            <Button onClick={() => load.mutate()} disabled={load.isPending}>
              {load.isPending ? '正在规划章节…' : '生成章规划'}
            </Button>
          </div>
          {onBack ? <WizardStepActions onBack={onBack} /> : null}
        </div>
      ) : (
        <div className="card-ui p-0">
          <button
            type="button"
            className="flex w-full items-center justify-between px-3 py-3 text-left"
            onClick={() => setExpanded((v) => !v)}
          >
            <span className="text-[13px] font-medium">章节列表</span>
            {expanded ? (
              <ChevronDown className="h-4 w-4 text-[var(--color-text-tertiary)]" />
            ) : (
              <ChevronRight className="h-4 w-4 text-[var(--color-text-tertiary)]" />
            )}
          </button>
          {expanded ? (
            <ul className="border-t border-[var(--color-border-tertiary)] px-3 py-2">
              {chapters.map((ch, i) => {
                const role = isChapterRole(ch.role) ? ch.role : ''
                const intentLabel = intentFieldLabel(role)
                return (
                  <li
                    key={ch.num ?? i}
                    className="space-y-2 border-b border-[var(--color-border-tertiary)] py-3 last:border-0"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="shrink-0 text-[13px] text-[var(--color-text-tertiary)]">
                        第{ch.num ?? i + 1}章
                      </span>
                      {role ? (
                        <Badge variant={role === 'paywall' ? 'hard' : 'soft'}>
                          {CHAPTER_ROLE_LABELS[role]}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="flex gap-2 text-[13px]">
                      <input
                        className="flex-1 rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-2 py-1 text-[13px] outline-none"
                        value={ch.title ?? ''}
                        placeholder="标题"
                        onChange={(e) =>
                          syncChapters(
                            updateChapter(chapters, i, { title: e.target.value }),
                          )
                        }
                      />
                    </div>
                    <select
                      className="w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] bg-transparent px-2 py-1.5 text-[11px] outline-none"
                      value={role}
                      onChange={(e) => {
                        const nextRole = e.target.value
                        const patch: Partial<PlanChapterRow> = {
                          role: nextRole || undefined,
                        }
                        if (nextRole && nextRole !== 'paid_open' && isChapterRole(nextRole)) {
                          const structured = getStructuredIntentFields(nextRole)
                          patch.intent = {
                            kind: nextRole,
                            ai_suggest: ch.intent?.ai_suggest ?? '',
                            final: structured
                              ? emptyStructuredFinal(nextRole)
                              : intentFinalText(ch),
                          }
                        } else if (nextRole === 'paid_open') {
                          patch.intent = undefined
                        }
                        syncChapters(updateChapter(chapters, i, patch))
                      }}
                    >
                      <option value="">选择叙事角色</option>
                      {CHAPTER_ROLES.map((r) => (
                        <option key={r} value={r}>
                          {CHAPTER_ROLE_LABELS[r]}
                        </option>
                      ))}
                    </select>
                    <input
                      className="w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-2 py-1 text-[11px] outline-none"
                      value={ch.beat ?? ''}
                      placeholder="本章要写什么（场景摘要）"
                      onChange={(e) =>
                        syncChapters(
                          updateChapter(chapters, i, { beat: e.target.value }),
                        )
                      }
                    />
                    <input
                      className="w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-2 py-1 text-[11px] outline-none"
                      value={ch.hook ?? ''}
                      placeholder="章末钩子"
                      onChange={(e) =>
                        syncChapters(
                          updateChapter(chapters, i, { hook: e.target.value }),
                        )
                      }
                    />
                    <label className="flex items-center gap-2 text-[11px] text-[var(--color-text-tertiary)]">
                      目标字数
                      <input
                        type="number"
                        min={500}
                        step={100}
                        className="h-[26px] w-24 rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-2 text-[11px] outline-none"
                        value={ch.word_count_target ?? wordsPerChapterResolved}
                        onChange={(e) =>
                          syncChapters(
                            updateChapter(chapters, i, {
                              word_count_target: Number(e.target.value) || null,
                            }),
                          )
                        }
                      />
                    </label>
                    {role === 'paid_open' ? (
                      <p className="text-[11px] text-[var(--color-text-tertiary)]">
                        付费首章不用单独填意图，写作与审阅会沿用「付费切割」章的心理状态。
                      </p>
                    ) : intentLabel ? (
                      <div className="space-y-1">
                        {ch.intent?.ai_suggest ? (
                          <p className="text-[10px] text-[var(--color-text-tertiary)]">
                            AI 建议：{ch.intent.ai_suggest}
                          </p>
                        ) : null}
                        <IntentFields
                          ch={ch}
                          onChange={(final) =>
                            syncChapters(updateIntent(chapters, i, { final }))
                          }
                        />
                      </div>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          ) : null}
        </div>
      )}

      {hasPlan ? (
        <div className="space-y-3">
          {validating ? (
            <p className="text-center text-[11px] text-[var(--color-text-tertiary)]">
              正在校验章序列…
            </p>
          ) : null}
          <PlanValidationPanel
            errors={validationErrors}
            warnings={validationWarnings}
          />
          {semanticNote ? (
            <p className="text-center text-[11px] text-[var(--color-text-tertiary)]">
              {semanticNote}
            </p>
          ) : null}
          <WizardStepActions onBack={onBack}>
            <Button
              variant="outline"
              onClick={() => load.mutate()}
              disabled={load.isPending}
            >
              <RefreshCw className="mr-1 h-3.5 w-3.5" />
              重新生成
            </Button>
            <Button
              variant="outline"
              onClick={() => semanticCheck.mutate()}
              disabled={
                semanticCheck.isPending || validating || hasBlockingErrors
              }
            >
              {semanticCheck.isPending ? '语义检查中…' : '深度语义检查（可选）'}
            </Button>
            <Button
              onClick={() => confirm.mutate()}
              disabled={confirm.isPending || hasBlockingErrors || validating}
            >
              {confirm.isPending ? '保存中…' : '确认并下一步'}
            </Button>
          </WizardStepActions>
        </div>
      ) : null}

      {load.error ? (
        <p className="text-center text-[13px] text-[var(--color-danger)]">
          {(load.error as Error).message}
        </p>
      ) : null}
      {confirm.error ? (
        <p className="text-center text-[13px] text-[var(--color-danger)]">
          {(confirm.error as Error).message}
        </p>
      ) : null}
      {semanticCheck.error ? (
        <p className="text-center text-[13px] text-[var(--color-danger)]">
          {(semanticCheck.error as Error).message}
        </p>
      ) : null}
    </div>
  )
}
