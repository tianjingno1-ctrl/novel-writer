import type { ReaderPreviewResult } from '@/api/productApi'

const LEVEL_LABEL: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
  unknown: '—',
}

type Props = {
  reader?: ReaderPreviewResult | null
  loading?: boolean
}

export function PreviewReaderTab({ reader, loading }: Props) {
  if (loading) {
    return <p className="text-sm text-muted">读者视角分析中…</p>
  }
  if (!reader) {
    return (
      <p className="text-sm text-muted">
        采纳前会评估爽点密度与章尾弃文风险
      </p>
    )
  }
  return (
    <div className="space-y-3 text-sm">
      <div className="flex justify-between gap-4">
        <span className="text-muted">爽点密度</span>
        <span className="font-medium">
          {LEVEL_LABEL[reader.payoff_density ?? ''] ?? reader.payoff_density}
        </span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-muted">章尾弃文风险</span>
        <span
          className={
            reader.drop_off_risk === 'high'
              ? 'font-medium text-warning'
              : 'font-medium'
          }
        >
          {LEVEL_LABEL[reader.drop_off_risk ?? ''] ?? reader.drop_off_risk}
        </span>
      </div>
      {reader.drop_off_reason ? (
        <p className="text-xs text-muted leading-relaxed">
          {reader.drop_off_reason}
        </p>
      ) : null}
      {reader.matched_emotions && reader.matched_emotions.length > 0 ? (
        <p className="text-xs text-muted">
          命中情绪节点：{reader.matched_emotions.join(' · ')}
        </p>
      ) : null}
    </div>
  )
}
