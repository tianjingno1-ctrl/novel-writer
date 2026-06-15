import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import {
  fetchBookFile,
  fetchBookFiles,
  saveBookFile,
  type BookFileMeta,
} from '@/api/bookFilesApi'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const GROUP_ORDER = ['setting', 'archive'] as const

function groupFiles(files: BookFileMeta[]) {
  const map = new Map<string, { label: string; items: BookFileMeta[] }>()
  for (const f of files) {
    const g = f.group ?? 'setting'
    const label = f.group_label ?? '书籍设定'
    const row = map.get(g) ?? { label, items: [] }
    row.items.push(f)
    map.set(g, row)
  }
  return GROUP_ORDER.filter((g) => map.has(g)).map((g) => ({
    id: g,
    label: map.get(g)!.label,
    items: map.get(g)!.items,
  }))
}

type Props = {
  /** 抽屉内嵌：省略页级标题，编辑器占满高度 */
  embedded?: boolean
}

export function BookFilesPanel({ embedded = false }: Props) {
  const qc = useQueryClient()
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [savedSnapshot, setSavedSnapshot] = useState('')

  const { data: listData, isLoading: listLoading } = useQuery({
    queryKey: ['book', 'files'],
    queryFn: fetchBookFiles,
  })

  const files = listData?.files ?? []
  const listScope = listData?.scope
  const grouped = useMemo(() => groupFiles(files), [files])

  useEffect(() => {
    if (!activeKey && files.length > 0) {
      setActiveKey(files[0].key)
    }
  }, [activeKey, files])

  const { data: fileData, isFetching: fileLoading } = useQuery({
    queryKey: ['book', 'files', activeKey],
    queryFn: () => fetchBookFile(activeKey!),
    enabled: Boolean(activeKey),
  })

  useEffect(() => {
    const content = fileData?.content ?? ''
    setDraft(content)
    setSavedSnapshot(content)
  }, [fileData?.content, activeKey])

  const dirty = draft !== savedSnapshot

  const save = useMutation({
    mutationFn: () => saveBookFile(activeKey!, draft),
    onSuccess: () => {
      setSavedSnapshot(draft)
      void qc.invalidateQueries({ queryKey: ['book', 'files'] })
      void qc.invalidateQueries({ queryKey: ['book', 'files', activeKey] })
    },
  })

  const activeMeta = files.find((f) => f.key === activeKey)
  const isArchive = activeMeta?.group === 'archive'

  return (
    <div className={cn('flex min-h-0 flex-col', embedded ? 'h-full gap-3' : 'space-y-3')}>
      {!embedded ? (
        <div>
          <p className="text-[13px] font-medium">书籍档案</p>
          <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
            设定（世界观、文风、人物）供续写参考；章后摘要与伏笔由写作流程维护，可在此查看与纠错。
            逐章写什么以「章规划」为准，勿在世界观里重复写每章情节。
          </p>
        </div>
      ) : (
        <p className="shrink-0 text-[11px] text-[var(--color-text-tertiary)]">
          {listScope === 'setting_only'
            ? '本书设定（世界观、文风、人物）；章后摘要由写作流程自动维护。'
            : '设定供 AI 续写参考；章后摘要与伏笔由写作流程写入，可在此纠错。'}
        </p>
      )}

      <div
        className={cn(
          'flex min-h-0 gap-3',
          embedded ? 'flex-1 flex-col sm:flex-row' : 'flex-col lg:flex-row',
        )}
      >
        <ul
          className={cn(
            'flex shrink-0 flex-col gap-3 overflow-y-auto',
            embedded ? 'sm:w-[168px]' : 'lg:w-[180px]',
          )}
        >
          {listLoading ? (
            <li className="text-[11px] text-[var(--color-text-tertiary)]">加载中…</li>
          ) : (
            grouped.map((section) => (
              <li key={section.id}>
                <p className="mb-1 px-1 text-[10px] font-medium uppercase tracking-wide text-[var(--color-text-tertiary)]">
                  {section.label}
                </p>
                <ul className="space-y-0.5">
                  {section.items.map((f) => (
                    <li key={f.key}>
                      <button
                        type="button"
                        onClick={() => setActiveKey(f.key)}
                        className={cn(
                          'w-full rounded-[var(--border-radius-md)] px-2.5 py-2 text-left text-[12px] transition-colors',
                          activeKey === f.key
                            ? 'border-[0.5px] border-[var(--color-border-tertiary)] bg-[var(--color-background-primary)] font-medium'
                            : 'text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]',
                        )}
                      >
                        {f.label}
                        <span className="mt-0.5 block text-[10px] font-normal text-[var(--color-text-tertiary)]">
                          {f.chars ?? 0} 字
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </li>
            ))
          )}
        </ul>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-2">
          {activeMeta ? (
            <p className="shrink-0 text-[11px] text-[var(--color-text-tertiary)]">
              {activeMeta.filename}
              {activeMeta.hint ? ` · ${activeMeta.hint}` : ''}
              {isArchive ? (
                <span className="ml-1 text-[var(--color-warning-text)]">
                  · 平时由写作流程自动更新，手改仅作纠错
                </span>
              ) : null}
            </p>
          ) : null}
          <textarea
            className={cn(
              'w-full resize-none rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] bg-[var(--color-background-primary)] p-3 font-mono text-[12px] leading-relaxed outline-none focus:border-[var(--color-primary)]',
              embedded ? 'min-h-0 flex-1' : 'min-h-[360px] resize-y',
            )}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={!activeKey || fileLoading}
            placeholder={fileLoading ? '加载中…' : 'Markdown 正文'}
          />
          <div className="flex shrink-0 items-center gap-2">
            <Button
              size="sm"
              disabled={!dirty || save.isPending || !activeKey}
              onClick={() => save.mutate()}
            >
              {save.isPending ? '保存中…' : '保存'}
            </Button>
            {dirty ? (
              <span className="text-[11px] text-[var(--color-warning-text)]">未保存</span>
            ) : (
              <span className="text-[11px] text-[var(--color-text-tertiary)]">
                {draft.length} 字
              </span>
            )}
          </div>
          {save.error ? (
            <p className="text-[11px] text-[var(--color-danger)]">
              {(save.error as Error).message}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
