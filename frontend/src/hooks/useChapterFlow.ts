import { useCallback, useState } from 'react'

import { fetchRhythmCheck } from '@/api/productApi'
import {
  acceptFemaleFictionRewrite,
  applyChapterTurn,
  confirmChapterSummary,
  createAttributionLog,
  extractReviseDraft,
  fetchChatHistory,
  finalizeChapter,
  pickTopReviewNote,
  precheckFailMessage,
  precheckPassLines,
  recordJudgment,
  runChapterPrecheck,
  pushChapterHighlight,
  runFemaleFictionReview,
  type PrecheckResult,
  type ReviewResult,
} from '@/api/chapterFlow'
import { fetchChapter, fetchChapterReview } from '@/api/productApi'
import { buildCriteriaReviseNote } from '@/lib/criteriaRevise'
import {
  canSkipPaywallIntentPrecheck,
  countChapterChars,
} from '@/lib/precheckIssues'

const MIN_ADOPTABLE_BODY_CHARS = 80

type PrecheckFailTarget = 'preview' | 'review'

export type HighlightConflict = {
  kind?: string
  message?: string
  ref?: string
}

export type RhythmWarning = {
  warning?: boolean
  message?: string
  chapters?: number[]
}

export type ChapterFlowPhase =
  | 'writing'
  | 'regenerating'
  | 'preview_cta'
  | 'running'
  | 'precheck_fail'
  | 'review_gate'
  | 'highlights_gate'
  | 'rhythm_gate'
  | 'judgment_fork'
  | 'revise_input'
  | 'revise_preview'
  | 'rules_drawer'
  | 'summary_gate'
  | 'chapter_done'

