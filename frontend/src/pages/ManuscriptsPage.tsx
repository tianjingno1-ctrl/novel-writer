import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { fetchPlanProduct, fetchChaptersList } from '@/api/productApi'
import { fetchWorkQueue } from '@/api/endpoints'
import { fetchStatus } from '@/api/endpoints'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useBookStore } from '@/stores/bookStore'

const STATUS_LABEL: Record<string, string> = {
  pending: '待写',
  drafting: '草稿',
  approved: '已定稿',
}

function statusVariant(status: string): 'default' | 'success' | 'warning' | 'muted' {
  if (status === 'approved') return 'success'
  if (status === 'drafting') return 'warning'
  return 'muted'
}

export function ManuscriptsPage() {
  const navigate = useNavigate()
  const setWriteChapterNum = useBookStore((s) => s.setWriteChapterNum)

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
  })
  const { data: plan } = useQuery({
    queryKey: ['plan', 'product'],
    queryFn: fetchPlanProduct,
  })
  const { data: chapters } = useQuery({
    queryKey: ['chapters'],
    queryFn: fetchChaptersList,
  })
  const { data: queue } = useQuery({
    queryKey: ['flow', 'work-queue'],
    queryFn: fetchWorkQueue,
  })

  const statuses = plan?.chapter_statuses ?? {}
  const chapterRows = chapters?.chapters ?? []
  const nums = new Set([
    ...chapterRows.map((c) => c.num),
    ...Object.keys(statuses).map(Number),
    ...(queue?.pending_write ?? []),
    ...(queue?.pending_review ?? []),
    ...(queue?.pending_summary ?? []),
  ])
  const sorted = [...nums].filter((n) => n > 0).sort((a, b) => a - b)

  const openChapter = (num: number) => {
    setWriteChapterNum(num)
    navigate('/writing')
  }

  return (
    <div className="mx-auto max-w-lg space-y-6 px-4 pb-24">
      <div className="flex items-start justify-between pt-2">
        <div>
          <h1 className="text-xl font-semibold">稿件</h1>
          <p className="mt-1 text-sm text-muted">
            {status?.project_title || '未选书'}
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => navigate('/complete')}>
          完结
        </Button>
      </div>

      {plan?.meta && typeof plan.meta === 'object' ? (
        <div className="rounded-xl border border-border bg-surface p-4 text-sm">
          <p className="font-medium">
            {(plan.meta as { logline?: string }).logline || '未设方向'}
          </p>
          {(plan.meta as { sell_point?: string }).sell_point ? (
            <p className="mt-1 text-muted">
              {(plan.meta as { sell_point?: string }).sell_point}
            </p>
          ) : null}
        </div>
      ) : null}

      <section className="rounded-xl border border-border bg-surface">
        <h2 className="border-b border-border px-4 py-3 text-sm font-medium">
          章节列表
        </h2>
        {sorted.length > 0 ? (
          <ul>
            {sorted.map((num) => {
              const st = statuses[String(num)] ?? 'pending'
              const ch = chapterRows.find((c) => c.num === num)
              return (
                <li key={num}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between border-b border-border/60 px-4 py-3 text-left last:border-0 hover:bg-accent/50"
                    onClick={() => openChapter(num)}
                  >
                    <div>
                      <span className="text-sm font-medium">第 {num} 章</span>
                      {ch?.title ? (
                        <span className="ml-2 text-sm text-muted">
                          {ch.title}
                        </span>
                      ) : null}
                      {ch?.chars ? (
                        <span className="ml-2 text-xs text-muted">
                          {ch.chars} 字
                        </span>
                      ) : null}
                    </div>
                    <Badge variant={statusVariant(st)}>
                      {STATUS_LABEL[st] ?? st}
                    </Badge>
                  </button>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="px-4 py-6 text-sm text-muted">
            暂无章节。完成开书向导后开始写作。
          </p>
        )}
      </section>

      {queue &&
      ((queue.pending_write?.length ?? 0) > 0 ||
        (queue.pending_review?.length ?? 0) > 0 ||
        (queue.pending_summary?.length ?? 0) > 0) ? (
        <section className="rounded-xl border border-border bg-surface p-4">
          <h2 className="text-sm font-medium">待办</h2>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            {(queue.pending_write ?? []).map((num) => (
              <li key={`w-${num}`}>
                第 {num} 章 · 待写
              </li>
            ))}
            {(queue.pending_review ?? []).map((num) => (
              <li key={`r-${num}`}>
                第 {num} 章 · 审阅中
              </li>
            ))}
            {(queue.pending_summary ?? []).map((num) => (
              <li key={`s-${num}`}>
                第 {num} 章 · 概述待确认
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
