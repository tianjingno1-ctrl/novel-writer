import { X } from 'lucide-react'

import {
  CHAPTER_ROLE_LABELS,
  formatPlanIntentDisplay,
  intentFieldLabel,
  isChapterRole,
  type ChapterIntent,
} from '@/lib/chapterRoles'

type ChapterPlan = {
  title?: string
  hook?: string
  role?: string
  intent?: ChapterIntent
  word_count_target?: number | null
  scenes?: Array<{ title?: string; beat?: string; summary?: string }>
}

type Props = {
  chapterNum: number
  logline?: string
  chapterPlan?: ChapterPlan | null
  onClose: () => void
}

function PlanField({
  label,
  value,
  empty = '暂无',
}: {
  label: string
  value?: string
  empty?: string
}) {
  const text = value?.trim()
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-wide text-[var(--color-text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 text-[12px] leading-relaxed text-[var(--color-text-primary)] whitespace-pre-wrap">
        {text || (
          <span className="text-[var(--color-text-tertiary)]">{empty}</span>
        )}
      </p>
    </div>
  )
}

export function ChapterPlanHintPanel({
  chapterNum,
  logline,
  chapterPlan,
  onClose,
}: Props) {
  const hook = chapterPlan?.hook?.trim()
  const title = chapterPlan?.title?.trim()
  const target = chapterPlan?.word_count_target
  const role = chapterPlan?.role
  const roleLabel =
    role && isChapterRole(role) ? CHAPTER_ROLE_LABELS[role] : role?.trim()
  const intentText = chapterPlan
    ? formatPlanIntentDisplay(chapterPlan)
    : ''
  const intentLabel = intentFieldLabel(role)
  const scenes = chapterPlan?.scenes ?? []
  const hasBookDirection = Boolean(logline?.trim())
  const hasChapterPlan = Boolean(
    title ||
      hook ||
      roleLabel ||
      intentText ||
      scenes.length > 0 ||
      (target && target > 0),
  )

  return (
    <div className="shrink-0 border-b border-[var(--color-border-tertiary)] bg-[var(--color-background-secondary)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[12px] font-medium text-[var(--color-text-primary)]">
          规划 · 第 {chapterNum} 章
        </p>
        <button
          type="button"
          className="rounded p-0.5 text-[var(--color-text-tertiary)] hover:bg-[var(--color-background-primary)]"
          onClick={onClose}
          aria-label="收起规划"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <div className="space-y-3">
          <p className="text-[11px] font-medium text-[var(--color-text-secondary)]">
            全书方向
          </p>
          {hasBookDirection ? (
            <PlanField label="Logline" value={logline} />
          ) : (
            <p className="text-[12px] text-[var(--color-text-tertiary)]">
              暂无方向（开书向导中确认后会显示）
            </p>
          )}
        </div>

        <div className="space-y-3">
          <p className="text-[11px] font-medium text-[var(--color-text-secondary)]">
            本章规划
          </p>
          {hasChapterPlan ? (
            <div className="space-y-2.5">
              <PlanField label="标题" value={title} empty="未命名" />
              {roleLabel ? (
                <PlanField label="叙事角色" value={roleLabel} />
              ) : null}
              <PlanField label="章末钩子" value={hook} />
              {intentText && intentLabel ? (
                <PlanField label={intentLabel} value={intentText} />
              ) : intentText ? (
                <PlanField label="叙事意图" value={intentText} />
              ) : null}
              {target && target > 0 ? (
                <p className="text-[11px] text-[var(--color-text-tertiary)]">
                  目标字数约 {target.toLocaleString()} 字（预检下限约{' '}
                  {Math.floor(target * 0.85).toLocaleString()} 字）
                </p>
              ) : null}
              {scenes.length > 0 ? (
                <div className="space-y-2">
                  <p className="text-[10px] font-medium uppercase tracking-wide text-[var(--color-text-tertiary)]">
                    场景 ({scenes.length})
                  </p>
                  {scenes.map((scene, idx) => {
                    const st = scene.title?.trim() || `场景 ${idx + 1}`
                    const beat = scene.beat?.trim()
                    const summary = scene.summary?.trim()
                    return (
                      <div
                        key={`${st}-${idx}`}
                        className="rounded border border-[var(--color-border-tertiary)] bg-[var(--color-background-primary)] px-2.5 py-2"
                      >
                        <p className="text-[11px] font-medium">{st}</p>
                        {beat ? (
                          <p className="mt-1 text-[12px] leading-relaxed whitespace-pre-wrap">
                            {beat}
                          </p>
                        ) : (
                          <p className="mt-1 text-[12px] text-[var(--color-text-tertiary)]">
                            暂无 beat
                          </p>
                        )}
                        {summary ? (
                          <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)] whitespace-pre-wrap">
                            概述：{summary}
                          </p>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-[12px] text-[var(--color-text-tertiary)]">
              暂无本章规划（向导「章节规划」步生成）
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
