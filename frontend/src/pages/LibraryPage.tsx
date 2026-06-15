import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Filter, Plus, RotateCcw, Search, Trash2, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  fetchLibrary,
  fetchLibraryTrash,
  purgeAllTrash,
  purgeBook,
  purgeBooks,
  restoreBook,
  switchBook,
  trashBook,
  trashBooks as trashBooksApi,
} from '@/api/endpoints'
import { isBookWritingReady } from '@/lib/bookReady'
import { refreshAfterBookSwitch } from '@/lib/bookQueryKeys'
import { PageHeader } from '@/components/layout/PageHeader'
import { WelcomeStart } from '@/components/onboarding/WelcomeStart'
import { Button } from '@/components/ui/button'
import { ConfirmModal } from '@/components/ui/ConfirmModal'
import { cn } from '@/lib/utils'
import { toast } from '@/stores/toastStore'
import type { LibraryBook } from '@/types/api'

const PLATFORM_LABEL: Record<string, string> = {
  tomato: '番茄',
  midu: '米读',
  qimao: '七猫',
  short_drama: '短剧',
  other: '其他',
}

type StatusFilter = 'all' | 'draft' | 'active' | 'done'
type ShelfView = 'shelf' | 'trash'

type ConfirmState =
  | { kind: 'trash'; book: LibraryBook; step: 1 | 2 }
  | { kind: 'trash-bulk'; books: LibraryBook[]; step: 1 | 2 }
  | { kind: 'purge'; book: LibraryBook }
  | { kind: 'purge-bulk'; books: LibraryBook[] }
  | { kind: 'purge-all' }
  | null

function bookTitleList(books: LibraryBook[], max = 5): string {
  const titles = books.map((b) => b.title || b.id)
  if (titles.length <= max) return titles.join('、')
  return `${titles.slice(0, max).join('、')} 等 ${titles.length} 本`
}

const STATUS_FILTER_OPTIONS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: '全部状态' },
  { id: 'draft', label: '草稿' },
  { id: 'active', label: '写作中' },
  { id: 'done', label: '已完结' },
]

type BookCardStatus = 'active' | 'done' | 'pending' | 'draft'

function mapShelfStatus(book: LibraryBook): BookCardStatus {
  const st = book.shelf_status
  if (st === 'draft') return 'draft'
  if (st === 'done') return 'done'
  if (st === 'active') return 'active'
  return 'pending'
}

const statusBadge: Record<BookCardStatus, { label: string; className: string }> = {
  active: { label: '写作中', className: 'badge-accent' },
  done: { label: '已完结', className: 'badge-done' },
  pending: { label: '未开始', className: 'badge-done' },
  draft: { label: '草稿', className: 'badge-warn' },
}

const cardAccent: Record<BookCardStatus, string> = {
  active: 'book-card--active',
  done: 'book-card--done',
  pending: '',
  draft: 'book-card--draft',
}

