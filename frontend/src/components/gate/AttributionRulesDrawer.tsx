import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import {
  decideDiagnosis,
  previewPromptPatch,
  rerunPreview,
  runPromptDiagnose,
  type DiagnoseSuspect,
} from '@/api/productApi'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'

type RerunScope = 'chapter_only' | 'from_chapter_n' | 'plan_only' | 'none'

type Props = {
  qualityLogId: string
  chapterNum: number
  onClose: () => void
  onDone: () => void
}

export function AttributionRulesDrawer({
  qualityLogId,
  chapterNum,
  onClose,
  onDone,
}: Props) {
  const [scope, setScope] = useState<RerunScope>('from_chapter_n')
  const [fromChapter, setFromChapter] = useState(chapterNum)
  const [patchText, setPatchText] = useState('')
  const [nodeId, setNodeId] = useState('writing.main')
  const [preview, setPreview] = useState('')

  const diagnose = useQuery({
    queryKey: ['diagnose', qualityLogId],
    queryFn: () => runPromptDiagnose(qualityLogId),
    enabled: Boolean(qualityLogId),
  })

  const suspect: DiagnoseSuspect | undefined =
    diagnose.data?.diagnosis?.suspects?.[0]

  useEffect(() => {
    if (suspect?.suggested_patch) {
      setPatchText(suspect.suggested_patch)
    }
    if (suspect?.node_id) {
      setNodeId(suspect.node_id)
    }
  }, [suspect])

  const previewMut = useMutation({
    mutationFn: () =>
      previewPromptPatch({
        node_id: nodeId,
        suggested_patch: patchText,
        patch_mode: 'append',
        save: false,
      }),
    onSuccess: (data) => {
      setPreview(String(data.preview_system ?? '').slice(0, 1200))
    },
  })

  const impactMut = useMutation({
    mutationFn: () =>
      rerunPreview({
        scope,
        from_chapter_num: fromChapter,
        current_chapter_num: chapterNum,
      }),
  })

  const applyMut = useMutation({
    mutationFn: async () => {
      const diagnosisId = diagnose.data?.diagnosis_id
      if (!diagnosisId) {
        throw new Error('无诊断记录')
      }
      await previewPromptPatch({
        node_id: nodeId,
        suggested_patch: patchText,
        patch_mode: 'append',
        save: true,
      })
      return decideDiagnosis(diagnosisId, {
        accepted: true,
        rerun_scope: scope === 'none' ? 'none' : scope,
        from_chapter_num: fromChapter,
        apply_override: true,
        execute_rerun: scope !== 'none',
      })
    },
    onSuccess: () => onDone(),
  })

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-surface shadow-xl">
      <div className="flex-1 overflow-auto p-6">
        <h3 className="text-lg font-semibold">🔧 找到问题根源</h3>

        {diagnose.isLoading ? (
          <p className="mt-4 text-sm text-muted">正在分析…</p>
        ) : null}
        {diagnose.error ? (
          <p className="mt-4 text-sm text-danger">
            {(diagnose.error as Error).message}
          </p>
        ) : null}

        {diagnose.data?.diagnosis?.summary ? (
          <p className="mt-3 text-sm text-muted leading-relaxed">
            {diagnose.data.diagnosis.summary}
          </p>
        ) : null}

        {suspect ? (
          <div className="mt-4 rounded-lg border border-border bg-accent/40 p-3 text-sm">
            <p className="font-medium">{suspect.node_id}</p>
            <p className="mt-1 text-muted">{suspect.reason}</p>
          </div>
        ) : null}

        <label className="mt-4 block text-xs font-medium text-muted">
          建议改成
        </label>
        <Textarea
          className="mt-1 font-mono text-xs"
          value={patchText}
          onChange={(e) => setPatchText(e.target.value)}
        />

        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => previewMut.mutate()}
            disabled={previewMut.isPending || !patchText.trim()}
          >
            预览 patch
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => impactMut.mutate()}
            disabled={impactMut.isPending}
          >
            看重跑影响
          </Button>
        </div>

        {preview ? (
          <pre className="mt-3 max-h-40 overflow-auto rounded-md bg-background p-2 text-xs">
            {preview}
          </pre>
        ) : null}
        {impactMut.data?.impact_preview ? (
          <p className="mt-2 text-xs text-muted whitespace-pre-wrap">
            {String(impactMut.data.impact_preview).slice(0, 400)}
          </p>
        ) : null}

        <p className="mt-6 text-sm font-medium">改了之后，重新写：</p>
        <div className="mt-2 space-y-2 text-sm">
          {(
            [
              ['chapter_only', '只重写本章'],
              ['from_chapter_n', '从本章往后都重写'],
              ['plan_only', '只重新规划'],
            ] as const
          ).map(([val, label]) => (
            <label key={val} className="flex items-center gap-2">
              <input
                type="radio"
                name="rerun-scope"
                checked={scope === val}
                onChange={() => setScope(val)}
              />
              {label}
            </label>
          ))}
          {scope === 'from_chapter_n' ? (
            <input
              type="number"
              min={1}
              className="ml-6 w-20 rounded border border-border px-2 py-1 text-sm"
              value={fromChapter}
              onChange={(e) => setFromChapter(Number(e.target.value))}
            />
          ) : null}
        </div>
      </div>

      <div className="flex gap-2 border-t border-border p-4">
        <Button variant="outline" className="flex-1" onClick={onClose}>
          不改
        </Button>
        <Button
          className="flex-1"
          disabled={applyMut.isPending || !diagnose.data?.diagnosis_id}
          onClick={() => applyMut.mutate()}
        >
          {applyMut.isPending ? '执行中…' : '改，重新写'}
        </Button>
      </div>
      {applyMut.error ? (
        <p className="px-4 pb-4 text-xs text-danger">
          {(applyMut.error as Error).message}
        </p>
      ) : null}
    </div>
  )
}
