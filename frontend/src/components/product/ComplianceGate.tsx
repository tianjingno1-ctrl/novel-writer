import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { fetchCompliancePreview } from '@/api/productApi'
import {
  applyAuthorProfile,
  extractAuthorProfile,
  fetchAuthorProfile,
} from '@/api/tasteApi'
import { Button } from '@/components/ui/button'

type Props = {
  target: string
  onProceed: () => void
  onRevise: (chapters: number[]) => void
}

export function ComplianceGate({ target, onProceed, onRevise }: Props) {
  const [ignored, setIgnored] = useState(false)

  const { data, refetch, isFetching } = useQuery({
    queryKey: ['compliance', 'preview', target],
    queryFn: () => fetchCompliancePreview(target),
    enabled: Boolean(target),
  })

  const risk = data?.risk_level ?? 'unknown'
  const highChapters =
    data?.high_risk_chapters
      ?.map((r) => r.chapter_num)
      .filter((n): n is number => typeof n === 'number') ?? []

  if (ignored || risk === 'low') {
    return (
      <Button className="w-full" size="sm" onClick={onProceed}>
        提交投递记录
      </Button>
    )
  }

  return (
    <div className="mt-3 space-y-3 rounded-lg border border-border bg-accent/30 p-3 text-left text-sm">
      <p className="font-medium">E4c 合规预检</p>
      <p className="text-xs text-muted">
        平台 {data?.platform ?? '—'} · 风险分 {data?.risk_score ?? '—'} ·{' '}
        {risk === 'high' ? '偏高' : risk === 'medium' ? '中等' : '较低'}
      </p>
      {highChapters.length > 0 ? (
        <p className="text-xs text-warning">
          高风险章：第 {highChapters.join('、')} 章（AI 腔片段偏多）
        </p>
      ) : null}
      <div className="flex flex-col gap-2">
        {risk === 'high' ? (
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onRevise(highChapters)}
            >
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
              重新检测
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
    <div className="rounded-xl border border-border p-4 text-left text-sm">
      <p className="font-medium">风格提炼（E8）</p>
      <p className="mt-1 text-xs text-muted">
        从本书口味库提炼跨书规律，写入 author_profile.json
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
        {extract.isPending ? '提炼中…' : '提炼作者风格资产'}
      </Button>
      {profile?.profile?.rules?.length ? (
        <p className="mt-2 text-xs text-muted">
          已有 {profile.profile.rules.length} 条跨书规则
        </p>
      ) : null}
      {extract.error ? (
        <p className="mt-2 text-xs text-danger">
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
    <div className="rounded-xl border border-dashed border-border p-4 text-sm">
      <p className="font-medium">继承作者风格资产</p>
      <p className="mt-1 text-xs text-muted">
        从 author_profile.json 带入规律与 reader_pattern
      </p>
      <div className="mt-3 flex gap-2">
        <Button
          size="sm"
          disabled={apply.isPending}
          onClick={() => apply.mutate(true)}
        >
          全部继承
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={apply.isPending}
          onClick={() => apply.mutate(false)}
        >
          跳过
        </Button>
      </div>
    </div>
  )
}
