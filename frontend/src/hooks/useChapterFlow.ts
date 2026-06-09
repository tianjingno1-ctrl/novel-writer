import { useCallback, useState } from 'react'

import {
  acceptFemaleFictionRewrite,
  applyChapterTurn,
  confirmChapterSummary,
  fetchChapter,
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

export type ChapterFlowPhase =
  | 'writing'
  | 'preview_cta'
  | 'running'
  | 'precheck_fail'
  | 'review_gate'
  | 'highlights_gate'
  | 'judgment_fork'
  | 'revise_input'
  | 'revise_preview'
  | 'rules_drawer'
  | 'summary_gate'
  | 'chapter_done'

export function useChapterFlow(chapterNum: number) {
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
  const [issueTags, setIssueTags] = useState<string[]>([])

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
    setIssueTags([])
    setChapterSaved(false)
  }, [])

  const onStreamDone = useCallback((saved: boolean) => {
    setChapterSaved(saved)
    setPhase('preview_cta')
  }, [])

  const ensureChapterSaved = useCallback(async (): Promise<boolean> => {
    if (chapterSaved) {
      return true
    }
    const hist = await fetchChatHistory()
    const messages = hist.messages ?? []
    const appended = new Set(hist.appended_indices ?? [])
    let msgIndex: number | null = null
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]?.role === 'assistant' && !appended.has(i)) {
        msgIndex = i
        break
      }
    }
    if (msgIndex == null) {
      setError('没有可采纳的写作预览')
      return false
    }
    const r = await applyChapterTurn(chapterNum, msgIndex)
    if (!r.ok) {
      setError('采纳预览失败')
      return false
    }
    setChapterSaved(true)
    return true
  }, [chapterNum, chapterSaved])

  const continueAfterPreview = useCallback(
    async (streamText: string) => {
      setBusy(true)
      setError(null)
      setPhase('running')
      try {
        const saved = await ensureChapterSaved()
        if (!saved) {
          setPhase('preview_cta')
          return
        }

        const pre = await runChapterPrecheck(
          chapterNum,
          streamText.trim() || '',
        )
        setPrecheck(pre)
        if (!pre.ok) {
          setPhase('precheck_fail')
          return
        }

        setPassLines(precheckPassLines(pre))

        const rev = await runFemaleFictionReview(chapterNum, {
          skip_precheck: true,
        })
        if (!rev.ok) {
          if (rev.precheck && !rev.precheck.ok) {
            setPrecheck(rev.precheck)
            setPhase('precheck_fail')
            return
          }
          throw new Error(rev.error ?? '审阅失败')
        }
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
      setPhase('highlights_gate')
    } catch (e) {
      setError(e instanceof Error ? e.message : '记录判断失败')
    } finally {
      setBusy(false)
    }
  }, [chapterNum, review?.log_id, review?.reply])

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
      setPhase('summary_gate')
    } catch (e) {
      setError(e instanceof Error ? e.message : '定稿失败')
    } finally {
      setBusy(false)
    }
  }, [chapterNum])

  const skipHighlights = useCallback(async () => {
    await proceedToFinalize()
  }, [proceedToFinalize])

  const confirmHighlight = useCallback(
    async (text: string) => {
      const snippet = text.trim()
      if (snippet) {
        await pushChapterHighlight(chapterNum, {
          text: snippet,
          annotation: '审阅通过亮点',
        }).catch(() => undefined)
      }
      await proceedToFinalize()
    },
    [chapterNum, proceedToFinalize],
  )

  const openJudgmentFork = useCallback(() => {
    setPhase('judgment_fork')
  }, [])

  const startReviseChapter = useCallback(async () => {
    try {
      const ch = await fetchChapter(chapterNum)
      setReviseOriginal(ch.content ?? '')
      setPhase('revise_input')
    } catch (e) {
      setError(e instanceof Error ? e.message : '读取章节失败')
    }
  }, [chapterNum])

  const toggleIssueTag = useCallback((tag: string) => {
    setIssueTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    )
  }, [])

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
        })
        if (!rev.ok) {
          throw new Error(rev.error ?? '改稿失败')
        }
        setReviseDraft(
          (rev.revised_text || rev.reply || '').trim(),
        )
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
      await recordJudgment(logId, 'rejected', '用户选择改规则').catch(() => undefined)
    }
    setPhase('rules_drawer')
  }, [review?.log_id])

  const closeRulesDrawer = useCallback(() => {
    setPhase('judgment_fork')
  }, [])

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
    onStreamDone,
    resetToWriting,
    continueAfterPreview,
    acceptReview,
    highlightDraft,
    skipHighlights,
    confirmHighlight,
    issueTags,
    toggleIssueTag,
    openJudgmentFork,
    startReviseChapter,
    submitRevise,
    acceptRevise,
    openRulesDrawer,
    closeRulesDrawer,
    confirmSummary,
    regenerateSummary,
    precheckFailMessage: precheck ? precheckFailMessage(precheck) : '',
  }
}
