import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import {
  createManuscript,
  fetchPlanProduct,
  updateLifecycle,
} from '@/api/productApi'
import { fetchActiveBook, fetchStats, fetchStatus, fetchWorkQueue } from '@/api/endpoints'
import { StyleExtractPanel } from '@/components/product/ComplianceGate'
import { Button } from '@/components/ui/button'

function writingDays(createdAt: string | undefined): number | null {
  if (!createdAt) return null
  const start = new Date(createdAt).getTime()
  if (Number.isNaN(start)) return null
  return Math.max(1, Math.ceil((Date.now() - start) / 86400000))
}

export function CompletePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
  })
  const { data: plan } = useQuery({
    queryKey: ['plan', 'product'],
    queryFn: fetchPlanProduct,
  })
  const { data: workQueue } = useQuery({
    queryKey: ['flow', 'work-queue'],
    queryFn: fetchWorkQueue,
  })
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
  })
  const { data: activeBook } = useQuery({
    queryKey: ['library', 'active'],
    queryFn: fetchActiveBook,
  })

  const statuses = plan?.chapter_statuses ?? {}
  const totalChapters = Object.keys(statuses).length
  const approved = Object.values(statuses).filter((s) => s === 'approved').length
  const pendingSummary = workQueue?.pending_summary ?? []
  const totalChars = stats?.total_chars ?? 0
  const writingDayCount = writingDays(activeBook?.book?.created_at)

  const markComplete = useMutation({
    mutationFn: async () => {
      const ms = await createManuscript(status?.project_title ?? '')
      const msId = String(
        (ms as { manuscript?: { id?: string } }).manuscript?.id ?? '',
      )
      if (!msId) throw new Error('创建稿件失败')
      await updateLifecycle({ status: 'complete', manuscript_id: msId })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['lifecycle'] })
    },
  })

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-[var(--color-overlay)] p-4">
      <div className="card-ui w-full max-w-md text-center shadow-[var(--shadow-md)]">
        <p className="text-3xl">🎉</p>
        <h1 className="page-title mt-3">完结！</h1>
        <p className="page-sub mt-2">
          {status?.project_title || '未命名'} · 共 {totalChapters || approved} 章
          {approved > 0 ? ` · 已定稿 ${approved} 章` : ''}
          {totalChars > 0 ? ` · ${totalChars.toLocaleString()} 字` : ''}
          {writingDayCount ? ` · 写作 ${writingDayCount} 天` : ''}
        </p>

        {pendingSummary.length > 0 ? (
          <div className="ai-warn mt-4 text-left">
            <p className="font-medium">
              {pendingSummary.length} 章摘要待确认
            </p>
            <Button
              size="sm"
              variant="outline"
              className="mt-2"
              onClick={() => navigate('/writing')}
            >
              去写作页处理
            </Button>
          </div>
        ) : null}

        <div className="mt-6 space-y-2">
          <Button
            className="w-full"
            variant="outline"
            disabled={markComplete.isPending}
            onClick={() => markComplete.mutate()}
          >
            {markComplete.isPending ? '处理中…' : '标记全书完结'}
          </Button>
          <StyleExtractPanel />
          <Button className="w-full" onClick={() => navigate('/manuscripts')}>
            去投递稿件 →
          </Button>
          <Button variant="ghost" className="w-full" onClick={() => navigate('/')}>
            返回书架
          </Button>
        </div>
      </div>
    </div>
  )
}