function BookCard({
  book,
  onOpen,
  onTrash,
  opening,
  batchMode,
  selected,
  onToggleSelect,
}: {
  book: LibraryBook
  onOpen: () => void
  onTrash: (e: React.MouseEvent) => void
  opening?: boolean
  batchMode?: boolean
  selected?: boolean
  onToggleSelect?: () => void
}) {
  const status = mapShelfStatus(book)
  const isDraft = status === 'draft'
  const platform = PLATFORM_LABEL[book.platform ?? ''] ?? book.platform ?? '—'
  const progress = book.progress_pct ?? 0
  const chapterLabel = book.chapter_label ?? (isDraft ? '草稿' : '未打开')
  const badge = statusBadge[status]

  return (
    <div className="group relative">
      {batchMode ? (
        <label className="absolute left-2 top-2 z-10 flex cursor-pointer items-center rounded p-1">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggleSelect}
            className="h-4 w-4 accent-[var(--color-primary)]"
            onClick={(e) => e.stopPropagation()}
          />
        </label>
      ) : null}
      <button
        type="button"
        disabled={opening}
        onClick={() => (batchMode ? onToggleSelect?.() : onOpen())}
        className={cn(
          'card-ui book-card flex w-full flex-col gap-3 text-left',
          cardAccent[status],
          isDraft && 'border-dashed',
          opening && 'pointer-events-none opacity-60',
          batchMode && selected && 'ring-2 ring-[var(--color-primary)]',
          batchMode && 'pl-8',
        )}
      >
        <div>
          <p className="pr-8 text-[15px] font-semibold tracking-tight">
            {book.title || book.id}
          </p>
          {book.chapter_label ? (
            <p className="mt-0.5 line-clamp-1 text-[11px] text-[var(--color-text-tertiary)]">
              {book.chapter_label}
            </p>
          ) : null}
          <p className="mt-1 flex gap-3 text-[12px] text-[var(--color-text-tertiary)]">
            <span>{platform}</span>
            <span>{book.type === 'short' ? '短篇' : book.type === 'novel' ? '长篇' : '—'}</span>
          </p>
        </div>
        {!isDraft ? (
          <div>
            <div className="progress-track mb-2">
              <div
                className={cn('progress-fill', status === 'done' && 'progress-fill-success')}
                style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
              />
            </div>
            <div className="flex items-center justify-between">
              <span className={badge.className}>{badge.label}</span>
              <span className="text-[11px] tabular-nums text-[var(--color-text-tertiary)]">
                {chapterLabel} · {progress}%
              </span>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <span className={badge.className}>{badge.label}</span>
            <span className="text-[11px] text-[var(--color-text-tertiary)]">继续向导</span>
          </div>
        )}
      </button>
      {!batchMode ? (
        <button
          type="button"
          title="移入垃圾站"
          className="absolute right-2 top-2 rounded p-1.5 text-[var(--color-text-tertiary)] opacity-0 transition-opacity hover:bg-[var(--color-background-secondary)] hover:text-[var(--color-danger)] group-hover:opacity-100 focus:opacity-100"
          onClick={onTrash}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  )
}

function TrashBookCard({
  book,
  onRestore,
  onPurge,
  pending,
  batchMode,
  selected,
  onToggleSelect,
}: {
  book: LibraryBook
  onRestore: () => void
  onPurge: () => void
  pending?: boolean
  batchMode?: boolean
  selected?: boolean
  onToggleSelect?: () => void
}) {
  const platform = PLATFORM_LABEL[book.platform ?? ''] ?? book.platform ?? '—'
  const trashedAt = book.trashed_at
    ? book.trashed_at.replace('T', ' ').slice(0, 16)
    : '—'

  return (
    <div
      className={cn(
        'card-ui relative flex flex-col gap-3 opacity-90',
        batchMode && selected && 'ring-2 ring-[var(--color-danger)]',
      )}
    >
      {batchMode ? (
        <label className="absolute left-2 top-2 z-10 flex cursor-pointer items-center rounded p-1">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggleSelect}
            className="h-4 w-4 accent-[var(--color-danger)]"
          />
        </label>
      ) : null}
      <div className={cn(batchMode && 'pl-6')}>
        <p className="text-[15px] font-semibold tracking-tight">{book.title || book.id}</p>
        <p className="mt-1 flex gap-3 text-[12px] text-[var(--color-text-tertiary)]">
          <span>{platform}</span>
          <span>{book.type === 'short' ? '短篇' : book.type === 'novel' ? '长篇' : '—'}</span>
        </p>
        <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
          移入于 {trashedAt}
        </p>
      </div>
      {!batchMode ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={pending} onClick={onRestore}>
            <RotateCcw className="mr-1 h-3.5 w-3.5" />
            恢复到书架
          </Button>
          <Button size="sm" variant="outline" disabled={pending} onClick={onPurge}>
            永久删除
          </Button>
        </div>
      ) : null}
    </div>
  )
}

