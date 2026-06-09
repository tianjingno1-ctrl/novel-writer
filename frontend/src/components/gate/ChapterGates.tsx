import { useState } from 'react'

import type { ChapterFlowPhase } from '@/hooks/useChapterFlow'
import { GateOverlay } from '@/components/gate/GateOverlay'
import { Button } from '@/components/ui/button'
import type { ResolvedCriteria } from '@/types/api'

const ISSUE_TAG_OPTIONS = [
  { id: 'hook_weak', label: '钩子弱' },
  { id: 'ai_tone', label: 'AI 腔' },
  { id: 'pacing_fast', label: '节奏太快' },
  { id: 'pacing_slow', label: '节奏太慢' },
  { id: 'emotion_shallow', label: '情感浅' },
  { id: 'logic_gap', label: '逻辑断层' },
] as const

type FlowHandlers = {
  busy: boolean
  passLines: string[]
  topNote: string
  resolvedCriteria?: ResolvedCriteria
  highlightDraft: string
  issueTags: string[]
  precheckFailMessage: string
  summaryText: string
  reviseOriginal: string
  reviseDraft: string
  onAcceptReview: () => void
  onRejectReview: () => void
  onSkipHighlights: () => void
  onConfirmHighlight: (text: string) => void
  onToggleIssueTag: (tag: string) => void
  onRewrite: () => void
  onStartRevise: () => void
  onOpenRules: () => void
  onSubmitRevise: (note: string) => void
  onAcceptRevise: () => void
  onConfirmSummary: () => void
  onRegenerateSummary: () => void
  onCloseRules: () => void
  onNextChapter: () => void
}

type Props = {
  phase: ChapterFlowPhase
  chapterNum: number
  handlers: FlowHandlers
}

