import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'

import {
  decideDiagnosis,
  fetchDiagnosis,
  previewPromptPatch,
  rerunPreview,
  runPromptDiagnose,
  type DiagnoseSuspect,
} from '@/api/productApi'
import { fetchPromptNode, PROMPT_SOURCE_LABEL } from '@/api/promptsApi'
import { fetchAuthorProfile } from '@/api/tasteApi'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { toast } from '@/stores/toastStore'

type RerunScope = 'chapter_only' | 'from_chapter_n' | 'plan_only' | 'none'

const NODE_LABEL: Record<string, string> = {
  'writing.main': '正文写作',
  'review.platform': '平台审阅',
  'prefill.direction': '故事方向',
  'prefill.plan': '章规划',
  'maintain.summary': '章节摘要',
  'check.deconstruct': '参考拆文',
  'diagnose.prompt': '归因诊断',
}

function friendlyNode(nodeId?: string): string {
  if (!nodeId) return '写作流程'
  return NODE_LABEL[nodeId] ?? '写作指令'
}

type Props = {
  qualityLogId?: string
  diagnosisId?: string
  chapterNum: number
  onClose: () => void
  /** executedRerun：是否已触发 P4 清章/重规划，前端应自动开写 */
  onDone: (opts?: { executedRerun: boolean }) => void
}

