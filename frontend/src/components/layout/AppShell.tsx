import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { fetchStatus } from '@/api/endpoints'
import { BottomNav } from '@/components/layout/BottomNav'
import { useBookStore } from '@/stores/bookStore'
import { useUiStore } from '@/stores/uiStore'
import { cn } from '@/lib/utils'

export function AppShell() {
  const location = useLocation()
  const shellMode = useUiStore((s) => s.shellMode)
  const setActiveBookId = useBookStore((s) => s.setActiveBookId)
  const setWriteChapterNum = useBookStore((s) => s.setWriteChapterNum)

  const isWriting = location.pathname.startsWith('/writing')
  const immersive =
    isWriting && (shellMode === 'flow' || shellMode === 'gate')
  const hideChrome =
    immersive ||
    location.pathname.startsWith('/library/new') ||
    shellMode === 'gate'

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    refetchInterval: 60_000,
    enabled: !immersive,
  })

  useEffect(() => {
    if (status?.book_id) {
      setActiveBookId(status.book_id)
    }
    if (status?.write_chapter_num != null) {
      setWriteChapterNum(status.write_chapter_num)
    }
  }, [status, setActiveBookId, setWriteChapterNum])

  return (
    <div className="min-h-screen bg-background">
      {!hideChrome && !isWriting ? (
        <header className="border-b border-border bg-surface/80 px-4 py-3 backdrop-blur-sm">
          <p className="text-sm font-medium">
            {status?.project_title || 'Novel Writer'}
          </p>
        </header>
      ) : null}

      <main
        className={cn(
          hideChrome ? 'min-h-screen' : 'min-h-[calc(100vh-8rem)]',
          !hideChrome && 'pb-20',
        )}
      >
        <Outlet />
      </main>

      {!hideChrome ? <BottomNav /> : null}
    </div>
  )
}
