import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { clearChatSession, restoreChatSession } from '@/api/endpoints'
import { Button } from '@/components/ui/button'
import type { AppStatus } from '@/types/api'

type Props = {
  status: AppStatus | undefined
  onRestored?: (chapterNum?: number) => void
}

function dismissKey(status: AppStatus) {
  return `session-dismiss:${status.book_id ?? 'default'}:${status.session_saved_at ?? ''}`
}

export function SessionRecoveryBanner({ status, onRestored }: Props) {
  const qc = useQueryClient()
  const [hidden, setHidden] = useState(false)

  if (!status?.session_on_disk || hidden) {
    return null
  }
  if (typeof window !== 'undefined' && sessionStorage.getItem(dismissKey(status)) === '1') {
    return null
  }

  const historyLen = status.history_len ?? 0
  const needsRestore = historyLen === 0

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['status'] })
    void qc.invalidateQueries({ queryKey: ['chat', 'history'] })
  }

  const restore = useMutation({
    mutationFn: restoreChatSession,
    onSuccess: (data) => {
      invalidate()
      const num = Number(data.chapter_num ?? data.write_chapter_num ?? 0)
      onRestored?.(num > 0 ? num : undefined)
    },
  })

  const discard = useMutation({
    mutationFn: clearChatSession,
    onSuccess: () => {
      sessionStorage.setItem(dismissKey(status), '1')
      invalidate()
    },
  })

  const dismiss = () => {
    sessionStorage.setItem(dismissKey(status), '1')
    setHidden(true)
  }

  const busy = restore.isPending || discard.isPending

  return (
    <div className="mx-4 mb-3 rounded-[var(--border-radius-md)] border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2 text-[12px]">
      <p className="font-medium text-[var(--color-warning-text)]">
        {needsRestore ? '检测到未恢复的续写会话' : '续写上下文已就绪'}
      </p>
      <p className="mt-0.5 text-[11px] text-[var(--color-text-secondary)]">
        {status.session_saved_at ? `保存于 ${status.session_saved_at}` : '磁盘备份'}
        {status.session_chapter_num ? ` · 第 ${status.session_chapter_num} 章` : ''}
        {!needsRestore && historyLen > 0 ? ` · ${historyLen} 条对话` : ''}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {needsRestore ? (
          <Button size="sm" disabled={busy} onClick={() => restore.mutate()}>
            {restore.isPending ? '恢复中…' : '恢复会话'}
          </Button>
        ) : (
          <Button size="sm" disabled={busy} onClick={dismiss}>
            知道了
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => discard.mutate()}
        >
          丢弃备份
        </Button>
      </div>
      {restore.error ? (
        <p className="mt-1 text-[11px] text-[var(--color-danger)]">
          {(restore.error as Error).message}
        </p>
      ) : null}
    </div>
  )
}
