import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ClipboardList, Stethoscope } from 'lucide-react'

import { createAttributionLog, fetchChatHistory } from '@/api/chapterFlow'
import { fetchChapter, fetchPlanProduct } from '@/api/productApi'
import { fetchStatus } from '@/api/endpoints'
import { AttributionRulesDrawer } from '@/components/gate/AttributionRulesDrawer'
import { ChapterGates } from '@/components/gate/ChapterGates'
import { GateStepIndicator } from '@/components/gate/GateStepIndicator'
import { ChapterSidebar } from '@/components/writing/ChapterSidebar'
import { SessionRecoveryBanner } from '@/components/writing/SessionRecoveryBanner'
import { ChapterPlanHintPanel } from '@/components/writing/ChapterPlanHintPanel'
import { BookFilesDrawer } from '@/components/writing/BookFilesDrawer'
import { ChapterEditor } from '@/components/writing/ChapterEditor'
import { Button } from '@/components/ui/button'
import {
  countChapterChars,
  evaluateWordCount,
} from '@/lib/precheckIssues'
import { cn } from '@/lib/utils'
import { useChapterFlow } from '@/hooks/useChapterFlow'
import { useSSEStream } from '@/hooks/useSSEStream'
import { useWorkQueue } from '@/hooks/useWorkQueue'
import { useBookStore } from '@/stores/bookStore'
import { isBookWritingReady } from '@/lib/bookReady'
import {
  chapterQueryKey,
  chatHistoryQueryKey,
  planProductQueryKey,
} from '@/lib/bookQueryKeys'
import { toast } from '@/stores/toastStore'

