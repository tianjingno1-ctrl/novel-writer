import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { fetchChapterReview } from '@/api/productApi'
import type { ChapterFlowPhase } from '@/hooks/useChapterFlow'
import type { HighlightConflict, RhythmWarning } from '@/hooks/useChapterFlow'
import { PrecheckIssuesPanel } from '@/components/gate/PrecheckIssuesPanel'
import { GatePanel } from '@/components/gate/GatePanel'
import type { PrecheckResult } from '@/api/chapterFlow'
import { Button } from '@/components/ui/button'
import type { ResolvedCriteria } from '@/types/api'
import { criterionKey, criterionLabel } from '@/lib/reviewCriteria'
import { filterOpenGaps } from '@/lib/gapFilter'
import { splitPrecheckIssues } from '@/lib/precheckIssues'

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
  regenerating?: boolean
  passLines: string[]
  topNote: string
  reviewProfileLabel?: string
  resolvedCriteria?: ResolvedCriteria
  highlightDraft: string
  highlightConflicts?: HighlightConflict[]
  rhythmWarning?: RhythmWarning | null
  l5bMandatory?: boolean
  issueTags: string[]
  precheckFailMessage: string
  precheck?: PrecheckResult | null
  summaryText: string
  reviseOriginal: string
  reviseDraft: string
  revisePrefillNote?: string
  onAcceptReview: () => void
  onRejectReview: () => void
  onAttributionFromReview?: () => void
  onSkipHighlights: () => void
  onConfirmHighlight: (text: string, force?: boolean) => void
  onDismissRhythm?: () => void
  onAttributionFromRhythm?: () => void
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
  onAdoptPreview?: () => void
  onRewritePreview?: () => void
  onReviseFromCriteria?: () => void
  onAcceptJudgment?: () => void
  canSkipPaywallIntent?: boolean
  onSkipPaywallIntent?: () => void
}

type Props = {
  phase: ChapterFlowPhase
  chapterNum: number
  handlers: FlowHandlers
}

const JUDGMENT_LABEL: Record<string, string> = {
  pass: '已通过',
  fail: '未通过',
  pending: '待判定',
}