export function ChapterGates({ phase, chapterNum, handlers }: Props) {
  const [reviseNote, setReviseNote] = useState('')
  const [highlightText, setHighlightText] = useState(handlers.highlightDraft)

  if (phase === 'running') {
    return (
      <div className="fixed inset-x-0 bottom-24 z-30 text-center text-sm text-muted">
        正在检查本章…
      </div>
    )
  }

  if (phase === 'precheck_fail') {
    return (
      <GateOverlay open>
        <h3 className="text-lg font-semibold">还需要再改改</h3>
        <p className="mt-3 text-sm text-muted leading-relaxed">
          {handlers.precheckFailMessage}
        </p>
        <div className="mt-6">
          <Button className="w-full" onClick={handlers.onRewrite}>
            回去改
          </Button>
        </div>
      </GateOverlay>
    )
  }

  if (phase === 'review_gate') {
    const hard = handlers.resolvedCriteria?.hard ?? []
    const soft = handlers.resolvedCriteria?.soft ?? []
    return (
      <GateOverlay open>
        <h3 className="text-lg font-semibold">本章分析</h3>
        <ul className="mt-4 space-y-2 text-sm">
          {handlers.passLines.map((line) => (
            <li key={line} className="text-success">
              ✓ {line}
            </li>
          ))}
          {handlers.topNote ? (
            <li className="text-muted">· {handlers.topNote}</li>
          ) : null}
        </ul>
        {hard.length > 0 || soft.length > 0 ? (
          <div className="mt-4 rounded-lg bg-accent/40 p-3 text-xs text-muted">
            {hard.length > 0 ? (
              <p className="mb-1">
                <span className="font-medium text-foreground">硬性：</span>
                {hard
                  .map((c) => c.label ?? (c as { content?: string }).content ?? c.id)
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            ) : null}
            {soft.length > 0 ? (
              <p>
                <span className="font-medium text-foreground">软性：</span>
                {soft
                  .map((c) => c.label ?? (c as { content?: string }).content ?? c.id)
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            ) : null}
          </div>
        ) : null}
        <div className="mt-6 border-t border-border pt-4">
          <p className="text-center text-sm font-medium">你觉得呢？</p>
          <div className="mt-3 flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              disabled={handlers.busy}
              onClick={handlers.onRejectReview}
            >
              有问题，我来说说
            </Button>
            <Button
              className="flex-1"
              disabled={handlers.busy}
              onClick={handlers.onAcceptReview}
            >
              {handlers.busy ? '处理中…' : '没问题'}
            </Button>
          </div>
        </div>
      </GateOverlay>
    )
  }

  if (phase === 'highlights_gate') {
    return (
      <GateOverlay open className="max-w-lg">
        <h3 className="text-lg font-semibold">记一笔亮点？</h3>
        <p className="mt-2 text-sm text-muted">
          审阅通过的片段可写入口味库，帮助后面几章（可跳过）
        </p>
        <textarea
          className="mt-3 min-h-24 w-full rounded-md border border-border bg-background p-3 text-sm"
          value={highlightText}
          onChange={(e) => setHighlightText(e.target.value)}
          placeholder="例如：开头三句悬念感很强"
        />
        <div className="mt-4 flex gap-2">
          <Button
            variant="outline"
            className="flex-1"
            disabled={handlers.busy}
            onClick={handlers.onSkipHighlights}
          >
            跳过
          </Button>
          <Button
            className="flex-1"
            disabled={handlers.busy}
            onClick={() => handlers.onConfirmHighlight(highlightText)}
          >
            {handlers.busy ? '处理中…' : '记下并继续'}
          </Button>
        </div>
      </GateOverlay>
    )
  }

  if (phase === 'judgment_fork') {
    return (
      <GateOverlay open>
        <h3 className="text-lg font-semibold">怎么处理？</h3>
        <div className="mt-4 space-y-3">
          <button
            type="button"
            className="w-full rounded-xl border border-border bg-accent/50 p-4 text-left transition-colors hover:border-primary/40"
            onClick={handlers.onStartRevise}
          >
            <p className="font-medium">✍️ 改这一章</p>
            <p className="mt-1 text-xs text-muted">告诉我哪里不对</p>
          </button>
          <button
            type="button"
            className="w-full rounded-xl border border-border bg-accent/50 p-4 text-left transition-colors hover:border-primary/40"
            onClick={handlers.onOpenRules}
          >
            <p className="font-medium">🔧 改写作规则</p>
            <p className="mt-1 text-xs text-muted">可能影响后面的章节</p>
          </button>
        </div>
      </GateOverlay>
    )
  }

  if (phase === 'revise_input') {
    return (
      <GateOverlay open className="max-w-lg">
        <h3 className="text-lg font-semibold">你的修改意见</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {ISSUE_TAG_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={`rounded-full border px-3 py-1 text-xs ${
                handlers.issueTags.includes(opt.id)
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-muted'
              }`}
              onClick={() => handlers.onToggleIssueTag(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <textarea
          className="mt-3 min-h-28 w-full rounded-md border border-border bg-background p-3 text-sm"
          placeholder="例如：情感节奏太快，苏瑶的犹豫要更深"
          value={reviseNote}
          onChange={(e) => setReviseNote(e.target.value)}
        />
        <div className="mt-4 flex gap-2">
          <Button
            className="flex-1"
            disabled={handlers.busy || !reviseNote.trim()}
            onClick={() => handlers.onSubmitRevise(reviseNote.trim())}
          >
            {handlers.busy ? '正在改…' : '生成修改版'}
          </Button>
        </div>
      </GateOverlay>
    )
  }

  if (phase === 'revise_preview') {
    return (
      <div className="fixed inset-0 z-50 flex flex-col bg-background">
        <header className="border-b border-border px-4 py-3 text-sm font-medium">
          对比修改
        </header>
        <div className="grid flex-1 gap-0 overflow-hidden md:grid-cols-2">
          <div className="overflow-auto border-b border-border p-4 md:border-b-0 md:border-r">
            <p className="mb-2 text-xs text-muted">原文</p>
            <pre className="font-serif whitespace-pre-wrap text-sm leading-relaxed">
              {handlers.reviseOriginal}
            </pre>
          </div>
          <div className="overflow-auto p-4">
            <p className="mb-2 text-xs text-muted">修改版</p>
            <pre className="font-serif whitespace-pre-wrap text-sm leading-relaxed">
              {handlers.reviseDraft}
              <span className="inline-block h-4 w-0.5 animate-pulse bg-foreground" />
            </pre>
          </div>
        </div>
        <div className="flex gap-2 border-t border-border p-4">
          <Button
            variant="outline"
            className="flex-1"
            onClick={handlers.onStartRevise}
          >
            重新改
          </Button>
          <Button
            className="flex-1"
            disabled={handlers.busy}
            onClick={handlers.onAcceptRevise}
          >
            用这个版本
          </Button>
        </div>
      </div>
    )
  }

  if (phase === 'rules_drawer') {
    return null
  }

  if (phase === 'summary_gate') {
    return (
      <GateOverlay open>
        <h3 className="text-lg font-semibold">第 {chapterNum} 章写完了 🎉</h3>
        <p className="mt-2 text-sm text-muted">自动生成了一句概述：</p>
        <p className="mt-3 rounded-lg bg-accent/60 p-3 font-serif text-sm leading-relaxed">
          「{handlers.summaryText || '（概述生成中，可稍后确认）'}」
        </p>
        <div className="mt-6 flex gap-2">
          <Button
            variant="outline"
            className="flex-1"
            disabled={handlers.busy}
            onClick={handlers.onRegenerateSummary}
          >
            换一句
          </Button>
          <Button
            className="flex-1"
            disabled={handlers.busy}
            onClick={handlers.onConfirmSummary}
          >
            就这句
          </Button>
        </div>
      </GateOverlay>
    )
  }

  if (phase === 'chapter_done') {
    return (
      <GateOverlay open>
        <h3 className="text-lg font-semibold">本章已完成</h3>
        <p className="mt-2 text-sm text-muted">概述已确认，可以写下一章了。</p>
        <Button className="mt-6 w-full" onClick={handlers.onNextChapter}>
          写下一章
        </Button>
      </GateOverlay>
    )
  }

  return null
}
