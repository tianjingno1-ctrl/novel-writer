import { Button } from '@/components/ui/button'
import { BOOK_FORMATS, GENRE_CHIPS } from '@/lib/bookMeta'
import {
  platformWordsHint,
  resolveWizardChapterCount,
  resolveWordsPerChapter,
  SHORT_CHAPTER_MAX,
  SHORT_CHAPTER_MIN,
  shortWordsPerChapter,
} from '@/lib/wordBudget'
import { useWizardStore } from '@/stores/wizardStore'

const PLATFORMS = [
  { id: 'tomato', label: '番茄' },
  { id: 'midu', label: '米读' },
  { id: 'qimao', label: '七猫' },
  { id: 'short_drama', label: '短剧平台' },
  { id: 'other', label: '其他' },
] as const

type Props = {
  onNext: () => void
  pending?: boolean
}

export function StepBasicInfo({ onNext, pending }: Props) {
  const basicTitle = useWizardStore((s) => s.basicTitle)
  const basicPlatform = useWizardStore((s) => s.basicPlatform)
  const basicBookType = useWizardStore((s) => s.basicBookType)
  const basicGenre = useWizardStore((s) => s.basicGenre)
  const totalWords = useWizardStore((s) => s.totalWords)
  const shortChapterCount = useWizardStore((s) => s.shortChapterCount)
  const novelChapterCount = useWizardStore((s) => s.novelChapterCount)
  const wordsPerChapter = useWizardStore((s) => s.wordsPerChapter)
  const setBasic = useWizardStore((s) => s.setBasic)
  const setTotalWords = useWizardStore((s) => s.setTotalWords)
  const setShortChapterCount = useWizardStore((s) => s.setShortChapterCount)
  const setNovelChapterCount = useWizardStore((s) => s.setNovelChapterCount)
  const setWordsPerChapter = useWizardStore((s) => s.setWordsPerChapter)

  const isShort = basicBookType === 'short'
  const resolvedChapters = resolveWizardChapterCount(
    basicBookType,
    totalWords,
    novelChapterCount,
    basicPlatform,
    shortChapterCount,
  )
  const resolvedWpc = resolveWordsPerChapter(
    basicBookType,
    totalWords,
    resolvedChapters,
    wordsPerChapter,
  )

  return (
    <div className="mx-auto max-w-lg space-y-5 px-4 pb-8">
      <div>
        <h2 className="text-[13px] font-medium">基本信息</h2>
        <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
          书名与平台取向（自动保存）
        </p>
      </div>

      <label className="block space-y-1">
        <span className="text-[11px] text-[var(--color-text-tertiary)]">书名</span>
        <input
          className="h-[30px] w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-3 text-[13px] outline-none"
          value={basicTitle}
          onChange={(e) => setBasic({ title: e.target.value })}
          placeholder="必填"
        />
      </label>

      <label className="block space-y-1">
        <span className="text-[11px] text-[var(--color-text-tertiary)]">平台</span>
        <select
          className="h-[30px] w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-3 text-[13px] outline-none"
          value={basicPlatform}
          onChange={(e) => setBasic({ platform: e.target.value })}
        >
          {PLATFORMS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </label>

      <div className="space-y-2">
        <span className="text-[11px] text-[var(--color-text-tertiary)]">篇幅</span>
        <div className="flex flex-wrap gap-2">
          {BOOK_FORMATS.map((chip) => (
            <button
              key={chip.id}
              type="button"
              onClick={() => setBasic({ bookType: chip.id })}
              className={
                basicBookType === chip.id
                  ? 'chip-selected cursor-pointer'
                  : 'rounded-full border border-[var(--color-border-secondary)] px-2 py-0.5 text-[10px] text-[var(--color-text-tertiary)]'
              }
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card-ui space-y-3">
        <p className="text-[13px] font-medium">篇幅与字数</p>
        {isShort ? (
          <>
            <label className="block space-y-1">
              <span className="text-[11px] text-[var(--color-text-tertiary)]">
                全书目标字数
              </span>
              <input
                type="number"
                min={3000}
                step={500}
                className="h-[30px] w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-3 text-[13px] outline-none"
                value={totalWords}
                onChange={(e) => setTotalWords(Number(e.target.value) || 0)}
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[11px] text-[var(--color-text-tertiary)]">
                目标章数
              </span>
              <input
                type="number"
                min={SHORT_CHAPTER_MIN}
                max={SHORT_CHAPTER_MAX}
                className="h-[30px] w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-3 text-[13px] outline-none"
                value={shortChapterCount}
                onChange={(e) =>
                  setShortChapterCount(Number(e.target.value) || SHORT_CHAPTER_MIN)
                }
              />
            </label>
            <p className="text-[11px] text-[var(--color-text-tertiary)]">
              章均约{' '}
              <strong className="font-medium text-[var(--color-text-secondary)]">
                {shortWordsPerChapter(totalWords, resolvedChapters)}
              </strong>{' '}
              字（{SHORT_CHAPTER_MIN}～{SHORT_CHAPTER_MAX} 章；须满足付费切割结构）
            </p>
          </>
        ) : (
          <>
            <label className="block space-y-1">
              <span className="text-[11px] text-[var(--color-text-tertiary)]">目标章数</span>
              <input
                type="number"
                min={1}
                max={200}
                className="h-[30px] w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-3 text-[13px] outline-none"
                value={novelChapterCount}
                onChange={(e) => setNovelChapterCount(Number(e.target.value) || 1)}
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[11px] text-[var(--color-text-tertiary)]">
                每章目标字数
              </span>
              <input
                type="number"
                min={500}
                step={100}
                className="h-[30px] w-full rounded-[var(--border-radius-md)] border-[0.5px] border-[var(--color-border-secondary)] px-3 text-[13px] outline-none"
                value={wordsPerChapter}
                onChange={(e) => setWordsPerChapter(Number(e.target.value) || 500)}
              />
              <span className="text-[10px] text-[var(--color-text-tertiary)]">
                {platformWordsHint(basicPlatform)} · 全书约{' '}
                {(resolvedChapters * resolvedWpc).toLocaleString()} 字
              </span>
            </label>
          </>
        )}
      </div>

      <div className="space-y-2">
        <span className="text-[11px] text-[var(--color-text-tertiary)]">题材（可选）</span>
        <div className="flex flex-wrap gap-2">
          {GENRE_CHIPS.map((chip) => (
            <button
              key={chip.id}
              type="button"
              onClick={() =>
                setBasic({ genre: basicGenre === chip.id ? '' : chip.id })
              }
              className={
                basicGenre === chip.id
                  ? 'chip-selected cursor-pointer'
                  : 'rounded-full border border-[var(--color-border-secondary)] px-2 py-0.5 text-[10px] text-[var(--color-text-tertiary)]'
              }
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      <Button
        className="w-full"
        disabled={!basicTitle.trim() || pending}
        onClick={onNext}
      >
        {pending ? '保存中…' : '下一步'}
      </Button>
    </div>
  )
}
