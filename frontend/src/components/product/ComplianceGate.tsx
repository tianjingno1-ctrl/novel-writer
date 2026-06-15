import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'

import { fetchCompliancePreview } from '@/api/productApi'
import {
  applyAuthorProfile,
  extractAuthorProfile,
  fetchAuthorProfile,
} from '@/api/tasteApi'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type Props = {
  target: string
  onProceed: () => void
  onRevise: (chapters: number[]) => void
}

const RISK_LABEL: Record<string, string> = {
  high: '偏高',
  medium: '中等',
  low: '较低',
  unknown: '检测中',
}

export function CompliancePreviewReport({ target }: { target: string }) {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['compliance', 'preview', target],
    queryFn: () => fetchCompliancePreview(target),
    enabled: Boolean(target),
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-[var(--color-text-tertiary)]">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        加载预检报告…
      </div>
    )
  }

  const risk = data?.risk_level ?? 'unknown'
  const highChapters =
    data?.high_risk_chapters
      ?.map((r) => r.chapter_num)
      .filter((n): n is number => typeof n === 'number') ?? []

  return (
    <div className="space-y-3 text-left">
      <p className="text-[11px] text-[var(--color-text-secondary)]">
        平台 {data?.platform ?? '—'} · AI 腔风险 {data?.risk_score ?? '—'} ·{' '}
        {RISK_LABEL[risk] ?? risk}
      </p>
      {highChapters.length > 0 ? (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-[var(--color-warning-text)]">
            高风险章节
          </p>
          <ul className="list-inside list-disc text-[11px] text-[var(--color-text-secondary)]">
            {data?.high_risk_chapters?.map((row) => (
              <li key={row.chapter_num}>
                第 {row.chapter_num} 章
                {row.ai_tone_score != null ? `（${row.ai_tone_score}）` : ''}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-[11px] text-[var(--color-text-tertiary)]">
          未检出明显高风险章节
        </p>
      )}
      <Button
        size="sm"
        variant="outline"
        disabled={isFetching}
        onClick={() => void refetch()}
      >
        {isFetching ? '刷新中…' : '重新检测'}
      </Button>
    </div>
  )
}

export function ComplianceGate({ target, onProceed, onRevise }: Props) {
  const [ignored, setIgnored] = useState(false)

  const { data, refetch, isFetching, isLoading } = useQuery({
    queryKey: ['compliance', 'preview', target],
    queryFn: () => fetchCompliancePreview(target),
    enabled: Boolean(target),
  })

  const risk = data?.risk_level ?? 'unknown'
  const highChapters =
    data?.high_risk_chapters
      ?.map((r) => r.chapter_num)
      .filter((n): n is number => typeof n === 'number') ?? []

  if (isLoading) {
    return (
      <div className="mt-3 flex items-center gap-2 text-[11px] text-[var(--color-text-tertiary)]">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        合规预检进行中…
      </div>
    )
  }

  if (ignored || risk === 'low') {
    return (
      <Button className="mt-3 w-full" size="sm" onClick={onProceed}>
        提交投递记录
      </Button>
    )
  }

  return (
    <div
      className={cn(
        'mt-3 space-y-3 rounded-[var(--border-radius-lg)] border-[0.5px] p-3 text-left',
        risk === 'high'
          ? 'border-[var(--color-warning)]/40 bg-[var(--color-warning-bg)]'
          : 'border-[var(--color-border-tertiary)] bg-[var(--color-background-secondary)]',
      )}
    >
      <p className="text-[13px] font-medium">合规预检</p>
      <p className="text-[11px] text-[var(--color-text-secondary)]">
        平台 {data?.platform ?? '—'} · AI 腔风险 {data?.risk_score ?? '—'} ·{' '}
        {RISK_LABEL[risk] ?? risk}
      </p>
      {highChapters.length > 0 ? (
        <p className="text-[11px] text-[var(--color-warning-text)]">
          建议先改：第 {highChapters.join('、')} 章（AI 腔片段偏多）
        </p>
      ) : null}
      <div className="flex flex-col gap-2">
        {risk === 'high' ? (
          <>
            <Button size="sm" variant="outline" onClick={() => onRevise(highChapters)}>
              回改问题章节
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setIgnored(true)}>
              忽略风险，继续投递
            </Button>
          </>
        ) : (
          <>
            <Button size="sm" onClick={onProceed}>
              风险可接受，继续投递
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={isFetching}
              onClick={() => void refetch()}
            >
              {isFetching ? '检测中…' : '重新检测'}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

export function StyleExtractPanel() {
  const extract = useMutation({
    mutationFn: extractAuthorProfile,
  })
  const { data: profile, refetch } = useQuery({
    queryKey: ['taste', 'author-profile'],
    queryFn: fetchAuthorProfile,
  })

  return (
    <div className="card-ui text-left">
      <p className="text-[13px] font-medium">提炼写作风格</p>
      <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
        从本书写作偏好归纳跨书规律，供下一本继承
      </p>
      <Button
        size="sm"
        className="mt-3"
        disabled={extract.isPending}
        onClick={() =>
          extract.mutate(undefined, {
            onSuccess: () => void refetch(),
          })
        }
      >
        {extract.isPending ? '提炼中…' : '开始提炼'}
      </Button>
      {profile?.profile?.rules?.length ? (
        <p className="mt-2 text-[11px] text-[var(--color-success-text)]">
          已有 {profile.profile.rules.length} 条跨书规则
        </p>
      ) : null}
      {extract.error ? (
        <p className="mt-2 text-[11px] text-[var(--color-danger)]">
          {(extract.error as Error).message}
        </p>
      ) : null}
    </div>
  )
}

export function AuthorProfileInherit() {
  const apply = useMutation({
    mutationFn: (inheritAll: boolean) =>
      applyAuthorProfile({ inherit_all: inheritAll }),
  })

  return (
    <div className="card-ui border-dashed text-[13px]">
      <p className="font-medium">继承写作风格</p>
      <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
        从作者档案带入已提炼的规律与读者偏好
      </p>
      <div className="mt-3 flex gap-2">
        <Button size="sm" disabled={apply.isPending} onClick={() => apply.mutate(true)}>
          {apply.isPending ? '处理中…' : '全部继承'}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={apply.isPending}
          onClick={() => apply.mutate(false)}
        >
          全新开始
        </Button>
      </div>
      {apply.error ? (
        <p className="mt-2 text-[11px] text-[var(--color-danger)]">
          {(apply.error as Error).message}
        </p>
      ) : null}
    </div>
  )
}
