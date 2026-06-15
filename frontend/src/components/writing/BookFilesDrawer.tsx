import { X } from 'lucide-react'

import { BookFilesPanel } from '@/components/writing/BookFilesPanel'

type Props = {
  bookTitle: string
  /** settings=短篇仅设定；archives=长篇设定+章后档案 */
  mode?: 'settings' | 'archives'
  onClose: () => void
}

export function BookFilesDrawer({
  bookTitle,
  mode = 'archives',
  onClose,
}: Props) {
  const heading = mode === 'settings' ? '本书设定' : '本书档案'
  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-[var(--color-overlay)]"
        aria-label="关闭本书档案"
        onClick={onClose}
      />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col border-l border-[var(--color-border-tertiary)] bg-[var(--color-background-primary)] shadow-xl">
        <header className="flex h-[var(--topbar-height)] shrink-0 items-center justify-between border-b border-[var(--color-border-tertiary)] px-4">
          <div className="min-w-0">
            <h3 className="text-[13px] font-medium">{heading}</h3>
            <p className="truncate text-[11px] text-[var(--color-text-tertiary)]">
              {bookTitle}
            </p>
          </div>
          <button
            type="button"
            className="rounded p-1 text-[var(--color-text-tertiary)] hover:bg-[var(--color-background-secondary)]"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-4">
          <BookFilesPanel embedded />
        </div>
      </aside>
    </>
  )
}
