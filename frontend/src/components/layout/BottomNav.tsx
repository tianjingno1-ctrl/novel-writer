import { FileText, Library, PenLine, Settings } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { cn } from '@/lib/utils'

const links = [
  { to: '/', label: '书架', icon: Library },
  { to: '/writing', label: '写作', icon: PenLine },
  { to: '/manuscripts', label: '稿件', icon: FileText },
  { to: '/settings', label: '设置', icon: Settings },
] as const

export function BottomNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-lg items-stretch justify-around px-2 pb-[env(safe-area-inset-bottom)]">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex flex-1 flex-col items-center gap-0.5 py-2.5 text-xs transition-colors',
                isActive
                  ? 'text-primary font-medium'
                  : 'text-muted hover:text-foreground',
              )
            }
          >
            <Icon className="h-5 w-5" strokeWidth={1.75} />
            <span>{label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
