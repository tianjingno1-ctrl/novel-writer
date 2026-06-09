import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { MoreHorizontal } from 'lucide-react'

import { fetchChapter, fetchPlanProduct, fetchReaderPreview } from '@/api/productApi'
import { fetchStatus, fetchWorkQueue } from '@/api/endpoints'
import { AttributionRulesDrawer } from '@/components/gate/AttributionRulesDrawer'
import { ChapterGates } from '@/components/gate/ChapterGates'
import { ChapterEditor } from '@/components/writing/ChapterEditor'
import { PreviewReaderTab } from '@/components/writing/PreviewReaderTab'
import { Button } from '@/components/ui/button'
import { useChapterFlow } from '@/hooks/useChapterFlow'
import { useSSEStream } from '@/hooks/useSSEStream'
import { useBookStore } from '@/stores/bookStore'
import { useUiStore } from '@/stores/uiStore'

function countChars(text: string) {
  return text.replace(/\s/g, '').length
}

export function FlowCanvas() {
  const qc = useQueryClient()
  const writeChapterNum = useBookStore((s) => s.writeChapterNum)
  const setShellMode = useUiStore((s) => s.setShellMode)
  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
  })

  const chapter = writeChapterNum ?? status?.write_chapter_num ?? 1
  const flow = useChapterFlow(chapter)
  const [previewTab, setPreviewTab] = useState<'edit' | 'reader'>('edit')

  const { data: chapterData, refetch: refetchChapter } = useQuery({
    queryKey: ['chapter', chapter],
    queryFn: () => fetchChapter(chapter),
  })
  const { data: planProduct } = useQuery({
    queryKey: ['plan', 'product'],
    queryFn: fetchPlanProduct,
  })

  const { streaming, text, error, lastEvent, start, stop, reset } =
    useSSEStream()

  const diskContent = chapterData?.content ?? ''
  const displayText = text || (streaming ? '' : diskContent)
  const charCount = countChars(displayText)
  const streamDone = lastEvent?.type === 'done'
  const showActionBar =
    flow.phase === 'preview_cta' && streamDone && displayText.length > 0

  const { data: readerData, isFetching: readerLoading } = useQuery({
    queryKey: ['reader-preview', chapter, displayText.slice(0, 200)],
    queryFn: async () => {
      const r = await fetchReaderPreview(chapter, displayText)
      return r.reader_preview ?? null
    },
    enabled: showActionBar,
  })

  const { data: workQueue } = useQuery({
    queryKey: ['flow', 'work-queue'],
    queryFn: fetchWorkQueue,
    enabled: flow.phase === 'chapter_done',
  })
  const isFlowWriting = flow.phase === 'writing' && !streaming && !text

  const gateActive =
    flow.phase !== 'writing' &&
    flow.phase !== 'preview_cta' &&
    flow.phase !== 'revise_preview' &&
    flow.phase !== 'rules_drawer'

  useEffect(() => {
    if (flow.phase === 'revise_preview' || flow.phase === 'rules_drawer') {
      setShellMode('gate')
    } else if (gateActive || showActionBar) {
      setShellMode(gateActive ? 'gate' : 'flow')
    } else {
      setShellMode('flow')
    }
    return () => setShellMode('default')
  }, [flow.phase, gateActive, showActionBar, setShellMode])

  useEffect(() => {
    if (streamDone && lastEvent?.type === 'done') {
      flow.onStreamDone(Boolean(lastEvent.chapter_saved))
      void refetchChapter()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamDone, lastEvent])

  const handleContinue = () => {
    flow.resetToWriting()
    void start('/api/chat/stream', {
      instruction: '续写本章',
      chapter_num: chapter,
    })
  }

  const title = status?.project_title || '未命名'

  return (
    <div className="relative flex min-h-screen flex-col bg-background">
      <header className="flex items-center justify-between px-6 py-4">
        <div>
          <p className="text-sm text-muted">{title}</p>
          <p className="font-serif text-lg text-foreground">第 {chapter} 章</p>
        </div>
        <button
          type="button"
          className="rounded-md p-2 text-muted hover:bg-accent"
          aria-label="更多"
        >
          <MoreHorizontal className="h-5 w-5" />
        </button>
      </header>

      <article
        className={`flex-1 px-6 pb-32 pt-4 transition-opacity ${
          gateActive ? 'opacity-40' : ''
        }`}
      >
        {isFlowWriting && diskContent && !text ? (
          <div className="mx-auto max-w-prose">
            <ChapterEditor
              chapterNum={chapter}
              initialContent={diskContent}
              readOnly={streaming}
              onSaved={() => void refetchChapter()}
            />
            <Button className="mt-6" size="lg" onClick={handleContinue}>
              继续写
            </Button>
          </div>
        ) : displayText ? (
          <div className="mx-auto max-w-prose">
            <div className="font-serif text-lg leading-[2] text-foreground whitespace-pre-wrap">
              {displayText}
              {streaming ? (
                <span className="ml-0.5 inline-block h-5 w-0.5 animate-pulse bg-foreground" />
              ) : null}
            </div>
          </div>
        ) : (
          <div className="flex h-full min-h-[50vh] flex-col items-center justify-center gap-4 text-center">
            <p className="font-serif text-muted">空白页，随时可以开始</p>
            <Button size="lg" onClick={handleContinue} disabled={streaming}>
              {streaming ? '正在写…' : '继续写'}
            </Button>
          </div>
        )}
      </article>

      {charCount > 0 && !gateActive && flow.phase !== 'rules_drawer' ? (
        <p className="fixed bottom-6 right-6 font-mono text-xs text-muted">
          {charCount.toLocaleString()} 字
        </p>
      ) : null}

      {showActionBar ? (
        <div className="fixed inset-x-0 bottom-6 z-30 px-4">
          <div className="mx-auto max-w-md rounded-xl border border-border bg-surface/95 px-5 py-4 shadow-lg backdrop-blur-sm">
            <div className="mb-3 flex gap-2 border-b border-border pb-2 text-sm">
              <button
                type="button"
                className={
                  previewTab === 'edit'
                    ? 'font-medium text-foreground'
                    : 'text-muted'
                }
                onClick={() => setPreviewTab('edit')}
              >
                编辑视角
              </button>
              <button
                type="button"
                className={
                  previewTab === 'reader'
                    ? 'font-medium text-foreground'
                    : 'text-muted'
                }
                onClick={() => setPreviewTab('reader')}
              >
                读者视角
              </button>
            </div>
            {previewTab === 'edit' ? (
              <p className="text-center text-sm text-foreground">
                读一读，觉得可以吗？
              </p>
            ) : (
              <PreviewReaderTab reader={readerData} loading={readerLoading} />
            )}
            <div className="mt-3 flex justify-center gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  reset()
                  handleContinue()
                }}
              >
                重写
              </Button>
              <Button
                disabled={flow.busy}
                onClick={() => void flow.continueAfterPreview(displayText)}
              >
                {flow.busy ? '检查中…' : '可以，继续'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {flow.phase === 'chapter_done' && workQueue?.rhythm_warning?.warning ? (
        <div className="fixed inset-x-4 bottom-28 z-30 mx-auto max-w-md rounded-lg border border-warning/40 bg-warning/10 p-3 text-center text-xs text-warning">
          {workQueue.rhythm_warning.message}
        </div>
      ) : null}

      {(error || flow.error) && flow.phase === 'writing' ? (
        <p className="fixed bottom-20 inset-x-4 text-center text-sm text-danger">
          {error ?? flow.error}
        </p>
      ) : null}

      {flow.phase === 'rules_drawer' && flow.review?.log_id ? (
        <AttributionRulesDrawer
          qualityLogId={flow.review.log_id}
          chapterNum={chapter}
          onClose={flow.closeRulesDrawer}
          onDone={() => {
            flow.resetToWriting()
            reset()
            void qc.invalidateQueries({ queryKey: ['plan'] })
            void qc.invalidateQueries({ queryKey: ['chapter', chapter] })
          }}
        />
      ) : null}

      <ChapterGates
        phase={flow.phase}
        chapterNum={chapter}
        handlers={{
          busy: flow.busy,
          passLines: flow.passLines,
          topNote: flow.topNote,
          resolvedCriteria: planProduct?.resolved_criteria,
          highlightDraft: flow.highlightDraft,
          issueTags: flow.issueTags,
          precheckFailMessage: flow.precheckFailMessage,
          summaryText: flow.summaryText,
          reviseOriginal: flow.reviseOriginal,
          reviseDraft: flow.reviseDraft,
          onAcceptReview: () => void flow.acceptReview(),
          onRejectReview: flow.openJudgmentFork,
          onSkipHighlights: () => void flow.skipHighlights(),
          onConfirmHighlight: (text) => void flow.confirmHighlight(text),
          onToggleIssueTag: flow.toggleIssueTag,
          onRewrite: () => {
            flow.resetToWriting()
            reset()
            handleContinue()
          },
          onStartRevise: () => void flow.startReviseChapter(),
          onOpenRules: () => void flow.openRulesDrawer(),
          onSubmitRevise: (note) => void flow.submitRevise(note),
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
        }}
      />

      {streaming ? (
        <button
          type="button"
          className="fixed bottom-16 left-1/2 z-30 -translate-x-1/2 text-xs text-muted underline"
          onClick={stop}
        >
          停止
        </button>
      ) : null}
    </div>
  )
}
