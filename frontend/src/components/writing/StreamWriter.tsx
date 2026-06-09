import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useSSEStream } from '@/hooks/useSSEStream'
import { useBookStore } from '@/stores/bookStore'
import type { ChatStreamRequest } from '@/types/api'

export function StreamWriter() {
  const writeChapterNum = useBookStore((s) => s.writeChapterNum)
  const [instruction, setInstruction] = useState('续写本章')
  const { streaming, text, error, lastEvent, start, stop, reset } =
    useSSEStream()

  const handleSend = () => {
    const body: ChatStreamRequest = {
      instruction: instruction.trim() || '续写本章',
      chapter_num: writeChapterNum,
    }
    void start('/api/chat/stream', body)
  }

  const done =
    lastEvent && lastEvent.type === 'done' ? lastEvent : null

  return (
    <Card>
      <CardHeader>
        <CardTitle>流式写书 · POST /api/chat/stream</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <textarea
          className="min-h-24 w-full rounded-md border border-border bg-background p-3 text-sm"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="写作指令"
          disabled={streaming}
        />
        <div className="flex gap-2">
          <Button onClick={handleSend} disabled={streaming}>
            {streaming ? '生成中…' : '发送'}
          </Button>
          <Button variant="outline" onClick={stop} disabled={!streaming}>
            停止
          </Button>
          <Button variant="ghost" onClick={reset}>
            清空
          </Button>
        </div>
        <p className="text-xs text-muted">
          SSE 事件格式：<code>type: chunk</code> + <code>text</code>，结束为{' '}
          <code>type: done</code>
        </p>
        {error ? (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
        ) : null}
        {text ? (
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-accent/50 p-3 text-sm">
            {text}
          </pre>
        ) : null}
        {done ? (
          <p className="text-xs text-muted">
            完成 · 第 {done.chapter_num} 章
            {done.chapter_saved ? ' · 已落盘' : ' · 预览待采纳'}
            {done.cost != null ? ` · 本次 ¥${done.cost.toFixed(4)}` : ''}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
