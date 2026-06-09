import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { createBook, fetchLibrary, switchBook } from '@/api/endpoints'
import { WelcomeStart } from '@/components/onboarding/WelcomeStart'
import { Button } from '@/components/ui/button'
import type { LibraryBook } from '@/types/api'

export function LibraryPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['library'],
    queryFn: fetchLibrary,
  })

  const doSwitch = useMutation({
    mutationFn: (bookId: string) => switchBook(bookId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['library'] })
      void qc.invalidateQueries({ queryKey: ['status'] })
    },
  })

  const doCreate = useMutation({
    mutationFn: () => createBook({ title: '新书', type: 'short', platform: 'tomato' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['library'] })
      navigate('/library/new?mode=quick')
    },
  })

  const books = data?.books ?? []
  const activeId = data?.active_book_id ?? ''
  const isEmpty = !isLoading && books.length === 0

  if (isEmpty) {
    return (
      <div className="pb-24">
        <WelcomeStart />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-lg space-y-4 px-4 pb-24">
      <div className="flex items-center justify-between pt-2">
        <h1 className="text-xl font-semibold">书架</h1>
        <Button
          size="sm"
          variant="outline"
          onClick={() => navigate('/library/new?mode=quick')}
        >
          新书
        </Button>
      </div>

      {isLoading ? <p className="text-sm text-muted">加载中…</p> : null}
      {error ? (
        <p className="text-sm text-danger">{(error as Error).message}</p>
      ) : null}

      <div className="space-y-3">
        {books.map((book: LibraryBook) => (
          <button
            key={book.id}
            type="button"
            className={`w-full rounded-xl border bg-surface p-4 text-left shadow-sm transition-colors hover:border-primary/40 ${
              book.id === activeId ? 'border-primary' : 'border-border'
            }`}
            onClick={() => {
              if (book.id !== activeId) {
                doSwitch.mutate(book.id)
              } else {
                navigate('/writing')
              }
            }}
          >
            <p className="font-medium">{book.title || book.id}</p>
            <p className="mt-1 text-xs text-muted">
              {book.type ?? 'novel'} · {book.platform ?? '—'}
              {book.id === activeId ? ' · 当前' : ''}
            </p>
          </button>
        ))}
      </div>

      <Button
        variant="ghost"
        className="w-full text-muted"
        onClick={() => doCreate.mutate()}
        disabled={doCreate.isPending}
      >
        快速新建（跳过引导）
      </Button>
    </div>
  )
}
