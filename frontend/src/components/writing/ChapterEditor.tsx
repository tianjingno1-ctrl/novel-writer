import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { saveChapter } from '@/api/productApi'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'

type Props = {
  chapterNum: number
  initialContent: string
  readOnly?: boolean
  onSaved?: (content: string) => void
}

/** 章节编辑器：衬线排版 + 手动保存（轻量富文本，避免打断心流时可只读） */
export function ChapterEditor({
  chapterNum,
  initialContent,
  readOnly = false,
  onSaved,
}: Props) {
  const [draft, setDraft] = useState(initialContent)
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    setDraft(initialContent)
  }, [initialContent])

  const save = useMutation({
    mutationFn: () => saveChapter(chapterNum, draft),
    onSuccess: () => {
      onSaved?.(draft)
      setEditing(false)
    },
  })

  if (readOnly && !editing) {
    return (
      <div className="font-serif text-lg leading-[2] whitespace-pre-wrap text-foreground">
        {draft || (
          <span className="text-muted italic">（暂无正文）</span>
        )}
      </div>
    )
  }

  if (!editing) {
    return (
      <div>
        <div className="font-serif text-lg leading-[2] whitespace-pre-wrap">
          {draft}
        </div>
        {!readOnly ? (
          <Button
            variant="ghost"
            size="sm"
            className="mt-4 text-muted"
            onClick={() => setEditing(true)}
          >
            编辑正文
          </Button>
        ) : null}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <Textarea
        className="min-h-[50vh] font-serif text-base leading-relaxed"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={() => save.mutate()}
          disabled={save.isPending}
        >
          {save.isPending ? '保存中…' : '保存'}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setDraft(initialContent)
            setEditing(false)
          }}
        >
          取消
        </Button>
      </div>
      {save.error ? (
        <p className="text-sm text-danger">{(save.error as Error).message}</p>
      ) : null}
    </div>
  )
}
