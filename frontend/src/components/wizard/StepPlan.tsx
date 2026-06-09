import { useMutation } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { applyPlan, prefillPlan } from '@/api/endpoints'
import { Button } from '@/components/ui/button'
import { useWizardStore, type PlanChapter } from '@/stores/wizardStore'

function updateChapter(
  chapters: PlanChapter[],
  index: number,
  patch: Partial<PlanChapter>,
) {
  return chapters.map((ch, i) => (i === index ? { ...ch, ...patch } : ch))
}

export function StepPlan() {
  const selectedDirection = useWizardStore((s) => s.selectedDirection)
  const chapterCount = useWizardStore((s) => s.chapterCount)
  const planTitle = useWizardStore((s) => s.planTitle)
  const planChapters = useWizardStore((s) => s.planChapters)
  const planLogId = useWizardStore((s) => s.planLogId)
  const setPlan = useWizardStore((s) => s.setPlan)
  const [expanded, setExpanded] = useState(true)
  const [localChapters, setLocalChapters] = useState<PlanChapter[]>([])

  const chapters = localChapters.length ? localChapters : planChapters

  const syncChapters = (next: PlanChapter[]) => {
    setLocalChapters(next)
    setPlan(planTitle, next, planLogId)
  }

  const load = useMutation({
    mutationFn: () =>
      prefillPlan({
        direction_option: selectedDirection ?? undefined,
        chapter_count: chapterCount,
      }),
    onSuccess: (data) => {
      const opt = data.option ?? {}
      const rows = opt.chapters ?? []
      setLocalChapters(rows)
      setPlan(
        String(opt.title ?? selectedDirection?.logline ?? '未命名'),
        rows,
        data.log_id ?? null,
      )
    },
  })

  const setStep = useWizardStore((s) => s.setStep)

  const confirm = useMutation({
    mutationFn: () =>
      applyPlan(
        {
          title: planTitle,
          chapters: chapters,
        },
        true,
        planLogId ?? undefined,
      ),
    onSuccess: () => {
      setStep('criteria')
    },
  })

  const hasPlan = chapters.length > 0

  return (
    <div className="mx-auto max-w-lg space-y-6 px-4 pb-8">
      <div className="text-center">
        <h2 className="text-xl font-semibold">
          {planTitle || '章规划'}
          {hasPlan ? ` · 共 ${chapters.length} 章` : ''}
        </h2>
        <p className="mt-2 text-sm text-muted">确认后就可以开始写了</p>
      </div>

      {!hasPlan ? (
        <div className="flex justify-center">
          <Button
            size="lg"
            onClick={() => load.mutate()}
            disabled={load.isPending}
          >
            {load.isPending ? '正在规划章节…' : '生成章规划'}
          </Button>
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-surface shadow-sm">
          <button
            type="button"
            className="flex w-full items-center justify-between px-5 py-4 text-left"
            onClick={() => setExpanded((v) => !v)}
          >
            <span className="font-medium">章节列表</span>
            {expanded ? (
              <ChevronDown className="h-4 w-4 text-muted" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted" />
            )}
          </button>
          {expanded ? (
            <ul className="border-t border-border px-5 py-2">
              {chapters.map((ch, i) => (
                <li
                  key={ch.num ?? i}
                  className="border-b border-border/60 py-3 last:border-0 space-y-2"
                >
                  <div className="flex gap-2 text-sm">
                    <span className="shrink-0 text-muted">第{ch.num ?? i + 1}章</span>
                    <input
                      className="flex-1 rounded border border-border bg-background px-2 py-1"
                      value={ch.title ?? ''}
                      placeholder="标题"
                      onChange={(e) =>
                        syncChapters(
                          updateChapter(chapters, i, { title: e.target.value }),
                        )
                      }
                    />
                  </div>
                  <input
                    className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                    value={ch.beat ?? ''}
                    placeholder="Beat"
                    onChange={(e) =>
                      syncChapters(
                        updateChapter(chapters, i, { beat: e.target.value }),
                      )
                    }
                  />
                  <input
                    className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                    value={ch.hook ?? ''}
                    placeholder="章末钩子"
                    onChange={(e) =>
                      syncChapters(
                        updateChapter(chapters, i, { hook: e.target.value }),
                      )
                    }
                  />
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}

      {hasPlan ? (
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
          <Button
            variant="outline"
            onClick={() => load.mutate()}
            disabled={load.isPending}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            重新生成规划
          </Button>
          <Button
            size="lg"
            onClick={() => confirm.mutate()}
            disabled={confirm.isPending}
          >
            确认，开始写 →
          </Button>
        </div>
      ) : null}

      {load.error ? (
        <p className="text-center text-sm text-danger">
          {(load.error as Error).message}
        </p>
      ) : null}
      {confirm.error ? (
        <p className="text-center text-sm text-danger">
          {(confirm.error as Error).message}
        </p>
      ) : null}
    </div>
  )
}
