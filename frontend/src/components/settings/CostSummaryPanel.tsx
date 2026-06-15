import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useMemo, useState } from 'react'

import { fetchCostSummary, fetchLibrary } from '@/api/endpoints'
import type { CostSummaryBook } from '@/types/api'

const STEP_LABEL: Record<string, string> = {
  writing: '写作',
  review: '质量审阅',
  summary: '概述',
  deconstruct: '拆文',
  diagnose: '诊断',
  attribution: '诊断',
  plan: '规划',
  other: '其他',
}

function stepLabel(tag: string): string {
  if (STEP_LABEL[tag]) return STEP_LABEL[tag]
  for (const [key, label] of Object.entries(STEP_LABEL)) {
    if (tag.includes(key)) return label
  }
  return tag
}

function formatCost(value: number): string {
  return `$${value.toFixed(4)}`
}

function bookLabel(bookId: string, titles: Map<string, string>): string {
  if (!bookId) return '未关联书籍'
  const title = titles.get(bookId)
  return title ? `${title} (${bookId})` : bookId
}

function BookCostRow({
  row,
  title,
}: {
  row: CostSummaryBook
  title: string
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)]">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[13px] hover:bg-[var(--color-background-secondary)]"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--color-text-tertiary)]" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--color-text-tertiary)]" />
        )}
        <span className="min-w-0 flex-1 truncate font-medium">{title}</span>
        <span className="shrink-0 tabular-nums text-[11px] text-[var(--color-text-tertiary)]">
          {formatCost(row.total_cost)}
        </span>
      </button>
      {open ? (
        <div className="border-t border-[var(--color-border-tertiary)] px-3 pb-3">
          <table className="mt-2 w-full text-[13px]">
            <thead>
              <tr className="text-left text-[11px] text-[var(--color-text-tertiary)]">
                <th className="pb-1 font-medium">步骤</th>
                <th className="pb-1 text-right font-medium">费用</th>
              </tr>
            </thead>
            <tbody>
              {row.steps.map((step) => (
                <tr
                  key={step.tag}
                  className="border-t border-[var(--color-border-tertiary)] first:border-t-0"
                >
                  <td className="py-1.5 pr-2">{stepLabel(step.tag)}</td>
                  <td className="py-1.5 text-right tabular-nums text-[11px]">
                    {formatCost(step.cost)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

export function CostSummaryPanel() {
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['cost', 'summary'],
    queryFn: fetchCostSummary,
  })

  const { data: library } = useQuery({
    queryKey: ['library'],
    queryFn: fetchLibrary,
  })

  const titles = useMemo(() => {
    const map = new Map<string, string>()
    for (const book of library?.books ?? []) {
      if (book.id && book.title) {
        map.set(book.id, book.title)
      }
    }
    return map
  }, [library?.books])

  const rows = data?.by_book ?? []
  const grandTotal = rows.reduce((sum, row) => sum + row.total_cost, 0)

  return (
    <div className="card-ui space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[13px] font-medium">费用统计</p>
        <button
          type="button"
          className="text-[11px] text-[var(--color-primary)] hover:underline disabled:opacity-50"
          disabled={isFetching}
          onClick={() => void refetch()}
        >
          {isFetching ? '刷新中…' : '刷新'}
        </button>
      </div>
      <p className="text-[11px] text-[var(--color-text-tertiary)]">
        数据来自费用日志，为预估费用，按书汇总。
      </p>
      {isLoading ? (
        <p className="text-[var(--color-text-tertiary)]">加载中…</p>
      ) : error ? (
        <p className="text-[var(--color-danger)]">{(error as Error).message}</p>
      ) : rows.length === 0 ? (
        <p className="text-[var(--color-text-tertiary)]">暂无费用记录</p>
      ) : (
        <>
          <p className="text-[13px]">
            总计{' '}
            <span className="font-medium tabular-nums">
              {formatCost(grandTotal)}
            </span>
          </p>
          <div className="space-y-2">
            {rows.map((row) => (
              <BookCostRow
                key={row.book_id || '__empty__'}
                row={row}
                title={bookLabel(row.book_id, titles)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