export function useChapterFlow(chapterNum: number, isShortBook = false) {
  const [phase, setPhase] = useState<ChapterFlowPhase>('writing')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [chapterSaved, setChapterSaved] = useState(false)
  const [precheck, setPrecheck] = useState<PrecheckResult | null>(null)
  const [review, setReview] = useState<ReviewResult | null>(null)
  const [topNote, setTopNote] = useState('')
  const [passLines, setPassLines] = useState<string[]>([])
  const [summaryText, setSummaryText] = useState('')
  const [reviseOriginal, setReviseOriginal] = useState('')
  const [reviseDraft, setReviseDraft] = useState('')
  const [highlightDraft, setHighlightDraft] = useState('')
  const [highlightConflicts, setHighlightConflicts] = useState<
    HighlightConflict[]
  >([])
  const [rhythmWarning, setRhythmWarning] = useState<RhythmWarning | null>(
    null,
  )
  const [l5bMandatory, setL5bMandatory] = useState(false)
  const [issueTags, setIssueTags] = useState<string[]>([])
  const [attributionLogId, setAttributionLogId] = useState<string | null>(
    null,
  )
  const [diagnosisId, setDiagnosisId] = useState<string | null>(null)
  const [revisePrefillNote, setRevisePrefillNote] = useState('')
  const [precheckFailTarget, setPrecheckFailTarget] =
    useState<PrecheckFailTarget | null>(null)
  const [precheckContent, setPrecheckContent] = useState('')

  const resetToWriting = useCallback(() => {
    setPhase('writing')
    setError(null)
    setPrecheck(null)
    setReview(null)
    setTopNote('')
    setPassLines([])
    setSummaryText('')
    setReviseOriginal('')
    setReviseDraft('')
    setHighlightDraft('')
    setHighlightConflicts([])
    setRhythmWarning(null)
    setL5bMandatory(false)
    setIssueTags([])
    setAttributionLogId(null)
    setDiagnosisId(null)
    setRevisePrefillNote('')
    setPrecheckFailTarget(null)
    setPrecheckContent('')
    setChapterSaved(false)
  }, [])

  const enterRegenerating = useCallback(() => {
    setPhase('regenerating')
    setError(null)
    setPrecheck(null)
    setReview(null)
    setTopNote('')
    setPassLines([])
    setReviseOriginal('')
    setReviseDraft('')
    setHighlightDraft('')
    setHighlightConflicts([])
    setRhythmWarning(null)
    setL5bMandatory(false)
    setIssueTags([])
    setAttributionLogId(null)
    setDiagnosisId(null)
    setRevisePrefillNote('')
    setPrecheckFailTarget(null)
    setPrecheckContent('')
    setChapterSaved(false)
  }, [])

  const onRegenerateFailed = useCallback(() => {
    setPhase('writing')
  }, [])

  const runPrecheckBeforePreview = useCallback(
    async (streamText: string) => {
      setBusy(true)
      setError(null)
      setPhase('running')
      try {
        const pre = await runChapterPrecheck(
          chapterNum,
          streamText.trim() || '',
        )
        setPrecheck(pre)
        if (!pre.ok) {
          setPrecheckFailTarget('preview')
          setPrecheckContent(streamText.trim() || '')
          setPhase('precheck_fail')
          return
        }
        setPassLines(precheckPassLines(pre))
        setPhase('preview_cta')
      } catch (e) {
        setError(e instanceof Error ? e.message : '预检失败')
        setPhase('writing')
      } finally {
        setBusy(false)
      }
    },
    [chapterNum],
  )

  const onStreamDone = useCallback(
    (saved: boolean, streamText: string) => {
      setChapterSaved(saved)
      void runPrecheckBeforePreview(streamText)
    },
    [runPrecheckBeforePreview],
  )

  const ensureChapterSaved = useCallback(
    async (previewText = ''): Promise<boolean> => {
      if (chapterSaved) {
        return true
      }
      const hist = await fetchChatHistory()
      const messages = hist.messages ?? []
      const appended = new Set(hist.appended_indices ?? [])

      const tryApplyAssistant = async (msgIndex: number): Promise<boolean> => {
        const r = await applyChapterTurn(chapterNum, msgIndex)
        if (!r.ok) {
          setError(r.error ?? '采纳预览失败')
          return false
        }
        setChapterSaved(true)
        return true
      }

      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i]?.role === 'assistant' && !appended.has(i)) {
          return tryApplyAssistant(i)
        }
      }

      // 试跑 / AUTO_APPEND 已写盘，或刷新后会话里无未采纳 turn
      try {
        const ch = await fetchChapter(chapterNum)
        const diskBody = (ch?.content ?? '').replace(/^#[^\n]*\n+/, '').trim()
        const diskChars = countChapterChars(diskBody)
        if (diskChars >= MIN_ADOPTABLE_BODY_CHARS) {
          setChapterSaved(true)
          return true
        }

        const previewChars = countChapterChars(previewText.trim())
        if (
          previewChars >= MIN_ADOPTABLE_BODY_CHARS ||
          messages.some((m) => m.role === 'assistant')
        ) {
          for (let i = messages.length - 1; i >= 0; i--) {
            if (messages[i]?.role === 'assistant') {
              return tryApplyAssistant(i)
            }
          }
        }
      } catch {
        /* fall through */
      }

      setError('没有可采纳的写作预览（正文未写入且无未采纳的 AI 回复）')
      return false
    },
    [chapterNum, chapterSaved],
  )

  const proceedToFinalize = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const fin = await finalizeChapter(chapterNum)
      if (!fin.ok) {
        throw new Error(fin.error ?? '定稿失败')
      }
      const body =
        fin.archive?.summary?.full_text ??
        fin.archive?.summary?.text ??
        ''
      setSummaryText(body.trim())
      const skipSummary =
        Boolean(fin.skipped || fin.summary_skipped || isShortBook)
      if (skipSummary) {
        setPhase('chapter_done')
        return
      }
      setPhase('summary_gate')
    } catch (e) {
      setError(e instanceof Error ? e.message : '定稿失败')
    } finally {
      setBusy(false)
    }
  }, [chapterNum, isShortBook])

  const checkRhythmAndProceed = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await fetchRhythmCheck(chapterNum)
      setL5bMandatory(Boolean(r.l5b_mandatory))
      const warn = r.rhythm_warning
      if (warn?.warning) {
        setRhythmWarning(warn)
        setPhase('rhythm_gate')
        return
      }
      await proceedToFinalize()
    } catch (e) {
      setError(e instanceof Error ? e.message : '节奏检查失败')
    } finally {
      setBusy(false)
    }
  }, [chapterNum, proceedToFinalize])

  const continueAfterPreview = useCallback(
    async (_streamText: string) => {
      setBusy(true)
      setError(null)
      setPhase('running')
      try {
        const saved = await ensureChapterSaved(_streamText)
        if (!saved) {
          setPhase('preview_cta')
          return
        }

        const rev = await runFemaleFictionReview(chapterNum, {
          skip_precheck: true,
        })
        if (!rev.ok) {
          if (rev.precheck && !rev.precheck.ok) {
            setPrecheck(rev.precheck)
            setPrecheckFailTarget('review')
            setPhase('precheck_fail')
            return
          }
          throw new Error(rev.error ?? '审阅失败')
        }
        const pre = await runChapterPrecheck(chapterNum)
        setPrecheck(pre)
        if (!pre.ok) {
          setPrecheckFailTarget('review')
          setReview(rev)
          setTopNote(pickTopReviewNote(rev.reply ?? ''))
          setPhase('precheck_fail')
          return
        }
        setPassLines(precheckPassLines(pre))
        setReview(rev)
        setTopNote(pickTopReviewNote(rev.reply ?? ''))
        setPhase('review_gate')
      } catch (e) {
        setError(e instanceof Error ? e.message : '处理失败')
        setPhase('preview_cta')
      } finally {
        setBusy(false)
      }
    },
    [chapterNum, ensureChapterSaved],
  )

  const skipPaywallIntentAndContinue = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const pre = await runChapterPrecheck(chapterNum, precheckContent, {
        skip_paywall_intent: true,
      })
      setPrecheck(pre)
      if (!pre.ok) {
        setPhase('precheck_fail')
        return
      }
      setPassLines(precheckPassLines(pre))
      if (precheckFailTarget === 'review') {
        if (!review?.log_id) {
          const rev = await runFemaleFictionReview(chapterNum, {
            skip_precheck: true,
            skip_paywall_intent: true,
          })
          if (!rev.ok) {
            throw new Error(rev.error ?? '审阅失败')
          }
          setReview(rev)
          setTopNote(pickTopReviewNote(rev.reply ?? ''))
        }
        setPhase('review_gate')
        return
      }
      setPhase('preview_cta')
    } catch (e) {
      setError(e instanceof Error ? e.message : '跳过检查失败')
    } finally {
      setBusy(false)
    }
  }, [chapterNum, precheckContent, precheckFailTarget, review?.log_id])

  const acceptReview = useCallback(async () => {
    const logId = review?.log_id
    if (!logId) {
      setError('缺少审阅记录')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const j = await recordJudgment(logId, 'accepted')
      if (!j.ok) {
        throw new Error(j.error ?? '记录判断失败')
      }
      const note = pickTopReviewNote(review?.reply ?? '')
      setHighlightDraft(note)
      setHighlightConflicts([])
      setPhase('highlights_gate')
    } catch (e) {
      setError(e instanceof Error ? e.message : '记录判断失败')
    } finally {
      setBusy(false)
    }
  }, [review?.log_id, review?.reply])

  const skipHighlights = useCallback(async () => {
    await checkRhythmAndProceed()
  }, [checkRhythmAndProceed])

  const confirmHighlight = useCallback(
    async (text: string, opts?: { force?: boolean }) => {
      const snippet = text.trim()
      setHighlightConflicts([])
      if (snippet) {
        const pushed = await pushChapterHighlight(chapterNum, {
          text: snippet,
          annotation: '审阅通过亮点',
          skip_conflict_check: opts?.force ?? false,
        })
        if (!pushed.ok) {
          if (pushed.conflicts?.length) {
            setHighlightConflicts(pushed.conflicts)
            setError('亮点与口味库冲突，请修改或确认强制写入')
            return
          }
          throw new Error(pushed.error ?? '写入亮点失败')
        }
      }
      await checkRhythmAndProceed()
    },
    [chapterNum, checkRhythmAndProceed],
  )

  const openJudgmentFork = useCallback(() => {
    setPhase('judgment_fork')
  }, [])

  const dismissJudgmentFork = useCallback(() => {
    setPhase('review_gate')
  }, [])

  const openAttributionFromReview = useCallback(async () => {
    const logId = review?.log_id
    if (logId) {
      await recordJudgment(logId, 'rejected', 'L4a 主动归因').catch(
        () => undefined,
      )
    }
    setPhase('rules_drawer')
  }, [review?.log_id])

  const openAttributionFromRhythm = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      let logId = review?.log_id
      if (!logId) {
        const created = await createAttributionLog(
          chapterNum,
          'L5b',
          rhythmWarning?.message ?? 'L5b 节奏预警归因',
        )
        if (!created.ok || !created.log_id) {
          throw new Error(created.error ?? '创建归因记录失败')
        }
        logId = created.log_id
        setAttributionLogId(logId)
      }
      if (logId) {
        await recordJudgment(logId, 'rejected', 'L5b 节奏预警归因').catch(
          () => undefined,
        )
      }
      setPhase('rules_drawer')
    } catch (e) {
      setError(e instanceof Error ? e.message : '无法进入归因')
    } finally {
      setBusy(false)
    }
  }, [chapterNum, review?.log_id, rhythmWarning?.message])

  const enterAttribution = useCallback(
    (opts: { qualityLogId?: string; diagnosisId?: string }) => {
      if (opts.qualityLogId) {
        setAttributionLogId(opts.qualityLogId)
        setReview({ ok: true, log_id: opts.qualityLogId })
      }
      if (opts.diagnosisId) {
        setDiagnosisId(opts.diagnosisId)
      }
      setPhase('rules_drawer')
    },
    [],
  )

  const dismissRhythmWarning = useCallback(async () => {
    await proceedToFinalize()
  }, [proceedToFinalize])

  const startReviseChapter = useCallback(async () => {
    try {
      const ch = await fetchChapter(chapterNum)
      setReviseOriginal(ch.content ?? '')
      setPhase('revise_input')
    } catch (e) {
      setError(e instanceof Error ? e.message : '读取章节失败')
    }
  }, [chapterNum])

  const enterComplianceRevise = useCallback(
    async (note?: string) => {
      setRevisePrefillNote(note?.trim() ?? '')
      await startReviseChapter()
    },
    [startReviseChapter],
  )

  const toggleIssueTag = useCallback((tag: string) => {
    setIssueTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    )
  }, [])

  const reviseFromCriteria = useCallback(async () => {
    const logId = review?.log_id
    setBusy(true)
    setError(null)
    try {
      const reviewDoc = await fetchChapterReview(chapterNum)
      const rounds = reviewDoc.review?.rounds ?? []
      const round =
        rounds.find((r) => r.quality_log_id === logId) ??
        rounds[rounds.length - 1]
      const reviseNote = buildCriteriaReviseNote({
        gaps: round?.gaps,
        reviewReply: review?.reply,
      })
      if (logId) {
        await recordJudgment(logId, 'needs_revision', '按审阅标准改稿').catch(
          () => undefined,
        )
      }
      const ch = await fetchChapter(chapterNum)
      setReviseOriginal(ch.content ?? '')
      const rev = await runFemaleFictionReview(chapterNum, {
        revise: true,
        skip_precheck: true,
        revise_note: reviseNote,
      })
      if (!rev.ok) {
        throw new Error(rev.error ?? '按审阅标准改稿失败')
      }
      setReviseDraft(extractReviseDraft(rev))
      setReview(rev)
      setPhase('revise_preview')
    } catch (e) {
      setError(e instanceof Error ? e.message : '按审阅标准改稿失败')
    } finally {
      setBusy(false)
    }
  }, [chapterNum, review?.log_id, review?.reply])

  const submitRevise = useCallback(
    async (userNote: string) => {
      const logId = review?.log_id
      if (logId) {
        await recordJudgment(logId, 'needs_revision', userNote, issueTags)
      }
      setBusy(true)
      setError(null)
      try {
        const rev = await runFemaleFictionReview(chapterNum, {
          revise: true,
          skip_precheck: true,
          revise_note: userNote.trim(),
        })
        if (!rev.ok) {
          throw new Error(rev.error ?? '改稿失败')
        }
        setReviseDraft(extractReviseDraft(rev))
        setReview(rev)
        setPhase('revise_preview')
      } catch (e) {
        setError(e instanceof Error ? e.message : '改稿失败')
      } finally {
        setBusy(false)
      }
    },
    [chapterNum, review?.log_id, issueTags],
  )

  const acceptRevise = useCallback(async () => {
    const logId = review?.log_id
    if (!logId) {
      setError('缺少改稿记录')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const acc = await acceptFemaleFictionRewrite(logId)
      if (!acc.ok) {
        throw new Error(acc.error ?? '采纳改稿失败')
      }
      const rev = await runFemaleFictionReview(chapterNum, {
        skip_precheck: true,
      })
      if (!rev.ok) {
        throw new Error(rev.error ?? '审阅失败')
      }
      setReview(rev)
      setTopNote(pickTopReviewNote(rev.reply ?? ''))
      const pre = await runChapterPrecheck(chapterNum)
      setPrecheck(pre)
      setPassLines(precheckPassLines(pre))
      setPhase('review_gate')
    } catch (e) {
      setError(e instanceof Error ? e.message : '采纳改稿失败')
    } finally {
      setBusy(false)
    }
  }, [chapterNum, review?.log_id])

  const regenerateSummary = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const fin = await finalizeChapter(chapterNum)
      const body =
        fin.archive?.summary?.full_text ??
        fin.archive?.summary?.text ??
        ''
      if (body.trim()) {
        setSummaryText(body.trim())
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '重新生成概述失败')
    } finally {
      setBusy(false)
    }
  }, [chapterNum])

  const openRulesDrawer = useCallback(async () => {
    const logId = review?.log_id
    if (logId) {
      await recordJudgment(logId, 'rejected', '用户选择改规则').catch(
        () => undefined,
      )
    }
    setPhase('rules_drawer')
  }, [review?.log_id])

  const closeRulesDrawer = useCallback(() => {
    if (!review?.log_id) {
      setPhase('writing')
      return
    }
    setPhase('judgment_fork')
  }, [review?.log_id])

  const confirmSummary = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await confirmChapterSummary(chapterNum)
      if (!r.ok) {
        throw new Error(r.error ?? '确认概述失败')
      }
      setPhase('chapter_done')
    } catch (e) {
      setError(e instanceof Error ? e.message : '确认概述失败')
    } finally {
      setBusy(false)
    }
  }, [chapterNum])

  return {
    phase,
    busy,
    error,
    setError,
    chapterSaved,
    precheck,
    review,
    topNote,
    passLines,
    summaryText,
    reviseOriginal,
    reviseDraft,
    highlightDraft,
    highlightConflicts,
    rhythmWarning,
    l5bMandatory,
    canSkipPaywallIntent: canSkipPaywallIntentPrecheck(precheck),
    skipPaywallIntentAndContinue,
    attributionLogId,
    diagnosisId,
    revisePrefillNote,
    onStreamDone,
    resetToWriting,
    enterRegenerating,
    onRegenerateFailed,
    continueAfterPreview,
    acceptReview,
    skipHighlights,
    confirmHighlight,
    issueTags,
    toggleIssueTag,
    openJudgmentFork,
    dismissJudgmentFork,
    openAttributionFromReview,
    openAttributionFromRhythm,
    enterAttribution,
    enterComplianceRevise,
    dismissRhythmWarning,
    startReviseChapter,
    reviseFromCriteria,
    submitRevise,
    acceptRevise,
    openRulesDrawer,
    closeRulesDrawer,
    confirmSummary,
    regenerateSummary,
    precheckFailMessage: precheck ? precheckFailMessage(precheck) : '',
  }
}