export function ChapterGates({ phase, chapterNum, handlers }: Props) {
  const [reviseNote, setReviseNote] = useState('')
  const { data: reviewData } = useQuery({
    queryKey: ['chapter', chapterNum, 'review'],
    queryFn: () => fetchChapterReview(chapterNum),
    enabled: phase === 'review_gate' && chapterNum > 0,
  })
  const reviewRounds = reviewData?.review?.rounds ?? []
  const [highlightText, setHighlightText] = useState(handlers.highlightDraft)
  const [ruleChecks, setRuleChecks] = useState<Record<string, boolean>>({})

  useEffect(() => {
    setHighlightText(handlers.highlightDraft)
  }, [handlers.highlightDraft])

  useEffect(() => {
    if (phase === 'revise_input' && handlers.revisePrefillNote) {
      setReviseNote(handlers.revisePrefillNote)
    }
  }, [phase, handlers.revisePrefillNote])

  useEffect(() => {
    if (phase !== 'review_gate') return
    const hard = handlers.resolvedCriteria?.hard ?? []
    const soft = handlers.resolvedCriteria?.soft ?? []
    const latest = reviewRounds[reviewRounds.length - 1]
    const openGaps = filterOpenGaps(latest?.gaps ?? [])
    const openHardRefs = new Set(
      openGaps
        .filter((g) => g.severity === 'hard')
        .map((g) => g.rule_ref)
        .filter(Boolean),
    )
    const openSoftRefs = new Set(
      openGaps
        .filter((g) => g.severity !== 'hard')
        .map((g) => g.rule_ref)
        .filter(Boolean),
    )
    const next: Record<string, boolean> = {}
    hard.forEach((c, i) => {
      const ref = String(c.ref ?? '')
      const key = criterionKey(c, 'hard', i)
      if (ref && !openHardRefs.has(ref)) next[key] = true
    })
    if (openHardRefs.size === 0) {
      soft.forEach((c, i) => {
        const ref = String(c.ref ?? '')
        const key = criterionKey(c, 'soft', i)
        if (ref && !openSoftRefs.has(ref)) next[key] = true
      })
    }
    setRuleChecks(next)
  }, [phase, reviewRounds, handlers.resolvedCriteria])

  if (phase === 'writing') {
    return null
  }

  if (phase === 'running' || phase === 'regenerating') {
    return (
      <GatePanel>
        <p className="text-center text-[13px] text-[var(--color-text-tertiary)] animate-pulse">
          {phase === 'regenerating'
            ? '正在重新生成本章…'
            : 'AI 正在检查…'}
        </p>
      </GatePanel>
    )
  }

  if (phase === 'preview_cta') {
    return (
      <GatePanel>
        <h3 className="text-[13px] font-medium">预览，是否采纳？</h3>
        <p className="mt-2 text-[13px] text-[var(--color-text-secondary)]">
          上方为 AI 生成本章正文。通读后可采纳进入审阅，或整章重新生成（覆盖旧稿）。
        </p>
        <div className="mt-4 flex gap-2">
          <Button
            variant="outline"
            className="flex-1"
            disabled={handlers.regenerating || handlers.busy}
            onClick={handlers.onRewritePreview}
          >
            整章重新生成
          </Button>
          <Button
            className="flex-1"
            disabled={handlers.busy || handlers.regenerating}
            onClick={handlers.onAdoptPreview}
          >
            {handlers.busy ? '检查中…' : '采纳'}
          </Button>
        </div>
      </GatePanel>
    )
  }

  if (phase === 'precheck_fail') {
    return (
      <GatePanel>
        <h3 className="text-[13px] font-medium">自动检查未通过</h3>
        <p className="mt-2 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {handlers.precheckFailMessage}
        </p>
        {handlers.precheck ? (
          <PrecheckIssuesPanel result={handlers.precheck} />
        ) : null}
        <div className="mt-4 space-y-2">
          {handlers.canSkipPaywallIntent && handlers.onSkipPaywallIntent ? (
            <Button
              variant="outline"
              className="w-full"
              disabled={handlers.busy}
              onClick={handlers.onSkipPaywallIntent}
            >
              {handlers.busy ? '处理中…' : '跳过「付费前心理状态」，继续'}
            </Button>
          ) : null}
          <Button className="w-full" disabled={handlers.regenerating} onClick={handlers.onRewrite}>
            整章重新生成
          </Button>
        </div>
      </GatePanel>
    )
  }

  if (phase === 'review_gate') {
    const precheckSoft = handlers.precheck
      ? splitPrecheckIssues(handlers.precheck).soft
      : []
    const hard = handlers.resolvedCriteria?.hard ?? []
    const soft = handlers.resolvedCriteria?.soft ?? []
    const hardKeys = hard.map((c, i) => criterionKey(c, 'hard', i))
    const allHardChecked =
      hardKeys.length === 0 || hardKeys.every((key) => ruleChecks[key])
    const latestRound = reviewRounds[reviewRounds.length - 1]
    const openGaps = filterOpenGaps(latestRound?.gaps ?? [])
    const openHardGaps = openGaps.filter((g) => g.severity === 'hard')

    const toggleRule = (key: string) => {
      setRuleChecks((prev) => ({ ...prev, [key]: !prev[key] }))
    }

    return (
      <GatePanel>
        <h3 className="text-[13px] font-medium">质量审阅</h3>
        {handlers.reviewProfileLabel ? (
          <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
            审阅标准：{handlers.reviewProfileLabel}
          </p>
        ) : null}
        <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-text-tertiary)]">
          下方勾选表示你确认本章已满足对应标准；AI 审阅仅供参考，不必等报告「全部通过」。
        </p>
        <ul className="mt-3 space-y-1 text-[13px]">
          {handlers.passLines.map((line) => (
            <li key={line} className="text-[var(--color-success)]">
              ✓ {line}
            </li>
          ))}
        </ul>

        {hard.length > 0 ? (
          <div className="mt-3 space-y-2">
            <p className="text-[11px] font-medium text-[var(--color-danger)]">必须</p>
            <ul className="space-y-2">
              {hard.map((c, i) => {
                const key = hardKeys[i]
                return (
                  <li key={key}>
                    <label className="flex cursor-pointer items-start gap-2 text-[13px]">
                      <input
                        type="checkbox"
                        className="mt-0.5 shrink-0"
                        checked={Boolean(ruleChecks[key])}
                        onChange={() => toggleRule(key)}
                      />
                      <span>{criterionLabel(c)}</span>
                    </label>
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}

        {soft.length > 0 ? (
          <div className="mt-3 space-y-2">
            <p className="text-[11px] font-medium text-[var(--color-text-tertiary)]">
              建议
            </p>
            <ul className="space-y-2">
              {soft.map((c, i) => {
                const key = criterionKey(c, 'soft', i)
                return (
                  <li key={key}>
                    <label className="flex cursor-pointer items-start gap-2 text-[13px] text-[var(--color-text-secondary)]">
                      <input
                        type="checkbox"
                        className="mt-0.5 shrink-0"
                        checked={Boolean(ruleChecks[key])}
                        onChange={() => toggleRule(key)}
                      />
                      <span>{criterionLabel(c)}</span>
                    </label>
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}

        {precheckSoft.length > 0 && handlers.precheck ? (
          <div className="mt-3 rounded-[var(--border-radius-md)] border border-[var(--color-warning)]/25 bg-[var(--color-warning-bg)] px-2 py-2">
            <p className="text-[11px] font-medium text-[var(--color-warning-text)]">
              机器预检建议（{precheckSoft.length}，不阻断审阅）
            </p>
            <PrecheckIssuesPanel result={handlers.precheck} mode="soft" />
          </div>
        ) : null}

        {openHardGaps.length > 0 ? (
          <div className="mt-3 rounded-[var(--border-radius-md)] border border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5 px-2 py-2">
            <p className="text-[11px] font-medium text-[var(--color-danger)]">
              本轮待改进（必须）
            </p>
            <ul className="mt-1 space-y-1 text-[12px] text-[var(--color-text-secondary)]">
              {openHardGaps.map((g) => (
                <li key={g.rule_ref ?? g.description}>
                  · {g.description ?? g.rule_ref}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="mt-3 text-[11px] text-[var(--color-success)]">
            AI 未检出必须项差距，勾选确认后可进入下一步
          </p>
        )}

        {handlers.topNote ? (
          <div className="ai-note mt-3">
            AI 建议：{handlers.topNote}
          </div>
        ) : null}

        {reviewRounds.length > 0 ? (
          <div className="mt-3 rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] p-2">
            <p className="text-[11px] font-medium text-[var(--color-text-tertiary)]">
              审阅记录（{reviewRounds.length} 轮）
            </p>
            <ul className="mt-1 max-h-24 space-y-1 overflow-auto text-[11px]">
              {[...reviewRounds].reverse().slice(0, 3).map((r) => {
                const roundOpenGaps = filterOpenGaps(r.gaps)
                return (
                <li key={`${r.round}-${r.quality_log_id}`} className="text-[var(--color-text-secondary)]">
                  第 {r.round} 轮 ·{' '}
                  {JUDGMENT_LABEL[r.judgment ?? ''] ?? r.judgment ?? '—'}
                  {roundOpenGaps.length > 0 ? (
                    <span className="text-[var(--color-text-tertiary)]">
                      {' '}
                      · {roundOpenGaps.length} 项差距
                    </span>
                  ) : null}
                  {roundOpenGaps.slice(0, 2).map((g) => (
                    <span
                      key={`${r.round}-${g.rule_ref}`}
                      className="block truncate text-[var(--color-text-tertiary)]"
                    >
                      {g.severity === 'hard' ? '必须' : '建议'} ·{' '}
                      {g.description ?? g.rule_ref}
                    </span>
                  ))}
                  {!roundOpenGaps.length && r.review_excerpt ? (
                    <span className="block truncate text-[var(--color-text-tertiary)]">
                      {r.review_excerpt.slice(0, 80)}
                    </span>
                  ) : null}
                </li>
                )
              })}
            </ul>
          </div>
        ) : null}

        <div className="mt-4 flex flex-col gap-2 border-t border-[var(--color-border-tertiary)] pt-4">
          {handlers.onReviseFromCriteria ? (
            <Button
              variant="outline"
              className="w-full"
              disabled={handlers.busy}
              onClick={handlers.onReviseFromCriteria}
            >
              {handlers.busy ? '正在改稿…' : '按审阅标准改稿'}
            </Button>
          ) : null}
          <div className="flex gap-2">
            <Button
              variant="dangerOutline"
              className="flex-1"
              disabled={handlers.busy}
              onClick={handlers.onRejectReview}
            >
              有问题，改稿
            </Button>
            <Button
              className="flex-1"
              disabled={handlers.busy || !allHardChecked}
              onClick={handlers.onAcceptReview}
            >
              {handlers.busy ? '处理中…' : '通过，进入下一步 →'}
            </Button>
          </div>
        </div>
        {handlers.onAttributionFromReview ? (
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 w-full text-[11px] text-[var(--color-text-tertiary)]"
            disabled={handlers.busy}
            onClick={handlers.onAttributionFromReview}
          >
            差距异常，查看诊断
          </Button>
        ) : null}
      </GatePanel>
    )
  }

  if (phase === 'highlights_gate') {
    return (
      <GatePanel>
        <h3 className="text-[13px] font-medium">本章亮点</h3>
        <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
          审阅通过的片段可写入写作偏好（可跳过）
        </p>
        <textarea
          className="mt-3 min-h-24 w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-primary)] p-3 text-[13px] outline-none"
          value={highlightText}
          onChange={(e) => setHighlightText(e.target.value)}
          placeholder="例如：开头三句悬念感很强"
        />
        {(handlers.highlightConflicts ?? []).length > 0 ? (
          <div className="ai-warn mt-3">
            <p className="font-medium">与已有规则冲突</p>
            <ul className="mt-1 list-inside list-disc text-[11px]">
              {(handlers.highlightConflicts ?? []).map((c, i) => (
                <li key={i}>{c.message ?? c.ref}</li>
              ))}
            </ul>
            <Button
              size="sm"
              variant="outline"
              className="mt-2"
              disabled={handlers.busy}
              onClick={() => handlers.onConfirmHighlight(highlightText, true)}
            >
              仍要写入
            </Button>
          </div>
        ) : null}
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
            {handlers.busy ? '处理中…' : '写入偏好'}
          </Button>
        </div>
      </GatePanel>
    )
  }

  if (phase === 'rhythm_gate') {
    const msg =
      handlers.rhythmWarning?.message ??
      '近几章弃文风险偏高，建议检查节拍'
    const blockSkip = Boolean(handlers.l5bMandatory && handlers.rhythmWarning?.warning)
    return (
      <GatePanel>
        <h3 className="text-[13px] font-medium">节奏提醒</h3>
        <p className="mt-2 text-[13px] text-[var(--color-warning-text)]">{msg}</p>
        {blockSkip ? (
          <p className="mt-2 text-[11px] text-[var(--color-text-tertiary)]">
            本章叙事角色为高风险档，节奏预警不可直接跳过。请改章或进入归因后再继续。
          </p>
        ) : null}
        <div className="mt-4 space-y-2">
          {blockSkip ? (
            <>
              <Button
                className="w-full"
                disabled={handlers.busy}
                onClick={handlers.onStartRevise}
              >
                改本章
              </Button>
              {handlers.onAttributionFromRhythm ? (
                <Button
                  variant="outline"
                  className="w-full"
                  disabled={handlers.busy}
                  onClick={handlers.onAttributionFromRhythm}
                >
                  进入归因
                </Button>
              ) : null}
            </>
          ) : (
            <>
              <Button
                className="w-full"
                disabled={handlers.busy}
                onClick={handlers.onDismissRhythm}
              >
                {handlers.busy ? '处理中…' : '继续'}
              </Button>
              {handlers.onAttributionFromRhythm ? (
                <Button
                  variant="outline"
                  className="w-full"
                  disabled={handlers.busy}
                  onClick={handlers.onAttributionFromRhythm}
                >
                  查看诊断
                </Button>
              ) : null}
            </>
          )}
        </div>
      </GatePanel>
    )
  }

  if (phase === 'judgment_fork') {
    return (
      <GatePanel>
        <h3 className="text-[13px] font-medium">通过还是修改？</h3>
        <div className="mt-3 space-y-2">
          <button
            type="button"
            className="w-full rounded-[var(--border-radius-lg)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-secondary)] p-3 text-left hover:border-[var(--color-primary)]/40"
            onClick={handlers.onAcceptJudgment}
          >
            <p className="text-[13px] font-medium">通过</p>
          </button>
          <button
            type="button"
            className="w-full rounded-[var(--border-radius-lg)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-secondary)] p-3 text-left hover:border-[var(--color-primary)]/40"
            onClick={handlers.onStartRevise}
          >
            <p className="text-[13px] font-medium">改本章</p>
            <p className="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">
              说明哪里不对
            </p>
          </button>
          <button
            type="button"
            className="w-full rounded-[var(--border-radius-lg)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-secondary)] p-3 text-left hover:border-[var(--color-primary)]/40"
            onClick={handlers.onOpenRules}
          >
            <p className="text-[13px] font-medium">改规则</p>
            <p className="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">
              可能影响后面的章节
            </p>
          </button>
        </div>
      </GatePanel>
    )
  }

  if (phase === 'revise_input') {
    return (
      <GatePanel>
        <h3 className="text-[13px] font-medium">说明改哪里</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {ISSUE_TAG_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={`rounded-full border px-3 py-1 text-[11px] ${
                handlers.issueTags.includes(opt.id)
                  ? 'border-[var(--color-primary)] bg-[var(--color-background-primary)] text-[var(--color-primary)]'
                  : 'border-[var(--color-border-secondary)] text-[var(--color-text-tertiary)]'
              }`}
              onClick={() => handlers.onToggleIssueTag(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <textarea
          className="mt-3 min-h-28 w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] p-3 text-[13px] outline-none"
          placeholder="例如：情感节奏太快，苏瑶的犹豫要更深"
          value={reviseNote}
          onChange={(e) => setReviseNote(e.target.value)}
        />
        <Button
          className="mt-4 w-full"
          disabled={handlers.busy || !reviseNote.trim()}
          onClick={() => handlers.onSubmitRevise(reviseNote.trim())}
        >
          {handlers.busy ? '正在改…' : '生成修改版'}
        </Button>
      </GatePanel>
    )
  }

  if (phase === 'revise_preview') {
    return (
      <div className="fixed inset-0 z-50 flex flex-col bg-[var(--color-background-primary)] pl-[var(--sidebar-width)]">
        <header className="flex h-[var(--topbar-height)] items-center border-b border-[var(--color-border-tertiary)] px-4 text-[13px] font-medium">
          对比修改
        </header>
        <div className="grid flex-1 gap-0 overflow-hidden md:grid-cols-2">
          <div className="overflow-auto border-b border-[var(--color-border-tertiary)] p-4 md:border-b-0 md:border-r">
            <p className="mb-2 text-[11px] text-[var(--color-text-tertiary)]">原文</p>
            <pre className="font-serif whitespace-pre-wrap text-[13px] leading-relaxed">
              {handlers.reviseOriginal}
            </pre>
          </div>
          <div className="overflow-auto p-4">
            <p className="mb-2 text-[11px] text-[var(--color-text-tertiary)]">修改版</p>
            <pre className="font-serif whitespace-pre-wrap text-[13px] leading-relaxed">
              {handlers.reviseDraft}
              <span className="inline-block h-4 w-0.5 animate-pulse bg-[var(--color-text-primary)]" />
            </pre>
          </div>
        </div>
        <div className="flex gap-2 border-t border-[var(--color-border-tertiary)] p-4">
          <Button variant="outline" className="flex-1" onClick={handlers.onStartRevise}>
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
      <GatePanel>
        <h3 className="text-[13px] font-medium">确认本章摘要</h3>
        <p className="mt-3 rounded-[var(--border-radius-md)] bg-[var(--color-background-secondary)] p-3 font-serif text-[13px] leading-relaxed">
          「{handlers.summaryText || '（概述生成中，可稍后确认）'}」
        </p>
        <div className="mt-4 flex gap-2">
          <Button
            variant="outline"
            className="flex-1"
            disabled={handlers.busy}
            onClick={handlers.onRegenerateSummary}
          >
            重新生成
          </Button>
          <Button
            className="flex-1"
            disabled={handlers.busy}
            onClick={handlers.onConfirmSummary}
          >
            确认
          </Button>
        </div>
      </GatePanel>
    )
  }

  if (phase === 'chapter_done') {
    return (
      <GatePanel className="border-[var(--color-primary)]/25">
        <h3 className="text-[13px] font-medium text-[var(--color-primary)]">
          第 {chapterNum} 章完成！
        </h3>
        <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
          概述已确认，可以写下一章了。
        </p>
        <Button className="mt-4 w-full" onClick={handlers.onNextChapter}>
          写下一章
        </Button>
      </GatePanel>
    )
  }

  return null
}
