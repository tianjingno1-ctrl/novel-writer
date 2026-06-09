import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'

import {
  createManuscript,
  fetchLifecycle,
  fetchPlanProduct,
  updateLifecycle,
} from '@/api/productApi'
import { fetchWorkQueue, initReviewCriteria } from '@/api/endpoints'
import { patchManuscript } from '@/api/productApi'
import {
  ComplianceGate,
  StyleExtractPanel,
} from '@/components/product/ComplianceGate'
import { Button } from '@/components/ui/button'
import { fetchStatus } from '@/api/endpoints'
import { useBookStore } from '@/stores/bookStore'

const SUBMISSION_TARGETS = [
  { id: 'text_editor', label: '文字编辑' },
  { id: 'comic_drama', label: '漫剧' },
  { id: 'short_drama', label: '短剧' },
] as const

export function CompletePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const setWriteChapterNum = useBookStore((s) => s.setWriteChapterNum)
  const [target, setTarget] = useState('text_editor')

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
  })
  const { data: plan } = useQuery({
    queryKey: ['plan', 'product'],
    queryFn: fetchPlanProduct,
  })
  const { data: lifecycle } = useQuery({
    queryKey: ['lifecycle'],
    queryFn: fetchLifecycle,
  })
  const { data: workQueue } = useQuery({
    queryKey: ['flow', 'work-queue'],
    queryFn: fetchWorkQueue,
  })

  const pendingSummary = workQueue?.pending_summary ?? []
  const pendingWrite = workQueue?.pending_write ?? []
  const statuses = plan?.chapter_statuses ?? {}

  const markComplete = useMutation({
    mutationFn: async () => {
      const ms = await createManuscript(status?.project_title ?? '')
      const msId = String(
        (ms as { manuscript?: { id?: string } }).manuscript?.id ?? '',
      )
      if (!msId) {
        throw new Error('创建稿件失败')
      }
      await updateLifecycle({ status: 'complete', manuscript_id: msId })
      return ms
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['lifecycle'] })
    },
  })

  const submit = useMutation({
    mutationFn: async () => {
      const lc = lifecycle?.lifecycle as { manuscript_id?: string } | undefined
      const msId = lc?.manuscript_id
      if (!msId) {
        throw new Error('请先标记全书完结')
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
      void qc.invalidateQueries({ queryKey: ['lifecycle'] })
    },
  })

  const totalChapters = Object.keys(statuses).length

  const goReviseChapters = (nums: number[]) => {
    const first = nums[0]
    if (first) {
      setWriteChapterNum(first)
      navigate('/writing')
    }
  }

  return (
    <div className="mx-auto max-w-md space-y-6 px-4 py-8 pb-24 text-center">
      <div>
        <p className="text-3xl">🎉</p>
        <h1 className="mt-2 text-xl font-semibold">全书完成</h1>
        <p className="mt-1 text-sm text-muted">
          {status?.project_title || '未命名'} · {totalChapters || '—'} 章
        </p>
      </div>

      {pendingSummary.length > 0 ? (
        <div className="rounded-xl border border-warning/40 bg-warning/10 p-4 text-left text-sm">
          <p className="font-medium text-warning">
            {pendingSummary.length} 章概述待确认
          </p>
          <p className="mt-1 text-xs text-muted">
            第 {pendingSummary.join('、')} 章
          </p>
          <Button
            size="sm"
            variant="outline"
            className="mt-2"
            onClick={() => navigate('/manuscripts')}
          >
            现在处理
          </Button>
        </div>
      ) : null}

      {pendingWrite.length > 0 ? (
        <p className="text-sm text-muted">
          另有 {pendingWrite.length} 章尚未开始写作
        </p>
      ) : null}

      <div className="space-y-3 text-left">
        <p className="text-sm font-medium text-center">接下来？</p>
        <Button
          className="w-full"
          variant="outline"
          disabled={markComplete.isPending}
          onClick={() => markComplete.mutate()}
        >
          {markComplete.isPending ? '处理中…' : '📚 留库 / 标记完结'}
        </Button>

        <StyleExtractPanel />

        <div className="rounded-xl border border-border p-4">
          <p className="text-sm font-medium mb-2">📝 投递</p>
          <div className="space-y-1 text-sm">
            {SUBMISSION_TARGETS.map((t) => (
              <label key={t.id} className="flex items-center gap-2">
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
          {submit.isSuccess ? (
            <p className="mt-3 text-xs text-success">投递记录已提交</p>
          ) : (
            <ComplianceGate
              target={target}
              onProceed={() => submit.mutate()}
              onRevise={goReviseChapters}
            />
          )}
        </div>
      </div>

      <Button variant="ghost" onClick={() => navigate('/')}>
        返回书架
      </Button>
    </div>
  )
}