export function FlowCanvas() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const writeChapterNum = useBookStore((s) => s.writeChapterNum)
  const setWriteChapterNum = useBookStore((s) => s.setWriteChapterNum)
  const consumeFlowIntent = useBookStore((s) => s.consumeFlowIntent)

  const { data: status, isFetched: statusReady } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
  })

  const bookId = (status?.book_id ?? '').trim()
  const chapter = writeChapterNum ?? status?.write_chapter_num ?? 1
  const { data: planProduct, isLoading: planLoading } = useQuery({
    queryKey: planProductQueryKey(bookId),
    queryFn: fetchPlanProduct,
    enabled: Boolean(bookId),
  })
  const isShortBook = status?.book_type === 'short'
  const flow = useChapterFlow(chapter, isShortBook)

  const { data: chapterData, refetch: refetchChapter } = useQuery({
    queryKey: chapterQueryKey(bookId, chapter),
    queryFn: () => fetchChapter(chapter),
    enabled: Boolean(bookId),
  })

  /** 侧栏切章后只读磁盘，避免把上一章会话预览串到新章 */
  const [preferDiskContent, setPreferDiskContent] = useState(false)

  useEffect(() => {
    setPreferDiskContent(false)
  }, [bookId])

  const { streaming, text, error, lastEvent, start, stop, reset } =
    useSSEStream()

  const diskContent = chapterData?.content ?? ''
  const diskBodyChars = countChapterChars(
    diskContent.replace(/^#[^\n]*\n+/, ''),
  )
  const wantsSessionFallback =
    !preferDiskContent &&
    !streaming &&
    !text &&
    diskBodyChars < 80 &&
    flow.phase === 'writing'

  const { data: chatHistory } = useQuery({
    queryKey: chatHistoryQueryKey(bookId),
    queryFn: fetchChatHistory,
    enabled: Boolean(bookId) && wantsSessionFallback,
  })

  const sessionPreview = (() => {
    if (!wantsSessionFallback) return ''
    const convChapter = chatHistory?.conversation_chapter_num
    if (convChapter != null && convChapter !== chapter) return ''
    const messages = chatHistory?.messages ?? []
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i]
      if (msg?.role === 'assistant' && (msg.content ?? '').trim()) {
        return msg.content ?? ''
      }
    }
    return ''
  })()

  const displayText =
    text ||
    (streaming || flow.phase === 'regenerating'
      ? ''
      : sessionPreview || diskContent)
  const streamDone = lastEvent?.type === 'done'

  const chapterStatus =
    planProduct?.chapter_statuses?.[String(chapter)] ?? ''
  /** 有正文但未定稿：中间展示全文 + 采纳/重写（含刷新后 phase 回到 writing） */
  const needsPreviewDecision =
    !streaming &&
    flow.phase !== 'regenerating' &&
    displayText.length > 0 &&
    chapterStatus !== 'approved' &&
    (flow.phase === 'writing' || flow.phase === 'preview_cta')

  const { data: workQueue } = useWorkQueue(true)

  const isFlowWriting = flow.phase === 'writing' && !streaming && !text
  const gateActive =
    flow.phase !== 'writing' &&
    flow.phase !== 'revise_preview' &&
    flow.phase !== 'rules_drawer'

  const showChapterGates =
    (gateActive || needsPreviewDecision || flow.phase === 'revise_preview') &&
    flow.phase !== 'rules_drawer'

  const gatesPhase =
    needsPreviewDecision &&
    (flow.phase === 'writing' || flow.phase === 'preview_cta')
      ? 'preview_cta'
      : flow.phase

  const canManualEdit =
    isFlowWriting &&
    Boolean(diskContent) &&
    flow.phase === 'writing' &&
    !gateActive &&
    !needsPreviewDecision

  const [showDiagnosis, setShowDiagnosis] = useState(false)
  const [showPlanHint, setShowPlanHint] = useState(false)
  const [showArchives, setShowArchives] = useState(false)
  const [diagnosisOpening, setDiagnosisOpening] = useState(false)

  /** 短篇：仅设定；长篇：设定 + 章后档案（数据仍按当前 book_id 隔离） */
  const bookType = status?.book_type ?? 'novel'
  const showBookSettings = bookType === 'short'
  const showBookArchives = bookType === 'novel' || bookType === 'world'
  const showFilesDrawer = showBookSettings || showBookArchives
  const filesDrawerLabel = showBookSettings && !showBookArchives ? '设定' : '档案'
  const filesDrawerMode = showBookArchives ? 'archives' : 'settings'

  const writingReady = isBookWritingReady(planProduct)

  useEffect(() => {
    if (!statusReady) return
    if (!bookId) {
      navigate('/', { replace: true })
    }
  }, [statusReady, bookId, navigate])

  useEffect(() => {
    if (!bookId || planLoading || !planProduct) return
    if (!writingReady) {
      navigate('/library/new?resume=1', { replace: true })
    }
  }, [bookId, planLoading, planProduct, writingReady, navigate])

  useEffect(() => {
    if (searchParams.get('archives') !== '1') return
    if (status === undefined) return
    if (showFilesDrawer) {
      setShowArchives(true)
    }
    const next = new URLSearchParams(searchParams)
    next.delete('archives')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams, showFilesDrawer, status])

  useEffect(() => {
    const intent = useBookStore.getState().flowIntent
    if (!intent) return
    if (intent.kind === 'revise') {
      if (intent.chapter !== chapter) {
        setWriteChapterNum(intent.chapter)
        return
      }
      consumeFlowIntent()
      void flow.enterComplianceRevise(
        intent.note ?? '合规回改：降低 AI 腔风险',
      )
      return
    }
    if (intent.kind === 'attribution') {
      consumeFlowIntent()
      flow.enterAttribution({
        qualityLogId: intent.qualityLogId,
        diagnosisId: intent.diagnosisId,
      })
      setShowDiagnosis(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapter, writeChapterNum])

  useEffect(() => {
    if (streamDone && lastEvent?.type === 'done') {
      flow.onStreamDone(Boolean(lastEvent.chapter_saved), displayText)
      void refetchChapter()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamDone, lastEvent, displayText])

  useEffect(() => {
    if (flow.phase === 'rules_drawer') {
      setShowDiagnosis(true)
    }
  }, [flow.phase])

  useEffect(() => {
    if (error) {
      toast('warning', error)
    }
  }, [error])

  useEffect(() => {
    if (error && flow.phase === 'regenerating') {
      flow.onRegenerateFailed()
    }
  }, [error, flow.phase, flow.onRegenerateFailed])

  useEffect(() => {
    if (flow.phase === 'chapter_done') {
      const t = window.setTimeout(() => {
        flow.resetToWriting()
        reset()
        void qc.invalidateQueries({ queryKey: ['status'] })
        void qc.invalidateQueries({ queryKey: ['flow', 'work-queue'] })
        void qc.invalidateQueries({ queryKey: ['plan'] })
      }, 1000)
      return () => window.clearTimeout(t)
    }
    return undefined
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flow.phase])

  const handleContinue = () => {
    flow.resetToWriting()
    void start('/api/chat/stream', {
      instruction: '续写本章',
      chapter_num: chapter,
      regenerate: false,
    })
  }

  const handleRegenerate = () => {
    if (streaming || flow.phase === 'regenerating') {
      return
    }
    stop()
    flow.enterRegenerating()
    reset()
    setPreferDiskContent(true)
    void qc.invalidateQueries({ queryKey: chapterQueryKey(bookId, chapter) })
    void qc.invalidateQueries({ queryKey: chatHistoryQueryKey(bookId) })
    void refetchChapter()
    void start(
      '/api/chat/stream',
      {
        regenerate: true,
        chapter_num: chapter,
      },
      (ev) => {
        if (ev.type === 'chapter_cleared') {
          void refetchChapter()
        }
        if (ev.type === 'done') {
          void refetchChapter()
        }
      },
    )
  }

  const title = status?.project_title || '未命名'
  const chapterPlan = chapterData?.plan
  const chapterTitle = chapterPlan?.title?.trim() ?? ''
  const logline = String(
    (planProduct?.meta as { logline?: string } | undefined)?.logline ?? '',
  ).trim()
  const wordCountTarget =
    flow.precheck?.word_count_target ?? chapterPlan?.word_count_target ?? null

  const charCount = countChapterChars(displayText)
  const wordStatus = evaluateWordCount(charCount, wordCountTarget)
  const showWordBar = streaming || displayText.length > 0

  const openDiagnosisDrawer = async () => {
    if (flow.diagnosisId) {
      flow.enterAttribution({ diagnosisId: flow.diagnosisId })
      setShowDiagnosis(true)
      return
    }
    const existingLog = flow.review?.log_id ?? flow.attributionLogId
    if (existingLog) {
      setShowDiagnosis(true)
      await flow.openRulesDrawer()
      return
    }
    setDiagnosisOpening(true)
    try {
      const created = await createAttributionLog(
        chapter,
        'L4a',
        '顶栏主动 Prompt 归因',
      )
      if (!created.ok || !created.log_id) {
        toast('warning', created.error ?? '无法创建诊断记录')
        return
      }
      flow.enterAttribution({ qualityLogId: created.log_id })
      setShowDiagnosis(true)
    } catch (e) {
      toast('warning', e instanceof Error ? e.message : '无法打开诊断')
    } finally {
      setDiagnosisOpening(false)
    }
  }

  const gateHandlers = {
    busy: flow.busy,
    regenerating: flow.phase === 'regenerating' || streaming,
    passLines: flow.passLines,
    topNote: flow.topNote,
    reviewProfileLabel: flow.review?.profile_label,
    resolvedCriteria: planProduct?.resolved_criteria,
    highlightDraft: flow.highlightDraft,
    highlightConflicts: flow.highlightConflicts,
    rhythmWarning: flow.rhythmWarning,
    l5bMandatory: flow.l5bMandatory,
    issueTags: flow.issueTags,
    precheckFailMessage: flow.precheckFailMessage,
    precheck: flow.precheck,
    summaryText: flow.summaryText,
    reviseOriginal: flow.reviseOriginal,
    reviseDraft: flow.reviseDraft,
    revisePrefillNote: flow.revisePrefillNote,
    onAcceptReview: () => void flow.acceptReview(),
    onRejectReview: flow.openJudgmentFork,
    onAttributionFromReview: () => void flow.openAttributionFromReview(),
    onSkipHighlights: () => void flow.skipHighlights(),
    onConfirmHighlight: (t: string, force?: boolean) => {
      void flow.confirmHighlight(t, { force }).then(() => {
        if (!force) toast('success', '已加入写作偏好')
      })
    },
    onDismissRhythm: () => void flow.dismissRhythmWarning(),
    onAttributionFromRhythm: () => void flow.openAttributionFromRhythm(),
    onToggleIssueTag: flow.toggleIssueTag,
    onRewrite: () => {
      handleRegenerate()
    },
    canSkipPaywallIntent: flow.canSkipPaywallIntent,
    onSkipPaywallIntent: () => {
      void flow.skipPaywallIntentAndContinue()
    },
    onStartRevise: () => void flow.startReviseChapter(),
    onOpenRules: () => {
      void openDiagnosisDrawer()
    },
    onSubmitRevise: (note: string) => void flow.submitRevise(note),
    onAcceptRevise: () => void flow.acceptRevise(),
    onConfirmSummary: () => void flow.confirmSummary(),
    onRegenerateSummary: () => void flow.regenerateSummary(),
    onCloseRules: flow.closeRulesDrawer,
    onNextChapter: () => {
      void qc.invalidateQueries({ queryKey: ['status'] })
      void qc.invalidateQueries({ queryKey: ['flow', 'work-queue'] })
      void qc.invalidateQueries({ queryKey: ['plan'] })
      flow.resetToWriting()
      reset()
    },
    onAdoptPreview: () => {
      void flow.continueAfterPreview(displayText).then(() => {
        void refetchChapter()
      })
    },
    onRewritePreview: () => {
      handleRegenerate()
    },
    onReviseFromCriteria: () => void flow.reviseFromCriteria(),
    onAcceptJudgment: () => void flow.acceptReview(),
  }

  if (!statusReady || !bookId || (planLoading && !planProduct)) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--bg)] text-[13px] text-[var(--color-text-tertiary)]">
        {!statusReady ? '加载写作页…' : !bookId ? '跳转书架…' : '加载书籍规划…'}
      </div>
    )
  }

  if (planProduct && !writingReady) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--bg)] text-[13px] text-[var(--color-text-tertiary)]">
        跳转开书向导…
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col bg-[var(--bg)]">
      <header className="flex h-[var(--topbar-height)] shrink-0 items-center justify-between border-b border-[var(--border)] bg-[var(--surface)] px-4">
        <div className="flex min-w-0 items-center gap-1 text-[13px]">
          <span className="truncate text-[var(--color-text-tertiary)]">{title}</span>
          <span className="text-[var(--color-text-tertiary)]">›</span>
          <span className="min-w-0 truncate font-medium">
            第 {chapter} 章
            {chapterTitle ? (
              <span className="ml-1 font-normal text-[var(--color-text-tertiary)]">
                {chapterTitle}
              </span>
            ) : null}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {showFilesDrawer ? (
            <Button
              variant="outline"
              size="sm"
              title={
                showBookSettings && !showBookArchives
                  ? '编辑本书 world/style 等设定'
                  : '编辑本书设定与章后档案'
              }
              onClick={() => setShowArchives(true)}
            >
              <Archive className="mr-1 h-3.5 w-3.5" />
              {filesDrawerLabel}
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            className={cn(
              diagnosisOpening && 'opacity-70',
            )}
            title="分析写作问题并调整 AI 写作规则"
            disabled={diagnosisOpening}
            onClick={() => void openDiagnosisDrawer()}
          >
            <Stethoscope className="mr-1 h-3.5 w-3.5" />
            {diagnosisOpening ? '打开中…' : '诊断'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className={cn(
              showPlanHint &&
                'border-[var(--color-text-primary)] bg-[var(--color-background-secondary)]',
            )}
            title="查看本书方向与本章场景摘要、钩子"
            aria-pressed={showPlanHint}
            onClick={() => setShowPlanHint((v) => !v)}
          >
            <ClipboardList className="mr-1 h-3.5 w-3.5" />
            规划
          </Button>
        </div>
      </header>

      <SessionRecoveryBanner
        status={status}
        onRestored={(num) => {
          if (num) {
            setWriteChapterNum(num)
          }
          toast('success', '续写会话已恢复')
        }}
      />

      {showPlanHint ? (
        <ChapterPlanHintPanel
          chapterNum={chapter}
          logline={logline}
          chapterPlan={chapterPlan}
          onClose={() => setShowPlanHint(false)}
        />
      ) : null}

      <div className="flex min-h-0 flex-1">
        <ChapterSidebar
          chapter={chapter}
          dimmed={gateActive}
          onSelectChapter={() => {
            stop()
            reset()
            setShowDiagnosis(false)
            flow.resetToWriting()
            setPreferDiskContent(true)
            void qc.invalidateQueries({ queryKey: chatHistoryQueryKey(bookId) })
            void refetchChapter()
          }}
        />

        <section className="flex min-w-0 flex-1 flex-col">
          <GateStepIndicator phase={flow.phase} />

          {showWordBar ? (
            <div className="flex shrink-0 items-center justify-between border-b border-[var(--color-border-tertiary)] px-4 py-2 text-[11px]">
              <span className="text-[var(--color-text-tertiary)]">
                {charCount.toLocaleString()} 字
                {wordCountTarget && wordCountTarget > 0
                  ? ` / 约 ${wordCountTarget}`
                  : ''}
              </span>
              {charCount > 0 && wordStatus.label ? (
                <span
                  className={cn(
                    wordStatus.ok
                      ? 'text-[var(--color-success)]'
                      : 'text-[var(--color-danger)]',
                  )}
                  title={wordStatus.detail}
                >
                  {wordStatus.label}
                </span>
              ) : null}
            </div>
          ) : null}

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            <div className="mx-auto w-full max-w-3xl">
              {(streaming || flow.phase === 'regenerating') && !displayText ? (
                <div className="space-y-2 animate-pulse">
                  <div className="h-3 rounded bg-[var(--color-background-secondary)]" />
                  <div className="h-3 w-5/6 rounded bg-[var(--color-background-secondary)]" />
                  <div className="h-3 w-4/6 rounded bg-[var(--color-background-secondary)]" />
                </div>
              ) : displayText ? (
                canManualEdit ? (
                  <ChapterEditor
                    chapterNum={chapter}
                    initialContent={diskContent}
                    readOnly={streaming}
                    onSaved={() => void refetchChapter()}
                  />
                ) : (
                  <div className="font-serif text-[13px] leading-[1.8] whitespace-pre-wrap text-[var(--color-text-primary)]">
                    {displayText}
                    {streaming ? (
                      <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-[var(--color-text-primary)]" />
                    ) : null}
                  </div>
                )
              ) : flow.phase === 'writing' && !gateActive && !needsPreviewDecision ? (
                <p className="text-center text-[13px] text-[var(--color-text-tertiary)]">
                  空白页，随时可以开始
                </p>
              ) : null}
            </div>
          </div>

          {flow.phase === 'writing' && !gateActive && !needsPreviewDecision ? (
            <div className="shrink-0 border-t border-[var(--color-border-tertiary)] px-4 py-3">
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-3">
                {streaming ? (
                  <p className="text-center text-[13px] text-[var(--color-text-tertiary)]">
                    AI 正在写作…
                    <button
                      type="button"
                      className="ml-2 underline"
                      onClick={stop}
                    >
                      取消
                    </button>
                  </p>
                ) : canManualEdit ? (
                  <Button onClick={handleContinue}>继续写</Button>
                ) : !displayText ? (
                  <Button className="w-full" onClick={handleContinue}>
                    继续写
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}

          {showChapterGates ? (
            <div className="shrink-0 border-t border-[var(--color-border-tertiary)] px-4 py-4">
              <div className="mx-auto w-full max-w-lg">
                {(error || flow.error) &&
                (gatesPhase === 'preview_cta' ||
                  gatesPhase === 'precheck_fail' ||
                  flow.phase === 'preview_cta' ||
                  flow.phase === 'precheck_fail') ? (
                  <p className="mb-3 text-center text-[13px] text-[var(--color-danger)]">
                    {error ?? flow.error}
                  </p>
                ) : null}
                <ChapterGates
                  phase={
                    flow.phase === 'revise_preview' || flow.phase === 'revise_input'
                      ? flow.phase
                      : gatesPhase
                  }
                  chapterNum={chapter}
                  handlers={gateHandlers}
                />
              </div>
            </div>
          ) : null}

          {flow.phase === 'chapter_done' &&
          workQueue?.rhythm_warning?.warning ? (
            <p className="mx-auto max-w-lg px-4 pb-3 text-center text-[11px] text-[var(--color-warning-text)]">
              {workQueue.rhythm_warning.message}
            </p>
          ) : null}

          {(error || flow.error) && flow.phase === 'writing' ? (
            <p className="mx-auto max-w-lg px-4 pb-3 text-center text-[13px] text-[var(--color-danger)]">
              {error ?? flow.error}
            </p>
          ) : null}
        </section>
      </div>

      {showArchives && showFilesDrawer ? (
        <BookFilesDrawer
          bookTitle={title}
          mode={filesDrawerMode}
          onClose={() => setShowArchives(false)}
        />
      ) : null}

      {(showDiagnosis || flow.phase === 'rules_drawer') &&
      (flow.review?.log_id || flow.attributionLogId || flow.diagnosisId) ? (
        <AttributionRulesDrawer
          qualityLogId={
            flow.review?.log_id ?? flow.attributionLogId ?? undefined
          }
          diagnosisId={flow.diagnosisId ?? undefined}
          chapterNum={chapter}
          onClose={() => {
            setShowDiagnosis(false)
            flow.closeRulesDrawer()
          }}
          onDone={async (opts) => {
            setShowDiagnosis(false)
            flow.resetToWriting()
            reset()
            await qc.invalidateQueries({ queryKey: ['plan'] })
            await qc.invalidateQueries({ queryKey: ['chapter', chapter] })
            if (opts?.executedRerun) {
              handleContinue()
            }
          }}
        />
      ) : null}
    </div>
  )
}