export function AttributionRulesDrawer({
  qualityLogId = '',
  diagnosisId: diagnosisIdProp = '',
  chapterNum,
  onClose,
  onDone,
}: Props) {
  const [scope, setScope] = useState<RerunScope>('from_chapter_n')
  const [fromChapter, setFromChapter] = useState(chapterNum)
  const [patchText, setPatchText] = useState('')
  const [nodeId, setNodeId] = useState('writing.main')
  const [preview, setPreview] = useState('')
  const [applyAuthorProfile, setApplyAuthorProfile] = useState(false)
  const [profileBookId, setProfileBookId] = useState('')

  const diagnose = useQuery({
    queryKey: ['diagnose', qualityLogId],
    queryFn: () => runPromptDiagnose(qualityLogId),
    enabled: Boolean(qualityLogId) && !diagnosisIdProp,
  })

  const existingDiagnosis = useQuery({
    queryKey: ['diagnosis', diagnosisIdProp],
    queryFn: () => fetchDiagnosis(diagnosisIdProp),
    enabled: Boolean(diagnosisIdProp),
  })

  const resolvedDiagnosisId =
    diagnose.data?.diagnosis_id ?? diagnosisIdProp ?? ''

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

  useEffect(() => {
    const doc = existingDiagnosis.data?.diagnosis
    if (!doc) return
    const patch = doc.patch
    const append = patch?.override?.append
    if (append) setPatchText(append)
    if (patch?.target_node) setNodeId(patch.target_node)
  }, [existingDiagnosis.data])

  const { data: authorProfileData } = useQuery({
    queryKey: ['taste', 'author-profile'],
    queryFn: fetchAuthorProfile,
  })
  const profileBooks = authorProfileData?.profile?.books ?? []

  const currentPrompt = useQuery({
    queryKey: ['prompts', 'node', nodeId],
    queryFn: () => fetchPromptNode(nodeId),
    enabled: Boolean(nodeId),
  })

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
      const diagnosisId = resolvedDiagnosisId
      if (!diagnosisId) throw new Error('无诊断记录')
      const hasPatch = Boolean(patchText.trim())
      if (hasPatch) {
        const saved = await previewPromptPatch({
          node_id: nodeId,
          suggested_patch: patchText,
          patch_mode: 'append',
          save: true,
        })
        if (saved && typeof saved === 'object' && saved.ok === false) {
          throw new Error(String(saved.error ?? '规则写入失败'))
        }
      }
      const decided = await decideDiagnosis(diagnosisId, {
        accepted: true,
        rerun_scope: scope === 'none' ? 'none' : scope,
        from_chapter_num: fromChapter,
        apply_override: !hasPatch,
        execute_rerun: scope !== 'none',
        apply_author_profile: applyAuthorProfile,
        author_profile_book_id: profileBookId,
      })
      if (decided && typeof decided === 'object' && decided.ok === false) {
        throw new Error(String(decided.error ?? '应用诊断失败'))
      }
      return { decided, executedRerun: scope !== 'none' }
    },
    onSuccess: ({ executedRerun }) => {
      toast('success', executedRerun ? '规则已应用，正在重写本章' : '诊断规则已应用')
      onDone({ executedRerun })
    },
  })

  const loading = diagnose.isLoading || existingDiagnosis.isLoading
  const summary =
    diagnose.data?.diagnosis?.summary ??
    existingDiagnosis.data?.diagnosis?.analysis

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-[var(--color-overlay)]"
        aria-label="关闭诊断"
        onClick={onClose}
      />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-[var(--color-border-tertiary)] bg-[var(--color-background-primary)] shadow-xl">
        <header className="flex h-[var(--topbar-height)] shrink-0 items-center justify-between border-b border-[var(--color-border-tertiary)] px-4">
          <h3 className="text-[13px] font-medium">诊断</h3>
          <button
            type="button"
            className="rounded p-1 text-[var(--color-text-tertiary)] hover:bg-[var(--color-background-secondary)]"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center gap-2 text-[13px] text-[var(--color-text-tertiary)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在分析差距…
            </div>
          ) : null}

          {diagnose.error ? (
            <p className="text-[13px] text-[var(--color-danger)]">
              {(diagnose.error as Error).message}
            </p>
          ) : null}
          {existingDiagnosis.error ? (
            <p className="text-[13px] text-[var(--color-danger)]">
              {(existingDiagnosis.error as Error).message}
            </p>
          ) : null}

          {summary ? (
            <div className="ai-note mt-2">
              <p className="font-medium">分析结果</p>
              <p className="mt-1 text-[11px] leading-relaxed">{summary}</p>
            </div>
          ) : null}

          {suspect ? (
            <div className="card-ui mt-3">
              <p className="text-[11px] text-[var(--color-text-tertiary)]">
                可能原因 · {friendlyNode(suspect.node_id)}
              </p>
              <p className="mt-1 text-[13px]">{suspect.reason}</p>
            </div>
          ) : null}

          {nodeId ? (
            <div className="mt-3 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] font-medium text-[var(--color-text-tertiary)]">
                  当前指令 · {friendlyNode(nodeId)}
                </p>
                <Link
                  to={`/settings?tab=prompts&node=${encodeURIComponent(nodeId)}`}
                  className="text-[11px] text-[var(--color-accent)] hover:underline"
                  onClick={onClose}
                >
                  在设置中查看
                </Link>
              </div>
              {currentPrompt.isLoading ? (
                <p className="text-[11px] text-[var(--color-text-tertiary)]">加载中…</p>
              ) : (
                <pre className="max-h-28 overflow-auto rounded-[var(--border-radius-md)] bg-[var(--color-background-secondary)] p-2 text-[10px] leading-relaxed whitespace-pre-wrap">
                  {String(currentPrompt.data?.system ?? '').slice(0, 600)}
                  {(currentPrompt.data?.system?.length ?? 0) > 600 ? '…' : ''}
                </pre>
              )}
              {currentPrompt.data?.prompt_source ? (
                <p className="text-[10px] text-[var(--color-text-tertiary)]">
                  来源：
                  {PROMPT_SOURCE_LABEL[currentPrompt.data.prompt_source] ??
                    currentPrompt.data.prompt_source}
                </p>
              ) : null}
            </div>
          ) : null}

          <label className="mt-4 block text-[11px] font-medium text-[var(--color-text-tertiary)]">
            建议调整的写作规则
          </label>
          <Textarea
            className="mt-1 min-h-24 text-[13px]"
            value={patchText}
            onChange={(e) => setPatchText(e.target.value)}
            placeholder="例如：减少总结性旁白，对话要更口语化"
          />

          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => previewMut.mutate()}
              disabled={previewMut.isPending || !patchText.trim()}
            >
              {previewMut.isPending ? '生成中…' : '预览效果'}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => impactMut.mutate()}
              disabled={impactMut.isPending}
            >
              {impactMut.isPending ? '计算中…' : '看重写范围'}
            </Button>
          </div>

          {preview ? (
            <pre className="mt-3 max-h-40 overflow-auto rounded-[var(--border-radius-md)] bg-[var(--color-background-secondary)] p-2 text-[11px] leading-relaxed">
              {preview}
            </pre>
          ) : null}
          {impactMut.data?.impact_preview ? (
            <p className="ai-warn mt-2 whitespace-pre-wrap text-[11px]">
              {String(impactMut.data.impact_preview).slice(0, 400)}
            </p>
          ) : null}

          <p className="mt-6 text-[13px] font-medium">应用后如何重写？</p>
          <div className="card-ui mt-2 space-y-2 border-dashed">
            <label className="flex items-start gap-2 text-[13px]">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={applyAuthorProfile}
                onChange={(e) => setApplyAuthorProfile(e.target.checked)}
              />
              <span>
                同时注入作者风格档案
                <span className="block text-[11px] text-[var(--color-text-tertiary)]">
                  使用已提炼的跨书写作规律
                </span>
              </span>
            </label>
            {applyAuthorProfile && profileBooks.length > 0 ? (
              <select
                className="h-[30px] w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-2 text-[13px] outline-none"
                value={profileBookId}
                onChange={(e) => setProfileBookId(e.target.value)}
              >
                <option value="">当前书 / 全部规则</option>
                {profileBooks.map((b) => (
                  <option key={b.book_id} value={b.book_id ?? ''}>
                    {b.book_title ?? b.book_id}
                  </option>
                ))}
              </select>
            ) : null}
          </div>

          <div className="mt-3 space-y-2 text-[13px]">
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
              <div className="ml-6 flex items-center gap-2 text-[11px] text-[var(--color-text-tertiary)]">
                从第
                <input
                  type="number"
                  min={1}
                  className="h-[26px] w-16 rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-2 text-[13px] outline-none"
                  value={fromChapter}
                  onChange={(e) => setFromChapter(Number(e.target.value))}
                />
                章开始
              </div>
            ) : null}
          </div>
        </div>

        <footer className="flex gap-2 border-t border-[var(--color-border-tertiary)] p-4">
          <Button variant="outline" className="flex-1" onClick={onClose}>
            取消
          </Button>
          <Button
            className="flex-1"
            disabled={applyMut.isPending || !resolvedDiagnosisId}
            onClick={() => applyMut.mutate()}
          >
            {applyMut.isPending ? '应用中…' : '应用并重写'}
          </Button>
        </footer>
        {applyMut.error ? (
          <p className="px-4 pb-4 text-[11px] text-[var(--color-danger)]">
            {(applyMut.error as Error).message}
          </p>
        ) : null}
      </aside>
    </>
  )
}