export function LibraryPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [view, setView] = useState<ShelfView>('shelf')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [platformFilter, setPlatformFilter] = useState<string>('all')
  const [filterOpen, setFilterOpen] = useState(false)
  const [confirm, setConfirm] = useState<ConfirmState>(null)
  const [openingBookId, setOpeningBookId] = useState<string | null>(null)
  const [batchMode, setBatchMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const filterRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['library'],
    queryFn: fetchLibrary,
  })

  const { data: trashData, isLoading: trashLoading } = useQuery({
    queryKey: ['library', 'trash'],
    queryFn: fetchLibraryTrash,
  })

  const invalidateShelf = () => {
    void qc.invalidateQueries({ queryKey: ['library'] })
    void qc.invalidateQueries({ queryKey: ['library', 'trash'] })
    void qc.invalidateQueries({ queryKey: ['status'] })
    void qc.invalidateQueries({ queryKey: ['plan'] })
  }

  const doSwitch = useMutation({
    mutationFn: (bookId: string) => switchBook(bookId),
    onSuccess: () => invalidateShelf(),
  })

  const doTrash = useMutation({
    mutationFn: (bookId: string) => trashBook(bookId),
    onSuccess: () => {
      toast('success', '已移入垃圾站')
      setConfirm(null)
      invalidateShelf()
    },
    onError: (e) => toast('warning', (e as Error).message),
  })

  const doTrashBulk = useMutation({
    mutationFn: (bookIds: string[]) => trashBooksApi(bookIds),
    onSuccess: (res) => {
      const failed = res.failed?.length ?? 0
      const count = res.count ?? 0
      if (failed > 0) {
        toast('warning', `已移入 ${count} 本，${failed} 本失败`)
      } else {
        toast('success', `已移入垃圾站 ${count} 本`)
      }
      setConfirm(null)
      setBatchMode(false)
      setSelectedIds([])
      invalidateShelf()
    },
    onError: (e) => toast('warning', (e as Error).message),
  })

  const doRestore = useMutation({
    mutationFn: (bookId: string) => restoreBook(bookId),
    onSuccess: () => {
      toast('success', '已恢复到书架')
      invalidateShelf()
    },
    onError: (e) => toast('warning', (e as Error).message),
  })

  const doPurge = useMutation({
    mutationFn: (bookId: string) => purgeBook(bookId),
    onSuccess: () => {
      toast('success', '已永久删除')
      setConfirm(null)
      invalidateShelf()
    },
    onError: (e) => toast('warning', (e as Error).message),
  })

  const doPurgeBulk = useMutation({
    mutationFn: (bookIds: string[]) => purgeBooks(bookIds),
    onSuccess: (res) => {
      const failed = res.failed?.length ?? 0
      const count = res.count ?? 0
      if (failed > 0) {
        toast('warning', `已永久删除 ${count} 本，${failed} 本失败`)
      } else {
        toast('success', `已永久删除 ${count} 本`)
      }
      setConfirm(null)
      setBatchMode(false)
      setSelectedIds([])
      invalidateShelf()
    },
    onError: (e) => toast('warning', (e as Error).message),
  })

  const doPurgeAll = useMutation({
    mutationFn: () => purgeAllTrash(),
    onSuccess: () => {
      toast('success', '垃圾站已清空')
      setConfirm(null)
      invalidateShelf()
    },
    onError: (e) => toast('warning', (e as Error).message),
  })

  const books = data?.books ?? []
  const trashBooks = trashData?.books ?? []
  /** 仅当书架与垃圾站都空时显示欢迎页（有书在垃圾站仍进书架 UI） */
  const isEmpty =
    !isLoading &&
    !trashLoading &&
    books.length === 0 &&
    trashBooks.length === 0

  const platformOptions = useMemo(() => {
    const set = new Set<string>()
    for (const b of books) {
      if (b.platform) set.add(b.platform)
    }
    return [...set].sort()
  }, [books])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = books.filter((b) => {
      if (q && !(b.title ?? '').toLowerCase().includes(q) && !b.id.toLowerCase().includes(q)) {
        return false
      }
      if (statusFilter !== 'all' && b.shelf_status !== statusFilter) {
        return false
      }
      if (platformFilter !== 'all' && b.platform !== platformFilter) {
        return false
      }
      return true
    })
    const activeId = data?.active_book_id
    return [...list].sort((a, b) => {
      if (a.id === activeId) return -1
      if (b.id === activeId) return 1
      const rank = (book: LibraryBook) => {
        if (book.shelf_status === 'active') return 0
        if (book.shelf_status === 'done') return 1
        if (book.wizard_complete) return 2
        return 3
      }
      return rank(a) - rank(b) || String(b.id).localeCompare(String(a.id))
    })
  }, [books, query, statusFilter, platformFilter, data?.active_book_id])

  const hasActiveFilters = statusFilter !== 'all' || platformFilter !== 'all'
  const actionPending =
    doTrash.isPending ||
    doTrashBulk.isPending ||
    doPurge.isPending ||
    doPurgeBulk.isPending ||
    doPurgeAll.isPending

  const exitBatchMode = () => {
    setBatchMode(false)
    setSelectedIds([])
  }

  const toggleSelected = (bookId: string) => {
    setSelectedIds((prev) =>
      prev.includes(bookId) ? prev.filter((id) => id !== bookId) : [...prev, bookId],
    )
  }

  const selectAllFiltered = () => {
    setSelectedIds(filtered.map((b) => b.id))
  }

  const selectAllTrash = () => {
    setSelectedIds(trashBooks.map((b) => b.id))
  }

  const selectedShelfBooks = useMemo(
    () => filtered.filter((b) => selectedIds.includes(b.id)),
    [filtered, selectedIds],
  )

  const selectedTrashBooks = useMemo(
    () => trashBooks.filter((b) => selectedIds.includes(b.id)),
    [trashBooks, selectedIds],
  )

  useEffect(() => {
    if (!filterOpen) return
    const onDocClick = (e: MouseEvent) => {
      if (filterRef.current && !filterRef.current.contains(e.target as Node)) {
        setFilterOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [filterOpen])

  useEffect(() => {
    exitBatchMode()
  }, [view])

  const openBook = (book: LibraryBook) => {
    setOpeningBookId(book.id)
    doSwitch.mutate(book.id, {
      onSuccess: async () => {
        try {
          const { plan } = await refreshAfterBookSwitch(qc)
          if (isBookWritingReady(plan)) {
            navigate('/writing')
          } else {
            navigate('/library/new?resume=1')
          }
        } catch (e) {
          toast('warning', (e as Error).message || '加载书籍信息失败')
        } finally {
          setOpeningBookId(null)
        }
      },
      onError: (e) => {
        setOpeningBookId(null)
        toast('warning', (e as Error).message || '切换书籍失败')
      },
    })
  }

  const requestTrash = (book: LibraryBook, e: React.MouseEvent) => {
    e.stopPropagation()
    setConfirm({ kind: 'trash', book, step: 1 })
  }

  const handleTrashConfirm = () => {
    if (!confirm || confirm.kind !== 'trash') return
    const isDone = confirm.book.shelf_status === 'done'
    if (isDone && confirm.step === 1) {
      setConfirm({ kind: 'trash', book: confirm.book, step: 2 })
      return
    }
    doTrash.mutate(confirm.book.id)
  }

  const handleTrashBulkConfirm = () => {
    if (!confirm || confirm.kind !== 'trash-bulk') return
    const hasDone = confirm.books.some((b) => b.shelf_status === 'done')
    if (hasDone && confirm.step === 1) {
      setConfirm({ kind: 'trash-bulk', books: confirm.books, step: 2 })
      return
    }
    doTrashBulk.mutate(confirm.books.map((b) => b.id))
  }

  const handlePurgeConfirm = () => {
    if (!confirm || confirm.kind !== 'purge') return
    doPurge.mutate(confirm.book.id)
  }

  const handlePurgeBulkConfirm = () => {
    if (!confirm || confirm.kind !== 'purge-bulk') return
    doPurgeBulk.mutate(confirm.books.map((b) => b.id))
  }

  const clearFilters = () => {
    setStatusFilter('all')
    setPlatformFilter('all')
  }

  const shelfSubtitle = useMemo(() => {
    const total = books.length
    const active = books.filter((b) => b.shelf_status === 'active').length
    const draft = books.filter((b) => b.shelf_status === 'draft').length
    const parts = [`${total} 本书`]
    if (active) parts.push(`${active} 本写作中`)
    if (draft) parts.push(`${draft} 本草稿`)
    if (trashBooks.length) parts.push(`垃圾站 ${trashBooks.length}`)
    return parts.join(' · ')
  }, [books, trashBooks.length])

  const confirmModal = (() => {
    if (!confirm) return null
    if (confirm.kind === 'trash') {
      const title = confirm.book.title || confirm.book.id
      const isDone = confirm.book.shelf_status === 'done'
      if (isDone && confirm.step === 2) {
        return (
          <ConfirmModal
            open
            title="再次确认"
            danger
            pending={actionPending}
            confirmLabel="移入垃圾站"
            message={
              <>
                已完结的<strong>《{title}》</strong>将移入垃圾站。之后可在垃圾站恢复，或手动永久删除。
              </>
            }
            onCancel={() => setConfirm(null)}
            onConfirm={handleTrashConfirm}
          />
        )
      }
      return (
        <ConfirmModal
          open
          title="移入垃圾站？"
          pending={actionPending}
          confirmLabel="移入垃圾站"
          message={
            isDone ? (
              <>
                《{title}》已完结。移入垃圾站后可恢复或永久删除；已完结作品需要再次确认。
              </>
            ) : (
              <>
                《{title}》将从书架移入垃圾站，写作数据仍保留，可随时恢复或永久删除。
              </>
            )
          }
          onCancel={() => setConfirm(null)}
          onConfirm={handleTrashConfirm}
        />
      )
    }
    if (confirm.kind === 'purge') {
      const title = confirm.book.title || confirm.book.id
      return (
        <ConfirmModal
          open
          title="永久删除？"
          danger
          pending={actionPending}
          confirmLabel="永久删除"
          message={
            <>
              《{title}》将被<strong>彻底删除</strong>，章节、规划与档案无法恢复。
            </>
          }
          onCancel={() => setConfirm(null)}
          onConfirm={handlePurgeConfirm}
        />
      )
    }
    if (confirm.kind === 'trash-bulk') {
      const titles = bookTitleList(confirm.books)
      const hasDone = confirm.books.some((b) => b.shelf_status === 'done')
      if (hasDone && confirm.step === 2) {
        return (
          <ConfirmModal
            open
            title="再次确认"
            danger
            pending={actionPending}
            confirmLabel="移入垃圾站"
            message={
              <>
                已完结作品也在选中范围内（{titles}）。移入垃圾站后可恢复或永久删除。
              </>
            }
            onCancel={() => setConfirm(null)}
            onConfirm={handleTrashBulkConfirm}
          />
        )
      }
      return (
        <ConfirmModal
          open
          title={`移入垃圾站？（${confirm.books.length} 本）`}
          pending={actionPending}
          confirmLabel="移入垃圾站"
          message={
            hasDone ? (
              <>
                {titles} 将移入垃圾站。其中含已完结作品，需要再次确认。
              </>
            ) : (
              <>
                {titles} 将从书架移入垃圾站，写作数据仍保留，可随时恢复或永久删除。
              </>
            )
          }
          onCancel={() => setConfirm(null)}
          onConfirm={handleTrashBulkConfirm}
        />
      )
    }
    if (confirm.kind === 'purge-bulk') {
      const titles = bookTitleList(confirm.books)
      return (
        <ConfirmModal
          open
          title={`永久删除？（${confirm.books.length} 本）`}
          danger
          pending={actionPending}
          confirmLabel="永久删除"
          message={
            <>
              {titles} 将被<strong>彻底删除</strong>，章节、规划与档案无法恢复。
            </>
          }
          onCancel={() => setConfirm(null)}
          onConfirm={handlePurgeBulkConfirm}
        />
      )
    }
    return (
      <ConfirmModal
        open
        title="清空垃圾站？"
        danger
        pending={actionPending}
        confirmLabel="全部永久删除"
        message="垃圾站中的所有书籍将被彻底删除，无法恢复。"
        onCancel={() => setConfirm(null)}
        onConfirm={() => doPurgeAll.mutate()}
      />
    )
  })()

  if (isEmpty) {
    return (
      <div className="mx-auto max-w-lg py-8">
        <WelcomeStart />
      </div>
    )
  }

  return (
    <div className="group/shelf">
      {confirmModal}

      <PageHeader
        title={view === 'trash' ? '垃圾站' : '我的书架'}
        subtitle={
          view === 'trash'
            ? `${trashBooks.length} 本待处理 · 恢复或永久删除`
            : shelfSubtitle
        }
        actions={
          <div className="flex flex-wrap gap-2">
            {view === 'shelf' ? (
              <>
                {batchMode ? (
                  <>
                    <Button variant="outline" onClick={exitBatchMode}>
                      取消
                    </Button>
                    <Button variant="outline" onClick={selectAllFiltered} disabled={filtered.length === 0}>
                      全选当前列表
                    </Button>
                    <Button
                      variant="outline"
                      disabled={selectedIds.length === 0}
                      onClick={() => setConfirm({ kind: 'trash-bulk', books: selectedShelfBooks, step: 1 })}
                    >
                      移入垃圾站 ({selectedIds.length})
                    </Button>
                  </>
                ) : (
                  <>
                    {books.length > 0 ? (
                      <Button variant="outline" onClick={() => setBatchMode(true)}>
                        批量管理
                      </Button>
                    ) : null}
                    {trashBooks.length > 0 ? (
                      <Button variant="outline" onClick={() => setView('trash')}>
                        <Trash2 className="mr-1 h-4 w-4" />
                        垃圾站
                        <span className="ml-1 rounded-full bg-[var(--color-background-secondary)] px-1.5 text-[11px]">
                          {trashBooks.length}
                        </span>
                      </Button>
                    ) : null}
                    <Button onClick={() => navigate('/library/new?mode=quick')}>
                      <Plus className="mr-1 h-4 w-4" />
                      新建书
                    </Button>
                  </>
                )}
              </>
            ) : (
              <>
                {batchMode ? (
                  <>
                    <Button variant="outline" onClick={exitBatchMode}>
                      取消
                    </Button>
                    <Button variant="outline" onClick={selectAllTrash} disabled={trashBooks.length === 0}>
                      全选
                    </Button>
                    <Button
                      variant="outline"
                      disabled={selectedIds.length === 0}
                      onClick={() => setConfirm({ kind: 'purge-bulk', books: selectedTrashBooks })}
                    >
                      永久删除 ({selectedIds.length})
                    </Button>
                  </>
                ) : (
                  <>
                    {trashBooks.length > 0 ? (
                      <Button variant="outline" onClick={() => setBatchMode(true)}>
                        批量管理
                      </Button>
                    ) : null}
                    {trashBooks.length > 0 ? (
                      <Button
                        variant="outline"
                        onClick={() => setConfirm({ kind: 'purge-all' })}
                      >
                        清空垃圾站
                      </Button>
                    ) : null}
                    <Button variant="outline" onClick={() => setView('shelf')}>
                      返回书架
                    </Button>
                  </>
                )}
              </>
            )}
          </div>
        }
      />

      {view === 'shelf' ? (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <div className="relative w-[200px]">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-text-tertiary)]" />
              <input
                type="search"
                placeholder="搜索书名…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="h-[34px] w-full rounded-[var(--border-radius-sm)] border border-[var(--color-border)] bg-[var(--color-background-primary)] pl-8 pr-2 text-[13px] outline-none focus:border-[var(--color-primary)]"
              />
            </div>

            <div className="relative" ref={filterRef}>
              <button
                type="button"
                onClick={() => setFilterOpen((v) => !v)}
                className={cn(
                  'flex h-[30px] items-center gap-1 rounded-[var(--border-radius-md)] border-[0.5px] px-2.5 text-[13px] transition-colors',
                  hasActiveFilters
                    ? 'border-[var(--color-primary)] bg-[var(--color-background-primary)] text-[var(--color-primary)]'
                    : 'border-[var(--color-border)] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]',
                )}
                aria-expanded={filterOpen}
                aria-label="筛选"
              >
                <Filter className="h-3.5 w-3.5" />
                筛选
                {hasActiveFilters ? (
                  <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-[var(--color-primary)]" />
                ) : null}
              </button>

              {filterOpen ? (
                <div className="card-ui absolute left-0 top-[calc(100%+6px)] z-20 w-56 space-y-3 shadow-lg">
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-medium">筛选</span>
                    {hasActiveFilters ? (
                      <button
                        type="button"
                        className="text-[11px] text-[var(--color-primary)] hover:underline"
                        onClick={clearFilters}
                      >
                        清除
                      </button>
                    ) : null}
                  </div>

                  <div>
                    <p className="mb-1.5 text-[11px] text-[var(--color-text-tertiary)]">状态</p>
                    <div className="flex flex-wrap gap-1">
                      {STATUS_FILTER_OPTIONS.map((opt) => (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => setStatusFilter(opt.id)}
                          className={cn(
                            'rounded-full px-2 py-0.5 text-[10px] transition-colors',
                            statusFilter === opt.id
                              ? 'badge-soft'
                              : 'border border-[var(--color-border-secondary)] text-[var(--color-text-tertiary)]',
                          )}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {platformOptions.length > 0 ? (
                    <div>
                      <p className="mb-1.5 text-[11px] text-[var(--color-text-tertiary)]">平台</p>
                      <div className="flex flex-wrap gap-1">
                        <button
                          type="button"
                          onClick={() => setPlatformFilter('all')}
                          className={cn(
                            'rounded-full px-2 py-0.5 text-[10px]',
                            platformFilter === 'all'
                              ? 'badge-soft'
                              : 'border border-[var(--color-border-secondary)] text-[var(--color-text-tertiary)]',
                          )}
                        >
                          全部
                        </button>
                        {platformOptions.map((p) => (
                          <button
                            key={p}
                            type="button"
                            onClick={() => setPlatformFilter(p)}
                            className={cn(
                              'rounded-full px-2 py-0.5 text-[10px]',
                              platformFilter === p
                                ? 'badge-soft'
                                : 'border border-[var(--color-border-secondary)] text-[var(--color-text-tertiary)]',
                            )}
                          >
                            {PLATFORM_LABEL[p] ?? p}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>

            {hasActiveFilters ? (
              <button
                type="button"
                className="flex items-center gap-1 text-[11px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
                onClick={clearFilters}
              >
                <X className="h-3 w-3" />
                清除筛选
              </button>
            ) : null}
          </div>

          {isLoading ? (
            <p className="mt-6 text-[11px] text-[var(--color-text-tertiary)]">加载中…</p>
          ) : null}
          {error ? (
            <p className="mt-6 text-[13px] text-[var(--color-danger)]">
              {(error as Error).message}
            </p>
          ) : null}

          {!isLoading && filtered.length === 0 ? (
            <p className="mt-6 text-center text-[13px] text-[var(--color-text-tertiary)]">
              没有匹配的书，试试调整搜索或筛选
            </p>
          ) : null}

          <div className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
            {filtered.map((book) => (
              <BookCard
                key={book.id}
                book={book}
                opening={openingBookId === book.id}
                batchMode={batchMode}
                selected={selectedIds.includes(book.id)}
                onToggleSelect={() => toggleSelected(book.id)}
                onOpen={() => openBook(book)}
                onTrash={(e) => requestTrash(book, e)}
              />
            ))}

            {!batchMode ? (
              <button
                type="button"
                onClick={() => navigate('/library/new?mode=quick')}
                className="card-ui book-card flex min-h-[160px] flex-col items-center justify-center gap-2 border-dashed text-[var(--color-text-tertiary)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
              >
                <Plus className="h-5 w-5" />
                <span className="text-[13px]">新建书</span>
              </button>
            ) : null}
          </div>
        </>
      ) : (
        <>
          {trashLoading ? (
            <p className="mt-6 text-[11px] text-[var(--color-text-tertiary)]">加载中…</p>
          ) : null}
          {!trashLoading && trashBooks.length === 0 ? (
            <p className="mt-8 text-center text-[13px] text-[var(--color-text-tertiary)]">
              垃圾站是空的
            </p>
          ) : (
            <div className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
              {trashBooks.map((book) => (
                <TrashBookCard
                  key={book.id}
                  book={book}
                  batchMode={batchMode}
                  selected={selectedIds.includes(book.id)}
                  onToggleSelect={() => toggleSelected(book.id)}
                  pending={doRestore.isPending || doPurge.isPending || doPurgeBulk.isPending}
                  onRestore={() => doRestore.mutate(book.id)}
                  onPurge={() => setConfirm({ kind: 'purge', book })}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
