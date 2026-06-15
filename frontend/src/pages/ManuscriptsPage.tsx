import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'

import {
  createManuscript,
  fetchLifecycle,
  listManuscripts,
  patchManuscript,
  updateLifecycle,
  type ManuscriptRow,
  type ManuscriptSubmission,
} from '@/api/productApi'
import { fetchLibrary, fetchStatus, initReviewCriteria, switchBook } from '@/api/endpoints'
import {
  ComplianceGate,
  CompliancePreviewReport,
} from '@/components/product/ComplianceGate'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useBookStore } from '@/stores/bookStore'
import { cn } from '@/lib/utils'

const SUBMISSION_TARGETS = [
  { id: 'text_editor', label: '文字编辑' },
  { id: 'comic_drama', label: '漫剧' },
  { id: 'short_drama', label: '短剧' },
] as const

const REJECT_TAG_OPTIONS = [
  { id: 'hook_weak', label: '钩子弱/开头慢' },
  { id: 'ai_tone', label: 'AI味重' },
  { id: 'pacing_slow', label: '节奏拖' },
  { id: 'character_off', label: '人设不对' },
  { id: 'emotion_flat', label: '情绪 flat/不落地' },
  { id: 'dialogue_stiff', label: '对话假' },
  { id: 'platform_mismatch', label: '不符合平台' },
] as const

const STATE_LABEL: Record<string, { label: string; variant: 'done' | 'hard' | 'warn' | 'muted' }> = {
  passed: { label: '通过', variant: 'done' },
  rejected: { label: '拒稿', variant: 'hard' },
  submitting: { label: '预检中', variant: 'warn' },
  draft: { label: '草稿', variant: 'muted' },
  result: { label: '已录入', variant: 'muted' },
}

function getSubmission(row: ManuscriptRow): ManuscriptSubmission {
  return row.submission ?? row.last_submission ?? {}
}

function targetLabel(target?: string) {
  return SUBMISSION_TARGETS.find((t) => t.id === target)?.label ?? target ?? '—'
}

function borderColor(state?: string, submission?: ManuscriptSubmission) {
  const result = submission?.result
  if (result === 'passed') return 'border-l-[var(--color-success)]'
  if (result === 'rejected') return 'border-l-[var(--color-danger)]'
  if (state === 'submitting') return 'border-l-[var(--color-warning)]'
  return 'border-l-[var(--color-border-secondary)]'
}

function badgeForRow(row: ManuscriptRow, sub: ManuscriptSubmission) {
  const result = sub.result?.toLowerCase()
  if (result === 'passed') return STATE_LABEL.passed
  if (result === 'rejected') return STATE_LABEL.rejected
  if (row.state === 'submitting') return STATE_LABEL.submitting
  return STATE_LABEL[row.state ?? ''] ?? {
    label: row.state ?? '—',
    variant: 'muted' as const,
  }
}

