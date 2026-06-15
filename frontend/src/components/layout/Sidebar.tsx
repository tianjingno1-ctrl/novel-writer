import { useQuery } from '@tanstack/react-query'
import {
  BookOpen,
  FileText,
  Heart,
  PenLine,
  Settings,
  Sparkles,
} from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'

import { fetchLibrary, fetchStatus } from '@/api/endpoints'
import { cn } from '@/lib/utils'

const MAIN_LINKS = [
  { to: '/', label: '书架', icon: BookOpen, end: true },
  { to: '/writing', label: '写作', icon: PenLine, end: false, showBadge: true },
  { to: '/manuscripts', label: '稿件', icon: FileText, end: false },
  { to: '/settings', label: '设置', icon: Settings, end: false, exactSettings: true },
] as const

const TASTE_LINKS = [
  { to: '/settings?tab=taste', label: '偏好规则', icon: Heart },
] as const

function NavItem({
  to,
  label,
  icon: Icon,
  end,
  badge,
  active,
  disabled,
  disabledTitle,
}: {
  to: string
  label: string
  icon: typeof BookOpen
  end?: boolean
  badge?: number
  active?: boolean
  disabled?: boolean
  disabledTitle?: string
}) {
  if (disabled) {
    return (
      <span
        title={disabledTitle}
        className="relative flex cursor-not-allowed items-center gap-2.5 px-5 py-2 text-[13px] text-[var(--color-text-light)] opacity-50"
      >
        <Icon className="h-[18px] w-[18px] shrink-0" strokeWidth={1.75} />
        <span>{label}</span>
      </span>
    )
  }

  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          'relative flex items-center gap-2.5 px-5 py-2 text-[13px] transition-colors',
          (active ?? isActive)
            ? 'bg-[var(--color-background-secondary)] font-medium text-[var(--color-primary)]'
            : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-background-secondary)] hover:text-[var(--color-text-primary)]',
          (active ?? isActive) &&
            'before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:rounded-r before:bg-[var(--color-primary)]',
        )
      }
    >
      <Icon className="h-[18px] w-[18px] shrink-0" strokeWidth={1.75} />
      <span>{label}</span>
      {badge && badge > 0 ? (
        <span className="ml-auto rounded-full bg-[var(--color-warning)] px-1.5 py-0.5 text-[10px] font-semibold text-white">
          {badge}
        </span>
      ) : null}
    </NavLink>
  )
}

export function Sidebar() {
  const location = useLocation()

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
  })
  const { data: library } = useQuery({
    queryKey: ['library'],
    queryFn: fetchLibrary,
  })

  const activeWritingCount =
    library?.books?.filter((b) => b.shelf_status === 'active').length ?? 0

  const settingsActive =
    location.pathname.startsWith('/settings') &&
    !location.search.includes('tab=taste')

  const tasteActive = location.pathname.startsWith('/settings') &&
    location.search.includes('tab=taste')

  const modelLabel =
    status?.model ?? status?.provider_name ?? status?.provider ?? '未配置'
  const hasActiveBook = Boolean((status?.book_id ?? '').trim())

  return (
    <aside className="fixed inset-y-0 left-0 z-50 flex w-[var(--sidebar-width)] flex-col border-r border-[var(--border)] bg-[var(--surface)]">
      <div className="border-b border-[var(--border)] px-5 py-5">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-[var(--color-primary)]" strokeWidth={2} />
          <div>
            <p className="text-[15px] font-bold tracking-tight">Novel Writer</p>
            <p className="text-[11px] text-[var(--color-text-tertiary)]">本地写作台</p>
          </div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 py-2">
        {MAIN_LINKS.map((link) => (
          <NavItem
            key={link.to}
            to={link.to}
            label={link.label}
            icon={link.icon}
            end={link.end}
            badge={'showBadge' in link && link.showBadge ? activeWritingCount : undefined}
            disabled={link.to === '/writing' && !hasActiveBook}
            disabledTitle={link.to === '/writing' ? '请先在书架选择或新建一本书' : undefined}
            active={
              'exactSettings' in link && link.exactSettings ? settingsActive : undefined
            }
          />
        ))}

        <p className="px-5 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-light)]">
          口味库
        </p>
        {TASTE_LINKS.map((link) => (
          <NavItem
            key={link.to}
            to={link.to}
            label={link.label}
            icon={link.icon}
            active={tasteActive}
          />
        ))}
      </nav>

      <div className="border-t border-[var(--border)] px-5 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)] text-[12px] font-semibold text-white">
            作
          </div>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium">本地作者</p>
            <p className="truncate text-[11px] text-[var(--color-text-tertiary)]">
              {modelLabel}
            </p>
          </div>
        </div>
      </div>
    </aside>
  )
}
