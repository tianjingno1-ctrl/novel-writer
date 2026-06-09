import { BookOpen, Rocket, Target } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

type Path = 'quick' | 'deconstruct' | 'import'

const paths: {
  id: Path
  icon: typeof Rocket
  title: string
  desc: string
  href: string
}[] = [
  {
    id: 'quick',
    icon: Rocket,
    title: '我有想法，直接开始写',
    desc: '5 分钟内开始第一章',
    href: '/library/new?mode=quick',
  },
  {
    id: 'deconstruct',
    icon: BookOpen,
    title: '我有一篇爆文想拆解',
    desc: '分析规律，再写自己的',
    href: '/library/new?mode=deconstruct',
  },
  {
    id: 'import',
    icon: Target,
    title: '我已经有大纲，直接导入',
    desc: '跳过方向，直接规划',
    href: '/library/new?mode=import',
  },
]

export function WelcomeStart() {
  const navigate = useNavigate()

  return (
    <div className="mx-auto max-w-md space-y-8 px-4 py-10 text-center">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          欢迎使用 Novel Writer
        </h1>
        <p className="mt-2 text-sm text-muted">你想怎么开始？</p>
      </div>

      <div className="space-y-3">
        {paths.map(({ id, icon: Icon, title, desc, href }) => (
          <button
            key={id}
            type="button"
            className="flex w-full items-start gap-4 rounded-xl border border-border bg-surface p-5 text-left shadow-sm transition-all hover:border-primary/40 hover:shadow-md"
            onClick={() => navigate(href)}
          >
            <div className="rounded-lg bg-accent p-2.5 text-primary">
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <p className="font-medium text-foreground">{title}</p>
              <p className="mt-1 text-sm text-muted">{desc}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
