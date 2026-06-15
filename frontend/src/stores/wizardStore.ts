import { create } from 'zustand'

import {
  applyBookTypeWordDefaults,
  clampShortChapterCount,
  DEFAULT_NOVEL_CHAPTER_COUNT,
  DEFAULT_SHORT_CHAPTER_COUNT,
  DEFAULT_SHORT_TOTAL_WORDS,
  DEFAULT_WORDS_PER_CHAPTER,
  deriveShortChapterCount,
  platformDefaultWordsPerChapter,
} from '@/lib/wordBudget'
import type { PlanChapterRow } from '@/lib/chapterRoles'
import type { BookFormatId, GenreId } from '@/lib/bookMeta'

export type WizardStep = 'basic' | 'reference' | 'direction' | 'plan' | 'criteria'

export type DirectionOption = {
  id?: string
  logline?: string
  sell_point?: string
  tone?: string
  hook?: string
  title?: string
  chapter_count?: number
  [key: string]: unknown
}

export type PlanChapter = PlanChapterRow

type WizardState = {
  step: WizardStep
  basicTitle: string
  basicPlatform: string
  basicBookType: BookFormatId
  basicGenre: GenreId | ''
  referenceExcerpt: string
  seed: string
  /** 短篇：全书目标字数 */
  totalWords: number
  /** 短篇：目标章数（3～10） */
  shortChapterCount: number
  /** 长篇：目标章数 */
  novelChapterCount: number
  /** 长篇：每章目标字数（短篇由总字数反推，只读展示） */
  wordsPerChapter: number
  directionOptions: DirectionOption[]
  selectedDirection: DirectionOption | null
  directionLogId: string | null
  planTitle: string
  planChapters: PlanChapter[]
  planLogId: string | null
  deconstructLogId: string | null
  deconstructSummary: string
  setStep: (step: WizardStep) => void
  setBasic: (patch: {
    title?: string
    platform?: string
    bookType?: BookFormatId
    genre?: GenreId | ''
  }) => void
  setTotalWords: (n: number) => void
  setShortChapterCount: (n: number) => void
  setNovelChapterCount: (n: number) => void
  setWordsPerChapter: (n: number) => void
  setReference: (text: string) => void
  setSeed: (text: string) => void
  setDirectionOptions: (opts: DirectionOption[], logId?: string | null) => void
  selectDirection: (opt: DirectionOption) => void
  setPlan: (title: string, chapters: PlanChapter[], logId?: string | null) => void
  setDeconstruct: (summary: string, logId?: string | null) => void
  reset: () => void
}

const initial = {
  step: 'basic' as WizardStep,
  basicTitle: '',
  basicPlatform: 'tomato',
  basicBookType: 'novel' as BookFormatId,
  basicGenre: '' as GenreId | '',
  referenceExcerpt: '',
  seed: '',
  totalWords: DEFAULT_SHORT_TOTAL_WORDS,
  shortChapterCount: DEFAULT_SHORT_CHAPTER_COUNT,
  novelChapterCount: DEFAULT_NOVEL_CHAPTER_COUNT,
  wordsPerChapter: DEFAULT_WORDS_PER_CHAPTER,
  directionOptions: [] as DirectionOption[],
  selectedDirection: null as DirectionOption | null,
  directionLogId: null as string | null,
  planTitle: '',
  planChapters: [] as PlanChapter[],
  planLogId: null as string | null,
  deconstructLogId: null as string | null,
  deconstructSummary: '',
}

export const useWizardStore = create<WizardState>((set) => ({
  ...initial,
  setStep: (step) => set({ step }),
  setBasic: (patch) =>
    set((s) => {
      const bookType = patch.bookType ?? s.basicBookType
      const platform = patch.platform ?? s.basicPlatform
      const bookTypeChanged =
        patch.bookType !== undefined && patch.bookType !== s.basicBookType
      const platformChanged =
        patch.platform !== undefined && patch.platform !== s.basicPlatform
      let totalWords = s.totalWords
      let shortChapterCount = s.shortChapterCount
      let novelChapterCount = s.novelChapterCount
      let wordsPerChapter = s.wordsPerChapter
      if (bookTypeChanged) {
        const d = applyBookTypeWordDefaults(bookType, platform)
        totalWords = d.totalWords
        shortChapterCount = d.shortChapterCount
        novelChapterCount = d.novelChapterCount
        wordsPerChapter = d.wordsPerChapter
      } else if (platformChanged) {
        wordsPerChapter = platformDefaultWordsPerChapter(platform)
        if (bookType === 'short') {
          shortChapterCount = deriveShortChapterCount(totalWords, platform)
        }
      }
      return {
        basicTitle: patch.title ?? s.basicTitle,
        basicPlatform: platform,
        basicBookType: bookType,
        basicGenre: patch.genre !== undefined ? patch.genre : s.basicGenre,
        totalWords,
        shortChapterCount,
        novelChapterCount,
        wordsPerChapter,
      }
    }),
  setTotalWords: (n) => set({ totalWords: Math.max(1000, n) }),
  setShortChapterCount: (n) =>
    set({ shortChapterCount: clampShortChapterCount(n) }),
  setNovelChapterCount: (n) =>
    set({ novelChapterCount: Math.max(1, Math.min(200, n)) }),
  setWordsPerChapter: (n) => set({ wordsPerChapter: Math.max(500, n) }),
  setReference: (text) => set({ referenceExcerpt: text }),
  setSeed: (text) => set({ seed: text }),
  setDirectionOptions: (opts, logId = null) =>
    set({ directionOptions: opts, directionLogId: logId }),
  selectDirection: (opt) => set({ selectedDirection: opt }),
  setPlan: (title, chapters, logId = null) =>
    set({ planTitle: title, planChapters: chapters, planLogId: logId }),
  setDeconstruct: (summary, logId = null) =>
    set({ deconstructSummary: summary, deconstructLogId: logId }),
  reset: () => set(initial),
}))
