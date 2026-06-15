import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { fetchStatus } from '@/api/endpoints'
import { Sidebar } from '@/components/layout/Sidebar'
import { ToastHost } from '@/components/ui/toast'
import { useBookStore } from '@/stores/bookStore'
import { cn } from '@/lib/utils'

export function AppShell() {
  const location = useLocation()
  const setActiveBookId = useBookStore((s) => s.setActiveBookId)
  const writeChapterNum = useBookStore((s) => s.writeChapterNum)
  const setWriteChapterNum = useBookStore((s) => s.setWriteChapterNum)
  const lastBookIdRef = useRef<string | null>(null)

  const isWizard = location.pathname.startsWith('/library/new')
  const isWriting = location.pathname.startsWith('/writing')
  const isComplete = location.pathname.startsWith('/complete')
  const hideSidebar = isWizard
  const fullBleed = isWriting || isComplete

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    refetchInterval: 60_000,
  })

  useEffect(() => {
    const bookId = status?.book_id
    if (!bookId) return

    const prevBookId = lastBookIdRef.current
    const bookChanged = prevBookId !== null && prevBookId !== bookId

    if (prevBookId !== bookId) {
      setActiveBookId(bookId)
      if (prevBookId === null || bookChanged) {
        setWriteChapterNum(status.write_chapter_num ?? null)
      }
      lastBookIdRef.current = bookId
      return
    }

    if (writeChapterNum == null && status.write_chapter_num != null) {
      setWriteChapterNum(status.write_chapter_num)
    }
  }, [
    status?.book_id,
    status?.write_chapter_num,
    writeChapterNum,
    setActiveBookId,
    setWriteChapterNum,
  ])

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      {!hideSidebar ? <Sidebar /> : null}
      <ToastHost />

      <div
        className={cn(
          'min-h-screen',
          !hideSidebar && 'pl-[var(--sidebar-width)]',
        )}
      >
        <main
          className={cn(
            'min-h-screen bg-[var(--bg)]',
            !fullBleed && !isWizard && 'page-shell',
          )}
        >
          <Outlet />
        </main>
      </div>
    </div>
  )
}
