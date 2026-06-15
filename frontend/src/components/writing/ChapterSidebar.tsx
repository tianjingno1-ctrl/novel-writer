import { useQuery } from '@tanstack/react-query'

import { setWriteChapter } from '@/api/endpoints'
import { fetchChaptersList, fetchPlanProduct } from '@/api/productApi'
import { cn } from '@/lib/utils'
import { useBookStore } from '@/stores/bookStore'

const STATUS_COLOR: Record<string, string> = {
  approved: 'bg-[var(--color-success)]',
  drafting: 'bg-[var(--color-primary)]',
  pending: 'bg-[var(--color-border-secondary)]',
}

type Props = {
  chapter: number
  dimmed?: boolean
  onSelectChapter: (num: number) => void
}

export function ChapterSidebar({ chapter, dimmed, onSelectChapter }: Props) {
  const setWriteChapterNum = useBookStore((s) => s.setWriteChapterNum)

  const { data: plan } = useQuery({
    queryKey: ['plan', 'product'],
    queryFn: fetchPlanProduct,
  })
  const { data: chaptersData } = useQuery({
    queryKey: ['chapters'],
    queryFn: fetchChaptersList,
  })

  const statuses = plan?.chapter_statuses ?? {}
  const rows = chaptersData?.chapters ?? []
  const nums = new Set([
    ...rows.map((c) => c.num),
    ...Object.keys(statuses).map(Number),
    chapter,
  ])
  const sorted = [...nums].filter((n) => n > 0).sort((a, b) => a - b)
  const approved = Object.values(statuses).filter((s) => s === 'approved').length
  const total = Math.max(sorted.length, Object.keys(statuses).length, 1)
  const pct = Math.round((approved / total) * 100)

  const pick = (num: number) => {
    if (num === chapter) return
    setWriteChapterNum(num)
    void setWriteChapter(num).catch(() => undefined)
    onSelectChapter(num)
  }

  return (
    <aside
      className={cn(
        'flex w-[180px] shrink-0 flex-col border-r border-[var(--color-border-tertiary)] bg-[var(--color-background-primary)]',
        dimmed && 'gate-dim',
      )}
    >
      <div className="flex items-center justify-between border-b border-[var(--color-border-tertiary)] px-3 py-2">
        <span className="text-[11px] text-[var(--color-text-tertiary)]">章节</span>
        <span className="text-[11px] font-medium text-[var(--color-primary)]">
          {approved}/{total}
        </span>
      </div>
      <ul className="flex-1 overflow-y-auto py-1">
        {sorted.map((num) => {
          const st = statuses[String(num)] ?? 'pending'
          const ch = rows.find((c) => c.num === num)
          const active = num === chapter
          return (
            <li key={num}>
              <button
                type="button"
                onClick={() => pick(num)}
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition-colors',
                  active
                    ? 'border-y border-[var(--color-border-tertiary)] bg-[var(--color-background-primary)] font-medium'
                    : 'hover:bg-[var(--color-background-secondary)]',
                )}
              >
                <span
                  className={cn(
                    'h-[7px] w-[7px] shrink-0 rounded-full',
                    STATUS_COLOR[st] ?? STATUS_COLOR.pending,
                  )}
                />
                <span className="min-w-0 flex-1 truncate">
                  第{num}章
                  {ch?.title ? (
                    <span className="ml-1 text-[11px] font-normal text-[var(--color-text-tertiary)]">
                      {ch.title}
                    </span>
                  ) : null}
                </span>
                {ch?.chars != null && ch.chars > 0 ? (
                  <span
                    className="shrink-0 text-[10px] tabular-nums text-[var(--color-text-tertiary)]"
                    title={
                      ch.word_count_target
                        ? `目标约 ${ch.word_count_target} 字`
                        : undefined
                    }
                  >
                    {ch.chars}
                    {ch.word_count_target ? `/${ch.word_count_target}` : ''}
                  </span>
                ) : ch?.word_count_target ? (
                  <span className="shrink-0 text-[10px] tabular-nums text-[var(--color-text-tertiary)]">
                    0/{ch.word_count_target}
                  </span>
                ) : null}
              </button>
            </li>
          )
        })}
      </ul>
      <div className="border-t border-[var(--color-border-tertiary)] px-3 py-2">
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-1 text-center text-[11px] text-[var(--color-text-tertiary)]">
          {pct}%
        </p>
      </div>
    </aside>
  )
}