export function ManuscriptsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const setFlowIntent = useBookStore((s) => s.setFlowIntent)
  const setWriteChapterNum = useBookStore((s) => s.setWriteChapterNum)

  const [sheetOpen, setSheetOpen] = useState(false)
  const [target, setTarget] = useState('text_editor')
  const [selectedBookId, setSelectedBookId] = useState('')

  const [precheckTarget, setPrecheckTarget] = useState<string | null>(null)
  const [resultMsId, setResultMsId] = useState<string | null>(null)
  const [rejectKind, setRejectKind] = useState<'content' | 'strategy'>('content')
  const [rejectTags, setRejectTags] = useState<string[]>([])
  const [rejectReason, setRejectReason] = useState('')

  const { data: library } = useQuery({
    queryKey: ['library'],
    queryFn: fetchLibrary,
  })
  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
  })
  const { data: lifecycle } = useQuery({
    queryKey: ['lifecycle'],
    queryFn: fetchLifecycle,
  })
  const { data: manuscripts, refetch: refetchMs } = useQuery({
    queryKey: ['manuscripts'],
    queryFn: () => listManuscripts(),
  })

  const books = library?.books ?? []
  const rows = manuscripts?.manuscripts ?? []
  const activeId = library?.active_book_id ?? status?.book_id ?? ''

  const markComplete = useMutation({
    mutationFn: async (bookId: string) => {
      if (bookId && bookId !== activeId) {
        await switchBook(bookId)
      }
      const ms = await createManuscript(
        books.find((b) => b.id === bookId)?.title ?? '',
      )
      const msId = String(
        (ms as { manuscript?: { id?: string } }).manuscript?.id ?? '',
      )
      if (!msId) throw new Error('创建稿件失败')
      await updateLifecycle({ status: 'complete', manuscript_id: msId })
      return msId
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['lifecycle'] })
      void qc.invalidateQueries({ queryKey: ['manuscripts'] })
    },
  })

  const submit = useMutation({
    mutationFn: async () => {
      const lc = lifecycle?.lifecycle as { manuscript_id?: string } | undefined
      let msId = lc?.manuscript_id as string | undefined
      if (!msId) {
        msId = await markComplete.mutateAsync(selectedBookId || activeId)
      }
      if (target !== 'text_editor') {
        await initReviewCriteria(`tomato_${target}_v1`).catch(() => undefined)
      }
      return patchManuscript(msId, {
        state: 'submitting',
        submission: {
          target,
          submitted_at: new Date().toISOString().slice(0, 10),
          compliance_checked: true,
        },
      })
    },
    onSuccess: () => {
      setSheetOpen(false)
      void refetchMs()
      void qc.invalidateQueries({ queryKey: ['lifecycle'] })
    },
  })

  const recordResult = useMutation({
    mutationFn: async ({
      msId,
      outcome,
      bookId,
    }: {
      msId: string
      outcome: 'passed' | 'rejected'
      bookId?: string
    }) => {
      if (bookId && bookId !== activeId) {
        await switchBook(bookId)
      }
      if (outcome === 'passed') {
        return patchManuscript(msId, { submission: { result: 'passed' } })
      }
      return patchManuscript(msId, {
        submission: {
          result: 'rejected',
          reject_tags: rejectTags,
          reject_reason: rejectReason.trim(),
          reject_kind: rejectKind,
        },
      })
    },
    onSuccess: (data, vars) => {
      setResultMsId(null)
      setRejectTags([])
      setRejectReason('')
      setRejectKind('content')
      void refetchMs()
      void qc.invalidateQueries({ queryKey: ['manuscripts'] })
      if (
        vars.outcome === 'rejected' &&
        data.rejection_fork === 'content' &&
        data.diagnosis_id
      ) {
        setFlowIntent({ kind: 'attribution', diagnosisId: data.diagnosis_id })
        navigate('/writing')
      }
    },
  })

  const ensureActiveBook = async (bookId?: string) => {
    if (bookId && bookId !== activeId) {
      await switchBook(bookId)
      void qc.invalidateQueries({ queryKey: ['status'] })
    }
  }

  const goDiagnosis = async (diagnosisId?: string, bookId?: string) => {
    if (!diagnosisId) return
    await ensureActiveBook(bookId)
    setFlowIntent({ kind: 'attribution', diagnosisId })
    navigate('/writing')
  }

  const goRevise = (chapters: number[]) => {
    const first = chapters[0]
    if (!first) return
    setFlowIntent({
      kind: 'revise',
      chapter: first,
      note: '合规回改：降低 AI 腔风险',
    })
    setWriteChapterNum(first)
    navigate('/writing')
  }

  const toggleRejectTag = (tag: string) => {
    setRejectTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    )
  }

  const resultRow = rows.find((r) => r.id === resultMsId)

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="稿件"
        subtitle="投递记录与合规预检"
        actions={
          <Button onClick={() => setSheetOpen(true)}>新建稿件</Button>
        }
      />

      <div className="mt-6 space-y-3">
        {rows.length === 0 ? (
          <div className="card-ui text-center text-[13px] text-[var(--color-text-tertiary)]">
            暂无稿件。全书完结后可在此投递。
          </div>
        ) : (
          rows.map((row) => {
            const sub = getSubmission(row)
            const st = badgeForRow(row, sub)
            const bookTitle =
              books.find((b) => b.id === row.book_id)?.title ?? row.title ?? row.id
            const tags = sub.reject_tags ?? []
            const pendingResult =
              row.state === 'submitting' && !String(sub.result ?? '').trim()

            return (
              <article
                key={row.id}
                className={cn(
                  'card-ui border-l-[3px]',
                  borderColor(row.state, sub),
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-[13px] font-medium">{bookTitle}</p>
                    <p className="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">
                      {targetLabel(sub.target)} · {sub.submitted_at ?? '—'}
                    </p>
                  </div>
                  <Badge variant={st.variant}>{st.label}</Badge>
                </div>
                {tags.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {tags.map((tag) => (
                      <span key={tag} className="badge-warn">
                        {REJECT_TAG_OPTIONS.find((o) => o.id === tag)?.label ?? tag}
                      </span>
                    ))}
                  </div>
                ) : null}
                {sub.reject_reason ? (
                  <p className="mt-2 text-[11px] text-[var(--color-text-secondary)]">
                    {sub.reject_reason}
                  </p>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-2">
                  {pendingResult ? (
                    <>
                      <Button
                        size="sm"
                        onClick={() => setResultMsId(row.id)}
                      >
                        录入投递结果
                      </Button>
                      {sub.target ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setPrecheckTarget(sub.target!)}
                        >
                          查看预检报告
                        </Button>
                      ) : null}
                    </>
                  ) : null}
                  {sub.result === 'rejected' ? (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!sub.diagnosis_id}
                        onClick={() => void goDiagnosis(sub.diagnosis_id, row.book_id)}
                      >
                        诊断
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => setSheetOpen(true)}
                      >
                        重新投递
                      </Button>
                    </>
                  ) : null}
                  {sub.result === 'passed' && sub.target ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setPrecheckTarget(sub.target!)}
                    >
                      查看预检报告
                    </Button>
                  ) : null}
                </div>
              </article>
            )
          })
        )}
      </div>

      {sheetOpen ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-[var(--color-overlay)] p-4 sm:items-center">
          <div className="card-ui w-full max-w-md">
            <h2 className="text-[13px] font-medium">新建稿件</h2>
            <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
              1. 选择书 → 2. 投递类型 → 3. 合规预检
            </p>

            <div className="mt-4 space-y-2">
              <p className="text-[11px] font-medium">选择书</p>
              {books.map((b) => (
                <label
                  key={b.id}
                  className="flex cursor-pointer items-center gap-2 text-[13px]"
                >
                  <input
                    type="radio"
                    name="book"
                    checked={(selectedBookId || activeId) === b.id}
                    onChange={() => setSelectedBookId(b.id)}
                  />
                  {b.title || b.id}
                </label>
              ))}
            </div>

            <div className="mt-4 space-y-2">
              <p className="text-[11px] font-medium">投递类型</p>
              {SUBMISSION_TARGETS.map((t) => (
                <label
                  key={t.id}
                  className="flex cursor-pointer items-center gap-2 text-[13px]"
                >
                  <input
                    type="radio"
                    name="target"
                    checked={target === t.id}
                    onChange={() => setTarget(t.id)}
                  />
                  {t.label}
                </label>
              ))}
            </div>

            <ComplianceGate
              target={target}
              onProceed={() => submit.mutate()}
              onRevise={goRevise}
            />

            <Button
              variant="ghost"
              className="mt-3 w-full"
              onClick={() => setSheetOpen(false)}
            >
              取消
            </Button>
          </div>
        </div>
      ) : null}

      {precheckTarget ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-[var(--color-overlay)] p-4 sm:items-center">
          <div className="card-ui w-full max-w-md">
            <h2 className="text-[13px] font-medium">合规预检报告</h2>
            <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
              {targetLabel(precheckTarget)}
            </p>
            <div className="mt-4">
              <CompliancePreviewReport target={precheckTarget} />
            </div>
            <Button
              variant="ghost"
              className="mt-4 w-full"
              onClick={() => setPrecheckTarget(null)}
            >
              关闭
            </Button>
          </div>
        </div>
      ) : null}

      {resultMsId && resultRow ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-[var(--color-overlay)] p-4 sm:items-center">
          <div className="card-ui w-full max-w-md text-left">
            <h2 className="text-[13px] font-medium">录入投递结果</h2>
            <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
              {books.find((b) => b.id === resultRow.book_id)?.title ?? resultRow.title}
            </p>

            <div className="mt-4">
              <Button
                className="w-full"
                disabled={recordResult.isPending}
                onClick={() =>
                  recordResult.mutate({
                    msId: resultMsId,
                    outcome: 'passed',
                    bookId: resultRow.book_id,
                  })
                }
              >
                {recordResult.isPending ? '保存中…' : '编辑通过'}
              </Button>
            </div>

            <div className="mt-4 space-y-3 border-t border-[var(--color-border-tertiary)] pt-4">
              <p className="text-[11px] font-medium text-[var(--color-danger)]">或：录入拒稿</p>
              <div className="flex flex-wrap gap-2">
                {REJECT_TAG_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className={cn(
                      'rounded-full border-[0.5px] px-2.5 py-1 text-[11px]',
                      rejectTags.includes(opt.id)
                        ? 'border-[var(--color-danger)] bg-[var(--color-danger-bg)] text-[var(--color-danger-text)]'
                        : 'border-[var(--color-border-secondary)] text-[var(--color-text-secondary)]',
                    )}
                    onClick={() => toggleRejectTag(opt.id)}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              <div>
                <p className="text-[11px] font-medium">拒稿原因</p>
                <textarea
                  className="mt-1 min-h-20 w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-primary)] p-2 text-[13px] outline-none"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="编辑反馈摘要…"
                />
              </div>

              <div>
                <p className="text-[11px] font-medium">拒稿类型</p>
                <div className="mt-2 space-y-1">
                  <label className="flex cursor-pointer items-center gap-2 text-[13px]">
                    <input
                      type="radio"
                      name="reject_kind"
                      checked={rejectKind === 'content'}
                      onChange={() => setRejectKind('content')}
                    />
                    内容问题 → 进入诊断
                  </label>
                  <label className="flex cursor-pointer items-center gap-2 text-[13px]">
                    <input
                      type="radio"
                      name="reject_kind"
                      checked={rejectKind === 'strategy'}
                      onChange={() => setRejectKind('strategy')}
                    />
                    投递策略 → 重新选类型
                  </label>
                </div>
              </div>

              <Button
                className="w-full"
                variant="dangerOutline"
                disabled={
                  recordResult.isPending ||
                  (rejectTags.length === 0 && !rejectReason.trim())
                }
                onClick={() =>
                  recordResult.mutate({
                    msId: resultMsId,
                    outcome: 'rejected',
                    bookId: resultRow.book_id,
                  })
                }
              >
                {recordResult.isPending ? '保存中…' : '确认拒稿'}
              </Button>
            </div>

            {recordResult.error ? (
              <p className="mt-2 text-[11px] text-[var(--color-danger)]">
                {(recordResult.error as Error).message}
              </p>
            ) : null}

            <Button
              variant="ghost"
              className="mt-3 w-full"
              onClick={() => {
                setResultMsId(null)
                setRejectTags([])
                setRejectReason('')
              }}
            >
              取消
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
